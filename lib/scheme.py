#!/usr/bin/env python3
"""A placed planting you can change one plant at a time.

    python3 -m lib.scheme <slug> --init     write the suggested map
    python3 -m lib.scheme <slug> --check    report overlaps and plants that do not fit
    python3 -m lib.scheme <slug> --serve    open the map on a phone

The map is the choosing. It does not write design.json, and it does not run
the design or the bed drawings. Those stay gated until the choice cards close.

Ornamental beds only. Each circle is one plant. Tap it, then tap a replacement.
The replacement has to fit the light, the soil, the depth, and the gap.
"""

import argparse
import json
import math
import os
import sys

from . import niches, yards

FILE = "scheme.json"
# Circles may kiss. A few hundredths of a foot is the float, not a real overlap.
TOUCH = 0.03
# Plants may stand closer than their full width. The extra ones come out
# as the bed matures.
PACK = 0.85
DRAW_MAX = 1.6
SCALE = 86  # px per foot. Small bulbs stay large enough to tap.


# Flower or leaf colour, so the map reads as a planting and not as grey dots.
PALETTE = {
    "Zinnia": "#e07a3d",
    "Gayfeather": "#7d5ea8",
    "Prairie phlox": "#e48ab0",
    "Bat-face cuphea": "#6b2d5b",
    "Four-nerve daisy": "#e6c84a",
    "Oxblood lily": "#7a1e2c",
    "Society garlic": "#c9a0d4",
    "Viola": "#5c4d8a",
    "Evening rain lily": "#f4f1e8",
    "Cedar sedge": "#6e8f62",
    "Texas sedge": "#8aa56e",
    "Cedar sage": "#c23b4a",
    "Holly fern": "#1f6b45",
    "Leopard plant": "#8a9a3a",
    "Chile pequin": "#b8332a",
    "Pigeonberry": "#d4537e",
    "Heartleaf skullcap": "#7a8fbf",
    "Pink skullcap": "#e59ab8",
    "Hinckley's columbine": "#e7b3c8",
    "Hosta": "#6f8f5a",
    "Inland sea oats": "#c4a15a",
    "Meadow sedge": "#8fa36a",
    "Tropical sage": "#d64545",
    "Basil": "#3f7d4e",
    "Bulbine": "#e6b84d",
    "Chocolate daisy": "#c48a3a",
    "Purple coneflower": "#c46aa0",
    "Mealy blue sage": "#6a8cc4",
    "Gregg's mistflower": "#9b7ec8",
    "Giant spiderwort": "#6a5acd",
    "Wild petunia": "#c9a0d8",
    "Snake herb": "#eceae4",
    "Chives": "#7d9a62",
    "Parsley": "#3f7d4e",
    "Oregano": "#6e8f55",
    "Fennel": "#d6de6a",
    "Snapdragon": "#e07aa8",
    "Mexican mint marigold": "#e6c84a",
    "Engelmann daisy": "#f0d24a",
    "Square-bud primrose": "#f2e27a",
    "Mexican feathergrass": "#c6b56a",
    "Gulf muhly": "#e7a0b8",
    "Milkweed": "#e07a3d",
    "Damianita": "#e6d15a",
    "Blackfoot daisy": "#f7f4ea",
    "Tropical sage": "#d64545",
    "Rosemary": "#3f6b45",
    "Mexican mint marigold": "#e6c84a",
    "White mistflower": "#f4f1ea",
    "Turk's cap": "#c23b4a",
    "Inland sea oats": "#c4a15a",
    "Sweet alyssum": "#f4f1ea",
    "Bluebonnet": "#6a8cc4",
    "Cyclamen": "#d46a9a",
    "Frog": "#7eb8c9",
    "Pale-leaf yucca": "#d5dcc8",
    "Royal Gold rose": "#e0a020",
    "Westerland rose": "#e08a3c",
    "Lindheimer's senna": "#e2c15a",
    "Pride of Barbados": "#e85d04",
}


def color_for(name):
    return PALETTE.get(name, "#8aa37b")


def _radius(plant):
    return float(plant["spread_ft"]) / 2.0


def _dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def overlaps(a, b):
    """True when two solid circles cross.

    A planting plan draws circles that touch. They do not stack.
    """
    return _dist(a, b) + TOUCH < _radius(a) + _radius(b)


