#!/usr/bin/env python3
"""Year-round shade model for any yard described by a site.json.

    python3 -m lib.sunmodel <slug> [--cell 6] [--outdir maps] [--quick]

Method
------
The yard floor is divided into a grid. For each cell, opaque obstructions are
reduced once to an obstruction horizon: the maximum blocked altitude in each of
360 azimuth bins, computed analytically from vertical wall segments rather than by
point sampling, so a fence six inches away produces no aliasing gaps.

Tree crowns cannot go in that horizon, because light passes underneath them
through the bare trunks. They are modelled as ellipsoids and tested with an exact
ray-ellipsoid intersection at every time step, which is what makes crown base
height matter in the results rather than being quietly averaged away.

The sun is stepped every five minutes in apparent solar time from sunrise to
sunset on a representative day for each month. Each step contributes its five
minutes fully if the beam is clear, nothing if an opaque obstruction blocks it,
and the crown's transmissivity if the only thing in the way is foliage.
Deciduous crowns switch transmissivity on their own leaf-on and leaf-off dates,
so a yard can hold an evergreen and a deciduous tree at once.

Outputs, all under the yard's maps/ directory
---------------------------------------------
    sun-hours-monthly.png     twelve monthly sun-hour maps, real leaf state
    sun-hours-leaf-state.png  shoulder months in both leaf states
    shade-clocks.png          hour-by-hour lit and shade on solstices, equinoxes
    sun-path.png              sun paths against the obstruction horizon
    crown-sensitivity.png     how much rides on the unmeasured crown numbers
    <barrier>-scenarios.png   what a proposed wall or trellis would cost
    sun-hours.json            every number in the drawings, machine-readable
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Polygon as MplPolygon, Circle

from . import siteschema, solar, yards

AZ_BINS = 360
EYE = 2.0                       # inches above grade: a seedling's point of view
STEP_H = 1.0 / 12.0             # five minutes

SUN_CMAP = LinearSegmentedColormap.from_list("sun", [
    "#2f3a4a", "#4a5b6e", "#7d8a7a", "#b7ae76", "#e0c15c",
    "#f2d94e", "#fdf0a0",
])
CLOCK_CMAP = LinearSegmentedColormap.from_list(
    "clock", ["#39424f", "#8d9482", "#f2d94e"])


def sun_vector(alt, az, x_axis_bearing):
    """Unit vector toward the sun, in yard coordinates."""
    th = math.radians(az - x_axis_bearing)
    ca = math.cos(math.radians(alt))
    return np.array([ca * math.cos(th), ca * math.sin(th),
                     math.sin(math.radians(alt))])


class Model:
    """The yard floor, its obstructions, and the light that reaches it."""

    def __init__(self, site, cell=6.0, year=None):
        self.S = site
        self.sun = solar.SolarSite.from_site(site, year=year)
        b = site["boundary"]
        self.s = float(b.get("north_fence_slope") or 0.0)
        self.W = float(b["width_east_west"])
        self.C = float(b["south_boundary_offset"])
        self.x_axis_bearing = site["frame"]["true_bearing_of_plus_x"]
        self.cell = cell

        nx = int(round(self.W / cell))
        ny = int(round(self.C / cell))
        xs = (np.arange(nx) + 0.5) * cell
        ys = (np.arange(ny) + 0.5) * cell
        self.xs, self.ys, self.nx, self.ny = xs, ys, nx, ny
        gx, gy = np.meshgrid(xs, ys)                      # (ny, nx)
        self.inside = gy > self.s * gx
        self.px = gx[self.inside]
        self.py = gy[self.inside]
        self.M = self.px.size

        self.trees = siteschema.trees(site)
        self.stacking = (site.get("features", {}) or {}).get(
            "canopy_stacking", "single")
        self.segments = self._base_segments()
        self.horizon = self._horizon(self.segments)
        self.crowns = self._crowns()
        self.overheads = self._overheads()
        self.zones = self._zones()

    # ---------------------------------------------------- obstruction segments
    def _base_segments(self):
        """Opaque obstructions as vertical wall segments (x1, y1, x2, y2, h, kind)."""
        segs = []
        obs = self.S.get("obstructions", {})

        ho = obs.get("house")
        if ho:
            segs.extend(self._house_segments(ho))
        for extra in obs.get("buildings", []):
            segs.extend(self._house_segments(extra))

        for fence in self._fences():
            pts = fence["points"]
            h = float(fence.get("height", 0))
            if h <= 0 or not fence.get("opaque", True):
                continue
            for i in range(len(pts) - 1):
                (x1, y1), (x2, y2) = pts[i], pts[i + 1]
                segs.append((x1, y1, x2, y2, h, fence.get("id", "fence")))

        for bd in obs.get("context_buildings", []):
            poly = bd["polygon"]
            for i in range(len(poly)):
                ax_, ay_ = poly[i]
                bx_, by_ = poly[(i + 1) % len(poly)]
                segs.append((ax_, ay_, bx_, by_, bd["height"], "neighbour"))
        return segs

    def _house_segments(self, ho):
        """A building whose yard-facing wall runs parallel to the Y axis.

        A gabled roof is sampled up the slope so a low ray cannot sneak between
        the eave and the ridge, and the gable end nearest the yard is stepped
        across its width because that triangle is what a corner of the yard sees.
        """
        segs = []
        y0, y1 = ho["wall_y"]
        wall_x = float(ho["wall_x"])
        eave = float(ho["eave_height"])
        ridge = float(ho.get("ridge_height") or eave)
        ridge_x = float(ho.get("ridge_x") or wall_x)
        width = float(ho.get("width") or 0.0)
        far_x = wall_x + width

        if ridge > eave and ridge_x != wall_x:
            for i in range(5):
                f = i / 4.0
                x = wall_x + f * (ridge_x - wall_x)
                segs.append((x, y0, x, y1, eave + f * (ridge - eave), "house"))
        else:
            segs.append((wall_x, y0, wall_x, y1, eave, "house"))

        if width:
            segs.append((far_x, y0, far_x, y1, eave, "house"))
            if ridge > eave:
                for i in range(4):
                    f0, f1 = i / 4.0, (i + 1) / 4.0
                    hx = lambda f: eave + (ridge - eave) * (1 - abs(2 * f - 1))
                    segs.append((wall_x + f0 * width, y0, wall_x + f1 * width, y0,
                                 max(hx(f0), hx(f1)), "house"))
            else:
                segs.append((wall_x, y0, far_x, y0, eave, "house"))
            segs.append((wall_x, y1, far_x, y1, eave, "house"))
        return segs

    def _fences(self):
        """Fences as polylines, accepting the older per-edge blocks too."""
        obs = self.S.get("obstructions", {})
        if obs.get("fences"):
            return obs["fences"]
        out = []
        wf = obs.get("west_fence")
        if wf:
            ext = wf.get("y_extent", [-2.0 * self.C, 4.0 * self.C])
            out.append({"id": "west fence", "height": wf["height"],
                        "opaque": wf.get("opaque", True),
                        "points": [[wf["x"], ext[0]], [wf["x"], ext[1]]]})
        nf = obs.get("north_fence")
        if nf:
            out.append({"id": "north fence", "height": nf["height"],
                        "opaque": nf.get("opaque", True),
                        "points": [[0.0, 0.0], [self.W, self.s * self.W]]})
        return out

    def barrier_segment(self, height, barrier=None):
        """A proposed wall, as a segment on whichever boundary it sits."""
        if barrier and barrier.get("points"):
            (x1, y1), (x2, y2) = barrier["points"][0], barrier["points"][-1]
            return (x1, y1, x2, y2, float(height), "barrier")
        return (0.0, self.C, self.W, self.C, float(height), "barrier")

    def _horizon(self, segments):
        """(M, AZ_BINS) maximum blocked altitude, in degrees."""
        az = np.radians(np.arange(AZ_BINS) + 0.5 - self.x_axis_bearing)
        ux, uy = np.cos(az), np.sin(az)
        hor = np.zeros((self.M, AZ_BINS))
        px = self.px[:, None]
        py = self.py[:, None]
        for x1, y1, x2, y2, h, _ in segments:
            if h <= 0:
                continue
            dx, dy = x2 - x1, y2 - y1
            denom = ux * dy - uy * dx
            with np.errstate(divide="ignore", invalid="ignore"):
                wx, wy = x1 - px, y1 - py
                t = (wx * dy - wy * dx) / denom
                sp = (wx * uy - wy * ux) / denom
                ok = (np.abs(denom) > 1e-12) & (t > 1e-6) & (sp >= 0.0) & (sp <= 1.0)
                alt = np.degrees(np.arctan2(h - EYE, np.where(ok, t, np.inf)))
            np.maximum(hor, np.where(ok, alt, 0.0), out=hor)
        return hor

    def horizon_with(self, height, barrier=None):
        if height <= 0:
            return self.horizon
        extra = self._horizon([self.barrier_segment(height, barrier)])
        return np.maximum(self.horizon, extra)

    # ------------------------------------------------------------------ crowns
    def _crowns(self, override=None):
        """Each crown as (centre, radii, tree). Ray-ellipsoid rather than a
        horizon entry, because light passes under a crown through bare trunks."""
        out = []
        for t in self.trees:
            base = t["crown_base_height"]
            radius = t["crown_radius"]
            cx = t["crown_center_x"]
            cy = t["crown_center_y"]
            if override:
                base = override.get("base", base)
                radius = override.get("radius", radius)
                cx = override.get("centre_x", cx)
            if radius is None or base is None or t.get("height") is None:
                continue
            top = t["height"]
            rz = max((top - base) / 2.0, 1e-6)
            out.append((np.array([cx, cy, (base + top) / 2.0], float),
                        np.array([radius, radius, rz], float), t))
        return out

    def set_crowns(self, base=None, radius=None, centre_x=None):
        self.crowns = self._crowns({"base": base, "radius": radius,
                                    "centre_x": centre_x})

    # --------------------------------------------------------------- overheads
    def _overheads(self):
        """Awnings, pergolas, carports and solid roof overhangs.

        A horizontal plane cannot go in the azimuth horizon for the same reason a
        tree crown cannot: light passes *under* it. An awning over a four-foot
        bed is the clearest case in gardening — it takes the high summer sun off
        the bed almost entirely, and does nothing at all about the low western
        sun of a summer evening, which arrives underneath it. Those two facts
        together are why a bed can be in shade all day and still scorch.

        Each is a rectangle in the yard plane at a height, with a transmissivity
        so that a slatted pergola or a shadecloth can be modelled as partial.
        """
        out = []
        for o in (self.S.get("obstructions", {}) or {}).get("overheads", []) or []:
            x = o.get("x")
            y = o.get("y")
            h = o.get("height")
            if not x or not y or h is None:
                continue
            out.append({"id": o.get("id", "overhead"),
                        "x0": float(min(x)), "x1": float(max(x)),
                        "y0": float(min(y)), "y1": float(max(y)),
                        "height": float(h),
                        "tau": float(o.get("transmissivity", 0.0))})
        return out

    def overhead_mult(self, d):
        """Beam multiplier per cell for the overhead planes in the way.

        The ray from a cell reaches the plane's height at one horizontal point.
        If that point is inside the rectangle the beam is intercepted; if it is
        beyond the edge, the beam came in under the awning and is untouched.
        """
        if not self.overheads:
            return np.ones(self.M), np.zeros(self.M, dtype=bool)
        mult = np.ones(self.M)
        any_hit = np.zeros(self.M, dtype=bool)
        dz = float(d[2])
        for o in self.overheads:
            rise = o["height"] - EYE
            if rise <= 0 or dz <= 1e-9:
                continue                       # sun below the plane, or at grade
            t = rise / dz
            hx = self.px + float(d[0]) * t
            hy = self.py + float(d[1]) * t
            hit = ((hx >= o["x0"]) & (hx <= o["x1"]) &
                   (hy >= o["y0"]) & (hy <= o["y1"]))
            mult = np.where(hit, np.minimum(mult, o["tau"]), mult)
            any_hit |= hit
        return mult, any_hit

    def overhead_blocks_point(self, point, d):
        p = np.asarray(point, float)
        dz = float(d[2])
        for o in self.overheads:
            rise = o["height"] - p[2]
            if rise <= 0 or dz <= 1e-9:
                continue
            t = rise / dz
            hx, hy = p[0] + float(d[0]) * t, p[1] + float(d[1]) * t
            if o["x0"] <= hx <= o["x1"] and o["y0"] <= hy <= o["y1"] \
                    and o["tau"] < 0.5:
                return True
        return False

    def crown_hits(self, d):
        """(M,) transmissivity multiplier per cell for the crowns in the way.

        Products are written as elementwise sums rather than with the matmul
        operator, which raises spurious floating-point flags under Accelerate.
        """
        origin = np.stack([self.px, self.py, np.full(self.M, EYE)], axis=1)
        hits = []
        for centre, radii, tree in self.crowns:
            q = (origin - centre) / radii
            e = d / radii
            a = float((e * e).sum())
            bq = 2.0 * (q * e).sum(axis=1)
            c = (q * q).sum(axis=1) - 1.0
            disc = bq * bq - 4.0 * a * c
            hits.append(((disc > 0.0) & (bq < 0.0) & (c > 0.0), tree))
        return hits

    def crown_blocks_point(self, point, d):
        p = np.asarray(point, float)
        for centre, radii, _ in self.crowns:
            q = (p - centre) / radii
            e = d / radii
            a = float((e * e).sum())
            bq = 2.0 * float((q * e).sum())
            c = float((q * q).sum()) - 1.0
            if bq * bq - 4.0 * a * c > 0.0 and bq < 0.0 and c > 0.0:
                return True
        return False

    # ------------------------------------------------------------------- zones
    def _zones(self):
        """Named regions, from site.json, plus whole-yard and the three bands.

        Every interval is half-open [lo, hi), so a cell centre landing exactly on
        a shared edge belongs to one zone and not both.
        """
        z = {}
        px, py = self.px, self.py
        # A zone can be described in site.json and still fall outside the sampled
        # extent, because the extent is chosen for the planting question and the
        # zone list is the whole property. Averaging over no cells is a numpy
        # error deep in a reduction, which is a terrible way to learn that a
        # patio is off the west edge of the grid. Catch it here, say so by name,
        # and keep the mask so analysis bands can still reference it.
        self.zones_offgrid = {}
        for key, spec in (self.S.get("zones") or {}).items():
            label = spec.get("label_short") or spec.get("label") or key
            mask = np.ones(self.M, dtype=bool)
            if spec.get("x"):
                lo, hi = spec["x"]
                mask &= (px >= lo) & (px < hi)
            mask &= self._y_mask(spec, px, py)
            if not mask.any():
                self.zones_offgrid[label] = {
                    "key": key,
                    "zone_x": spec.get("x"),
                    "zone_y": spec.get("y"),
                    "grid_x": [float(px.min()), float(px.max())],
                    "grid_y": [float(py.min()), float(py.max())],
                }
            z[label] = mask

        bands = self.S.get("analysis_bands")
        if bands is None:
            bands = [{"label": "West third"}, {"label": "Middle third"},
                     {"label": "East third"}]
        n = len(bands)
        for i, band in enumerate(bands):
            lo = band.get("x_from", self.W * i / n)
            hi = band.get("x_to", self.W * (i + 1) / n)
            m = (px >= lo) & (px < hi)
            # A band that names no depth spans the yard. Naming one lets a band
            # follow a single bed, which is the difference between reporting the
            # light on a rose and reporting the light on the lawn behind it.
            if band.get("y_from") is not None:
                m &= py >= band["y_from"]
            if band.get("y_to") is not None:
                m &= py < band["y_to"]
            if band.get("zone"):
                m &= z.get(self._zone_label(band["zone"]),
                           np.ones(self.M, dtype=bool))
            z[band.get("label", f"band {i + 1}")] = m

        z["Whole yard"] = np.ones(self.M, dtype=bool)
        return z

    def _zone_label(self, key):
        spec = (self.S.get("zones") or {}).get(key) or {}
        return spec.get("label_short") or spec.get("label") or key

    def _y_mask(self, spec, px, py):
        mask = np.ones(self.M, dtype=bool)
        if spec.get("y"):
            lo, hi = spec["y"]
            mask &= (py >= lo) & (py < hi)
            return mask
        north = spec.get("y_north")
        south = spec.get("y_south")
        if isinstance(north, (int, float)):
            mask &= py >= north
        elif north:
            mask &= py >= self.s * px
        if isinstance(south, (int, float)):
            mask &= py < south
        elif south:
            mask &= py < self.C
        return mask

    def zone_order(self):
        """Whole yard first, then the named zones, then the bands.

        Zones that hold no cells are left out. They are not reportable — there is
        nothing to average — and `zones_offgrid` carries them with the reason.
        """
        named = [k for k in self.zones
                 if k != "Whole yard" and k not in self.zones_offgrid]
        return ["Whole yard"] + named

    # -------------------------------------------------------------- the model
    def canopy(self, d, doy, tau_override=None):
        """Beam multiplier and a hit flag for the crowns in the way.

        Two trees whose crowns have merged into one mass should not attenuate a
        beam twice, but two trees at opposite ends of a yard should. Which
        applies is a property of the planting, not of the maths, so it comes from
        `features.canopy_stacking`:

            single    the most opaque crown in the way wins. The default, and
                      right for a row of the same species grown together
            multiply  every crown attenuates in turn, for genuinely separate trees
        """
        mult = np.ones(self.M)
        any_hit = np.zeros(self.M, dtype=bool)
        for hit, tree in self.crown_hits(d):
            tau = (tau_override if tau_override is not None
                   else siteschema.tree_transmissivity(tree, doy)[0])
            if self.stacking == "multiply":
                mult = np.where(hit, mult * tau, mult)
            else:
                mult = np.where(hit, np.minimum(mult, tau), mult)
            any_hit |= hit
        # An awning is not foliage and does not share the stacking rule: it
        # attenuates whatever the leaves already did.
        omult, ohit = self.overhead_mult(d)
        return mult * omult, (any_hit | ohit)

    def day(self, doy, horizon=None, tau_override=None):
        """Effective and fully-clear sun hours per cell for one day."""
        hor = self.horizon if horizon is None else horizon
        rise, set_ = self.sun.day_length(doy)
        eff = np.zeros(self.M)
        clear = np.zeros(self.M)
        t = rise
        while t <= set_:
            alt, az = self.sun.position(doy, t)
            if alt > 0.5:
                blocked = alt <= hor[:, int(az) % AZ_BINS]
                d = sun_vector(alt, az, self.x_axis_bearing)
                mult, any_crown = self.canopy(d, doy, tau_override)
                eff += STEP_H * np.where(blocked, 0.0, mult)
                clear += STEP_H * (~blocked & ~any_crown)
            t += STEP_H
        return eff, clear

    def lit_at(self, doy, solar_hour, horizon=None):
        """Per-cell state at one instant: 0 shade, tau filtered, 1 full sun."""
        hor = self.horizon if horizon is None else horizon
        alt, az = self.sun.position(doy, solar_hour)
        if alt <= 0.5:
            return None
        blocked = alt <= hor[:, int(az) % AZ_BINS]
        d = sun_vector(alt, az, self.x_axis_bearing)
        mult, _ = self.canopy(d, doy)
        return np.where(blocked, 0.0, mult), alt, az

    def sun_window(self, doy):
        """First and last clock time with unobstructed sun anywhere in the yard."""
        rise, set_ = self.sun.day_length(doy)
        first = last = None
        t = rise
        while t <= set_:
            alt, az = self.sun.position(doy, t)
            if alt > 0.5:
                blocked = alt <= self.horizon[:, int(az) % AZ_BINS]
                d = sun_vector(alt, az, self.x_axis_bearing)
                _, shaded = self.canopy(d, doy)
                if (~blocked & ~shaded).any():
                    first = t if first is None else first
                    last = t
            t += STEP_H
        if first is None:
            return None, None
        return (self.sun.solar_to_clock(doy, first),
                self.sun.solar_to_clock(doy, last))

    def leaf_state(self, doy):
        """Whether any deciduous crown is in leaf on this day."""
        for _, _, t in self.crowns:
            if siteschema.tree_transmissivity(t, doy)[1]:
                return True
        return False

    def to_grid(self, values, fill=np.nan):
        g = np.full((self.ny, self.nx), fill)
        g[self.inside] = values
        return g


# --------------------------------------------------------------- rendering

def yard_axes(ax, m, title=None, labels=True):
    """Plan-view axes, north up, with the yard outline and its furniture."""
    W, C, s = m.W, m.C, m.s
    ax.set_xlim(-14, W + 14)
    ax.set_ylim(-C - 14, 14)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(MplPolygon([(0, 0), (W, -s * W), (W, -C), (0, -C)], closed=True,
                            fc="none", ec="#1b1f23", lw=1.6, zorder=6))
    for spec in (m.S.get("zones") or {}).values():
        if spec.get("outline") is False or not spec.get("y"):
            continue
        ax.plot([spec.get("x", [0, W])[0], spec.get("x", [0, W])[1]],
                [-spec["y"][0]] * 2, color="#7a5b33", lw=1.0,
                ls=(0, (5, 3)), zorder=6)
    for t in m.trees:
        if t.get("trunk_x") is None:
            continue
        ax.add_patch(Circle((t["trunk_x"], -t["trunk_y"]), 5, fc="#5b3f28",
                            ec="white", lw=0.6, zorder=7))
    if title:
        ax.set_title(title, fontsize=9.5, color="#2f3437", pad=4)
    if labels and m.S.get("narrative", {}).get("north_label"):
        ax.text(W / 2, 20, m.S["narrative"]["north_label"], fontsize=6.5,
                color="#9aa0a6", ha="center")


def heatmap_panel(ax, m, grid, vmax, title):
    im = ax.imshow(grid, origin="upper", extent=[0, m.W, -m.C, 0],
                   cmap=SUN_CMAP, vmin=0, vmax=vmax, interpolation="bilinear",
                   zorder=2)
    yard_axes(ax, m, title, labels=False)
    return im


def fig_monthly(m, outdir):
    rows = []
    for mon, doy in solar.MONTH_DOY.items():
        eff, clear = m.day(doy)
        rows.append((mon, eff, clear, m.leaf_state(doy)))
    vmax = max(float(np.nanmax(e)) for _, e, _, _ in rows) or 1.0

    fig, axes = plt.subplots(3, 4, figsize=(13.2, 14.4))
    im = None
    for ax, (mon, eff, clear, leaf_on) in zip(axes.ravel(), rows):
        state = "in leaf" if leaf_on else "bare"
        label = f"{mon}   ·   {state}" if m.crowns else mon
        im = heatmap_panel(ax, m, m.to_grid(eff), vmax, label)
        ax.text(m.W / 2, -m.C - 26,
                f"yard mean {eff.mean():.1f} h   ·   best cell {eff.max():.1f} h",
                fontsize=7.2, color="#6b7280", ha="center")
    fig.suptitle("EFFECTIVE DIRECT SUN HOURS PER DAY, MONTH BY MONTH",
                 fontsize=16, fontweight="bold", color="#2f3437", y=0.990)
    fig.text(0.5, 0.963, m.S.get("narrative", {}).get(
        "monthly_caption",
        "Representative day each month, with each crown's transmissivity applied "
        "by season.\nNorth is up. Darker is shadier."),
        fontsize=9.5, color="#6b7280", ha="center", va="top", linespacing=1.6)
    cax = fig.add_axes([0.30, 0.038, 0.40, 0.010])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label("effective direct sun, hours per day", fontsize=8.5, color="#6b7280")
    cb.ax.tick_params(labelsize=7.5)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.912, bottom=0.065,
                        wspace=0.02, hspace=0.16)
    path = os.path.join(outdir, "sun-hours-monthly.png")
    fig.savefig(path, dpi=140, facecolor="white")
    plt.close(fig)
    print("wrote", path)


def fig_leaf_state(m, outdir):
    """Shoulder months in both leaf states. Skipped when nothing is deciduous."""
    decid = [t for _, _, t in m.crowns if t.get("deciduous", True)]
    if not decid:
        return {}
    months = m.S.get("narrative", {}).get("shoulder_months",
                                          ["Mar", "Apr", "May", "Oct"])
    tau_on = min(t["transmissivity_leaf_on"] for t in decid)
    tau_off = max(t["transmissivity_leaf_off"] for t in decid)
    states = [(f"bare branches, {tau_off * 100:.0f}% transmission", tau_off),
              (f"full leaf, {tau_on * 100:.0f}% transmission", tau_on)]

    fig, axes = plt.subplots(2, len(months), figsize=(3.4 * len(months), 8.0))
    results, grids = {}, {}
    for r, (label, tau) in enumerate(states):
        for c, mon in enumerate(months):
            eff, _ = m.day(solar.MONTH_DOY[mon], tau_override=tau)
            grids[(r, c)] = eff
            results.setdefault(mon, {})[label] = float(eff.mean())
    vmax = max(float(g.max()) for g in grids.values()) or 1.0
    im = None
    for r, (label, _) in enumerate(states):
        for c, mon in enumerate(months):
            eff = grids[(r, c)]
            im = heatmap_panel(axes[r, c], m, m.to_grid(eff), vmax, mon)
            axes[r, c].text(m.W / 2, -m.C - 26, f"mean {eff.mean():.1f} h",
                            fontsize=7.4, color="#6b7280", ha="center")
        axes[r, 0].text(-40, -m.C / 2, label, rotation=90, va="center",
                        ha="center", fontsize=9.5, fontweight="bold",
                        color="#4e6b3d")
    gaps = {mon: results[mon][states[0][0]] - results[mon][states[1][0]]
            for mon in months}
    worst = max(gaps, key=gaps.get)
    fig.suptitle("HOW MUCH DOES LEAF-OUT TIMING MATTER?", fontsize=15,
                 fontweight="bold", color="#2f3437", y=0.975)
    fig.text(0.5, 0.925,
             "Same months, same geometry, canopy transmissivity the only "
             f"difference. The largest gap is {gaps[worst]:.1f} h, in {worst}. "
             + ("Leaf-out timing is not the variable that matters; crown spread is."
                if gaps[worst] < 0.5 else
                "Leaf-out timing is doing real work here."),
             fontsize=9, color="#6b7280", ha="center")
    cax = fig.add_axes([0.32, 0.05, 0.36, 0.016])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label("effective direct sun, hours per day", fontsize=8.5, color="#6b7280")
    cb.ax.tick_params(labelsize=7.5)
    fig.subplots_adjust(left=0.05, right=0.98, top=0.88, bottom=0.10,
                        wspace=0.06, hspace=0.20)
    path = os.path.join(outdir, "sun-hours-leaf-state.png")
    fig.savefig(path, dpi=140, facecolor="white")
    plt.close(fig)
    print("wrote", path)
    return results


def fig_shade_clocks(m, outdir):
    dates = list(solar.DOY.items())
    clocks = m.S.get("narrative", {}).get("clock_hours", list(range(11, 21)))
    fig, axes = plt.subplots(len(dates), len(clocks),
                             figsize=(1.42 * len(clocks), 2.55 * len(dates)))
    summary = {}
    for r, (name, doy) in enumerate(dates):
        leaf_on = m.leaf_state(doy)
        for c, ch in enumerate(clocks):
            ax = axes[r, c]
            res = m.lit_at(doy, m.sun.clock_to_solar(doy, ch + 0.5))
            if res is None:
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis("off")
                ax.add_patch(MplPolygon([(0.05, 0.05), (0.95, 0.05), (0.95, 0.95),
                                         (0.05, 0.95)], closed=True,
                                        fc="#2b3038", ec="none"))
                ax.text(0.5, 0.5, "dark", fontsize=8, color="#7a828c",
                        ha="center", va="center")
            else:
                state, alt, az = res
                ax.imshow(m.to_grid(state), origin="upper",
                          extent=[0, m.W, -m.C, 0], cmap=CLOCK_CMAP, vmin=0,
                          vmax=1, interpolation="nearest", zorder=2)
                yard_axes(ax, m, labels=False)
                frac = float((state > 0.5).mean())
                ax.text(m.W / 2, -m.C - 22,
                        f"{frac * 100:.0f}% of the yard lit   alt {alt:.0f}°",
                        fontsize=6.2, color="#6b7280", ha="center")
            if r == 0:
                hh = ch % 12 or 12
                ax.set_title(f"{hh} {'am' if ch < 12 else 'pm'}", fontsize=9,
                             fontweight="bold", color="#2f3437", pad=6)
        label = f"{name}\n{'in leaf' if leaf_on else 'bare'}" if m.crowns else name
        axes[r, 0].text(-52, -m.C / 2, label, rotation=90, va="center",
                        ha="center", fontsize=9.5, fontweight="bold",
                        color="#2f3437", linespacing=1.4)
        eff, _ = m.day(doy)
        first, last = m.sun_window(doy)
        summary[name] = {
            "yard_mean_sun_hours": round(float(eff.mean()), 2),
            "first_sun_clock": solar.fmt_clock(first) if first else "none",
            "last_sun_clock": solar.fmt_clock(last) if last else "none",
        }

    fig.suptitle("SHADE CLOCK — WHERE THE SUN ACTUALLY LANDS, HOUR BY HOUR",
                 fontsize=15, fontweight="bold", color="#2f3437", y=0.985)
    fig.text(0.5, 0.955,
             "Local clock time. Yellow is unobstructed sun, grey-green is "
             "canopy-filtered, dark is shade. Every panel is the same yard, "
             "north up.", fontsize=9, color="#6b7280", ha="center")
    fig.subplots_adjust(left=0.045, right=0.995, top=0.90, bottom=0.02,
                        wspace=0.05, hspace=0.18)
    path = os.path.join(outdir, "shade-clocks.png")
    fig.savefig(path, dpi=130, facecolor="white")
    plt.close(fig)
    print("wrote", path)
    return summary


def fig_sun_path(m, outdir):
    """The one chart that explains a yard: sun paths against the horizon."""
    pts = m.S.get("narrative", {}).get("sun_path_points")
    if not pts:
        pts = [{"label": "Middle of the yard",
                "xy": [m.W / 2, m.C / 2], "color": "#1f6f8b"}]
    palette = ["#b03a2e", "#1f6f8b", "#4e6b3d", "#8a5a52"]
    az_grid = np.arange(40, 321, 1.0)
    alt_grid = np.arange(0.5, 88.0, 0.75)

    fig, ax = plt.subplots(figsize=(14.6, 8.4))
    for i, spec in enumerate(pts):
        x, y = spec["xy"]
        col = spec.get("color", palette[i % len(palette)])
        idx = int(np.argmin((m.px - x) ** 2 + (m.py - y) ** 2))
        hor = m.horizon[idx]
        prof = np.array([hor[int(a) % AZ_BINS] for a in az_grid])
        ax.fill_between(az_grid, 0, prof, color=col, alpha=0.16, zorder=2)
        ax.plot(az_grid, prof, color=col, lw=1.8, zorder=3,
                label=f"{spec['label']} — built")

        if m.crowns or m.overheads:
            pt = np.array([m.px[idx], m.py[idx], EYE])
            mask = np.zeros((alt_grid.size, az_grid.size), dtype=bool)
            for j, a in enumerate(az_grid):
                for k, al in enumerate(alt_grid):
                    d = sun_vector(al, a, m.x_axis_bearing)
                    mask[k, j] = (m.crown_blocks_point(pt, d) or
                                  m.overhead_blocks_point(pt, d))
            if mask.any():
                ax.contourf(az_grid, alt_grid, mask.astype(float),
                            levels=[0.5, 1.5], colors=[col], alpha=0.20, zorder=2)
                ax.contour(az_grid, alt_grid, mask.astype(float), levels=[0.5],
                           colors=[col], linewidths=1.0, linestyles="dashed",
                           zorder=3)

    for name, doy, col in (("Jun 21", 172, "#e0a11b"),
                           ("Mar 20 / Sep 22", 79, "#c98a2b"),
                           ("Dec 21", 355, "#8d6a3f")):
        rise, set_ = m.sun.day_length(doy)
        ts = np.arange(rise, set_ + 1e-9, 1 / 30.0)
        path_pts = [m.sun.position(doy, t) for t in ts]
        ax.plot([p[1] for p in path_pts], [p[0] for p in path_pts], color=col,
                lw=2.4, zorder=5, label=f"sun path, {name}")
        for hour in range(5, 21):
            sh = m.sun.clock_to_solar(doy, hour)
            if rise <= sh <= set_:
                alt, az = m.sun.position(doy, sh)
                ax.plot([az], [alt], marker="o", ms=4.5, color=col, zorder=6)
                if hour >= 12:
                    ax.annotate(f"{hour % 12 or 12}", (az, alt), (3, 5),
                                textcoords="offset points", fontsize=7,
                                color=col, fontweight="bold", zorder=7)

    for note in m.S.get("narrative", {}).get("sun_path_notes", []):
        kw = dict(fontsize=note.get("size", 8.6), color=note.get("color", "#2f3437"),
                  ha=note.get("ha", "center"), linespacing=1.45, zorder=8)
        if note.get("bold"):
            kw["fontweight"] = "bold"
        if note.get("arrow_to"):
            ax.annotate(note["text"], xy=tuple(note["arrow_to"]),
                        xytext=tuple(note["at"]),
                        bbox=dict(boxstyle="round,pad=0.4", fc="white",
                                  ec="#d6d2c8", alpha=0.95),
                        arrowprops=dict(arrowstyle="-|>", color=kw["color"],
                                        lw=1.2), **kw)
        elif note.get("box", True):
            ax.text(note["at"][0], note["at"][1], note["text"],
                    bbox=dict(boxstyle="round,pad=0.35", fc="white",
                              ec="#d6d2c8", alpha=0.92), **kw)
        else:
            ax.text(note["at"][0], note["at"][1], note["text"], alpha=0.85, **kw)

    ax.set_xlim(40, 320)
    ax.set_ylim(0, 90)
    ax.set_xlabel("true azimuth, degrees   (90 east · 180 south · 270 west)",
                  fontsize=9.5, color="#4b5158")
    ax.set_ylabel("altitude, degrees", fontsize=9.5, color="#4b5158")
    ax.set_xticks(range(45, 321, 15))
    ax.grid(color="#e6e8ea", lw=0.7)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(fontsize=8.6, loc="lower left", framealpha=0.96, ncol=2,
              bbox_to_anchor=(0.005, 0.02))
    ax.set_title("SUN PATHS AGAINST THE OBSTRUCTION HORIZON", fontsize=15,
                 fontweight="bold", color="#2f3437", loc="left", pad=54)
    ax.text(0, 1.028,
            "Solid outlines are built obstructions as seen from points in the "
            "yard: everything below a line is blocked. Dashed outlines are tree\n"
            "crowns, which float clear of the ground, so the gap beneath them is "
            "open. Where a sun path runs above every outline, that spot has\n"
            "direct sun at that moment.",
            transform=ax.transAxes, fontsize=9.2, color="#6b7280", linespacing=1.6)
    fig.tight_layout()
    path = os.path.join(outdir, "sun-path.png")
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    print("wrote", path)


def fig_crown_sensitivity(m, outdir):
    """How much of the answer rests on crown shape nobody has measured.

    Observing a canopy from inside a yard pins where the leaves stop on the near
    side and says nothing about how far the crown reaches the other way, or how
    high the leafy part starts. Both unknowns push hard on the result, so this
    grid holds the observed near edge fixed and varies the two.
    """
    if not m.crowns:
        return {}
    radii = [t["crown_radius"] for _, _, t in m.crowns if t.get("crown_radius")]
    if not radii:
        return {}
    ref = m.crowns[0][2]
    east_edge = ref["crown_center_x"] + ref["crown_radius"]
    bases_ft = [4, 8, 12, 16, 20, 24]
    spread_ft = [10, 16, 22, 30, 40]
    doy = solar.MONTH_DOY["Jun"]
    keep = m.crowns
    band = m.zones.get(m.S.get("narrative", {}).get("canopy_band"))
    if band is None:
        band = m.px < m.W / 3.0

    grid_all = np.zeros((len(bases_ft), len(spread_ft)))
    grid_band = np.zeros_like(grid_all)
    for i, bft in enumerate(bases_ft):
        for j, sft in enumerate(spread_ft):
            r = sft * 12.0 / 2.0
            m.set_crowns(base=bft * 12.0, radius=r, centre_x=east_edge - r)
            eff, _ = m.day(doy)
            grid_all[i, j] = eff.mean()
            grid_band[i, j] = eff[band].mean()

    m.set_crowns(radius=0.01)
    open_sky = float(m.day(doy)[0].mean())
    m.crowns = keep
    modelled_base_ft = ref["crown_base_height"] / 12.0

    fig, axes = plt.subplots(1, 2, figsize=(15.0, 7.2))
    im = None
    for ax, g, name in ((axes[0], grid_all, "Whole yard"),
                        (axes[1], grid_band, "Under the trees")):
        im = ax.imshow(g, cmap="YlGnBu_r", origin="lower", aspect="auto",
                       vmin=0, vmax=open_sky)
        for i in range(len(bases_ft)):
            for j in range(len(spread_ft)):
                frac = g[i, j] / open_sky if open_sky else 0
                ax.text(j, i, f"{g[i, j]:.1f} h\n{frac * 100:.0f}%", ha="center",
                        va="center", fontsize=8.8,
                        color="white" if frac < 0.55 else "#20303a",
                        fontweight="bold", linespacing=1.25)
        ax.set_xticks(range(len(spread_ft)))
        ax.set_xticklabels([f"{s} ft" for s in spread_ft])
        ax.set_yticks(range(len(bases_ft)))
        ax.set_yticklabels([f"{b} ft" for b in bases_ft])
        ax.set_xlabel("crown spread, with the near edge held where it was observed",
                      fontsize=9, color="#4b5158")
        ax.set_ylabel("height the leafy crown starts", fontsize=9.5, color="#4b5158")
        ax.set_title(f"{name} — June sun hours, and percent of open sky",
                     fontsize=10.5, color="#2f3437", loc="left")
        if modelled_base_ft in bases_ft:
            row = bases_ft.index(modelled_base_ft)
            ax.add_patch(plt.Rectangle((-0.5, row - 0.5), 1, 1, fc="none",
                                       ec="#b03a2e", lw=3.0))
        ax.add_patch(plt.Rectangle((2.5, -0.5), 2, 3, fc="none", ec="#1d7a4c",
                                   lw=2.6, ls=(0, (5, 3))))

    lo, hi = float(grid_all.min()), float(grid_all.max())
    fig.suptitle("THE CROWN SHAPE IS THE BIGGEST UNKNOWN IN THIS MODEL",
                 fontsize=15, fontweight="bold", color="#2f3437", y=0.985)
    fig.text(0.5, 0.925,
             f"June, in full leaf. With no trees at all the yard would get "
             f"{open_sky:.1f} h a day. Red is the crown as currently modelled. "
             f"The dashed green region is normal\nproportions for a tree this "
             f"tall. Across the grid the answer runs from {lo:.1f} to {hi:.1f} h "
             f"a day — that whole spread is riding on two numbers nobody has "
             f"measured.",
             fontsize=9, color="#6b7280", ha="center", linespacing=1.6)
    cax = fig.add_axes([0.34, 0.045, 0.34, 0.018])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label("effective June sun, hours per day", fontsize=8.5, color="#6b7280")
    cb.ax.tick_params(labelsize=7.5)
    fig.subplots_adjust(top=0.80, bottom=0.19, left=0.07, right=0.98, wspace=0.22)
    path = os.path.join(outdir, "crown-sensitivity.png")
    fig.savefig(path, dpi=145, facecolor="white")
    plt.close(fig)
    print("wrote", path)
    return {"open_sky_june": round(open_sky, 2),
            "crown_base_ft": bases_ft, "crown_spread_ft": spread_ft,
            "near_edge_inches": round(east_edge, 1),
            "range_hours": [round(lo, 2), round(hi, 2)],
            "whole_yard": [[round(v, 2) for v in row] for row in grid_all],
            "under_trees": [[round(v, 2) for v in row] for row in grid_band]}


def barrier_scenarios(m, outdir):
    """What a proposed wall, fence or trellis would cost in light."""
    proposals = m.S.get("obstructions", {}).get("proposed_barriers") or []
    out = {}
    for barrier in proposals:
        heights = [0] + list(barrier.get("heights", [72, 84, 96]))
        bid = barrier.get("id", "barrier")
        label = barrier.get("label", "proposed barrier")
        zones = barrier.get("report_zones") or m.zone_order()[:4]
        zones = [z for z in zones if z in m.zones]
        months = solar.MONTHS
        data = {}
        for h in heights:
            hor = m.horizon_with(h, barrier)
            per_month = {}
            for mon in months:
                eff, _ = m.day(solar.MONTH_DOY[mon], horizon=hor)
                per_month[mon] = {z: float(eff[m.zones[z]].mean()) for z in zones}
            data[h] = per_month

        fig, axes = plt.subplots(1, 2, figsize=(15.4, 6.8),
                                 gridspec_kw={"width_ratios": [1.5, 1]})
        cols = ["#2f3437", "#1f6f8b", "#c98a2b", "#b03a2e", "#6b7280"]
        ax = axes[0]
        for k, h in enumerate(heights):
            vals = [data[h][mon][zones[0]] for mon in months]
            lab = "no barrier (today)" if h == 0 else f"{h / 12:.0f} ft"
            ax.plot(months, vals, marker="o", ms=5, lw=2.2,
                    color=cols[k % len(cols)], label=lab)
        ax.set_ylabel(f"effective sun, hours per day, {zones[0].lower()}",
                      fontsize=9.5, color="#4b5158")
        ax.grid(color="#e9ebec", lw=0.7)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.legend(fontsize=9, loc="upper left")
        ax.set_title("Sun-hour cost, month by month", fontsize=11,
                     color="#2f3437", loc="left")

        ax = axes[1]
        annual = {h: {z: float(np.mean([data[h][mon][z] for mon in months]))
                      for z in zones} for h in heights}
        raised = [h for h in heights if h > 0]
        width = 0.8 / max(len(raised), 1)
        xs = np.arange(len(zones))
        for k, h in enumerate(raised):
            loss = [annual[0][z] - annual[h][z] for z in zones]
            off = (k - (len(raised) - 1) / 2.0) * width
            ax.bar(xs + off, loss, width, color=cols[(k + 1) % len(cols)],
                   label=f"{h / 12:.0f} ft")
            for xi, v in zip(xs + off, loss):
                ax.text(xi, v + 0.008, f"{v * 60:.0f}m", ha="center", fontsize=7.4,
                        color=cols[(k + 1) % len(cols)], fontweight="bold")
        ax.set_xticks(xs)
        ax.set_xticklabels([z.replace(" (", "\n(") for z in zones], fontsize=8.4)
        ax.set_ylabel("annual mean sun lost, hours per day", fontsize=9.5,
                      color="#4b5158")
        ax.grid(color="#e9ebec", lw=0.7, axis="y")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.legend(fontsize=9, title="height", title_fontsize=8.5)
        ax.set_title("What each height costs, averaged over the year",
                     fontsize=11, color="#2f3437", loc="left")

        worst = max(zones, key=lambda z: annual[0][z] - annual[raised[0]][z]) \
            if raised else zones[0]
        cost = annual[0][worst] - annual[raised[0]][worst] if raised else 0.0
        step = (annual[raised[0]][zones[0]] - annual[raised[-1]][zones[0]]) \
            if len(raised) > 1 else 0.0
        fig.suptitle(f"{label.upper()}: SUN-HOUR COST BY HEIGHT", fontsize=15,
                     fontweight="bold", color="#2f3437", y=0.99)
        fig.text(0.5, 0.945,
                 f"Going from the lowest to the highest option costs another "
                 f"{step * 60:.0f} minutes a day, so height is not really the "
                 f"decision. Whether to build it at all is,\nand the bill is paid "
                 f"mainly by the {worst.lower()}, which gives up "
                 f"{cost:.2f} h a day of its {annual[0][worst]:.2f}.",
                 fontsize=9, color="#6b7280", ha="center", linespacing=1.6)
        fig.subplots_adjust(top=0.80, bottom=0.13, left=0.06, right=0.985,
                            wspace=0.24)
        path = os.path.join(outdir, f"{bid}-scenarios.png")
        fig.savefig(path, dpi=145, facecolor="white")
        plt.close(fig)
        print("wrote", path)
        out[bid] = {"label": label,
                    "by_height": {str(k): v for k, v in data.items()}}
    return out


def zone_table(m):
    table = {z: {} for z in m.zone_order()}
    for mon, doy in solar.MONTH_DOY.items():
        eff, clear = m.day(doy)
        for z in table:
            sel = m.zones[z]
            table[z][mon] = {"effective": round(float(eff[sel].mean()), 2),
                             "clear": round(float(clear[sel].mean()), 2),
                             "best_cell": round(float(eff[sel].max()), 2)}
    return table


def zone_timing(m, months=("Apr", "Jun", "Aug")):
    """When each zone's sun arrives, not just how much of it there is.

    Two beds can both read four hours a day and be entirely different places to
    plant. Four morning hours is a gentle bed; four hours between one o'clock
    and sunset, against a west-facing wall, in a climate with fifty days over
    95 F, kills things that the hour count says should be fine. This records the
    share of each zone's direct sun that falls after solar noon and after one
    o'clock, plus the clock time it starts and stops, so a design check can see
    the difference.
    """
    out = {}
    for z in m.zone_order():
        sel = m.zones[z]
        if not sel.any():
            continue
        tot = aft = late = 0.0
        first = last = None
        for mon in months:
            doy = solar.MONTH_DOY[mon]
            off = m.sun.clock_offset(doy)
            rise, set_ = m.sun.day_length(doy)
            t = rise
            while t <= set_:
                alt, az = m.sun.position(doy, t)
                if alt > 0.5:
                    lit = m.lit_at(doy, t)
                    if lit is not None:
                        share = float(lit[0][sel].mean())
                        if share > 0.01:
                            tot += STEP_H * share
                            if t > 12.0:
                                aft += STEP_H * share
                            if t + off > 13.0:
                                late += STEP_H * share
                            clock = t + off
                            first = clock if first is None else min(first, clock)
                            last = clock if last is None else max(last, clock)
                t += STEP_H
        if tot <= 0:
            continue
        out[z] = {"months": list(months),
                  "afternoon_share": round(aft / tot, 2),
                  "after_1pm_share": round(late / tot, 2),
                  "first_sun_clock": round(first, 2) if first else None,
                  "last_sun_clock": round(last, 2) if last else None}
    return out


def light_category(hours):
    if hours >= 6.0:
        return "full sun"
    if hours >= 4.0:
        return "part sun"
    if hours >= 3.0:
        return "part shade"
    if hours >= 1.5:
        return "shade"
    return "deep shade"


def print_markdown(m, table, clocks):
    months = solar.MONTHS
    print("\n### Effective direct sun, hours per day\n")
    print("| Zone | " + " | ".join(months) + " | Year |")
    print("|" + "---|" * (len(months) + 2))
    for z, per in table.items():
        vals = [per[mon]["effective"] for mon in months]
        print(f"| {z} | " + " | ".join(f"{v:.1f}" for v in vals)
              + f" | **{np.mean(vals):.1f}** |")
    print("\n### Fully unobstructed sun only, canopy counted as opaque\n")
    print("| Zone | " + " | ".join(months) + " | Year |")
    print("|" + "---|" * (len(months) + 2))
    for z, per in table.items():
        vals = [per[mon]["clear"] for mon in months]
        print(f"| {z} | " + " | ".join(f"{v:.1f}" for v in vals)
              + f" | **{np.mean(vals):.1f}** |")
    print("\n### The daily sun window\n")
    print("| Date | Yard mean sun | First sun anywhere | Last sun anywhere |")
    print("|---|---|---|---|")
    for k, v in clocks.items():
        print(f"| {k} | {v['yard_mean_sun_hours']:.1f} h | "
              f"{v['first_sun_clock']} | {v['last_sun_clock']} |")
    whole = np.mean([table["Whole yard"][mon]["effective"] for mon in months])
    growing = np.mean([table["Whole yard"][mon]["effective"]
                       for mon in ("Apr", "May", "Jun", "Jul", "Aug", "Sep")])
    print(f"\n**{whole:.1f} h a day annual mean, {growing:.1f} h in the growing "
          f"season — {light_category(growing)}.**")


def run(slug, cell=6.0, outdir=None, quick=False):
    site = yards.load_site(slug)
    errs, warns = siteschema.validate(site)
    for w in warns:
        print("warning:", w)
    if errs:
        for e in errs:
            print("ERROR:", e)
        raise SystemExit("site.json is not complete enough to model")

    outdir = outdir or os.path.join(yards.yard_dir(slug), "maps")
    os.makedirs(outdir, exist_ok=True)
    m = Model(site, cell=cell)
    print(f"{slug}: {m.M} cells at {cell:g} in, {len(m.segments)} obstruction "
          f"segments, {len(m.crowns)} crowns, {m.sun.tz_name}")
    for label, off in m.zones_offgrid.items():
        print(f"warning: zone {label!r} lies outside the sampled extent and is "
              f"NOT in the sun report. zone x={off['zone_x']} y={off['zone_y']}, "
              f"grid x={off['grid_x']} y={off['grid_y']}. Widen `boundary` if it "
              f"should be modelled — but that moves every average.")

    table = zone_table(m)
    clocks = fig_shade_clocks(m, outdir)
    result = {"by_zone_and_month": table, "sun_window": clocks,
              "sun_timing": zone_timing(m)}

    if not quick:
        fig_monthly(m, outdir)
        result["leaf_state_comparison"] = fig_leaf_state(m, outdir)
        fig_sun_path(m, outdir)
        result["crown_sensitivity"] = fig_crown_sensitivity(m, outdir)
        result["barrier_scenarios"] = barrier_scenarios(m, outdir)

    months = solar.MONTHS
    whole = [table["Whole yard"][mon]["effective"] for mon in months]
    growing = [table["Whole yard"][mon]["effective"]
               for mon in ("Apr", "May", "Jun", "Jul", "Aug", "Sep")]
    result["summary"] = {
        "annual_mean_hours": round(float(np.mean(whole)), 2),
        "growing_season_mean_hours": round(float(np.mean(growing)), 2),
        "light_category": light_category(float(np.mean(growing))),
        "sunniest_zone": max(
            (z for z in table if z != "Whole yard"),
            key=lambda z: np.mean([table[z][mon]["effective"] for mon in months])),
        "best_cell_hours": round(max(table["Whole yard"][mon]["best_cell"]
                                     for mon in months), 2),
    }
    yards.save(slug, "sun-hours.json", result)
    print("wrote", yards.path(slug, "sun-hours.json"))
    print_markdown(m, table, clocks)
    return m, result


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--cell", type=float, default=6.0, help="grid cell, inches")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--quick", action="store_true",
                    help="tables and shade clocks only, skip the slow figures")
    args = ap.parse_args()
    run(args.slug, cell=args.cell, outdir=args.outdir, quick=args.quick)


if __name__ == "__main__":
    main()
