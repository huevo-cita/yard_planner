#!/usr/bin/env python3
"""A placed planting you can change one plant at a time.

    python3 -m lib.scheme <slug> --init     write the suggested map
    python3 -m lib.scheme <slug> --check    report overlaps and plants that do not fit
    python3 -m lib.scheme <slug> --review   check the map against practice/
    python3 -m lib.scheme <slug> --serve    open the map on a phone

The map is the choosing. It does not write design.json, and it does not run
the design or the bed drawings. Those stay gated until the choice cards close.

Ornamental beds only. Each circle is one plant. Tap it, then tap a replacement.
The replacement has to fit the light, the soil, the depth, the gap, and any
size limit in the vision.

The yard facts come from `design.json` and `scheme-brief.json`. The design
and drawing rules come from `practice/rules.json`. This file holds neither.
"""

import argparse
import datetime
import json
import math
import sys

from . import niches, practice, yards

FILE = "scheme.json"
BRIEF = "scheme-brief.json"
# Circles may kiss. A few hundredths of a foot is the float, not a real overlap.
TOUCH = 0.03
SCALE = 86  # px per foot, the most a bed is drawn at
SHEET_PX = 1180  # a bed is scaled down to fit this width
# The search grid for a new drift, in feet.
STEP = 0.25
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Masses of one species that one bed may hold.
MASSES_PER_SPECIES = 2


# The fill for each flower color word in the catalog, from the Okabe and Ito
# set that practice/drawing.md names. Blue and purple share sky blue, and pink
# takes reddish purple, because the set has no ninth color. The code label and
# the marks carry the meaning, so color is never the only cue.
FLOWER_HEX = {
    "yellow": "#F0E442",
    "white": "#FFFFFF",
    "red": "#D55E00",
    "purple": "#56B4E9",
    "blue": "#56B4E9",
    "pink": "#CC79A7",
    "orange": "#E69F00",
    "green": "#009E73",
}
# The fruit mark. The same set as the flowers, plus the dark blue and the
# black of the Okabe and Ito set, because fruit is often blue or black.
FRUIT_HEX = dict(FLOWER_HEX, blue="#0072B2", black="#000000")
del FRUIT_HEX["green"]
LEAF_FILL = "#b9cf9f"
EVERGREEN_FILL = "#6f8f5a"
# A dormant plant shows straw, not its flower color, so a dormant plant
# with white flowers does not look the same as one in flower.
DORMANT_FILL = "#d9c9a3"
# White flowers on the soil color read as an empty circle. In flower, a
# white-flowered plant shows white spots on its leaf color.
WHITE_BLOOM_TILE = (
    f"<rect width='12' height='12' fill='{LEAF_FILL}'></rect>"
    "<circle cx='3' cy='3' r='2.4' fill='#fff' stroke='#8a8a80' stroke-width='.5'></circle>"
    "<circle cx='9' cy='9' r='2.4' fill='#fff' stroke='#8a8a80' stroke-width='.5'></circle>")


FEATURE_FILL = "#999999"


def color_for(flower=None, evergreen=False, feature=False):
    """The fill for a plant. With no flower color on record, the leaf shows."""
    if feature:
        return FEATURE_FILL
    if flower and flower in FLOWER_HEX:
        return FLOWER_HEX[flower]
    return EVERGREEN_FILL if evergreen else LEAF_FILL


# ------------------------------------------------------------------ geometry

def _radius(plant):
    return float(plant["spread_ft"]) / 2.0


def _dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def overlaps(a, b):
    """True when two solid circles cross.

    A planting plan draws circles that touch. They do not stack.
    """
    return _dist(a, b) + TOUCH < _radius(a) + _radius(b)


def _tall_ft():
    return float(practice.rule("design.height_bands_ft")[-1])


def _is_canopy(plant):
    """A structure plant in the top height band, such as a climbing rose.

    Tall means the top band in practice, so a grass at 3 ft is not a canopy.
    """
    height = plant.get("height_ft")
    return height is not None and float(height) >= _tall_ft() and _is_structure(plant)


def _under_canopy(a, b):
    """True when one plant grows under the canopy of a tall structure plant.

    A climbing rose over a low groundcover is layering, not crowding.
    """
    for top, low in ((a, b), (b, a)):
        low_h = low.get("height_ft")
        if _is_canopy(top) and low_h is not None and float(low_h) < _tall_ft():
            return True
    return False


def _crowds(a, b):
    return overlaps(a, b) and not _under_canopy(a, b)


def in_bed(bed, plant):
    """True when the circle sits in plantable soil.

    A plant that is already in the ground may lean onto the wall or past the
    measured end, because the source drawing shows it there. A new plant may
    not, and it may not enter a keep-out strip.
    """
    r = _radius(plant)
    length = float(bed["length_ft"])
    depth = float(bed["depth_ft"])
    stay = plant.get("locked") or plant.get("kept")
    end_slop = 0.5 if stay else 0.02
    back_slop = float(bed.get("above_ft") or 0) + (0.15 if stay else 0.02)
    if plant["x"] - r < -end_slop or plant["x"] + r > length + end_slop:
        return False
    if plant["y"] - r < -0.02 or plant["y"] + r > depth + back_slop:
        return False
    if not stay:
        for band in bed.get("keep_out") or []:
            x_from = float(band.get("x_from") or 0)
            x_to = float(band["x_to"]) if band.get("x_to") is not None else length
            if plant["x"] + r <= x_from or plant["x"] - r >= x_to:
                continue
            if plant["y"] - r < float(band["y_below"]) - 0.001:
                return False
    return True


def _touch(plants):
    """Shrink solid circles until they touch. The centers stay."""
    for _ in range(12):
        changed = False
        for i, left in enumerate(plants):
            for right in plants[i + 1:]:
                if not _crowds(left, right):
                    continue
                dist = _dist(left, right)
                if dist < 0.2:
                    continue
                need = _radius(left) + _radius(right)
                scale = max(0.2, (dist - TOUCH) / need)
                left["spread_ft"] = round(max(0.4, left["spread_ft"] * scale), 3)
                right["spread_ft"] = round(max(0.4, right["spread_ft"] * scale), 3)
                changed = True
        if not changed:
            break


def _size_key(plant):
    """The group that shares one circle size, or None for a plant that keeps its own.

    A plant in the ground groups only with plants in the ground, so a new
    plant never sets its size. A canopy keeps the size that the source shows.
    """
    if plant.get("feature") or _is_canopy(plant):
        return None
    return (plant["name"], plant.get("niche"), bool(plant.get("locked")))


def _even_sizes(plants):
    """One plant in one niche gets one circle: the smallest in the group.

    The smallest size keeps every circle clear of its neighbours.
    """
    least = {}
    for plant in plants:
        key = _size_key(plant)
        if key:
            least[key] = min(least.get(key, plant["spread_ft"]), plant["spread_ft"])
    for plant in plants:
        key = _size_key(plant)
        if key:
            plant["spread_ft"] = least[key]


def shrunk_canopy(plant):
    """True when a canopy plant is drawn smaller than the source drawing shows it."""
    source = plant.get("drawn_ft")
    if not source or not _is_canopy(plant):
        return False
    start = float(source) if plant.get("locked") else min(float(source), spacing_for(plant))
    return plant["spread_ft"] < start - 0.001


def uneven(plants):
    """Groups of one plant in one niche that are drawn at different sizes."""
    sizes = {}
    for plant in plants:
        key = _size_key(plant)
        if key:
            sizes.setdefault(key, []).append(plant)
    return [group for group in sizes.values()
            if max(p["spread_ft"] for p in group) - min(p["spread_ft"] for p in group) > 0.001]


# ------------------------------------------------------------------ the yard

class Yard:
    """The files that every check on this map reads, loaded once."""

    def __init__(self, slug):
        from . import fits
        self.slug = slug
        self.site = yards.load_site(slug)
        self.sun = yards.load(slug, "sun-hours.json") or {}
        self.cond = yards.load_conditions(slug)
        self.vis = yards.load(slug, "vision.json") or {}
        self.niches = {n["id"]: n for n in (niches.load(slug) or {}).get("niches") or []}
        try:
            self.region = fits.region_for(slug, self.site)
        except SystemExit:
            self.region = None
        self._verdicts = {}

    def rejection(self, niche_id, cand):
        key = (niche_id, cand.get("name"))
        if key not in self._verdicts:
            niche = self.niches.get(niche_id)
            if niche is None:
                self._verdicts[key] = "this spot has no plant list"
            else:
                self._verdicts[key] = niches._rejects(
                    dict(cand), niche, _swap_slot(), self.site, self.sun,
                    self.cond, self.vis)
        return self._verdicts[key]

    def regional(self, key):
        return practice.regional(key, self.region)


def _swap_slot():
    """A slot with no row budget.

    The row budget asks whether a whole row of this plant would fit. A swap
    is one circle. Light, depth, pH, drainage and size limits still apply.
    The gap check does the rest.
    """
    return {"id": "swap", "count": [1, 1]}


def rejection(slug, niche, cand, site=None, sun=None, cond=None, vis=None):
    """Why this plant cannot go in this niche, or None when it can."""
    site = yards.load_site(slug) if site is None else site
    sun = yards.load(slug, "sun-hours.json") or {} if sun is None else sun
    cond = yards.load_conditions(slug) if cond is None else cond
    vis = yards.load(slug, "vision.json") or {} if vis is None else vis
    return niches._rejects(dict(cand), niche, _swap_slot(), site, sun, cond, vis)


def _candidates(niche):
    """One record per name. The same plant on two rows is still one plant."""
    out = {}
    for slot in niches._slots(niche):
        for cand in slot.get("candidates") or []:
            out.setdefault(cand["name"], cand)
    return out


# ------------------------------------------------------------------ traits

def _seasons():
    from . import fits
    out = {}
    for catalog in fits.catalogs().values():
        for key, months in (catalog.get("seasons") or {}).items():
            if isinstance(months, list):
                out.setdefault(key, months)
    return out


def traits(name, botanical, record=None):
    """What the map needs to know about a plant through the year.

    The design record wins where it has a value. The catalog fills the rest.
    A value that neither holds stays None, and the page says so.
    """
    from . import design as design_mod
    rec = record or {}
    cat = design_mod._match_record({"name": name, "botanical": botanical}) or {}

    def get(key):
        if rec.get(key) is not None:
            return rec.get(key)
        return cat.get(key)

    evergreen = bool(get("evergreen"))
    bloom = [m for m in MONTHS if m in (get("bloom") or [])]
    leaf = rec.get("months") or cat.get("months")
    if not leaf:
        season = "evergreen" if evergreen else (cat.get("season") or "warm")
        leaf = _seasons().get(season) or MONTHS
    if evergreen:
        leaf = list(MONTHS)
    # Fruit shows only with a color on record, because the mark is that color.
    fruit_color = get("fruit_color") if get("fruit_color") in FRUIT_HEX else None
    fruit = [m for m in MONTHS if m in (get("fruit_months") or [])] if fruit_color else []
    # A plant that carries fruit or flowers is not dormant.
    leaf = [m for m in MONTHS if m in leaf or m in bloom or m in fruit]
    host = get("host")
    return {
        "bloom": bloom,
        "leaf": leaf,
        "fruit": fruit,
        "fruit_color": fruit_color,
        "fruit_what": get("fruit_what") if fruit else None,
        # Who eats the fruit, such as ["birds"]. This counts even when the
        # fruit is not colorful, because it is food.
        "fruit_for": list(get("fruit_for") or []),
        "seed_for": list(get("seed_for") or []),
        "evergreen": evergreen,
        "nectar": get("nectar"),
        "host": list(host) if isinstance(host, list) else ([host] if host else []),
        "flower": get("flower_color"),
        "height_ft": get("mature_height_ft"),
        "mature_spread_ft": get("mature_spread_ft"),
        "habit": get("habit") or "",
        "native": get("native"),
        "role": rec.get("role") or "",
        "layer": rec.get("layer") or "",
    }


