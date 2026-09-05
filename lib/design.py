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

A third optional field decides whether the plant is judged on winter light:

    winter_active   true where the plant carries live foliage through the dark
                    months and is expected to look like something. That is a
                    different claim from `evergreen`, which says only that the
                    leaves do not fall, and the two come apart in both
                    directions — a grass holding dry seed heads all winter
                    reads beautifully in December and photosynthesises none of
                    it, and a root-hardy shrub cut to the ground in November is
                    absent by design rather than failing. It wants a
                    `winter_active_why` beside it saying what settled it,
                    because it is a judgement about a plant rather than a
                    measurement of the yard.

A fourth says what was done to the ground under one planting:

    drainage_amendment  a mound, a raised pocket, a gravel bed — the position's
                    own answer to ground that drains too slowly for the plant
                    standing in it. It is a fact about THIS planting and not
                    about the plant, which is the whole point: the same
                    rosemary is a different proposition on a grit mound and
                    flush in clay, and a checker that cannot tell them apart
                    refuses a bed whose plan already answers it. It carries
                    `source`, and an amendment nobody has scheduled is worth
                    less than one somebody has.

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

from . import conditions, doubts, solar, vision as vision_mod, yards

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

# What makes a month hot enough for a scorch objection to be allowed to name it:
# the mean number of days in it that top 95 F, from the yard's own weather
# record. Six days is about one day in five, and the bar is there because a
# shade plant does not burn on a single hot afternoon — the claim the objection
# makes is about sustained heat, and a month with four hot days in it cannot
# support one.
#
# This is a policy threshold and not a fact about a yard, which is why it is
# here and why the series it is applied to is in `site.json`. `climate.heat`
# carried only an annual count, and an annual count cannot answer which months
# are hot: it was being quoted at a cyclamen lifted in March to prove it would
# scorch in July.
HOT_MONTH_DAYS = 6.0

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

# The months a winter-active plant's second light test is measured over, and
# again not a definition of its own — `solar.STANDING_SEASON` is the only one,
# and `lib.niches` reports a bed's winter figure over the same constant, so the
# number a person is shown when choosing for a bed is the number this module
# then judges the choice on.
WINTER_LIGHT_MONTHS = solar.STANDING_SEASON


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
    if ms == list(WINTER_LIGHT_MONTHS):
        return f"the standing season, {ms[0]}-{ms[-1]}"
    return ", ".join(ms)


def zone_best(sun, site, zone, months=None):
    vals = _series(sun, site, zone, months, "best_cell")
    return round(max(vals), 2) if vals else None


def hot_months(site):
    """The months this yard's own record says top 95 F often enough to burn.

    Returns None where the yard has never been asked, which is a third answer
    and not an empty list: a record with no monthly heat series cannot say
    whether July is hot here, and a coastal yard whose every month comes back
    under the bar genuinely has nothing to scorch anything. `check_coverage`
    reports the first case rather than letting the scorch check disappear.

    The fact lives in `site.json` because it is a fact about a place, and it is
    `derived` rather than assumed — `lib.climate --heat-months` decomposes the
    same thirty years of ERA5 daily maxima the annual count already came from,
    and prints the annual figure recomputed beside the stored one so the two can
    be seen to agree.
    """
    by_month = ((site.get("climate") or {}).get("heat") or {}) \
        .get("days_over_95f_by_month")
    if not isinstance(by_month, dict) or not by_month:
        return None
    return [m for m in MONTHS
            if (by_month.get(m) or 0) >= HOT_MONTH_DAYS]


def standing_months(plant):
    """The months the plant is physically in the ground, which is not its window.

    `check_light` judges a plant over `months`, else `bloom`, else the growing
    season, and that is the right window for asking whether it gets enough light
    to grow. It is the wrong window for asking whether it burns, and the two
    came apart in both directions at once on one yard:

      the cyclamen    lifted in March, judged over Dec-Mar, and told that
                      5.45 h of winter sun meant it would scorch in July
      the sedge       evergreen, judged over a Mar-Apr bloom, standing in the
                      bed all summer with nothing looking at August at all

    So `bloom` is not consulted here for anything perennial. A bloom list says
    when a plant flowers; it says nothing about when it is present, and using it
    as a proxy for presence is what hid August from an evergreen. `months` IS
    consulted, for annual and perennial alike, because a planting that states
    its own months has answered this question directly.
    """
    if plant.get("months"):
        return list(plant["months"])
    if plant.get("annual"):
        return list(plant.get("bloom") or DEFAULT_LIGHT_MONTHS)
    return list(MONTHS)


