#!/usr/bin/env python3
"""Measuring trees and buildings from USGS 3DEP lidar.

    python3 -m lib.lidar --coverage 39.7392 -104.9903
    python3 -m lib.lidar <slug> [--radius 150] [--write]

The single most consequential unknown in a shade model is how wide a tree crown
is and how high off the ground it starts. Both are nearly impossible to eyeball
from inside a yard, where you can see where the leaves stop on the near side and
nothing at all about the far side. Airborne lidar sees the whole crown from
above, so it answers both.

Data
----
USGS 3DEP publishes classified point clouds as Entwine Point Tiles on AWS Open
Data. No key, no account, no quota:

    coverage    hobuinc/usgs-lidar boundaries/resources.geojson
    tiles       s3-us-west-2.amazonaws.com/usgs-lidar-public/<project>/

ASPRS classifications used here: 2 ground, 5 high vegetation, 6 building.

Method and its limits
---------------------
Ground returns build a coarse terrain surface, and every other point is measured
against it, so a sloping yard does not turn into a tall tree.

Vegetation returns become a canopy height model, local maxima in it become tree
apexes, and points are assigned to the nearest apex. Per tree the height is
solid, the crown radius is good, and the crown base is the weakest of the three:
airborne lidar sees the top of a crown far better than the bottom, and a tree
standing over a shrub will read as having no trunk at all. Every number comes
back with the count of points behind it so a thin sample is visible as a thin
sample.

Building returns give an eave height from the roof edge and a ridge height from
the peak. A flat roof reports the two within a foot of each other, which is the
correct answer for a flat roof.

The survey is a snapshot with a date on it. A crown measured in 2017 is not the
crown standing there now, and the reported year is carried into site.json so
that ages visibly rather than silently.
"""
import argparse
import io
import json
import math
import os
import sys
import urllib.request

import numpy as np

from . import frame, siteschema, yards

RESOURCES = ("https://raw.githubusercontent.com/hobuinc/usgs-lidar/master/"
             "boundaries/resources.geojson")
EPT_ROOT = "https://s3-us-west-2.amazonaws.com/usgs-lidar-public"
CACHE = os.path.join(yards.GARDEN_ROOT, ".cache", "lidar")
UA = {"User-Agent": "yard-survey/1.0 (personal garden planning)"}

GROUND, LOW_VEG, MED_VEG, HIGH_VEG, BUILDING = 2, 3, 4, 5, 6
M_TO_IN = 39.3700787
M_TO_FT = 3.280839895


# --------------------------------------------------------------------- fetch

def _get(url, binary=False, cache_key=None, timeout=120):
    if cache_key:
        os.makedirs(CACHE, exist_ok=True)
        p = os.path.join(CACHE, cache_key.replace("/", "__"))
        if os.path.exists(p):
            with open(p, "rb") as fh:
                data = fh.read()
            return data if binary else data.decode()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        data = fh.read()
    if cache_key:
        with open(os.path.join(CACHE, cache_key.replace("/", "__")), "wb") as fh:
            fh.write(data)
    return data if binary else data.decode()


def _json(url, cache_key=None):
    return json.loads(_get(url, cache_key=cache_key))


def _point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xin = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < xin:
                inside = not inside
    return inside


def _covers(geom, lon, lat):
    polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
             else geom["coordinates"])
    for poly in polys:
        if poly and _point_in_ring(lon, lat, poly[0]):
            return True
    return False


def _year(name):
    """USGS project names usually carry their survey year. NY_NewYorkCity does
    not, which is why the points themselves get asked as well."""
    import re
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", name)]
    return max(years) if years else None


GPS_EPOCH_UNIX = 315964800          # 1980-01-06, when GPS time started counting
GPS_UTC_LEAP = 18                   # GPS runs ahead of UTC by this many seconds


def flight_dates(gps_time):
    """When the plane actually flew, read from the points' own timestamps.

    A project name is a poor source for this and sometimes has no year in it at
    all. The GPS timestamp on every return is unambiguous. LAS files store either
    standard GPS time or, far more commonly, adjusted standard GPS time, which is
    the same number less a billion; the two are told apart by magnitude.
    """
    import datetime
    t = np.asarray(gps_time, dtype=float)
    t = t[np.isfinite(t) & (t > 0)]
    if t.size == 0:
        return None
    if np.median(t) < 1e9:
        t = t + 1e9
    unix = t + GPS_EPOCH_UNIX - GPS_UTC_LEAP
    lo, hi = float(unix.min()), float(unix.max())
    to_d = lambda u: datetime.datetime.utcfromtimestamp(u).date()
    try:
        first, last = to_d(lo), to_d(hi)
    except (OverflowError, OSError, ValueError):
        return None
    if not (1990 < first.year < 2100):
        return None
    return {"first": first.isoformat(), "last": last.isoformat(),
            "year": last.year, "month": last.month,
            "note": "read from the GPS timestamp on the returns themselves"}


