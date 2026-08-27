#!/usr/bin/env python3
"""Architectural drawings of a yard, rendered from its site.json.

    python3 -m lib.drawsite <slug> [--outdir maps]

Writes, into the yard's maps/ directory:

    site-plan.png       dimensioned plan, architectural conventions
    site-context.png    the yard's position on the lot, with neighbours
    elevation.png       looking at the primary wall
    section.png         a cut across the yard: what is tall, and how far away

Everything comes from site.json. Nothing is hard-coded here but drawing style.

Where a yard needs a callout that only makes sense for that yard, it goes in
site.json under `drawings`, not in this file:

    "drawings": {
      "plan": {
        "extent": [-152, 664, -472, 118],
        "title": "ASTORIA SIDE YARD — DIMENSIONED PLAN",
        "subtitle": "...",
        "context": [ {"kind": "street", "rect": [...], "label": "12th STREET"} ],
        "notes": [ {"text": "...", "at": [x, y], "arrow_to": [x, y]} ],
        "titleblock": [["Address", "..."], ["Lot area", "..."], ...]
      }
    }
"""
import argparse
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Polygon, Circle, Rectangle, Wedge

from . import siteschema, solar, yards

INK = "#2f3437"
MUTED = "#6b7280"
DIM = "#b03a2e"          # dimension lines, red as per drafting convention
SOIL = "#f4efe4"
LAWN = "#dfe8cf"
WOOD = "#d9b98c"
WOOD_LINE = "#a9814f"
STRIP = "#cbd8bd"
FENCE = "#4f6b3e"
HOUSE = "#ddd6cb"
HOUSE_EDGE = "#8a7f6d"
PAVER = "#cfcac1"
CANOPY = "#7d9b6a"
STEEL = "#8d949c"
STREET = "#eceff1"

DIM_Z = 16

ZONE_STYLE = {
    "lawn": (LAWN, "#7e8f66"),
    "patio": (WOOD, "#8a6636"),
    "deck": (WOOD, "#8a6636"),
    "bed": (SOIL, "#8a7a55"),
    "strip": (STRIP, "#5c7a4b"),
    "gravel": (PAVER, "#8b867d"),
    "default": ("#eceae4", "#8a8478"),
}


def halo(color="white", lw=2.6):
    return [pe.withStroke(linewidth=lw, foreground=color)]


def ftin(inches):
    """Inches as feet and inches. Rounding to the nearest foot turns 19 ft 6 in
    into 20 ft, which is exactly the kind of quiet error this system exists to
    avoid."""
    ft = int(abs(inches)) // 12
    rem = abs(inches) - ft * 12
    sign = "-" if inches < 0 else ""
    if rem < 0.5:
        return f"{sign}{ft} ft"
    return f"{sign}{ft} ft {rem:.0f} in"


def wrap(text, width=54):
    import textwrap
    return textwrap.wrap(text, width) or [""]


# ---------------------------------------------------------------- dimensions

def dim_h(ax, x1, x2, y, text, side=1, gap=0, fs=8.5, color=DIM):
    """Horizontal dimension between x1 and x2, drawn at plot height y."""
    ax.annotate("", xy=(x1, y), xytext=(x2, y), zorder=DIM_Z,
                arrowprops=dict(arrowstyle="<|-|>", color=color, lw=1.0,
                                shrinkA=0, shrinkB=0, mutation_scale=9))
    for x in (x1, x2):
        ax.plot([x, x], [y - 4 * side, y + 4 * side], color=color, lw=0.8,
                zorder=DIM_Z)
    ax.text((x1 + x2) / 2.0, y + (7 + gap) * side, text, ha="center",
            va="bottom" if side > 0 else "top", fontsize=fs, color=color,
            fontweight="bold", zorder=DIM_Z + 1, path_effects=halo("white", 3.2))


def dim_v(ax, y1, y2, x, text, side=1, fs=8.5, color=DIM, rot=90, label_xy=None):
    """Vertical dimension between plot heights y1 and y2, drawn at x."""
    ax.annotate("", xy=(x, y1), xytext=(x, y2), zorder=DIM_Z,
                arrowprops=dict(arrowstyle="<|-|>", color=color, lw=1.0,
                                shrinkA=0, shrinkB=0, mutation_scale=9))
    for y in (y1, y2):
        ax.plot([x - 4 * side, x + 4 * side], [y, y], color=color, lw=0.8,
                zorder=DIM_Z)
    tx, ty = label_xy or (x + 7 * side, (y1 + y2) / 2.0)
    ax.text(tx, ty, text, ha="center", va="center", rotation=rot, fontsize=fs,
            color=color, fontweight="bold", zorder=DIM_Z + 1,
            path_effects=halo("white", 3.2))


def witness(ax, x, y1, y2, color=DIM):
    ax.plot([x, x], [y1, y2], color=color, lw=0.6, ls=(0, (5, 3)), alpha=0.8,
            zorder=DIM_Z)


