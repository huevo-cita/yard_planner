#!/usr/bin/env python3
"""The proposed planting, and whether the yard can actually support it.

    python3 -m lib.design <slug>            summary and every objection
    python3 -m lib.design <slug> --init     empty design.json
    python3 -m lib.design <slug> --json     objections, machine-readable

This is a linter for a garden. It does not choose plants; that is research, and
it has to be done fresh for every region because a plant list does not travel.
What it does is take a chosen list and check it against what was measured — sun
hours by zone and month, soil texture and pH, whether a hose reaches, how much
ground there actually is — and object where the yard cannot support it.

The objections are the point. It is easy to assemble a beautiful, coherent,
regionally appropriate planting that quietly needs six hours of sun in a bed that
gets three, and nothing about the plan looks wrong until August.

Every plant carries its own requirements
----------------------------------------
There is no plant database here, deliberately. A requirement is recorded on the
plant as researched, with a `source`, and the checks run against that. A shipped
database would be wrong about half of it, would not know the local cultivar, and
would tempt everyone into skipping the research that actually matters.

    {"name": "Gulf muhly", "botanical": "Muhlenbergia capillaris",
     "count": 5, "zone": "back_bed", "light": "full sun",
     "mature_spread_ft": 3.0, "mature_height_ft": 3.0,
     "water": "low", "ph_range": [6.0, 8.0], "bloom": ["Oct", "Nov"],
     "evergreen": false, "role": "accent",
     "source": "Lady Bird Johnson Wildflower Center, 2026-08"}

What the objections mean
------------------------
    blocking    the plant will not survive, or the design contradicts a `must`.
                Change it
    serious     it will survive and disappoint. Usually a trade worth naming
    note        worth knowing, not worth changing anything for

Nothing is silently dropped or substituted. The objection is raised and the
person decides, because a `serious` objection is often a trade they are happy to
make and there is no way to know that from here.
"""
import argparse
import datetime
import json
import re

from . import solar, vision as vision_mod, yards

# Hours of direct sun each nursery label actually needs, and what it looks like
# when it is short. These are the thresholds sunmodel reports against.
LIGHT_NEED = {
    "full sun": (6.0, "flops, stops blooming, and gets mildew"),
    "part sun": (4.0, "blooms thinly and leans"),
    "part shade": (3.0, "survives but stays sparse"),
    "shade": (1.5, "thins out"),
    "deep shade": (0.0, ""),
}
LIGHT_ORDER = ["deep shade", "shade", "part shade", "part sun", "full sun"]

# Too much sun is a real failure in a hot climate and is usually missed, because
# nobody thinks of sun as something a plant can have too much of.
SCORCH_MARGIN = 3.0

WATER_NEED = {"low": 0, "moderate": 1, "high": 2}

MONTHS = list(solar.MONTH_DOY.keys()) if hasattr(solar, "MONTH_DOY") else \
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def blank(slug):
    return {"yard": slug, "created": datetime.date.today().isoformat(),
            "plants": [], "hardscape": [], "layout": {"beds": []},
            "notes": []}


def _obj(level, about, say, fix=None):
    o = {"level": level, "about": about, "say": say}
    if fix:
        o["fix"] = fix
    return o


def _table(sun):
    return (sun or {}).get("by_zone_and_month") or (sun or {}).get("zones") or {}


def resolve_zone(sun, site, zone):
    """A design names a zone however the person did. The sun model keys its
    table by display label. Match on either, and on the analysis bands, so that
    `back_bed`, `Back bed` and `Back bed along the house` all land."""
    table = _table(sun)
    if zone in table:
        return zone
    aliases = {}
    for key, z in (site.get("zones") or {}).items():
        for name in (key, z.get("label"), z.get("label_short")):
            if name:
                aliases.setdefault(_norm(name), []).append(key)
    want = _norm(zone)
    for name in table:
        if _norm(name) == want:
            return name
        if want in aliases and any(_norm(name) == _norm(k) or
                                   _norm(name) == want for k in aliases[want]):
            return name
    # last resort: the site's own label for this key, matched loosely
    z = (site.get("zones") or {}).get(zone) or {}
    for name in table:
        for cand in (z.get("label_short"), z.get("label")):
            if cand and _norm(cand) == _norm(name):
                return name
    return None


def _norm(s):
    return "".join(c for c in str(s).lower() if c.isalnum())