def leaf_state(flown, lat):
    """Whether the flight caught the trees in leaf, and what that costs.

    Most 3DEP acquisitions are deliberately flown leaf-off, because bare
    branches let the pulse through to the ground and that is what a terrain
    model needs. It is the worst possible season for measuring a crown: the
    height is still right, but the spread is the spread of the branch structure,
    which a deciduous tree overhangs by a good margin once it leafs out.
    """
    if not flown:
        return None
    m = flown.get("month")
    if m is None:
        return None
    if lat >= 0:
        on = 5 <= m <= 9
    else:
        on = m <= 3 or m >= 11
    if on:
        return {"in_leaf": True,
                "note": f"flown in month {m}, so deciduous crowns were in leaf "
                        f"and the measured spread is the real summer spread"}
    return {"in_leaf": False,
            "note": f"flown in month {m}, leaf-off. Heights hold, but a deciduous "
                    f"crown's measured spread is its bare branch structure and "
                    f"will read narrow against its summer shade footprint. "
                    f"Evergreens are unaffected"}


def coverage(lat, lon):
    """Every 3DEP project whose boundary contains this point, newest first."""
    fc = _json(RESOURCES, cache_key="resources.geojson")
    hits = []
    for feat in fc["features"]:
        props = feat.get("properties", {})
        name = props.get("name")
        geom = feat.get("geometry")
        if not name or not geom:
            continue
        try:
            if _covers(geom, lon, lat):
                hits.append({"name": name, "points": props.get("count"),
                             "year": _year(name),
                             "url": f"{EPT_ROOT}/{name}/ept.json"})
        except Exception:
            continue
    hits.sort(key=lambda h: (h.get("year") or 0), reverse=True)
    return hits


# ----------------------------------------------------------------------- EPT

