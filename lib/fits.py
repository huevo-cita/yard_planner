#!/usr/bin/env python3
"""Would this plant go anywhere in this yard — asked standing in a nursery.

    python3 -m lib.fits <slug> --plant "gulf muhly"    one plant, every place
    python3 -m lib.fits <slug> --all                   every plant that fits
    python3 -m lib.fits <slug> --tag                   check by nursery tag alone
    python3 -m lib.fits <slug> --card                  -> FITS.html, for the phone
    python3 -m lib.fits <slug> --intake queued.json    absorb what the phone queued

Why this exists
---------------
The yard already knows which plants suit it. `lib.niches` groups the ground by
what will grow in it, and `_rejects` judges a candidate against a niche. But
both of those run at a desk, on a slate somebody researched in advance. The
question this module answers arrives at the wrong moment and in the wrong
place: a person is holding a pot in a shop, twenty minutes from home, and wants
to know whether it goes anywhere.

Nothing here re-implements the horticulture. Three real linter calls decide it:

    niches._rejects   light over the plant's own months, mature spread against
                      the bed's depth, and the row's share of the bed
    design.check_soil pH judged against the layers the roots actually reach,
                      and sharp drainage judged against the whole profile
    design.check_water whether a hose reaches, and whether the bed is in the
                      rain shadow of a roof

The soil block is deliberately stripped out of the niche before `_rejects` sees
it. That is not dropping the soil question, it is asking it once and asking it
the better way: `niches.json` caches a flat per-niche pH carrying the *native*
layer's figure, and every bed on a yard like cloverleaf has six inches of
imported soil above that. `design.check_soil` reads `conditions.soil.layers`
and judges the layer a plant is actually rooting in. The two disagree for most
of the acid-side palette, which is filed as a doubt on that yard's board.

Where the answers come from
---------------------------
Plant facts come from a regional catalog under `catalog/`, which holds no
address and belongs to no yard. Place facts come from the yard: the niches in
`niches.json` with their slot budgets, and the yard-scale areas from
`sun-hours.json`, which are real ground a tree could go in and which no niche
covers.

This job is never gated. It is read-only, it plans nothing and it buys nothing,
so it belongs with the cheap paths in AGENTS.md — refusing to answer while
somebody is standing in an aisle would only teach them to stop asking. What it
does instead is say on the face of every answer what it was computed from, and
`--card` warns when the sun model has moved since the last card was built.
"""
import argparse
import datetime
import hashlib
import json
import os
import re

from . import design, doubts, niches, solar, yards

CATALOG_DIR = os.path.join(yards.REPO_ROOT, "catalog")
TODAY = datetime.date.today().isoformat()

# The three answers, and the middle one is the reason there are three. A plant
# that suits a bed perfectly well and has nowhere to go in it is not a refusal
# — the ground is right and the rows are spoken for — and reporting it as one
# sends somebody home from a shop having learnt the wrong thing.
FITS, FULL, NO = "fits", "fits-no-room", "no"

# Root zones for a plant checked from its nursery tag alone, since a tag never
# states one and `design.ph_by_layer` needs it to know which layers to judge.
# Keyed by mature spread, which is the only size a tag reliably gives. Coarse
# on purpose: the layers here are inches thick and the question is only which
# side of six inches the roots come down on.
TAG_ROOT_DEPTH = [(1.0, 8.0), (2.0, 12.0), (4.0, 18.0), (8.0, 24.0)]
TAG_ROOT_DEEP = 36.0

TAG_SPREADS = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 20.0]
TAG_ACID_RANGE = [4.5, 6.0]

# Trailing clauses the linters add for a reader at a desk, which are exactly
# wrong for a reader in a shop. Stripped from the short line only; the full
# reason keeps every word, because the short line is a summary and the argument
# has to stay somewhere a person can go and read it.
_TRAIL = re.compile(r",? (which is the figure [^.]*|and design\.py says so"
                    r"|which the linter then rejects[^.]*)", re.I)


# ------------------------------------------------------------------ catalog

