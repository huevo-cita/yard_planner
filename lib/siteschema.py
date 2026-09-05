#!/usr/bin/env python3
"""The shape of site.json, plus provenance, validation and migration.

    python3 -m lib.siteschema <slug>            validate and report
    python3 -m lib.siteschema <slug> --migrate  rewrite in the current shape

site.json is the source of truth for a yard's geometry and for the 3D model the
shade calculation casts rays against. Everything is in **inches**, in a plan frame
aligned to whatever edge the yard was measured from.

Top-level keys
--------------
    yard          slug
    address       mailing, lat, lon, timezone, parcel identifiers, sources
    frame         the plan coordinate frame and its true bearings
    boundary      the yard outline, and the measurements it was fitted from
    zones         named regions of the yard floor
    features      trees, and anything sitting in or on the yard
    obstructions  house, fences, neighbouring buildings: what casts shade from
                  the ground up, plus `overheads` for the things that cast shade
                  from a height and let light in underneath — eaves, awnings,
                  pergolas, carports
    provenance    dotted path -> how that number came to be known
    assumptions   plain-language list of what was assumed
    verify_on_site  plain-language list of what to go and check

Provenance
----------
Numbers stay plain numbers so the file stays readable. How each one was learned is
recorded separately, keyed by dotted path:

    "provenance": {
      "boundary.width_east_west": {"source": "measured", "date": "2026-08-14"},
      "features.trees.0.crown_radius": {"source": "assumed",
                                        "note": "back-solved from reported canopy"}
    }

`source` is one of measured, lidar, photo, parcel, osm, survey, reported, derived,
assumed. `derived` means computed from another dataset rather than observed here,
such as frost dates worked out from thirty years of gridded reanalysis: better
than an assumption and worse than a measurement, and it carries the source
dataset's own error with it.

Anything `assumed`, and anything with no entry at all, is a candidate for the gap
list. That is the whole point of tracking it.
"""
import json
import math
import os
import sys

import numpy as np

from . import yards

SOURCES = ["measured", "lidar", "photo", "parcel", "osm", "survey", "reported",
           "derived", "assumed"]

SCHEMA_VERSION = 2

TREE_DEFAULTS = {
    "species": None,
    "deciduous": True,
    "leaf_on": "04-15",
    "leaf_off": "11-01",
    "transmissivity_leaf_on": 0.10,
    "transmissivity_leaf_off": 0.55,
    "crown_base_height": None,
    "crown_center_x": None,
    "crown_center_y": None,
    "crown_plan": None,
}


# ------------------------------------------------------------- dotted paths

def get_path(obj, path, default=None):
    """Read a dotted path. List indices are plain integers: features.trees.0.height"""
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        elif isinstance(cur, dict):
            if part not in cur:
                return default
            cur = cur[part]
        else:
            return default
    return cur


def set_path(obj, path, value):
    parts = str(path).split(".")
    cur = obj
    for i, part in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(cur, list):
            cur = cur[int(part)]
            continue
        if part not in cur or not isinstance(cur[part], (dict, list)):
            cur[part] = [] if nxt.isdigit() else {}
        cur = cur[part]
    if isinstance(cur, list):
        cur[int(parts[-1])] = value
    else:
        cur[parts[-1]] = value


# ---------------------------------------------------------------- provenance

def provenance_of(site, path):
    return site.get("provenance", {}).get(path)


def set_provenance(site, path, source, date=None, note=None, uncertainty=None,
                   readings=None):
    if source not in SOURCES:
        raise ValueError(f"unknown provenance source {source!r}; expected one of "
                         + ", ".join(SOURCES))
    entry = {"source": source}
    if date:
        entry["date"] = date
    if note:
        entry["note"] = note
    if uncertainty is not None:
        entry["uncertainty"] = uncertainty
    if readings:
        entry["readings"] = normalize_readings(readings)
    site.setdefault("provenance", {})[path] = entry
    return entry