def scalebar(ax, x, y, feet=5, label=True):
    L = feet * 12.0
    step = max(feet // 5, 1)
    n = feet // step
    for i in range(n):
        ax.add_patch(Rectangle((x + i * step * 12, y), step * 12, L * 0.075,
                               fc=INK if i % 2 == 0 else "white",
                               ec=INK, lw=0.8, zorder=12))
    ax.text(x, y - L * 0.15, "0", ha="center", fontsize=7.5, color=INK)
    ax.text(x + L, y - L * 0.15, f"{feet} ft", ha="center", fontsize=7.5, color=INK)
    if label:
        ax.text(x + L / 2.0, y + L * 0.15, "S C A L E", ha="center", fontsize=7,
                color=MUTED, fontweight="bold")


def north_arrows(ax, x, y, site, R=42):
    """True north, plus any second bearing the yard cares about."""
    yard_north = site.get("frame", {}).get("yard_north_true_bearing", 0.0)
    arrows = [(yard_north, "TRUE\nNORTH", INK, 2.2, 1.0)]
    second = site.get("frame", {}).get("secondary_bearing")
    if second:
        arrows.append((second.get("plot_angle", 0.0), second.get("label", ""),
                       "#1f6f8b", 1.6, 0.58))
    for ang, lab, col, lw, f in arrows:
        a = math.radians(ang)
        dx, dy = -math.sin(a) * R * f, math.cos(a) * R * f
        ax.annotate("", xy=(x + dx, y + dy), xytext=(x, y),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=lw,
                                    mutation_scale=13), zorder=13)
        ax.text(x + dx * 1.34, y + dy * 1.34, lab, ha="center", va="center",
                fontsize=7.6, fontweight="bold", color=col, linespacing=1.15,
                zorder=13, path_effects=halo())
    ax.add_patch(Circle((x, y), R * 0.07, fc=INK, ec="none", zorder=13))


def titleblock(ax, x, y, w, lines, title="SITE DATA"):
    ax.add_patch(Rectangle((x, y), w, -12 - 11.5 * len(lines), fc="white",
                           ec=INK, lw=1.2, zorder=14))
    ax.text(x + 6, y - 9, title, fontsize=9.5, fontweight="bold", color=INK,
            zorder=15)
    for i, (k, v) in enumerate(lines):
        yy = y - 21.5 - 11.5 * i
        ax.text(x + 6, yy, k, fontsize=7.2, color=MUTED, zorder=15)
        ax.text(x + w - 6, yy, str(v), fontsize=7.2, color=INK, ha="right",
                fontweight="bold", zorder=15)


def notes_block(ax, x, y, lines, step=15, heading_size=8.4, size=7.6):
    for i, ln in enumerate(lines):
        ax.text(x, y - step * i, ln,
                fontsize=heading_size if i == 0 else size,
                color=DIM if i == 0 else MUTED,
                fontweight="bold" if i == 0 else "normal")


def annotate_all(ax, notes, default_color=INK):
    """Free-form callouts declared in site.json."""
    for n in notes or []:
        kw = dict(fontsize=n.get("size", 8.0), color=n.get("color", default_color),
                  ha=n.get("ha", "center"), va=n.get("va", "center"),
                  linespacing=1.4, zorder=n.get("zorder", 12))
        if n.get("bold"):
            kw["fontweight"] = "bold"
        if n.get("rotation"):
            kw["rotation"] = n["rotation"]
        if n.get("italic"):
            kw["style"] = "italic"
        if n.get("arrow_to"):
            ax.annotate(n["text"], xy=tuple(n["arrow_to"]), xytext=tuple(n["at"]),
                        path_effects=halo("white", 3),
                        arrowprops=dict(arrowstyle="-|>", color=kw["color"],
                                        lw=1.1), **kw)
        else:
            if n.get("box"):
                kw["bbox"] = dict(boxstyle="round,pad=0.5", fc="#f8f8f5",
                                  ec="#d6d2c8")
            ax.text(n["at"][0], n["at"][1], n["text"], **kw)


def frame(extent, figsize):
    # An equal-aspect axis inside a figure of a different shape pads one side
    # with dead white space, so the figure follows the extent unless the yard
    # asked for a specific size.
    w, h = extent[1] - extent[0], extent[3] - extent[2]
    if w > 0 and h > 0:
        want = h / w
        have = figsize[1] / figsize[0]
        if abs(want - have) > 0.12:
            figsize = [figsize[0], round(figsize[0] * want, 2)] \
                if want < 2.2 else [round(figsize[1] / want, 2), figsize[1]]
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


# ------------------------------------------------------------------- helpers