def _scorch(plant, want, need, sun, site):
    """A shade plant burning in the months it is standing through the heat.

    Two things were wrong with the version of this that read
    `climate.heat.days_over_95f_per_year`, and they compounded. The heat figure
    was annual, so it said "45.8 days over 95 F a year" for a plant that would
    be composted before the first of them; and the hour figure beside it was a
    mean over the plant's own window, so the sentence "it will scorch in July"
    was printed under a number that had never looked at July. Three of the four
    objections this raised on one yard were about plants that were either not
    there in summer or had been measured somewhere else in the calendar.

    The window is now the overlap of two things: the months the plant is
    standing in the ground, and the months this yard is hot. Where that overlap
    is empty the check says nothing, which is the whole of the cyclamen case.

    Where it is not empty the objection is decided on ONE month — the hottest
    the plant stands through — and it is the same month the sentence names. That
    identity is the point of the fix rather than a detail of it. The old message
    said July because July is when things burn, and measured whatever window the
    light check happened to be using, so the month in the claim and the month in
    the number had nothing to do with each other. Any version of this that
    triggers on one month and reports another brings the same bug back with
    better wording.

    Hottest rather than brightest, and that is a real choice with a real cost.
    Averaging the hot months together is out for the reason `_winter_light`
    gives: a mean over June, July and August dilutes the month that does the
    damage, and on one real bed it reports 4.48 h where August is 4.91. Taking
    the brightest instead is defensible and was tried, and it reads badly on the
    ground — g01 runs 8.96 h in June against 8.00 in August, so the objection
    came out naming June, a month with 7.1 days over 95 F, in preference to
    August's 18.2. Sun is what the bed has too much of and heat is what turns it
    into scorch, so the month worth judging is the one where the heat is worst
    and the sun figure is that month's own. What this gives up is the bed that is
    blazing in June and shaded by August; nothing on this yard is shaped that
    way, and an objection quoting June in Austin is one nobody would act on.
    """
    hot = hot_months(site)
    if not hot:
        return []
    by_month = ((site.get("climate") or {}).get("heat") or {}) \
        .get("days_over_95f_by_month", {})
    burn = [m for m in standing_months(plant) if m in hot]
    if not burn:
        return []
    zone = plant["zone"]
    worst = max(burn, key=lambda m: (by_month.get(m) or 0,
                                     zone_hours(sun, site, zone, [m]) or 0))
    have, days = zone_hours(sun, site, zone, [worst]), by_month.get(worst)
    if have is None or have <= need + SCORCH_MARGIN:
        return []
    return [_obj("serious", plant["name"],
                 f"is a {want} plant and it is standing in this bed through "
                 f"{worst}, the hottest month it is here for — {days} days over "
                 f"95 F in an average year, on a lot whose hot months are "
                 f"{', '.join(hot)}. Zone {zone} averages {have} h in {worst} "
                 f"against the {need} h its {want} rating wants. It will scorch "
                 f"in {worst} whatever the watering",
                 "move it to the shaded end, or give it afternoon "
                 "shade specifically — morning sun of the same length "
                 "is a different thing entirely")]


def winter_active(plant):
    """Whether this plant is working through the dark months, or just standing.

    `evergreen` is deliberately not the answer, and the temptation to use it is
    the whole reason this exists. It is a statement about leaves falling off,
    and the question the winter light check needs answered is whether the plant
    is photosynthesising and expected to look presentable while everything
    around it is dormant. On the yard this was written for, the two disagree in
    both directions at once: inland sea oats holds papery seed heads that are
    the best thing in the bed on 13 December and is `evergreen: false`, while
    an autumn sage flagged `evergreen: true` is semi-evergreen at best and gets
    nipped by a 28 F night.

    The other rejected mechanism was reading the `december` prose each entry
    carries — "ratty to dormant", "brown, deliberately", "absent by design".
    That prose is the EVIDENCE for setting this field and must not become the
    mechanism: it is free text written for a person, its wording will drift the
    first time somebody rewrites an entry, and a check that turns on the word
    "ratty" fails silently and in the direction of saying nothing.

    Returns None where nothing has been decided, which is a third answer and
    not a no — `check_coverage` reports it rather than guessing.
    """
    v = plant.get("winter_active")
    return v if isinstance(v, bool) else None


def _winter_light(plant, want, need, sun, site, already_short):
    """The second light test, for a plant that has to work through winter.

    A plant's own window is `months`, or failing that `bloom`. For anything
    that dies back that is right, and a dormant crown does not care what
    December is doing. For a plant still in leaf it is the wrong window, and
    wrong in a way that hides itself: bloom months are selected for being
    bright, so winter is not ignored but DILUTED. The four-nerve daisy in g04
    is judged over a bloom list of Mar-Jun plus Sep-Dec, clears its 4.0 h floor
    by 0.25 h, and reads 3.66 h across the months it is the only green thing in
    the bed.

    Two deliberate restraints, because a check that fires twice for one fault
    is the check somebody switches off.

    It says nothing where the plant is ALREADY refused for want of light on its
    own window. The rosemary in g03 blooms Nov-Mar, which is the standing
    season exactly, so its winter figure and its judged figure are the same
    3.06 h; a second objection would repeat a number and offer no new decision.

    And it offers no sunniest-cell escape. The primary check can honestly say
    "this may work in one corner", because its window is a season the plant is
    growing in throughout. Over a window whose entire point is that it contains
    the dark months, the brightest cell is by construction March's, and on g04
    that is 5.67 h against a bed reading 3.66 — offering it would be this
    check's own failure mode reappearing one level down, in the escape hatch.

    The level is `serious` and never `blocking`, which is a judgement and not
    an oversight. A plant here has already cleared the light it needs to grow;
    what it is short of is the light to look like something in the months it
    was planted to carry. That is the module's own definition of `serious` —
    it will survive and disappoint — and calling it blocking would put a thin
    winter rosette beside a shrub in soil that will kill it.
    """
    if winter_active(plant) is not True:
        return []
    zone = plant["zone"]
    have = zone_hours(sun, site, zone, list(WINTER_LIGHT_MONTHS))
    if have is None or have >= need or already_short:
        return []
    return [_obj("serious", plant["name"],
                 f"is marked winter-active, so it is in leaf through the dark "
                 f"months, and zone {zone} averages {have} h over "
                 f"{window_label(WINTER_LIGHT_MONTHS)} against the {need} h "
                 f"its {want} rating wants — {round(need - have, 2)} h short. "
                 f"It passes on its own window because those months are "
                 f"brighter. This is how it looks in winter rather than "
                 f"whether it lives",
                 "accept a thin winter on it and say so, move it to ground "
                 "that keeps its light past November, or carry this bed's "
                 "winter structure with something rated lower")]


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
    out += _winter_light(plant, want, need, sun, site, already_short=have < need)
    if want in ("shade", "part shade"):
        out += _scorch(plant, want, need, sun, site)
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