class EPT:
    """One Entwine Point Tile pyramid, queried over a small box."""

    def __init__(self, project):
        self.project = project
        self.base = f"{EPT_ROOT}/{project}"
        self.info = _json(f"{self.base}/ept.json", cache_key=f"{project}.ept.json")
        self.bounds = self.info["bounds"]
        self.span = self.info.get("span", 128)
        self.year = _year(project)
        self._hier = {}

    # ---- coordinate systems
    def crs(self):
        from rasterio.crs import CRS
        srs = self.info.get("srs", {})
        if srs.get("horizontal"):
            return CRS.from_epsg(int(srs["horizontal"]))
        if srs.get("wkt"):
            return CRS.from_wkt(srs["wkt"])
        raise ValueError(f"{self.project} declares no horizontal SRS")

    def project_xy(self, lon, lat):
        from rasterio.crs import CRS
        from rasterio.warp import transform
        xs, ys = transform(CRS.from_epsg(4326), self.crs(), [lon], [lat])
        return xs[0], ys[0]

    def units_to_m(self):
        """3DEP projects publish in metres or in US survey feet."""
        try:
            unit = self.crs().linear_units.lower()
        except Exception:
            unit = "metre"
        return 0.3048006096012192 if "foot" in unit or "feet" in unit else 1.0

    def local_scale(self, lon, lat, probe_m=200.0):
        """Projected distance per true ground metre, measured at this spot.

        Not cosmetic. Several 3DEP projects, New York City among them, publish in
        Web Mercator, whose scale factor is 1/cos(latitude): at 40.8 degrees a
        crown that is really 20 ft across measures 26 ft if this is ignored. State
        plane and UTM are much closer to unity but not exactly one either, so the
        factor is measured rather than assumed, by projecting two points a known
        distance apart.
        """
        dlat = probe_m / 111320.0
        x0, y0 = self.project_xy(lon, lat)
        x1, y1 = self.project_xy(lon, lat + dlat)
        u2m = self.units_to_m()
        return math.hypot(x1 - x0, y1 - y0) * u2m / probe_m

    # ---- octree walk
    def _node_bounds(self, key):
        d, x, y, z = (int(v) for v in key.split("-"))
        n = 2 ** d
        x0, y0, z0, x1, y1, z1 = self.bounds
        sx, sy, sz = (x1 - x0) / n, (y1 - y0) / n, (z1 - z0) / n
        return (x0 + x * sx, y0 + y * sy, z0 + z * sz,
                x0 + (x + 1) * sx, y0 + (y + 1) * sy, z0 + (z + 1) * sz)

    def _hierarchy(self, key):
        if key not in self._hier:
            self._hier[key] = _json(
                f"{self.base}/ept-hierarchy/{key}.json",
                cache_key=f"{self.project}.h.{key}.json")
        return self._hier[key]

    def _nodes(self, box, max_depth):
        """Keys of every populated node overlapping the box, all depths.

        EPT is progressive: a node holds points the coarser levels did not, so
        every depth down the chain contributes and the deepest alone is not
        enough.
        """
        found = []
        table = self._hierarchy("0-0-0-0")
        stack = ["0-0-0-0"]
        seen = set()
        while stack:
            key = stack.pop()
            if key in seen:
                continue
            seen.add(key)
            count = table.get(key)
            if count is None:
                continue
            if count == -1:
                try:
                    table = dict(table, **self._hierarchy(key))
                except Exception:
                    continue
                count = table.get(key, 0)
                if count in (None, -1):
                    continue
            bx = self._node_bounds(key)
            if bx[3] < box[0] or bx[0] > box[2] or bx[4] < box[1] or bx[1] > box[3]:
                continue
            if count > 0:
                found.append(key)
            d = int(key.split("-")[0])
            if d >= max_depth:
                continue
            _, x, y, z = (int(v) for v in key.split("-"))
            for dx in (0, 1):
                for dy in (0, 1):
                    for dz in (0, 1):
                        stack.append(f"{d + 1}-{2 * x + dx}-{2 * y + dy}-{2 * z + dz}")
        return found

    def query(self, box, max_depth=12, verbose=True):
        """Every point in the box, as a dict of arrays.

        Returns x, y, z and classification always, and returns/number_of_returns
        and RGB when the delivery carries them, because those are what make it
        possible to tell a tree from a roof in a delivery that never classified
        either.
        """
        import laspy
        keys = self._nodes(box, max_depth)
        if verbose:
            print(f"  {len(keys)} EPT nodes overlap the query box")
        cols = {k: [] for k in ("x", "y", "z", "c", "rn", "nr", "t",
                                "r", "g", "b")}
        for key in keys:
            try:
                raw = _get(f"{self.base}/ept-data/{key}.laz", binary=True,
                           cache_key=f"{self.project}.d.{key}.laz")
            except Exception as exc:
                if verbose:
                    print(f"  node {key} unavailable: {exc}")
                continue
            las = laspy.read(io.BytesIO(raw))
            x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
            sel = (x >= box[0]) & (x <= box[2]) & (y >= box[1]) & (y <= box[3])
            if not sel.any():
                continue
            cols["x"].append(x[sel])
            cols["y"].append(y[sel])
            cols["z"].append(z[sel])
            cols["c"].append(np.asarray(las.classification)[sel])
            for name, src in (("rn", "return_number"),
                              ("nr", "number_of_returns"), ("t", "gps_time"),
                              ("r", "red"), ("g", "green"), ("b", "blue")):
                try:
                    cols[name].append(np.asarray(las[src])[sel])
                except Exception:
                    pass
        out = {}
        for k, parts in cols.items():
            out[k] = np.concatenate(parts) if parts else np.array([])
        return out


# ------------------------------------------------- classification, or its absence

OVERLAP_BIT = 16


def normalize_classes(c):
    """Undo the pre-LAS-1.4 convention of flagging overlap by adding 16.

    New York City's delivery arrives as classes 1, 2, 17 and 18, which is
    unclassified and ground twice over: once for the primary swath and once for
    the overlap between flight lines. Read literally, 17 and 18 mean bridge deck
    and high noise, and a whole neighbourhood turns into bridges.
    """
    present = {int(v) for v in np.unique(c)}
    overlap = {v for v in present if OVERLAP_BIT <= v < 32
               and (v - OVERLAP_BIT) in present}
    if not overlap:
        return c, None
    out = c.copy()
    for v in overlap:
        out[c == v] = v - OVERLAP_BIT
    return out, sorted(overlap)