def in_bed(bed, plant):
    """True when the circle sits in plantable soil.

    A locked plant may lean onto the wall. It is already there. A new plant
    may not. On g02 the front half-foot is the bluebonnet strip, and a new
    circle may not enter it.
    """
    r = _radius(plant)
    length = float(bed["length_ft"])
    depth = float(bed["depth_ft"])
    # The east gulf muhly is drawn past the measured end of the soil.
    # A rose on a trellis is drawn above the soil. Both stay.
    stay = plant.get("locked") or plant.get("kept")
    end_slop = 0.5 if stay else 0.02
    back_slop = float(bed.get("above_ft") or 0) + (0.15 if stay else 0.02)
    if plant["x"] - r < -0.02 or plant["x"] + r > length + end_slop:
        return False
    if plant["y"] - r < -0.02 or plant["y"] + r > depth + back_slop:
        return False
    band = bed.get("keep_out")
    if band and not stay:
        if plant["y"] - r < float(band["y_below"]) - 0.001:
            return False
    return True


def _niche_by_id(data):
    return {n["id"]: n for n in data.get("niches") or []}


def _candidates(niche):
    """One record per name. The same plant on two rows is still one plant."""
    out = {}
    for slot in niches._slots(niche):
        for cand in slot.get("candidates") or []:
            out.setdefault(cand["name"], cand)
    return out


def _swap_slot():
    """A slot with no row budget.

    The row budget asks whether a whole row of this plant would fit. A swap
    is one circle. Light, depth, pH and drainage still apply. The gap check
    does the rest.
    """
    return {"id": "swap", "count": [1, 1]}


def rejection(slug, niche, cand, site=None, sun=None, cond=None):
    """Why this plant cannot go in this niche, or None when it can."""
    site = yards.load_site(slug) if site is None else site
    sun = yards.load(slug, "sun-hours.json") or {} if sun is None else sun
    cond = yards.load_conditions(slug) if cond is None else cond
    return niches._rejects(dict(cand), niche, _swap_slot(), site, sun, cond)


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
        if overlaps(trial, other):
            return False
    return True


def _draw_spread(mature):
    """Width drawn on the map. A wide shrub is drawn smaller so more fit."""
    return round(min(float(mature), DRAW_MAX), 3)


def _look(name, botanical, spread):
    """Mature width and habit from the catalog, when the record matches."""
    from . import design as design_mod
    record = design_mod._match_record(
        {"name": name, "botanical": botanical}) or {}
    mature = record.get("mature_spread_ft") or spread
    return round(float(mature), 3), record.get("habit") or ""


def _plant(bed_id, niche_id, name, botanical, spread, x, y, locked=False,
           kept=False, mature=None, habit=""):
    return {
        "id": f"{bed_id}-{x:.2f}-{y:.2f}",
        "name": name,
        "botanical": botanical or "",
        "x": round(float(x), 3),
        "y": round(float(y), 3),
        "spread_ft": round(float(spread), 3),
        "mature_spread_ft": round(float(mature if mature is not None else spread), 3),
        "habit": habit or "",
        "locked": bool(locked),
        "kept": bool(kept),
        "niche": niche_id,
        "color": color_for(name),
    }


def _touch(plants):
    """Shrink solid circles until they touch. The centers stay."""
    for _ in range(12):
        changed = False
        for i, left in enumerate(plants):
            for right in plants[i + 1:]:
                if not overlaps(left, right):
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


def _run(bed_id, niche_id, catalog, y, start, seq):
    """Lay plants in a row that touches, left to right.

    `seq` is (name, count) pairs. Spread comes from the slate.
    """
    out = []
    x = float(start)
    for name, count in seq:
        cand = catalog[name]
        spread = float(cand["mature_spread_ft"])
        r = spread / 2.0
        for _ in range(count):
            out.append(_plant(
                bed_id, niche_id, cand["name"], cand.get("botanical"),
                spread, x + r, y))
            x += spread
    return out


def _locked(bed_id, niche_id, name, botanical, spread, x, y):
    return _plant(bed_id, niche_id, name, botanical, spread, x, y, locked=True)


