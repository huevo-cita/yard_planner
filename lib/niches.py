#!/usr/bin/env python3
"""niches.json — the ground grouped by what will grow in it, and who chooses.

    python3 -m lib.niches <slug> --derive        the niches, from the measured site
    python3 -m lib.niches <slug> --capacity      how many plants each has room for
    python3 -m lib.niches <slug> --compositions  arrangements worth having a view on
    python3 -m lib.niches <slug> --slate FILE    record researched candidates
    python3 -m lib.niches <slug> --rank          a top recommendation per slot, with why
    python3 -m lib.niches <slug> --photos        iNaturalist photos for the candidates
    python3 -m lib.niches <slug> --ask           file the choice cards
    python3 -m lib.niches <slug> --ballot        serve it to a phone on the LAN
    python3 -m lib.niches <slug> --recommend-all take every recommendation
    python3 -m lib.niches <slug> --sync FILE     fold the picks back in
    python3 -m lib.niches <slug> --review        every pick, its reason, and what was not taken
    python3 -m lib.niches <slug> --reopen SLOT --reason "..."
    python3 -m lib.niches <slug> --export        picked plants into design.json
    python3 -m lib.niches <slug> --check         stale slates, empty slots

Why this exists
---------------
The yard already knows which plants *can* live in a given patch of ground.
`lib.design` checks light, water, pH, depth and area, and objects where the site
cannot support a planting. What it has no way to know is which of the plants
that fit anyone would be glad to look at — and there is no shortage of them.
Somebody dislikes the smell of a plant, or the way it looks in winter, or has a
bad association with it that nothing in a measurement will ever reveal.

So: group the ground into niches, work out how much room each one has, fill
every slot with candidates that all already fit, and put the choice to a person
with photographs.

Declining is a first-class answer
---------------------------------
Most people setting up a yard for the first time do not want fourteen decisions,
and for a bed nobody looks at they are right not to. So the recommendation is
computed either way, the opening question is whether they want to choose at all,
and taking the recommendations is one command. A deferral is recorded as
`deferred` rather than `decided`, so the question *which slots did nobody
actually look at* is answerable months later.

Every decision stays revisable, permanently. `--review` shows what was picked
and what was not taken, `--reopen` puts a slot back in play, and each slot keeps
a `decisions[]` trail rather than being overwritten. Reopening late in the
season warns rather than refuses, and says when the next window opens.

A niche is a growing-condition signature, not a bed
---------------------------------------------------
Two beds with the same light, soil and water are one niche and get one slate; a
single bed whose ends straddle a light threshold is two. g03 on the yard this
was written against runs 4.73 h at its south end and 3.77 at its north, which
lands either side of the 4.0 h that separates part sun from part shade in
`design.LIGHT_NEED`, so the same bed genuinely supports two different plantings.

WHICH SERIES the light figure comes from is not a detail, and this module states
it rather than leaving it to be inferred, because the answer changes the split.
It uses the growing-season mean of `effective` hours from `sun-hours.json` — the
same series `design.zone_hours` averages — for one reason that overrides every
other consideration: a slot budgeted against one series and linted against
another can offer a candidate the linter will then reject, and a slate that
does that is worse than no slate. The other readings are printed alongside so
the choice can be argued with, and on g03 they disagree: the Mar 20 column
reads 4.85 and 3.41, and 13 December reads 3.90 and 2.47, which straddles 3.0
instead and would split the bed somewhere else entirely.

A slot, not a bed
-----------------
The unit of choice is a slot: a layer within a niche, with a size class and a
count. "Four large, or two large and two medium and two small" is not
arithmetic, it is a different kind of bed, and that is the thing a person can
have an opinion about — so `--compositions` asks it first, and only where the
area genuinely supports alternatives. A 13 sq ft bed has one sensible answer.

The slot budget comes from `design.check_space`'s own band, 45 to 115 percent
of usable area at mature spread, so a planting assembled here passes that check
by construction rather than by luck.
"""
import argparse
import datetime
import hashlib
import json
import os
import re

from . import design, doubts, yards

# The months a perennial is actually growing here, and therefore the months a
# light figure has to describe. Winter is reported separately rather than
# averaged in, because a bed that is bright in December and dark in July is a
# different proposition from the reverse and the mean hides both.
GROWING = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
WINTER = ["Dec", "Jan"]

# Size classes, by mature spread. The boundaries are where the practical
# question changes: under a foot a plant is edging and is planted in runs, one
# to two feet is a front-row clump, and over three feet it is a shrub that
# governs the bed rather than filling it.
SIZES = [
    ("edging", 0.0, 1.0, 5),
    ("small", 1.0, 2.0, 3),
    ("medium", 2.0, 3.0, 3),
    ("large", 3.0, 5.0, 1),
    ("anchor", 5.0, 99.0, 1),
]

# Which layers a border wants, and the share of its area each should take.
# Front-heavy on purpose: the front row is what is seen from a seat, and a bed
# planted evenly across its layers reads as a hedge with things in front of it.
LAYERS = [("back", 0.40), ("middle", 0.35), ("front", 0.25)]

SETTLED = ("decided", "deferred")


# --------------------------------------------------------------- the file

def blank(slug):
    return {"yard": slug, "created": datetime.date.today().isoformat(),
            "series": series_note(), "niches": [], "notes": []}


def load(slug):
    return yards.load(slug, "niches.json") or {}


def save(slug, data):
    return yards.save(slug, "niches.json", data)


def series_note():
    return {
        "light": "growing-season mean of `effective` hours, sun-hours.json",
        "months": GROWING,
        "why": "the same series design.zone_hours averages, so a slot budgeted "
               "here is judged by check_light on the same number. A slate built "
               "against a different series can offer a candidate the linter "
               "then rejects.",
        "winter_reported_separately": WINTER,
    }


def _slots(niche):
    return niche.get("slots") or []


def find(data, ident):
    """A niche or a slot, by id. Both, because every command takes either."""
    for n in data.get("niches") or []:
        if n["id"] == ident:
            return n, None
        for s in _slots(n):
            if s["id"] == ident:
                return n, s
    return None, None


# --------------------------------------------------------------- signatures