def _plant(bed_id, niche_id, name, botanical, spread, x, y, locked=False,
           kept=False, record=None, feature=False):
    t = traits(name, botanical, record)
    mature = t["mature_spread_ft"] or spread
    return {
        "id": f"{bed_id}-{x:.2f}-{y:.2f}",
        "name": name,
        "botanical": botanical or "",
        "x": round(float(x), 3),
        "y": round(float(y), 3),
        "spread_ft": round(float(spread), 3),
        "mature_spread_ft": round(float(mature), 3),
        "locked": bool(locked),
        "kept": bool(kept),
        "feature": bool(feature),
        "niche": niche_id,
        "color": color_for(t["flower"], t.get("evergreen"), feature),
        **{k: v for k, v in t.items() if k != "mature_spread_ft"},
    }


def spacing_for(plant):
    """Planting distance on center, from practice/rules.json.

    Herbaceous plants go in closer than their mature spread and are edited
    from the third year. Shrubs and trees go in at their mature spread.
    """
    dense = practice.rule("design.plant_dense_then_thin")
    mature = float(plant.get("mature_spread_ft") or plant.get("spread_ft") or 1.0)
    habit = plant.get("habit") or ""
    if habit in ("shrub", "tree") or not dense.get("applies"):
        return round(mature, 2)
    key = "groundcover_oc_ft" if habit == "groundcover" else "herbaceous_oc_ft"
    return round(max(0.5, min(mature, float(dense[key]))), 2)


def _mass_sizes():
    sizes = practice.rule("design.mass_sizes")
    return sorted(sizes.get("small_bed") or sizes["default"], reverse=True)


def _is_structure(plant):
    from . import design as design_mod
    return design_mod._is_structure(plant)


def _is_makeup(plant):
    from . import design as design_mod
    return design_mod._is_makeup(plant)


def _feeds(plant):
    """True when the plant counts toward the nectar spine."""
    return (plant.get("nectar") is True and not _is_structure(plant)
            and not _is_makeup(plant))


def _genus(plant):
    return ((plant.get("botanical") or "").split() or [""])[0].lower()


# ------------------------------------------------------------------ the beds

def load_brief(slug):
    """The yard facts that the design file does not hold.

    Bed order, the reason for each bed, keep-out strips, niche splits, and
    name overrides. A yard without a brief gets one sheet per border bed.
    """
    return yards.load(slug, BRIEF) or {}


def _short_name(label):
    """The plant name without the notes that the layout adds."""
    name = label.split(" - ")[0].split(" (")[0].strip()
    return name or label


def _stays(label, record):
    """True when the plant is already in the ground and does not move."""
    blob = f"{label} {(record or {}).get('role') or ''}".lower()
    return "(existing" in blob or " existing" in blob


def _niche_of(spec, x):
    """The niche that holds this x position in the bed."""
    splits = spec.get("niches")
    if splits is None:
        return "bed_" + spec["id"]
    for split in splits:
        limit = split.get("x_below")
        if limit is None or float(x) < float(limit):
            return split["id"]
    return None


def _niche_ids(spec):
    splits = spec.get("niches")
    if splits is None:
        return ["bed_" + spec["id"]]
    return [split["id"] for split in splits]


def _bed_specs(slug, design):
    """One spec per sheet, in the brief order, else in the layout order."""
    brief = load_brief(slug)
    specs = list(brief.get("beds") or [])
    if specs:
        return specs, brief.get("plants") or {}
    out = []
    for spec in (design.get("layout") or {}).get("beds") or []:
        if spec.get("type") != "border":
            continue
        name = spec.get("name") or ""
        out.append({"id": name.split("-")[0], "layout": name})
    return out, {}


def _beds_from_garden(slug):
    """The planting already drawn, one circle per plant on that map."""
    design = yards.load(slug, "design.json") or {}
    records = {p.get("name"): p for p in design.get("plants") or []}
    layouts = {spec.get("name"): spec
               for spec in (design.get("layout") or {}).get("beds") or []}
    specs, renames = _bed_specs(slug, design)
    found = []
    for brief in specs:
        spec = layouts.get(brief.get("layout"))
        if not spec:
            continue
        bed_id = brief["id"]
        plants = []
        extent_x = float(spec.get("length") or 0)
        extent_y = float(spec.get("depth") or 0)
        for src in spec.get("plants") or []:
            key = src.get("plant") or src.get("label") or ""
            record = records.get(key) or {}
            over = renames.get(key) or {}
            name = over.get("name") or _short_name(key)
            botanical = over.get("botanical", record.get("botanical") or "")
            locked = over.get("stays", _stays(key, record))
            feature = "botanical" in over and not over["botanical"]
            drawn = round(float(src["r"]) * 2, 3)
            x, y = float(src["x"]), float(src["y"])
            extent_x = max(extent_x, x + drawn / 2)
            extent_y = max(extent_y, y + drawn / 2)
            plant = _plant(
                bed_id, _niche_of(brief, x), name, botanical, drawn, x, y,
                locked=locked, kept=True, record=record, feature=feature)
            plant["drawn_ft"] = drawn
            if not locked:
                # A plant that is not in the ground yet is drawn at its
                # planting distance. The ring shows the mature width.
                mature = float(plant["mature_spread_ft"] or drawn)
                plant["mature_spread_ft"] = round(max(mature, drawn), 3)
                plant["spread_ft"] = round(min(drawn, spacing_for(plant)), 3)
            plants.append(plant)
        depth = float(spec.get("depth") or extent_y)
        bed = {
            "id": bed_id,
            "zone": spec.get("zone") or "bed_" + bed_id,
            "length_ft": round(max(float(spec.get("length") or 0),
                                   extent_x + 0.08), 3),
            "depth_ft": round(depth, 3),
            "above_ft": round(max(0.0, extent_y - depth + 0.08), 3),
            "wall": brief.get("wall") or "House wall",
            "front": brief.get("front") or "Front edge",
            "why": brief.get("why") or "",
            "niches": _niche_ids(brief),
            "splits": brief.get("niches"),
            "plants": plants,
        }
        strips = brief.get("keep_out") or []
        if isinstance(strips, dict):
            strips = [strips]
        if strips:
            bed["keep_out"] = [dict(strip) for strip in strips]
        if brief.get("more"):
            bed["more"] = list(brief["more"])
        found.append(bed)
    return found


# ------------------------------------------------------------ the new drifts

def _rank(plant):
    """A host comes first, then nectar. A color annual comes last."""
    if _is_makeup(plant):
        return 3
    if plant.get("host"):
        return 0
    if plant.get("nectar") is True:
        return 1
    return 2


def _coverage(yard, plants):
    """Nectar species by month and by season, and the hosts, for one bed."""
    by_month = {m: set() for m in MONTHS}
    for plant in plants:
        if _feeds(plant):
            for m in plant.get("bloom") or []:
                by_month[m].add(plant["name"])
    seasons = {}
    for season, months in (yard.regional("wildlife.seasons") or {}).items():
        names = set()
        for m in months:
            names |= by_month.get(m, set())
        seasons[season] = names
    hosts = {p["name"] for p in plants if p.get("host")}
    return by_month, seasons, hosts


def _keystone(yard):
    value = yard.regional("wildlife.keystone_genera") or {}
    if isinstance(value, dict):
        names = (value.get("herbaceous_confirmed") or []) + (value.get("woody_confirmed") or [])
    else:
        names = value
    return {g.lower() for g in names}


def _score(yard, bed, cand, elsewhere):
    """How much this species would add to the bed, by the practice rules."""
    by_month, seasons, hosts = _coverage(yard, bed["plants"])
    months = yard.regional("wildlife.nectar_months") or []
    per_season = practice.rule("wildlife.nectar_species_per_season")
    min_hosts = practice.rule("wildlife.min_hosts_per_bed")
    keystone = _keystone(yard)
    bloom = set(cand.get("bloom") or [])
    gain = 0.0
    if _feeds(cand):
        gain += 3 * sum(1 for m in months if m in bloom and not by_month[m])
        for season, have in seasons.items():
            span = set((yard.regional("wildlife.seasons") or {}).get(season) or [])
            if len(have) < per_season and bloom & span and cand["name"] not in have:
                gain += 2
    if cand.get("host"):
        gain += 4 if len(hosts) < min_hosts else 1
    if _genus(cand) in keystone:
        gain += 1
    if cand.get("native"):
        gain += 1
    elif cand.get("native") is False:
        gain -= 2
    if cand["name"] in elsewhere:
        gain += 1
    if any(p["name"] == cand["name"] for p in bed["plants"]):
        gain -= 2
    colors = {p.get("flower") for p in bed["plants"]
              if (_feeds(p) or p.get("host")) and p.get("flower")}
    flower = cand.get("flower")
    if flower and colors:
        if flower in colors:
            gain += 1
        elif len(colors) >= max(practice.rule("design.color_theme_count")):
            gain -= 1
    return gain


def _pool(yard, bed):
    """Candidates for this bed, with the niches that accept each one."""
    pool = {}
    for niche_id in bed["niches"]:
        niche = yard.niches.get(niche_id)
        if not niche:
            continue
        for name, cand in _candidates(niche).items():
            if bed.get("more") and name not in bed["more"]:
                continue
            if yard.rejection(niche_id, cand):
                continue
            entry = pool.get(name)
            if entry is None:
                sample = _plant(bed["id"], niche_id, name, cand.get("botanical"),
                                float(cand["mature_spread_ft"]), 0, 0)
                sample["height_ft"] = sample.get("height_ft") or cand.get("mature_height_ft")
                sample["mature_spread_ft"] = float(cand["mature_spread_ft"])
                entry = pool[name] = {"plant": sample, "cand": cand, "niches": set()}
            entry["niches"].add(niche_id)
    return pool


def _target_y(bed, height, spacing):
    """Tall toward the wall, short toward the front, by the bed's own range."""
    heights = [float(p["height_ft"]) for p in bed["plants"]
               if p.get("height_ft") and not _is_structure(p)
               and p.get("layer") != "vine"]
    tallest = max(heights + [float(height or 0), 0.1])
    lo = spacing / 2 + 0.05
    for band in bed.get("keep_out") or []:
        # A strip along part of the bed is left to in_bed, so the open end
        # of the bed can still take a low plant.
        if band.get("x_from") is None and band.get("x_to") is None:
            lo = max(lo, float(band["y_below"]) + spacing / 2 + 0.02)
    hi = float(bed["depth_ft"]) - spacing / 2 - 0.02
    if hi < lo:
        return None, lo, hi
    frac = min(1.0, float(height or 0) / tallest)
    return lo + (hi - lo) * frac, lo, hi


