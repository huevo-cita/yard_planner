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
     "evergreen": false, "role": "accent", "layer": "back",
     "source": "Lady Bird Johnson Wildflower Center, 2026-08"}

Two optional fields change how much ground a plant is judged to occupy, and
both of them were a wrong answer on a real bed before they existed:

    layer      front / middle / back / vine / accent. A `vine` is carried on a
               trellis and takes no ground, which is the difference between a
               bed reading 1.49x overplanted and reading 0.77x.
    annual     true for anything that holds the ground for one season and then
               comes out. Cool-season annuals tucked among established
               perennials are a succession rather than a competition, and
               counting both at full spread double-books ground that only one
               of them occupies at a time.

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

from . import doubts, solar, vision as vision_mod, yards

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

# The months `LIGHT_NEED` is compared against when a plant names none of its
# own. Not a second definition — `solar.GROWING_SEASON` is the only one, and
# `sunmodel` classes the whole yard on the same window — but named here because
# it is the default this module applies, and a test that asserts the two are
# the same object is what stops them drifting apart again.
#
# The default used to be all twelve months, which docked every bed more than an
# hour of open sky before an obstruction was counted and withdrew four full-sun
# plants from a real design on the strength of December light they were never
# going to be alive in.
DEFAULT_LIGHT_MONTHS = solar.GROWING_SEASON


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


def resolve_site_zone(site, zone):
    """A design's zone name, resolved to the key `site.json` files it under.

    `resolve_zone` above answers a different question — it resolves to the label
    the *sun model* keys its table by. The area and container records live on
    `site.json` under their own keys, so a design that names a bed by its label
    rather than its key found no area at all and the space check silently passed.
    """
    zones = (site.get("zones") or {})
    if zone in zones:
        return zone
    want = _norm(zone)
    for key, z in zones.items():
        names = [key]
        if isinstance(z, dict):
            names += [z.get("label"), z.get("label_short")]
        if any(name and _norm(name) == want for name in names):
            return key
    return None


def _series(sun, site, zone, months, field):
    name = resolve_zone(sun, site, zone)
    if name is None:
        return []
    z = _table(sun).get(name) or {}
    keys = [m for m in (months or DEFAULT_LIGHT_MONTHS) if m in z]
    return [z[m].get(field) for m in keys
            if isinstance(z[m], dict) and z[m].get(field) is not None]


def zone_hours(sun, site, zone, months=None):
    """Effective sun hours for a zone, averaged over the months given.

    With no months, over `DEFAULT_LIGHT_MONTHS`. Callers that want the
    twelve-month mean have to ask for it by name — `solar.MONTHS` — because a
    figure whose window nobody stated is how the two windows got confused in
    the first place.
    """
    vals = _series(sun, site, zone, months, "effective")
    return round(sum(vals) / len(vals), 2) if vals else None