def infer_classes(pts, h_ft, cls, min_height_ft=6.0, cell_ft=3.0):
    """Separate vegetation from building when the delivery never did.

    Plenty of 3DEP deliveries stop at ground and unclassified, which leaves the
    two things a shade model needs most sitting in the same undifferentiated
    heap. Three signals pull them apart, and they are combined per cell rather
    than per point because any one of them is noisy on its own:

        multiple returns   a pulse that got through the top of something and
                           kept going hit foliage, not a roof
        greenness          when the delivery carries RGB, an excess-green index
                           separates a canopy from a shingle roof outright
        roughness          the spread of heights inside a small cell is large in
                           a crown and small on a roof plane, except at its edges

    This is inference, not classification, and it is labelled that way all the
    way through to site.json.
    """
    above = (h_ft >= min_height_ft) & (cls != GROUND)
    veg = np.zeros(h_ft.shape, dtype=bool)
    bld = np.zeros(h_ft.shape, dtype=bool)
    if not above.any():
        return veg, bld, "no above-ground returns"

    x, y = pts["x"], pts["y"]
    gx = np.floor(x / (cell_ft / M_TO_FT)).astype(int)
    gy = np.floor(y / (cell_ft / M_TO_FT)).astype(int)

    have_rgb = pts["r"].size == h_ft.size and pts["r"].size > 0
    if have_rgb:
        r = pts["r"].astype(float)
        g = pts["g"].astype(float)
        b = pts["b"].astype(float)
        exg = (2 * g - r - b) / np.maximum(r + g + b, 1.0)
    have_ret = pts["nr"].size == h_ft.size and pts["nr"].size > 0
    multi = pts["nr"] > 1 if have_ret else np.zeros(h_ft.shape, dtype=bool)

    cells = {}
    idx = np.nonzero(above)[0]
    for i in idx:
        cells.setdefault((gx[i], gy[i]), []).append(i)

    for cell, members in cells.items():
        m = np.array(members)
        hs = h_ft[m]
        score = 0
        if have_ret and multi[m].mean() > 0.25:
            score += 1
        if have_rgb and float(np.median(exg[m])) > 0.02:
            score += 1
        if hs.size > 2 and float(hs.std()) > 2.5:
            score += 1
        need = 2 if (have_rgb and have_ret) else 1
        if score >= need:
            veg[m] = True
        else:
            bld[m] = True

    signals = [n for n, ok in (("multiple returns", have_ret),
                               ("RGB greenness", have_rgb),
                               ("height roughness", True)) if ok]
    return veg, bld, ("inferred from " + ", ".join(signals) +
                      "; the delivery classified neither vegetation nor building")


# ------------------------------------------------------------------ analysis

def terrain(x, y, z, cell_m):
    """Coarse ground surface, and a function giving ground height anywhere."""
    if x.size == 0:
        return lambda qx, qy: np.zeros_like(qx)
    gx = np.floor(x / cell_m).astype(int)
    gy = np.floor(y / cell_m).astype(int)
    table = {}
    for kx, ky, kz in zip(gx, gy, z):
        table.setdefault((kx, ky), []).append(kz)
    med = {k: float(np.median(v)) for k, v in table.items()}
    fallback = float(np.median(z))

    def ground(qx, qy):
        out = np.full(np.shape(qx), fallback, dtype=float)
        qgx = np.floor(np.asarray(qx) / cell_m).astype(int)
        qgy = np.floor(np.asarray(qy) / cell_m).astype(int)
        flat = out.ravel()
        for i, (kx, ky) in enumerate(zip(qgx.ravel(), qgy.ravel())):
            v = med.get((kx, ky))
            if v is None:                       # widen the search one ring
                best = [med[(kx + dx, ky + dy)]
                        for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                        if (kx + dx, ky + dy) in med]
                v = float(np.median(best)) if best else fallback
            flat[i] = v
        return out
    return ground


def _grid_max(x, y, h, cell):
    """Highest return in each cell: a canopy or roof height model."""
    gx = np.floor(x / cell).astype(int)
    gy = np.floor(y / cell).astype(int)
    grid = {}
    for kx, ky, kh in zip(gx, gy, h):
        k = (kx, ky)
        if kh > grid.get(k, -1e9):
            grid[k] = kh
    return grid