def _grow(bed, sample, spacing, size, niches_ok, spec):
    """A drift of `size` touching circles near the right height, or None."""
    y_t, lo, hi = _target_y(bed, sample.get("height_ft"), spacing)
    if y_t is None:
        return None
    length = float(bed["length_ft"])
    points = []
    y = lo
    while y <= hi + 1e-6:
        x = spacing / 2 + 0.05
        while x <= length - spacing / 2 - 0.02 + 1e-6:
            points.append((round(x, 3), round(y, 3)))
            x += STEP
        y += STEP
    placed = bed["plants"]
    band = _band(sample.get("height_ft"))

    def layered(trial):
        """No layer jump: not in front of a shorter plant, not behind a taller one."""
        if band is None:
            return True
        for other in placed:
            if (_is_structure(other) or _is_makeup(other)
                    or other.get("height_ft") is None):
                continue
            if abs(other["x"] - trial["x"]) > _radius(other) + spacing / 2:
                continue
            other_band = _band(other["height_ft"])
            if other["y"] > trial["y"] + 0.3 and other_band < band:
                return False
            if other["y"] < trial["y"] - 0.3 and other_band > band:
                return False
        return True

    def free(x, y, members):
        if _niche_of(spec, x) not in niches_ok:
            return False
        trial = {"x": x, "y": y, "spread_ft": spacing}
        if not in_bed(bed, dict(trial, locked=False, kept=False)):
            return False
        if any(overlaps(trial, other) for other in placed + members):
            return False
        return layered(trial)

    seeds = sorted(points, key=lambda p: (abs(p[1] - y_t), p[0]))
    for sx, sy in seeds[:600]:
        if not free(sx, sy, []):
            continue
        members = [{"x": sx, "y": sy, "spread_ft": spacing}]
        while len(members) < size:
            cx = sum(m["x"] for m in members) / len(members)
            cy = sum(m["y"] for m in members) / len(members)
            best = None
            for px, py in points:
                near = min(math.hypot(px - m["x"], py - m["y"]) for m in members)
                if near > spacing * 1.2:
                    continue
                if not free(px, py, members):
                    continue
                cost = math.hypot(px - cx, py - cy) + 0.5 * abs(py - y_t)
                if best is None or cost < best[0]:
                    best = (cost, px, py)
            if best is None:
                break
            members.append({"x": best[1], "y": best[2], "spread_ft": spacing})
        if len(members) == size:
            return members
    return None


def _add_drifts(yard, beds, specs):
    """Add drifts of one nectar or host species each. Do not mix a grid."""
    sizes = _mass_sizes()
    placed_names = {}
    # A new plant of a species already in the garden takes the same traits,
    # so one species does not show two bloom seasons on one page.
    known = {}
    for bed in beds:
        for plant in bed["plants"]:
            placed_names.setdefault(plant["name"], set()).add(bed["id"])
            known.setdefault(plant["name"], plant)
    trait_keys = [k for k in traits("", "") if k != "mature_spread_ft"] + ["color"]
    for bed in beds:
        spec = specs[bed["id"]]
        pool = _pool(yard, bed)
        for name, entry in pool.items():
            if name in known:
                entry["plant"].update({k: known[name].get(k) for k in trait_keys})
        tried = set()
        drifts = {}
        while True:
            elsewhere = {n for n, where in placed_names.items()
                         if where - {bed["id"]}}
            ranked = []
            for name, entry in pool.items():
                sample = entry["plant"]
                if name in tried or _rank(sample) >= 2:
                    continue
                if drifts.get(name, 0) >= MASSES_PER_SPECIES:
                    continue
                ranked.append((-_score(yard, bed, sample, elsewhere),
                               _rank(sample), name))
            if not ranked:
                break
            ranked.sort()
            _, _, name = ranked[0]
            entry = pool[name]
            sample = entry["plant"]
            spacing = min(spacing_for(sample), max(0.5, float(bed["depth_ft"]) / 2))
            same = [p["spread_ft"] for p in bed["plants"] if p["name"] == name]
            if same:
                spacing = min(spacing, min(same))
            drift = None
            for size in sizes:
                drift = _grow(bed, sample, spacing, size, entry["niches"], spec)
                if drift:
                    break
            if not drift:
                tried.add(name)
                continue
            for member in drift:
                niche_id = _niche_of(spec, member["x"])
                plant = _plant(bed["id"], niche_id, name,
                               entry["cand"].get("botanical"), spacing,
                               member["x"], member["y"])
                plant["mature_spread_ft"] = float(sample["mature_spread_ft"])
                plant["height_ft"] = sample.get("height_ft")
                if name in known:
                    plant.update({k: known[name].get(k) for k in trait_keys})
                bed["plants"].append(plant)
            drifts[name] = drifts.get(name, 0) + 1
            placed_names.setdefault(name, set()).add(bed["id"])


def suggest(slug):
    """The garden already drawn, plus drifts of nectar and host plants."""
    yard = Yard(slug)
    beds = _beds_from_garden(slug)
    specs = {b["id"]: b for b in load_brief(slug).get("beds") or []}
    for bed in beds:
        specs.setdefault(bed["id"], {"id": bed["id"]})
        _touch(bed["plants"])
    _add_drifts(yard, beds, specs)
    for bed in beds:
        _touch(bed["plants"])
        _even_sizes(bed["plants"])
    # Stable ids. The id does not change when a plant is swapped, or a saved
    # tap would point at nothing.
    for bed in beds:
        for i, plant in enumerate(bed["plants"], start=1):
            plant["id"] = f"{bed['id']}-{i:02d}"
    return {"beds": beds, "built": datetime.date.today().isoformat()}


def audit(slug, scheme=None):
    """Overlaps, plants outside the soil, and plants the slate would refuse."""
    scheme = scheme if scheme is not None else load(slug)
    yard = Yard(slug)
    bad = []
    for bed in scheme.get("beds") or []:
        plants = bed.get("plants") or []
        for plant in plants:
            if not in_bed(bed, plant):
                bad.append(f"{plant['id']} {plant['name']} sits outside {bed['id']}")
            if not plant.get("botanical") and not plant.get("feature"):
                bad.append(f"{plant['id']} {plant['name']} has no botanical name")
            if plant.get("locked") or plant.get("kept"):
                continue
            niche = yard.niches.get(plant.get("niche"))
            cand = _candidates(niche).get(plant["name"]) if niche else None
            if cand is None:
                bad.append(f"{plant['id']} {plant['name']} is not on the slate "
                           f"for {plant.get('niche')}")
                continue
            why = yard.rejection(plant["niche"], cand)
            if why:
                bad.append(f"{plant['id']} {plant['name']}: {why}")
        for i, a in enumerate(plants):
            for b in plants[i + 1:]:
                if _crowds(a, b):
                    bad.append(f"{a['id']} {a['name']} overlaps {b['id']} {b['name']}")
        for group in uneven(plants):
            sizes = ", ".join(f"{p['id']} {p['spread_ft']:g}" for p in group)
            bad.append(f"{group[0]['name']} in {bed['id']} has more than one size: {sizes}")
        for plant in plants:
            if shrunk_canopy(plant):
                bad.append(f"{plant['id']} {plant['name']} shrank to {plant['spread_ft']:g} ft "
                           f"from {float(plant['drawn_ft']):g} ft in the source drawing")
    return bad


# ------------------------------------------------------------------ review

def _groups(plants):
    """Runs of the same plant that stand near each other."""
    used = set()
    groups = []
    for index, plant in enumerate(plants):
        if index in used:
            continue
        group = [plant]
        used.add(index)
        grew = True
        while grew:
            grew = False
            for other_index, other in enumerate(plants):
                if other_index in used or other["name"] != plant["name"]:
                    continue
                near = any(
                    _dist(other, member) <= max(
                        other["spread_ft"], member["spread_ft"]) + 0.4
                    for member in group)
                if not near:
                    continue
                group.append(other)
                used.add(other_index)
                grew = True
        groups.append(group)
    return groups


def _band(height):
    from . import design as design_mod
    return design_mod._band(height)


def _taller_than_behind(bed, plant, height):
    """The shortest plant behind this spot in a lower height band, or None.

    The tests are the same as the layer check in the review, with one
    difference. Seasonal color counts here, because a tall plant in
    front hides it all the same.
    """
    band = _band(height)
    if band is None:
        return None
    behind = []
    for other in bed.get("plants") or []:
        if other is plant or other.get("id") == plant.get("id"):
            continue
        if other["y"] <= plant["y"] + 0.3 or other.get("height_ft") is None:
            continue
        if other.get("feature") or _is_structure(other):
            continue
        if abs(other["x"] - plant["x"]) > _radius(other) + _radius(plant):
            continue
        if _band(other["height_ft"]) < band:
            behind.append(other)
    if not behind:
        return None
    return min(behind, key=lambda other: float(other["height_ft"]))