def rooting_depth(plant):
    """How deep this plant's feeding roots go, in inches, or None.

    A researched per-plant fact carried exactly like `light`, `ph_range` and
    `soil_drainage`, with a `rooting_depth_source` beside it. None where nobody
    has looked it up, which is a third answer and not a shallow one: a check
    that picks a depth in order to have one is the same bug as the yard-wide pH
    it exists to replace, one field along.

    A scalar rather than a range, and that is a deliberate narrowing. Roots vary
    with soil, season and how the plant was raised, and the honest interval for
    most of these is wide. But the question every caller asks is *which layers
    does this plant occupy*, the layers here are inches thick, and a range would
    put half the yard permanently in the maybe column while reading as more
    precise than the source it came from. The uncertainty goes where it can be
    argued with: `rooting_depth_source` says what the figure is, whose class it
    came from, and what claim the design is actually leaning on.
    """
    v = plant.get("rooting_depth_in")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        return None
    return float(v)


# What one layer says about one plant's pH range.
#
#   ok        this layer suits it, whatever else does
#   out       this layer does not, and the record is definite about that
#   depends   the layer's pH has never been measured, and the plant's range
#             covers part of what it plausibly is and not the rest
#   unknown   the layer's pH has never been measured and nothing says what it
#             plausibly is, so there is nothing to compare
#
# `depends` and `unknown` are separated from `out` because they are not
# findings about the plant, they are findings about the record, and
# `check_coverage` owns those. Rolling them into an objection would put a
# sentence about a plant in front of somebody when the thing that is wrong is
# that nobody has tested the soil.
PH_OK, PH_OUT, PH_DEPENDS, PH_UNKNOWN = "ok", "out", "depends", "unknown"


def ph_verdict(layer, rng):
    """Whether one layer suits a plant's pH range.

    A plausible band is consulted **only** where the layer carries no reading of
    its own, and never in place of one. That line is the difference between this
    and softening every objection on the yard: the native layer here has a
    value — an assumed, map-derived 8.2, but a value the whole plant palette was
    chosen against — and turning it into the 7.8-8.3 interval its own note
    quotes would drop every remaining pH objection to a shrug. A layer with
    nothing recorded is a different case, because the alternative there is not a
    weaker objection, it is no information at all.
    """
    if not rng or len(rng) != 2:
        return PH_OK
    lo, hi = float(rng[0]), float(rng[1])
    ph = layer.get("ph")
    if ph is not None:
        return PH_OK if lo <= float(ph) <= hi else PH_OUT
    band = layer.get("ph_plausible")
    if isinstance(band, (list, tuple)) and len(band) == 2:
        blo, bhi = float(band[0]), float(band[1])
        if lo <= blo and bhi <= hi:
            return PH_OK           # anything it plausibly is suits this plant
        if bhi < lo or blo > hi:
            return PH_OUT          # nothing it plausibly is would
        return PH_DEPENDS
    return PH_UNKNOWN


def ph_by_layer(plant, layers):
    """Every layer this plant's roots reach, with its verdict and how sure.

    Returns a list of `(layer, verdict, certain)`. Shared with `check_coverage`
    so that the objection and the report of what could not be checked are two
    readings of one computation rather than two implementations of one rule.
    """
    rng = plant.get("ph_range")
    if not rng:
        return []
    certain, possible = conditions.reached(layers, rooting_depth(plant))
    return ([(l, ph_verdict(l, rng), True) for l in certain]
            + [(l, ph_verdict(l, rng), False) for l in possible])


def _layer_name(layer):
    return str(layer.get("name") or layer.get("material") or "that layer")


def _layer_where(layer, depth):
    """`the native layer, from 6 in down` — with the share of the root zone."""
    top = float(layer.get("top_in") or 0)
    bottom = layer.get("bottom_in")
    span = (f"the top {bottom:g} in" if top <= 0 and bottom
            else f"the top of the bed" if top <= 0
            else f"from {top:g} in down")
    share = conditions.share_of_root_zone(layer, depth)
    if share is None:
        return f"the {_layer_name(layer)} layer, {span}"
    return (f"the {_layer_name(layer)} layer, {span}, which holds "
            f"{share * 100:.0f} percent of a {depth:g} in root zone")