# ---------------------------------------------------- read once, or read twice
#
# `source` says what KIND of act produced a number. It does not say how many
# times that act happened, and those are different facts with different weight:
# a crown radius paced once and a crown radius paced twice by different means on
# different days are both `measured`, and only the second one has survived
# anything. On one yard the four figures that had reproduced were the strongest
# evidence in the record and lived entirely in the doubt board and the change
# log, where no model and no fingerprint could see them.
#
# So a provenance entry may carry `readings`: one dict per time somebody went and
# looked, each with a `date`, the `value` they got, and `how` they got it. The
# entry's own `date` and the value at the path stay authoritative — `readings` is
# the history behind them, and `validate` checks the two still agree, which is
# what stops this becoming decoration.

READING_KEYS = ("date", "value", "how", "caveat")


def normalize_readings(readings):
    out = []
    for r in readings:
        if not isinstance(r, dict) or "date" not in r:
            raise ValueError(f"a reading needs at least a date: {r!r}")
        bad = set(r) - set(READING_KEYS)
        if bad:
            raise ValueError(f"unknown reading field(s) {sorted(bad)}; expected "
                             + ", ".join(READING_KEYS))
        out.append({k: r[k] for k in READING_KEYS if k in r})
    return sorted(out, key=lambda r: r["date"])


def confirmations(entry, tol=1e-6):
    """How many times this value has been read, and whether it reproduced.

    `reproduced` is deliberately strict: every reading carrying a value has to
    agree with the latest one. Two readings that DISAGREE are still two
    readings, and that is a correction rather than a confirmation - which is the
    more interesting of the two, so it must not be reported as agreement.
    """
    reads = entry.get("readings") or []
    if not reads:
        return None
    vals = [r["value"] for r in reads if r.get("value") is not None]
    same = all(abs(v - vals[-1]) <= tol for v in vals) if len(vals) > 1 else None
    return {"readings": len(reads),
            "first": reads[0]["date"], "last": reads[-1]["date"],
            "reproduced": same,
            "caveats": [r["caveat"] for r in reads if r.get("caveat")]}


def confirmed_paths(site):
    """Paths read more than once, and what came of it. Newest re-read first."""
    out = []
    for p, e in (site.get("provenance") or {}).items():
        c = confirmations(e)
        if c and c["readings"] > 1:
            out.append((p, c))
    return sorted(out, key=lambda r: (r[1]["last"], r[0]), reverse=True)


def assumed_paths(site):
    """Every path explicitly recorded as assumed, with its note."""
    out = []
    for p, e in sorted(site.get("provenance", {}).items()):
        if e.get("source") == "assumed":
            out.append((p, e.get("note") or "", e.get("uncertainty")))
    return out


# Sources that count as an observation of the world rather than a guess about
# it. `parcel` belongs here: a recorded plat from a county appraisal district is
# a legal survey document, and is usually the hardest number in a site record.
# `osm` stays out because it is volunteer-traced from imagery, `derived` because
# it is only ever as good as whatever it was computed from, and `reported`
# because someone remembering their fence height is not a measurement.
HARD_SOURCES = ("measured", "lidar", "photo", "survey", "parcel")


def measured_fraction(site):
    """How much of what we know was actually measured rather than guessed."""
    prov = site.get("provenance", {})
    if not prov:
        return 0.0
    hard = sum(1 for e in prov.values()
               if e.get("source") in HARD_SOURCES)
    return hard / len(prov)


# ------------------------------------------------------------------- trees

def trees(site):
    """Normalized tree list, defaults filled in, crown centre resolved.

    Reading always goes through here so callers never have to care whether a
    file predates the trees[] shape.
    """
    raw = get_path(site, "features.trees") or []
    out = []
    for i, t in enumerate(raw):
        tree = dict(TREE_DEFAULTS)
        tree.update(t)
        tree.setdefault("id", f"tree-{i + 1}")
        if tree.get("crown_center_x") is None:
            tree["crown_center_x"] = tree.get("trunk_x")
        if tree.get("crown_center_y") is None:
            tree["crown_center_y"] = tree.get("trunk_y")
        if tree.get("crown_base_height") is None and tree.get("height"):
            # a crown with no measured base is modelled from half height, which
            # is the usual proportion for an open-grown broadleaf
            tree["crown_base_height"] = tree["height"] * 0.5
        out.append(tree)
    return out