class Geom:
    """The handful of numbers every drawing needs, pulled out once."""

    def __init__(self, site):
        b = site["boundary"]
        self.S = site
        self.s = float(b.get("north_fence_slope") or 0.0)
        self.W = float(b["width_east_west"])
        self.C = float(b["south_boundary_offset"])
        self.trees = siteschema.trees(site)
        self.draw = site.get("drawings", {}) or {}

    def nf(self, x):
        """Plot y of the sloped north boundary at x."""
        return -self.s * x

    @property
    def yS(self):
        return -self.C

    def outline(self):
        return [(0, 0), (self.W, self.nf(self.W)), (self.W, self.yS), (0, self.yS)]

    def spec(self, name, key, default=None):
        return (self.draw.get(name, {}) or {}).get(key, default)

    def extent(self, name, default):
        return self.spec(name, "extent", default)

    def zone_polygon(self, z):
        """A zone as a plan polygon, honouring the sloped boundary."""
        x0, x1 = z.get("x", [0, self.W])
        if z.get("y"):
            y0, y1 = z["y"]
            return [(x0, -y0), (x1, -y0), (x1, -y1), (x0, -y1)]
        north = z.get("y_north")
        south = z.get("y_south", self.C)
        south = self.C if not isinstance(south, (int, float)) else south
        if isinstance(north, (int, float)):
            return [(x0, -north), (x1, -north), (x1, -south), (x0, -south)]
        return [(x0, self.nf(x0)), (x1, self.nf(x1)), (x1, -south), (x0, -south)]


def draw_context_shapes(ax, items):
    """Streets, parking, neighbouring ground: whatever the yard sits among."""
    for it in items or []:
        kind = it.get("kind", "area")
        fc = {"street": STREET, "parking": "#f0f0ec", "open": "#f0f0ec",
              "lot": "#f5f5f2"}.get(kind, "#f2f2ee")
        if it.get("rect"):
            x, y, w, h = it["rect"]
            ax.add_patch(Rectangle((x, y), w, h, fc=it.get("fill", fc),
                                   ec=it.get("edge", "none"),
                                   lw=it.get("lw", 0), zorder=it.get("zorder", 0),
                                   ls=(0, (4, 3)) if it.get("dashed") else "-"))
        elif it.get("polygon"):
            ax.add_patch(Polygon([tuple(p) for p in it["polygon"]], closed=True,
                                 fc=it.get("fill", fc),
                                 ec=it.get("edge", "#d6d2c8"),
                                 lw=it.get("lw", 1.0), zorder=it.get("zorder", 0)))
        if it.get("label"):
            ax.text(it["label_at"][0], it["label_at"][1], it["label"],
                    fontsize=it.get("size", 10), color=it.get("color", "#9aa0a6"),
                    fontweight="bold", ha="center",
                    rotation=it.get("rotation", 0), zorder=2)


# ---------------------------------------------------------------- site plan