def _ph_by_depth(plant, layers):
    """The pH objection, judged against the layers the roots are actually in.

    Only a `certain` verdict of `out` raises an objection here. Where the layer
    that does not suit the plant is one the roots *might* reach and nobody has
    researched the depth, the finding is that the depth is unresearched, and
    that belongs to `check_coverage` — an objection resting on a rooting depth
    this module chose for itself would be the yard-wide 8.2 all over again.
    """
    rng = plant.get("ph_range")
    bad = [(l, c) for l, v, c in ph_by_layer(plant, layers) if v == PH_OUT]
    if not any(c for _, c in bad):
        return []
    depth = rooting_depth(plant)
    where = "; ".join(_layer_where(l, depth) for l, c in bad if c)
    reads = "; ".join(
        (f"{l['ph']}" if l.get("ph") is not None
         else f"plausibly {l['ph_plausible'][0]}-{l['ph_plausible'][1]}")
        for l, c in bad if c)
    rooted = (f"roots {depth:g} in" if depth else "roots into the surface layer")
    return [_obj("serious", plant["name"],
                 f"wants pH {rng[0]}-{rng[1]} and {rooted}, which puts it in "
                 f"{where} — reading {reads}. The imported soil above is not "
                 f"the whole of what this plant is standing in",
                 "amending pH is a losing fight in open ground and a deeper "
                 "imported layer only postpones it. Either choose something "
                 "suited to the layer the roots reach, or grow this one in a "
                 "container where the medium is yours")]


def check_soil(plant, cond, site=None):
    """Whether the soil suits the plant — where the plant is in soil at all.

    A container is not the ground. Its medium is whatever gets put in it, so
    holding a potted plant to the yard's pH refuses it for a reason that does
    not apply — and this function's own advice for a pH mismatch is to *grow it
    in a container where the medium is yours*, which it then objected to.

    Where the bed has a layered record the checks run against the layers, and
    the two arms deliberately part company. pH is asked of the layers the roots
    are in; drainage is asked of the profile, because water leaves through the
    slowest layer whatever the rooting depth. See `lib.conditions`.
    """
    out = []
    key = plant.get("zone")
    if site is not None and key:
        key = resolve_site_zone(site, key) or key
        if zone_kind(site, key) == "container":
            return out
    soil = (cond or {}).get("soil") or {}
    layers = conditions.bed_layers(cond, key)

    if layers:
        out += _ph_by_depth(plant, layers)
    else:
        ph = soil.get("ph")
        rng = plant.get("ph_range")
        if ph is not None and rng and not (rng[0] <= ph <= rng[1]):
            out.append(_obj("serious", plant["name"],
                            f"wants pH {rng[0]}-{rng[1]} and the soil reads "
                            f"{ph}",
                            "amending pH is a losing fight in open ground. "
                            "Either choose something suited to the soil, or "
                            "grow this one in a container where the medium is "
                            "yours"))

    if plant.get("soil_drainage") == "sharp":
        if layers:
            out += _sharp_by_depth(plant, layers)
        else:
            drain = (soil.get("drainage") or "").lower()
            if "slow" in drain or "poor" in drain:
                out += _sharp_drainage(plant, drain)
    return out


def _sharp_by_depth(plant, layers):
    """A sharp-drainage plant over a layered profile.

    Depth is asked and deliberately does not change the answer, which is the
    whole content of this function. Six inches of good soil over group D clay
    does not drain: the clay is where the water has to go, it cannot, and the
    water stands upward from that interface. A plant rooting entirely in the
    imported layer is therefore inside the perched zone rather than above it,
    and reading across from the pH rule — shallow roots, imported soil, no
    objection — would be exactly wrong. What depth buys is a better sentence,
    not a different verdict.
    """
    lim = conditions.limiting_layer(layers)
    if lim is None:
        return []
    drain = str(lim.get("drainage") or "").lower()
    top = float(lim.get("top_in") or 0)
    depth = rooting_depth(plant)
    above = [l for l in layers if float(l.get("top_in") or 0) < top]
    over = (f"{top:g} in of {_layer_name(above[0])} soil over "
            f"{_layer_name(lim)}" if above and top > 0
            else f"{_layer_name(lim)} from the surface")
    where = (f", and it roots {depth:g} in, so it is "
             + ("inside" if depth <= top else "through")
             + " the layer that perches" if depth else "")
    ground = (f"this bed is {over}, which drains {drain}. Water leaves through "
              f"the slowest layer whatever the rooting depth, and it stands "
              f"upward from that interface{where}")
    return _sharp_drainage(plant, drain, ground=ground)


def drainage_amendment(plant):
    """What was done to the ground under this planting, where anything was.

    A dict or None. Read `describe` for the shape of it.
    """
    a = plant.get("drainage_amendment")
    return a if isinstance(a, dict) and a.get("describe") else None