def tree_transmissivity(tree, doy):
    """Fraction of the beam that gets through this crown on this day."""
    if not tree.get("deciduous", True):
        return tree.get("transmissivity_leaf_on", 0.10), True
    on = _md_to_doy(tree.get("leaf_on", "04-15"))
    off = _md_to_doy(tree.get("leaf_off", "11-01"))
    leaf_on = on <= doy <= off
    return (tree["transmissivity_leaf_on"] if leaf_on
            else tree["transmissivity_leaf_off"]), leaf_on


_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def _md_to_doy(md):
    try:
        m, d = str(md).split("-")
        return _CUM[int(m) - 1] + int(d)
    except Exception:
        return 105


# --------------------------------------------------------------- crown plan

TWO_PI = 2.0 * math.pi

# A wedge is cut out of the circle by two half-planes through the trunk, and a
# pair of half-planes cannot describe an arc wider than a semicircle. Anything
# wider is split into equal parts before it reaches the ray test.
MAX_WEDGE_DEG = 180.0


def crown_wedges(tree, x_axis_bearing, radius=None):
    """A crown's plan shape as angular wedges, or None if it is a circle.

    `crown_radius` is a scalar, so a crown is a circle in plan, and most are
    close enough. cloverleaf-austin's t11 is not: taped from the trunk base it
    reads 17 ft along the property line, 14 ft toward the house's south-east
    corner, 14-17 ft for the bulk, and 22 ft on one bearing where a single limb
    runs out perpendicular to the line. No ellipse fits that — an ellipse is
    convex and reaches furthest on its own major axis, and this crown reaches
    furthest on a bearing where the bulk is at its narrowest.

    So a tree may carry a `crown_plan`, which says where the crown departs from
    `crown_radius` and nothing else:

        "crown_plan": {
          "note": "why this crown is not a circle",
          "arcs": [{"id": "west-limb", "true_bearing": 297.8, "width_deg": 12.0,
                    "radius": 264.0, "note": "the one limb, 22 ft"}]}

    Bearings are TRUE degrees, because that is what somebody standing at the
    trunk with a tape and a compass can actually produce, and because a true
    bearing survives the yard frame being re-derived. They are converted here
    against `frame.true_bearing_of_plus_x`.

    Everything outside the declared arcs keeps `crown_radius`, which is what
    makes the whole thing opt-in: a tree with no `crown_plan` returns None and
    is modelled by exactly the code that has always modelled it. It also keeps
    the scalar honest — it goes on meaning the bulk drip line, the number a
    person would give if asked for one radius, rather than becoming an average
    of the profile that nothing can be checked against.

    Returns (lo, hi, radius) in YARD-FRAME radians, measured from +x toward +y,
    covering the full circle exactly once with no overlaps, each span no wider
    than `MAX_WEDGE_DEG`. Overlapping arcs raise, because two radii claiming
    the same bearing is a record that does not describe a shape.
    """
    arcs = (tree.get("crown_plan") or {}).get("arcs") or []
    if not arcs:
        return None
    tid = tree.get("id", "?")
    bulk = tree.get("crown_radius") if radius is None else radius
    if bulk is None:
        raise ValueError(f"{tid} carries a crown_plan but no crown_radius; the "
                         f"arcs say where the crown leaves the bulk, so there "
                         f"has to be a bulk for them to leave")
    bulk = float(bulk)

    spans = []
    for i, arc in enumerate(arcs):
        where = f"{tid} crown_plan.arcs.{i}"
        if arc.get("true_bearing") is None:
            raise ValueError(f"{where} has no true_bearing")
        width = float(arc.get("width_deg") or 0.0)
        if not 0.0 < width < 360.0:
            raise ValueError(
                f"{where} has width_deg {width:g}. An arc has to span some "
                f"ground and less than the whole circle — a crown that is one "
                f"radius all round is a circle, and the scalar already says so")
        r = float(arc["radius"]) if arc.get("radius") is not None else bulk
        if r <= 0.0:
            raise ValueError(f"{where} has radius {r:g}")
        theta = math.radians(float(arc["true_bearing"]) - x_axis_bearing)
        w = math.radians(width)
        spans.append(((theta - w / 2.0) % TWO_PI, w, r, i))
    spans.sort()

    n = len(spans)
    for i, (lo, w, _, idx) in enumerate(spans):
        nxt = spans[(i + 1) % n][0] + (TWO_PI if i == n - 1 else 0.0)
        if lo + w > nxt + 1e-9:
            raise ValueError(
                f"{tid} crown_plan arcs {idx} and {spans[(i + 1) % n][3]} "
                f"overlap. Two radii claiming the same bearing do not describe "
                f"a shape; widen one, narrow the other, or merge them")

    out = []
    for i, (lo, w, r, _) in enumerate(spans):
        out.append((lo, lo + w, r))
        gap_hi = spans[(i + 1) % n][0] + (TWO_PI if i == n - 1 else 0.0)
        if gap_hi - (lo + w) > 1e-9:
            out.append((lo + w, gap_hi, bulk))
    return [w for lo, hi, r in out for w in _split_wedge(lo, hi, r)]