def _components(cells, connectivity=8):
    """Connected groups of occupied cells."""
    nbr = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        nbr += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    seen = set()
    out = []
    for c in cells:
        if c in seen:
            continue
        stack, group = [c], []
        seen.add(c)
        while stack:
            cur = stack.pop()
            group.append(cur)
            for dx, dy in nbr:
                n = (cur[0] + dx, cur[1] + dy)
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(group)
    return out


def _hull(points):
    """Convex hull, monotone chain. Enough for a footprint outline."""
    pts = sorted(set(map(tuple, points)))
    if len(pts) <= 2:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and \
                    (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) - \
                    (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0]) <= 0:
                out.pop()
            out.append(p)
        return out
    return half(pts)[:-1] + half(pts[::-1])[:-1]


def crown_base(heights, bin_ft=2.0):
    """Height at which the crown's returns thin out to nothing.

    Walking down from the densest layer, the base is where the return density
    falls below a tenth of the peak. That is the honest reading of a vertical
    profile, and it is systematically a little high on a tree standing over
    shrubs, because the shrub returns fill in what would otherwise be the gap.
    """
    if heights.size < 12:
        return None, "too few returns to read a vertical profile"
    top = float(np.percentile(heights, 99))
    edges = np.arange(0, top + bin_ft, bin_ft)
    counts, _ = np.histogram(heights, bins=edges)
    if counts.max() == 0:
        return None, "no returns"
    peak = int(np.argmax(counts))
    thresh = counts.max() * 0.10
    i = peak
    while i > 0 and counts[i - 1] >= thresh:
        i -= 1
    return float(edges[i]), (f"vertical profile thins below {thresh:.0f} returns "
                             f"per {bin_ft:.0f} ft band under this height")


def find_trees(x, y, h, cell_ft=2.0, min_height_ft=12.0, window_ft=10.0,
               max_radius_ft=45.0):
    """Segment vegetation returns into trees.

    A canopy height model, local maxima as apexes, points to the nearest apex.
    Trees planted close together merge into one crown, which is not a failure of
    the method: to a beam of light a merged canopy really is one obstruction.
    """
    keep = h >= min_height_ft
    x, y, h = x[keep], y[keep], h[keep]
    if x.size < 30:
        return []

    chm = _grid_max(x, y, h, cell_ft)
    win = max(int(round(window_ft / cell_ft)), 1)
    peaks = []
    for (kx, ky), kh in chm.items():
        best = True
        for dx in range(-win, win + 1):
            for dy in range(-win, win + 1):
                other = chm.get((kx + dx, ky + dy))
                if other is not None and (other > kh or
                                          (other == kh and (dx, dy) < (0, 0))):
                    best = False
                    break
            if not best:
                break
        if best:
            peaks.append(((kx + 0.5) * cell_ft, (ky + 0.5) * cell_ft, kh))
    if not peaks:
        return []

    px = np.array([p[0] for p in peaks])
    py = np.array([p[1] for p in peaks])
    d2 = (x[:, None] - px[None, :]) ** 2 + (y[:, None] - py[None, :]) ** 2
    owner = np.argmin(d2, axis=1)
    near = np.sqrt(d2[np.arange(x.size), owner]) <= max_radius_ft

    trees = []
    for i, (ax_, ay_, ah) in enumerate(peaks):
        sel = (owner == i) & near
        n = int(sel.sum())
        if n < 30:
            continue
        hs = h[sel]
        height = float(np.percentile(hs, 99))
        top = hs >= height - 3.0
        apex_x = float(np.mean(x[sel][top])) if top.any() else ax_
        apex_y = float(np.mean(y[sel][top])) if top.any() else ay_
        r = np.sqrt((x[sel] - apex_x) ** 2 + (y[sel] - apex_y) ** 2)
        base, base_note = crown_base(hs)
        crown = hs >= (base or 0) + 1.0
        radius = float(np.percentile(r[crown], 90)) if crown.sum() > 10 \
            else float(np.percentile(r, 90))
        trees.append({
            "apex_x_m": apex_x, "apex_y_m": apex_y,
            "height_ft": round(height, 1),
            "crown_radius_ft": round(radius, 1),
            "crown_base_ft": round(base, 1) if base is not None else None,
            "crown_base_note": base_note,
            "returns": n,
            "spread_ft": round(radius * 2, 1),
        })
    trees.sort(key=lambda t: -t["height_ft"])
    return trees