def draw_plan(site, path):
    g = Geom(site)
    W, C, yS = g.W, g.C, g.yS
    ext = g.extent("plan", [-0.65 * W, 2.85 * W, -1.47 * C, 0.37 * C])
    fig, ax = frame(ext, g.spec("plan", "figsize", [16.5, 12.4]))

    draw_context_shapes(ax, g.spec("plan", "context"))

    # the house, drawn beyond the yard's edge
    ho = site.get("obstructions", {}).get("house")
    if ho:
        y0, y1 = ho["wall_y"]
        width = float(ho.get("width") or 0)
        ax.add_patch(Rectangle((ho["wall_x"], -y1), width, y1 - y0, fc=HOUSE,
                               ec=HOUSE_EDGE, lw=1.6, zorder=1))
        if width:
            ax.text(ho["wall_x"] + width / 2, -(y0 + y1) / 2, "HOUSE",
                    fontsize=15, fontweight="bold", color="#7c7264",
                    ha="center", rotation=90, zorder=2)

    # the yard
    ax.add_patch(Polygon(g.outline(), closed=True, fc=SOIL, ec=INK, lw=2.6,
                         zorder=3))

    for key, z in (site.get("zones") or {}).items():
        style = ZONE_STYLE.get(z.get("style", key.split("_")[-1]),
                               ZONE_STYLE["default"])
        poly = g.zone_polygon(z)
        ax.add_patch(Polygon(poly, closed=True, fc=style[0], ec="none",
                             hatch=z.get("hatch"), alpha=0.95, zorder=4))
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        width = max(p[0] for p in poly) - min(p[0] for p in poly)
        label = (z.get("label_short") or z.get("label") or key).upper()
        # a narrow strip gets its label turned to run along it
        rot = 90 if width < 0.22 * W else 0
        ax.text(cx, cy, label, fontsize=z.get("label_size", 11),
                fontweight="bold", color=style[1], ha="center", va="center",
                rotation=rot, zorder=6, path_effects=halo(style[0], 4))
        if z.get("area_sqft"):
            off = (0, -21) if rot == 0 else (16, 0)
            ax.text(cx + off[0], cy + off[1], f"{z['area_sqft']:.0f} sq ft",
                    fontsize=8.4, color=style[1], ha="center", va="center",
                    rotation=rot, zorder=6, path_effects=halo(style[0], 3))

    # decking, laid across whichever zone is built of boards
    for key, z in (site.get("zones") or {}).items():
        if z.get("style") not in ("patio", "deck") or not z.get("y"):
            continue
        x0, x1 = z.get("x", [0, W])
        y0, y1 = z["y"]
        for i in range(1, int((y1 - y0) / 8)):
            ax.plot([x0, x1], [-y1 + i * 8] * 2, color=WOOD_LINE, lw=0.55,
                    alpha=0.65, zorder=6)

    # anything paved, edged or laid down that is not a zone in its own right
    for ov in (site.get("features") or {}).get("overlays", []):
        pts = [(p[0], -p[1]) for p in ov["polygon"]]
        ax.add_patch(Polygon(pts, closed=True, fc=ov.get("fill", PAVER),
                             ec=ov.get("edge", "#aaa49a"), lw=0.9,
                             hatch=ov.get("hatch"), alpha=0.95, zorder=6))

    # fences
    for f in site.get("obstructions", {}).get("fences", []):
        # Clamped to the yard by default, because a boundary fence drawn past
        # the plot reads as someone else's. A wall that genuinely runs beyond
        # the modelled ground — a house flank, usually — says so and is left
        # alone, with the drawing's own extent deciding what is visible.
        pts = [(p[0], -p[1]) for p in f["points"]]
        if not f.get("extends_beyond_yard"):
            pts = [(max(min(x, W), 0), max(min(y, 0), yS)) for x, y in pts]
        colour = HOUSE_EDGE if "house" in str(f.get("id", "")).lower() else FENCE
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=colour, lw=5.5,
                solid_capstyle="butt", zorder=8, clip_on=True)
    for legacy, pts in (("west_fence", None), ("north_fence", None)):
        blk = site.get("obstructions", {}).get(legacy)
        if not blk:
            continue
        if legacy == "west_fence":
            ax.plot([blk["x"], blk["x"]], [0, yS], color=FENCE, lw=5.5,
                    solid_capstyle="butt", zorder=8)
        else:
            ax.plot([0, W], [0, g.nf(W)], color=FENCE, lw=5.5,
                    solid_capstyle="butt", zorder=8)

    # the house wall along the yard
    if ho:
        ax.plot([ho["wall_x"], ho["wall_x"]], [g.nf(W), yS], color=HOUSE_EDGE,
                lw=5.5, solid_capstyle="butt", zorder=9)

    # half-round wells in a wall
    ww = (site.get("features") or {}).get("window_wells")
    if ww:
        for i, cy in enumerate(ww["centers_y"]):
            ax.add_patch(Wedge((ww.get("wall_x", W), -cy), ww["radius"], 90, 270,
                               fc="#e8eaec", ec=STEEL, lw=1.6, zorder=10))
            ax.text(ww.get("wall_x", W) - ww["radius"] - 6, -cy, f"WW{i + 1}",
                    fontsize=7.4, color="#5f666d", fontweight="bold",
                    ha="right", va="center", zorder=11)

    # overhead planes: awnings, pergolas, the roof edge itself
    for ov in site.get("obstructions", {}).get("overheads", []) or []:
        ox0, ox1 = min(ov["x"]), max(ov["x"])
        oy0, oy1 = min(ov["y"]), max(ov["y"])
        ax.add_patch(Rectangle((ox0, -oy1), ox1 - ox0, oy1 - oy0, fc="none",
                               ec="#8a6d3b", lw=1.6, ls=(0, (7, 4)), zorder=10,
                               clip_on=True))
        ax.text((ox0 + ox1) / 2, -(oy0 + oy1) / 2,
                (ov.get("label") or ov.get("id", "")).upper(),
                fontsize=7.2, fontweight="bold", color="#8a6d3b",
                ha="center", va="center", zorder=11, clip_on=True,
                path_effects=halo("white", 3))

    # trees, crown then trunk. Clipped, because the trees that matter to a
    # shade model are routinely on someone else's lot.
    for n, t in enumerate(g.trees, 1):
        if t.get("crown_radius"):
            ax.add_patch(Circle((t["crown_center_x"], -t["crown_center_y"]),
                                t["crown_radius"], fc=CANOPY, ec="#5c7a4b",
                                lw=1.1, ls=(0, (6, 4)), alpha=0.24, zorder=7,
                                clip_on=True))
    for n, t in enumerate(g.trees, 1):
        ax.add_patch(Circle((t["trunk_x"], -t["trunk_y"]), 7.5, fc="#6b4f34",
                            ec="white", lw=1.2, zorder=11, clip_on=True))
        ax.text(t["trunk_x"] + 15, -t["trunk_y"], str(n), fontsize=8,
                fontweight="bold", color="#6b4f34", va="center", zorder=11,
                clip_on=True)

    # proposed barriers
    for bar in site.get("obstructions", {}).get("proposed_barriers", []):
        pts = bar.get("points", [[0, C], [W, C]])
        ax.plot([p[0] for p in pts], [-p[1] for p in pts], color="#7d3c98",
                lw=3.0, ls=(0, (9, 5)), zorder=10)
        ax.text(sum(p[0] for p in pts) / len(pts), -pts[0][1] - 15,
                bar.get("label", "proposed barrier").upper(),
                fontsize=8.4, color="#7d3c98", fontweight="bold", ha="center")

    # dimensions: the measurements the yard was actually fitted from
    for st in site["boundary"].get("measured_depths", []):
        x = st.get("x")
        if x is None:
            continue
        dim_v(ax, g.nf(x), yS, x, f'{st["depth"]:.0f}"', side=-1, fs=8.4, rot=0,
              label_xy=(x, ext[3] * 0.14))
    dim_v(ax, 0, yS, -34, f'{C:.0f}"  along the west edge', side=-1, fs=8.4)
    dim_h(ax, 0, W, yS - 68, f'{W:.0f}"  ({ftin(W)})', side=-1, fs=9)
    witness(ax, 0, yS, yS - 64)
    witness(ax, W, yS, yS - 64)

    annotate_all(ax, g.spec("plan", "notes"))
    na = g.spec("plan", "north_arrow_at",
                [ext[1] - 0.12 * (ext[1] - ext[0]),
                 ext[2] + 0.86 * (ext[3] - ext[2])])
    north_arrows(ax, na[0], na[1], site, R=52)
    scalebar(ax, ext[0] + 6, ext[2] + 0.07 * (ext[3] - ext[2]), 5)

    ax.text(ext[0] + 4, ext[3] - 12,
            g.spec("plan", "title", f"{site.get('title', site.get('yard', ''))} "
                                    "— DIMENSIONED PLAN"),
            fontsize=16, fontweight="bold", color=INK)
    sub = g.spec("plan", "subtitle",
                 "All dimensions in inches, as measured on site.")
    ax.text(ext[0] + 4, ext[3] - 26, sub, fontsize=9, color=MUTED)

    tb = g.spec("plan", "titleblock") or default_titleblock(site, g)
    tb_x = ext[1] - 0.24 * (ext[1] - ext[0])
    titleblock(ax, tb_x, ext[3] - 0.16 * (ext[3] - ext[2]),
               0.21 * (ext[1] - ext[0]), tb)

    lines = ["VERIFY ON SITE"]
    for v in site.get("verify_on_site", [])[:8]:
        chunks = wrap(v, 46)
        lines.append("· " + chunks[0])
        lines.extend("  " + c for c in chunks[1:])
    if len(lines) > 1:
        notes_block(ax, tb_x, ext[2] + 0.44 * (ext[3] - ext[2]), lines, step=13)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