# The bed map already drawn. The key is the layout name. The value is the
# short name, the botanical name, and whether the plant stays put.
_GARDEN = {
    "Climbing Royal Gold (existing, east trellis)":
        ("Royal Gold rose", "Rosa 'Royal Gold'", True),
    "Pale-leaf yucca": ("Pale-leaf yucca", "Yucca pallida", True),
    "Cyclamen": ("Cyclamen", "Cyclamen", False),
    "Four-nerve daisy": ("Four-nerve daisy", "Tetraneuris scaposa", False),
    "Pansy and viola": ("Viola", "Viola", False),
    "Gulf muhly": ("Gulf muhly", "Muhlenbergia capillaris", True),
    "Milkweed - ASK FOR Asclepias tuberosa OR A. asperula BY NAME":
        ("Milkweed", "Asclepias tuberosa", False),
    "Mealy blue sage": ("Mealy blue sage", "Salvia farinacea", False),
    "Tropical sage": ("Tropical sage", "Salvia coccinea", False),
    "Damianita": ("Damianita", "Chrysactinia mexicana", False),
    "Blackfoot daisy": ("Blackfoot daisy", "Melampodium leucanthum", False),
    "Climbing Westerland (existing, west trellis, ft 19.2)":
        ("Westerland rose", "Rosa 'KORwest'", True),
    "FROG": ("Frog", "", True),
    "Bluebonnet (existing self-sown seed bank)":
        ("Bluebonnet", "Lupinus texensis", True),
    "Rosemary 'Tuscan Blue' (upright)": ("Rosemary", "Salvia rosmarinus", False),
    "Mexican mint marigold": ("Mexican mint marigold", "Tagetes lucida", False),
    "Lindheimer's senna (existing, ft 3.25-5.5)":
        ("Lindheimer's senna", "Senna lindheimeriana", True),
    "White mistflower": ("White mistflower", "Ageratina havanensis", False),
    "Turk's cap": ("Turk's cap", "Malvaviscus arboreus var. drummondii", False),
    "Inland sea oats": ("Inland sea oats", "Chasmanthium latifolium", False),
    "Viola": ("Viola", "Viola", False),
    "Sweet alyssum": ("Sweet alyssum", "Lobularia maritima", False),
    "Cedar sedge": ("Cedar sedge", "Carex planostachys", False),
    "Pride of Barbados (existing x3)":
        ("Pride of Barbados", "Caesalpinia pulcherrima", True),
    "Chile pequin": ("Chile pequin", "Capsicum annuum var. glabriusculum", False),
}

_LAYOUT = {
    "g01-southeast-corner": "g01",
    "g02-rear-wall": "g02",
    "g03-seating": "g03",
    "g04-west-wall": "g04",
    "g05-front": "g05",
}

# More plants than the mature bed can hold. They come out later.
_MORE = {
    "g01": ["Prairie phlox", "Society garlic", "Bat-face cuphea",
            "Oxblood lily", "Evening rain lily", "Gayfeather"],
    "g02": ["Mexican feathergrass", "Gregg's mistflower", "Purple coneflower",
            "Gayfeather", "Prairie phlox", "Chocolate daisy", "Oxblood lily",
            "Bat-face cuphea", "Society garlic", "Zinnia"],
    "g03": ["Holly fern", "Cedar sage", "Pigeonberry", "Heartleaf skullcap",
            "Basil", "Inland sea oats", "Tropical sage"],
    "g04": ["Prairie phlox", "Pink skullcap", "Bulbine", "Evening rain lily",
            "Zinnia", "Four-nerve daisy", "Cedar sage"],
    "g05": ["Pigeonberry", "Heartleaf skullcap", "Leopard plant",
            "Hinckley's columbine", "Inland sea oats", "Hosta",
            "Meadow sedge"],
}

_WHY = {
    "g01": ("The rose and the yucca stay. The flowers already here stay. "
            "More nectar plants fill the openings."),
    "g02": ("Gulf muhly, milkweed, and the sages stay. More nectar plants "
            "sit between them for butterflies. The lawn edge stays bare "
            "for bluebonnets."),
    "g03": ("The senna, mistflower, and Turk's cap stay. Shade plants for "
            "birds and hummingbirds fill the gaps."),
    "g04": ("Pride of Barbados stays. More flowers fill the bed."),
    "g05": ("Chile pequin stays for the birds. More shade plants fill "
            "the front."),
}


def _niche_of(bed_id, x):
    if bed_id == "g03":
        return "bed_g03-1" if x < 3 else "bed_g03-2"
    return "bed_" + bed_id


def _beds_from_garden(slug):
    """The planting already drawn, one circle per plant on that map."""
    design = yards.load(slug, "design.json") or {}
    found = {}
    for spec in (design.get("layout") or {}).get("beds") or []:
        bed_id = _LAYOUT.get(spec.get("name"))
        if not bed_id:
            continue
        plants = []
        extent_x = float(spec.get("length") or 0)
        extent_y = float(spec.get("depth") or 0)
        for src in spec.get("plants") or []:
            key = src.get("plant") or src.get("label") or ""
            name, botanical, locked = _GARDEN.get(key, (key, "", True))
            spread = round(float(src["r"]) * 2, 3)
            mature, habit = _look(name, botanical, spread)
            x, y = float(src["x"]), float(src["y"])
            extent_x = max(extent_x, x + spread / 2)
            extent_y = max(extent_y, y + spread / 2)
            plants.append(_plant(
                bed_id, _niche_of(bed_id, x), name, botanical, spread, x, y,
                locked=locked, kept=True, mature=mature, habit=habit))
        depth = float(spec.get("depth") or extent_y)
        found[bed_id] = {
            "id": bed_id,
            "length_ft": round(max(float(spec.get("length") or 0),
                                   extent_x + 0.08), 3),
            "depth_ft": round(depth, 3),
            "above_ft": round(max(0.0, extent_y - depth + 0.08), 3),
            "wall": "House wall",
            "front": "Front edge",
            "why": _WHY[bed_id],
            "plants": plants,
        }
    if "g02" in found:
        found["g02"]["front"] = "Bluebonnet edge. Do not plant here."
        found["g02"]["keep_out"] = {
            "y_below": 0.5,
            "label": "Bluebonnets. Leave this strip bare.",
        }
    return [found[k] for k in ("g01", "g02", "g03", "g04", "g05") if k in found]