def _sharp_drainage(plant, drain, ground=None):
    """A sharp-drainage plant in slow ground, and whether the plan answers it.

    Without this the objection is unanswerable, which is a specific and bad
    kind of wrong: the fix it printed was *plant it on a mound with grit*, and
    on this yard that mound was already designed, dated, funded and on the
    shopping list before the objection was ever raised. So the check refused
    nine plants and then recommended the thing the plan already said to do, on
    every run, forever. An objection that cannot be satisfied by doing the
    right thing is one people learn to scroll past, and the next real one goes
    with it.

    What it deliberately does NOT do is decide that a mound is enough. Nobody
    knows that — the drainage reading here is `assumed` and the percolation
    test has been declined twice. The amendment moves the objection from a
    claim about the SOIL, which the plan cannot change, to a claim about a
    TASK, which can be checked, slip, or be dropped. That is a better place for
    the risk to sit and it is not the same as the risk going away, so the note
    says what the plant is depending on and where to find it.

    Three levels, and the difference between them is evidence and not severity:

      blocking   nothing recorded. Unchanged, and this is still the right
                 answer where the ground is slow and nobody has said otherwise.
      serious    an amendment asserted with no `source`. Weaker than nothing
                 recorded would be honest about, because it reads like an
                 answer while resting on nobody, so it is called out rather
                 than believed.
      note       an amendment with a source. The design is answered; what is
                 left is doing it.

    `ground` is the sentence describing what is wrong with the soil. It is a
    parameter so that a layered bed can say which layer perches and how deep it
    is, through the same three levels rather than a second copy of them; the
    default is the flat reading every yard had before profiles existed.
    """
    a = drainage_amendment(plant)
    ground = ground or f"the soil drains {drain}"
    if not a:
        return [_obj("blocking", plant["name"],
                     f"needs sharp drainage and {ground}. This "
                     f"is the classic way to kill rosemary and lavender, and "
                     f"it takes two years so nobody connects it to the soil",
                     "plant it on a mound or in a raised pocket with grit, "
                     "with the crown set high, and record it as a "
                     "`drainage_amendment` on the planting so this check can "
                     "see it")]
    src = [s for s in (a.get("source") or []) if str(s).strip()]
    if not src:
        return [_obj("serious", plant["name"],
                     f"needs sharp drainage, {ground}, and the "
                     f"planting claims {a['describe']} — but nothing says "
                     f"where that is written down, so there is no way to tell "
                     f"whether it is a plan or a hope. An amendment nobody has "
                     f"scheduled is not one",
                     "add `source` to the amendment pointing at the task or "
                     "plan line that builds it, or drop the claim and let the "
                     "drainage objection stand")]
    return [_obj("note", plant["name"],
                 f"needs sharp drainage and {ground}, and it is "
                 f"planted on {a['describe']} — {', '.join(str(s) for s in src)}"
                 + (f". {a['why']}" if a.get("why") else "")
                 + f". The soil objection is answered by the planting position "
                   f"rather than by the ground, so this plant lives or dies on "
                   f"that being built as written",
                 f"if that step is dropped or skipped on the day, this plant "
                 f"goes into the ground it was refused for")]


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
#
# Which is worth reading twice, because it is also how this check went blind.
# Sharing the band means a slate assembled there lands inside it here BY
# CONSTRUCTION — the two cannot disagree about area, so their agreement about
# area says nothing. `bed_g05` was handed three rows summing to 6.5 ft of
# spread in a bed 3.708 ft deep and passed at 1.10x, because 1.10x was the only
# question either side asked. Anything the band cannot see has to be measured
# on a different axis, against a different number, or it is not measured at
# all. `row_stack` below is that axis.
COVER_FLOOR, COVER_CEILING = 0.45, 1.15

# The ranks of a border, back to front, as `layer` records them on a plant.
# Anything else — an `accent`, or a typo — is still standing in the bed and
# still occupying depth, so it is counted as a band of its own and NAMED, never
# quietly dropped. A guard that skips what it does not recognise is how seven
# `lib.schedule` archetypes went unreachable reading `kind` where the design
# wrote `item`.
ROWS = ("back", "middle", "front")