def default_titleblock(site, g):
    a = site.get("address", {})
    b = site["boundary"]
    rows = []
    if a.get("mailing"):
        rows.append(("Address", a["mailing"]))
    if a.get("lat"):
        rows.append(("Lat / Lon", f"{a['lat']:.5f}, {a['lon']:.5f}"))
    rows.append(("Yard area", f"{b.get('area_sqft', 0):.0f} sq ft"))
    rows.append(("Width", f'{g.W:.0f}"  ({ftin(g.W)})'))
    rows.append(("Depth, west", f'{b.get("depth_along_west_fence", g.C):.0f}"'))
    if b.get("north_fence_angle_off_square_deg"):
        rows.append(("Boundary angle",
                     f"{b['north_fence_angle_off_square_deg']:.2f}° off square"))
    f = site.get("frame", {})
    if f.get("true_bearing_of_plus_x") is not None:
        rows.append(("X axis bearing", f"true {f['true_bearing_of_plus_x']:.2f}°"))
    return rows


# ------------------------------------------------------------------- context

def draw_context(site, path):
    """The yard's position on the lot, with the neighbours that cast shade."""
    g = Geom(site)
    W, C = g.W, g.C
    ext = g.extent("context", [-1.25 * W, 3.4 * W, -3.3 * C, 1.25 * C])
    fig, ax = frame(ext, g.spec("context", "figsize", [11.6, 15.0]))

    draw_context_shapes(ax, g.spec("context", "context"))

    for bd in site.get("obstructions", {}).get("context_buildings", []):
        xs = [p[0] for p in bd["polygon"]]
        ys = [-p[1] for p in bd["polygon"]]
        if max(xs) < ext[0] or min(xs) > ext[1] or max(ys) < ext[2] \
                or min(ys) > ext[3]:
            continue
        ax.add_patch(Polygon(list(zip(xs, ys)), closed=True, fc="#e4e4e0",
                             ec="#c2beb5", lw=0.9, zorder=1))
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        if ext[0] < mx < ext[1] and ext[2] < my < ext[3]:
            ax.text(mx, my, f"{bd['height'] / 12:.0f} ft", fontsize=6.6,
                    color="#a5a09a", ha="center", va="center", zorder=2)

    ho = site.get("obstructions", {}).get("house")
    if ho:
        y0, y1 = ho["wall_y"]
        ax.add_patch(Rectangle((ho["wall_x"], -y1), float(ho.get("width") or 0),
                               y1 - y0, fc=HOUSE, ec=HOUSE_EDGE, lw=1.8, zorder=3))

    if site.get("address", {}).get("lot_polygon"):
        ax.add_patch(Polygon([(p[0], -p[1]) for p in
                              site["address"]["lot_polygon"]], closed=True,
                             fc="none", ec="#b03a2e", lw=1.6, ls=(0, (8, 5)),
                             zorder=2))

    ax.add_patch(Polygon(g.outline(), closed=True, fc="#cfe0b8", ec=INK, lw=2.4,
                         zorder=5))
    ax.text(W / 2, -C / 2, f"THE YARD\n{site['boundary'].get('area_sqft', 0):.0f}"
                           " sq ft", fontsize=12, fontweight="bold",
            color="#5d7345", ha="center", va="center", linespacing=1.4, zorder=6)

    annotate_all(ax, g.spec("context", "notes"))
    north_arrows(ax, ext[1] - 0.10 * (ext[1] - ext[0]),
                 ext[3] - 0.10 * (ext[3] - ext[2]), site, R=96)
    scalebar(ax, ext[0] + 8, ext[2] + 0.06 * (ext[3] - ext[2]), 20)
    ax.text(ext[0] + 4, ext[3] - 20,
            g.spec("context", "title", "THE YARD IN CONTEXT"), fontsize=15,
            fontweight="bold", color=INK)
    ax.text(ext[0] + 4, ext[3] - 44, g.spec(
        "context", "subtitle",
        "Neighbouring footprints and heights from OSM and city data."),
        fontsize=8.6, color=MUTED)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# ----------------------------------------------------------------- elevation