# How wide an added plant is drawn. The real width stays on the choice list.
_PLACE = 1.0
# How many extra plants each bed takes. The rest come out as the bed matures.
_CAP = {"g01": 6, "g02": 22, "g03": 12, "g04": 8, "g05": 8}


def _wildlife_rank(cand):
    """A host comes first, then nectar. A color annual comes last.

    The slate copy may not carry the catalog fields. Read those from
    the catalog when the candidate does not have them.
    """
    from . import design as design_mod
    host = cand.get("host")
    if host is None:
        host = design_mod._field(cand, "host")
    nectar = cand.get("nectar")
    if nectar is None:
        nectar = design_mod._field(cand, "nectar")
    habit = cand.get("habit") or design_mod._field(cand, "habit")
    if host:
        return 0
    if habit == "annual":
        return 3
    if nectar is True:
        return 1
    return 2


def _add_more(slug, beds):
    """Add masses of one nectar or host plant. Do not mix the grid."""
    data = niches.load(slug)
    by_id = _niche_by_id(data)
    site = yards.load_site(slug)
    sun = yards.load(slug, "sun-hours.json") or {}
    cond = yards.load_conditions(slug)
    for bed in beds:
        wanted = list(_MORE.get(bed["id"]) or [])
        catalogs = {}
        ranked = []
        for name in wanted:
            for niche_id in { _niche_of(bed["id"], 0), _niche_of(bed["id"], 6) }:
                cat = catalogs.get(niche_id)
                if cat is None:
                    niche = by_id.get(niche_id)
                    cat = _candidates(niche) if niche else {}
                    catalogs[niche_id] = cat
                cand = cat.get(name)
                if cand:
                    ranked.append(( _wildlife_rank(cand), name, cand, niche_id))
                    break
        ranked.sort(key=lambda row: (row[0], row[1]))
        masses = 0
        for rank, name, cand, niche_id in ranked:
            if masses >= 2:
                break
            if rank >= 2:
                continue
            already = sum(1 for plant in bed["plants"] if plant["name"] == name)
            if already >= 3:
                continue
            niche = by_id.get(niche_id)
            if not niche or rejection(slug, niche, cand, site, sun, cond):
                continue
            spread = round(min(float(cand["mature_spread_ft"]), 1.5), 3)
            half = spread / 2
            y = half + 0.08
            band = bed.get("keep_out")
            if band:
                y = max(y, float(band["y_below"]) + half + 0.04)
            placed = False
            while y < float(bed["depth_ft"]) - half and not placed:
                x = half + 0.08
                row = []
                while x < float(bed["length_ft"]) - half and len(row) < 3:
                    here = _niche_of(bed["id"], x)
                    here_niche = by_id.get(here)
                    here_cand = (_candidates(here_niche).get(name)
                                 if here_niche else None)
                    if not here_cand or rejection(
                            slug, here_niche, here_cand, site, sun, cond):
                        x = round(x + spread, 2)
                        row = []
                        continue
                    mature, habit = _look(
                        cand["name"], cand.get("botanical"),
                        float(cand["mature_spread_ft"]))
                    plant = _plant(
                        bed["id"], here, cand["name"], cand.get("botanical"),
                        spread, x, y, mature=mature, habit=habit)
                    blocked = (not in_bed(bed, plant)
                               or any(overlaps(plant, other)
                                      for other in bed["plants"] + row))
                    if blocked:
                        x = round(x + 0.4, 2)
                        row = []
                        continue
                    row.append(plant)
                    x = round(x + spread, 2)
                if len(row) >= 2:
                    bed["plants"].extend(row)
                    masses += 1
                    placed = True
                y = round(y + 0.6, 2)