def _series(sun, site, zone, months, field):
    name = resolve_zone(sun, site, zone)
    if name is None:
        return []
    z = _table(sun).get(name) or {}
    keys = [m for m in (months or z.keys()) if m in z]
    return [z[m].get(field) for m in keys
            if isinstance(z[m], dict) and z[m].get(field) is not None]


def zone_hours(sun, site, zone, months=None):
    """Effective sun hours for a zone, averaged over the months given."""
    vals = _series(sun, site, zone, months, "effective")
    return round(sum(vals) / len(vals), 2) if vals else None


def zone_best(sun, site, zone, months=None):
    vals = _series(sun, site, zone, months, "best_cell")
    return round(max(vals), 2) if vals else None


def check_light(plant, sun, site):
    out = []
    zone, want = plant.get("zone"), (plant.get("light") or "").lower()
    if not zone or want not in LIGHT_NEED:
        return out
    months = plant.get("months") or plant.get("bloom") or None
    have = zone_hours(sun, site, zone, months)
    if have is None:
        return [_obj("note", plant["name"],
                     f"no sun-hour figure for zone {zone!r}; the light check "
                     f"could not run",
                     "run `python3 -m lib.sunmodel <slug>` and check the zone "
                     "name matches site.json")]

    need, symptom = LIGHT_NEED[want]
    window = "over " + ", ".join(months) if months else "over the year"
    if have < need:
        best = zone_best(sun, site, zone, months)
        fix = None
        if best and best >= need:
            fix = (f"the sunniest cell in that zone does reach {best} h, so this "
                   f"may work in one corner of it rather than across the bed")
        out.append(_obj("blocking" if have < need - 1.5 else "serious",
                        plant["name"],
                        f"wants {want} ({need}+ h) and zone {zone} averages "
                        f"{have} h {window}. It {symptom}",
                        fix or f"move it to a brighter zone, or swap for "
                               f"something rated {_label_for(have)}"))
    if want in ("shade", "part shade") and have > need + SCORCH_MARGIN:
        hot = (site.get("climate") or {}).get("heat", {}) \
            .get("days_over_95f_per_year")
        if hot and hot > 20:
            out.append(_obj("serious", plant["name"],
                            f"is a {want} plant in a zone averaging {have} h, in "
                            f"a climate with {hot} days over 95 F a year. It will "
                            f"scorch in July whatever the watering",
                            "move it to the shaded end, or give it afternoon "
                            "shade specifically — morning sun of the same length "
                            "is a different thing entirely"))
    return out


def check_sun_timing(design, sun, site):
    """Sun that arrives entirely in the afternoon, in a climate that gets hot.

    The hour count says a bed is fine and the plants die anyway. This is usually
    why: the bed takes its whole daily sun load between one o'clock and sunset,
    when the air is at its hottest and the soil has already dried, and gets
    nothing in the cool of the morning when a plant could actually use it.

    This is a fact about a bed, not about a plant, so it is reported once per
    zone with the plants it applies to named. Repeating it under every plant in
    the bed buries it.
    """
    out = []
    timing = ((sun or {}).get("sun_timing") or {})
    hot = (site.get("climate") or {}).get("heat", {}) \
        .get("days_over_95f_per_year")
    if not timing or not hot or hot < 20:
        return out
    by_zone = {}
    for p in design.get("plants", []):
        if p.get("zone"):
            by_zone.setdefault(p["zone"], []).append(p["name"])
    for zone, names in by_zone.items():
        key = resolve_zone({"by_zone_and_month": timing}, site, zone)
        if not key:
            continue
        t = timing[key]
        late = t.get("after_1pm_share")
        if late is None or late < 0.8:
            continue
        have = zone_hours(sun, site, zone)
        first = t.get("first_sun_clock")
        when = f", and nothing before {_clock(first)}" if first else ""
        out.append(_obj(
            "serious", f"zone {zone}",
            f"takes {int(late * 100)} percent of its direct sun after 1 p.m."
            f"{when}, in a climate with {hot} days over 95 F a year. The "
            f"{have} h figure reads like part sun and behaves like full "
            f"afternoon sun, which is the harshest exposure there is. It "
            f"applies to everything here: "
            f"{', '.join(sorted(set(names))[:4])}"
            + (" and others" if len(set(names)) > 4 else ""),
            "afternoon shade is the fix, not less sun overall: a panel on the "
            "western side, or something in front that is already up and full "
            "by the time the heat arrives"))
    return out