def draw_elevation(site, path):
    """Looking at the primary wall. Horizontal axis runs along the wall."""
    g = Geom(site)
    ho = site.get("obstructions", {}).get("house")
    if not ho:
        return
    W, C = g.W, g.C
    y0 = g.s * W
    eave = ho["eave_height"]
    ridge = float(ho.get("ridge_height") or eave)
    ext = g.extent("elevation", [y0 - 96, C + 116, -52, ridge + 86])
    fig, ax = frame(ext, g.spec("elevation", "figsize", [10.4, 8.6]))

    ax.add_patch(Rectangle((y0, 0), C - y0, eave, fc=HOUSE, ec=HOUSE_EDGE,
                           lw=2.0, zorder=3))
    if ridge > eave:
        ax.add_patch(Rectangle((y0, eave), C - y0, ridge - eave, fc="#eae4da",
                               ec=HOUSE_EDGE, lw=1.0, ls=(0, (6, 4)), zorder=2))
        ax.text((y0 + C) / 2, eave + 30,
                f"roof behind — ridge {ridge / 12:.0f} ft", fontsize=8,
                color="#948a7c", ha="center", zorder=4)
    ax.text((y0 + C) / 2, eave * 0.62, "HOUSE WALL", fontsize=13,
            fontweight="bold", color="#7c7264", ha="center", zorder=4)

    ax.plot([ext[0] + 22, ext[1] - 22], [0, 0], color=INK, lw=2.2, zorder=5)
    for x in range(int(ext[0] + 26), int(ext[1] - 22), 11):
        ax.plot([x, x - 7], [0, -7], color=MUTED, lw=0.6, zorder=4)

    ww = (site.get("features") or {}).get("window_wells")
    if ww:
        for i, cy in enumerate(ww["centers_y"]):
            ax.add_patch(Wedge((cy, 0), ww["radius"], 0, 180, fc="#e8eaec",
                               ec=STEEL, lw=1.6, zorder=7))
            ax.plot([cy - ww["radius"], cy + ww["radius"]],
                    [ww["guard_height"], ww["guard_height"]], color=STEEL,
                    lw=2.4, zorder=8)
            ax.text(cy, -19, f"WW{i + 1}", fontsize=7.8, color="#5f666d",
                    fontweight="bold", ha="center", zorder=8)

    for f in site.get("obstructions", {}).get("fences", []) or []:
        pass
    nf = site.get("obstructions", {}).get("north_fence")
    if nf:
        ax.plot([y0, y0], [0, nf["height"]], color=FENCE, lw=4.0, zorder=6)
        ax.annotate(f"north fence  {nf['height'] / 12:.0f} ft",
                    xy=(y0 + 3, nf["height"] * 0.72), xytext=(y0 + 46, 104),
                    fontsize=7.8, color=FENCE, fontweight="bold", ha="left",
                    arrowprops=dict(arrowstyle="-|>", color=FENCE, lw=1.0))

    levels = [(eave, f"{eave / 12:.0f} ft eave")]
    if ridge > eave:
        levels.append((ridge, f"{ridge / 12:.0f} ft ridge"))
    if nf:
        levels.insert(0, (nf["height"], f"{nf['height'] / 12:.0f} ft fence"))
    for h, lab in levels:
        ax.plot([ext[0] + 6, C + 62], [h, h], color="#c9ccce", lw=0.7,
                ls=(0, (6, 5)), zorder=1)
        ax.text(C + 66, h, lab, fontsize=7.2, color=MUTED, va="center")

    dim_v(ax, 0, eave, y0 - 50, f'{eave:.0f}"  ({eave / 12:.0f} ft)', side=-1, fs=8)
    dim_h(ax, y0, C, -32, f'{C - y0:.0f}"  yard length along the wall',
          side=-1, fs=8.4)

    annotate_all(ax, g.spec("elevation", "notes"))
    ax.text(ext[0] + 4, ext[3] - 8, g.spec(
        "elevation", "title", "ELEVATION — LOOKING AT THE HOUSE WALL"),
        fontsize=14, fontweight="bold", color=INK)
    ax.text(ext[0] + 4, ext[3] - 28, g.spec("elevation", "subtitle", ""),
            fontsize=8.6, color=MUTED)
    scalebar(ax, C + 10, ext[3] - 56, 5)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# ------------------------------------------------------------------- section