def review(slug, scheme=None):
    """The map against practice/. One finding per line, with its rule."""
    from . import design as design_mod
    scheme = scheme if scheme is not None else load(slug)
    yard = Yard(slug)
    out = []

    def say(bed, key, text):
        out.append({"bed": bed, "rule": key, "text": text,
                    "cite": practice.cite(key)})

    months = yard.regional("wildlife.nectar_months") or []
    per_season = practice.rule("wildlife.nectar_species_per_season")
    min_hosts = practice.rule("wildlife.min_hosts_per_bed")
    sizes = _mass_sizes()
    small = float(practice.rule("design.mass_small_below_ft"))
    theme = practice.rule("design.color_theme_count")
    # No source gives a number for the skyline range, so the rule may be null.
    skyline = practice.rule("design.skyline_min_range_ft")
    share = float(practice.rule("wildlife.native_share"))
    front_share = float(practice.rule("design.front_layer_share"))
    tall_share = float(practice.rule("design.tall_layer_share_max"))
    ever_share = float(practice.rule("design.evergreen_share"))
    bands = practice.rule("design.height_bands_ft")
    winter = [m for m in MONTHS if m not in (yard.regional("wildlife.nectar_months") or [])]
    seen = {}
    total, native = 0.0, 0.0
    for bed in scheme.get("beds") or []:
        plants = [p for p in bed.get("plants") or [] if not p.get("feature")]
        for plant in plants:
            seen.setdefault(plant["name"], set()).add(bed["id"])
            # By mature canopy area, not by count. An annual counts as
            # non-native, because it is makeup and not habitat.
            area = float(plant.get("mature_spread_ft") or plant["spread_ft"]) ** 2
            if plant.get("native") is not None or _is_makeup(plant):
                total += area
                if plant.get("native") and not _is_makeup(plant):
                    native += area
        if not bed.get("niches"):
            say(bed["id"], "design.mass_sizes",
                f"{len(plants)} plant in a pot. The bed checks do not apply.")
            continue
        by_month, seasons, hosts = _coverage(yard, plants)
        gaps = [m for m in months if not by_month[m]]
        if gaps:
            say(bed["id"], "wildlife.nectar_months",
                f"no nectar plant in flower in {', '.join(gaps)}.")
        for season, names in seasons.items():
            if len(names) < per_season:
                say(bed["id"], "wildlife.nectar_species_per_season",
                    f"{len(names)} nectar species in {season}, not {per_season}.")
        if len(hosts) < min_hosts:
            say(bed["id"], "wildlife.min_hosts_per_bed",
                f"{len(hosts)} larval host plants, not {min_hosts}.")
        for group in _groups(plants):
            head = group[0]
            new = not head.get("kept")
            h = head.get("height_ft")
            if new and len(group) not in sizes and len(group) < max(sizes):
                say(bed["id"], "design.mass_sizes",
                    f"{head['name']} is a group of {len(group)}.")
            if new and len(group) == 1 and h is not None and float(h) < small:
                say(bed["id"], "design.mass_small_below_ft",
                    f"{head['name']} stands alone at {h} ft.")
        told = set()
        for low in plants:
            for high in plants:
                if low is high or low["y"] >= high["y"] - 0.3:
                    continue
                if low.get("kept") and high.get("kept"):
                    continue
                if abs(low["x"] - high["x"]) > _radius(low) + _radius(high):
                    continue
                if any(_is_structure(p) or _is_makeup(p) for p in (low, high)):
                    continue
                lb, hb = _band(low.get("height_ft")), _band(high.get("height_ft"))
                if lb is None or hb is None or lb <= hb:
                    continue
                key = (low["name"], high["name"])
                if key in told:
                    continue
                told.add(key)
                say(bed["id"], "design.height_bands_ft",
                    f"{low['name']} ({low.get('height_ft')} ft) stands in front "
                    f"of {high['name']} ({high.get('height_ft')} ft).")
        judged = [p for p in plants if p.get("height_ft") is not None]
        if len(judged) >= 5:
            low = sum(1 for p in judged if _band(p["height_ft"]) <= 1)
            # The emergent layer, by height: the background band.
            tall = sum(1 for p in judged if float(p["height_ft"]) > float(bands[-1]))
            if low / len(judged) < front_share:
                say(bed["id"], "design.front_layer_share",
                    f"{low} of {len(judged)} plants are {bands[1]} ft or shorter.")
            if tall / len(judged) > tall_share:
                say(bed["id"], "design.tall_layer_share_max",
                    f"{tall} of {len(judged)} plants are over {bands[-1]} ft.")
        ever = sum(1 for p in plants if p.get("evergreen"))
        if plants and ever / len(plants) < ever_share:
            say(bed["id"], "design.evergreen_share",
                f"{ever} of {len(plants)} plants hold structure in winter. "
                f"Standing stems are not on record, so they are not counted.")
        if winter and not any(p.get("evergreen") or set(p.get("bloom") or []) & set(winter)
                              for p in plants):
            say(bed["id"], "design.interest_every_season",
                f"nothing is green or in flower in {', '.join(winter)}.")
        heights = [float(p["height_ft"]) for p in plants
                   if p.get("height_ft") and not _is_structure(p)]
        if skyline is not None and len(heights) >= 3 and max(heights) - min(heights) < float(skyline):
            say(bed["id"], "design.skyline_min_range_ft",
                f"the top of the bed stays within {max(heights) - min(heights):.1f} ft.")
        colors = {p.get("flower") for p in plants
                  if (_feeds(p) or p.get("host")) and p.get("flower")}
        if colors and not (min(theme) <= len(colors) <= max(theme) + 1):
            say(bed["id"], "design.color_theme_count",
                f"{len(colors)} flower colors in the wildlife plants: "
                f"{', '.join(sorted(colors))}.")
        for limit in design_mod.limits_for(yard.vis, bed.get("zone")):
            tallest = max(plants, key=lambda p: float(p.get("height_ft") or 0)
                          if not design_mod._exempt(p, limit) else -1)
            widest = max(plants, key=lambda p: float(p.get("mature_spread_ft") or 0)
                         if not design_mod._exempt(p, limit) else -1)
            for plant in {tallest["name"]: tallest, widest["name"]: widest}.values():
                breach = design_mod.limit_breach(plant, bed.get("zone"), yard.vis)
                if breach:
                    say(bed["id"], "design.height_bands_ft",
                        f"{plant['name']}: {breach[1]}")
            out.append({"bed": bed["id"], "rule": "vision.limits",
                        "text": f"tallest {tallest['name']} "
                                f"{tallest.get('height_ft')} ft, widest "
                                f"{widest['name']} {widest.get('mature_spread_ft')} ft, "
                                f"limit {limit.get('max_height_ft')} ft.",
                        "cite": "vision.json limits", "info": True})
    repeat = int(practice.rule("design.repeat_min_beds"))
    if not any(len(where) >= repeat for where in seen.values()):
        say("yard", "design.repeat_min_beds", "no plant repeats from bed to bed.")
    if total and native / total < share:
        say("yard", "wildlife.native_share",
            f"native plants cover {native / total:.0%} of the mature planting area.")
    every = [p for bed in scheme.get("beds") or [] for p in bed.get("plants") or []
             if not p.get("feature")]
    nectar = {p["name"] for p in every if p.get("nectar") is True and not _is_makeup(p)}
    fewest = int(practice.rule("wildlife.min_nectar_species_total"))
    if len(nectar) < fewest:
        say("yard", "wildlife.min_nectar_species_total",
            f"{len(nectar)} nectar species in the yard, not {fewest}.")
    makeup = practice.rule("wildlife.annuals_as_makeup")
    annual = sum(1 for p in every if _is_makeup(p))
    if every and annual / len(every) > float(makeup["max_share"]):
        say("yard", "wildlife.annuals_as_makeup",
            f"{annual} of {len(every)} plants are annual makeup.")
    return out


# ------------------------------------------------------------------ choosing

def load(slug):
    return yards.load(slug, FILE)


def find_plant(scheme, plant_id):
    for bed in scheme.get("beds") or []:
        for plant in bed.get("plants") or []:
            if plant["id"] == plant_id:
                return bed, plant
    return None, None


def _photo_for(yard, plant):
    """The first photograph of this plant on any slate, else in the cache."""
    name = plant.get("name") or ""
    botanical = (plant.get("botanical") or "").strip().lower()
    for niche in yard.niches.values():
        for cand in _candidates(niche).values():
            same = cand["name"] == name or (
                botanical and (cand.get("botanical") or "").strip().lower() == botanical)
            if same and cand.get("photos"):
                return cand["photos"][0]
    # Only a plain binomial goes to the photo service. A genus, a cultivar
    # or "A / B" names no one species, and a photo of one would be a guess.
    words = botanical.split()
    if len(words) == 2 and all(w.isalpha() for w in words):
        found = niches._fetch_photos(plant["botanical"].strip())
        if found:
            return found[0]
    return {}


def current_for(scheme, plant_id, yard):
    """The plant that stands in this circle now, in the shape of a choice."""
    _, plant = find_plant(scheme, plant_id)
    if not plant:
        return None
    photo = _photo_for(yard, plant)
    return {
        "name": plant["name"],
        "botanical": plant.get("botanical") or "",
        "tall_ft": plant.get("height_ft"),
        "grows_ft": round(float(plant.get("mature_spread_ft") or plant["spread_ft"]), 2),
        "bloom": plant.get("bloom") or [],
        "fruit": plant.get("fruit") or [],
        "fruit_what": plant.get("fruit_what") or "",
        "fruit_for": plant.get("fruit_for") or [],
        "seed_for": plant.get("seed_for") or [],
        "nectar": plant.get("nectar") is True,
        "host": plant.get("host") or [],
        "color": plant.get("color") or color_for(plant.get("flower"), plant.get("evergreen"),
                                                 plant.get("feature")),
        "photo": photo.get("url") or "",
        "attribution": (photo.get("attribution") or "")[:80],
        "locked": bool(plant.get("locked")),
    }


def fits_gap(bed, plant, spread, neighbors):
    """True when a plant of this spread can stand where `plant` stands.

    A plant no wider than the circle already here takes no new ground.
    """
    if float(spread) <= float(plant["spread_ft"]) + 0.001:
        return True
    trial = dict(plant)
    trial["spread_ft"] = float(spread)
    trial["locked"] = False
    trial["kept"] = False
    if not in_bed(bed, trial):
        return False
    for other in neighbors:
        if other["id"] == plant["id"]:
            continue
        if _crowds(trial, other):
            return False
    return True


def options_for(slug, scheme, plant_id, yard=None):
    """Plants that can replace this one circle. Locked circles have none."""
    bed, plant = find_plant(scheme, plant_id)
    if not bed or not plant:
        return None, "That plant is not on the map."
    if plant.get("locked"):
        return [], None
    yard = yard or Yard(slug)
    niche = yard.niches.get(plant.get("niche"))
    if not niche:
        return [], "This spot has no plant list."
    out = []
    refused = []
    for cand in _candidates(niche).values():
        if cand["name"] == plant["name"]:
            continue
        why = yard.rejection(plant["niche"], cand)
        if why:
            refused.append(why)
            continue
        hole = float(plant["spread_ft"])
        spacing = spacing_for({"mature_spread_ft": cand["mature_spread_ft"],
                               "habit": cand.get("habit")})
        spread = round(min(spacing, hole), 3)
        if not fits_gap(bed, plant, spread, bed["plants"]):
            continue
        t = traits(cand["name"], cand.get("botanical"))
        photo = (cand.get("photos") or [None])[0] or {}
        sample = dict(t, name=cand["name"])
        # The flag reads the height that a swap plants, so it matches the result.
        shorter = _taller_than_behind(bed, dict(plant, spread_ft=spread), t["height_ft"])
        tall_ft = t["height_ft"] if t["height_ft"] is not None else cand.get("mature_height_ft")
        out.append({
            "name": cand["name"],
            "botanical": cand.get("botanical") or "",
            "spread_ft": spread,
            "grows_ft": round(float(cand["mature_spread_ft"]), 2),
            "tall_ft": tall_ft,
            "bloom": t["bloom"],
            "fruit": t["fruit"],
            "fruit_what": t["fruit_what"] or "",
            "fruit_for": t["fruit_for"],
            "seed_for": t["seed_for"],
            "nectar": t["nectar"] is True,
            "host": t["host"],
            "note": (cand.get("note") or "").split(". ")[0],
            "color": color_for(t["flower"], t.get("evergreen")),
            "photo": photo.get("url") or "",
            "attribution": (photo.get("attribution") or "")[:80],
            "rank": _rank(sample),
            # A taller plant in front of a shorter one breaks
            # design.no_layer_jump. The option stays, at the bottom.
            "taller_than": ({"name": shorter["name"],
                             "tall_ft": shorter["height_ft"]} if shorter else None),
        })
    out.sort(key=lambda row: (row["taller_than"] is not None, row["rank"],
                              row["name"].lower()))
    if not out:
        return [], _site_limit(refused)
    return out, None


def _site_limit(reasons):
    """The site fact that kept every other plant off the list."""
    blob = " ".join(reasons).lower()
    if "window" in blob or ("past" in blob and " ft" in blob):
        return "The size limit here rules out the other plants."
    if any(word in blob for word in ("sun", "shade", "light", "hour")):
        return "The light here rules out the other plants."
    if "depth" in blob or "root" in blob:
        return "The soil depth here rules out the other plants."
    if "drain" in blob:
        return "The drainage here rules out the other plants."
    return "No other plant on this list fits this spot."


def swap(slug, plant_id, name):
    """Replace one circle and write the file. The other circles stay."""
    scheme = load(slug)
    if not scheme:
        raise SystemExit(f"{slug} has no {FILE}. Run --init first.")
    bed, plant = find_plant(scheme, plant_id)
    if not plant:
        return None, "That plant is not on the map."
    if plant.get("locked"):
        return None, "This plant stays. It is already in the ground."
    choices, err = options_for(slug, scheme, plant_id)
    if err:
        return None, err
    picked = next((c for c in choices if c["name"] == name), None)
    if not picked:
        return None, f"{name} does not fit this gap."
    fresh = _plant(bed["id"], plant["niche"], picked["name"], picked["botanical"],
                   picked["spread_ft"], plant["x"], plant["y"])
    fresh["id"] = plant["id"]
    fresh["mature_spread_ft"] = picked["grows_ft"]
    # The whole old plant, because the old name can fail the fit check. A
    # kept plant from the design is not always a choice on the slate.
    scheme.setdefault("history", []).append({
        "id": plant["id"], "before": json.loads(json.dumps(plant)),
        "after": fresh["name"],
        "at": datetime.datetime.now().isoformat(timespec="seconds")})
    plant.clear()
    plant.update(fresh)
    yards.save(slug, FILE, scheme)
    return plant, None