def window_label(months):
    """Which months a sun figure is a mean of, in words.

    Every objection quoting an hour figure has to say what it averaged, because
    the reader's next move is to hold it against a nursery tag and the two are
    only comparable if they cover the same season. The message this replaces
    said "over the year" whatever it had actually measured.
    """
    ms = list(months or DEFAULT_LIGHT_MONTHS)
    if ms == list(MONTHS):
        return "the year"
    if ms == list(DEFAULT_LIGHT_MONTHS):
        return f"the growing season, {ms[0]}-{ms[-1]}"
    return ", ".join(ms)


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
    window = window_label(months)
    if have < need:
        best = zone_best(sun, site, zone, months)
        fix = None
        if best and best >= need:
            fix = (f"the sunniest cell in that zone does reach {best} h, so this "
                   f"may work in one corner of it rather than across the bed")
        out.append(_obj("blocking" if have < need - 1.5 else "serious",
                        plant["name"],
                        f"wants {want} ({need}+ h) and zone {zone} averages "
                        f"{have} h over {window}. It {symptom}",
                        fix or f"move it to a brighter zone, or swap for "
                               f"something rated {_label_for(have)}"))
    if want in ("shade", "part shade") and have > need + SCORCH_MARGIN:
        hot = (site.get("climate") or {}).get("heat", {}) \
            .get("days_over_95f_per_year")
        if hot and hot > 20:
            out.append(_obj("serious", plant["name"],
                            f"is a {want} plant in a zone averaging {have} h "
                            f"over {window}, in "
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
            f"{have} h figure — a mean over {window_label(None)} — reads like "
            f"part sun and behaves like full "
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


def check_soil(plant, cond, site=None):
    """Whether the soil suits the plant — where the plant is in soil at all.

    A container is not the ground. Its medium is whatever gets put in it, so
    holding a potted plant to the yard's pH refuses it for a reason that does
    not apply — and this function's own advice for a pH mismatch is to *grow it
    in a container where the medium is yours*, which it then objected to.
    """
    out = []
    if site is not None and plant.get("zone"):
        key = resolve_site_zone(site, plant["zone"]) or plant["zone"]
        if zone_kind(site, key) == "container":
            return out
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


def footprint(plant):
    """Ground a plant occupies at mature spread.

    A vine is the exception, and it is not a rounding error: a climbing rose on
    an 80 in trellis was counted as if its whole 3 ft canopy sat on the soil,
    which read one bed at 1.49x overplanted when the bed is fine and its own
    notes say so — the canopy is carried overhead and the ground beneath it
    still plants. The base a vine does occupy is small and unrecorded, and the
    answer does not move across its plausible range.
    """
    if plant.get("layer") == "vine":
        return 0.0
    spread = plant.get("mature_spread_ft")
    if not spread:
        return 0.0
    return plant.get("count", 1) * 3.1416 * (spread / 2.0) ** 2


# The band a border planting has to land in. Below the floor it reads as sparse
# and wants weeding for years; above the ceiling it is overplanted and the
# plants that lose are the slow expensive ones. `lib.niches` budgets its slots
# against this same band, so a planting picked there passes here by
# construction rather than by luck.
COVER_FLOOR, COVER_CEILING = 0.45, 1.15


def check_space(design, site, sun):
    """Overplanting, which is the most common failure and the least visible."""
    out = []
    by_zone = {}
    for p in design.get("plants", []):
        z = p.get("zone")
        if not z or not p.get("mature_spread_ft"):
            continue
        by_zone.setdefault(z, []).append(p)

    areas = zone_areas(site)
    for z, plants in by_zone.items():
        key = resolve_site_zone(site, z) or z
        kind = zone_kind(site, key)

        if kind == "container":
            out += _check_containers(z, plants,
                                     zone_containers(site, key) or 0)
            continue
        if kind == "grid":
            out += _check_grid(z, plants, site, key)
            continue

        soil = areas.get(key)
        if not soil:
            continue                # reported by check_coverage, not passed over
        # Canopies are judged against the ground a canopy can occupy, roots
        # against the soil. Where no apron is declared these are the same
        # number and nothing below changes.
        usable, allowance = zone_canopy_room(site, key, soil)

        # Annuals and perennials in one bed are a succession, not a crowd: the
        # violas come out before the perennials have their summer size. Judging
        # the bed on whichever group needs more ground counts the busiest
        # moment, which is the honest reading, rather than adding two plantings
        # that are never both at full spread.
        perennial = sum(footprint(p) for p in plants if not p.get("annual"))
        annual = sum(footprint(p) for p in plants if p.get("annual"))
        need = max(perennial, annual)
        both = perennial + annual
        note = ""
        if annual and both > usable * COVER_CEILING >= need:
            note = (f" Counting the {annual:.0f} sq ft of annuals alongside the "
                    f"perennials rather than after them would read "
                    f"{both / usable:.2f}x, and they are a succession.")

        room = ""
        if allowance:
            room = (f" The {usable:.0f} sq ft is {soil:.0f} of soil plus the "
                    f"{allowance:.0f} sq ft of apron this zone's "
                    f"{z_overhang(site, key):g} ft canopy overhang allows the "
                    f"tops to lean out over.")

        if need > usable * COVER_CEILING:
            over = round(need / usable, 2)
            out.append(_obj("serious", f"zone {z}",
                            f"the plants at mature spread need {need:.0f} sq ft "
                            f"and the zone has {usable:.0f}. That is {over}x "
                            f"overplanted" + room,
                            "cut the count. A first-year bed that looks full is "
                            "overplanted, and the plants that lose are usually "
                            "the expensive slow ones"))
        elif allowance and need > soil * COVER_CEILING:
            # Passes only because the tops are allowed out over the apron. True,
            # and worth saying: the roots are still in the soil figure, and if
            # the apron is ever planted or paved the bed is overplanted again.
            out.append(_obj("note", f"zone {z}",
                            f"the planting fits at {need / usable:.2f}x only "
                            f"because the tops may lean out over the apron — "
                            f"against soil alone it is "
                            f"{need / soil:.2f}x.{room} The roots are all still "
                            f"in the {soil:.0f} sq ft",
                            "no change needed, but do not later plant or pave "
                            "the apron without revisiting the count, and expect "
                            "the front rank to lean"))
        elif need < usable * COVER_FLOOR:
            out.append(_obj("note", f"zone {z}",
                            f"the planting covers about "
                            f"{100 * need / usable:.0f}% of the zone at maturity, "
                            f"which will read as sparse and will want mulching "
                            f"and weeding for years" + note,
                            "add groundcover between, or tighten the layout and "
                            "leave deliberate open ground rather than accidental "
                            "gaps"))
        out += _check_depth(z, plants, site, key)
    return out


def _check_depth(zone, plants, site, key):
    """A plant wider than the bed is deep, which area alone never catches.

    A bed can be comfortably under its area budget and still have nowhere to put
    something: a two-foot rosette in a bed two foot five deep has nowhere to go,
    and it leans out over the edge or into the wall whatever the square footage
    says. Reported once per zone with the plants named, because it is a fact
    about the bed.
    """
    z = (site.get("zones") or {}).get(key) or {}
    depth = z.get("usable_depth_ft")
    if not depth:
        return []
    # A canopy and a root ball are different constraints, and a bed with a
    # gravel or stone apron in front of it can hold a plant whose top leans out
    # over ground its roots could never occupy. That has to be declared per
    # zone, because whether the apron may be shaded is a judgement about how the
    # bed should look, not something derivable from the measurements.
    reach = float(depth) + float(z.get("canopy_overhang_ft") or 0)
    over = [(p["name"], p["mature_spread_ft"], p.get("count", 1))
            for p in plants
            if p.get("layer") != "vine"
            and (p.get("mature_spread_ft") or 0) > reach]
    if not over:
        return []
    # Individual plants, not entries. Two white mistflower under one entry are
    # two plants with nowhere to go, and reporting "1" invites someone to move
    # one thing and consider it handled.
    n = sum(c for _, _, c in over)
    worst = ", ".join(
        (f"{c} {name}" if c > 1 else name) + f" at {s:g} ft"
        for name, s, c in sorted(over, key=lambda x: -x[1])[:4])
    allowed = ("" if reach == float(depth) else
               f", plus the {reach - float(depth):g} ft of overhang this zone "
               f"allows")
    return [_obj("serious", f"zone {zone}",
                 f"{n} plant{'' if n == 1 else 's'} spread wider "
                 f"than the bed is deep — {depth:g} ft of usable depth"
                 f"{allowed}, against {worst}. Area is not the constraint here; "
                 f"there is nowhere for them to go but out over the edge or "
                 f"into the wall",
                 "move them to a deeper bed, choose narrower plants for this "
                 "one, or set `canopy_overhang_ft` on the zone if a canopy may "
                 "lean out over whatever is in front of the soil")]


def _check_grid(zone, plants, site, key):
    """A square-foot bed, counted in squares.

    Dense planting is the method in a grid, not a fault, so judging it against
    the border band reports a correctly planted bed as overplanted. What is
    worth checking is whether the planting fits the squares there are.
    """
    z = (site.get("zones") or {}).get(key) or {}
    squares = z.get("squares")
    if not squares:
        return []
    planted = sum(p.get("count", 1) for p in plants)
    if planted > squares:
        return [_obj("note", f"zone {zone}",
                     f"{planted} entries for {squares} squares. A square-foot "
                     f"bed is meant to be full, and several of these share a "
                     f"square by design — worth a look at the map rather than a "
                     f"count",
                     f"check the grid in the bed map covers all {squares}")]
    return []


def _check_containers(zone, plants, pots):
    """A pot bed, counted in pots."""
    planted = sum(p.get("count", 1) for p in plants)
    n = f"{planted} plant" + ("" if planted == 1 else "s")
    if planted > pots:
        return [_obj("serious", f"zone {zone}",
                     f"{n} for {pots} containers. A pot of this size holds one "
                     f"of these, and two root systems sharing the medium is a "
                     f"slow decline over two summers rather than an obvious "
                     f"failure anyone would connect to the pot",
                     "one per container, or a bigger container")]
    if planted < pots:
        spare = pots - planted
        return [_obj("note", f"zone {zone}",
                     f"{n} in {pots} containers, so "
                     f"{spare} container{'' if spare == 1 else 's'} "
                     f"{'stands' if spare == 1 else 'stand'} empty")]
    return []


def check_coverage(design, site, cond, sun):
    """What could not be checked, said out loud.

    Three of the checks below read a flat scalar that a yard may record as prose
    under some other key, and each of them answered a missing input by moving on
    to the next plant. An objection list with nothing in it then means either
    "the site supports this" or "I could not look", and there is no way to tell
    which from the outside. On the yard this was written against all three were
    inert at once: no zone had an `area_sqft`, `soil` carried no `ph`, and
    `water` carried no `hose_reaches` — so the space, soil and water checks had
    never run, while the bed maps carried the sums somebody had done by hand.

    One objection per missing input, naming what it disabled. Per plant it would
    be fifty lines saying the same thing, which is its own kind of silence.
    """
    out = []
    plants = design.get("plants", [])
    if not plants:
        return out

    # --- space
    areas = zone_areas(site)
    blind = []
    for z in sorted({p.get("zone") for p in plants if p.get("zone")}):
        key = resolve_site_zone(site, z) or z
        if not areas.get(key) and not zone_containers(site, key):
            blind.append(z)
    if blind:
        out.append(_obj("note", "space",
                        f"no usable area recorded for "
                        f"{', '.join(repr(z) for z in blind)}, so the "
                        f"overplanting check did not run there. It is the most "
                        f"common failure and the least visible, and an empty "
                        f"objection list here does not mean the beds fit",
                        "set `area_sqft` on those zones in site.json (and "
                        "`unplantable_sqft` for any gravel or stone inside the "
                        "bed), or `containers` where the bed is pots"))

    # --- soil
    soil = (cond or {}).get("soil") or {}
    fussy = [p for p in plants if p.get("ph_range")]
    if soil.get("ph") is None and fussy:
        out.append(_obj("note", "soil",
                        f"no soil pH on record, so the pH check did not run for "
                        f"{len(fussy)} plants that state a range they need",
                        "set `soil.ph` in conditions.json — a $15 strip is "
                        "enough, and the yard-conditions skill walks it"))
    sharp = [p for p in plants if p.get("soil_drainage") == "sharp"]
    if not (soil.get("drainage") or "").strip() and sharp:
        out.append(_obj("note", "soil",
                        f"no soil drainage on record, so the drainage check did "
                        f"not run for {len(sharp)} plants needing sharp "
                        f"drainage. This is the classic way to kill rosemary "
                        f"and lavender, and it takes two years",
                        "set `soil.drainage` in conditions.json from a "
                        "percolation test, or from the USDA class"))

    # --- water
    water = (cond or {}).get("water") or {}
    thirsty = [p for p in plants if (p.get("water") or "").lower() == "high"]
    if water.get("hose_reaches") is None and thirsty:
        out.append(_obj("note", "water",
                        f"nothing on record about whether a hose reaches, so "
                        f"that check did not run for {len(thirsty)} plants "
                        f"needing regular water",
                        "set `water.hose_reaches` in conditions.json"))
    if water.get("rain_shadow_zones") is None:
        out.append(_obj("note", "water",
                        "no rain-shadow zones on record, so nothing checked "
                        "whether a bed sits under an eave or awning and gets "
                        "almost no natural rain",
                        "set `water.rain_shadow_zones` in conditions.json, to "
                        "an empty list if genuinely none — which is a different "
                        "statement from saying nothing"))
    return out


def zone_areas(site):
    """Usable square feet per zone, net of anything declared unplantable.

    The deduction used to apply only to an area computed from a `box`, so a zone
    stating `area_sqft` outright kept its river rock and gravel in the plantable
    figure. Both routes net it off now, which means `area_sqft` is the gross bed
    soil and `unplantable_sqft` is subtracted from it exactly once.
    """
    out = {}
    for name, z in (site.get("zones") or {}).items():
        if not isinstance(z, dict):
            continue
        sq = None
        if z.get("area_sqft"):
            sq = float(z["area_sqft"])
        else:
            box = z.get("box")
            if box and len(box) == 4:
                x0, y0, x1, y1 = box
                sq = abs((x1 - x0) * (y1 - y0)) / 144.0
        if sq is None:
            continue
        for taken in (z.get("unplantable_sqft"), z.get("rock_band_sqft")):
            if taken:
                sq -= float(taken)
        out[name] = max(0.0, sq)
    return out


def z_overhang(site, key):
    """The canopy overhang a zone declares, in feet."""
    z = (site.get("zones") or {}).get(key) or {}
    return float(z.get("canopy_overhang_ft") or 0)


def zone_canopy_room(site, key, soil):
    """Square feet a CANOPY may occupy, which is not the same as the soil.

    `zone_areas` nets off the river rock and the gravel, because nothing roots
    in them. But a plant standing in the soil behind a stone apron leans its
    top out over that apron perfectly happily, and `check_space` compares a sum
    of mature SPREADS — canopy footprints — against the soil figure. So a bed
    with an apron is judged on ground the tops were never going to need, and
    reads as overplanted on the strength of its own hardscape.

    `canopy_overhang_ft` already declares that this is allowed, and
    `_check_depth` already honours it on the depth arm. It was never applied to
    the area arm, so half the constraint used the allowance and half ignored it.

    The allowance is the overhang depth along the bed's run, capped by the
    unplantable area actually declared: a canopy cannot lean out over a strip
    that is not there. The run is recovered as soil over usable depth rather
    than asked for, because it is already implied by two numbers the zone
    carries and a third would be a third thing to keep in step.
    """
    z = (site.get("zones") or {}).get(key) or {}
    overhang = float(z.get("canopy_overhang_ft") or 0)
    depth = float(z.get("usable_depth_ft") or 0)
    strip = sum(float(z.get(k) or 0)
                for k in ("unplantable_sqft", "rock_band_sqft"))
    if overhang <= 0 or depth <= 0 or strip <= 0 or soil <= 0:
        return soil, 0.0
    run = soil / depth
    return soil + min(overhang * run, strip), min(overhang * run, strip)


def zone_containers(site, key):
    """How many pots a zone is, where it is pots rather than ground.

    A barrel bed is not a small border. Its binding constraint is one plant per
    barrel, and square footage barely enters into it — measured as area with the
    vines excluded it reads as 0 percent covered and trips the sparse branch.
    """
    z = (site.get("zones") or {}).get(key)
    if not isinstance(z, dict):
        return None
    c = z.get("containers")
    if isinstance(c, dict) and c.get("count"):
        return int(c["count"])
    return None


# What a zone is measured in. `border` is the default and the only one that
# judges mature spread against square footage. The other two have their own
# unit, and applying the border unit to them gives a confident wrong answer in
# both directions: pots read as sparse when they are full, and a square-foot
# grid reads as overplanted when dense planting is the whole method.
ZONE_KINDS = ("border", "grid", "container")


def zone_kind(site, key):
    z = (site.get("zones") or {}).get(key)
    if not isinstance(z, dict):
        return "border"
    kind = (z.get("kind") or "").lower()
    if kind in ZONE_KINDS:
        return kind
    return "container" if z.get("containers") else "border"


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


def check(slug, force=False):
    design = yards.load(slug, "design.json") or {}
    site = yards.load(slug, "site.json") or {}
    cond = yards.load_conditions(slug)
    vis = yards.load_vision(slug)
    sun = yards.load(slug, "sun-hours.json")

    out = []
    # An objection list computed on doubtful geometry is the most misleading
    # artifact this module can produce: it reads as a verdict, and a `blocking`
    # objection that evaporates once a fence turns out to be open rail has cost
    # someone a replanning session for nothing.
    stamp = doubts.gate(slug, "design", force=force)
    if stamp:
        open_now = doubts.open_cards(slug, job="design")
        out.append(_obj("note", "doubts",
                        stamp
                        + (" — " + "; ".join(c["question"] for c in open_now)
                           if open_now else "")
                        + ". Treat every verdict below as provisional",
                        f"python3 -m lib.doubts {slug} --open"))
    if not sun:
        out.append(_obj("blocking", "light",
                        "no sun-hours.json, so no plant's light requirement can "
                        "be checked at all. This is the check that matters most",
                        "run `python3 -m lib.sunmodel " + slug + "`"))
    for p in design.get("plants", []):
        out += check_light(p, sun, site)
        out += check_water(p, cond, site)
        out += check_soil(p, cond, site)
    out += check_sun_timing(design, sun, site)
    out += check_space(design, site, sun)
    out += check_coverage(design, site, cond, sun)
    out += check_vision(design, vis)
    out += check_season(design, vis, site)
    out += check_grouping(design)

    rank = {"blocking": 0, "serious": 1, "note": 2}
    out.sort(key=lambda o: rank[o["level"]])
    return out


def report(slug, force=False):
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

    objs = check(slug, force=force)
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
    ap.add_argument("--force", action="store_true",
                    help="check against a board with open doubts; the "
                         "objections come back flagged provisional")
    args = ap.parse_args()

    if args.init:
        if yards.load(args.slug, "design.json"):
            print(f"{args.slug} already has a design.json; not overwriting")
            return
        print(f"wrote {yards.save(args.slug, 'design.json', blank(args.slug))}")
        return
    if args.json:
        print(json.dumps(check(args.slug, force=args.force), indent=2))
        return
    report(args.slug, force=args.force)


if __name__ == "__main__":
    main()