def suggest(slug):
    """The garden already drawn, plus masses of nectar and host plants."""
    beds = _beds_from_garden(slug)
    for bed in beds:
        _touch(bed["plants"])
    _add_more(slug, beds)
    for bed in beds:
        _touch(bed["plants"])
    # Stable ids. Coordinates stay in the record; the id does not change when
    # a plant is swapped, or a saved tap would point at nothing.
    for bed in beds:
        for i, plant in enumerate(bed["plants"], start=1):
            plant["id"] = f"{bed['id']}-{i:02d}"
    return {"beds": beds}


def audit(slug, scheme=None):
    """Overlaps, plants outside the soil, and swaps the slate would refuse."""
    scheme = scheme if scheme is not None else load(slug)
    data = niches.load(slug)
    niches_by = _niche_by_id(data)
    site = yards.load_site(slug)
    sun = yards.load(slug, "sun-hours.json") or {}
    cond = yards.load_conditions(slug)
    bad = []
    for bed in scheme.get("beds") or []:
        plants = bed.get("plants") or []
        for plant in plants:
            if not in_bed(bed, plant):
                bad.append(f"{plant['id']} {plant['name']} sits outside {bed['id']}")
            if not plant.get("botanical") and plant.get("name") != "Frog":
                bad.append(f"{plant['id']} {plant['name']} has no botanical name")
            if plant.get("locked") or plant.get("kept"):
                continue
            niche = niches_by.get(plant.get("niche"))
            cand = _candidates(niche).get(plant["name"]) if niche else None
            if cand is None:
                bad.append(f"{plant['id']} {plant['name']} is not on the slate "
                           f"for {plant.get('niche')}")
                continue
            why = rejection(slug, niche, cand, site, sun, cond)
            if why:
                bad.append(f"{plant['id']} {plant['name']}: {why}")
        for i, a in enumerate(plants):
            for b in plants[i + 1:]:
                if overlaps(a, b):
                    bad.append(f"{a['id']} {a['name']} overlaps {b['id']} {b['name']}")
    return bad


def load(slug):
    return yards.load(slug, FILE)


def find_plant(scheme, plant_id):
    for bed in scheme.get("beds") or []:
        for plant in bed.get("plants") or []:
            if plant["id"] == plant_id:
                return bed, plant
    return None, None


def options_for(slug, scheme, plant_id):
    """Plants that can replace this one circle. Locked circles have none."""
    bed, plant = find_plant(scheme, plant_id)
    if not bed or not plant:
        return None, "That plant is not on the map."
    if plant.get("locked"):
        return [], None
    data = niches.load(slug)
    niche = _niche_by_id(data).get(plant.get("niche"))
    if not niche:
        return [], "This spot has no plant list."
    site = yards.load_site(slug)
    sun = yards.load(slug, "sun-hours.json") or {}
    cond = yards.load_conditions(slug)
    out = []
    refused = []
    for cand in _candidates(niche).values():
        if cand["name"] == plant["name"]:
            continue
        why = rejection(slug, niche, cand, site, sun, cond)
        if why:
            refused.append(why)
            continue
        # Draw a wide plant at the size of this circle. The list says how
        # wide it grows. The bed is planted full, and some plants come out.
        hole = float(plant["spread_ft"])
        spread = round(min(_draw_spread(cand["mature_spread_ft"]), hole), 3)
        if not fits_gap(bed, plant, spread, bed["plants"]):
            continue
        photo = (cand.get("photos") or [None])[0] or {}
        out.append({
            "name": cand["name"],
            "botanical": cand.get("botanical") or "",
            "spread_ft": spread,
            "grows_ft": round(float(cand["mature_spread_ft"]), 2),
            "note": (cand.get("note") or "").split(". ")[0],
            "color": color_for(cand["name"]),
            "photo": photo.get("url") or "",
            "attribution": (photo.get("attribution") or "")[:80],
            "rank": _wildlife_rank(cand),
        })
    out.sort(key=lambda row: (row["rank"], row["name"].lower()))
    if not out:
        return [], _site_limit(refused)
    return out, None


def _site_limit(reasons):
    """The site fact that kept every other plant off the list."""
    blob = " ".join(reasons).lower()
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
    plant["name"] = picked["name"]
    plant["botanical"] = picked["botanical"]
    plant["spread_ft"] = picked["spread_ft"]
    plant["color"] = picked["color"]
    yards.save(slug, FILE, scheme)
    return plant, None


# ---------------------------------------------------------------- the page

TITLE = "The beds"