def _undo_count(scheme, plant_id=None):
    history = scheme.get("history") or []
    return {"plant": sum(1 for h in history if h["id"] == plant_id),
            "all": len(history)}


def undo(slug, plant_id=None):
    """Put back the plant from before the newest swap, on one circle or on the map."""
    scheme = load(slug)
    if not scheme:
        raise SystemExit(f"{slug} has no {FILE}. Run --init first.")
    history = scheme.get("history") or []
    index = next((i for i in range(len(history) - 1, -1, -1)
                  if not plant_id or history[i]["id"] == plant_id), None)
    if index is None:
        return None, "There is no change to undo."
    entry = history[index]
    _, plant = find_plant(scheme, entry["id"])
    if not plant:
        return None, "That plant is not on the map."
    history.pop(index)
    plant.clear()
    plant.update(entry["before"])
    yards.save(slug, FILE, scheme)
    return plant, None


# ---------------------------------------------------------------- the page

TITLE = "The beds"


def _esc(text):
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def codes(scheme):
    """A short code for each plant name, unique on the page."""
    out = {}
    taken = set()
    names = []
    for bed in scheme.get("beds") or []:
        for plant in bed.get("plants") or []:
            if plant["name"] not in names:
                names.append(plant["name"])
    for name in names:
        words = [w for w in name.replace("'", "").replace("-", " ").split() if w[0].isalpha()]
        if len(words) >= 2:
            base = (words[0][0] + words[1][0]).upper()
        else:
            base = (words[0][:2] if words else name[:2]).upper()
        code = base
        tail = "".join(words)[2:] if words else ""
        i = 0
        while code in taken:
            if i < len(tail):
                code = base[0] + tail[i].upper()
            else:
                code = f"{base}{i - len(tail) + 2}"
            i += 1
        taken.add(code)
        out[name] = code
    return out


def _text_px(text, size):
    return len(text) * size * 0.62


def _box_covers(box, centre, radius):
    """True when a label box reaches more than a pixel into a circle."""
    x, y, w, h = box
    nx = min(max(centre[0], x), x + w)
    ny = min(max(centre[1], y), y + h)
    return math.hypot(nx - centre[0], ny - centre[1]) < radius - 1


def _svg(bed, code_of, font, tap):
    length = float(bed["length_ft"])
    depth = float(bed["depth_ft"])
    above = float(bed.get("above_ft") or 0)
    pad = 36
    scale = min(SCALE, (SHEET_PX - 2 * pad) / max(length, 1.0))
    tag_h = font + 10
    plants = bed.get("plants") or []

    def xy(plant):
        return (pad + float(plant["x"]) * scale,
                pad + (above + depth - float(plant["y"])) * scale)

    # Every circle is one plant and carries only its code. The schedule gives
    # the count. A label that does not fit inside its circle goes to a row of tags
    # under the front edge, in x order, so the leaders do not cross.
    inside, outside = [], []
    group_of = {}
    groups = _groups(plants)
    for index, group in enumerate(groups):
        for member in group:
            group_of[id(member)] = index

    def fits_in(member, text):
        width = _text_px(text, font) + 8
        r = max(_radius(member) * scale, 10)
        if width > r * 2 - 2 or font + 2 > r * 2:
            return False
        mx, my = xy(member)
        box = (mx - width / 2, my - font / 2 - 1, width, font + 2)
        # A plant under a canopy is drawn inside the canopy, so its label may
        # sit on the canopy too.
        return not any(other is not member and not _under_canopy(member, other)
                       and _box_covers(box, xy(other), _radius(other) * scale)
                       for other in plants)

    for group in groups:
        code = code_of[group[0]["name"]]
        for member in group:
            if fits_in(member, code):
                inside.append((*xy(member), code, group, member))
            else:
                mx, my = xy(member)
                outside.append((mx, my, code, [member]))
    outside.sort(key=lambda row: row[0])
    rows = []
    tags = []
    base_y = pad + (above + depth) * scale + 18
    for ax, ay, text, group in outside:
        width = _text_px(text, font) + 10
        placed = False
        for row_i, end in enumerate(rows):
            x = max(ax - width / 2, end + 6, pad)
            if x - ax < 260:
                rows[row_i] = x + width
                tags.append((ax, ay, x, base_y + row_i * (tag_h + 6), width, text, group))
                placed = True
                break
        if not placed:
            x = max(ax - width / 2, pad)
            rows.append(x + width)
            tags.append((ax, ay, x, base_y + (len(rows) - 1) * (tag_h + 6), width, text, group))
    tag_rows = len(rows)
    right = max([pad + length * scale] + [t[2] + t[4] for t in tags]) + pad
    width_px = int(right)
    front_y = pad + (above + depth) * scale + 18 + tag_rows * (tag_h + 6) + 8
    height_px = int(front_y + font + 12)
    parts = [
        f"<svg class=bed data-bed='{_esc(bed['id'])}' width='{width_px}' "
        f"height='{height_px}' viewBox='0 0 {width_px} {height_px}' role='img' "
        f"aria-label='{_esc(bed['id'])} planting plan'>",
        f"<defs><pattern id='stone-{_esc(bed['id'])}' width='14' height='14' "
        f"patternUnits='userSpaceOnUse'><rect width='14' height='14' fill='#e4dfd6'></rect>"
        f"<circle cx='4' cy='4' r='2.6' fill='#b8b0a3'></circle>"
        f"<circle cx='11' cy='10' r='2.2' fill='#c7bfb2'></circle></pattern>"
        f"<pattern id='white-bloom-{_esc(bed['id'])}' width='12' height='12' "
        f"patternUnits='userSpaceOnUse'>{WHITE_BLOOM_TILE}</pattern></defs>",
    ]
    soil_top = pad + above * scale
    # Labels go in the last layer, so no circle covers them.
    top = []
    parts.append(
        f"<rect x='{pad}' y='{soil_top:.1f}' width='{length * scale:.1f}' "
        f"height='{depth * scale:.1f}' class=soil></rect>")
    for band in bed.get("keep_out") or []:
        x_from = float(band.get("x_from") or 0)
        x_to = float(band["x_to"]) if band.get("x_to") is not None else length
        h = float(band["y_below"]) * scale
        y = soil_top + (depth - float(band["y_below"])) * scale
        x0 = pad + x_from * scale
        parts.append(
            f"<rect x='{x0:.1f}' y='{y:.1f}' width='{(x_to - x_from) * scale:.1f}' "
            f"height='{h:.1f}' class='band {_esc(band.get('kind') or 'sown')}'"
            + (f" fill='url(#stone-{_esc(bed['id'])})'" if band.get("kind") == "stone" else "")
            + "></rect>")
        top.append(
            f"<text class=bandlabel x='{x0 + 8:.1f}' y='{y + h - 6:.1f}'>"
            f"{_esc(band.get('label') or '')}</text>")
    top.append(
        f"<text class=edge x='{pad}' y='{pad - 12:.1f}'>"
        f"{_esc(bed.get('wall') or '')}</text>")
    top.append(
        f"<text class=edge x='{pad}' y='{front_y + font:.1f}'>"
        f"{_esc(bed.get('front') or '')}</text>")
    labelled = {id(h): (x, y, t) for x, y, t, g, h in inside}
    # A drift of one species reads as one outline. Each member is drawn as a
    # wider circle with a stroke, then again without one, which leaves only
    # the outer edge of the union.
    edge, fill = [], []
    for group in _groups(plants):
        if len(group) < 2 or all(p.get("kept") for p in group):
            continue
        for member in group:
            mx, my = xy(member)
            rr = max(_radius(member) * scale, 10) + 5
            edge.append(f"<circle cx='{mx:.1f}' cy='{my:.1f}' r='{rr:.1f}'></circle>")
            fill.append(f"<circle cx='{mx:.1f}' cy='{my:.1f}' r='{rr - 1.2:.1f}'></circle>")
    if edge:
        parts.append("<g class=bubble-edge>" + "".join(edge) + "</g>")
        parts.append("<g class=bubble-fill>" + "".join(fill) + "</g>")
    for plant in plants:
        cx, cy = xy(plant)
        r = max(_radius(plant) * scale, 10)
        classes = ["plant"]
        if plant.get("locked"):
            classes.append("locked")
        elif plant.get("kept"):
            classes.append("kept")
        if plant.get("host"):
            classes.append("host")
        parts.append(
            f"<g class='{' '.join(classes)}' data-id='{_esc(plant['id'])}' "
            f"data-name='{_esc(plant['name'])}' "
            f"data-code='{_esc(code_of[plant['name']])}' "
            f"data-group='{group_of[id(plant)]}' "
            f"data-feeds='{'1' if _feeds(plant) else '0'}' "
            f"data-locked='{'1' if plant.get('locked') else '0'}' "
            f"data-bloom='{' '.join(plant.get('bloom') or [])}' "
            f"data-leaf='{' '.join(plant.get('leaf') or [])}' "
            f"data-ever='{'1' if plant.get('evergreen') else '0'}' "
            f"data-nectar='{'1' if plant.get('nectar') is True else '0'}' "
            f"data-fruit='{' '.join(plant.get('fruit') or [])}' "
            f"data-flower='{_esc(color_for(plant.get('flower'), plant.get('evergreen'), plant.get('feature')))}'>")
        parts.append(
            f"<circle class=hit cx='{cx:.1f}' cy='{cy:.1f}' r='{max(r, tap / 2):.1f}'></circle>")
        parts.append(
            f"<circle class=solid cx='{cx:.1f}' cy='{cy:.1f}' r='{r:.1f}' "
            f"fill='{_esc(plant.get('color') or '#8aa37b')}'></circle>")
        mature = float(plant.get("mature_spread_ft") or plant["spread_ft"]) / 2 * scale
        covers = any(other is not plant and _dist(plant, other) * scale < mature
                     for other in plants)
        if not covers and mature > r + 4:
            parts.append(
                f"<circle class=mature cx='{cx:.1f}' cy='{cy:.1f}' r='{mature:.1f}'></circle>")
        if plant.get("habit") == "grass":
            for dx in (-4, 0, 4):
                parts.append(
                    f"<line x1='{cx + dx:.1f}' y1='{cy - 6:.1f}' "
                    f"x2='{cx + dx:.1f}' y2='{cy + 6:.1f}' class=tuft></line>")
        parts.append(
            f"<circle class=evering cx='{cx:.1f}' cy='{cy:.1f}' r='{max(r - 4, 4):.1f}'></circle>")
        if plant.get("nectar") is True:
            parts.append(
                f"<circle class=nectar cx='{cx + r * 0.62:.1f}' cy='{cy - r * 0.62:.1f}' r='3.5'></circle>")
        if plant.get("fruit") and plant.get("fruit_color") in FRUIT_HEX:
            fx, fy = cx + r * 0.5, cy + r * 0.5
            hexed = FRUIT_HEX[plant["fruit_color"]]
            berries = ((-4.2, 0), (4.2, 0), (0, -6))
            # A white halo under a dark edge, so the fruit shows on a flower
            # of the same color.
            parts.append(
                "<g class=fruit>"
                + "".join(f"<circle class=halo cx='{fx + dx:.1f}' cy='{fy + dy:.1f}' r='5.6'></circle>"
                          for dx, dy in berries)
                + "".join(f"<circle cx='{fx + dx:.1f}' cy='{fy + dy:.1f}' r='4' fill='{hexed}'></circle>"
                          for dx, dy in berries)
                + "</g>")
        if plant.get("host"):
            lx, ly = cx - r * 0.62, cy - r * 0.62
            parts.append(
                f"<path class=leaf d='M{lx - 5:.1f},{ly + 3:.1f} Q{lx:.1f},{ly - 7:.1f} "
                f"{lx + 5:.1f},{ly - 3:.1f} Q{lx:.1f},{ly + 7:.1f} {lx - 5:.1f},{ly + 3:.1f}Z'></path>")
        if id(plant) in labelled:
            x, y, text = labelled[id(plant)]
            top.append(
                f"<text class=code data-group='{group_of[id(plant)]}' "
                f"data-host='{_esc(plant['id'])}' "
                f"x='{x:.1f}' y='{y + font * 0.36:.1f}' "
                f"text-anchor='middle'>{_esc(text)}</text>")
        parts.append("</g>")
    for ax, ay, x, y, width, text, group in tags:
        head_r = max(_radius(group[0]) * scale, 10)
        parts.append(
            f"<line class=leader x1='{ax:.1f}' y1='{ay + head_r:.1f}' "
            f"x2='{x + width / 2:.1f}' y2='{y:.1f}'></line>")
        parts.append(
            f"<g class=tag data-for='{_esc(group[0]['id'])}' "
            f"data-group='{group_of[id(group[0])]}'>"
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{width:.1f}' height='{tag_h}' rx='4'></rect>"
            f"<text x='{x + width / 2:.1f}' y='{y + tag_h / 2 + font * 0.36:.1f}' "
            f"text-anchor='middle'>{_esc(text)}</text></g>")
    parts.append("<g class=labels>" + "".join(top) + "</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def _strip(bed, yard):
    """Twelve months under the bed: nectar species, evergreen, and gaps."""
    plants = [p for p in bed.get("plants") or [] if not p.get("feature")]
    by_month, _, hosts = _coverage(yard, plants)
    season = yard.regional("wildlife.nectar_months") or []
    top = max([len(v) for v in by_month.values()] + [1])
    ever = any(p.get("evergreen") for p in plants)
    cells = []
    for m in MONTHS:
        n = len(by_month[m])
        gap = m in season and n == 0 and bool(bed.get("niches"))
        cls = "cell gap" if gap else "cell"
        flowers = sum(1 for p in plants if m in (p.get("bloom") or []))
        cells.append(
            f"<button type=button class='{cls}' data-month='{m}' "
            f"aria-label='{m}: {n} nectar species, {flowers} plants in flower'>"
            f"<span class=bar style='height:{int(4 + 28 * n / top)}px'></span>"
            f"<b>{n}</b><i>{m[0]}</i>{'<em>E</em>' if ever else ''}</button>")
    gaps = [m for m in MONTHS if m in season and not by_month[m]]
    if not bed.get("niches"):
        note = "One plant in a pot. The nectar count does not apply."
    elif gaps:
        note = f"{bed['id']}: no nectar in {', '.join(gaps)}."
    else:
        note = f"{bed['id']}: nectar in every month from {season[0]} to {season[-1]}." if season else ""
    host_note = (f"Host plants: {', '.join(sorted(hosts))}." if hosts
                 else "No host plant in this bed.")
    return (f"<div class=strip data-bed='{_esc(bed['id'])}'>{''.join(cells)}</div>"
            f"<p class=stripnote>{_esc(note)} {_esc(host_note)} "
            f"The number is the nectar species in flower. E means evergreen structure.</p>")


def _months_text(months):
    if not months:
        return "not on record"
    if len(months) == 12:
        return "all year"
    # Runs of months, read round the year, so Dec to Mar is one run.
    have = [m in months for m in MONTHS]
    start = next(i for i in range(12) if have[i] and not have[i - 1])
    runs = []
    for step in range(12):
        j = (start + step) % 12
        if have[j] and (not runs or not have[j - 1]):
            runs.append([MONTHS[j]])
        elif have[j]:
            runs[-1].append(MONTHS[j])
    return ", ".join(r[0] if len(r) == 1 else (f"{r[0]}, {r[1]}" if len(r) == 2 else f"{r[0]}-{r[-1]}")
                     for r in runs)


def _schedule(bed, code_of):
    """Code, count, names, spacing, size and bloom. ISO 11091 order."""
    rows = []
    seen = {}
    for plant in bed.get("plants") or []:
        row = seen.get(plant["name"])
        if row is None:
            row = {"plant": plant, "count": 0, "existing": 0, "first": plant["id"]}
            seen[plant["name"]] = row
            rows.append(row)
        row["count"] += 1
        if plant.get("kept"):
            row["existing"] += 1
    lines = ["<table class=schedule>",
             "<tr><th>Code</th><th>Count</th><th>Plant</th><th>Botanical name</th>"
             "<th>Size at planting</th><th>Spacing</th><th>Height</th><th>Width</th>"
             "<th>Flowers</th><th>Fruit</th><th>Wildlife</th></tr>"]
    for row in rows:
        plant = row["plant"]
        wild = []
        if plant.get("nectar") is True:
            wild.append("nectar")
        if plant.get("host"):
            wild.append("host: " + ", ".join(plant["host"]))
        if plant.get("fruit_for"):
            wild.append("fruit for " + ", ".join(plant["fruit_for"]))
        if plant.get("seed_for"):
            wild.append("seed for " + ", ".join(plant["seed_for"]))
        count = str(row["count"])
        if row["existing"] == row["count"]:
            count += " existing"
        elif row["existing"]:
            count += f" ({row['existing']} existing)"
        height = plant.get("height_ft")
        lines.append(
            "<tr data-for='{}' tabindex=0><td>{}</td><td>{}</td><td>{}</td><td><i>{}</i></td>"
            "<td>{}</td><td>{} ft o.c.</td><td>{}</td><td>{} ft</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                _esc(row["first"]),
                _esc(code_of[plant["name"]]), _esc(count), _esc(plant["name"]),
                _esc(plant.get("botanical") or "-"),
                _esc(plant.get("container") or "not set"),
                f"{float(plant.get('spread_ft') or 0):.1f}",
                f"{float(height):.1f} ft" if isinstance(height, (int, float)) else "-",
                f"{float(plant.get('mature_spread_ft') or plant.get('spread_ft') or 0):.1f}",
                _esc(_months_text(plant.get("bloom") or [])),
                _esc(f"{plant.get('fruit_what') or 'fruit'}, {_months_text(plant['fruit'])}"
                     if plant.get("fruit") else "-"),
                _esc(", ".join(wild) or "-")))
    lines.append("</table>")
    return "".join(lines)