def row_stack(plants):
    """(depth_ft, ranks) — the depth a layered planting consumes front to back.

    Ranks in a border do not interleave. A rank whose widest plant spreads *s*
    feet occupies *s* feet of the bed's depth, because the rank behind it has to
    stand clear of it or it shades the one in front out, which is the entire
    point of planting in layers. Put the centres at (s_back + s_front) / 2 apart
    — the closest they can be — and add the half-spread hanging off each end,
    and the total comes to exactly the SUM of the ranks' spreads. Three rows at
    2.5, 2.5 and 1.5 ft need 6.5 ft of depth. There is no arrangement of them
    that needs less.

    No area calculation can find that, and this is the second axis rather than a
    refinement of the first: 32.45 sq ft of bed holds 35.7 sq ft of plants at
    1.10x, comfortably inside the coverage band, in a bed 3.708 ft deep. The two
    numbers are not in tension because they are not about the same thing.

    A rank is as deep as its WIDEST member, not as deep as its mean. Six plants
    in the back row of g02 spread 1.2 to 3.0 ft; the band has to be 3.0 ft wide
    where the plateau goldeneye stands, and the slack elsewhere along the run is
    length, not depth. Taking the max is also the lenient reading, which is the
    right direction for a check that objects.

    Vines are excluded on the same grounds `footprint` excludes them: the canopy
    is carried on a trellis overhead and the ground under it still plants.
    """
    ranks = {}
    for p in plants:
        layer = p.get("layer")
        if layer == "vine":
            continue
        spread = p.get("mature_spread_ft") or 0
        if not spread:
            continue
        # Every unrecognised layer shares one band rather than getting one
        # each: three plants filed `accent` are three plants in the same rank
        # until somebody says otherwise, and inventing three ranks out of one
        # word would object to a bed that is fine.
        key = layer if layer in ROWS else "other"
        wide, name, count = ranks.get(key, (0.0, None, 0))
        if float(spread) > wide:
            wide, name = float(spread), p.get("name")
        ranks[key] = (wide, name, count + 1)
    order = ROWS + ("other",)
    out = [(k, ranks[k][0], ranks[k][1], ranks[k][2])
           for k in order if k in ranks]
    return row_stack_depth([d for _k, d, _n, _c in out]), out


def row_stack_depth(spreads):
    """The depth a set of ranks consumes. Named so both modules read one rule.

    `lib.niches` spends this budget when it proposes rows and `check_space`
    measures it against what was actually planted, and they must not each carry
    their own copy of the arithmetic — that is how `check_space` and
    `lib.niches` came to agree about g05's area while both were wrong about it.

    One rule in one place is not the same as two modules agreeing, and the
    difference is what they feed it: niches feeds it the MIDPOINT spread of a
    size class, `check_space` feeds it the spread of the plant somebody actually
    bought. A slot that fits at the midpoint of `medium` fails at the top of it,
    and the linter is where that surfaces.
    """
    return sum(float(s) for s in spreads)


def depth_room(site, key):
    """Feet of depth a rank stack may occupy in this zone.

    Usable depth plus whatever canopy overhang the zone declares, which is the
    same allowance `_check_depth` already gives an individual plant and for the
    same reason: a top may lean out over a stone apron its roots could never
    occupy. Undeclared means none, deliberately — whether the front rank may
    lean out over what is in front of the soil is a judgement about how the bed
    should look, not something recoverable from the measurements, so the
    objection names the declaration as its remedy rather than assuming a figure.
    """
    z = (site.get("zones") or {}).get(key) or {}
    depth = z.get("usable_depth_ft")
    if not depth:
        return None
    return float(depth) + z_overhang(site, key)


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
        out += _check_row_depth(z, plants, site, key)
    return out