def _esc(text):
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _svg(bed):
    length = float(bed["length_ft"])
    depth = float(bed["depth_ft"])
    above = float(bed.get("above_ft") or 0)
    pad = 36
    gutter = 150
    width = int(length * SCALE + pad * 2 + gutter)
    height = int((depth + above) * SCALE + pad * 2)
    parts = [
        f"<svg class=bed data-bed='{_esc(bed['id'])}' width='{width}' "
        f"height='{height}' viewBox='0 0 {width} {height}' role='img'>"
    ]
    soil_top = pad + above * SCALE
    parts.append(
        f"<rect x='{pad}' y='{soil_top:.1f}' width='{length * SCALE:.1f}' "
        f"height='{depth * SCALE:.1f}' class=soil></rect>")
    band = bed.get("keep_out")
    if band:
        h = float(band["y_below"]) * SCALE
        y = soil_top + (depth - float(band["y_below"])) * SCALE
        parts.append(
            f"<rect x='{pad}' y='{y:.1f}' width='{length * SCALE:.1f}' "
            f"height='{h:.1f}' class=band></rect>")
        parts.append(
            f"<text class=bandlabel x='{pad + 8}' y='{y + h - 6:.1f}'>"
            f"{_esc(band.get('label') or '')}</text>")
    parts.append(
        f"<text class=edge x='{pad}' y='{soil_top - 10:.1f}'>"
        f"{_esc(bed.get('wall') or '')}</text>")
    parts.append(
        f"<text class=edge x='{pad}' y='{soil_top + depth * SCALE + 22:.1f}'>"
        f"{_esc(bed.get('front') or '')}</text>")
    for plant in bed.get("plants") or []:
        cx = pad + float(plant["x"]) * SCALE
        cy = pad + (above + depth - float(plant["y"])) * SCALE
        r = _radius(plant) * SCALE
        locked = " locked" if plant.get("locked") else ""
        drawn = max(r, 10)
        label = plant["name"] if drawn * 2 > len(plant["name"]) * 6.2 + 8 else ""
        mature = float(plant.get("mature_spread_ft") or plant["spread_ft"])
        ring = mature / 2 * SCALE
        covers = any(
            other is not plant and _dist(plant, other) < mature / 2
            for other in bed.get("plants") or [])
        parts.append(
            f"<g class='plant{locked}' data-id='{_esc(plant['id'])}' "
            f"data-name='{_esc(plant['name'])}' "
            f"data-locked='{'1' if plant.get('locked') else '0'}'>")
        color = plant.get("color") or "#8aa37b"
        parts.append(
            f"<circle class=solid cx='{cx:.1f}' cy='{cy:.1f}' r='{drawn:.1f}' "
            f"fill='{_esc(color)}' fill-opacity='0.4'></circle>")
        if not covers and ring > drawn + 4:
            parts.append(
                f"<circle class=mature cx='{cx:.1f}' cy='{cy:.1f}' "
                f"r='{ring:.1f}'></circle>")
        if plant.get("habit") == "grass":
            for dx in (-4, 0, 4):
                parts.append(
                    f"<line x1='{cx + dx:.1f}' y1='{cy - 6:.1f}' "
                    f"x2='{cx + dx:.1f}' y2='{cy + 6:.1f}' class=tuft></line>")
        parts.append(
            f"<text x='{cx:.1f}' y='{cy + 4:.1f}' text-anchor='middle'>"
            f"{_esc(label)}</text>")
        parts.append("</g>")
    slot = 0
    for group in _groups(bed.get("plants") or []):
        if len(group) < 2:
            continue
        sample = group[0]
        drawn = max(_radius(sample) * SCALE, 10)
        if drawn * 2 > len(sample["name"]) * 6.2 + 8:
            continue
        anchor = max(group, key=lambda item: item["x"])
        cx = pad + float(anchor["x"]) * SCALE
        cy = pad + (above + depth - float(anchor["y"])) * SCALE
        lx = pad + length * SCALE + 14
        ly = pad + 16 + slot * 16
        slot += 1
        count = len(group)
        parts.append(
            f"<line class=leader x1='{cx:.1f}' y1='{cy:.1f}' "
            f"x2='{lx:.1f}' y2='{ly:.1f}'></line>")
        parts.append(
            f"<text class=mass x='{lx + 4:.1f}' y='{ly + 4:.1f}'>"
            f"{count} {_esc(sample['name'])}</text>")
    parts.append("</svg>")
    return "\n".join(parts)


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