def _split_wedge(lo, hi, r, limit=math.radians(MAX_WEDGE_DEG)):
    parts = max(int(math.ceil((hi - lo) / limit - 1e-12)), 1)
    step = (hi - lo) / parts
    return [(lo + k * step, lo + (k + 1) * step, r) for k in range(parts)]


def crown_reach(tree):
    """The furthest the crown reaches in plan, arcs included.

    The bounding circle, so anything that wants one number off a crown — a
    drawing, a distance check, a bounding test — gets a figure that is too
    generous rather than one that quietly misses the limb.
    """
    r = tree.get("crown_radius")
    arcs = (tree.get("crown_plan") or {}).get("arcs") or []
    radii = [float(a["radius"]) for a in arcs if a.get("radius") is not None]
    if r is not None:
        radii.append(float(r))
    return max(radii) if radii else None


# ------------------------------------------------------------------ migration

def migrate(site):
    """Bring an older site.json up to the current shape, in place.

    The one real change: a single named species block holding a list of trunk
    positions becomes one entry per tree under features.trees, so a yard can hold
    several species and each tree can carry its own measured crown.
    """
    changed = []
    feats = site.setdefault("features", {})

    if "trees" not in feats:
        merged = []
        for key in list(feats):
            blob = feats[key]
            if not isinstance(blob, dict):
                continue
            ys = blob.get("trunks_y")
            if ys is None and blob.get("trunk_y") is None:
                continue
            ys = ys if ys is not None else [blob.get("trunk_y")]
            height = blob.get("height_modelled") or blob.get("height")
            base = (blob.get("crown_base_height")
                    or blob.get("crown_base_height_assumed"))
            for i, ty in enumerate(ys):
                merged.append({
                    "id": f"{key.rstrip('s')}-{i + 1}",
                    "label": blob.get("label"),
                    "species": blob.get("species") or blob.get("label"),
                    "trunk_x": blob.get("trunk_x"),
                    "trunk_y": ty,
                    "height": height,
                    "height_range_ft": blob.get("height_range_ft"),
                    "crown_radius": blob.get("crown_radius"),
                    "crown_base_height": base,
                    "deciduous": blob.get("deciduous", True),
                    "leaf_on": blob.get("leaf_on", TREE_DEFAULTS["leaf_on"]),
                    "leaf_off": blob.get("leaf_off", TREE_DEFAULTS["leaf_off"]),
                    "transmissivity_leaf_on": blob.get(
                        "transmissivity_leaf_on",
                        TREE_DEFAULTS["transmissivity_leaf_on"]),
                    "transmissivity_leaf_off": blob.get(
                        "transmissivity_leaf_off",
                        TREE_DEFAULTS["transmissivity_leaf_off"]),
                    "notes": blob.get("canopy_extent_note"),
                    "verify": blob.get("verify"),
                })
            feats.pop(key)
            changed.append(f"features.{key} -> features.trees ({len(ys)} trees)")
        if merged:
            feats["trees"] = merged
        else:
            feats.setdefault("trees", [])

    if "provenance" not in site:
        site["provenance"] = {}
        changed.append("added provenance map")

    # anything the old file called out as an assumption becomes a real record
    for text in site.get("assumptions", []):
        key = f"assumptions.{len(site['provenance'])}"
        if not any(e.get("note") == text for e in site["provenance"].values()):
            site["provenance"][key] = {"source": "assumed", "note": text}

    if site.get("schema_version") != SCHEMA_VERSION:
        site["schema_version"] = SCHEMA_VERSION
        changed.append(f"schema_version -> {SCHEMA_VERSION}")

    return changed