def _check_row_depth(zone, plants, site, key):
    """The ranks, added up, against the depth there is. See `row_stack`.

    `_check_depth` below asks whether any ONE plant is wider than the bed, which
    is a real question and a narrower one: every plant in g05's derived slate
    passes it — 2.5, 2.5 and 1.5 ft in a bed 3.708 ft deep, not one of them
    over — and the three of them together need 6.5 ft. What a layered planting
    consumes is the sum, and nothing was reading it.
    """
    room = depth_room(site, key)
    if not room:
        return []
    stack, ranks = row_stack(plants)
    # One rank is `_check_depth`'s question with extra words. Reported there,
    # against the individual plants, where the remedy is per plant.
    if len(ranks) < 2 or stack <= room:
        return []

    z = (site.get("zones") or {}).get(key) or {}
    depth = float(z.get("usable_depth_ft"))
    named = ", ".join(
        f"{k} {d:g} ft" + (f" ({n})" if n else "")
        for k, d, n, _c in ranks)
    allowed = ("" if room == depth else
               f" — {depth:g} ft of usable depth plus the {room - depth:g} ft "
               f"of overhang this zone allows the front rank to lean out over")
    unranked = next((c for k, _d, _n, c in ranks if k == "other"), 0)
    guessed = ""
    if unranked:
        layers = sorted({str(p.get("layer")) for p in plants
                         if p.get("layer") not in ROWS
                         and p.get("layer") != "vine"
                         and (p.get("mature_spread_ft") or 0)})
        guessed = (f" {unranked} of these "
                   f"{'is' if unranked == 1 else 'are'} filed as "
                   f"{', '.join(repr(x) for x in layers)} rather than as one of "
                   f"{', '.join(ROWS)}, so they were counted as a single band "
                   f"of their own; if they in fact stand within another rank, "
                   f"say so with `layer` and this number falls.")
    return [_obj("serious", f"zone {zone}",
                 f"the ranks add up to {stack:g} ft of depth and the bed has "
                 f"{room:g}{allowed}. That is {stack / room:.2f}x on depth, "
                 f"against {named}, each rank as deep as its widest plant. "
                 f"Area is not the constraint and cannot see this: the ranks "
                 f"cannot overlap without the back one shading out the front "
                 f"one, so what a layered bed consumes is the sum."
                 + guessed,
                 f"lose a rank, or take the widest rank down a size class — "
                 f"{stack - room:g} ft has to come out of the stack. Setting "
                 f"`canopy_overhang_ft` on the zone is the other answer, and "
                 f"only if the front rank may really lean out over whatever is "
                 f"in front of the soil")]


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
    # over ground its roots could never occupy. One helper, because
    # `_check_row_depth` needs the same figure and two copies of "depth plus
    # whatever overhang is declared" is one copy too many.
    reach = depth_room(site, key)
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

    # --- light, and which season it was judged over
    #
    # Not a missing input, which is what the rest of this function reports, but
    # the same silence: a plant carrying neither `months` nor `bloom` is judged
    # over `DEFAULT_LIGHT_MONTHS`, and the objection list gives no sign of it.
    # On the yard this was written against, thirteen autumn-sown vegetables were
    # measured over the seven months not one of them was in the ground - 6.46 h
    # against 5.41 h for their own season - and it took someone reading three
    # confident objections about spinach scorching in July to notice.
    #
    # A default is the right behaviour and this does not change it. What it
    # changes is that the default stops being invisible.
    defaulted = [p["name"] for p in plants
                 if p.get("zone") and (p.get("light") or "").lower() in LIGHT_NEED
                 and not p.get("months") and not p.get("bloom")]
    if defaulted:
        out.append(_obj("note", "light",
                        f"{len(defaulted)} plants name neither their growing "
                        f"months nor a bloom season, so their light was judged "
                        f"over {window_label(None)} — "
                        f"{', '.join(sorted(defaulted)[:6])}"
                        + (" and others" if len(defaulted) > 6 else "")
                        + ". For anything whose season is winter that is the "
                          "wrong half of the year, and it reads as a verdict "
                          "either way",
                        "set `months` on each from whatever document owns its "
                        "dates, listing the months one by one so a season that "
                        "crosses New Year does not come out empty"))

    # --- heat, and whether the scorch check could run at all
    #
    # The same silence as the section above, and this one used to be worse than
    # silence: the check ran on an annual hot-day count, which every hot climate
    # has, and so it never went quiet and never named a month. Requiring a
    # monthly series means a yard that has not got one gets no scorch objections
    # at all, and that has to be said out loud or the check has simply vanished.
    tender = [p for p in plants
              if p.get("zone") and (p.get("light") or "").lower()
              in ("shade", "part shade")]
    if hot_months(site) is None and tender:
        out.append(_obj("note", "heat",
                        f"no monthly hot-day series on record, so nothing "
                        f"checked whether {len(tender)} shade-rated plants are "
                        f"standing in too much sun in the months this yard is "
                        f"actually hot. An annual count of days over 95 F "
                        f"cannot answer that: it is the same figure in a yard "
                        f"whose plant is lifted in March",
                        "run `python3 -m lib.climate " + (site.get("yard") or
                        "<slug>") + " --heat-months`, which derives it from the "
                        "same thirty years the annual count came from"))

    # --- winter, and which plants nobody has decided about
    #
    # The same silence one field over. `winter_active` governs whether a plant
    # is judged on winter light at all, and an entry that has never been asked
    # the question is indistinguishable in the objection list from one that was
    # asked and answered no.
    #
    # `evergreen: true` is the prompt here and deliberately not the mechanism.
    # It is where the question ARISES — something that keeps its leaves is
    # worth deciding about — and using it as the answer is what this whole
    # field exists to avoid, because it would object about four plants that are
    # brown, cut to the ground or standing in dry seed heads and do not care
    # what December is doing.
    undecided = [p["name"] for p in plants
                 if p.get("evergreen") and p.get("zone")
                 and (p.get("light") or "").lower() in LIGHT_NEED
                 and winter_active(p) is None]
    if undecided:
        out.append(_obj("note", "winter",
                        f"{len(undecided)} plants keep their leaves and none "
                        f"of them says whether it is actually working through "
                        f"winter, so the winter light check did not run for "
                        f"them — {', '.join(sorted(undecided)[:6])}"
                        + (" and others" if len(undecided) > 6 else "")
                        + ". Evergreen is not the same claim: a grass holding "
                          "dry seed heads looks like winter and needs no light "
                          "for it",
                        "set `winter_active` on each, with a "
                        "`winter_active_why` saying what settled it — the "
                        "entry's own December note is usually the evidence"))
    unsourced = [p["name"] for p in plants
                 if winter_active(p) is not None
                 and not str(p.get("winter_active_why") or "").strip()]
    if unsourced:
        out.append(_obj("note", "winter",
                        f"{len(unsourced)} plants declare `winter_active` with "
                        f"no reason beside it — "
                        f"{', '.join(sorted(unsourced)[:6])}"
                        + (" and others" if len(unsourced) > 6 else "")
                        + ". It is a judgement about a plant rather than a "
                          "measurement of the yard, so an undefended one is a "
                          "verdict nobody can disagree with",
                        "add `winter_active_why` naming the evidence"))

    # --- soil, layer by layer
    #
    # Three silences, and they are the ones this whole mechanism creates. The
    # depth-aware pH check is quieter than the yard-wide one it replaces, and
    # most of that quiet is correct — a viola rooting five inches into imported
    # garden soil was never in the caliche. But some of it is a check that could
    # not run, and if that is invisible then the yard has traded a confidently
    # wrong answer for a confidently blank one, which is the worse trade.
    #
    # Aggregated per finding rather than per plant, the same as everything else
    # here. Nineteen lines saying "nobody has measured the imported soil" is
    # nineteen ways of not reading it once.
    out += check_layer_coverage(plants, site, cond)

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