def page(scheme, token, stamp=None, yard=None):
    yard = yard or Yard(scheme.get("slug") or "")
    beds = scheme.get("beds") or []
    code_of = codes(scheme)
    font = max(int(practice.rule("drawing.min_text_px")),
               int(practice.rule("drawing.label_text_px")))
    tap = int(practice.rule("drawing.tap_target_px"))
    peak = yard.regional("wildlife.monarch_peak") or {}
    peak = (peak.get("peak") if isinstance(peak, dict) else peak) or []
    buttons, sheets = [], []
    for i, bed in enumerate(beds):
        on = " on" if i == 0 else ""
        n = len(bed.get("plants") or [])
        buttons.append(
            f"<button type=button class='tab{on}' data-bed='{_esc(bed['id'])}'>"
            f"{_esc(bed['id'])} <span>{n}</span></button>")
        flag = "" if i == 0 else " hidden"
        sheets.append(
            f"<section class=sheet data-bed='{_esc(bed['id'])}'{flag}>"
            f"<p class=why>{_esc(bed.get('why') or '')}</p>"
            f"<div class=scroller>{_svg(bed, code_of, font, tap)}</div>"
            f"{_strip(bed, yard)}{_schedule(bed, code_of)}</section>")
    stamp_html = ""
    if stamp:
        stamp_html = (f"<p class=stamp>{_esc(stamp)}. Picks here change the "
                      f"copy, not the garden.</p>")
    months = "".join(
        f"<button type=button class=month data-month='{m}'>{m}</button>"
        for m in MONTHS)
    body = (_PAGE
            .replace("__TITLE__", TITLE)
            .replace("__STAMP__", stamp_html)
            .replace("__MONTHS__", months)
            .replace("__TABS__", "".join(buttons))
            .replace("__SHEETS__", "".join(sheets))
            .replace("__FONT__", str(font))
            .replace("__TAP__", str(tap))
            .replace("__TOKEN__", json.dumps(token))
            .replace("__PEAK__", json.dumps(peak))
            .replace("__LEAF__", LEAF_FILL)
            .replace("__EVER__", EVERGREEN_FILL)
            .replace("__DORMANT__", DORMANT_FILL)
            .replace("__WHITE_TILE__", WHITE_BLOOM_TILE))
    return body