def find_buildings(x, y, h, zmin_ft=6.0, cell_ft=2.0, min_cells=40):
    """Building returns to footprints with eave and ridge heights."""
    keep = h >= zmin_ft
    x, y, h = x[keep], y[keep], h[keep]
    if x.size < min_cells:
        return []
    grid = _grid_max(x, y, h, cell_ft)
    out = []
    for group in _components(set(grid)):
        if len(group) < min_cells:
            continue
        hs = np.array([grid[c] for c in group])
        pts = [((c[0] + 0.5) * cell_ft, (c[1] + 0.5) * cell_ft) for c in group]
        hull = _hull(pts)
        # the eave is the roof edge: cells with a missing neighbour
        edge = [grid[c] for c in group
                if any((c[0] + dx, c[1] + dy) not in grid
                       for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))]
        eave = float(np.median(edge)) if edge else float(np.percentile(hs, 20))
        ridge = float(np.percentile(hs, 98))
        out.append({
            "eave_ft": round(eave, 1),
            "ridge_ft": round(ridge, 1),
            "flat_roof": bool(ridge - eave < 2.0),
            "footprint_sqft": round(len(group) * cell_ft ** 2),
            "hull_m": [[p[0], p[1]] for p in hull],
            "cells": len(group),
        })
    out.sort(key=lambda b: -b["footprint_sqft"])
    return out


# ---------------------------------------------------------------- the survey