def catalogs():
    """Every regional catalog on disk, by region id."""
    out = {}
    if not os.path.isdir(CATALOG_DIR):
        return out
    for name in sorted(os.listdir(CATALOG_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(CATALOG_DIR, name)) as fh:
            data = json.load(fh)
        out[data.get("region") or name[:-5]] = data
    return out


def region_for(slug, site=None):
    """Which catalog covers this yard, from the county its address names.

    The county rather than the coordinate, because a bounding box for a plant
    region would be a second geography to maintain and would put a rooftop
    latitude into a file that is otherwise free of one.
    """
    site = site if site is not None else (yards.load(slug, "site.json") or {})
    addr = site.get("address") or {}
    county = (addr.get("county") or "").strip().lower()
    street = (addr.get("street") or "")
    for region, cat in catalogs().items():
        counties = [c.lower() for c in (cat.get("counties") or [])]
        if county and county in counties:
            return region
        for st in cat.get("states") or []:
            if county and county in counties and f" {st} " in f" {street} ":
                return region
    return None


def load_catalog(region):
    cats = catalogs()
    if region not in cats:
        have = ", ".join(sorted(cats)) or "none"
        raise SystemExit(f"no catalog {region!r} under catalog/. Have: {have}")
    data = cats[region]
    seasons = data.get("seasons") or {}
    for p in data.get("plants") or []:
        # `season` is the catalog's shorthand for the months a plant is in
        # active growth. It is expanded here, once, so that `_rejects` sees the
        # same `months` field a hand-researched slate would carry and no check
        # downstream has to know the shorthand exists.
        if not p.get("months"):
            window = seasons.get(p.get("season"))
            if isinstance(window, list):
                p["months"] = list(window)
        p["name"] = p.get("name") or (p.get("names") or [p["botanical"]])[0]
    return data


def find(catalog, query):
    """Every plant matching a name, best first. Never guesses between two.

    Returns a list because "sage" is four different plants in this catalog and
    picking one of them silently is how somebody buys the wrong thing. An exact
    name match short-circuits; otherwise every substring hit comes back and the
    caller asks.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    exact, starts, holds = [], [], []
    for p in catalog.get("plants") or []:
        names = [p["botanical"]] + list(p.get("names") or [])
        low = [n.lower() for n in names]
        if q in low:
            exact.append(p)
        elif any(n.startswith(q) for n in low):
            starts.append(p)
        elif any(q in n for n in low):
            holds.append(p)
    return exact or (starts + holds)


# ------------------------------------------------------------------- places

def places(slug, site=None, sun=None, cond=None, nich=None):
    """Every piece of ground a plant could go in, beds and open yard alike.

    Two kinds, and they are judged by the same rules with different budgets.

    A **bed** comes from `niches.json` and carries its slots, so the answer can
    tell a plant that does not suit the ground from one that suits it and has
    no row left to stand in.

    An **area** is a yard-scale zone from the sun model — the front, the back,
    the court, the two sides. No niche covers these because nothing has been
    designed there, and leaving them out would mean a shrub or a tree came back
    "fits nowhere" while half the lot sat empty. They get one open slot with no
    count and no share, which makes `_rejects` skip the row-budget arm, and no
    usable depth, which makes it skip the depth arm. Both are right: open
    ground has no row to overdraw and no back edge to outgrow.
    """
    site = site if site is not None else (yards.load(slug, "site.json") or {})
    sun = sun if sun is not None else (yards.load(slug, "sun-hours.json") or {})
    cond = cond if cond is not None else (yards.load(slug, "conditions.json") or {})
    nich = nich if nich is not None else (yards.load(slug, "niches.json") or {})

    out = []
    for n in nich.get("niches") or []:
        zone = (n.get("zones") or [n.get("id")])[0]
        out.append({"id": n["id"], "label": n.get("label") or n["id"],
                    "kind": "bed", "zone": zone, "niche": n,
                    "slots": list(n.get("slots") or []) or [_open_slot(n["id"])],
                    "hours": (n.get("light") or {}).get("hours"),
                    "category": (n.get("light") or {}).get("category"),
                    "area_sqft": n.get("area_sqft"),
                    "depth_ft": n.get("usable_depth_ft")})

    covered = {z for p in out for z in (p["niche"].get("zones") or [])}
    areas = design.zone_areas(site)
    for key, z in (site.get("zones") or {}).items():
        if key in covered or not isinstance(z, dict):
            continue
        hours = design.zone_hours(sun, site, key)
        if hours is None:
            continue
        out.append({"id": key, "label": z.get("label") or key,
                    "kind": "area", "zone": key,
                    "niche": _area_niche(key, z, hours, cond),
                    "slots": [_open_slot(key)],
                    "hours": hours, "category": design._label_for(hours),
                    "area_sqft": areas.get(key) or _span_area(z),
                    "depth_ft": None,
                    "style": z.get("style")})
    return out


def _span_area(zone):
    """Square feet from a zone's own x and y spans, in inches.

    Only where `design.zone_areas` found nothing, and only ever for display.
    The yard-scale zones are rectangles over the site frame rather than beds
    with a measured area, and a gross footprint is worth printing beside the
    light figure even though nothing budgets against it.
    """
    x, y = zone.get("x"), zone.get("y")
    if not (isinstance(x, list) and isinstance(y, list)
            and len(x) == 2 and len(y) == 2):
        return None
    return round(abs((x[1] - x[0]) * (y[1] - y[0])) / 144.0, 1)


def _open_slot(place_id):
    """A slot with no row budget and no pick, so only the ground is judged."""
    return {"id": f"{place_id}.open", "layer": "open", "count": None,
            "budget_share": None, "spread_ft": None}


def _area_niche(key, zone, hours, cond):
    water = (cond or {}).get("water") or {}
    return {"id": key, "label": zone.get("label") or key, "zones": [key],
            "kind": "area", "area_sqft": None,
            "usable_depth_ft": None, "overhang_ft": None,
            "light": {"hours": round(hours, 2),
                      "category": design._label_for(hours)},
            "soil": {},
            "water": {"hose_reaches": water.get("hose_reaches"),
                      "irrigated": bool(water.get("irrigation")),
                      "rain_shadow": False}}


def _no_soil(niche):
    """The niche with its cached soil block emptied.

    `_rejects` compares a candidate's `ph_range` against one flat number per
    niche, and that number is the native layer's. `design.check_soil` asks the
    same question of the layer the roots reach. Running both would refuse a
    plant twice on one fact and refuse it on the worse of the two readings, so
    the flat arms are made inert here and the layered check owns the question.
    """
    n = dict(niche)
    n["soil"] = {}
    return n


# ---------------------------------------------------------------- verdicts

def evaluate(plant, place, site, sun, cond):
    """Whether this plant goes in this place, and the sentence that says why.

    Every slot in the place is tried, because a bed refuses a plant row by row:
    a shrub that overdraws the front edging may sit perfectly well in the back
    rank. The place refuses the plant only when every row does.
    """
    p = dict(plant)
    p["zone"] = place["zone"]
    niche = _no_soil(place["niche"])

    # The number that actually decides, recovered here rather than taken from
    # the niche. `niches.json` caches one growing-season mean per niche, and
    # `_rejects` judges a plant over the plant's OWN months — Mar to Nov for a
    # perennial, all twelve for an evergreen, Oct to Feb for a winter crop. A
    # margin quoted from the cached figure would therefore be a margin against
    # a number no check consulted, which is exactly the confusion the niche
    # `series` block exists to prevent.
    months = p.get("months") or p.get("bloom") or None
    judged = design.zone_hours(sun, site, place["zone"], months)
    ctx = {"judged_h": judged if judged is not None else place["hours"],
           "window": window_short(months),
           "needs_h": design.LIGHT_NEED[(p["light"] or "").lower()][0]}

    passed, refused = [], {}
    for slot in place["slots"]:
        why = niches._rejects(p, niche, slot, site, sun)
        if why:
            refused[slot["id"]] = why
        else:
            passed.append(slot)

    if not passed:
        return _verdict(NO, place, _governing(refused, place), None, plant, ctx)

    ground = [o for o in design.check_soil(p, cond, site)
              + design.check_water(p, cond, site)
              if o.get("level") in ("blocking", "serious")]
    if ground:
        return _verdict(NO, place, ground[0]["say"], None, plant, ctx,
                        fix=ground[0].get("fix"))

    free = [s for s in passed if not s.get("pick")]
    if not free:
        taken = ", ".join(str((s.get("pick") or {}).get("plant")
                              or (s.get("pick") or {}).get("name") or s["id"])
                          for s in passed)
        return _verdict(FULL, place,
                        f"suits this ground, and every row it could join is "
                        f"already taken — {taken}. Reopen one with "
                        f"`yard niches <slug> --reopen <slot>` to make room",
                        passed[0], plant, ctx)

    best = max(free, key=lambda s: s.get("budget_share") or 0)
    return _verdict(FITS, place, None, best, plant, ctx)


def _verdict(kind, place, why, slot, plant, ctx, fix=None):
    out = {"place": place["id"], "label": place["label"],
           "kind": place["kind"], "verdict": kind,
           "hours": place["hours"], "category": place["category"],
           "judged_h": round(float(ctx["judged_h"]), 2),
           "judged_over": ctx["window"], "needs_h": ctx["needs_h"]}
    if slot is not None:
        out["slot"] = slot["id"]
        if slot.get("count"):
            out["count"] = slot["count"]
    if kind in (FITS, FULL):
        out["light_margin_h"] = round(out["judged_h"] - ctx["needs_h"], 2)
        depth = place.get("depth_ft")
        if depth:
            out["depth_margin_ft"] = round(
                float(depth) - float(plant["mature_spread_ft"]), 2)
    if why:
        out["why"] = why
        out["short"] = _short(why)
    if fix:
        out["fix"] = fix
    return out


def window_short(months):
    """`Mar-Nov` rather than nine month names.

    `design.window_label` is written for an objection a person reads at a desk
    and names the season it belongs to. This is the same fact for a line of
    text on a phone, where a nine-month list is most of the width of the
    screen. A run that wraps the year — a winter crop standing Oct to Feb —
    is still one run and reads as one.
    """
    ms = list(months or solar.GROWING_SEASON)
    order = design.MONTHS
    if len(ms) >= 12:
        return "the year"
    if len(ms) == 1:
        return ms[0]
    idx = sorted(order.index(m) for m in ms if m in order)
    if not idx:
        return ", ".join(ms)
    start = None
    for i, n in enumerate(idx):
        if (n - 1) % 12 not in idx:
            start = n
            break
    if start is None:
        return ", ".join(order[n] for n in idx)
    run = [start]
    while len(run) < len(idx) and (run[-1] + 1) % 12 in idx:
        run.append((run[-1] + 1) % 12)
    if len(run) != len(idx):
        return ", ".join(order[n] for n in idx)
    return f"{order[run[0]]}-{order[run[-1]]}"


def _governing(refused, place):
    """One reason out of up to three rows, without hiding that they differ.

    Where every row refuses for the same reason — which is what happens whenever
    the light or the bed depth is the problem, since neither varies by row —
    that reason is the whole story. Where they differ the roomiest row's reason
    is the kindest true one, and the fact that the others said something else is
    stated rather than dropped.
    """
    if not refused:
        return "refused, and nothing recorded why"
    distinct = set(refused.values())
    if len(distinct) == 1:
        return refused[next(iter(refused))]
    roomy = max(place["slots"],
                key=lambda s: (s["id"] in refused, s.get("budget_share") or 0))
    why = refused.get(roomy["id"]) or sorted(distinct)[0]
    return (f"{why}. The other rows in {place['label']} refuse it for reasons "
            f"of their own")


def _short(why):
    """The first sentence, trimmed of the clauses written for a desk.

    A display convenience over the linters' own words, not a second statement
    of the rule: it only ever shortens, and `why` keeps every word beside it.
    Where the trimming finds nothing to cut, the first sentence is returned
    whole, which is always true if sometimes long.
    """
    first = re.split(r"\. (?=[A-Z])", why.strip(), maxsplit=1)[0]
    first = _TRAIL.sub("", first).strip().rstrip(",").rstrip(".")
    if len(first) > 150:
        first = first[:147].rsplit(" ", 1)[0] + "..."
    return first


def check(plant, slug, site=None, sun=None, cond=None, ps=None):
    """One plant against every place, best first."""
    site = site if site is not None else (yards.load(slug, "site.json") or {})
    sun = sun if sun is not None else (yards.load(slug, "sun-hours.json") or {})
    cond = cond if cond is not None else (yards.load(slug, "conditions.json") or {})
    ps = ps if ps is not None else places(slug, site, sun, cond)
    out = [evaluate(plant, pl, site, sun, cond) for pl in ps]
    order = {FITS: 0, FULL: 1, NO: 2}
    return sorted(out, key=lambda v: (order[v["verdict"]],
                                      -(v.get("light_margin_h") or -99)))


# --------------------------------------------------------------- tag checks

def tag_root_depth(spread):
    for upto, depth in TAG_ROOT_DEPTH:
        if spread <= upto:
            return depth
    return TAG_ROOT_DEEP


def tag_plant(light, spread, acid=False, sharp=False):
    """A plant record built from what a nursery tag actually states.

    A tag gives the light word, the mature size, and sometimes "acid-loving" or
    "needs excellent drainage". It never gives a rooting depth and rarely gives
    a pH range, so both are inferred and the inference is named in the record,
    so a verdict resting on it can be read as resting on it.
    """
    p = {"name": f"a {light} plant {spread:g} ft wide",
         "botanical": "unidentified", "light": light, "water": "moderate",
         "mature_height_ft": spread, "mature_spread_ft": spread,
         # Stated rather than left to the default. `_rejects` falls back to the
         # growing season when a record names no months, and then describes
         # what it did as "over the year" — so the verdict and the figure
         # beside it disagreed in words while agreeing in arithmetic. Naming
         # the window makes the sentence true and changes no number.
         "months": list(solar.GROWING_SEASON),
         "months_source": "assumed: nothing on a tag says when a plant grows",
         "rooting_depth_in": tag_root_depth(spread),
         "rooting_depth_source": "inferred from mature spread, lib.fits",
         "source": "nursery tag"}
    if acid:
        p["ph_range"] = list(TAG_ACID_RANGE)
        p["ph_note"] = "assumed from an acid-loving label on the tag"
    if sharp:
        p["soil_drainage"] = "sharp"
    return p


def tag_key(light, spread, acid, sharp):
    return f"{light}|{spread:g}|{int(bool(acid))}{int(bool(sharp))}"


def tag_grid(slug, site=None, sun=None, cond=None, ps=None):
    """Every tag a plant could carry, answered in advance.

    This is the whole of the offline fallback. A plant the catalog has never
    heard of still has a label on its pot, and the label carries enough to run
    the same three checks over. Computed here in Python against the same
    functions, so the phone holds answers rather than rules.
    """
    site = site if site is not None else (yards.load(slug, "site.json") or {})
    sun = sun if sun is not None else (yards.load(slug, "sun-hours.json") or {})
    cond = cond if cond is not None else (yards.load(slug, "conditions.json") or {})
    ps = ps if ps is not None else places(slug, site, sun, cond)
    grid = {}
    for light in design.LIGHT_ORDER:
        for spread in TAG_SPREADS:
            for acid in (False, True):
                for sharp in (False, True):
                    p = tag_plant(light, spread, acid, sharp)
                    grid[tag_key(light, spread, acid, sharp)] = [
                        evaluate(p, pl, site, sun, cond) for pl in ps]
    return grid


# ------------------------------------------------------------------- report

def _stamps(slug, site=None):
    """What this answer was computed from, so a stale one can be spotted.

    Not a gate. `fits` is read-only and nothing it prints commits anybody to
    anything, so an open doubt is reported on the face of the answer rather
    than used to refuse it — a tool that goes silent while somebody is standing
    in a shop is a tool they stop carrying.
    """
    out = {"built": TODAY, "yard": slug}
    sand = yards.sandbox_stamp(slug)
    if sand:
        out["sandbox"] = sand
    p = yards.path(slug, "sun-hours.json")
    if os.path.exists(p):
        out["sun_model"] = (yards.load(slug, "sun-hours.json") or {}).get("updated")
        out["sun_model_file"] = datetime.date.fromtimestamp(
            os.path.getmtime(p)).isoformat()
        # A card is a frozen answer, and the one way it goes quietly wrong is
        # the light moving underneath it. Compared as files rather than as
        # stamped dates, because a re-run of the sun model that lands on the
        # same day still changes the answer.
        old = yards.path(slug, "FITS.html")
        if os.path.exists(old) and os.path.getmtime(old) < os.path.getmtime(p):
            out["stale_sun"] = (
                f"The sun model was rebuilt on "
                f"{out['sun_model_file']}, after this card. Rebuild it with "
                f"`yard fits {slug} --card`")
    cards = doubts.open_cards(slug, job="design")
    if cards:
        out["open_doubts"] = [{"id": c["id"], "question": c["question"]}
                              for c in cards]
    return out


def report(slug, results, plant, stamps):
    lines = [f"{plant['name']}  ({plant['botanical']})",
             f"  {plant['light']}, {plant['water']} water, "
             f"{plant['mature_height_ft']:g} ft tall by "
             f"{plant['mature_spread_ft']:g} ft wide"
             + (f", pH {plant['ph_range'][0]}-{plant['ph_range'][1]}"
                if plant.get("ph_range") else "")
             + (", needs sharp drainage"
                if plant.get("soil_drainage") == "sharp" else ""),
             f"  source: {plant.get('source')}", ""]
    for group, head in ((FITS, "GOES IN"), (FULL, "SUITS, BUT NO ROOM"),
                        (NO, "NO")):
        rows = [r for r in results if r["verdict"] == group]
        if not rows:
            continue
        lines.append(head)
        for r in rows:
            where = (f"{r['label']} — {r['judged_h']:g} h, needs "
                     f"{r['needs_h']:g}")
            if group == FITS:
                margin = r.get("light_margin_h") or 0
                lines.append(f"  {where}, so {margin:+g} h to spare")
                if r.get("slot"):
                    lines.append(f"      row {r['slot']}")
            else:
                lines.append(f"  {where}")
                lines.append(f"      {r.get('short') or r.get('why')}")
        lines.append("")
    lines += _stamp_lines(stamps, design.window_label(plant.get("months")))
    return "\n".join(lines)


def _stamp_lines(stamps, window=None):
    out = ["--",
           f"computed {stamps['built']} against the sun model of "
           f"{stamps.get('sun_model') or 'unknown date'}"
           + (f", light averaged over {window}" if window else
              ", each plant judged on the light in its own growing months")]
    if stamps.get("sandbox"):
        out.insert(0, f"!! {stamps['sandbox']}")
    if stamps.get("stale_sun"):
        out.append(f"!! {stamps['stale_sun']}")
    for c in stamps.get("open_doubts") or []:
        out.append(f"!! open doubt [{c['id']}] against design: {c['question']}")
    return out


# ------------------------------------------------------------------ intake

PENDING_DIR = os.path.join(CATALOG_DIR, "pending")

# What a queued name still needs before it can be checked. Every one of these
# is a fact somebody has to look up, which is why a queued plant is never
# written into the catalog itself: a record with nulls in it would be a plant
# the catalog claims to know and cannot judge, and `_rejects` would refuse it
# for having no facts rather than for anything about the plant.
NEEDS = ["light", "water", "mature_height_ft", "mature_spread_ft",
         "ph_range", "season", "rooting_depth_in", "source"]


def intake(slug, queued, catalog, site, sun, cond, ps, nich=None):
    """Absorb what the phone queued: research jobs out, bought plants on.

    Two outputs, because a queued line is one of two different things. A name
    the catalog has never heard of is a research job, and it goes to
    `catalog/pending/<region>.json` with the fields it still needs named, so
    nothing is lost and nothing unresearched is smuggled into the catalog.

    A plant that was actually bought is a different matter — it is in the boot
    of the car and it has to go somewhere. That one is checked against the
    yard and written out as a slate file for `lib.niches`, which is the module
    that owns the candidate lists. It is written rather than applied, because
    `niches.slate` replaces a slot's candidates outright and quietly dropping
    somebody's researched shortlist is not a thing to do on their behalf. The
    file therefore carries the slot's existing candidates alongside the new
    one, so running the command it prints adds rather than overwrites.
    """
    known, unknown, placed, homeless = [], [], [], []
    for item in queued:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        hits = find(catalog, name)
        if len(hits) == 1:
            known.append((item, hits[0]))
        elif len(hits) > 1:
            unknown.append((item, f"matches {len(hits)} plants — say which"))
        else:
            unknown.append((item, "not in the catalog"))

    nich = nich if nich is not None else (yards.load(slug, "niches.json") or {})
    slate = {}
    for item, plant in known:
        if not item.get("bought"):
            continue
        res = check(plant, slug, site, sun, cond, ps)
        fits = [r for r in res if r["verdict"] == FITS and r.get("slot")
                and any(n["id"] == r["place"]
                        for n in nich.get("niches") or [])]
        if not fits:
            homeless.append((plant, res))
            continue
        best = fits[0]
        _, slot = niches.find(nich, best["slot"])
        rows = slate.setdefault(best["slot"], list((slot or {}).get(
            "candidates") or []))
        if not any(c.get("botanical") == plant["botanical"] for c in rows):
            rows.append({k: v for k, v in plant.items()
                         if k not in ("fit", "score", "score_why")})
        placed.append((plant, best))

    pending_path = None
    if unknown:
        pending_path = _write_pending(catalog["region"], unknown)
    slate_path = None
    if slate:
        slate_path = yards.path(slug, "fits-bought.json")
        with open(slate_path, "w") as fh:
            json.dump(slate, fh, indent=2)
            fh.write("\n")
    return {"known": known, "unknown": unknown, "placed": placed,
            "homeless": homeless, "pending_path": pending_path,
            "slate_path": slate_path}


def _write_pending(region, unknown):
    os.makedirs(PENDING_DIR, exist_ok=True)
    path = os.path.join(PENDING_DIR, f"{region}.json")
    data = {"region": region, "pending": True,
            "why": "Names queued from a phone that the catalog could not "
                   "answer. Research each one, fill every field in `needs`, "
                   "and move the record into the region's catalog file. "
                   "Nothing here is loaded by lib.fits.",
            "plants": []}
    if os.path.exists(path):
        with open(path) as fh:
            data = json.load(fh)
    have = {p.get("queried") for p in data.get("plants") or []}
    for item, why in unknown:
        if item["name"] in have:
            continue
        data.setdefault("plants", []).append(
            {"queried": item["name"], "queued_on": item.get("added"),
             "bought": bool(item.get("bought")), "why": why,
             "botanical": None, "names": [item["name"]],
             "needs": list(NEEDS)})
    data["updated"] = TODAY
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return path


def _report_intake(slug, res):
    out = []
    if res["placed"]:
        out.append("BOUGHT, AND IT GOES SOMEWHERE")
        for plant, best in res["placed"]:
            out.append(f"  {plant['name']}  ->  {best['label']}, row "
                       f"{best['slot']}  "
                       f"({best['judged_h']:g} h over {best['judged_over']}, "
                       f"needs {best['needs_h']:g})")
        out.append("")
    if res["homeless"]:
        out.append("BOUGHT, AND NOTHING HERE TAKES IT")
        for plant, all_res in res["homeless"]:
            near = min(all_res, key=lambda r: abs(
                (r["judged_h"] or 0) - r["needs_h"]))
            out.append(f"  {plant['name']}")
            out.append(f"      closest is {near['label']}: "
                       f"{near.get('short') or 'no row free'}")
        out.append("")
    if res["unknown"]:
        out.append("NEEDS RESEARCH")
        for item, why in res["unknown"]:
            out.append(f"  {item['name']}  — {why}")
        out.append(f"\n  filed to {res['pending_path']}")
        out.append(f"  fill in: {', '.join(NEEDS)}")
        out.append("")
    seen = [(i, p) for i, p in res["known"] if not i.get("bought")]
    if seen:
        out.append("ALREADY IN THE CATALOG, NOT BOUGHT")
        for item, plant in seen:
            out.append(f"  {item['name']}  ->  {plant['name']} "
                       f"({plant['botanical']})")
        out.append("")
    if res["slate_path"]:
        out.append(f"wrote {res['slate_path']}")
        out.append("It carries each slot's existing candidates as well as the "
                   "new one, because")
        out.append("`--slate` replaces a slot's list rather than adding to "
                   "it. Apply it with:")
        out.append(f"\n  yard niches {slug} --slate "
                   f"{os.path.basename(res['slate_path'])}\n")
    if not any((res["placed"], res["homeless"], res["unknown"], seen)):
        out.append("nothing queued.")
    return "\n".join(out)


# ---------------------------------------------------------------- the card

# Verdict codes, because the payload carries one per plant per place and the
# words would be most of the file. The phone never interprets them beyond
# choosing a colour and a heading.
CODE = {FITS: 0, FULL: 1, NO: 2}

CARD_TITLE = "Would it go anywhere?"


def yard_key(slug):
    """A stable, meaningless name for a yard, for anything that leaves the house.

    A slug often repeats the street. A page that carries the slug says where
    somebody lives, on a phone that can be lost, in a file that can be
    forwarded, at a URL that can be indexed.
    `lib.niches` already refuses to put a yard label on the ballot for exactly
    this reason, and the card is a worse case than the ballot because it is
    built to be carried out of the house.

    So the card is keyed by a digest instead. It is not a secret and it is not
    meant to be one: it only has to be stable, so the queue in the phone's
    storage stays attached to one yard, and `--intake` can still refuse a queue
    built for a different one.
    """
    return hashlib.sha256(slug.encode()).hexdigest()[:8]

CARD_CSS = """
:root { --ink:#1a1a1a; --muted:#5c5c5c; --rule:#dcdcdc; --accent:#2f5d34;
        --band:#f6f7f4; --yes:#2f5d34; --room:#8a6d1f; --no:#8c2f2f; }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:#fff; color:var(--ink);
       font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
       padding-bottom:4rem; }
header { position:sticky; top:0; z-index:5; background:#fff;
         border-bottom:2px solid var(--accent); padding:.6rem .9rem .5rem; }
h1 { font-size:1.05rem; margin:0 0 .15rem; letter-spacing:-.01em; }
.sub { font-size:.72rem; color:var(--muted); line-height:1.35; }
.warn { background:#fff6e5; border-left:3px solid var(--room); color:#5a4406;
        font-size:.74rem; padding:.4rem .6rem; margin:.4rem 0 0; }
.warn.hard { background:#fdeceb; border-left-color:var(--no); color:#6b1f1f; }
nav { display:flex; gap:.4rem; margin-top:.5rem; }
nav button { flex:1; font:inherit; font-size:.82rem; padding:.42rem;
             border:1px solid var(--rule); background:#fff; color:var(--muted);
             border-radius:7px; }
nav button[aria-selected=true] { background:var(--accent); border-color:var(--accent);
                                 color:#fff; font-weight:600; }
main { padding:.75rem .9rem 0; max-width:44rem; margin:0 auto; }
input[type=search], input[type=text] { width:100%; font:inherit; padding:.6rem .7rem;
       border:1px solid var(--rule); border-radius:8px; background:var(--band); }
.hits { list-style:none; margin:.5rem 0 0; padding:0; }
.hits li { padding:.55rem .2rem; border-bottom:1px solid var(--rule); }
.hits b { font-weight:600; }
.hits .lat { color:var(--muted); font-style:italic; font-size:.82rem; }
.hits .meta { color:var(--muted); font-size:.76rem; }
.plant { display:flex; gap:.7rem; align-items:flex-start; margin:.2rem 0 .7rem; }
.plant img { width:76px; height:76px; object-fit:cover; border-radius:8px;
             background:var(--band); flex:none; }
.plant .lat { color:var(--muted); font-style:italic; font-size:.85rem; }
.plant .meta { color:var(--muted); font-size:.78rem; margin-top:.15rem; }
h2.group { font-size:.72rem; text-transform:uppercase; letter-spacing:.07em;
           margin:1.1rem 0 .3rem; color:var(--muted); }
h2.group.yes { color:var(--yes); } h2.group.room { color:var(--room); }
h2.group.no { color:var(--no); }
.row { border-left:3px solid var(--rule); padding:.4rem 0 .4rem .6rem;
       margin-bottom:.3rem; }
.row.yes { border-left-color:var(--yes); background:#f3f7f3; }
.row.room { border-left-color:var(--room); background:#fdf9ef; }
.row.no { border-left-color:var(--no); }
.row .where { font-weight:600; font-size:.94rem; }
.row .light { color:var(--muted); font-size:.76rem; font-variant-numeric:tabular-nums; }
.row .say { font-size:.82rem; color:#444; margin-top:.2rem; }
.row details summary { font-size:.74rem; color:var(--accent); cursor:pointer;
                       margin-top:.2rem; list-style:none; }
.row details summary::-webkit-details-marker { display:none; }
.row details p { font-size:.8rem; color:#444; margin:.3rem 0 0; }
.chips { display:flex; flex-wrap:wrap; gap:.35rem; margin:.4rem 0 .2rem; }
.chips button { font:inherit; font-size:.8rem; padding:.34rem .6rem;
                border:1px solid var(--rule); background:#fff; border-radius:999px; }
.chips button[aria-pressed=true] { background:var(--accent); border-color:var(--accent);
                                   color:#fff; font-weight:600; }
label.tog { display:flex; align-items:center; gap:.5rem; font-size:.85rem;
            padding:.35rem 0; }
h3 { font-size:.78rem; text-transform:uppercase; letter-spacing:.06em;
     color:var(--muted); margin:1rem 0 .3rem; }
.q { display:flex; gap:.4rem; margin-top:.4rem; }
.q button, .wide { font:inherit; padding:.55rem .8rem; border-radius:8px;
                   border:1px solid var(--accent); background:var(--accent);
                   color:#fff; font-weight:600; }
.wide { width:100%; margin-top:.6rem; }
.ghost { background:#fff; color:var(--accent); }
.queue { list-style:none; margin:.6rem 0 0; padding:0; }
.queue li { display:flex; align-items:center; gap:.55rem; padding:.45rem .2rem;
            border-bottom:1px solid var(--rule); font-size:.9rem; }
.queue li span { flex:1; }
.queue li.bought span { color:var(--muted); }
.queue button { font:inherit; font-size:.8rem; border:0; background:none;
                color:var(--no); padding:.2rem .35rem; }
.none { color:var(--muted); font-size:.85rem; padding:.8rem 0; }
footer { margin:2rem 0 0; padding:.9rem; border-top:1px solid var(--rule);
         color:var(--muted); font-size:.7rem; line-height:1.5; }
"""

CARD_JS = r"""
var D = DATA, S = D.strings, P = D.places, cur = null;
function $(id){ return document.getElementById(id); }
function esc(s){ var d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }
function tab(n){
  ['find','tag','queue'].forEach(function(t){
    $('t_'+t).setAttribute('aria-selected', String(t===n));
    $('p_'+t).hidden = (t!==n);
  });
  if (n==='queue') drawQueue();
}
/* Search is the only thing the phone computes, and it computes no
   horticulture: it ranks names by where the query lands in them. */
function search(q){
  q = q.trim().toLowerCase();
  var out = $('hits');
  if (q.length < 2){ out.innerHTML=''; return; }
  var hits = [];
  D.plants.forEach(function(p,i){
    var best = 9;
    p.n.concat([p.b]).forEach(function(n){
      var k = n.toLowerCase(), at = k.indexOf(q);
      if (at === 0) best = Math.min(best, 0);
      else if (at > 0) best = Math.min(best, 1);
    });
    if (best < 9) hits.push([best, p.n[0].length, i]);
  });
  hits.sort(function(a,b){ return a[0]-b[0] || a[1]-b[1]; });
  if (!hits.length){
    out.innerHTML = '<li class="none">Nothing by that name. Use <b>By tag</b> '
      + 'to check it from the pot label, and add it to the queue below.</li>';
    return;
  }
  out.innerHTML = hits.slice(0,25).map(function(h){
    var p = D.plants[h[2]];
    return '<li onclick="show('+h[2]+')"><b>'+esc(p.n[0])+'</b> '
      + '<span class="lat">'+esc(p.b)+'</span><br>'
      + '<span class="meta">'+esc(p.l)+', '+p.w+' ft wide'
      + (p.na ? ' &middot; native' : '') + '</span></li>';
  }).join('');
}
function show(i){
  cur = i;
  var p = D.plants[i];
  $('hits').innerHTML = '';
  $('q_find').value = p.n[0];
  var img = p.ph ? '<img src="'+esc(p.ph)+'" alt="" loading="lazy">' : '';
  var bits = [p.l, p.wa+' water', p.h+' ft by '+p.w+' ft'];
  if (p.pl) bits.push('pH '+p.pl[0]+'-'+p.pl[1]);
  if (p.sh) bits.push('needs sharp drainage');
  $('detail').innerHTML =
    '<div class="plant">'+img+'<div><b>'+esc(p.n[0])+'</b><br>'
    + '<span class="lat">'+esc(p.b)+'</span>'
    + '<div class="meta">'+bits.map(esc).join(' &middot; ')+'</div>'
    + (p.no ? '<div class="meta">'+esc(p.no)+'</div>' : '')
    + '<div class="meta">source: '+esc(p.s)+'</div></div></div>'
    + verdicts(p.v);
}
/* Render only. Every code and sentence below was computed in Python by the
   same functions lib.design and lib.niches use, so nothing here can disagree
   with the linter that will check the design later. */
function verdicts(v){
  var g = [[0,'yes','Goes in'],[1,'room','Suits it, but no row free'],[2,'no','No']];
  var html = '';
  g.forEach(function(grp){
    var rows = [];
    P.forEach(function(pl, j){
      if (v[j][0] !== grp[0]) return;
      var say = v[j][1] > -1 ? S[v[j][1]] : '';
      var full = v[j][2] > -1 ? S[v[j][2]] : '';
      rows.push('<div class="row '+grp[1]+'"><div class="where">'+esc(pl.la)
        + '</div><div class="light">'+v[j][3]+' h over '+esc(S[v[j][4]])
        + ' &middot; needs '+v[j][5]+' h'
        + (pl.k==='area' ? ' &middot; open ground' : '')+'</div>'
        + (say ? '<div class="say">'+esc(say)+'</div>' : '')
        + (full && full !== say
           ? '<details><summary>why, in full</summary><p>'+esc(full)+'</p></details>'
           : '')
        + '</div>');
    });
    if (rows.length) html += '<h2 class="group '+grp[1]+'">'+grp[2]
      + ' &middot; '+rows.length+'</h2>' + rows.join('');
  });
  return html;
}
/* ---- by tag ---- */
var tg = { l:null, s:null, a:false, d:false };
function pick(kind, val, el){
  tg[kind] = val;
  Array.prototype.forEach.call(el.parentNode.children, function(b){
    b.setAttribute('aria-pressed', String(b === el));
  });
  drawTag();
}
function drawTag(){
  if (tg.l === null || tg.s === null){
    $('tagout').innerHTML = '<p class="none">Read the pot label: pick the sun '
      + 'word and the mature width it gives.</p>';
    return;
  }
  var key = tg.l+'|'+tg.s+'|'+(tg.a?1:0)+(tg.d?1:0);
  var v = D.tags[key];
  $('tagout').innerHTML = v ? verdicts(v)
    : '<p class="none">No answer stored for that combination.</p>';
}
function tog(kind, el){ tg[kind] = el.checked; drawTag(); }
/* ---- queue ---- */
var KEY = 'fits-queue-' + D.yard;
function readQ(){ try { return JSON.parse(localStorage.getItem(KEY)) || []; }
                  catch(e){ return []; } }
function writeQ(q){ localStorage.setItem(KEY, JSON.stringify(q)); drawQueue(); }
function addQ(){
  var t = $('q_new').value.trim();
  if (!t) return;
  var q = readQ();
  q.push({name:t, added:new Date().toISOString().slice(0,10), bought:false,
          where:null});
  $('q_new').value = '';
  writeQ(q);
}
function drawQueue(){
  var q = readQ(), el = $('qlist');
  if (!q.length){
    el.innerHTML = '<li class="none">Nothing queued. Anything the catalogue '
      + 'has never heard of goes here, and <code>--intake</code> researches it '
      + 'properly at home.</li>';
    $('q_copy').hidden = true;
    return;
  }
  $('q_copy').hidden = false;
  el.innerHTML = q.map(function(it, i){
    return '<li class="'+(it.bought?'bought':'')+'">'
      + '<input type="checkbox" '+(it.bought?'checked':'')
      + ' onchange="mark('+i+',this.checked)" title="bought">'
      + '<span>'+esc(it.name)+'</span>'
      + '<button onclick="drop('+i+')">remove</button></li>';
  }).join('');
}
function mark(i, on){ var q=readQ(); q[i].bought = on; writeQ(q); }
function drop(i){ var q=readQ(); q.splice(i,1); writeQ(q); }
function copyQ(){
  var body = JSON.stringify({yard_key: D.yard, region: D.region,
                             queued: readQ()}, null, 1);
  var ta = document.createElement('textarea');
  ta.value = body; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
  if (navigator.clipboard) { navigator.clipboard.writeText(body); }
  $('q_copy').textContent = 'copied — paste into queued.json';
  setTimeout(function(){ $('q_copy').textContent = 'copy for --intake'; }, 2500);
}
document.addEventListener('DOMContentLoaded', function(){
  $('q_find').addEventListener('input', function(){ search(this.value); });
  drawTag(); drawQueue();
});
"""


def public_stamps(slug, stamps):
    """The stamps with the yard's name taken out, for anything that leaves.

    One function rather than two scrubs, because the page shows these twice —
    once as a warning banner and once inside the payload — and a scrub applied
    at only one of those is worse than none: the file reads as anonymous and
    is not.

    Everything the stamps are for survives. The build date, the sun model they
    rest on, the open doubts and the sandbox warning all describe a record,
    not a place. Only the name is dropped, and any command line quoting it is
    rewritten to the placeholder so the instruction still reads.
    """
    # Not only this slug. A sandbox stamp names the yard it is a copy of —
    # `SANDBOX of cloverleaf-austin` — so scrubbing the current slug alone
    # would leave the real yard's street name on a rehearsal card.
    #
    # The origin is read out of the stamp rather than off disk, because the
    # text being scrubbed is the thing that has to be safe. A scrub that
    # depends on a marker file scrubs nothing when the file is missing, and
    # fails silently, which is the failure worth engineering against.
    names = {slug} | set(yards.list_yards())
    for v in stamps.values():
        if isinstance(v, str):
            names |= set(re.findall(r"SANDBOX of (\S+)", v))
    names = sorted(n for n in names if n)
    names.sort(key=len, reverse=True)

    def scrub(node):
        if isinstance(node, str):
            for n in names:
                node = node.replace(n, "<slug>")
            return node
        if isinstance(node, dict):
            return {k: scrub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [scrub(v) for v in node]
        return node

    return {k: scrub(v) for k, v in stamps.items() if k != "yard"}


def _card_data(slug, catalog, ps, site, sun, cond, stamps, offline=True,
               want_photos=True):
    """Every answer the card can give, computed here so the phone computes none.

    Strings are interned. Most of the payload is refusal sentences and a good
    many of them repeat exactly — every plant four feet wide is refused by g04
    in the same words — so a shared table is most of the difference between a
    file that moves over AirDrop and one that does not.
    """
    strings, index = [], {}

    def intern(s):
        if not s:
            return -1
        if s not in index:
            index[s] = len(strings)
            strings.append(s)
        return index[s]

    def pack(results):
        return [[CODE[r["verdict"]], intern(r.get("short")),
                 intern(r.get("why")), r["judged_h"],
                 intern(r["judged_over"]), r["needs_h"]] for r in results]

    plants = []
    for p in catalog["plants"]:
        res = [evaluate(p, pl, site, sun, cond) for pl in ps]
        rec = {"n": [p["name"]] + [x for x in (p.get("names") or [])
                                   if x != p["name"]],
               "b": p["botanical"], "l": p["light"], "wa": p["water"],
               "h": p["mature_height_ft"], "w": p["mature_spread_ft"],
               "s": p.get("source"), "v": pack(res)}
        if p.get("ph_range"):
            rec["pl"] = p["ph_range"]
        if p.get("soil_drainage") == "sharp":
            rec["sh"] = 1
        if p.get("native"):
            rec["na"] = 1
        if p.get("note"):
            rec["no"] = p["note"]
        if want_photos:
            shots = niches._fetch_photos(p["botanical"], offline=offline)
            if shots:
                rec["ph"] = shots[0].get("url")
        plants.append(rec)

    tags = {k: pack(v) for k, v in
            tag_grid(slug, site, sun, cond, ps).items()}

    return {"yard": yard_key(slug), "region": catalog["region"],
            "built": TODAY,
            "stamps": public_stamps(slug, stamps),
            "strings": strings, "plants": plants,
            "tags": tags,
            "tag_axes": {"lights": design.LIGHT_ORDER, "spreads": TAG_SPREADS},
            "places": [{"id": pl["id"], "la": pl["label"], "k": pl["kind"],
                        "hr": pl["hours"], "cat": pl["category"]}
                       for pl in ps]}


def card(slug, catalog, ps, site, sun, cond, stamps, offline=True,
         want_photos=True):
    data = _card_data(slug, catalog, ps, site, sun, cond, stamps,
                      offline=offline, want_photos=want_photos)
    blob = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    stamps = public_stamps(slug, stamps)

    warns = []
    if stamps.get("sandbox"):
        warns.append(("hard", stamps["sandbox"]
                      + " — these answers are a rehearsal, not the plan"))
    if stamps.get("stale_sun"):
        warns.append(("hard", stamps["stale_sun"]))
    for c in stamps.get("open_doubts") or []:
        warns.append(("", f"Open doubt [{c['id']}] against the design: "
                          f"{c['question']}"))
    warn_html = "".join(
        f'<p class="warn {cls}">{_esc(text)}</p>' for cls, text in warns)

    lights = "".join(
        f'<button aria-pressed="false" onclick="pick(\'l\',\'{_esc(l)}\',this)">'
        f'{_esc(l)}</button>' for l in design.LIGHT_ORDER)
    spreads = "".join(
        f'<button aria-pressed="false" onclick="pick(\'s\',{s:g},this)">'
        f'{s:g} ft</button>' for s in TAG_SPREADS)

    return _CARD_HTML.format(
        title=CARD_TITLE, region=_esc(catalog["region"]),
        built=stamps["built"],
        sunmodel=_esc(stamps.get("sun_model") or "unknown date"),
        counts=f"{len(catalog['plants'])} plants against "
               f"{len(ps)} pieces of ground",
        warns=warn_html, lights=lights, spreads=spreads,
        css=CARD_CSS, js=CARD_JS, data=blob)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_CARD_HTML = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Fits?">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="theme-color" content="#2f5d34">
<link rel="apple-touch-icon" href="data:image/svg+xml,\
%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 180'%3E\
%3Crect width='180' height='180' rx='38' fill='%232f5d34'/%3E\
%3Ctext x='90' y='124' font-size='104' text-anchor='middle' fill='%23fff'\
 font-family='Helvetica,Arial'%3E%3F%3C/text%3E%3C/svg%3E">
<title>{title}</title>
<style>{css}</style>
<header>
  <h1>{title}</h1>
  <div class="sub">{region} catalogue &middot; {counts}<br>
    built {built} on the sun model of {sunmodel}. Works with no signal.</div>
  {warns}
  <nav>
    <button id="t_find"  aria-selected="true"  onclick="tab('find')">By name</button>
    <button id="t_tag"   aria-selected="false" onclick="tab('tag')">By tag</button>
    <button id="t_queue" aria-selected="false" onclick="tab('queue')">Queue</button>
  </nav>
</header>
<main>
  <section id="p_find">
    <input type="search" id="q_find" placeholder="Type a plant name"
           autocomplete="off" autocapitalize="off" spellcheck="false">
    <ul class="hits" id="hits"></ul>
    <div id="detail"></div>
  </section>

  <section id="p_tag" hidden>
    <h3>What the label says</h3>
    <div class="chips">{lights}</div>
    <div class="chips">{spreads}</div>
    <label class="tog"><input type="checkbox" onchange="tog('a',this)">
      acid-loving, or the label names ericaceous compost</label>
    <label class="tog"><input type="checkbox" onchange="tog('d',this)">
      needs excellent or sharp drainage</label>
    <div id="tagout"></div>
  </section>

  <section id="p_queue" hidden>
    <h3>Plants this card could not name</h3>
    <div class="q">
      <input type="text" id="q_new" placeholder="What was on the label?">
      <button onclick="addQ()">add</button>
    </div>
    <ul class="queue" id="qlist"></ul>
    <button class="wide ghost" id="q_copy" onclick="copyQ()" hidden>
      copy for --intake</button>
  </section>

  <footer>
    Every verdict here was computed at a desk by <code>lib.fits</code>, through
    the same <code>niches._rejects</code> and <code>design.check_soil</code>
    that will check the planting plan. This page searches and displays them; it
    decides nothing, so it cannot disagree with the plan.
    <br><br>
    Light is the measured sun for that ground averaged over the months each
    plant is actually growing, which is why two plants can read different hours
    for the same bed. Rebuild the card with
    <code>yard fits &lt;slug&gt; --card</code> whenever the sun model changes.
    <br><br>
    This page names no address and no yard. It carries bed nicknames, hours of
    sun and a soil pH, which describe ground rather than a household.
  </footer>
</main>
<script>var DATA={data};</script>
<script>{js}</script>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--plant", metavar="NAME",
                    help="one plant, checked against every place")
    ap.add_argument("--all", action="store_true",
                    help="every catalog plant that fits, grouped by place")
    ap.add_argument("--tag", action="store_true",
                    help="check by nursery tag: --light --spread --acid --sharp")
    ap.add_argument("--light", choices=design.LIGHT_ORDER)
    ap.add_argument("--spread", type=float, metavar="FT")
    ap.add_argument("--acid", action="store_true",
                    help="the tag says acid-loving")
    ap.add_argument("--sharp", action="store_true",
                    help="the tag says it needs excellent drainage")
    ap.add_argument("--catalog", metavar="REGION",
                    help="override the region inferred from the address")
    ap.add_argument("--places", action="store_true",
                    help="list the ground this yard has, and its light")
    ap.add_argument("--card", action="store_true",
                    help="build the offline HTML card for a phone")
    ap.add_argument("-o", "--out", metavar="PATH",
                    help="where to write the card (default <yard>/FITS.html)")
    ap.add_argument("--photos", action="store_true",
                    help="fetch any missing plant photographs from iNaturalist")
    ap.add_argument("--no-photos", action="store_true",
                    help="build the card with no photographs at all")
    ap.add_argument("--intake", metavar="FILE",
                    help="the queue copied off the phone")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    site = yards.load(args.slug, "site.json")
    if site is None:
        raise SystemExit(f"{args.slug} has no site.json")
    sun = yards.load(args.slug, "sun-hours.json") or {}
    cond = yards.load(args.slug, "conditions.json") or {}
    ps = places(args.slug, site, sun, cond)
    stamps = _stamps(args.slug, site)

    if args.places:
        _print_places(ps, stamps, args.json)
        return

    region = args.catalog or region_for(args.slug, site)
    if region is None:
        raise SystemExit(
            f"no catalog covers {args.slug}. Name one with --catalog, or add "
            f"the county to a file in catalog/. Have: "
            f"{', '.join(sorted(catalogs())) or 'none'}")
    catalog = load_catalog(region)

    if args.tag:
        if not (args.light and args.spread):
            raise SystemExit("--tag needs --light and --spread, which is what "
                             "the pot label states")
        plant = tag_plant(args.light, args.spread, args.acid, args.sharp)
        res = check(plant, args.slug, site, sun, cond, ps)
        print(json.dumps({"plant": plant, "places": res, "stamps": stamps},
                         indent=2) if args.json
              else report(args.slug, res, plant, stamps))
        return

    if args.plant:
        hits = find(catalog, args.plant)
        if not hits:
            _miss(args.plant, region)
            return
        if len(hits) > 1:
            print(f"{args.plant!r} matches {len(hits)} plants in "
                  f"{region}. Ask for one of them by name:\n")
            for p in hits:
                print(f"  {p['name']}  ({p['botanical']})  — "
                      f"{p['light']}, {p['mature_spread_ft']:g} ft wide")
            return
        plant = hits[0]
        res = check(plant, args.slug, site, sun, cond, ps)
        print(json.dumps({"plant": plant, "places": res, "stamps": stamps},
                         indent=2) if args.json
              else report(args.slug, res, plant, stamps))
        return

    if args.all:
        _print_all(args.slug, catalog, ps, site, sun, cond, stamps, args.json)
        return

    if args.intake:
        with open(args.intake) as fh:
            payload = json.load(fh)
        # By digest, because the card no longer knows the yard's name. A queue
        # copied off the phone still has to be refused for the wrong yard, and
        # the digest is enough to do that without the name travelling.
        stated = payload.get("yard_key") or payload.get("yard")
        if stated and stated not in (yard_key(args.slug), args.slug):
            raise SystemExit(
                f"that queue was built for a different yard (key {stated!r}; "
                f"{args.slug} is {yard_key(args.slug)!r})")
        res = intake(args.slug, payload.get("queued") or [], catalog,
                     site, sun, cond, ps)
        print(_report_intake(args.slug, res))
        return

    if args.card:
        out = args.out or yards.path(args.slug, "FITS.html")
        html = card(args.slug, catalog, ps, site, sun, cond, stamps,
                    offline=not args.photos, want_photos=not args.no_photos)
        with open(out, "w") as fh:
            fh.write(html)
        combos = len(design.LIGHT_ORDER) * len(TAG_SPREADS) * 4
        kb = len(html.encode()) / 1024.0
        print(f"wrote {out}  ({kb:.0f} KB, {len(catalog['plants'])} plants "
              f"and {combos} tag combinations, each against {len(ps)} "
              f"pieces of ground)")
        for line in _stamp_lines(stamps):
            print(line)
        print("\nAirDrop it to the phone, open it in Safari, then Share ->\n"
              "Add to Home Screen. It needs no signal after that.")
        return

    ap.print_help()


def _miss(query, region):
    print(f"nothing in the {region} catalog matches {query!r}.\n")
    print("Check it from the pot label instead:\n")
    print(f"  yard fits <slug> --tag --light 'full sun' --spread 3\n")
    print("and add it properly later with --intake.")


def _print_places(ps, stamps, as_json):
    if as_json:
        print(json.dumps({"places": ps, "stamps": stamps}, indent=2,
                         default=str))
        return
    beds = [p for p in ps if p["kind"] == "bed"]
    areas = [p for p in ps if p["kind"] == "area"]
    for head, group in (("BEDS", beds), ("OPEN GROUND", areas)):
        if not group:
            continue
        print(head)
        for p in sorted(group, key=lambda x: -(x["hours"] or 0)):
            free = sum(1 for s in p["slots"] if not s.get("pick"))
            area = f"{p['area_sqft']:g} sq ft" if p.get("area_sqft") else "—"
            depth = f", {p['depth_ft']:.1f} ft deep" if p.get("depth_ft") else ""
            print(f"  {p['label']:<22} {p['hours']:>5.2f} h  "
                  f"{p['category']:<11} {area}{depth}  "
                  f"{free}/{len(p['slots'])} rows free")
        print()
    print("\n".join(_stamp_lines(stamps)))


def _print_all(slug, catalog, ps, site, sun, cond, stamps, as_json):
    by_place = {p["id"]: [] for p in ps}
    nowhere = []
    for plant in catalog["plants"]:
        res = [evaluate(plant, pl, site, sun, cond) for pl in ps]
        landed = False
        for r in res:
            if r["verdict"] in (FITS, FULL):
                by_place[r["place"]].append((plant, r))
                landed = True
        if not landed:
            nowhere.append(plant)
    if as_json:
        print(json.dumps(
            {"places": {k: [{"plant": p["botanical"], "verdict": r["verdict"],
                             "name": p["name"]} for p, r in v]
                        for k, v in by_place.items()},
             "nowhere": [p["botanical"] for p in nowhere],
             "stamps": stamps}, indent=2))
        return
    for pl in sorted(ps, key=lambda x: -(x["hours"] or 0)):
        rows = by_place[pl["id"]]
        print(f"{pl['label']}  —  {pl['hours']} h, {pl['category']}, "
              f"{len(rows)} of {len(catalog['plants'])} fit")
        for plant, r in sorted(rows, key=lambda t: -(t[1].get(
                "light_margin_h") or -99)):
            flag = "" if r["verdict"] == FITS else "   (no row free)"
            print(f"    {plant['name']:<34} {plant['botanical']}{flag}")
        print()
    if nowhere:
        print(f"GOES NOWHERE HERE  ({len(nowhere)})")
        for p in nowhere:
            print(f"    {p['name']:<34} {p['botanical']}")
        print()
    print("\n".join(_stamp_lines(stamps)))


if __name__ == "__main__":
    main()