def _schedule(bed):
    """Count, botanical name, spacing, and mature width."""
    rows = []
    seen = {}
    for plant in bed.get("plants") or []:
        row = seen.get(plant["name"])
        if row is None:
            row = {"name": plant["name"],
                   "botanical": plant.get("botanical") or "",
                   "count": 0,
                   "spacing": plant.get("spread_ft") or 0,
                   "mature": plant.get("mature_spread_ft") or plant.get("spread_ft") or 0}
            seen[plant["name"]] = row
            rows.append(row)
        row["count"] += 1
    lines = ["<table class=schedule>",
             "<tr><th>Count</th><th>Plant</th><th>Botanical name</th>"
             "<th>Spacing</th><th>Mature width</th></tr>"]
    for row in rows:
        lines.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{} ft o.c.</td>"
            "<td>{} ft</td></tr>".format(
                row["count"], _esc(row["name"]), _esc(row["botanical"]),
                row["spacing"], row["mature"]))
    lines.append("</table>")
    lines.append(
        "<p class=key>A solid circle is the spacing. A thin ring is the "
        "mature width. A dashed circle stays.</p>")
    return "".join(lines)


def page(scheme, token, stamp=None):
    beds = scheme.get("beds") or []
    buttons = []
    svgs = []
    notes = []
    for i, bed in enumerate(beds):
        on = " on" if i == 0 else ""
        n = len(bed.get("plants") or [])
        buttons.append(
            f"<button type=button class='tab{on}' data-bed='{_esc(bed['id'])}'>"
            f"{_esc(bed['id'])} <span>{n}</span></button>")
        flag = "" if i == 0 else " hidden"
        svgs.append(
            f"<div class=sheet data-bed='{_esc(bed['id'])}'{flag}>"
            f"{_svg(bed)}{_schedule(bed)}</div>")
        notes.append(
            f"<p class=why data-bed='{_esc(bed['id'])}'{flag}>"
            f"{_esc(bed.get('why') or '')}</p>")
    stamp_html = ""
    if stamp:
        stamp_html = (f"<p class=stamp>{_esc(stamp)}. Picks here change the "
                      f"copy, not the garden.</p>")
    return f"""<!doctype html>
<html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>{TITLE}</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;margin:0 auto;padding:1rem;
max-width:70rem;color:#1c1c17;background:#fbfaf6}}
h1{{font-size:1.35rem;margin:0 0 .3rem}}
.lede,.why{{color:#5b5b50;font-size:.92rem}}
.stamp{{background:#8a3b12;color:#fff;padding:.5rem .7rem;border-radius:6px}}
.tabs{{display:flex;gap:.4rem;margin:.8rem 0;flex-wrap:wrap}}
.tab{{font:inherit;border:1px solid #cfd8c3;background:#fff;border-radius:99px;
padding:.35rem .7rem;cursor:pointer}}
.tab.on{{background:#4a7c2f;color:#fff;border-color:#4a7c2f}}
.tab span{{opacity:.75}}
.scroller{{overflow-x:auto;border:1px solid #e4e0d4;border-radius:10px;background:#f3efe4}}
svg.bed{{display:block}}
.soil{{fill:#f6f1e4;stroke:#6b5b45;stroke-width:2}}
.band{{fill:#d5dec4;stroke:none}}
.bandlabel,.edge{{fill:#6b6b5e;font-size:13px}}
.plant{{cursor:pointer}}
.plant circle.solid{{stroke:#3d3428;stroke-width:1.6}}
.plant circle.mature{{fill:none;stroke:#6b5b45;stroke-width:1;stroke-dasharray:3 3}}
.plant.locked circle.solid{{stroke-dasharray:4 3;cursor:default}}
.plant text{{fill:#1c1c17;font-size:11px;font-weight:600;pointer-events:none}}
.tuft{{stroke:#3d3428;stroke-width:1.2}}
.leader{{stroke:#6b5b45;stroke-width:1}}
.mass{{fill:#1c1c17;font-size:12px}}
.schedule{{border-collapse:collapse;margin:.6rem 0;font-size:.85rem}}
.schedule th,.schedule td{{border-bottom:1px solid #e4e0d4;text-align:left;padding:.2rem .5rem}}
.key{{color:#5b5b50;font-size:.82rem}}
.plant.on circle{{stroke:#1c1c17;stroke-width:3}}
.panel{{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;
padding:.8rem;max-height:48vh;overflow:auto;margin:0 -1rem -1rem}}
.opt{{display:flex;gap:.6rem;align-items:center;width:100%;text-align:left;
font:inherit;border:1px solid #ddd;background:#fff;border-radius:8px;
padding:.35rem;margin:.35rem 0;cursor:pointer}}
.opt img{{width:64px;height:64px;object-fit:cover;border-radius:6px;flex:none}}
.opt b{{display:block}}
.opt i,.opt small{{display:block;color:#6b6b5e;font-size:.78rem}}
.saved{{background:#e6efdc;padding:.4rem .6rem;border-radius:6px}}
[hidden]{{display:none !important}}
</style></head><body>
{stamp_html}
<h1>{TITLE}</h1>
<p class=lede>A solid circle is the spacing. A thin ring is the mature width.
A dashed circle stays. Tap any other plant, then tap the one you want there.</p>
<div class=tabs>{''.join(buttons)}</div>
{''.join(notes)}
<div class=scroller>{''.join(svgs)}</div>
<div class=panel id=panel hidden>
<p id=status></p>
<div id=list></div>
</div>
<script>
const token = {json.dumps(token)};
const panel = document.getElementById('panel');
const list = document.getElementById('list');
const status = document.getElementById('status');
let current = null;

function showBed(id) {{
  document.querySelectorAll('.tab,.sheet,.why').forEach(el => {{
    const on = el.dataset.bed === id;
    el.classList.toggle('on', on && el.classList.contains('tab'));
    if (!el.classList.contains('tab')) el.hidden = !on;
  }});
  closePanel();
}}
document.querySelectorAll('.tab').forEach(btn => {{
  btn.addEventListener('click', () => showBed(btn.dataset.bed));
}});

function closePanel() {{
  panel.hidden = true;
  current = null;
  document.querySelectorAll('.plant.on').forEach(el => el.classList.remove('on'));
}}

function paint(group, plant) {{
  const circle = group.querySelector('circle');
  const text = group.querySelector('text');
  circle.setAttribute('fill', plant.color);
  const spread = plant.spread_ft * {SCALE} / 2;
  circle.setAttribute('r', Math.max(spread, 10));
  group.dataset.name = plant.name;
  const wide = spread * 2 > plant.name.length * 6.2 + 8;
  text.textContent = wide ? plant.name : '';
}}

async function openPlant(group, savedName) {{
  document.querySelectorAll('.plant.on').forEach(el => el.classList.remove('on'));
  group.classList.add('on');
  current = group.dataset.id;
  panel.hidden = false;
  list.replaceChildren();
  status.className = '';
  if (group.dataset.locked === '1') {{
    status.textContent = group.dataset.name + ' stays. It is already in the ground.';
    return;
  }}
  status.textContent = savedName
    ? ('Saved ' + savedName + '.')
    : ('Choices for ' + group.dataset.name + '.');
  if (savedName) status.className = 'saved';
  const res = await fetch('/' + token + '/options/' + current);
  const data = await res.json();
    if (!data.options || !data.options.length) {{
    status.textContent = data.why || 'No other plant on this list fits this spot.';
    return;
  }}
  data.options.forEach(opt => {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'opt';
    if (opt.photo) {{
      const img = document.createElement('img');
      img.alt = '';
      img.src = opt.photo;
      btn.appendChild(img);
    }}
    const span = document.createElement('span');
    const title = document.createElement('b');
    title.textContent = opt.name;
    const meta = document.createElement('i');
    const wide = opt.grows_ft || opt.spread_ft;
    meta.textContent = opt.botanical + ' · grows to ' + wide + ' ft';
    const note = document.createElement('small');
    note.textContent = opt.note || opt.attribution || '';
    span.append(title, meta, note);
    btn.appendChild(span);
    btn.addEventListener('click', () => saveSwap(group, opt.name));
    list.appendChild(btn);
  }});
}}

async function saveSwap(group, name) {{
  status.className = '';
  status.textContent = 'Saving ' + name + '.';
  const res = await fetch('/' + token + '/swap', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id: group.dataset.id, name: name}})
  }});
  const data = await res.json();
  if (!res.ok) {{
    status.textContent = data.error || 'That plant does not fit this gap.';
    return;
  }}
  paint(group, data.plant);
  openPlant(group, data.plant.name);
}}

document.querySelectorAll('.plant').forEach(group => {{
  group.addEventListener('click', () => openPlant(group));
}});
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
            self.end_headers()
            self.wfile.write(raw)

        def _json(self, payload, code=200):
            self._send(json.dumps(payload), code, "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/" + token:
                return self._send(page(load(slug), token, stamp))
            prefix = f"/{token}/options/"
            if path.startswith(prefix):
                scheme = load(slug)
                opts, err = options_for(slug, scheme, path[len(prefix):])
                if err and opts is None:
                    return self._json({"error": err}, 404)
                return self._json({"options": opts or [], "why": err or ""})
            self._send("Not found", 404, "text/plain")

        def do_POST(self):
            if self.path.split("?", 1)[0].rstrip("/") != f"/{token}/swap":
                return self._send("Not found", 404, "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n).decode() or "{}")
            except json.JSONDecodeError:
                return self._json({"error": "The change was not readable."}, 400)
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