def survey(slug, radius_ft=150.0, max_depth=12, write=False, project=None):
    site = yards.load_site(slug)
    lat, lon = yards.latlon(site)
    hits = coverage(lat, lon)
    if not hits:
        print(f"No 3DEP coverage at {lat}, {lon}. Tree and building heights stay "
              f"a gap; photo measurement or a clinometer is the fallback.")
        return None
    chosen = project or hits[0]["name"]
    print(f"coverage: {', '.join(h['name'] for h in hits)}")
    print(f"using:    {chosen}")

    ept = EPT(chosen)
    olon, olat = frame.to_world(site, 0.0, 0.0)
    ox, oy = ept.project_xy(olon, olat)
    u2m = ept.units_to_m()
    scale = ept.local_scale(olon, olat)
    r = radius_ft / M_TO_FT * scale / u2m
    box = (ox - r, oy - r, ox + r, oy + r)
    epsg = ept.info.get("srs", {}).get("horizontal")
    print(f"query:    {radius_ft:.0f} ft around the yard origin, EPSG:{epsg}, "
          f"survey year {ept.year or 'not stated'}")
    if abs(scale - 1.0) > 0.001:
        print(f"          projection scale {scale:.5f} at this latitude; "
              f"horizontal distances divided by it")

    pts = ept.query(box, max_depth=max_depth)
    x, y, z, c = pts["x"], pts["y"], pts["z"], pts["c"]
    if x.size == 0:
        print("  no points returned")
        return None

    c, overlap = normalize_classes(c)
    if overlap:
        print(f"  classes {overlap} are overlap-flagged duplicates; "
              f"stripped back to {[v - OVERLAP_BIT for v in overlap]}")
    counts = {int(k): int(v) for k, v in zip(*np.unique(c, return_counts=True))}
    print(f"  {x.size} points: " + ", ".join(
        f"{n} class {k}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])))

    # horizontal into true metres, vertical is already true
    x = x * u2m / scale
    y = y * u2m / scale
    z = z * u2m
    ox_m, oy_m = ox * u2m / scale, oy * u2m / scale
    pts["x"], pts["y"] = x, y

    g = c == GROUND
    if g.sum() < 20:
        print("  warning: very few ground returns, so heights above grade are "
              "shaky here")
    ground = terrain(x[g], y[g], z[g], cell_m=4.0)
    h_ft = (z - ground(x, y)) * M_TO_FT
    xf = (x - ox_m) * M_TO_FT
    yf = (y - oy_m) * M_TO_FT

    classified = np.isin(c, [HIGH_VEG, BUILDING]).sum() > 0.02 * x.size
    if classified:
        veg = np.isin(c, [HIGH_VEG, MED_VEG])
        bldg = c == BUILDING
        how = "delivery's own ASPRS classification (5 vegetation, 6 building)"
    else:
        veg, bldg, how = infer_classes(pts, h_ft, c)
        print(f"  no vegetation or building classes in this delivery; "
              f"{veg.sum()} points read as canopy and {bldg.sum()} as roof, "
              f"{how.split(';')[0]}")

    trees = find_trees(xf[veg], yf[veg], h_ft[veg])
    builds = find_buildings(xf[bldg], yf[bldg], h_ft[bldg])

    flown = flight_dates(pts["t"]) if pts["t"].size else None
    year = (flown or {}).get("year") or ept.year

    # what the cloud says at each tree already in site.json, whether or not the
    # segmenter found anything there
    bearing = math.radians(site["frame"]["true_bearing_of_plus_x"])
    conv = math.radians(site["frame"].get("grid_convergence_deg", 0.0))
    yx, yy = _to_yard(xf, yf, bearing - conv)
    audit = []
    for i, t in enumerate(siteschema.trees(site)):
        if t.get("trunk_x") is None:
            continue
        near = ((yx - t["trunk_x"]) ** 2 + (yy - t["trunk_y"]) ** 2) < 60.0 ** 2
        tallest = float(h_ft[near].max()) if near.any() else None
        reported = (t.get("height") or 0) / 12.0
        row = {"index": i, "id": t.get("id"), "returns_within_5ft": int(near.sum()),
               "tallest_return_ft": round(tallest, 1) if tallest is not None else None,
               "modelled_height_ft": round(reported, 1)}
        if tallest is not None and reported and tallest < 0.5 * reported:
            row["verdict"] = (
                f"nothing above {tallest:.0f} ft stood here when the survey flew "
                f"in {year}, against {reported:.0f} ft standing there now. The "
                f"survey predates the tree; lidar cannot measure this crown")
        elif tallest is None:
            row["verdict"] = "no returns at this spot"
        else:
            row["verdict"] = "canopy present in the survey"
        audit.append(row)

    for t in trees:
        t["yard_x"], t["yard_y"] = [
            round(v, 1) for v in _to_yard(t.pop("apex_x_m"), t.pop("apex_y_m"),
                                          bearing - conv)]
    for bd in builds:
        bd["yard_polygon"] = [[round(v, 1) for v in _to_yard(px, py,
                                                             bearing - conv)]
                              for px, py in bd.pop("hull_m")]

    result = {
        "project": chosen, "survey_year": year, "flown": flown,
        "leaf_state": leaf_state(flown, lat),
        "epsg": epsg, "projection_scale": round(scale, 6),
        "queried": {"lat": lat, "lon": lon, "radius_ft": radius_ft},
        "point_counts": counts,
        "canopy_classification": how,
        "classified_by_delivery": bool(classified),
        "trees": trees, "buildings": builds,
        "modelled_trees_audit": audit,
        "method": ("ground surface from class 2 on a 4 m grid; heights measured "
                   "against it; canopy height model at 2 ft; local maxima as tree "
                   "apexes; crown base from the vertical return profile"),
    }
    yards.save(slug, "lidar.json", result)
    print(f"\nwrote {yards.path(slug, 'lidar.json')}")
    report(result)
    if write:
        apply_to_site(slug, result)
    return result


def _to_yard(east_ft, north_ft, bearing_rad):
    b = bearing_rad
    return ((east_ft * math.sin(b) + north_ft * math.cos(b)) * 12.0,
            (east_ft * math.cos(b) - north_ft * math.sin(b)) * 12.0)


def report(result):
    trees = result["trees"]
    print(f"\n{len(trees)} tree crowns within the query radius, tallest first:")
    print(f"  {'x':>8s} {'y':>8s} {'height':>8s} {'radius':>8s} {'spread':>8s} "
          f"{'base':>7s} {'returns':>8s}")
    for t in trees[:14]:
        base = f"{t['crown_base_ft']:.0f} ft" if t["crown_base_ft"] is not None \
            else "  —"
        print(f"  {t['yard_x']:8.0f} {t['yard_y']:8.0f} "
              f"{t['height_ft']:6.0f} ft {t['crown_radius_ft']:6.0f} ft "
              f"{t['spread_ft']:6.0f} ft {base:>7s} {t['returns']:8d}")
    print(f"\n{len(result['buildings'])} buildings:")
    for b in result["buildings"][:8]:
        roof = "flat" if b["flat_roof"] else f"ridge {b['ridge_ft']:.0f} ft"
        print(f"  {b['footprint_sqft']:6d} sq ft   eave {b['eave_ft']:5.1f} ft   "
              f"{roof}")

    audit = result.get("modelled_trees_audit") or []
    if audit:
        print("\nagainst the trees already in site.json:")
        for row in audit:
            tall = (f"{row['tallest_return_ft']:.1f} ft"
                    if row["tallest_return_ft"] is not None else "nothing")
            print(f"  {str(row['id']):16s} modelled {row['modelled_height_ft']:.0f} ft, "
                  f"tallest return {tall} from {row['returns_within_5ft']} points")
            print(f"                   {row['verdict']}")

    flown = result.get("flown")
    when = (f"flown {flown['first']} to {flown['last']}" if flown
            else f"survey year {result['survey_year'] or 'unknown'}")
    print(f"\n{when}. Anything planted or felled since is not in this.")
    ls = result.get("leaf_state")
    if ls:
        print(f"{ls['note']}.")


def apply_to_site(slug, result, match_radius_in=120.0):
    """Write lidar measurements onto the trees already in site.json.

    Existing trees are matched by position rather than replaced wholesale,
    because the person on the ground knows which trunk is which and the point
    cloud does not.
    """
    site = yards.load_site(slug)
    existing = siteschema.trees(site)
    raw = site.setdefault("features", {}).setdefault("trees", [])
    year = result["survey_year"]
    changed, refused = [], []
    audit = {a["index"]: a for a in result.get("modelled_trees_audit") or []}

    for i, t in enumerate(existing):
        best, bd = None, 1e18
        for lt in result["trees"]:
            d = math.hypot(lt["yard_x"] - t["trunk_x"], lt["yard_y"] - t["trunk_y"])
            if d < bd:
                best, bd = lt, d
        row = audit.get(i, {})
        if row.get("verdict", "").startswith("the survey predates") or \
                "predates the tree" in row.get("verdict", ""):
            refused.append((i, row["verdict"]))
            siteschema.set_provenance(
                site, f"features.trees.{i}.height", "reported",
                note=f"lidar cannot help: {row['verdict']}")
            continue
        if best is None or bd > match_radius_in:
            refused.append((i, f"no lidar crown within {match_radius_in / 12:.0f} ft "
                               f"of this trunk"))
            continue
        old_r = t.get("crown_radius")
        raw[i]["height"] = round(best["height_ft"] * 12.0, 1)
        raw[i]["crown_radius"] = round(best["crown_radius_ft"] * 12.0, 1)
        if best["crown_base_ft"] is not None:
            raw[i]["crown_base_height"] = round(best["crown_base_ft"] * 12.0, 1)
        raw[i]["lidar"] = {"project": result["project"], "year": year,
                           "returns": best["returns"],
                           "match_distance_in": round(bd, 1)}
        for field, note in (
                ("height", f"99th percentile of {best['returns']} returns"),
                ("crown_radius", "90th percentile crown-point distance from the "
                                 "apex, so a lopsided crown reads as its wider side"),
                ("crown_base_height", best["crown_base_note"])):
            siteschema.set_provenance(site, f"features.trees.{i}.{field}", "lidar",
                                      date=str(year), note=note)
        changed.append((i, old_r, raw[i]["crown_radius"]))

    yards.save(slug, "site.json", site)
    print(f"\nupdated {len(changed)} trees in site.json:")
    for i, old, new in changed:
        was = f"{old:.0f}" if old else "unknown"
        print(f"  tree {i + 1}: crown radius {was}\" -> {new:.0f}\" (measured)")
    for i, why in refused:
        print(f"  tree {i + 1}: left alone — {why}")
    if changed:
        print("Re-run the sun model; the light numbers have moved.")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--coverage", nargs=2, type=float, metavar=("LAT", "LON"))
    ap.add_argument("--radius", type=float, default=150.0)
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--project", default=None)
    ap.add_argument("--write", action="store_true",
                    help="write measurements onto site.json")
    args = ap.parse_args()

    if args.coverage:
        lat, lon = args.coverage
        hits = coverage(lat, lon)
        if not hits:
            print(f"no 3DEP coverage at {lat}, {lon}")
            return
        for h in hits:
            print(f"  {h['name']:44s} {h['year'] or '?'}  "
                  f"{(h['points'] or 0):>14,} points")
        return
    if not args.slug:
        print(__doc__)
        return
    survey(args.slug, radius_ft=args.radius, max_depth=args.depth,
           write=args.write, project=args.project)


if __name__ == "__main__":
    main()