def _clock(h):
    hh, mm = int(h), int(round((h - int(h)) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    ampm = "am" if hh < 12 else "pm"
    return f"{(hh - 1) % 12 + 1}:{mm:02d} {ampm}"


def _label_for(hours):
    for name in reversed(LIGHT_ORDER):
        if hours >= LIGHT_NEED[name][0]:
            return name
    return "deep shade"


def check_water(plant, cond, site):
    out = []
    need = WATER_NEED.get((plant.get("water") or "").lower())
    if need is None:
        return out
    water = (cond or {}).get("water") or {}
    if need >= 2 and water.get("hose_reaches") is False:
        out.append(_obj("blocking", plant["name"],
                        "needs regular water and no hose reaches that bed",
                        "run a hose or drip line first, or choose something "
                        "drought-tolerant. A bed that cannot be watered in "
                        "August will not be watered in August"))
    if plant.get("zone") in (water.get("rain_shadow_zones") or []) and \
            not water.get("irrigation"):
        out.append(_obj("serious", plant["name"],
                        f"sits in {plant['zone']}, which is under a roof or "
                        f"awning and gets almost no natural rain. Irrigation is "
                        f"the whole water supply there, not a supplement",
                        "drip, and accept that it never gets switched off "
                        "entirely — only turned down"))
    return out


def check_soil(plant, cond):
    out = []
    soil = (cond or {}).get("soil") or {}
    ph = soil.get("ph")
    rng = plant.get("ph_range")
    if ph is not None and rng and not (rng[0] <= ph <= rng[1]):
        out.append(_obj("serious", plant["name"],
                        f"wants pH {rng[0]}-{rng[1]} and the soil reads {ph}",
                        "amending pH is a losing fight in open ground. Either "
                        "choose something suited to the soil, or grow this one "
                        "in a container where the medium is yours"))
    drain = (soil.get("drainage") or "").lower()
    if plant.get("soil_drainage") == "sharp" and \
            ("slow" in drain or "poor" in drain):
        out.append(_obj("blocking", plant["name"],
                        f"needs sharp drainage and the soil drains {drain}. This "
                        f"is the classic way to kill rosemary and lavender, and "
                        f"it takes two years so nobody connects it to the soil",
                        "plant it on a mound or in a raised pocket with grit, "
                        "with the crown set high"))
    return out


def check_space(design, site, sun):
    """Overplanting, which is the most common failure and the least visible."""
    out = []
    by_zone = {}
    for p in design.get("plants", []):
        z = p.get("zone")
        spread = p.get("mature_spread_ft")
        if not z or not spread:
            continue
        n = p.get("count", 1)
        by_zone.setdefault(z, []).append((p["name"], n, spread))

    areas = zone_areas(site)
    for z, plants in by_zone.items():
        usable = areas.get(z)
        if not usable:
            continue
        need = sum(n * 3.1416 * (s / 2.0) ** 2 for _, n, s in plants)
        if need > usable * 1.15:
            over = round(need / usable, 2)
            out.append(_obj("serious", f"zone {z}",
                            f"the plants at mature spread need {need:.0f} sq ft "
                            f"and the zone has {usable:.0f}. That is {over}x "
                            f"overplanted",
                            "cut the count. A first-year bed that looks full is "
                            "overplanted, and the plants that lose are usually "
                            "the expensive slow ones"))
        elif need < usable * 0.45:
            out.append(_obj("note", f"zone {z}",
                            f"the planting covers about "
                            f"{100 * need / usable:.0f}% of the zone at maturity, "
                            f"which will read as sparse and will want mulching "
                            f"and weeding for years",
                            "add groundcover between, or tighten the layout and "
                            "leave deliberate open ground rather than accidental "
                            "gaps"))
    return out


def zone_areas(site):
    """Usable square feet per zone, net of anything declared unplantable."""
    out = {}
    for name, z in (site.get("zones") or {}).items():
        if isinstance(z, dict) and z.get("area_sqft"):
            out[name] = float(z["area_sqft"])
            continue
        box = z.get("box") if isinstance(z, dict) else None
        if box and len(box) == 4:
            x0, y0, x1, y1 = box
            sq = abs((x1 - x0) * (y1 - y0)) / 144.0
            for taken in (z.get("unplantable_sqft"), z.get("rock_band_sqft")):
                if taken:
                    sq -= float(taken)
            out[name] = max(0.0, sq)
    return out


def check_vision(design, vision):
    """Whether the design honours what was actually asked for."""
    out = []
    if not vision:
        return [_obj("note", "vision",
                     "no vision.json, so nothing checks this design against what "
                     "they asked for. It is the assistant's taste until it is "
                     "reviewed",
                     "run the yard-vision skill")]

    text = json.dumps(design).lower()
    for w in vision_mod._wants(vision):
        want = w.get("want", "")
        key = _content_words(want)
        hit = any(t in text for t in key)
        if w.get("strength") == "must" and key and not hit:
            out.append(_obj("blocking", "vision",
                            f"they said this is non-negotiable and the design "
                            f"does not mention it: {want!r}",
                            "either it is in the design or the design changes"))

    # A dislike is checked against what is being planted and built, not against
    # the whole file. Scanning the prose finds the word "through" in a note and
    # reports it as a violation, which trains the reader to ignore the check.
    for d in (vision.get("dislikes") or []):
        phrase = d.get("want", d) if isinstance(d, dict) else d
        scope = d.get("applies_to") if isinstance(d, dict) else None
        names = " ".join(
            [str(p.get("name", "")) for p in design.get("plants", [])
             if not scope or p.get("zone") == scope] +
            [str(h.get("item", "")) for h in design.get("hardscape", [])
             if not scope or h.get("zone") == scope]).lower()
        for token in _content_words(phrase):
            if token in names:
                where = f" in {scope}" if scope else ""
                out.append(_obj("serious", "vision",
                                f"they said {phrase!r} and {token!r} is in the "
                                f"design{where}"))
                break
    return out


# Words that carry no meaning for a keyword match. Without this the checks fire
# on prose rather than on plants.
_STOPWORDS = {
    "about", "above", "actually", "after", "again", "against", "along", "also",
    "always", "among", "around", "because", "before", "being", "below",
    "between", "both", "cannot", "could", "does", "doing", "done", "down",
    "during", "each", "either", "else", "enough", "even", "ever", "every",
    "everything", "from", "further", "getting", "gets", "give", "given",
    "going", "have", "having", "here", "however", "into", "itself", "just",
    "keep", "kept", "kill", "kills", "know", "least", "less", "like", "likely",
    "look", "looks", "made", "make", "makes", "many", "more", "most", "much",
    "must", "near", "need", "needs", "never", "next", "nothing", "often",
    "once", "only", "onto", "other", "over", "own", "past", "plant", "plants",
    "prefer", "prefers", "rather", "really", "same", "several", "should",
    "since", "some", "still", "such", "than", "that", "their", "them", "then",
    "there", "these", "they", "thing", "things", "this", "those", "though",
    "three", "through", "time", "under", "until", "upon", "very", "want",
    "wants", "well", "were", "what", "when", "where", "which", "while", "will",
    "with", "within", "without", "would", "year", "years", "your",
}


def _content_words(phrase):
    return [t.strip(".,;:'\"()") for t in str(phrase).lower().split()
            if len(t.strip(".,;:'\"()")) > 4
            and t.strip(".,;:'\"()").isalpha()
            and t.strip(".,;:'\"()") not in _STOPWORDS]


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _target_month(target):
    """The month abbreviation of a target date, in any shape the record holds it.

    `vision.json` stores a target date as a recorded preference — a dict with a
    strength and the sentence it came from — so the date arrives wrapped and with
    prose around it. Slicing ten characters off `str()` of that dict yields
    "{'want': '", which raises and makes this check silently do nothing. Every
    yard whose vision.json used the documented shape has been skipping the whole
    season check.
    """
    if isinstance(target, datetime.date):
        return target.strftime("%b")
    if isinstance(target, list) and target:
        target = target[0]
    if isinstance(target, dict):
        target = (target.get("date") or target.get("want")
                  or target.get("value") or "")
    hit = _ISO.search(str(target))
    if not hit:
        raise ValueError(f"no date in {target!r}")
    return datetime.date.fromisoformat(hit.group(0)).strftime("%b")


def check_season(design, vision, site):
    """Whether anything is happening on the date it has to be right by."""
    out = []
    target = (vision or {}).get("target_date")
    if not target:
        return out
    try:
        month = _target_month(target)
    except ValueError:
        return out

    blooming = [p["name"] for p in design.get("plants", [])
                if month in (p.get("bloom") or [])]
    ever = [p["name"] for p in design.get("plants", []) if p.get("evergreen")]

    if not blooming:
        out.append(_obj("serious", "target date",
                        f"the date that matters is in {month} and nothing in the "
                        f"design is recorded as blooming then. It is easy to "
                        f"assemble a lovely palette that peaks six weeks off",
                        "chart bloom by month and fill the gap, and carry "
                        "bulletproof seasonal annuals as insurance — they will "
                        "look right on the day whatever the perennials do"))
    elif len(blooming) < 3:
        out.append(_obj("note", "target date",
                        f"only {len(blooming)} things bloom in {month}: "
                        f"{', '.join(blooming)}. One bad spring and the date has "
                        f"nothing on it"))

    n = len([p for p in design.get("plants", []) if p.get("count")])
    if n and len(ever) < max(1, n // 5):
        out.append(_obj("note", "winter",
                        f"{len(ever)} of {n} entries hold structure out of "
                        f"season. Most native perennials look like nothing from "
                        f"November to March, and a bed with no bones looks "
                        f"abandoned rather than dormant",
                        "a spine of evergreen shrubs or aromatic mounds among "
                        "the perennials, not instead of them"))
    return out


def check_grouping(design):
    out = []
    singles = [p["name"] for p in design.get("plants", [])
               if p.get("count") == 1 and p.get("role") not in
               ("specimen", "tree", "structure", "existing")]
    if len(singles) >= 5:
        out.append(_obj("note", "layout",
                        f"{len(singles)} plants appear once each. One of "
                        f"everything reads as a collection rather than a "
                        f"planting",
                        "groups of three or five of the same thing, and repeat "
                        "the group along the bed"))
    return out


def check(slug):
    design = yards.load(slug, "design.json") or {}
    site = yards.load(slug, "site.json") or {}
    cond = yards.load_conditions(slug)
    vis = yards.load_vision(slug)
    sun = yards.load(slug, "sun-hours.json")

    out = []
    if not sun:
        out.append(_obj("blocking", "light",
                        "no sun-hours.json, so no plant's light requirement can "
                        "be checked at all. This is the check that matters most",
                        "run `python3 -m lib.sunmodel " + slug + "`"))
    for p in design.get("plants", []):
        out += check_light(p, sun, site)
        out += check_water(p, cond, site)
        out += check_soil(p, cond)
    out += check_sun_timing(design, sun, site)
    out += check_space(design, site, sun)
    out += check_vision(design, vis)
    out += check_season(design, vis, site)
    out += check_grouping(design)

    rank = {"blocking": 0, "serious": 1, "note": 2}
    out.sort(key=lambda o: rank[o["level"]])
    return out


def report(slug):
    design = yards.load(slug, "design.json")
    if not design:
        print(f"{slug} has no design.json yet")
        return
    plants = design.get("plants", [])
    total = sum(p.get("count", 1) for p in plants)
    print(f"{slug} — proposed design\n")
    print(f"  {len(plants)} kinds, {total} plants")
    for z in sorted({p.get("zone") for p in plants if p.get("zone")}):
        inz = [p for p in plants if p.get("zone") == z]
        print(f"    {z:20s} {sum(p.get('count', 1) for p in inz):3d} plants, "
              f"{len(inz)} kinds")

    objs = check(slug)
    if not objs:
        print("\n  nothing to object to. The site supports this")
        return
    counts = {}
    for o in objs:
        counts[o["level"]] = counts.get(o["level"], 0) + 1
    print("\n  " + ", ".join(f"{n} {lvl}" for lvl, n in counts.items()) + ":\n")
    for o in objs:
        print(f"  [{o['level']}] {o['about']}")
        for line in vision_mod._wrap(o["say"], 70):
            print(f"      {line}")
        if o.get("fix"):
            for line in vision_mod._wrap("-> " + o["fix"], 70):
                print(f"      {line}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.init:
        if yards.load(args.slug, "design.json"):
            print(f"{args.slug} already has a design.json; not overwriting")
            return
        print(f"wrote {yards.save(args.slug, 'design.json', blank(args.slug))}")
        return
    if args.json:
        print(json.dumps(check(args.slug), indent=2))
        return
    report(args.slug)


if __name__ == "__main__":
    main()