def _bed_key(site, zone):
    """The site's own key for a design zone, or the design's key unchanged.

    `site` is optional here for the same reason it is optional on `check_soil`:
    the layered record is keyed by bed and a caller that only has beds should
    not have to fabricate a site to ask about them.
    """
    if site is None:
        return zone
    return resolve_site_zone(site, zone) or zone


def check_layer_coverage(plants, site, cond):
    """What the depth-aware soil check could not settle, said out loud.

    The pH arm of `check_soil` now answers a narrower question than the yard-wide
    scalar did, and it answers it correctly for far fewer plants. Everything it
    stops saying has to land somewhere, and there are exactly three places it
    can land: the layer suits the plant (silence is right), the layer's pH has
    never been measured (nobody knows), or the plant's rooting depth has never
    been researched (nobody looked). Only the first of those is a pass.
    """
    out = []
    unmeasured, no_depth, blank_layer, unprofiled = [], [], [], []
    discontinuous = {}
    any_profile = bool(((cond or {}).get("soil", {}).get("layers") or {})
                       .get("profiles"))

    for p in plants:
        zone = p.get("zone")
        if not zone:
            continue
        key = _bed_key(site, zone)
        if site is not None and zone_kind(site, key) == "container":
            continue
        layers = conditions.bed_layers(cond, key)
        if layers is None:
            if any_profile and p.get("ph_range"):
                unprofiled.append(key)
            continue
        if key not in discontinuous:
            gaps = conditions.layer_gaps(layers)
            if gaps:
                discontinuous[key] = gaps
        for layer, verdict, certain in ph_by_layer(p, layers):
            if verdict == PH_DEPENDS:
                unmeasured.append(p["name"])
            elif verdict == PH_UNKNOWN:
                blank_layer.append(p["name"])
            elif verdict == PH_OUT and not certain:
                no_depth.append(p["name"])

    if unmeasured:
        names = sorted(set(unmeasured))
        out.append(_obj("note", "soil",
                        f"{len(unmeasured)} plantings root in an imported "
                        f"layer whose "
                        f"pH has never been measured, and their own range "
                        f"covers part of what that layer plausibly is and not "
                        f"the rest — {', '.join(names[:6])}"
                        + (" and others" if len(names) > 6 else "")
                        + ". They are not passing the pH check; the pH check "
                          "cannot run on them. A bagged garden soil at the acid "
                          "end of its plausible band sits under the floor these "
                          "state",
                        "one lab test settles the whole list. Sample the "
                        "imported layer separately from the native one, or the "
                        "blend destroys the distinction that makes this "
                        "answerable"))
    if blank_layer:
        names = sorted(set(blank_layer))
        out.append(_obj("note", "soil",
                        f"{len(blank_layer)} plantings root in a layer that "
                        f"records "
                        f"neither a pH nor a plausible range, so nothing could "
                        f"be compared at all — {', '.join(names[:6])}"
                        + (" and others" if len(names) > 6 else ""),
                        "set `ph` on the layer where it has been measured, or "
                        "`ph_plausible` with a source where it has not. A layer "
                        "with neither disables the check silently"))
    if no_depth:
        names = sorted(set(no_depth))
        out.append(_obj("note", "soil",
                        f"{len(no_depth)} plantings would be refused by a "
                        f"layer their "
                        f"roots may or may not reach, and no `rooting_depth_in` "
                        f"is on record for them — {', '.join(names[:6])}"
                        + (" and others" if len(names) > 6 else "")
                        + ". The objection was not raised, because raising one "
                          "on a depth this module picked for itself is the same "
                          "fault as the yard-wide pH it replaced",
                        "set `rooting_depth_in` and `rooting_depth_source` on "
                        "each, from an effective-root-zone table rather than "
                        "from the plant's height"))
    for bed, gaps in sorted(discontinuous.items()):
        out.append(_obj("note", "soil",
                        f"{bed}'s profile does not join up: {'; '.join(gaps)}. "
                        f"Every verdict here is decided from `top_in`, so this "
                        f"changes no objection and is reported for that reason "
                        f"— the boundary is stated twice and only one of the "
                        f"two is being believed",
                        "make each layer's `bottom_in` the next layer's "
                        "`top_in`, and leave the deepest layer's `bottom_in` "
                        "null so it runs past anything that will be planted"))
    if unprofiled:
        beds = sorted(set(unprofiled))
        out.append(_obj("note", "soil",
                        f"{', '.join(beds)} carries plants that state a pH "
                        f"range and has no entry in `soil.layers.beds`, so it "
                        f"was judged on the yard-wide scalar while the other "
                        f"beds were judged layer by layer. Two rules on one "
                        f"yard is worse than either",
                        "add the bed to `soil.layers.beds`, naming the profile "
                        "it actually has"))
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