def signature(niche):
    """A digest of the growing conditions, and nothing else.

    What a slate is bound to. It deliberately excludes the label, the notes,
    the slots and every pick, so that re-deriving after a sun model re-run
    invalidates a slate only when the *conditions* moved — and does invalidate
    it then, rather than leaving a plant list chosen for a bed that has since
    turned out to be shadier.
    """
    facts = {
        "light_h": round(float((niche.get("light") or {}).get("hours") or 0), 1),
        "category": (niche.get("light") or {}).get("category"),
        "soil": niche.get("soil"),
        "water": niche.get("water"),
        "area_sqft": round(float(niche.get("area_sqft") or 0), 1),
        "depth_ft": round(float(niche.get("usable_depth_ft") or 0), 2),
        "kind": niche.get("kind"),
    }
    blob = json.dumps(facts, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# --------------------------------------------------------------- deriving

_FT = re.compile(r"ft\s*([\d.]+)\s*-\s*([\d.]+)")


def position_spans(slug, zone_label):
    """(from_ft, to_ft, hours) within one bed, out of position-sun.json.

    The keys of that file are free text named after the planting being
    re-chosen — "g03 ft 3-5   white mistflower" — so deriving a niche from them
    inherits the structure of the very thing the person is about to change, and
    needs the foot range pulled out of a label with a regex. That is a real
    limitation and it is reported rather than hidden: where there is no
    position-sun coverage, a bed is one niche whatever its ends actually do.
    """
    pos = yards.load(slug, "position-sun.json") or {}
    out = []
    for key, vals in pos.items():
        if not key.lower().startswith(zone_label.lower()):
            continue
        hit = _FT.search(key)
        if not hit or not isinstance(vals, dict):
            continue
        h = vals.get("growing_season_mean")
        if h is None:
            continue
        out.append((float(hit.group(1)), float(hit.group(2)), float(h), key))
    return sorted(out)


def along_the_bed(spans):
    """(kept, dropped) — the spans that describe distance ALONG a bed.

    Some of those keys are not positions along the bed at all: g02 carries both
    "ft 0-3 west corner block" and "ft 0-3 damianita" for the FRONT row, which
    is the same three feet of length at a different depth into the bed. They
    read 5.46 h and 6.13 h, and treating them as neighbours makes the bed look
    like it crosses a light threshold at ft 0 — which produced a niche of zero
    square feet the first time this ran.

    Variation across a bed's depth is real and worth knowing, but it is a
    different axis from variation along it, and only one of them can split a bed
    into lengths. Keep a non-overlapping run and hand back the rest to be
    reported rather than silently dropped.
    """
    kept, dropped, edge = [], [], None
    for s in sorted(spans):
        if edge is not None and s[0] < edge:
            dropped.append(s)
            continue
        kept.append(s)
        edge = s[1]
    return kept, dropped


def _mean(spans):
    """Length-weighted mean hours over a run.

    Weighted, because two feet at 4.73 h and one foot at 4.07 h is not 4.40:
    most of that piece of bed is brighter than the midpoint, and a slate chosen
    for the midpoint is chosen for ground that does not exist.
    """
    total = sum(b - a for a, b, _, _ in spans) or 1.0
    return sum((b - a) * h for a, b, h, _ in spans) / total


def light_band(hours):
    """The brightest label this many hours actually supports."""
    return design._label_for(hours)


# A piece of bed smaller than this is not a planting, it is a gap. Splitting a
# bed into a niche nobody can plant produces a question nobody can answer.
MIN_NICHE_SQFT = 4.0


def split(spans):
    """Cut a bed in two where it crosses a light threshold, or don't.

    Returns [(spans, hours)] — one piece if the bed is one niche, two if its
    ends genuinely support different plantings. Only thresholds actually
    straddled, one cut at most, and never a cut that leaves a sliver: splitting
    at every flicker produces a dozen two-foot niches and a dozen questions,
    which is its own way of making the whole thing ignorable.
    """
    if len(spans) < 2:
        return [(spans, _mean(spans))], None
    thresholds = sorted({v[0] for v in design.LIGHT_NEED.values() if v[0] > 0})
    lo = min(h for _, _, h, _ in spans)
    hi = max(h for _, _, h, _ in spans)
    crossed = [t for t in thresholds if lo < t < hi]
    if not crossed:
        return [(spans, _mean(spans))], None

    # The threshold nearest the middle of the range: the one the bed most
    # decisively sits either side of, rather than one it grazes at one end.
    t = min(crossed, key=lambda x: abs(x - (lo + hi) / 2))
    at = None
    for i in range(len(spans) - 1):
        if (spans[i][2] >= t) != (spans[i + 1][2] >= t):
            at = i + 1
            break
    if at is None:
        return [(spans, _mean(spans))], None
    a, b = spans[:at], spans[at:]
    run = spans[-1][1] - spans[0][0]
    if min(sum(y - x for x, y, _, _ in p) for p in (a, b)) < 0.15 * run:
        return [(spans, _mean(spans))], None
    return [(a, _mean(a)), (b, _mean(b))], (spans[at][0], t)


def derive(slug):
    """Build the niches from what was measured. Never invents a condition."""
    site = yards.load_site(slug)
    cond = yards.load_conditions(slug)
    vis = yards.load_vision(slug)
    sun = yards.load(slug, "sun-hours.json")
    if not sun:
        raise SystemExit(
            f"{slug} has no sun-hours.json, and light is the condition that "
            f"decides most of this.\n  python3 -m lib.sunmodel {slug}")

    areas = design.zone_areas(site)
    constraints = _constraints(vis)
    out, notes = [], []

    planted = [k for k, z in (site.get("zones") or {}).items()
               if isinstance(z, dict) and (z.get("style") == "bed"
                                           or k in areas)]
    for key in sorted(planted):
        z = site["zones"][key]
        area = areas.get(key)
        if not area:
            notes.append(f"{key} has no usable area, so it gets no niche and "
                         f"nothing will be offered for it. Set area_sqft on the "
                         f"zone in site.json.")
            continue
        label = z.get("label_short") or z.get("label") or key
        hours = design.zone_hours(sun, site, key, GROWING)
        if hours is None:
            notes.append(f"{key} has no sun-hour figure under any name the sun "
                         f"table uses, so it gets no niche.")
            continue
        winter = design.zone_hours(sun, site, key, WINTER)
        timing = ((sun.get("sun_timing") or {}).get(
            design.resolve_zone(sun, site, key) or key) or {})

        raw = position_spans(slug, label)
        spans, crosswise = along_the_bed(raw)
        if crosswise:
            rows = ", ".join(f"{h:g} h at {k.split('  ')[-1].strip()}"
                             for _, _, h, k in crosswise)
            notes.append(
                f"{label} has position-sun readings that cover the same feet "
                f"twice — {rows} — which is variation across the depth of the "
                f"bed, not along its length. They are not used to split it, "
                f"because only one axis can, but the front of this bed is "
                f"brighter than the back and that is worth knowing when the "
                f"front row is chosen.")

        pieces, cut = split(spans) if spans else ([([], hours)], None)
        run = (spans[-1][1] - spans[0][0]) if spans else 0
        if cut and run:
            smallest = min(sum(b - a for a, b, _, _ in p) / run
                           for p, _ in pieces) * area
            if smallest < MIN_NICHE_SQFT:
                notes.append(
                    f"{label} crosses the {cut[1]:g} h threshold at ft "
                    f"{cut[0]:g}, but that leaves {smallest:.1f} sq ft on one "
                    f"side — too little to plant as its own thing. It stays "
                    f"one niche, chosen for the darker end so nothing offered "
                    f"for it is short of light.")
                pieces, cut = [(spans, min(h for _, h in pieces))], None
        if cut:
            at, t = cut
            notes.append(
                f"{label} is two niches, cut at ft {at:g} where it crosses the "
                f"{t:g} h threshold: {pieces[0][1]:.2f} h one side and "
                f"{pieces[1][1]:.2f} h the other, which is "
                f"{light_band(pieces[0][1])} against "
                f"{light_band(pieces[1][1])}. Those are growing-season means. "
                f"The other readings of the same bed disagree — the Mar 20 "
                f"column is brighter throughout, and 13 December is dark "
                f"enough that it would straddle a lower threshold and cut the "
                f"bed somewhere else. The foot ranges come from "
                f"position-sun.json, whose keys are named after the planting "
                f"being re-chosen, so this split partly inherits the shape of "
                f"what is being replaced.")

        for i, (piece, h) in enumerate(pieces):
            single = len(pieces) == 1
            # Share by the extent of the piece, not by the feet position-sun
            # happens to cover. That file has gaps — g03 has no reading at ft
            # 5-6 or 7-8 — and counting only covered feet quietly shrinks the
            # bed by however much nobody sampled.
            share = 1.0 if (single or not run) else \
                (piece[-1][1] - piece[0][0]) / run
            span_label = (label if single else
                          f"{label} ft {piece[0][0]:g}-{piece[-1][1]:g}")
            n = {
                "id": key if single else f"{key}-{i + 1}",
                "label": span_label,
                "zones": [key],
                "kind": design.zone_kind(site, key),
                "area_sqft": round(area * share, 1),
                "usable_depth_ft": z.get("usable_depth_ft"),
                "light": {
                    "hours": round(h, 2),
                    "category": light_band(h),
                    "winter_hours": winter,
                    "afternoon_share": timing.get("after_1pm_share"),
                    "first_sun_clock": timing.get("first_sun_clock"),
                },
                "soil": _soil(cond, design.zone_kind(site, key)),
                "water": _water(cond, key),
                "constraints": constraints,
            }
            if not single:
                n["span_ft"] = [piece[0][0], piece[-1][1]]
            if n["kind"] == "container":
                n["containers"] = design.zone_containers(site, key)
            if n["kind"] == "grid":
                n["squares"] = z.get("squares")
            n["signature"] = signature(n)
            out.append(n)

    # Two beds with the same conditions are one question, not two. Collapsing
    # them is what stops the ballot asking the same thing twice, and it is also
    # good design: the same plant repeated across the garden reads as rhythm.
    merged, seen = [], {}
    for n in out:
        sig = n["signature"]
        if sig in seen and n["kind"] == seen[sig]["kind"]:
            first = seen[sig]
            first["zones"] += n["zones"]
            first["area_sqft"] = round(first["area_sqft"] + n["area_sqft"], 1)
            first["label"] += f" + {n['label']}"
            notes.append(f"{n['label']} has the same growing conditions as "
                         f"{first['zones'][0]}, so they are one niche and get "
                         f"one slate. The same plant in both is rhythm.")
            continue
        seen[sig] = n
        merged.append(n)

    data = load(slug) or blank(slug)
    data["series"] = series_note()
    # Keep decisions already made. Re-deriving must not silently discard a
    # person's picks, and a niche whose signature moved is reported by --check
    # rather than quietly rebuilt.
    old = {n["id"]: n for n in data.get("niches") or []}
    for n in merged:
        was = old.get(n["id"])
        if was:
            for keep in ("slots", "composition", "compositions"):
                if was.get(keep):
                    n[keep] = was[keep]
    data["niches"] = merged
    data["notes"] = notes
    return data


def _soil(cond, kind="border"):
    """The soil a plant in this niche will actually root in.

    A container is not the ground, and giving it the ground's numbers refuses
    every acidic plant in the garden for a reason that does not apply to it —
    the medium in a pot is whatever gets put in it. `check_soil`'s own advice
    for a pH mismatch is *grow it in a container where the medium is yours*, so
    reading the yard's pH into a container niche contradicts the remedy the
    linter recommends.
    """
    if kind == "container":
        return {"ph": None, "drainage": "as potted", "texture": "potting mix",
                "note": "a pot holds whatever medium goes into it, so the "
                        "yard's pH and clay do not rule here. Whatever is "
                        "chosen sets its own requirement for the mix."}
    s = (cond or {}).get("soil") or {}
    return {"ph": s.get("ph"), "drainage": s.get("drainage"),
            "texture": s.get("texture")}


def _water(cond, key):
    w = (cond or {}).get("water") or {}
    return {"hose_reaches": w.get("hose_reaches"),
            "irrigated": bool(w.get("irrigation")),
            "rain_shadow": key in (w.get("rain_shadow_zones") or [])}


def _constraints(vis):
    """What the person has ruled out, as sentences a candidate is checked
    against. Refusals and `must` wants only — a preference is not a filter."""
    out = []
    for r in (vis or {}).get("refusals") or []:
        out.append(r if isinstance(r, str) else r.get("want") or str(r))
    for d in (vis or {}).get("dislikes") or []:
        out.append("dislikes: " + (d.get("want") if isinstance(d, dict)
                                   else str(d)))
    style = (vis or {}).get("style") or {}
    if isinstance(style, dict) and style.get("stated"):
        out.append("style: " + style["stated"])
    return out


# --------------------------------------------------------------- capacity

def capacity(slug, data=None):
    """Slots per niche: a layer, a size class, and how many will fit.

    Budgeted against `design.check_space`'s own band so the result passes that
    check by construction. Two constraints beyond area, both of which have bitten
    a real bed:

      depth   a size class whose mature spread exceeds the usable depth is
              excluded outright, however much area there is. A two-foot rosette
              in a bed two foot five deep has nowhere to go.
      group   a slot with room for two of something offers three, or a smaller
              class. `check_grouping` already objects that one of everything
              reads as a collection rather than a planting, and two is the same
              failure with an extra plant.
    """
    data = data or load(slug)
    if not data.get("niches"):
        raise SystemExit(f"{slug} has no niches yet: --derive first")

    for n in data["niches"]:
        if n["kind"] == "container":
            n["slots"] = _container_slots(n)
            continue
        if n["kind"] == "grid":
            n["slots"] = _grid_slots(n)
            continue
        n["slots"] = _border_slots(n)
    return data


def _fits(spread, depth):
    return depth is None or spread <= float(depth)


def _footprint(rep):
    return 3.1416 * (rep / 2.0) ** 2


def _classes_for(layer, depth):
    """Size classes a layer can hold at this depth, biggest first.

    A back row wants the largest thing that fits, a front row the smallest, and
    the depth of the bed decides what "largest" means. Depth is an outright
    exclusion, not a penalty: area is not the constraint on a plant wider than
    the bed, and no amount of square footage gives it somewhere to go.
    """
    order = {"back": ["anchor", "large", "medium", "small"],
             "middle": ["medium", "large", "small"],
             "front": ["small", "edging"]}[layer]
    by_name = {c: (lo, hi, m) for c, lo, hi, m in SIZES}
    out = []
    for name in order:
        lo, hi, minimum = by_name[name]
        rep = (lo + hi) / 2 if hi < 90 else lo + 1.0
        if _fits(rep, depth):
            out.append((name, rep, _footprint(rep), minimum))
    return out


# How many rows a bed of a given depth physically has. A two-and-a-half foot
# border is a back row and a front row; calling for a middle row as well is
# asking for three plants standing on each other's feet, and the bed then reads
# as overplanted for a reason no count will explain.
def _rows_for(depth):
    if depth is None:
        return [lay for lay, _ in LAYERS]
    d = float(depth)
    if d < 1.5:
        return ["front"]
    if d < 3.0:
        return ["back", "front"]
    return [lay for lay, _ in LAYERS]


def _no_row(layer, depth, rows):
    return (f"a bed {float(depth):.1f} ft deep holds "
            f"{len(rows)} row{'' if len(rows) == 1 else 's'} "
            f"({' and '.join(rows)}), not three. There is no {layer} of this "
            f"bed to plant")


def _border_slots(n):
    """Lay a border out as rows, spending an area budget from the back forwards.

    The order matters. The back row is what the bed is *for* — it is the thing
    seen over everything else — so it gets first call on the space, and the
    front row takes what is left. A bed too small to afford a minimum group in
    some layer loses that layer entirely rather than being given two of
    something, because two of a thing is the collection `check_grouping`
    objects to, with an extra plant.
    """
    area, depth = float(n["area_sqft"]), n.get("usable_depth_ft")
    floor = area * design.COVER_FLOOR
    ceiling = area * design.COVER_CEILING
    slots, excluded, spent_lo, spent_hi = [], [], 0.0, 0.0

    rows = _rows_for(depth)
    total = sum(sh for lay, sh in LAYERS if lay in rows)
    for layer, raw_share in LAYERS:
        if layer not in rows:
            excluded.append((layer, _no_row(layer, depth, rows)))
            continue
        share = raw_share / total
        choices = _classes_for(layer, depth)
        pick = None
        for name, rep, foot, minimum in choices:
            # Affordable only if the minimum group still fits under the ceiling
            # once the rows behind it have been paid for. This is the check
            # that stops three groups of three being proposed for a bed with
            # room for six plants.
            if spent_lo + foot * minimum <= ceiling:
                pick = (name, rep, foot, minimum)
                break
        if not pick:
            reason = (f"even {choices[-1][3]} of the smallest {layer}-row "
                      f"plant is {choices[-1][3] * choices[-1][2]:.1f} sq ft, "
                      f"and only {ceiling - spent_lo:.1f} sq ft of the "
                      f"{area:.0f} is left once the rows behind it are planted"
                      if choices else
                      f"every {layer}-row size spreads wider than this bed's "
                      f"{depth:g} ft of usable depth")
            excluded.append((layer, reason))
            continue

        name, rep, foot, minimum = pick
        lo = max(minimum, round(floor * share / foot))
        lo = min(lo, max(minimum, int((ceiling - spent_lo) // foot)))
        hi = max(lo, int(ceiling * share / foot))
        hi = min(hi, max(lo, int((ceiling - spent_hi) // foot)))
        spent_lo += foot * lo
        spent_hi += foot * hi
        slots.append({
            "id": f"{n['id']}.{layer}",
            "layer": layer,
            "size": name,
            "spread_ft": round(rep, 2),
            "count": [lo, max(lo, hi)],
            "each_sqft": round(foot, 1),
            "budget_share": round(share, 3),
            "why": (f"the {layer} row of {n['label']}. A {name} plant here "
                    f"spreads about {rep:g} ft and takes {foot:.1f} sq ft, so "
                    f"{lo} to {hi} of them keeps the bed inside the "
                    f"{design.COVER_FLOOR:.0%}-{design.COVER_CEILING:.0%} "
                    f"coverage the design check wants. At least {minimum}, "
                    f"because fewer of one thing reads as a collection rather "
                    f"than a planting."),
            "alternatives": [c[0] for c in choices if c[0] != name],
            "decisions": [],
        })

    for layer, reason in excluded:
        slots.append({"id": f"{n['id']}.{layer}", "layer": layer, "size": None,
                      "count": [0, 0], "excluded": reason, "decisions": []})

    if slots and spent_lo:
        n["budget"] = {
            "usable_sqft": round(area, 1),
            "at_minimum_counts": round(spent_lo, 1),
            "at_maximum_counts": round(spent_hi, 1),
            "band_sqft": [round(floor, 1), round(ceiling, 1)],
        }
    return slots


def _container_slots(n):
    pots = n.get("containers") or 1
    return [{"id": f"{n['id']}.pot{i + 1}", "layer": f"pot {i + 1}",
             "size": "container", "count": [1, 1],
             "why": f"one plant per container, pot {i + 1} of {pots}. Two root "
                    f"systems in a barrel is one plant and its shadow.",
             "decisions": []} for i in range(pots)]


def _grid_slots(n):
    """A square-foot bed is chosen by the square, not by the layer.

    Deliberately coarse: three bands along the bed rather than 32 questions.
    Nobody wants to be asked 32 times, and the bands are how the owner's own
    layout is organised anyway — tall at one end, colour at the other.
    """
    squares = n.get("squares") or 0
    if not squares:
        return []
    per = max(1, squares // 3)
    bands = [("tall end", per), ("middle", per), ("colour end",
                                                  squares - 2 * per)]
    return [{"id": f"{n['id']}.{name.replace(' ', '-')}", "layer": name,
             "size": "square", "count": [k, k],
             "why": f"{k} of {squares} squares, the {name} of the bed.",
             "decisions": []} for name, k in bands]


# --------------------------------------------------------------- compositions

# Three ways to arrange the same square footage. They are not styles applied on
# top of a planting — they change how many plants of what size are bought, so
# the question has to be settled before any species is offered.
ARRANGEMENTS = [
    ("anchored",
     "one big plant that holds the bed, a few mid-size drifts around it, and a "
     "run of edging at the front",
     "reads as designed rather than collected, and still has shape in "
     "February when most of it is cut back",
     "the anchor is the expensive plant and the slowest to establish, and if "
     "it fails the bed has an obvious hole in it",
     1.15),
    ("layered",
     "no single anchor: three or four kinds in each row, in overlapping drifts",
     "the longest season of interest, because something is always coming into "
     "flower as something else goes over",
     "the most to look after, and the most things to learn the habits of. This "
     "is the arrangement that most rewards time in the garden and most "
     "punishes a busy spring",
     1.30),
    ("massed",
     "one mid-size plant repeated across the whole bed, with at most one other",
     "the calmest to look at, the cheapest per square foot, and by a distance "
     "the easiest to keep — one plant's habits to learn, one pruning date",
     "one flowering season rather than several, and if that plant turns out to "
     "dislike the spot the whole bed fails at once",
     0.80),
]

# Under this, the arrangements stop being different things. A bed with room for
# six plants laid out three ways gives three descriptions of the same six
# plants, and asking about it spends the person's patience on nothing.
COMPOSITION_MIN_SQFT = 25.0


def compositions(slug, data=None):
    """Offer arrangements, but only where they would actually differ.

    The number of questions asked has to scale with the size of the space.
    Somebody with one small bed and one big one should be asked once, about the
    big one — and asking them twice is how the whole mechanism gets skipped.
    """
    data = data or load(slug)
    asked, skipped = [], []
    for n in data.get("niches") or []:
        if n.get("kind") != "border":
            skipped.append((n, f"a {n['kind']} bed is arranged by its "
                               f"{'pots' if n['kind'] == 'container' else 'squares'}, "
                               f"and there is only one way to do that"))
            n.pop("compositions", None)
            continue
        area = float(n.get("area_sqft") or 0)
        rows = [s for s in _slots(n) if not s.get("excluded")]
        if area < COMPOSITION_MIN_SQFT or len(rows) < 2:
            skipped.append((n, f"{area:.0f} sq ft over {len(rows)} row"
                               f"{'' if len(rows) == 1 else 's'} has one "
                               f"sensible answer, so there is nothing to "
                               f"choose between"))
            n.pop("compositions", None)
            continue

        opts = []
        for name, what, pro, con, cost in ARRANGEMENTS:
            plants = sum(s["count"][0] for s in rows)
            opts.append({
                "name": name, "what": what, "pro": pro, "con": con,
                "roughly": f"about {round(plants * cost)} plants, "
                           f"{'more' if cost > 1 else 'less'} than the "
                           f"{plants} a plain reading of the area gives"
                           if cost != 1.0 else f"about {plants} plants",
                "cost_index": cost,
            })
        # Recommend against the maintenance the person actually has time for,
        # not against what looks best in a photograph.
        n["compositions"] = {"options": opts,
                             "recommended": _recommend_arrangement(slug, n),
                             "chosen": n.get("composition")}
        asked.append(n)
    return data, asked, skipped


def _recommend_arrangement(slug, n):
    cond = yards.load_conditions(slug) or {}
    vis = yards.load_vision(slug) or {}
    person = cond.get("person") or {}
    hours = (person.get("hours_per_week")
             or (person.get("time") or {}).get("hours_per_week"))
    exp = (person.get("experience") or "").lower()
    if isinstance(hours, dict):
        hours = hours.get("low") or hours.get("value")
    thin = (isinstance(hours, (int, float)) and hours <= 3) or exp in (
        "none", "a little")

    # A bed whose stated job is feeding things cannot be massed, whatever the
    # hours say. One species is one flowering season, and a pollinator bed with
    # one flowering season is empty of nectar for most of the year — which is
    # not a maintenance trade-off, it is the bed failing at the thing it was
    # asked to do.
    blob = json.dumps(vis).lower()
    feeds = any(w in blob for w in ("pollinator", "butterfl", "monarch",
                                    "nectar", "wildlife", "bees"))
    if thin and not feeds:
        return {"name": "massed",
                "because": "the hours on record are the binding constraint "
                           "here, and a massed bed is one plant's habits to "
                           "learn and one pruning date"}
    if thin and feeds:
        return {"name": "anchored",
                "because": "the hours on record point at a massed bed, but "
                           "this one is meant to feed butterflies and bees, "
                           "and one species is one flowering season with "
                           "nothing on either side of it. Anchored is the "
                           "compromise: a few kinds with staggered flowering, "
                           "and far less to look after than a layered bed"}
    if float(n["area_sqft"]) > 60:
        return {"name": "anchored",
                "because": "a bed this size without an anchor reads as a strip "
                           "of undifferentiated planting from any distance"}
    return {"name": "layered",
            "because": "enough room for real drifts, and the hours on record "
                       "cover the extra looking-after"}


# --------------------------------------------------------------- the slate

# Everything design.py will later judge a plant on. A candidate missing any of
# these cannot be checked, and a candidate that cannot be checked has no
# business on a ballot: the whole promise of this stage is that everything
# offered already fits.
REQUIRED = ("name", "botanical", "light", "water", "mature_spread_ft",
            "mature_height_ft", "source")


def slate(slug, incoming, data=None):
    """Record researched candidates per slot, refusing the ones that do not fit.

    The refusal is the point. If the ballot can offer a plant that
    `lib.design` will later reject, then somebody chooses a plant, likes it,
    and is told afterwards that it was never possible — which is worse than not
    having been asked. So every candidate is put through the same three
    constraints the linter uses, here, before anybody sees it.
    """
    data = data or load(slug)
    site = yards.load_site(slug)
    sun = yards.load(slug, "sun-hours.json") or {}
    kept, refused = 0, []
    for slot_id, cands in incoming.items():
        n, s = find(data, slot_id)
        if not s:
            refused.append((slot_id, "-", "there is no slot with that id"))
            continue
        ok = []
        for c in cands:
            why = _rejects(c, n, s, site, sun)
            if why:
                refused.append((slot_id, c.get("name", "?"), why))
                continue
            c = dict(c)
            c["fit"] = _fit(c, n, s)
            ok.append(c)
            kept += 1
        s["candidates"] = ok
        s["slate_signature"] = n["signature"]
        s["slated"] = datetime.date.today().isoformat()
    return data, kept, refused


def _rejects(c, niche, slot, site, sun):
    missing = [f for f in REQUIRED if not c.get(f)]
    if missing:
        return f"no {', '.join(missing)} recorded, so it cannot be checked"

    want = (c.get("light") or "").lower()
    if want not in design.LIGHT_NEED:
        return f"light {c['light']!r} is not one of {', '.join(design.LIGHT_NEED)}"
    need = design.LIGHT_NEED[want][0]

    # Ask the light question exactly the way check_light will ask it, on the
    # same zone and over the same months. This is the whole reason the module
    # docstring makes a point of naming its series: check_light averages over
    # each plant's OWN bloom months, not over the growing season, so a winter
    # crop is judged on December light. A slate built on the growing-season
    # figure offers broccoli for a bed that is full sun in July and a long way
    # short of it in December — which the linter then rejects, after somebody
    # has chosen it.
    zone = niche["zones"][0]
    months = c.get("months") or c.get("bloom") or None
    have = design.zone_hours(sun, site, zone, months)
    when = (f"over {', '.join(months)}" if months else "over the year")
    if have is not None and have < need:
        return (f"wants {want} — {need:g} h — and {zone} averages "
                f"{have:.2f} h {when}, which is the figure check_light will "
                f"use. The growing-season mean for this niche is "
                f"{niche['light']['hours']} h, which is the brighter reading "
                f"and not the one that governs")
    # And the other end of it. A shade plant in a bed that gets six hours in a
    # climate with a real summer scorches in July, and check_light blocks that
    # too — so a slate that only tests the floor offers exactly the wrong plant
    # for the brightest bed in the garden.
    hot = ((site.get("climate") or {}).get("heat") or {}).get(
        "days_over_95f_per_year")
    if (want in ("shade", "part shade") and have is not None
            and hot and hot > 20 and have > need + design.SCORCH_MARGIN):
        return (f"is a {want} plant and {zone} averages {have:.2f} h {when}, "
                f"in a climate with {hot} days over 95 F. It will scorch in "
                f"July whatever the watering, and design.py says so")
    have = have if have is not None else float(niche["light"]["hours"])

    depth = niche.get("usable_depth_ft")
    spread = float(c["mature_spread_ft"])
    if depth and spread > float(depth) + float(niche.get("overhang_ft") or 0):
        return (f"spreads {spread:g} ft in a bed {float(depth):.1f} ft deep. "
                f"Area is not the constraint; there is nowhere for it to go")

    # Against this slot's share of the bed, not the whole bed. Checking each
    # row against the whole niche lets every row pass on its own and the bed
    # be overplanted once they are added up — g01 came out at 1.49x that way,
    # with two rows that each looked fine, because a candidate is allowed to
    # sit at the top of its size class rather than at the midpoint the budget
    # was drawn against.
    share = slot.get("budget_share")
    if slot.get("count") and slot["count"][0] and share:
        room = float(niche["area_sqft"]) * design.COVER_CEILING * share
        need = _footprint(spread) * slot["count"][0]
        if need > room:
            return (f"{slot['count'][0]} of it at {spread:g} ft spread is "
                    f"{need:.1f} sq ft, and this row's share of the bed is "
                    f"{room:.1f}. It fits the bed only by taking room the "
                    f"other rows are counting on")

    soil = niche.get("soil") or {}
    ph, rng = soil.get("ph"), c.get("ph_range")
    if ph and rng and not (float(rng[0]) <= float(ph) <= float(rng[1])):
        return f"wants pH {rng[0]}-{rng[1]} and this soil is {ph}"

    drain = (soil.get("drainage") or "").lower()
    if c.get("soil_drainage") == "sharp" and ("slow" in drain
                                              or "poor" in drain):
        return (f"needs sharp drainage and this soil drains {drain}. That is "
                f"the classic slow way to kill a plant — two years, so nobody "
                f"connects it to the soil — and design.py blocks it outright")
    return None


def _fit(c, niche, slot):
    """How much margin a candidate has, so a recommendation can be argued for.

    Margin rather than a pass mark: two plants can both fit and one of them be
    two hours of light off the edge of what it wants. That difference is the
    difference between a plant that thrives and one that survives, and it is
    invisible in a yes/no.
    """
    want = design.LIGHT_NEED[(c["light"] or "").lower()][0]
    have = float(niche["light"]["hours"])
    depth = float(niche.get("usable_depth_ft") or 0)
    spread = float(c["mature_spread_ft"])
    return {
        "light_margin_h": round(have - want, 2),
        "depth_margin_ft": round(depth - spread, 2) if depth else None,
        "slot_spread_ft": slot.get("spread_ft"),
        "spread_vs_slot": (round(spread / slot["spread_ft"], 2)
                           if slot.get("spread_ft") else None),
    }


# --------------------------------------------------------------- ranking

def rank(slug, data=None):
    """A top recommendation per slot, and the reason it beat the runner-up.

    A recommendation nobody can argue with is a recommendation nobody can
    check. So each one records its score, the reason in a sentence, and the
    plant that came second — which is not a consolation prize: the runner-up
    becomes the documented substitute for the day the nursery is out of the
    first choice, which `bom` already knows how to use.
    """
    data = data or load(slug)
    vis = yards.load_vision(slug) or {}
    cond = yards.load_conditions(slug) or {}
    src = yards.load(slug, "sourcing.json") or {}
    # A target date arrives in whatever shape the record holds it — a bare ISO
    # string, a recorded preference with a strength, or a sentence describing a
    # season. design._target_month already handles all three, having been
    # written after this exact assumption made the season check silently do
    # nothing on every yard using the documented shape. A second, weaker copy
    # of that parsing here is how the bug comes back.
    try:
        month = design._target_month(vis.get("target_date"))
    except (ValueError, TypeError):
        month = None
    exp = ((cond.get("person") or {}).get("experience") or "").lower()
    disliked = {(d.get("want") or "")[4:].strip()
                for d in (vis.get("dislikes") or []) if isinstance(d, dict)
                and (d.get("want") or "").startswith("not ")}

    ranked = 0
    for n in data.get("niches") or []:
        for s in _slots(n):
            cands = s.get("candidates") or []
            if not cands:
                continue
            scored = sorted(
                ((_score(c, n, month, exp, src), c) for c in cands),
                key=lambda x: -x[0][0])
            # Neither a plant ruled out by a reopen nor one already on the
            # dislikes list. `check_vision` enforces the dislikes, so
            # recommending one produces a design that objects to itself.
            barred = set(s.get("ruled_out") or []) | disliked
            out = [x for x in scored if x[1]["name"] not in barred]
            if not out:
                s["recommended"] = None
                s["no_recommendation"] = (
                    f"every candidate here is either on the dislikes list or "
                    f"was ruled out on a reopen — {', '.join(sorted(barred))}. "
                    f"There is nothing left to recommend, so this one needs "
                    f"more research rather than a default.")
                continue
            (top, why), best = out[0]
            scored = out + [x for x in scored if x not in out]
            s["recommended"] = {
                "name": best["name"],
                "score": round(top, 2),
                "because": why,
                "runner_up": out[1][1]["name"] if len(out) > 1 else None,
                "runner_up_because": out[1][0][1] if len(out) > 1 else None,
                "substitute": out[1][1]["name"] if len(out) > 1 else None,
            }
            if s.get("ruled_out"):
                s["recommended"]["not_offered"] = (
                    f"{', '.join(s['ruled_out'])} ruled out on a reopen, so "
                    f"not recommended — still on the ballot if you change your "
                    f"mind")
            for (sc, w), c in scored:
                c["score"], c["score_why"] = round(sc, 2), w
            s["candidates"] = [c for _, c in scored]
            ranked += 1
    return data, ranked


_MONTHS = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
           "06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct",
           "11": "Nov", "12": "Dec"}

# Rough hours a year of looking after, by how a plant is usually described.
# Coarse on purpose — the difference that matters is between a plant that wants
# nothing and one that wants deadheading every week, not between four hours and
# five.
UPKEEP = {"low": 0.0, "very low": 0.0, "moderate": 1.0, "medium": 1.0,
          "high": 2.0}


def _score(c, niche, month, experience, sourcing):
    """Score a candidate, and say in a sentence why it scored that way."""
    parts, points = [], 0.0

    lm = c["fit"]["light_margin_h"]
    if lm >= 1.5:
        points += 2
        parts.append(f"{lm:.1f} h more light than it needs")
    elif lm >= 0.5:
        points += 1
        parts.append(f"{lm:.1f} h of light in hand")
    else:
        parts.append(f"only {lm:.1f} h of light margin, which is tight")

    dm = c["fit"].get("depth_margin_ft")
    if dm is not None and dm >= 0.5:
        points += 1
        parts.append("comfortably inside the bed's depth")
    elif dm is not None and dm < 0.2:
        parts.append("as wide as the bed is deep")

    if month and month in (c.get("bloom") or []):
        points += 2
        parts.append(f"in flower in {month}, which is what the date on record "
                     f"asks for")
    elif c.get("evergreen"):
        points += 1
        parts.append("evergreen, so it is present on the day whether or not it "
                     "is flowering")

    if c.get("native"):
        points += 1
        parts.append("native")

    up = UPKEEP.get((c.get("maintenance") or "").lower())
    if up == 0.0:
        points += 1
        parts.append("wants next to nothing doing to it")
    elif up and up >= 2.0 and experience in ("none", "a little", "some"):
        points -= 1
        parts.append(f"wants real upkeep, against {experience} experience")

    where = _stocked(c, sourcing)
    if where:
        points += 1
        parts.append(f"stocked at {where}")
    else:
        parts.append("not on any local supplier list, so it may need ordering")

    return points, "; ".join(parts).capitalize() + "."


def _stocked(c, sourcing):
    names = {(c.get("name") or "").lower(), (c.get("botanical") or "").lower()}
    for sup in (sourcing.get("suppliers") or []):
        blob = json.dumps(sup).lower()
        if any(nm and nm in blob for nm in names):
            return sup.get("name") or sup.get("id")
    return None


# --------------------------------------------------------------- photos

# iNaturalist, because it is keyless, free and has a photo of nearly every
# garden plant. Two rules, both non-negotiable:
#
#   host     only inaturalist-open-data. The static.inaturalist.org copies are
#            all-rights-reserved, and using one because it was convenient is a
#            licence breach that would sit in this repo indefinitely.
#   licence  only the open codes below. No code means unknown, and unknown is
#            treated as closed.
#
# And a candidate with no usable photo is labelled as having none. It is never
# dropped — that would quietly bias the ballot toward whatever is well
# photographed — and it is never given a photo of something else.
INAT = "https://api.inaturalist.org/v1/taxa"
OPEN_LICENCES = {"cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"}
OPEN_HOST = "inaturalist-open-data.s3.amazonaws.com"
PHOTO_CACHE = os.path.join(yards.GARDEN_ROOT, ".cache", "plantphotos")
PER_PLANT = 4


def photos(slug, data=None, offline=False):
    data = data or load(slug)
    got, without = 0, []
    seen = {}
    for n in data.get("niches") or []:
        for s in _slots(n):
            for c in s.get("candidates") or []:
                key = (c.get("botanical") or c.get("name") or "").strip()
                if not key:
                    continue
                if key not in seen:
                    seen[key] = _fetch_photos(key, offline=offline)
                c["photos"] = seen[key]
                if seen[key]:
                    got += len(seen[key])
                else:
                    c["no_photo"] = ("no openly-licensed photograph found. "
                                     "Offered anyway — look it up before "
                                     "choosing")
                    without.append(c.get("name") or key)
    return data, got, without


def _fetch_photos(botanical, offline=False):
    import urllib.parse
    import urllib.request
    key = "".join(ch if ch.isalnum() else "_" for ch in botanical.lower())
    os.makedirs(PHOTO_CACHE, exist_ok=True)
    path = os.path.join(PHOTO_CACHE, key + ".json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    if offline:
        return []
    # Two calls, not one. The search endpoint returns a taxon with an empty
    # `taxon_photos`, which looks exactly like a plant nobody has photographed
    # — the first version of this reported no usable photo for all twenty
    # candidates and the filters were not the problem. Only /taxa/<id> carries
    # the photos.
    def get(u):
        r = urllib.request.Request(
            u, headers={"User-Agent": "yard-design/1.0 (garden planning)"})
        with urllib.request.urlopen(r, timeout=20) as fh:
            return json.load(fh)

    # Fall back to the bare binomial. Half of what gets planted here is named
    # to the variety — "Anisacanthus quadrifidus var. wrightii" — and the
    # search finds nothing for the full string while the species has a hundred
    # photographs. The photograph is of the species either way, which is what
    # the label should then say.
    tries = [botanical]
    words = botanical.replace("var.", " ").replace("subsp.", " ").split()
    if len(words) > 2:
        tries.append(" ".join(words[:2]))
    try:
        out = []
        for i, q in enumerate(tries):
            found = get(f"{INAT}?q={urllib.parse.quote(q)}"
                        f"&rank=species,variety,subspecies&per_page=1")
            results = found.get("results") or []
            if not results:
                continue
            out = _usable(get(f"{INAT}/{results[0]['id']}")["results"][0])
            if out and i:
                for ph in out:
                    ph["of"] = (f"the species {q}, not the variety "
                                f"{botanical} specifically")
            if out:
                break
    except Exception:
        return []
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    return out


def _usable(taxon):
    out = []
    for tp in (taxon.get("taxon_photos") or [])[:20]:
        p = tp.get("photo") or {}
        url = p.get("medium_url") or p.get("url") or ""
        lic = (p.get("license_code") or "").lower()
        if OPEN_HOST not in url or lic not in OPEN_LICENCES:
            continue
        out.append({
            "url": url,
            "licence": lic,
            "attribution": p.get("attribution")
            or f"{p.get('native_page_url') or 'iNaturalist'} ({lic})",
        })
        if len(out) >= PER_PLANT:
            break
    return out


# --------------------------------------------------------------- the cards

FORK = "Do you want to choose the plants yourself, niche by niche?"


def ask(slug, data=None):
    """Put the fork and every slot on the doubt board.

    The opening question is itself a card, and either answer settles it
    `decided` — because declining to choose *is* a choice, and recording it as
    something less than one is how a person ends up with a garden nobody
    remembers agreeing to.

    Nothing is settled here. This files and stops. Filing a card and then
    running the job it blocks in the same turn is the failure the whole
    mechanism exists to prevent, and doing it here would be doing it in the one
    place where a human is unambiguously the point.
    """
    data = data or load(slug)
    board = doubts.load(slug)
    have = {c.get("about_slot") for c in board.get("cards", [])
            if c.get("about_slot")}
    asked = {c.get("question") for c in board.get("cards", [])}
    filed = []

    if FORK not in asked:
        c = doubts.record(
            slug, FORK, kind="choice", blocks=["design"],
            priced={"decisions": 3},
            detail="Every niche has a recommendation already worked out, so "
                   "either answer moves. Choosing takes about a minute a slot "
                   "on a phone; taking the recommendations takes one command "
                   "and records that nobody looked, which is worth being able "
                   "to ask about later. Nothing here is permanent either way.",
            options=[
                doubts.option(
                    "choose them myself",
                    pro="the garden contains plants you picked, and the ones "
                        "you turned down stay turned down",
                    con="one pass on a phone, a minute or so per slot",
                    cost="no money, some attention"),
                doubts.option(
                    "take the recommendations",
                    pro="done in one command, and every option stays on file "
                        "to come back to whenever you like",
                    con="the plants are chosen on fit and availability, which "
                        "cannot know what you like the look of",
                    cost="none"),
            ])
        filed.append(c)
        board = doubts.load(slug)

    for n in data.get("niches") or []:
        for s in _slots(n):
            if s.get("excluded") or not s.get("candidates"):
                continue
            if s["id"] in have:
                continue
            rec = s.get("recommended") or {}
            lo, hi = s["count"]
            count = f"{lo}" if lo == hi else f"{lo} to {hi}"
            place = (f"{s['layer']} row" if s["layer"] in
                     ("back", "middle", "front") else s["layer"])
            c = doubts.record(
                slug,
                f"{n['label']}, {place}: which plant, and how many?",
                kind="choice", blocks=["design", "bom"],
                priced={"decisions": 1},
                # A container slot has no row spread to quote, and one plant is
                # not "1 plants". Both read as a template someone forgot to
                # finish, on the one screen a person is asked to decide from.
                detail=(f"{count} plant{'' if lo == hi == 1 else 's'}"
                        + (f" of about {s['spread_ft']:g} ft spread"
                           if s.get("spread_ft") else "")
                        + f". {n['light']['hours']} h of growing-season sun "
                          f"— {n['light']['category']}. Every option below "
                          f"already fits the light, the depth and the soil; "
                          f"the question is only which you would rather look "
                          f"at."),
                options=[doubts.option(
                    c2["name"] + (" (recommended)"
                                  if c2["name"] == rec.get("name") else ""),
                    pro=c2.get("score_why") or "fits",
                    con=c2.get("no_photo") or c2.get("con")
                        or "nothing against it beyond taste",
                    cost=c2.get("price_note") or "see sourcing",
                ) for c2 in s["candidates"]])
            board = doubts.load(slug)
            doubts.find(board, c["id"]).update(
                {"about_slot": s["id"], "about_niche": n["id"]})
            yards.save(slug, "doubts.json", board)
            filed.append(c)
            s["card"] = c["id"]

    return data, filed


def recommend_all(slug, data=None, note=None):
    """Take every recommendation, and say out loud what that decided.

    Never silent. The whole value of `deferred` over `decided` is being able to
    ask later which slots nobody actually looked at, and that is worth nothing
    if the person was not told at the time what was chosen on their behalf.
    """
    data = data or load(slug)
    took = []
    for n in data.get("niches") or []:
        for s in _slots(n):
            rec = s.get("recommended")
            if not rec or s.get("pick"):
                continue
            cand = next((c for c in s.get("candidates") or []
                         if c["name"] == rec["name"]), {})
            how_many = count_for(n, s, cand)
            s["pick"] = {"name": rec["name"], "count": how_many,
                         "chosen_by": "deferred",
                         "substitute": rec.get("substitute")}
            s.setdefault("decisions", []).append({
                "on": datetime.date.today().isoformat(),
                "pick": rec["name"], "count": how_many,
                "by": "deferred", "why": rec.get("because"),
                "note": note or "took the recommendation without looking",
            })
            if s.get("card"):
                try:
                    doubts.settle(slug, s["card"],
                                  f"{rec['name']} x{how_many} — "
                                  f"recommendation taken unread",
                                  by="deferred")
                except SystemExit:
                    pass
            took.append((n, s, rec))
    if took:
        # The fork itself was decided, even though the slots were not. Somebody
        # weighed choosing against not choosing and picked not choosing, and
        # recording that as anything less than a decision is how a person ends
        # up with a garden nobody remembers agreeing to.
        settle_fork(slug, "take the recommendations",
                    f"{len(took)} slots taken as recommended")
    return data, took


# --------------------------------------------------------------- the ballot

# A page title that says nothing about whose garden it is. The slug is the
# street name and `site.label` is no better, and this is served unencrypted to
# whatever else is on the wifi. Niche labels, numbers, plant names and
# photographs, and nothing else.
BALLOT_TITLE = "Choosing plants"


def ballot_html(data, token, saved=None, stamp=None):
    P = []
    A = P.append
    A(f"<!doctype html><html><head><meta charset=utf-8>"
      f"<meta name=viewport content='width=device-width,initial-scale=1'>"
      f"<title>{BALLOT_TITLE}</title><style>{_CSS}</style></head><body>")
    if stamp:
        # A page is a generated document like any other, and this one is the
        # single most misleading thing in the repo to meet unstamped: it asks
        # somebody standing in the garden to decide their real beds. Rehearsing
        # the ballot is the reason the sandbox exists, so the rehearsal has to
        # say so where the decision is actually being made.
        A(f"<p class=stamp>{_esc(stamp)} &mdash; picks made here change the "
          f"copy, not the garden.</p>")
    A(f"<h1>{BALLOT_TITLE}</h1>")
    A("<p class=lede>Everything offered here already fits the light, the soil "
      "and the depth of the bed it is offered for. The only question is which "
      "you would rather look at. Tap once to choose it; tap the same card "
      "again to mark it your second choice, which becomes the substitute if "
      "the nursery is out. Nothing is decided until you press save.</p>")
    if saved:
        A(f"<p class=saved>Saved {saved} choices. You can change any of them "
          f"whenever you like.</p>")
    A(f"<form method=post action='/{token}/save'>")

    for n in data.get("niches") or []:
        slots = [s for s in _slots(n) if s.get("candidates")]
        if not slots:
            continue
        L = n["light"]
        A(f"<section><h2>{_esc(n['label'])}</h2>")
        A(f"<p class=cond>{L['hours']} hours of sun a day through the growing "
          f"season — {L['category']}. {n['area_sqft']} sq ft")
        if n.get("usable_depth_ft"):
            A(f", {float(n['usable_depth_ft']):.1f} ft front to back")
        if L.get("winter_hours"):
            A(f". In December it drops to {L['winter_hours']} hours")
        A(".</p>")
        comp = (n.get("compositions") or {}).get("chosen")
        if comp:
            A(f"<p class=cond>Laid out as a <b>{_esc(comp)}</b> bed.</p>")

        for s in slots:
            lo, hi = s["count"]
            need = f"{lo}" if lo == hi else f"{lo}&ndash;{hi}"
            A(f"<h3>{_esc(s['layer'])} &mdash; room for {need}</h3>")
            A(f"<p class=why>{_esc(s.get('why', ''))}</p>")
            A("<div class=grid>")
            rec = (s.get("recommended") or {}).get("name")
            pick = (s.get("pick") or {}).get("name")
            for c in s["candidates"]:
                on = "sel" if (pick or rec) == c["name"] else ""
                A(f"<label class='card {on}'>")
                A(f"<input type=radio name='{_esc(s['id'])}' "
                  f"value='{_esc(c['name'])}' "
                  f"{'checked' if (pick or rec) == c['name'] else ''}>")
                ph = (c.get("photos") or [])
                if ph:
                    A(f"<img src='{_esc(ph[0]['url'])}' alt='' loading=lazy>")
                    if ph[0].get("of"):
                        A(f"<span class=attr>photo of "
                          f"{_esc(ph[0]['of'])}</span>")
                    A(f"<span class=attr>{_esc(ph[0]['attribution'])[:70]}</span>")
                else:
                    A("<span class=nophoto>no openly-licensed photograph. "
                      "Worth looking it up before you choose &mdash; it is "
                      "listed anyway rather than dropped, because a plant "
                      "without a picture is not a worse plant</span>")
                A(f"<b>{_esc(c['name'])}</b>")
                A(f"<i>{_esc(c.get('botanical', ''))}</i>")
                if c["name"] == rec:
                    A("<span class=rec>recommended</span>")
                A(f"<span class=why>{_esc(c.get('score_why', ''))}</span>")
                if c.get("elsewhere"):
                    A(f"<span class=rhythm>also chosen for "
                      f"{_esc(c['elsewhere'])} &mdash; repeating a plant "
                      f"across the garden reads as rhythm, not as a "
                      f"clash</span>")
                A("</label>")
            A("</div>")
            A(f"<label class=second>Second choice, used if the first is out of "
              f"stock: <select name='{_esc(s['id'])}__sub'><option value=''>"
              f"&mdash;</option>")
            for c in s["candidates"]:
                A(f"<option value='{_esc(c['name'])}'>{_esc(c['name'])}</option>")
            A("</select></label>")
            # Vetoing is a separate act from not choosing, and the ballot has
            # to keep them apart. Picking A over B says you preferred A today;
            # it does not say B should never be offered again anywhere in the
            # garden. Only a ticked box says that, and it needs a reason,
            # because the reason is what makes it survive being re-read in two
            # years by somebody who has forgotten.
            A("<fieldset class=veto><legend>Never offer me these again, "
              "anywhere</legend>")
            for c in s["candidates"]:
                A(f"<label><input type=checkbox name='{_esc(s['id'])}__veto' "
                  f"value='{_esc(c['name'])}'> {_esc(c['name'])}</label>")
            A(f"<input name='{_esc(s['id'])}__no' placeholder='why? "
              f"e.g. the smell reminds me of a hospital'></fieldset>")
        A("</section>")

    A("<button type=submit>Save these choices</button></form>")
    A("</body></html>")
    return "\n".join(P)


_CSS = """
 body{font:16px/1.5 system-ui,sans-serif;margin:0 auto;padding:1rem;
      max-width:52rem;color:#1c1c17;background:#fbfaf6}
 h1{font-size:1.4rem} h2{font-size:1.2rem;margin:2rem 0 .2rem;
      border-bottom:2px solid #cfd8c3;padding-bottom:.2rem}
 h3{font-size:1rem;margin:1.2rem 0 .2rem;text-transform:lowercase;color:#4a5d3a}
 .lede,.cond,.why{color:#5b5b50;font-size:.9rem;margin:.2rem 0}
 .saved{background:#e6efdc;padding:.6rem;border-radius:6px}
 .stamp{background:#8a3b12;color:#fff;padding:.5rem .7rem;margin:0 0 .8rem;border-radius:6px;font-weight:600;letter-spacing:.02em}
 .grid{display:grid;gap:.6rem;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
 .card{display:flex;flex-direction:column;gap:.2rem;border:2px solid #ddd;
       border-radius:10px;padding:.5rem;cursor:pointer;background:#fff}
 .card:has(input:checked){border-color:#4a7c2f;background:#f2f8ec}
 .card input{position:absolute;opacity:0}
 .card img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px}
 .card b{font-size:.95rem} .card i{font-size:.8rem;color:#6b6b5e}
 .attr{font-size:.6rem;color:#8a8a7e}
 .nophoto{font-size:.75rem;color:#8a6d3b;background:#fdf6e3;padding:.4rem;
          border-radius:6px}
 .rec{font-size:.7rem;background:#4a7c2f;color:#fff;padding:.1rem .4rem;
      border-radius:99px;align-self:flex-start}
 .rhythm{font-size:.72rem;color:#4a5d3a;font-style:italic}
 .card .why{font-size:.75rem}
 .second,.no{display:block;font-size:.85rem;margin:.5rem 0;color:#5b5b50}
 .no input,.second select{font:inherit;padding:.3rem;width:100%;max-width:26rem;
       border:1px solid #ccc;border-radius:6px}
 button{position:sticky;bottom:1rem;width:100%;padding:.9rem;font:inherit;
        background:#4a7c2f;color:#fff;border:0;border-radius:10px;margin-top:2rem}
"""


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("'", "&#39;").replace('"', "&quot;"))


def mark_rhythm(data):
    """Note where the same plant is already offered elsewhere.

    Surfaced as rhythm rather than as a clash, because repeating a plant across
    a garden is how a collection of beds turns into one garden — the opposite of
    a mistake, and the ballot should not make it feel like one.
    """
    where = {}
    for n in data.get("niches") or []:
        for s in _slots(n):
            nm = (s.get("pick") or s.get("recommended") or {}).get("name")
            if nm:
                where.setdefault(nm, []).append(n["label"])
    for n in data.get("niches") or []:
        for s in _slots(n):
            for c in s.get("candidates") or []:
                other = [w for w in where.get(c["name"], [])
                         if w != n["label"]]
                c["elsewhere"] = ", ".join(other) if other else None
    return data


def serve(slug, port=8730, host="0.0.0.0"):
    """One page, on the LAN, behind a random token in the path.

    A token rather than a password because the threat here is a housemate's
    laptop finding it by accident, not an attacker — and a login screen on a
    garden ballot is the kind of friction that means it never gets used. It
    binds to the LAN on purpose: the point is to stand in the garden holding
    the phone, looking at the actual bed.
    """
    import secrets
    import socket
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    token = secrets.token_urlsafe(9)
    state = {"data": mark_rhythm(load(slug)), "saved": None,
             "picks": None, "stamp": yards.sandbox_stamp(slug)}

    class H(BaseHTTPRequestHandler):
        def _send(self, body, code=200, ctype="text/html; charset=utf-8"):
            raw = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.rstrip("/") != "/" + token:
                return self._send("Not found", 404, "text/plain")
            self._send(ballot_html(state["data"], token, state["saved"],
                               state["stamp"]))

        def do_POST(self):
            if self.path != f"/{token}/save":
                return self._send("Not found", 404, "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(self.rfile.read(n).decode())
            # Checkboxes repeat the same field name, so a veto of three
            # plants arrives as three values under one key. Keeping only the
            # first would silently drop two of them.
            state["picks"] = {k: (v if k.endswith("__veto") else v[0])
                              for k, v in form.items() if v and v[0]}
            state["saved"] = len([k for k in state["picks"]
                                  if "__" not in k])
            self._send(ballot_html(state["data"], token, state["saved"],
                               state["stamp"]))

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "localhost"
    return srv, f"http://{ip}:{port}/{token}", state


# --------------------------------------------------------------- sync

def settle_fork(slug, answer, how):
    """Settle the opening fork, because acting on it IS answering it.

    The fork blocks `design`. Somebody who works through the ballot, or who
    runs `--recommend-all`, has answered it as plainly as anybody can — and
    leaving it open means the gate refuses after the person has done exactly
    what was asked of them, which is the fastest way to teach someone that the
    gate is noise to be forced past.
    """
    for c in doubts.load(slug).get("cards") or []:
        if c.get("question") == FORK and c.get("status") == "open":
            try:
                doubts.settle(slug, c["id"], f"{answer} — {how}", by="decided")
            except SystemExit:
                pass
            return c["id"]
    return None


def sync(slug, picks, data=None, by="decided"):
    """Fold picks back in — appending to a trail, never overwriting.

    Three things happen besides recording the pick, and each exists because
    losing it would waste the person's attention:

      the trail      every decision is appended, so "what did I pick last
                     time, and why did I change it" has an answer
      the rejections go into `vision.dislikes`, where `check_vision` enforces
                     them permanently. Somebody who says once that they cannot
                     stand a plant should never be offered it again, in this
                     bed or any other, this year or in five years
      the substitute the second choice becomes the documented stand-in for the
                     day the nursery is out, which `bom._substitute` already
                     knows what to do with
    """
    data = data or load(slug)
    vis = yards.load_vision(slug) or {}
    today = datetime.date.today().isoformat()
    changed, rejected = [], []

    for slot_id, choice in picks.items():
        if "__" in slot_id:
            continue
        n, s = find(data, slot_id)
        if not s:
            continue
        no = (picks.get(slot_id + "__no") or "").strip()
        vetoed = picks.get(slot_id + "__veto") or []
        if isinstance(vetoed, str):
            vetoed = [vetoed]
        was = (s.get("pick") or {}).get("name")
        sub = _substitute(s, choice, vetoed, picks.get(slot_id + "__sub"))

        if was != choice:
            cand = next((c for c in s.get("candidates") or []
                         if c["name"] == choice), {})
            how_many = count_for(n, s, cand)
            s["pick"] = {"name": choice, "count": how_many,
                         "chosen_by": by, "substitute": sub}
            s.setdefault("decisions", []).append(
                {"on": today, "pick": choice, "count": how_many, "by": by,
                 "substitute": sub, "was": was, "why": "chosen on the ballot"})
            changed.append((n, s, was, choice))

        # Only what was explicitly ticked. Preferring one plant to another is
        # not a statement that the other is unacceptable, and treating it as
        # one puts words in somebody's mouth that then bind every future
        # design — the first version of this banned a plant the same person had
        # picked in another bed on the same page.
        for name in vetoed:
            if name == choice:
                continue
            rejected.append((name, no or "turned down on the ballot, no reason "
                                         "given", n["label"]))

    # A plant chosen anywhere in the garden cannot also be banned from it. This
    # should be impossible now that a veto has to be ticked, but a dislike is
    # permanent and enforced by check_vision forever, so it is worth one more
    # line to make sure a contradiction cannot be written down.
    chosen = {(s.get("pick") or {}).get("name")
              for nn in data.get("niches") or [] for s in _slots(nn)}
    contradictory = [r for r in rejected if r[0] in chosen]
    rejected = [r for r in rejected if r[0] not in chosen]

    if rejected:
        vis.setdefault("dislikes", [])
        known = {d.get("want") for d in vis["dislikes"] if isinstance(d, dict)}
        from . import vision as vision_mod
        for name, why, where in rejected:
            text = f"not {name}"
            if text in known:
                continue
            vis["dislikes"].append(vision_mod.want(
                text, strength="strong",
                source=f"turned down on the plant ballot, {today}: {why}",
                applies_to=where))
            known.add(text)
        yards.save(slug, "vision.json", vis)

    for n, s, was, choice in changed:
        if s.get("card"):
            try:
                doubts.settle(slug, s["card"],
                              f"{choice} x{(s.get('pick') or {}).get('count') or s['count'][0]}",
                              by=by)
            except SystemExit:
                pass
    if changed:
        settle_fork(slug, "choose them myself",
                    f"{len(changed)} slots picked on the ballot")
    return data, changed, rejected, contradictory


def count_for(niche, slot, candidate):
    """How many of *this* plant, rather than how many of its size class.

    The slot budget is drawn against a representative spread for the class, but
    a class is a range: a 0.8 ft frogfruit and a 1.5 ft cedar sage are both
    "small", and three of each cover very different amounts of ground. Holding
    the count fixed at the class figure means picking the smaller plant quietly
    produces a sparse bed — which is exactly what happened the first time this
    ran, on two beds at 43 and 35 percent.

    So the count follows the plant. You buy more of a small thing, which is
    what anybody laying out a bed would do without being asked.
    """
    if not slot.get("budget_share") or not candidate.get("mature_spread_ft"):
        return slot["count"][0]
    room = (float(niche["area_sqft"]) * slot["budget_share"]
            * (design.COVER_FLOOR + design.COVER_CEILING) / 2.0)
    each = _footprint(float(candidate["mature_spread_ft"]))
    minimum = next((m for c, lo, hi, m in SIZES if c == slot.get("size")), 3)
    ceiling = int(float(niche["area_sqft"]) * slot["budget_share"]
                  * design.COVER_CEILING // each) or minimum
    return max(minimum, min(ceiling, round(room / each)))


def _substitute(slot, chosen, vetoed, asked_for=None):
    """The stand-in for the day the nursery is out of the first choice.

    It cannot be the chosen plant, and it cannot be something just banned —
    both of which the first version happily recorded, offering a substitute the
    person had rejected on the same page. Otherwise the best-ranked remaining
    candidate, since the ranking is already a judgement about fit.
    """
    barred = set(vetoed) | {chosen}
    if asked_for and asked_for not in barred:
        return asked_for
    for c in slot.get("candidates") or []:
        if c["name"] not in barred:
            return c["name"]
    return None


def log_changes(slug, changed):
    """One changelog entry per decision that moved off a previous one."""
    from . import changelog
    filed = []
    for n, s, was, now in changed:
        if not was or was == now:
            continue
        filed.append(changelog.record(
            slug, f"{n['label']} {s['layer']} row is now {now}",
            kind="change", subject=n["label"], was=was, now=now,
            why=(s["decisions"][-1].get("why")
                 or "changed on the plant ballot"),
            affects=["PLAN.md"]))
    return filed


# --------------------------------------------------------------- the season

def season(slug, slot_id, data=None, today=None):
    """Whether it is too late to change this, and when the next window opens.

    Three conditions, named apart because the remedies are not the same thing:
    a plant already in the ground has to be dug up, a window that has closed
    means waiting, and a plant already bought means money already spent on
    something that can often still be returned or given away. Rolling them into
    one "too late" tells somebody they cannot do something when what they
    actually face is a trip to the nursery.

    It warns. It never refuses. Somebody who wants to dig up a shrub they have
    decided they hate is entitled to, and being told the cost is the help.
    """
    data = data or load(slug)
    n, s = find(data, slot_id)
    if not s:
        return []
    site = yards.load_site(slug)
    today = today or datetime.date.today()
    tasks = _tasks(slug)
    zones = set(n["zones"]) | {n["label"]}
    warn = []

    for t in tasks:
        if not _touches(t, zones, site):
            continue
        kind, done = t.get("kind"), t.get("done")
        when = t.get("date") or (t.get("window") or {}).get("from")
        if kind in ("plant", "sow", "transplant") and done:
            warn.append({
                "what": "already in the ground",
                "say": f"{t['id']} on {when} is marked done — this was planted. "
                       f"Changing it now means digging up what is there.",
                "next": _next_window(site, kind, today),
            })
        elif kind == "buy" and done:
            warn.append({
                "what": "already bought",
                "say": f"{t['id']} on {when} is marked done — the plants for "
                       f"this were bought. Changing the choice does not undo "
                       f"the spend, though most nurseries will take back "
                       f"something unplanted.",
                "next": None,
            })

    closed = _window_closed(site, today)
    if closed:
        warn.append({"what": "window closed this season", "say": closed[0],
                     "next": closed[1]})
    return warn


def _tasks(slug):
    t = yards.load(slug, "tasks.json") or {}
    return t.get("tasks") if isinstance(t, dict) else (t or [])


def _touches(task, zones, site):
    """Does this task happen in this niche's ground?

    `where.bed` is one comma-joined string holding things like "g03, g01, g04"
    as well as bare "raised bed", so it needs splitting rather than matching
    whole. Several tasks carry no `where` at all, and those are reported as
    unmatched rather than silently assumed to be elsewhere — a planting task
    with no bed recorded is exactly the one worth looking at by hand.
    """
    where = task.get("where") or {}
    bed = where.get("bed")
    if not bed:
        return False
    for part in str(bed).split(","):
        part = part.strip()
        if not part:
            continue
        if part in zones:
            return True
        key = design.resolve_site_zone(site, part)
        if key and key in zones:
            return True
    return False


def unmatched_tasks(slug):
    """Dated planting work whose bed is not recorded, so nothing can gate on it."""
    site = yards.load_site(slug)
    out = []
    for t in _tasks(slug):
        if t.get("kind") not in ("plant", "sow", "transplant", "buy"):
            continue
        bed = (t.get("where") or {}).get("bed")
        if not bed:
            out.append((t["id"], t.get("title", ""), "no where.bed recorded"))
            continue
        parts = [p.strip() for p in str(bed).split(",") if p.strip()]
        bad = [p for p in parts if not design.resolve_site_zone(site, p)]
        if len(bad) == len(parts):
            out.append((t["id"], t.get("title", ""),
                        f"where.bed {bed!r} matches no zone"))
    return out


def _frost(site):
    f = ((site.get("climate") or {}).get("frost_32f") or {})
    return ((f.get("first_fall") or {}).get("median"),
            (f.get("last_spring") or {}).get("median"))


SUMMER = ((6, 1), (9, 15))


def _window_closed(site, today):
    """Whether today falls in a stretch when nothing should go in the ground.

    Two of them here, and they are different kinds of claim, so they say which:

      the frost gap  between the median first frost and the median last frost,
                     both from this yard's own 30 years of daily weather. A
                     median, which means half of all years are worse than the
                     date given — worth saying rather than presenting it as a
                     line in the sand.
      the summer     June to mid-September in Central Texas, which is a rule of
                     thumb rather than anything this record measured, and is
                     labelled as such.

    The frost gap wraps across the new year, which is the case the first version
    of this got wrong: it compared a January date against the *coming*
    December and concluded the window was still open, in the middle of the one
    stretch of the year it exists to warn about.
    """
    first_fall, last_spring = _frost(site)
    if first_fall and last_spring:
        fm, fd = first_fall.split()
        sm, sd = last_spring.split()
        year = today.year if today.month >= _MONTH_N[fm] else today.year - 1
        shut = datetime.date(year, _MONTH_N[fm], int(fd))
        opens = datetime.date(year + 1, _MONTH_N[sm], int(sd))
        if shut <= today < opens:
            return (f"the autumn planting window closed around {first_fall}, "
                    f"the median first frost in this yard's own 30-year "
                    f"record. Half of all years are colder than that, so "
                    f"treat it as the middle of a range rather than a "
                    f"deadline.",
                    f"after the median last frost, about {last_spring} "
                    f"{opens.year} — {(opens - today).days} days away")

    (am, ad), (bm, bd) = SUMMER
    if (am, 1) <= (today.month, today.day) <= (bm, bd):
        return ("it is the middle of a Central Texas summer, and a new plant "
                "put in now spends its first months trying not to die rather "
                "than rooting. This one is a rule of thumb, not a figure out "
                "of this yard's weather record.",
                f"autumn planting opens around 1 October, "
                f"{(datetime.date(today.year, 10, 1) - today).days} days away")
    return None


_MONTH_N = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
     "Nov", "Dec"])}


def _next_window(site, kind, today):
    first_fall, last_spring = _frost(site)
    return (f"woody planting here reopens in the autumn, before about "
            f"{first_fall}; anything tender waits until after {last_spring}")


# --------------------------------------------------------------- reopen

def reopen(slug, ident, reason, data=None):
    """Put a slot or a whole niche back in play, and re-gate what it feeds."""
    # Same bargain as a waived doubt: changing your mind is free, and saying
    # why is the price. Six months on, a slot that went back and forth twice
    # with no reasons recorded is indistinguishable from a bug.
    if not (reason or "").strip() or len(reason.strip()) < 12:
        raise SystemExit(
            "--reason is required to reopen a slot, and has to be long enough "
            "for somebody to disagree with. What changed?")
    data = data or load(slug)
    n, s = find(data, ident)
    if not n:
        raise SystemExit(f"{slug} has no niche or slot {ident!r}")
    targets = [s] if s else [x for x in _slots(n) if x.get("pick")]
    if not targets:
        raise SystemExit(f"nothing has been picked for {ident!r} yet, so "
                         f"there is nothing to reopen")
    today = datetime.date.today().isoformat()
    warned = []
    for slot in targets:
        # The season warnings are advisory. A yard with no site.json or no
        # tasks.json yet still gets to change its mind; it just does not get
        # told whether the window is open.
        try:
            warned.append((slot, season(slug, slot["id"], data)))
        except (FileNotFoundError, KeyError):
            warned.append((slot, []))
        gone = (slot.get("pick") or {}).get("name")
        slot.setdefault("decisions", []).append(
            {"on": today, "by": "reopened", "why": reason, "was": gone})
        # Whatever was moved off stops being the recommendation. Somebody who
        # reopens a slot and is immediately handed back the plant they reopened
        # it to get away from will not use this twice. It stays on the ballot,
        # because they may yet decide it was fine — it just no longer gets
        # offered as the answer.
        if gone:
            # The key can exist holding null, from a slot that was written
            # before anything was ever ruled out of it, so setdefault is not
            # enough on its own.
            out = slot.get("ruled_out") or []
            if gone not in out:
                out.append(gone)
            slot["ruled_out"] = out
        slot["pick"] = None
        if slot.get("card"):
            try:
                doubts.reopen(slug, slot["card"], reason)
            except SystemExit:
                pass
    return data, warned


# --------------------------------------------------------------- review

def review(slug, ident=None, data=None):
    """Every slot's pick, its reason, and what was not taken.

    For every slot, decided or deferred. A page somebody opens two years later
    wanting to know why the bed is the way it is should not have to distinguish
    between a decision made carefully and one nobody looked at — it should say
    which, and show the alternatives either way.
    """
    data = data or load(slug)
    L = []
    for n in data.get("niches") or []:
        if ident and ident not in (n["id"], n["label"]):
            continue
        Li = n["light"]
        L.append(f"\n{n['label']}  [{n['id']}]")
        L.append(f"  {Li['hours']} h growing-season sun, {Li['category']}; "
                 f"{n['area_sqft']} sq ft"
                 + (f", {float(n['usable_depth_ft']):.1f} ft deep"
                    if n.get("usable_depth_ft") else ""))
        chosen = (n.get("compositions") or {}).get("chosen")
        if chosen:
            L.append(f"  laid out as {chosen}")
        for s in _slots(n):
            if s.get("excluded"):
                L.append(f"    {s['id']}  -- {s['excluded']}")
                continue
            pick = s.get("pick")
            rec = s.get("recommended") or {}
            if pick:
                how = ("you chose it" if pick["chosen_by"] == "decided"
                       else "recommendation taken; nobody looked at the "
                            "alternatives")
                L.append(f"    {s['id']}  {pick['name']} x{pick['count']}"
                         f"  ({how})")
                if pick.get("substitute"):
                    L.append(f"      if out of stock: {pick['substitute']}")
            else:
                L.append(f"    {s['id']}  nothing picked yet"
                         + (f"; would recommend {rec['name']}"
                            if rec.get("name") else ""))
            # The reason for the plant that is actually going in, not for the
            # one that was recommended. Where somebody overrode the
            # recommendation, printing the recommendation's reasoning under
            # their choice reads as though the system talked them into it.
            shown = (pick or rec).get("name")
            cand = next((c for c in s.get("candidates") or []
                         if c["name"] == shown), None)
            if cand and cand.get("score_why"):
                L.append(f"      why: {cand['score_why']}")
            if pick and rec.get("name") and rec["name"] != pick["name"]:
                L.append(f"      the recommendation was {rec['name']}, "
                         f"not taken")
            others = [c["name"] for c in s.get("candidates") or []
                      if c["name"] != shown]
            if others:
                L.append(f"      not taken: {', '.join(others)}")
            for d in s.get("decisions") or []:
                bit = d.get("pick") or "reopened"
                L.append(f"      {d['on']}  {bit}"
                         + (f" (was {d['was']})" if d.get("was") else "")
                         + f"  -- {d.get('why', '')}")
    return "\n".join(L)


def check(slug, data=None):
    """Stale slates, empty slots, and picks that no longer fit."""
    data = data or load(slug)
    fresh = {n["id"]: signature(n) for n in derive(slug)["niches"]}
    bad = []
    for n in data.get("niches") or []:
        now = fresh.get(n["id"])
        if now and now != n.get("signature"):
            bad.append((n["id"], "the growing conditions moved since these "
                                 "niches were derived — re-derive, and check "
                                 "any slate bound to the old signature"))
        for s in _slots(n):
            if s.get("excluded"):
                continue
            if not s.get("candidates"):
                bad.append((s["id"], "no candidates researched, so there is "
                                     "nothing to offer for it"))
                continue
            if s.get("slate_signature") != n.get("signature"):
                bad.append((s["id"], "the slate was researched against "
                                     "different conditions than this niche "
                                     "now has"))
            if len(s["candidates"]) < 2:
                bad.append((s["id"], f"only one candidate "
                                     f"({s['candidates'][0]['name']}), so "
                                     f"there is nothing here to choose "
                                     f"between. Offering it as a choice wastes "
                                     f"the one thing this stage is asking for, "
                                     f"which is somebody's attention — either "
                                     f"research more, or let it default"))
            if not s.get("recommended"):
                bad.append((s["id"], "candidates but no recommendation: "
                                     "--rank has not run"))
            without = [c["name"] for c in s["candidates"] if not c.get("photos")]
            if without:
                bad.append((s["id"], f"no openly-licensed photograph for "
                                     f"{', '.join(without)} — still offered, "
                                     f"but labelled"))
    for tid, title, why in unmatched_tasks(slug):
        bad.append((tid, f"{why}, so no season warning can be raised for it "
                         f"({title[:40]})"))
    return bad


# --------------------------------------------------------------- export

def export(slug, data=None):
    """Write the picks into design.json as real plants.

    `chosen_by` rides along, so the plan can say how many of these somebody
    actually picked — which is a different and more honest sentence than
    implying they all were.
    """
    data = data or load(slug)
    d = yards.load(slug, "design.json") or {"plants": []}
    by_slot = {p.get("from_slot"): p for p in d.get("plants") or []
               if p.get("from_slot")}
    added, updated, waiting = 0, 0, []
    for n in data.get("niches") or []:
        for s in _slots(n):
            pick = s.get("pick")
            if not pick:
                # Three different situations wanting three different next
                # moves, and reporting them alike is worse than useless: it
                # sent somebody researching candidates for four rows that the
                # beds are too shallow to hold.
                if s.get("excluded"):
                    waiting.append((s["id"], s["excluded"], False))
                elif s.get("candidates"):
                    waiting.append((s["id"], "nobody has chosen yet", True))
                else:
                    waiting.append((s["id"],
                                    "no candidates researched for it yet",
                                    True))
                continue
            cand = next((c for c in s.get("candidates") or []
                         if c["name"] == pick["name"]), None)
            if not cand:
                waiting.append((s["id"], f"{pick['name']} is picked but is no "
                                         f"longer on this slot's slate", True))
                continue
            row = dict(cand)
            for gone in ("fit", "score", "score_why", "photos", "no_photo",
                         "elsewhere"):
                row.pop(gone, None)
            row.update({"count": pick["count"], "zone": n["zones"][0],
                        "layer": s["layer"], "chosen_by": pick["chosen_by"],
                        "from_slot": s["id"]})
            if pick.get("substitute"):
                row["substitute"] = pick["substitute"]
            if s["id"] in by_slot:
                by_slot[s["id"]].update(row)
                updated += 1
            else:
                d.setdefault("plants", []).append(row)
                added += 1
    return d, added, updated, waiting


# --------------------------------------------------------------- reporting

def _wrap(text, width=74, indent=""):
    words, line, out = str(text).split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(indent + line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(indent + line)
    return out


def report(slug, data):
    print(f"\n{slug} — {len(data.get('niches') or [])} niches")
    print(f"  light figure: {data['series']['light']}")
    for line in _wrap(data["series"]["why"], 72, "    "):
        print(line)
    for n in data.get("niches") or []:
        L = n["light"]
        print(f"\n  {n['label']}  [{n['id']}]")
        print(f"    {L['hours']} h {L['category']}, "
              f"{L['winter_hours'] or '?'} h in winter; "
              f"{n['area_sqft']} sq ft"
              + (f", {float(n['usable_depth_ft']):.1f} ft deep"
                 if n.get("usable_depth_ft") else "")
              + f"; {n['kind']}")
        for s in _slots(n):
            if s.get("excluded"):
                print(f"      -- {s['layer']}: {s['excluded']}")
                continue
            lo, hi = s["count"]
            cnt = f"{lo}" if lo == hi else f"{lo}-{hi}"
            got = len(s.get("candidates") or [])
            rec = (s.get("recommended") or {}).get("name")
            pick = (s.get("pick") or {}).get("name")
            print(f"      {s['layer']:9s} {str(s['size']):9s} x{cnt:6s} "
                  f"{got} candidates"
                  + (f"; picked {pick}" if pick else
                     f"; would pick {rec}" if rec else ""))
    if data.get("notes"):
        print("\n  what to know about how these were worked out")
        for note in data["notes"]:
            for line in _wrap(note, 72, "    "):
                print(line)
            print()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--derive", action="store_true")
    ap.add_argument("--capacity", action="store_true")
    ap.add_argument("--compositions", action="store_true")
    ap.add_argument("--compose", nargs=2, metavar=("NICHE", "NAME"),
                    help="record the arrangement chosen for a niche")
    ap.add_argument("--slate", metavar="FILE",
                    help="JSON of {slot_id: [candidate, ...]}")
    ap.add_argument("--rank", action="store_true")
    ap.add_argument("--photos", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="use only cached photos")
    ap.add_argument("--ask", action="store_true", help="file the choice cards")
    ap.add_argument("--recommend-all", action="store_true")
    ap.add_argument("--ballot", action="store_true")
    ap.add_argument("--port", type=int, default=8730)
    ap.add_argument("--sync", metavar="FILE",
                    help="JSON of {slot_id: plant name}")
    ap.add_argument("--review", nargs="?", const=True, metavar="NICHE")
    ap.add_argument("--reopen", metavar="NICHE|SLOT")
    ap.add_argument("--reason")
    ap.add_argument("--season", metavar="SLOT")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    slug = args.slug
    stamp = yards.sandbox_stamp(slug)

    if args.derive:
        data = derive(slug)
        data = capacity(slug, data)
        save(slug, data)
        report(slug, data)
        if stamp:
            print(f"\n  {stamp}")
        print("\n  next: research candidates per slot and record them with "
              "--slate")
        return

    if args.capacity:
        data = capacity(slug)
        save(slug, data)
        report(slug, data)
        return

    if args.compositions:
        data, asked, skipped = compositions(slug)
        save(slug, data)
        for n, why in skipped:
            print(f"  {n['label']}: not asked — {why}")
        for n in asked:
            c = n["compositions"]
            print(f"\n  {n['label']} — {n['area_sqft']} sq ft, "
                  f"three ways to plant it")
            for o in c["options"]:
                mark = " <- recommended" if o["name"] == \
                    c["recommended"]["name"] else ""
                print(f"    {o['name']}{mark}")
                for label, text in (("", o["what"]), ("for", o["pro"]),
                                    ("against", o["con"]),
                                    ("size", o["roughly"])):
                    for line in _wrap(f"{label + ': ' if label else ''}{text}",
                                      66, "        "):
                        print(line)
            for line in _wrap("recommended because "
                              + c["recommended"]["because"], 70, "      "):
                print(line)
        if asked:
            print("\n  record a choice with --compose <niche> <name>")
        return

    if args.compose:
        data = load(slug)
        n, _ = find(data, args.compose[0])
        if not n:
            raise SystemExit(f"no niche {args.compose[0]!r}")
        n.setdefault("compositions", {})["chosen"] = args.compose[1]
        n["composition"] = args.compose[1]
        save(slug, data)
        print(f"  {n['label']} will be planted {args.compose[1]}")
        return

    if args.slate:
        with open(args.slate) as fh:
            incoming = json.load(fh)
        data, kept, refused = slate(slug, incoming)
        save(slug, data)
        print(f"  {kept} candidates recorded")
        for slot_id, name, why in refused:
            print(f"  refused  {slot_id}  {name}")
            for line in _wrap(why, 66, "      "):
                print(line)
        if refused:
            print("\n  Refused here rather than on the ballot on purpose: "
                  "offering something the design linter will later reject is "
                  "worse than not offering it.")
        return

    if args.rank:
        data, n = rank(slug)
        save(slug, data)
        print(f"  ranked {n} slots")
        for niche in data["niches"]:
            for s in _slots(niche):
                r = s.get("recommended")
                if not r:
                    continue
                print(f"\n  {s['id']}  ->  {r['name']}")
                for line in _wrap(r["because"], 68, "      "):
                    print(line)
                if r.get("runner_up"):
                    print(f"      runner-up {r['runner_up']}, which becomes "
                          f"the substitute if the first is out of stock")
        return

    if args.photos:
        data, got, without = photos(slug, offline=args.offline)
        save(slug, data)
        print(f"  {got} openly-licensed photographs cached")
        if without:
            print(f"  no usable photograph for: {', '.join(sorted(set(without)))}")
            print("  Those stay on the ballot, labelled. Dropping them would "
                  "quietly favour whatever happens to be well photographed, "
                  "and giving them somebody else's photograph would be worse.")
        return

    if args.ask:
        data, filed = ask(slug)
        save(slug, data)
        print(f"  filed {len(filed)} cards on the doubt board")
        for c in filed:
            print(f"    {c['id']}  {c['question'][:66]}")
        print("\n  These block design and bom, which is the point: the turn "
              "ends here.")
        print(f"  Serve them:  python3 -m lib.niches {slug} --ballot")
        print(f"  Or take the recommendations:  python3 -m lib.niches {slug} "
              f"--recommend-all")
        return

    if args.recommend_all:
        data, took = recommend_all(slug)
        save(slug, data)
        print(f"  took {len(took)} recommendations. This is what that "
              f"decided:\n")
        for n, s, rec in took:
            print(f"    {n['label']:28s} {s['layer']:8s} "
                  f"{rec['name']} x{s['count'][0]}")
        print("\n  Recorded as `deferred`, not `decided`, so it stays "
              "answerable later which of these anybody actually looked at.")
        print(f"  Every option is still on file: python3 -m lib.niches {slug} "
              f"--review")
        return

    if args.ballot:
        srv, url, state = serve(slug, port=args.port)
        print(f"  open this on a phone on the same wifi:\n\n    {url}\n")
        print("  Ctrl-C when you are done, then --sync the file it writes.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
        if state["picks"]:
            path = os.path.join(yards.yard_dir(slug), "ballot-picks.json")
            with open(path, "w") as fh:
                json.dump(state["picks"], fh, indent=1)
            print(f"\n  saved {path}")
            print(f"  python3 -m lib.niches {slug} --sync {path}")
        else:
            print("\n  nothing was submitted, so nothing changed")
        return

    if args.sync:
        with open(args.sync) as fh:
            picks = json.load(fh)
        data, changed, rejected, clash = sync(slug, picks)
        save(slug, data)
        entries = log_changes(slug, changed)
        print(f"  {len(changed)} picks recorded")
        for n, s, was, now in changed:
            print(f"    {s['id']:24s} {now}"
                  + (f"  (was {was})" if was else ""))
        for name, why, where in clash:
            print(f"\n  not banning {name}: it was also picked for another "
                  f"bed on the same page. A dislike is permanent and "
                  f"check_vision enforces it everywhere, so it cannot be "
                  f"written against something the garden contains. Reopen "
                  f"the other slot first if you meant it.")
        if rejected:
            print(f"\n  {len(rejected)} rejections written to vision.dislikes, "
                  f"where check_vision enforces them from now on:")
            for name, why, where in rejected:
                print(f"    not {name} — {why}")
        if entries:
            print(f"\n  {len(entries)} changelog entries: "
                  f"{', '.join(e['id'] for e in entries)}")
        return

    if args.review:
        print(review(slug, None if args.review is True else args.review))
        return

    if args.season:
        for w in season(slug, args.season):
            print(f"  {w['what']}")
            for line in _wrap(w["say"], 68, "      "):
                print(line)
            if w.get("next"):
                for line in _wrap("next window: " + w["next"], 68, "      "):
                    print(line)
        return

    if args.reopen:
        if not args.reason:
            raise SystemExit(
                "--reopen needs --reason. In six months the question is not "
                "what it says, it is why it changed")
        data, warned = reopen(slug, args.reopen, args.reason)
        save(slug, data)
        for slot, warns in warned:
            print(f"  reopened {slot['id']}")
            for w in warns:
                print(f"    warning — {w['what']}")
                for line in _wrap(w["say"], 66, "        "):
                    print(line)
                if w.get("next"):
                    for line in _wrap("next window: " + w["next"], 66,
                                      "        "):
                        print(line)
        print("\n  design, drawbeds, bom and schedule are gated again until "
              "this is settled.")
        return

    if args.export:
        d, added, updated, waiting = export(slug)
        yards.save(slug, "design.json", d)
        # Count only what this export is answerable for. Tallying every plant
        # in design.json overstates it the moment a slot is reopened, and an
        # overstated count is the kind nobody checks twice.
        mine = [p for p in d["plants"] if p.get("from_slot")]
        picked = sum(1 for p in mine if p.get("chosen_by") == "decided")
        deferred = sum(1 for p in mine if p.get("chosen_by") == "deferred")
        print(f"  {added} plants added, {updated} updated in design.json")
        print(f"  {picked} of the {len(mine)} from slots a person chose; "
              f"{deferred} taken as recommended without looking")
        pending = [w for w in waiting if w[2]]
        settled = [w for w in waiting if not w[2]]
        if pending:
            print(f"\n  {len(pending)} slot{'s' if len(pending) > 1 else ''} "
                  f"still waiting on somebody:")
            for sid, why, _ in pending:
                print(f"    {sid:<24} {why}")
            print("\n  design will report those beds as sparse, correctly — "
                  "the ground really is empty.")
        if settled:
            # Not pending, and saying so matters: reported alongside the real
            # ones, these sent somebody researching plants for rows that do
            # not exist.
            print(f"\n  {len(settled)} row{'s' if len(settled) > 1 else ''} "
                  f"the bed cannot hold, so nothing is owed for "
                  f"{'them' if len(settled) > 1 else 'it'}:")
            for sid, why, _ in settled:
                print(f"    {sid:<24} {why}")
        print(f"\n  now run:  python3 -m lib.design {slug}")
        return

    if args.check:
        bad = check(slug)
        if not bad:
            print("  every slot has a slate, a recommendation and photographs, "
                  "and every slate matches the conditions it was researched "
                  "for")
            return
        for what, why in bad:
            print(f"  {what}")
            for line in _wrap(why, 68, "      "):
                print(line)
        return

    data = load(slug)
    if not data:
        raise SystemExit(f"{slug} has no niches yet:\n"
                         f"  python3 -m lib.niches {slug} --derive")
    report(slug, data)


if __name__ == "__main__":
    main()