def crown_polygon(cx, cr, base, top, n=26):
    """Crown silhouette: broadest a little above mid-height."""
    pts = []
    for i in range(n + 1):
        f = i / n
        w = cr * math.sin(math.pi * (0.18 + 0.82 * f)) ** 0.75
        pts.append((cx + w, base + f * (top - base)))
    for i in range(n, -1, -1):
        f = i / n
        w = cr * math.sin(math.pi * (0.18 + 0.82 * f)) ** 0.75
        pts.append((cx - w, base + f * (top - base)))
    return pts


def draw_section(site, path):
    """A cut across the yard: what is tall, and how far away it stands."""
    g = Geom(site)
    W = g.W
    ho = site.get("obstructions", {}).get("house") or {}
    eave = float(ho.get("eave_height") or 0)
    ridge = float(ho.get("ridge_height") or eave)
    tallest = max([t.get("height") or 0 for t in g.trees] + [ridge, 1.0])
    ext = g.extent("section", [-1.45 * W, 3.0 * W, -0.65 * W, tallest * 1.42])
    fig, ax = frame(ext, g.spec("section", "figsize", [15.0, 14.2]))

    ax.plot([ext[0], ext[1]], [0, 0], color=INK, lw=2.2, zorder=6)
    for x in range(int(ext[0]) + 4, int(ext[1]), 14):
        ax.plot([x, x - 9], [0, -10], color="#c4c8ca", lw=0.6, zorder=3)
    ax.add_patch(Rectangle((0, -44), W, 44, fc=SOIL, ec="none", zorder=2))

    # trees, collapsed onto the section by their distance across the yard
    by_x = {}
    for t in g.trees:
        by_x.setdefault(round(t["crown_center_x"], 1), []).append(t)
    graze = None
    for cx, group in by_x.items():
        t = max(group, key=lambda q: q["height"])
        cr = t.get("crown_radius") or 0
        base = t["crown_base_height"]
        crown = crown_polygon(cx, cr, base, t["height"])
        ax.add_patch(Polygon(crown, closed=True, fc=CANOPY, ec="#4e6b3d", lw=1.3,
                             alpha=0.32, zorder=4))
        for k, _ in enumerate(group):
            dx = (k - (len(group) - 1) / 2.0) * 6
            ax.add_patch(Rectangle((cx + dx - 3.5, 0), 7, base, fc="#6b4f34",
                                   ec="none", alpha=0.9, zorder=5))
        outer = max(crown, key=lambda p: p[0])
        if graze is None or outer[1] > graze[1]:
            graze = outer
        dim_v(ax, 0, t["height"], cx - 128,
              f'{t["height"] / 12:.0f} ft', side=-1, fs=9)
        dim_v(ax, 0, base, cx - 58, f'crown base\n{base / 12:.0f} ft', side=-1,
              fs=7.4, rot=0)

    if ho:
        far = ho["wall_x"] + float(ho.get("width") or 0)
        ax.add_patch(Polygon([(ho["wall_x"], 0), (ho["wall_x"], eave),
                              (ho.get("ridge_x", ho["wall_x"]), ridge),
                              (far, eave), (far, 0)], closed=True, fc=HOUSE,
                             ec=HOUSE_EDGE, lw=2.0, zorder=5))
        ax.text((ho["wall_x"] + far) / 2, 96, "HOUSE", fontsize=13,
                fontweight="bold", color="#7c7264", ha="center", zorder=6)
        dim_v(ax, 0, eave, far + 24, f"{eave / 12:.0f} ft eave", side=1, fs=8)
        if ridge > eave:
            dim_v(ax, 0, ridge, far + 118, f"{ridge / 12:.0f} ft ridge", side=1,
                  fs=8)

    wf = site.get("obstructions", {}).get("west_fence")
    if wf:
        ax.plot([wf["x"], wf["x"]], [0, wf["height"]], color=FENCE, lw=5.0,
                zorder=7)
        ax.text(wf["x"] - 18, wf["height"] * 0.53,
                f"{wf['height'] / 12:.0f} ft fence", fontsize=8, color=FENCE,
                fontweight="bold", rotation=90, va="center", ha="center")

    # the altitude needed to see over each obstruction, from a few spots
    if graze and ho:
        for x0, tgt, col, tf in ((ho["wall_x"] - 4, graze, "#b03a2e", 0.80),
                                 (W / 7.0, graze, "#b03a2e", 0.34),
                                 (0, (ho["wall_x"], eave), "#1f6f8b", 0.58),
                                 (W / 2.0, (ho["wall_x"], eave), "#1f6f8b", 0.34)):
            if abs(tgt[0] - x0) < 1:
                continue
            ang = math.degrees(math.atan2(tgt[1], abs(tgt[0] - x0)))
            ax.plot([x0, tgt[0]], [0, tgt[1]], color=col, lw=1.2, ls=(0, (7, 4)),
                    zorder=8)
            ax.text(x0 + (tgt[0] - x0) * tf, tgt[1] * tf, f"{ang:.0f}°",
                    fontsize=8.6, color=col, fontweight="bold", ha="center",
                    va="center", zorder=9, path_effects=halo("white", 3.4))

    # real afternoon sun in this plane, and where its shade line lands
    if graze:
        sun = solar.SolarSite.from_site(site)
        wall_az = site.get("bearings_true", {}).get(
            "house_west_wall_faces",
            (site["frame"]["true_bearing_of_plus_x"] + 180.0) % 360.0)
        doy = solar.DOY["Jun 21"]
        y_lab = ext[3] * 0.88
        for hh in g.spec("section", "sun_hours", [13.0, 14.0, 15.0]):
            pa = solar.profile_angle(*sun.position(doy, hh), wall_azimuth=wall_az)
            if pa is None or pa <= 1:
                continue
            t = math.tan(math.radians(pa))
            land = graze[0] + graze[1] / t
            h_wall = graze[1] - (W - graze[0]) * t
            inside = land <= W
            col = "#e0a11b" if inside else "#c0392b"
            end = (land, 0.0) if inside else (W, max(h_wall, 0.0))
            x_top = graze[0] - (y_lab - graze[1]) / t
            ax.annotate("", xy=end, xytext=(x_top, y_lab),
                        arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6,
                                        alpha=0.92), zorder=10)
            ax.text(x_top, y_lab + 12,
                    f"{solar.fmt_clock(sun.solar_to_clock(doy, hh))}\n"
                    f"{pa:.0f}° in plane", fontsize=7.6, color=col,
                    fontweight="bold", ha="center", va="bottom",
                    linespacing=1.3, zorder=11)
            if inside:
                ax.plot([land], [0], marker="v", ms=9, color=col, zorder=11)
        ax.add_patch(Circle((graze[0], graze[1]), 6.5, fc="#c0392b", ec="white",
                            lw=1.2, zorder=12))

    dim_h(ax, 0, W, -74, f'{W:.0f}"  yard width', side=-1, fs=8.6)
    annotate_all(ax, g.spec("section", "notes"))
    ax.text(ext[0] + 4, ext[3] - 10, g.spec(
        "section", "title", "SECTION — LOOKING ACROSS THE YARD"), fontsize=14,
        fontweight="bold", color=INK)
    ax.text(ext[0] + 4, ext[3] - 28, g.spec("section", "subtitle", ""),
            fontsize=8.6, color=MUTED)
    scalebar(ax, ext[0] + 4, ext[3] * 0.84, 5)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


def run(slug, outdir=None):
    site = yards.load_site(slug)
    outdir = outdir or os.path.join(yards.yard_dir(slug), "maps")
    os.makedirs(outdir, exist_ok=True)
    draw_plan(site, os.path.join(outdir, "site-plan.png"))
    draw_context(site, os.path.join(outdir, "site-context.png"))
    draw_elevation(site, os.path.join(outdir, "elevation.png"))
    draw_section(site, os.path.join(outdir, "section.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()
    run(args.slug, args.outdir)


if __name__ == "__main__":
    main()