_PAGE = """<!doctype html>
<html lang=en><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>__TITLE__</title>
<style>
body{font:16px/1.45 system-ui,sans-serif;margin:0 auto;padding:1rem;
max-width:72rem;color:#1c1c17;background:#fbfaf6}
h1{font-size:1.35rem;margin:0 0 .3rem}
.lede,.why,.stripnote,.key{color:#4f4f45;font-size:.92rem}
.stamp{background:#8a3b12;color:#fff;padding:.5rem .7rem;border-radius:6px}
.bar-top{position:sticky;top:0;z-index:3;background:#fbfaf6;padding:.4rem 0;
border-bottom:1px solid #e4e0d4}
.months{display:flex;gap:.25rem;overflow-x:auto;scroll-snap-type:x mandatory;
padding-bottom:.2rem}
.month{flex:0 0 auto;min-width:48px;min-height:44px;font:inherit;
border:1px solid #b9c3aa;background:#fff;border-radius:8px;cursor:pointer;
scroll-snap-align:start}
.month.on{background:#2f5d1e;color:#fff;border-color:#2f5d1e;font-weight:700}
.controls{display:flex;gap:.5rem;align-items:center;margin-top:.35rem}
#play{min-height:44px;min-width:64px;font:inherit;border:1px solid #6b5b45;
background:#fff;border-radius:8px;cursor:pointer}
#summary{margin:0;font-size:.95rem}
.tabs{display:flex;gap:.4rem;margin:.8rem 0;flex-wrap:wrap}
.tab{font:inherit;min-height:44px;border:1px solid #b9c3aa;background:#fff;
border-radius:99px;padding:.35rem .9rem;cursor:pointer}
.tab.on{background:#2f5d1e;color:#fff;border-color:#2f5d1e}
.tab span{opacity:.8}
.scroller{overflow-x:auto;border:1px solid #e4e0d4;border-radius:10px;background:#f3efe4}
svg.bed{display:block}
.soil{fill:#f6f1e4;stroke:#2e261b;stroke-width:3.5}
.band.sown{fill:#d5dec4;stroke:none}
.band.stone{stroke:#8a8275;stroke-width:.8}
.bandlabel,.edge{fill:#3d3a33;font-size:__FONT__px}
.bandlabel{font-weight:600;paint-order:stroke;stroke:#fbfaf6;stroke-width:3.5px}
.plant{cursor:pointer}
.plant circle.hit{fill:transparent;stroke:none}
.plant circle.solid{stroke:#2e261b;stroke-width:2.4;fill-opacity:.85}
.plant.kept circle.solid,.plant.locked circle.solid{stroke-width:1.2}
.bubble-edge circle{fill:none;stroke:#2e261b;stroke-width:1.2}
.bubble-fill circle{fill:#f6f1e4;stroke:none}
.plant .evering{fill:none;stroke:#fff;stroke-width:1.4;display:none;pointer-events:none}
.plant.m-ever .evering{display:inline}
.plant.locked{cursor:default}
body:not(.show-mature) .plant circle.mature{display:none}
.plant circle.mature{fill:none;stroke:#4a3f30;stroke-width:.9;stroke-dasharray:1 2.5;pointer-events:none}
.labels text{pointer-events:none}
.labels .code{fill:#1c1c17;font-size:__FONT__px;font-weight:700;pointer-events:none;
paint-order:stroke;stroke:#fbfaf6;stroke-width:3px}
.tuft{stroke:#2e261b;stroke-width:1.2;pointer-events:none}
.nectar{fill:#1c1c17;stroke:#fff;stroke-width:1;pointer-events:none}
.leaf{fill:#2f5d1e;stroke:#fff;stroke-width:1;pointer-events:none}
.plant.m-leaf .nectar,.plant.m-ever .nectar{display:none}
.fruit{display:none;pointer-events:none}
.fruit circle{stroke:#1c1c17;stroke-width:1.2}
.fruit circle.halo{fill:#fff;stroke:none}
.plant.m-fruit .fruit{display:inline}
.plant.m-dormant{opacity:.7}
.plant.m-dormant circle.solid{fill-opacity:.55;stroke-dasharray:4 3}
.plant.m-dormant .nectar,.plant.m-dormant .tuft{display:none}
.plant.on circle.solid{stroke:#000;stroke-width:4}
.leader{stroke:#4a3f30;stroke-width:.8}
.tag rect{fill:#fff;stroke:#4a3f30;stroke-width:1}
.tag text{fill:#1c1c17;font-size:__FONT__px;font-weight:700}
.strip{display:grid;grid-template-columns:repeat(12,minmax(44px,1fr));gap:3px;
margin:.6rem 0 .2rem;overflow-x:auto}
.cell{position:relative;min-height:64px;font:inherit;font-size:.8rem;
border:1px solid #d4cfbf;background:#fff;border-radius:6px;cursor:pointer;
display:flex;flex-direction:column;align-items:center;justify-content:flex-end;padding:2px}
.cell .bar{display:block;width:60%;background:#c98a2b;border-radius:2px}
.cell b{font-size:.8rem}
.cell i{font-style:normal;color:#4f4f45}
.cell em{position:absolute;top:2px;right:4px;font-style:normal;font-size:.7rem;color:#2f5d1e;font-weight:700}
.cell.gap{border:2px solid #b3261e}
.cell.on{outline:3px solid #2f5d1e;outline-offset:1px}
.schedule{border-collapse:collapse;margin:.6rem 0;font-size:.85rem;display:block;overflow-x:auto}
.schedule tr[data-for]{cursor:pointer}
.schedule tr[data-for]:hover,.schedule tr[data-for]:focus{background:#eef3e6}
.schedule th,.schedule td{border-bottom:1px solid #e4e0d4;text-align:left;padding:.25rem .5rem;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:.3rem 1rem;font-size:.85rem;color:#4f4f45;margin:.4rem 0}
.legend svg{vertical-align:middle}
.panel{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;
padding:.8rem;max-height:48vh;overflow:auto;margin:0 -1rem -1rem;z-index:4}
.opt{display:flex;gap:.6rem;align-items:center;width:100%;min-height:44px;text-align:left;
font:inherit;border:1px solid #ddd;background:#fff;border-radius:8px;
padding:.35rem;margin:.35rem 0;cursor:pointer}
.opt img,.opt .swatch{width:64px;height:64px;object-fit:cover;border-radius:6px;flex:none}
.opt .swatch{display:block;border:1px solid #2e261b}
.opt.now{cursor:default;border:2px solid #2f5d1e;background:#eef3e6}
.opt b{display:block}
.opt i,.opt small{display:block;color:#4f4f45;font-size:.8rem}
.opt.tall{background:#f6f3ec;border-style:dashed}
.opt .taller{display:block;color:#7a3e00;font-size:.8rem;font-weight:600}
#close,#undo{min-height:44px;min-width:44px;float:right;font:inherit;border:1px solid #ddd;background:#fff;border-radius:8px}
#undo{margin-right:.4rem;padding:0 .8rem}
.saved{background:#e6efdc;padding:.4rem .6rem;border-radius:6px}
[hidden]{display:none !important}
</style></head><body>
__STAMP__
<h1>__TITLE__</h1>
<p class=lede>Pick a month to see what is in flower. Tap a plant to see what else fits that spot.</p>
<div class=bar-top>
<div class=months role=group aria-label=Month>__MONTHS__</div>
<div class=controls><button type=button id=play>Play</button><p id=summary aria-live=polite></p></div>
</div>
<div class=legend>
<span><svg width=26 height=26><circle cx=13 cy=13 r=10 fill='#e27aa6' stroke='#2e261b' stroke-width=2.4></circle><circle cx=19 cy=7 r=3.5 fill='#1c1c17' stroke='#fff'></circle></svg> in flower, dot gives nectar</span>
<span><svg width=26 height=26><defs><pattern id=white-bloom-key width=12 height=12 patternUnits=userSpaceOnUse>__WHITE_TILE__</pattern></defs><circle cx=13 cy=13 r=10 fill='url(#white-bloom-key)' stroke='#2e261b' stroke-width=1.6></circle></svg> white flowers</span>
<span><svg width=26 height=26><circle cx=13 cy=13 r=10 fill='__LEAF__' stroke='#2e261b' stroke-width=1.6></circle><circle cx=14.5 cy=19 r=4.6 fill='#fff'></circle><circle cx=21.5 cy=19 r=4.6 fill='#fff'></circle><circle cx=18 cy=13.5 r=4.6 fill='#fff'></circle><circle cx=14.5 cy=19 r=3.4 fill='#D55E00' stroke='#1c1c17' stroke-width=1></circle><circle cx=21.5 cy=19 r=3.4 fill='#D55E00' stroke='#1c1c17' stroke-width=1></circle><circle cx=18 cy=13.5 r=3.4 fill='#D55E00' stroke='#1c1c17' stroke-width=1></circle></svg> colorful fruit, in its color</span>
<span><svg width=26 height=26><circle cx=13 cy=13 r=10 fill='__LEAF__' stroke='#2e261b' stroke-width=1.6></circle></svg> green, not in flower</span>
<span><svg width=26 height=26><circle cx=13 cy=13 r=10 fill='__EVER__' stroke='#2e261b' stroke-width=1.6></circle><circle cx=13 cy=13 r=6 fill=none stroke='#fff' stroke-width=1.4></circle></svg> evergreen structure</span>
<span><svg width=26 height=26 opacity=.7><circle cx=13 cy=13 r=10 fill='__DORMANT__' fill-opacity=.55 stroke='#2e261b' stroke-width=1.6 stroke-dasharray='4 3'></circle></svg> dormant, died back</span>
<span><svg width=26 height=26><path d='M8,16 Q13,6 18,10 Q13,20 8,16Z' fill='#2f5d1e'></path></svg> larval host</span>
<span><svg width=26 height=26><circle cx=13 cy=13 r=10 fill='none' stroke='#2e261b' stroke-width=1.2></circle></svg> in the plan now (thin line)</span>
<span><svg width=26 height=26><circle cx=13 cy=13 r=10 fill='none' stroke='#2e261b' stroke-width=2.4></circle></svg> new (thick line)</span>
<label><input type=checkbox id=mature-toggle><svg width=26 height=26><circle cx=13 cy=13 r=11 fill='none' stroke='#4a3f30' stroke-width=.9 stroke-dasharray='1 2.5'></circle></svg> show mature width</label>
</div>
<div class=tabs>__TABS__</div>
__SHEETS__
<p class=key>A circle is drawn at its planting distance, so the circles touch. Every circle is one plant and carries its code. One outline marks each new drift. The schedule gives the count of each plant. Press Ctrl+Z or Cmd+Z to undo the last change. The code is in the schedule. Tap a schedule row to reach a plant that is too small to tap.</p>
<div class=panel id=panel hidden>
<button type=button id=close aria-label=Close>X</button>
<button type=button id=undo hidden title='Undo the last change to this plant (Ctrl+Z or Cmd+Z)'>Undo</button>
<p id=status></p>
<div id=list></div>
</div>
<script>
const token = __TOKEN__;
const PEAK = __PEAK__;
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const panel = document.getElementById('panel');
const list = document.getElementById('list');
const status = document.getElementById('status');
const undoBtn = document.getElementById('undo');
const summary = document.getElementById('summary');
let current = null;
let month = MONTHS[new Date().getMonth()];
let bed = null;
let timer = null;

function look(group, m) {
  const has = key => (group.dataset[key] || '').split(' ').includes(m);
  const circle = group.querySelector('circle.solid');
  group.classList.remove('m-bloom', 'm-leaf', 'm-ever', 'm-dormant');
  group.classList.toggle('m-fruit', has('fruit'));
  if (has('bloom')) {
    group.classList.add('m-bloom');
    const white = group.dataset.flower.toUpperCase() === '#FFFFFF';
    circle.setAttribute('fill', white
      ? 'url(#white-bloom-' + group.closest('svg').dataset.bed + ')' : group.dataset.flower);
    return 'bloom';
  }
  if (group.dataset.ever === '1') {
    group.classList.add('m-ever');
    circle.setAttribute('fill', '__EVER__');
    return 'ever';
  }
  if (has('leaf')) {
    group.classList.add('m-leaf');
    circle.setAttribute('fill', '__LEAF__');
    return 'leaf';
  }
  group.classList.add('m-dormant');
  circle.setAttribute('fill', '__DORMANT__');
  return 'dormant';
}

function setMonth(m) {
  month = m;
  document.querySelectorAll('.month').forEach(b => b.classList.toggle('on', b.dataset.month === m));
  document.querySelectorAll('.cell').forEach(c => c.classList.toggle('on', c.dataset.month === m));
  let flower = 0, nectar = 0, fruit = 0;
  const hosts = new Set();
  document.querySelectorAll('.plant').forEach(g => {
    const state = look(g, m);
    if (g.closest('.sheet').dataset.bed !== bed) return;
    if (state === 'bloom') {
      flower += 1;
      if (g.dataset.nectar === '1') nectar += 1;
    }
    if (g.classList.contains('m-fruit')) fruit += 1;
    if (g.classList.contains('host')) hosts.add(g.dataset.name);
  });
  const names = {Jan:'January',Feb:'February',Mar:'March',Apr:'April',May:'May',Jun:'June',
    Jul:'July',Aug:'August',Sep:'September',Oct:'October',Nov:'November',Dec:'December'};
  let text = names[m] + ' in ' + bed + '. ' + flower + ' plants in flower, ' + nectar +
    ' give nectar, ' + (fruit ? fruit + ' in fruit, ' : '') +
    hosts.size + ' host plant' + (hosts.size === 1 ? '' : 's') + '.';
  if (PEAK.includes(m)) text += ' The monarch migration peaks this month.';
  summary.textContent = text;
  save();
}

function showBed(id) {
  bed = id;
  document.querySelectorAll('.tab').forEach(el => el.classList.toggle('on', el.dataset.bed === id));
  document.querySelectorAll('.sheet').forEach(el => { el.hidden = el.dataset.bed !== id; });
  closePanel();
  setMonth(month);
}

function save(extra) {
  const parts = [bed, month];
  if (extra) parts.push(extra);
  history.replaceState(null, '', '#' + parts.join('/'));
}

document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => showBed(btn.dataset.bed)));
document.querySelectorAll('.month,.cell').forEach(btn => btn.addEventListener('click', () => {
  stop();
  setMonth(btn.dataset.month);
}));

function stop() {
  if (timer) clearInterval(timer);
  timer = null;
  document.getElementById('play').textContent = 'Play';
}
document.getElementById('play').addEventListener('click', () => {
  if (timer) return stop();
  let i = 0;
  document.getElementById('play').textContent = 'Stop';
  setMonth(MONTHS[i]);
  timer = setInterval(() => {
    i += 1;
    if (i >= MONTHS.length) return stop();
    setMonth(MONTHS[i]);
  }, 1000);
});

function closePanel() {
  panel.hidden = true;
  current = null;
  document.querySelectorAll('.plant.on').forEach(el => el.classList.remove('on'));
}
document.getElementById('close').addEventListener('click', closePanel);

function card(opt, tag, prefix) {
  const el = document.createElement(tag);
  el.className = 'opt';
  if (tag === 'button') el.type = 'button';
  if (opt.photo) {
    const img = document.createElement('img');
    img.alt = '';
    img.src = opt.photo;
    el.appendChild(img);
  } else {
    const swatch = document.createElement('span');
    swatch.className = 'swatch';
    swatch.style.background = opt.color || '__LEAF__';
    el.appendChild(swatch);
  }
  const span = document.createElement('span');
  const title = document.createElement('b');
  title.textContent = (prefix || '') + opt.name;
  const meta = document.createElement('i');
  const wild = [];
  if (opt.host && opt.host.length) wild.push('host for ' + opt.host.join(', '));
  if (opt.nectar) wild.push('nectar');
  if (opt.fruit_for && opt.fruit_for.length) wild.push('fruit for ' + opt.fruit_for.join(', '));
  if (opt.seed_for && opt.seed_for.length) wild.push('seed for ' + opt.seed_for.join(', '));
  meta.textContent = opt.botanical + ' · ' + (opt.tall_ft ? opt.tall_ft + ' ft tall, ' : '') +
    opt.grows_ft + ' ft wide' + (opt.bloom.length ? ' · flowers ' + opt.bloom.join(' ') : '') +
    (opt.fruit && opt.fruit.length ? ' · ' + (opt.fruit_what || 'fruit') + ' ' + opt.fruit.join(' ') : '') +
    (wild.length ? ' · ' + wild.join(', ') : '');
  const note = document.createElement('small');
  note.textContent = opt.note || opt.attribution || '';
  span.append(title, meta);
  if (opt.taller_than) {
    el.classList.add('tall');
    const warn = document.createElement('span');
    warn.className = 'taller';
    warn.textContent = 'Taller than ' + opt.taller_than.name + ' behind it: ' +
      opt.tall_ft + ' ft against ' + opt.taller_than.tall_ft + ' ft.';
    span.appendChild(warn);
  }
  span.appendChild(note);
  el.appendChild(span);
  return el;
}

async function openPlant(group, done) {
  document.querySelectorAll('.plant.on').forEach(el => el.classList.remove('on'));
  group.classList.add('on');
  current = group.dataset.id;
  panel.hidden = false;
  list.replaceChildren();
  undoBtn.hidden = true;
  status.className = '';
  const label = group.dataset.name + ' (' + group.dataset.code + ')';
  const locked = group.dataset.locked === '1';
  if (locked) status.textContent = label + ' stays. It is already in the ground.';
  else if (done) status.textContent = done;
  else status.textContent = 'Choices for ' + label + '.';
  if (done) status.className = 'saved';
  const res = await fetch('/' + token + '/options/' + current);
  const data = await res.json();
  if (current !== group.dataset.id) return;
  if (data.current) {
    const now = card(data.current, 'div', 'Now: ');
    now.classList.add('now');
    now.setAttribute('aria-current', 'true');
    list.appendChild(now);
  }
  undoBtn.hidden = !(data.undo && data.undo.plant);
  if (locked) return;
  if (!data.options || !data.options.length) {
    if (!done) status.textContent = data.why || 'No other plant on this list fits this spot.';
    return;
  }
  data.options.forEach(opt => {
    const btn = card(opt, 'button');
    btn.addEventListener('click', () => saveSwap(group, opt.name));
    list.appendChild(btn);
  });
}

async function undoSwap(id) {
  const res = await fetch('/' + token + '/undo', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(id ? {id: id} : {})
  });
  const data = await res.json();
  if (!res.ok) {
    panel.hidden = false;
    status.className = '';
    status.textContent = data.error || 'There is no change to undo.';
    return;
  }
  const group = document.querySelector('.plant[data-id="' + data.plant.id + '"]');
  if (group) bed = group.closest('.sheet').dataset.bed;
  save('back:' + data.plant.id + ':' + encodeURIComponent(data.plant.name));
  location.reload();
}

undoBtn.addEventListener('click', () => undoSwap(current));
document.addEventListener('keydown', e => {
  if (e.key.toLowerCase() !== 'z' || !(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey) return;
  const el = document.activeElement;
  if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return;
  e.preventDefault();
  undoSwap(current);
});

async function saveSwap(group, name) {
  status.className = '';
  status.textContent = 'Saving ' + name + '.';
  const res = await fetch('/' + token + '/swap', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: group.dataset.id, name: name})
  });
  const data = await res.json();
  if (!res.ok) {
    status.textContent = data.error || 'That plant does not fit this gap.';
    return;
  }
  save('saved:' + group.dataset.id + ':' + encodeURIComponent(data.plant.name));
  location.reload();
}

document.querySelectorAll('.plant').forEach(group => group.addEventListener('click', () => openPlant(group)));
document.getElementById('mature-toggle').addEventListener('change', e =>
  document.body.classList.toggle('show-mature', e.target.checked));
document.querySelectorAll('.schedule tr[data-for]').forEach(row => row.addEventListener('click', () => {
  const group = document.querySelector('.plant[data-id="' + row.dataset.for + '"]');
  if (group) openPlant(group);
}));
document.querySelectorAll('.tag').forEach(tag => tag.addEventListener('click', () => {
  const group = document.querySelector('.plant[data-id="' + tag.dataset.for + '"]');
  if (group) openPlant(group);
}));

(function start() {
  const parts = decodeURIComponent(location.hash.slice(1)).split('/');
  const first = document.querySelector('.tab');
  const known = id => document.querySelector('.tab[data-bed="' + id + '"]');
  if (parts[1] && MONTHS.includes(parts[1])) month = parts[1];
  showBed(parts[0] && known(parts[0]) ? parts[0] : first.dataset.bed);
  if (parts[2] && (parts[2].startsWith('saved:') || parts[2].startsWith('back:'))) {
    const bits = parts[2].split(':');
    const group = document.querySelector('.plant[data-id="' + bits[1] + '"]');
    const name = bits.slice(2).join(':');
    if (group) openPlant(group, (bits[0] === 'back' ? 'Put back ' : 'Saved ') + name + '.');
  }
})();
</script>
</body></html>"""