# ----------------------------------------------------------------- validation

def validate(site):
    """Problems that would stop the shade model, plus softer warnings."""
    errs, warns = [], []

    a = site.get("address", {})
    if a.get("lat") is None or a.get("lon") is None:
        errs.append("address.lat/lon missing — nothing solar can be computed")
    if not a.get("timezone"):
        warns.append("address.timezone missing — clock times will be guessed from "
                     "longitude, which is an hour wrong in places like Austin")

    b = site.get("boundary", {})
    for k in ("width_east_west", "south_boundary_offset"):
        if b.get(k) is None:
            errs.append(f"boundary.{k} missing")
    if b.get("north_fence_slope") is None:
        warns.append("boundary.north_fence_slope missing, assuming a square yard")

    f = site.get("frame", {})
    xb = f.get("true_bearing_of_plus_x")
    if f.get("true_bearing_of_plus_x") is None:
        errs.append("frame.true_bearing_of_plus_x missing — the yard has no "
                    "orientation, so sun angles cannot be resolved")

    o = site.get("obstructions", {})
    if not o:
        warns.append("no obstructions recorded; the sun model will report open sky")

    for i, t in enumerate(trees(site)):
        for k in ("trunk_x", "trunk_y", "height"):
            if t.get(k) is None:
                errs.append(f"features.trees.{i}.{k} missing")
        if t.get("crown_radius") is None:
            warns.append(f"features.trees.{i}.crown_radius missing — the single "
                         "most consequential unknown in most yards")
        try:
            wedges = crown_wedges(t, xb) if xb is not None else None
        except ValueError as exc:
            errs.append(f"features.trees.{i}.crown_plan: {exc}")
            wedges = None
        if wedges is not None and len({round(r, 9) for _, _, r in wedges}) == 1:
            warns.append(
                f"features.trees.{i}.crown_plan describes one radius all "
                f"round, which is the circle crown_radius already draws. "
                f"Either the arcs are wrong or the plan is not needed.")

    for p, e in site.get("provenance", {}).items():
        if e.get("source") not in SOURCES:
            warns.append(f"provenance {p} has an unrecognised source")
        # A reading history that has drifted from the value it is history for is
        # worse than no history: it reads as corroboration for a number nobody
        # took. So the two are checked against each other every time.
        try:
            reads = normalize_readings(e.get("readings") or [])
        except ValueError as exc:
            errs.append(f"provenance {p}.readings: {exc}")
            continue
        if not reads:
            continue
        latest = reads[-1]
        held = get_path(site, p)
        if latest.get("value") is not None and isinstance(held, (int, float)):
            if abs(latest["value"] - held) > 1e-6:
                errs.append(
                    f"provenance {p} says its latest reading on {latest['date']} "
                    f"was {latest['value']}, and the value there is {held}. One of "
                    f"them is stale, and a reading history that disagrees with "
                    f"its own value is corroboration for a number nobody took.")
        if e.get("date") and e["date"] < latest["date"]:
            warns.append(
                f"provenance {p} is dated {e['date']} but carries a reading from "
                f"{latest['date']}. The entry date should be the last time "
                f"somebody looked.")

    for i, fid, h, ratio in roofs_as_walls(site):
        height = f"{h:.0f} in" if h else "its stated height"
        warns.append(
            f"obstructions.fences.{i} ({fid}) is a CLOSED ring at {height} that "
            f"contains every wall corner and encloses {ratio:.0%} of the wall "
            f"footprint's area. That is a ROOF outline, not a wall. Every fence "
            f"polyline is modelled as a vertical wall from the ground to its "
            f"height, so this stands the eave overhang on the ground and models "
            f"every bed under it as indoors — losing the low winter sun that in "
            f"reality passes underneath a ledge nine feet up. Carry the WALL "
            f"footprint in the fence list, and move the roof outline to "
            f"obstructions.overheads as a horizontal plane: "
            f'{{"polygon": <roof>, "hole": <walls>, "height": <eave>, '
            f'"transmissivity": 0}}.')

    for label, key, where, frac in enclosed_zones(site):
        msg = (f"zone {label!r} (zones.{key}) has {frac:.0%} of its footprint "
               f"inside {where}, which is opaque from grade up. That ground is "
               f"indoors: it cannot be planted, it reads as permanent shade, "
               f"and it pulls the zone's mean down for a reason that has "
               f"nothing to do with light. Correct the zone rectangle or the "
               f"obstruction — a bed recorded square against a wall that runs "
               f"at an angle always overlaps a little.")
        if frac >= 0.5:
            errs.append(msg + " At this fraction the zone is mostly indoors "
                              "and its average means nothing.")
        else:
            warns.append(msg)

    return errs, warns