def serve(slug, port=8740, host="0.0.0.0"):
    """One page, on the LAN, behind a random token in the path."""
    import secrets
    import socket
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    if not load(slug):
        raise SystemExit(f"{slug} has no {FILE}. Run --init first.")
    token = secrets.token_urlsafe(9)
    stamp = yards.sandbox_stamp(slug)

    class H(BaseHTTPRequestHandler):
        def _send(self, body, code=200, ctype="text/html; charset=utf-8"):
            raw = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _json(self, payload, code=200):
            self._send(json.dumps(payload), code, "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/" + token:
                return self._send(page(load(slug), token, stamp, Yard(slug)))
            prefix = f"/{token}/options/"
            if path.startswith(prefix):
                scheme = load(slug)
                plant_id = path[len(prefix):]
                yard = Yard(slug)
                opts, err = options_for(slug, scheme, plant_id, yard)
                if err and opts is None:
                    return self._json({"error": err}, 404)
                return self._json({"options": opts or [], "why": err or "",
                                   "current": current_for(scheme, plant_id, yard),
                                   "undo": _undo_count(scheme, plant_id)})
            self._send("Not found", 404, "text/plain")

        def do_POST(self):
            path = self.path.split("?", 1)[0].rstrip("/")
            if path not in (f"/{token}/swap", f"/{token}/undo"):
                return self._send("Not found", 404, "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n).decode() or "{}")
            except json.JSONDecodeError:
                return self._json({"error": "The change was not readable."}, 400)
            if path.endswith("/undo"):
                plant, err = undo(slug, body.get("id") or None)
            else:
                plant, err = swap(slug, body.get("id") or "", body.get("name") or "")
            if err:
                return self._json({"error": err}, 409)
            self._json({"plant": plant})

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "localhost"
    return srv, f"http://{ip}:{port}/{token}"


def main():
    ap = argparse.ArgumentParser(description="A bed map you can edit one plant at a time.")
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true",
                    help="write the suggested planting")
    ap.add_argument("--force", action="store_true",
                    help="replace an existing map")
    ap.add_argument("--check", action="store_true",
                    help="report overlaps and plants that do not fit")
    ap.add_argument("--review", action="store_true",
                    help="check the map against practice/")
    ap.add_argument("--html", metavar="PATH",
                    help="write the page to a file, for a browser test")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8740)
    args = ap.parse_args()

    if args.init:
        existing = load(args.slug)
        if existing and not args.force:
            raise SystemExit(
                f"{args.slug} already has {FILE}. --force replaces it, "
                f"including any swaps already saved.")
        scheme = suggest(args.slug)
        bad = audit(args.slug, scheme)
        if bad:
            for line in bad:
                print(f"  {line}")
            raise SystemExit(
                f"the suggestion has {len(bad)} problem"
                f"{'' if len(bad) == 1 else 's'}. Nothing was written.")
        yards.save(args.slug, FILE, scheme)
        n = sum(len(b["plants"]) for b in scheme["beds"])
        print(f"  wrote {FILE}: {len(scheme['beds'])} beds, {n} plants")
        return

    if args.check:
        if not load(args.slug):
            raise SystemExit(f"{args.slug} has no {FILE}.")
        bad = audit(args.slug)
        if not bad:
            print("  every plant sits in its bed, and every open circle fits")
            return
        for line in bad:
            print(f"  {line}")
        raise SystemExit(f"  {len(bad)} problem{'' if len(bad) == 1 else 's'}")

    if args.review:
        if not load(args.slug):
            raise SystemExit(f"{args.slug} has no {FILE}.")
        found = review(args.slug)
        real = [f for f in found if not f.get("info")]
        for f in found:
            mark = "  info" if f.get("info") else "  find"
            print(f"{mark}  {f['bed']:5} {f['text']}")
            print(f"              {f['cite']}")
        print(f"  {len(real)} finding{'' if len(real) == 1 else 's'}")
        return

    if args.html:
        html = page(load(args.slug), "local", yards.sandbox_stamp(args.slug),
                    Yard(args.slug))
        with open(args.html, "w") as fh:
            fh.write(html)
        print(f"  wrote {args.html}")
        return

    if args.serve:
        srv, url = serve(args.slug, port=args.port)
        print(f"  open this on a phone on the same wifi:\n\n    {url}\n")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
        return

    scheme = load(args.slug)
    if not scheme:
        raise SystemExit(
            f"{args.slug} has no {FILE}.\n"
            f"  python3 -m lib.scheme {args.slug} --init")
    for bed in scheme["beds"]:
        print(f"  {bed['id']:4}  {len(bed['plants']):3} plants  {bed.get('why')}")


if __name__ == "__main__":
    main()