def zone_names(site):
    return list((site.get("zones") or {}).keys())


# ------------------------------------------------------------------- geometry

def in_polygon(poly, x, y):
    """Even-odd point-in-polygon, vectorised over x and y.

    A repeated closing vertex is harmless: a zero-length edge straddles nothing.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    inside = np.zeros(np.broadcast(x, y).shape, dtype=bool)
    x1, y1 = poly[-1]
    for x2, y2 in poly:
        with np.errstate(divide="ignore", invalid="ignore"):
            cut = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= ((y1 > y) != (y2 > y)) & (x < cut)
        x1, y1 = x2, y2
    return inside


def polygon_area(poly):
    """Signed area by the shoelace formula. A closing vertex is tolerated."""
    p = poly[:-1] if list(poly[0]) == list(poly[-1]) else poly
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
               for i in range(len(p))) / 2.0


def ground_rings(site):
    """Everything opaque that stands on the ground, as (label, polygon).

    A fence polyline whose endpoints coincide is not a fence: it encloses
    something, and the shade model will run an opaque wall right round it from
    grade to its height. The house footprint comes first so that a record which
    carries the same polygon twice reports it under its own name.
    """
    out = []
    obs = site.get("obstructions") or {}
    walls = (obs.get("house_walls") or {}).get("polygon")
    if walls:
        out.append(("obstructions.house_walls", walls))
    for i, f in enumerate(obs.get("fences") or []):
        pts = f.get("points") or []
        if len(pts) > 3 and list(pts[0]) == list(pts[-1]) and f.get("opaque", True):
            out.append((f"obstructions.fences.{i} ({f.get('id', 'fence')})", pts))
    for i, b in enumerate(obs.get("context_buildings") or []):
        if b.get("polygon"):
            name = b.get("name") or b.get("id") or "building"
            out.append((f"obstructions.context_buildings.{i} ({name})",
                        b["polygon"]))
    return out


def roofs_as_walls(site):
    """Closed fence rings that swallow the wall footprint: a roof entered as a wall.

    An eave is a horizontal shelf nine feet up. Entered in the fence list it
    becomes a vertical wall standing on the ground, and every bed tucked under
    the overhang is then modelled as being inside the building. The signature is
    exact and needs no threshold on height: a ring that contains every wall
    corner and encloses materially more area than the walls do is the wall
    outline offset outward by its own eaves.
    """
    obs = site.get("obstructions") or {}
    walls = (obs.get("house_walls") or {}).get("polygon")
    if not walls:
        return []
    wa = abs(polygon_area(walls))
    if wa <= 0:
        return []
    out = []
    for i, f in enumerate(obs.get("fences") or []):
        pts = f.get("points") or []
        if len(pts) < 4 or list(pts[0]) != list(pts[-1]) \
                or not f.get("opaque", True):
            continue
        ra = abs(polygon_area(pts))
        if ra <= wa * 1.05:
            continue
        if in_polygon(np.asarray(pts, float), [p[0] for p in walls],
                      [p[1] for p in walls]).all():
            out.append((i, f.get("id", "fence"), f.get("height"), ra / wa))
    return out


def enclosed_zones(site, sample=11):
    """Zones whose floor falls inside something opaque standing on the ground.

    A bed modelled as indoors is always a bug, whatever put it there — a roof
    outline entered as a wall, a bed rectangle recorded square against a wall
    that runs at an angle, a neighbouring footprint traced over the line. It
    reads as near-permanent shade, which is true and useless, and it drags the
    zone's mean down without ever looking like an error.

    Returns (label, key, obstruction label, fraction) worst-first, naming only
    the worst offender per zone so one buried bed does not report five times.
    """
    rings = ground_rings(site)
    if not rings:
        return []
    f = (np.arange(sample) + 0.5) / sample
    out = []
    for key, spec in (site.get("zones") or {}).items():
        xr, yr = spec.get("x"), spec.get("y")
        if not xr or not yr:
            continue
        gx, gy = np.meshgrid(xr[0] + f * (xr[1] - xr[0]),
                             yr[0] + f * (yr[1] - yr[0]))
        worst, where = 0.0, None
        for label, poly in rings:
            frac = float(in_polygon(np.asarray(poly, float), gx, gy).mean())
            if frac > worst:
                worst, where = frac, label
        if worst > 0.02:
            out.append((spec.get("label_short") or spec.get("label") or key,
                        key, where, worst))
    return sorted(out, key=lambda r: -r[3])


def load(slug):
    return yards.load_site(slug)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    slug = sys.argv[1]
    site = yards.load_site(slug)

    if "--assumed" in sys.argv:
        # Two skills document this flag and it was never implemented, so the
        # command they tell you to run for a site walk printed the module
        # docstring. The summary below already lists the assumed paths, but
        # truncates each note to 70 characters, and the note is the whole
        # point: it is what says WHY the value was guessed and therefore what
        # would falsify it.
        ass = assumed_paths(site)
        reported = sum(1 for e in (site.get("provenance") or {}).values()
                       if e.get("source") == "reported")
        print(f"{slug}: {len(ass)} assumed values, "
              f"{measured_fraction(site) * 100:.0f}% of the record measured")
        for p, note, unc in ass:
            print(f"\n  {p}")
            if unc:
                print(f"    uncertainty: {unc}")
            print(f"    {note or '(no note, which is the worst kind)'}")
        if reported:
            # Not assumed, and not measured either. A site walk wants these too,
            # and it would be misleading to let this flag imply the rest of the
            # record is solid.
            print(f"\n  and {reported} more recorded as `reported` — somebody's "
                  f"statement rather than a guess, but still not a measurement. "
                  f"`python3 -m lib.gaps {slug}` ranks both kinds by what they "
                  f"cost.")
        return

    if "--migrate" in sys.argv:
        changed = migrate(site)
        yards.save(slug, "site.json", site)
        print(f"migrated {slug}:")
        for c in changed or ["nothing to change"]:
            print("  " + c)

    errs, warns = validate(site)
    print(f"\n{slug}: {len(trees(site))} trees, "
          f"{len(site.get('zones') or {})} zones, "
          f"{len(site.get('provenance') or {})} provenance entries, "
          f"{measured_fraction(site) * 100:.0f}% measured")
    twice = confirmed_paths(site)
    if twice:
        agreed = [p for p, c in twice if c["reproduced"]]
        print(f"  {len(twice)} value{'s' if len(twice) > 1 else ''} read more "
              f"than once, {len(agreed)} reproducing")
        for p, c in twice:
            verdict = ("reproduced" if c["reproduced"] else "CORRECTED"
                       if c["reproduced"] is False else "re-read")
            print(f"    {p}  {c['readings']}x, {c['first']} to {c['last']}, "
                  f"{verdict}")
            for cav in c["caveats"]:
                print(f"      caveat: {cav}")
    for e in errs:
        print("  ERROR   " + e)
    for w in warns:
        print("  warning " + w)
    if not errs and not warns:
        print("  clean")

    ass = assumed_paths(site)
    if ass:
        print(f"\n  {len(ass)} assumed values:")
        for p, note, _ in ass:
            print(f"    {p:44s} {note[:70]}")


if __name__ == "__main__":
    main()
