#!/usr/bin/env python3
"""What is missing, ranked by how much it changes the answer.

    python3 -m lib.gaps <slug>              the ranked list
    python3 -m lib.gaps <slug> --quick      skip the sun-model probes
    python3 -m lib.gaps <slug> --json       write coverage.json only

A list of unknowns is useless; every yard has hundreds. What is worth having is
an ordering, and an ordering needs each gap priced in a unit that means
something. So each is measured in its own:

    hours of light   a geometry gap is priced by actually re-running the shade
                     model across the plausible range of the unknown and
                     reporting the spread in the answer. Not a guess about
                     importance — a measurement of it
    dollars          a conditions gap is priced by what getting it wrong costs,
                     in plants that die or materials bought twice
    decisions        a vision gap is priced by naming which design decisions
                     cannot be made until it is answered

Those three do not share a unit, and pretending otherwise would be the exact
kind of false precision this system exists to avoid. So they are reported in
their own units and ordered by a stated exchange rate, written down here where
it can be argued with:

    one hour a day of light  ~  $250  ~  4 blocked decisions

That is a judgement, not a fact. It says an hour a day of growing-season light
is worth about what a decent shrub costs to replace twice, which is roughly how
it feels standing in a yard. Change `WEIGHTS` if it feels wrong.
"""
import argparse
import copy
import json
import sys

import numpy as np

from . import (conditions, doubts, inputs, siteschema, solar,
               sunmodel, yards)

# the stated exchange rate: how much one unit of each is worth, on one scale
WEIGHTS = {"hours_per_day": 10.0, "usd": 0.04, "decisions": 2.5}

PROBE_CELL = 12.0                       # coarse grid; this is a sensitivity, not a map

# Three months sampled across the growing season, NOT the growing season. The
# comment here used to call it "the growing season", which is a sample being
# passed off as a window, and the two are 0.28 h apart on cloverleaf-austin -
# enough to move a bed across a `LIGHT_NEED` boundary if anybody ever quoted
# this figure as a bed's light.
#
# Nobody should. Everything this module publishes from it is a DIFFERENCE: the
# spread between the brightest and darkest plausible value of an unknown, which
# is what prices a gap. A constant bias cancels out of a spread and does not
# cancel out of a level, so the sample is honest for what it is used for and
# wrong for what its old comment implied. `solar.GROWING_SEASON` is the window;
# this is a sample of it, and `solar.SEASON_SAMPLE` is where that is written
# down.
PROBE_MONTHS = solar.SEASON_SAMPLE


# ------------------------------------------------------------------ the probe

def _mean_hours(site, cell=PROBE_CELL, months=PROBE_MONTHS, zone=None):
    m = sunmodel.Model(site, cell=cell)
    mask = m.zones.get(zone) if zone else None
    if mask is not None and not mask.any():
        mask = None
    vals = []
    for mon in months:
        eff = m.day(solar.MONTH_DOY[mon])[0]
        vals.append(float(eff[mask].mean() if mask is not None else eff.mean()))
    return float(np.mean(vals))


def light_spread(site, mutate, values, cell=PROBE_CELL, zone=None):
    """Re-run the shade model across a range of an unknown, and report the spread.

    This is the whole idea. Rather than asserting that crown spread matters, it
    sets the crown to each plausible value in turn and measures how far the
    yard's light moves. A gap that changes nothing sinks to the bottom of the
    list on its own.

    `zone` scopes the measurement. A tree that shades the whole yard should be
    judged on the whole yard, but an awning over one four-foot bed would average
    away to nothing there while completely governing the bed underneath it. The
    honest number is the one for the ground the thing actually rules.
    """
    out = []
    for v in values:
        s = copy.deepcopy(site)
        try:
            mutate(s, v)
            out.append((v, _mean_hours(s, cell=cell, zone=zone)))
        except Exception:
            continue
    if len(out) < 2:
        return None
    hrs = [h for _, h in out]
    return {"tried": [[v, round(h, 2)] for v, h in out],
            "low": round(min(hrs), 2), "high": round(max(hrs), 2),
            "spread_hours": round(max(hrs) - min(hrs), 2),
            "measured_over": zone or "the whole yard"}


def _zone_under(site, ov):
    """The named zone an overhead plane covers most of, by label.

    Returned as the label the sun model keys its masks by, so it can be handed
    straight to `light_spread`.
    """
    ox0, ox1 = float(min(ov["x"])), float(max(ov["x"]))
    oy0, oy1 = float(min(ov["y"])), float(max(ov["y"]))
    best, best_area = None, 0.0
    for key, spec in (site.get("zones") or {}).items():
        if not spec.get("x") or not spec.get("y"):
            continue
        zx0, zx1 = float(min(spec["x"])), float(max(spec["x"]))
        zy0, zy1 = float(min(spec["y"])), float(max(spec["y"]))
        area = (max(0.0, min(ox1, zx1) - max(ox0, zx0)) *
                max(0.0, min(oy1, zy1) - max(oy0, zy0)))
        if area > best_area:
            best_area = area
            best = spec.get("label_short") or spec.get("label") or key
    return best


def _set_all_trees(field):
    def mutate(site, value):
        for t in site.get("features", {}).get("trees", []):
            t[field] = value
    return mutate


def _set_path(path):
    def mutate(site, value):
        siteschema.set_path(site, path, value)
    return mutate


# ------------------------------------------------------------- geometry gaps

def site_gaps(site, quick=False):
    gaps = []
    prov = site.get("provenance", {})

    def source_of(path):
        """Provenance for a field, falling back to whatever covers it.

        A survey stamps `features.trees` once for all fourteen trees it found.
        Without the fallback every one of those trees reads as unmeasured and
        buries the real gaps under a list of things lidar already answered.
        """
        parts = path.split(".")
        for n in range(len(parts), 0, -1):
            hit = prov.get(".".join(parts[:n]))
            if hit:
                return hit.get("source")
        return None

    trees = siteschema.trees(site)

    # crown spread, usually the single largest unknown in a yard with trees
    if trees:
        soft = [i for i in range(len(trees))
                if source_of(f"features.trees.{i}.crown_radius") in
                (None, "assumed", "reported")]
        if soft:
            current = trees[soft[0]].get("crown_radius")
            values = [60.0, 120.0, 180.0, 240.0]          # 10 to 40 ft spread
            probe = None if quick else light_spread(
                site, _set_all_trees("crown_radius"), values)
            gaps.append(_gap(
                key="site.tree_crown_radius",
                section="site",
                label=f"crown spread of {len(soft)} tree"
                      f"{'s' if len(soft) > 1 else ''}",
                state="assumed",
                unit="hours_per_day",
                amount=(probe or {}).get("spread_hours"),
                detail=(f"modelled at {current:.0f} in "
                        f"({current / 6:.0f} ft across)" if current else "unset"),
                how=("Lidar answers this outright where the survey is recent "
                     "enough: `python3 -m lib.lidar <slug> --write`. Where it is "
                     "not, stand back far enough to see the whole crown and "
                     "estimate its width against the house, or pace out the "
                     "shadow at noon"),
                effort="minutes, if the lidar survey postdates the tree",
                probe=probe))

        soft = [i for i in range(len(trees))
                if source_of(f"features.trees.{i}.crown_base_height") in
                (None, "assumed")]
        if soft:
            values = [48.0, 144.0, 240.0, 336.0]         # 4 to 28 ft
            probe = None if quick else light_spread(
                site, _set_all_trees("crown_base_height"), values)
            gaps.append(_gap(
                key="site.crown_base_height",
                section="site",
                label="height the leafy crown starts",
                state="assumed",
                unit="hours_per_day",
                amount=(probe or {}).get("spread_hours"),
                detail="light passes under a high crown through the bare trunks, "
                       "which is why this is not a detail",
                how="Lidar, or sight up the trunk and mark where the lowest live "
                    "branch is against something of known height",
                effort="minutes",
                probe=probe))

        for i, t in enumerate(trees):
            if source_of(f"features.trees.{i}.height") in (None, "assumed"):
                gaps.append(_gap(
                    key=f"site.tree_height.{i}", section="site",
                    label=f"height of {t.get('id') or f'tree {i + 1}'}",
                    state="assumed", unit="hours_per_day", amount=None,
                    detail="reported rather than measured",
                    how="Lidar, or a phone clinometer against a known distance",
                    effort="minutes"))
            if not t.get("species") or source_of(
                    f"features.trees.{i}.species") == "assumed":
                gaps.append(_gap(
                    key=f"site.tree_species.{i}", section="site",
                    label=f"species of {t.get('id') or f'tree {i + 1}'}",
                    state="missing", unit="decisions", amount=2,
                    detail="species decides root aggression, leaf-out and "
                           "leaf-drop dates, and whether a planter next to it "
                           "can survive",
                    how="Photograph a leaf, the bark and a twig with buds, and "
                        "identify, or ask the extension office",
                    effort="one photo"))

    # the obstruction model
    obs = site.get("obstructions", {})
    ho = obs.get("house")
    if ho and source_of("obstructions.house.eave_height") in (None, "reported",
                                                              "assumed"):
        values = [ho["eave_height"] - 36, ho["eave_height"],
                  ho["eave_height"] + 36]
        probe = None if quick else light_spread(
            site, _set_path("obstructions.house.eave_height"), values)
        gaps.append(_gap(
            key="site.eave_height", section="site",
            label="house eave height",
            state="reported", unit="hours_per_day",
            amount=(probe or {}).get("spread_hours"),
            detail=f"modelled at {ho['eave_height'] / 12:.0f} ft, plus or minus "
                   f"3 ft either way",
            how="One photo of the wall with a door or window of known size in "
                "frame, through the photo-surveyor subagent",
            effort="one photo",
            probe=probe))
    # Overhead planes. An awning over a four-foot bed is not a detail: it is a
    # seasonal switch, off in winter when the sun slides under it and full on in
    # summer when the sun is overhead. Getting its projection wrong by two feet
    # moves the answer more than any tree in the yard.
    for i, ov in enumerate(obs.get("overheads", []) or []):
        under = _zone_under(site, ov)
        for field, label, deltas, how in [
            ("y", "projection", (-24.0, 0.0, 24.0),
             "Measure from the wall to the awning's outer edge with a tape, or "
             "one photo of the end elevation with a door in frame through the "
             "photo-surveyor subagent"),
            ("height", "height above grade", (-18.0, 0.0, 18.0),
             "Tape from the ground to the awning's underside at the wall")]:
            if source_of(f"obstructions.overheads.{i}.{field}") not in (
                    None, "assumed", "reported"):
                continue
            if field == "y":
                y0, y1 = float(min(ov["y"])), float(max(ov["y"]))
                values = [[y0, y1 + dz] for dz in deltas]
                cur = f"{(y1 - y0) / 12:.1f} ft out from the wall"
            else:
                values = [float(ov["height"]) + dz for dz in deltas]
                cur = f"{float(ov['height']) / 12:.1f} ft up"
            probe = None if quick else light_spread(
                site, _set_path(f"obstructions.overheads.{i}.{field}"), values,
                zone=under)
            gaps.append(_gap(
                key=f"site.overhead_{field}.{i}", section="site",
                label=f"{ov.get('label') or ov.get('id', 'overhead')}: {label}",
                state=source_of(f"obstructions.overheads.{i}.{field}") or "assumed",
                unit="hours_per_day", amount=(probe or {}).get("spread_hours"),
                detail=f"modelled at {cur}, and never measured",
                how=how, effort="one tape measure", probe=probe))

    if not obs:
        gaps.append(_gap(
            key="site.obstructions", section="site",
            label="nothing casting shade is recorded",
            state="missing", unit="hours_per_day", amount=None,
            detail="the sun model will report open sky, which is almost never "
                   "true",
            how="Record the house, fences and neighbouring buildings",
            effort="an hour"))

    # Bed dimensions. Not a shade question, which is why this engine used to miss
    # them entirely: a bed's size decides how many plants fit and how much soil,
    # compost and mulch it takes, so an unmeasured bed prices the whole bill of
    # materials wrong in both directions at once. Ordering by area means the
    # 40-square-foot unknown outranks the 4-square-foot one.
    for key, spec in sorted((site.get("zones") or {}).items()):
        if spec.get("style") == "lawn" or not spec.get("x") or not spec.get("y"):
            continue
        soft = [ax for ax in ("x", "y")
                if source_of(f"zones.{key}.{ax}") in (None, "assumed", "reported")]
        if not soft:
            continue
        name = spec.get("label_short") or spec.get("label") or key
        wx = abs(float(spec["x"][1]) - float(spec["x"][0]))
        wy = abs(float(spec["y"][1]) - float(spec["y"][0]))
        sqft = wx * wy / 144.0
        placement = spec.get("placement")
        both = len(soft) == 2
        gaps.append(_gap(
            key=f"site.zone_dims.{key}", section="site",
            label=(f"where {name} actually is" if placement == "assumed"
                   else f"{'size' if both else 'depth'} of {name}"),
            state=source_of(f"zones.{key}.{soft[0]}") or "assumed",
            unit="usd",
            # A bed's cost scales with its area: soil, compost, mulch, edging and
            # the plants themselves. Roughly $9 a square foot of new bed is a
            # defensible planning figure, and getting the size wrong risks a
            # fraction of it either way.
            amount=round(sqft * 9.0 * (0.5 if both else 0.3)),
            detail=(f"modelled at {wx:.0f} x {wy:.0f} in ({sqft:.0f} sq ft) "
                    + ("with a position that was invented outright"
                       if placement == "assumed"
                       else f"on {'no measurement at all' if both else 'a reported depth'}")),
            how=("Tape it: the long dimension, and the depth from the wall or "
                 "edge at three points, because beds are rarely parallel"),
            effort="five minutes"))

    if not site.get("frame", {}).get("anchor"):
        gaps.append(_gap(
            key="site.frame_anchor", section="site",
            label="the yard is not registered to the world",
            state="missing", unit="decisions", amount=3,
            detail="without it, neighbouring buildings cannot be placed and "
                   "lidar cannot be queried",
            how="Record the lon/lat of the yard's origin corner",
            effort="minutes"))
    if not site.get("address", {}).get("timezone"):
        gaps.append(_gap(
            key="site.timezone", section="site", label="time zone",
            state="missing", unit="decisions", amount=1,
            detail="clock times are being guessed from longitude, which is an "
                   "hour wrong in places like Austin",
            how="Set address.timezone to the IANA name", effort="seconds"))

    errs, warns = siteschema.validate(site)
    for e in errs:
        gaps.append(_gap(key="site.invalid", section="site", label=e,
                         state="missing", unit="decisions", amount=5,
                         detail="the shade model cannot run without this",
                         how="Fill it in", effort="varies"))
    return gaps


# ------------------------------------------------------------ condition gaps

CONDITION_GAPS = [
    ("soil.texture", "soil texture", 400,
     "Planting into unknown soil is how a whole bed dies in its second summer. "
     "Clay that was treated as loam drowns roots; sand that was treated as loam "
     "starves them",
     "Jar test: `python3 -m lib.soil --jar <sand> <silt> <clay>`", "a jar and a day"),
    ("soil.drainage", "drainage rate", 600,
     "The single most common cause of dead shrubs. A slow-draining hole kills "
     "everything planted in it, one plant at a time, over two years",
     "Percolation test: `python3 -m lib.soil --perc <inches> <minutes>`",
     "a hole, two fills, an hour"),
    ("soil.compaction", "compaction", 250,
     "Decides whether beds can be planted into or have to be built on top of, "
     "which is a difference of several hundred dollars of imported soil",
     "Push a screwdriver into moist soil: `python3 -m lib.soil --probe <inches>`",
     "two minutes"),
    ("soil.ph", "pH", 200,
     "Only matters if the design has acid-lovers or a first-time vegetable bed "
     "in it. If it does, it matters completely",
     "Strips, or a $15-30 extension lab test if the design turns on it",
     "minutes, or two weeks for a lab"),
    ("materials.on_hand", "what is already on site", 300,
     "Every unrecorded bag of compost is a bag bought twice, and every "
     "unrecorded pot is a pot bought twice",
     "Walk the garage and the side return and write down quantities",
     "twenty minutes"),
    ("tools.owned", "what tools exist", 150,
     "Decides whether a task is free, a rental, or a purchase, and which "
     "weekend it belongs in",
     "List what is owned, borrowable and rentable nearby", "ten minutes"),
    ("person.experience", "experience and what has been done before", 350,
     "The schedule is gated on this. Tasks beyond the level need the how-to "
     "written in, or hiring out, and getting it wrong stalls a whole weekend",
     "Ask", "two minutes"),
    ("person.hours_per_week", "hours a week available", 0,
     "Without it the schedule is a list, not a plan, and cannot be back-planned "
     "from a date",
     "Ask, honestly", "one minute"),
    ("budget.ceiling_usd", "budget ceiling", 0,
     "Without it there is no cut list, and a design that cannot be afforded is "
     "not a design",
     "Ask, along with whether it is a lump sum or monthly", "one minute"),
    ("water.hose_reach_ft", "whether water reaches", 500,
     "A bed a hose cannot reach is a bed that will not get watered in August, "
     "whatever anyone intends in March",
     "Walk the hose out and see where it stops", "five minutes"),
]


def condition_gaps(cond):
    if cond is None:
        return [_gap(key="conditions.missing", section="conditions",
                     label="no conditions.json at all",
                     state="missing", unit="usd", amount=1500,
                     detail="no soil, no inventory, no budget, no hours. Every "
                            "schedule and every shopping list downstream is "
                            "guesswork until this exists",
                     how="Run the yard-conditions skill",
                     effort="one conversation and a couple of tests")]
    gaps = []
    summary = conditions.soil_summary(cond)
    have = {
        "soil.texture": summary["texture"] is not None
        and "USDA" not in " ".join(summary["basis"]),
        "soil.drainage": any("percolation" in b for b in summary["basis"]),
        "soil.compaction": summary["compaction"] is not None,
        "soil.ph": summary["ph"] is not None,
        "materials.on_hand": bool((cond.get("materials") or {}).get("on_hand")),
        "tools.owned": bool((cond.get("tools") or {}).get("owned")),
        "person.experience": bool((cond.get("person") or {}).get("experience")),
        "person.hours_per_week": (cond.get("person") or {}).get("hours_per_week")
        is not None,
        "budget.ceiling_usd": (cond.get("budget") or {}).get("ceiling_usd")
        is not None,
        "water.hose_reach_ft": (cond.get("water") or {}).get("hose_reach_ft")
        is not None,
    }
    for key, label, usd, why, how, effort in CONDITION_GAPS:
        if have.get(key):
            continue
        unit = "usd" if usd else "decisions"
        gaps.append(_gap(key=f"conditions.{key}", section="conditions",
                         label=label, state="missing", unit=unit,
                         amount=usd if usd else 4, detail=why, how=how,
                         effort=effort))

    for row in conditions.staleness(cond):
        if row["state"] == "stale":
            gaps.append(_gap(
                key=f"conditions.stale.{row['section']}", section="conditions",
                label=f"{row['section']} last confirmed {row['age_days']} days ago",
                state="stale", unit="usd",
                amount=200 if row["section"] == "materials" else 80,
                detail=f"the window for this is {row['window_months']} months. "
                       f"Compost gets used and beds get weedy",
                how="Re-confirm rather than trusting it", effort="a question"))
    return gaps


# --------------------------------------------------------------- vision gaps

VISION_GAPS = [
    ("purpose", "what the yard is for", 4,
     "Everything downstream. A yard for growing food, a yard for sitting in and "
     "a yard for children to run in share almost no decisions"),
    ("style", "the look they are after", 3,
     "Plant palette, hardscape material, bed shape, edging"),
    ("maintenance_appetite", "how much upkeep they actually want", 4,
     "Whether the planting can be seasonal or has to be self-sufficient, and "
     "whether a lawn is on the table at all"),
    ("must_keep", "what stays", 2,
     "Every layout decision has to work around these"),
    ("dislikes", "what they do not want", 2,
     "Cheaper to learn now than after it is planted"),
    ("target_date", "the date it has to be right by", 5,
     "Without it nothing can be back-planned, bloom windows cannot be aimed, "
     "and seed-start dates cannot be counted backwards"),
]


def doubt_gaps(slug):
    """Open doubts, as gaps, so there is one ranked list rather than two.

    A doubt and a gap are the same kind of object seen from different sides: a
    gap is something the record never knew, a doubt is something the record
    claims and nobody believes. Both are priced in the same units and both change
    what happens next, so a board kept separate from the gap report just means
    two lists to read and one of them getting skipped.
    """
    out = []
    for c in doubts.open_cards(slug):
        priced = c.get("priced") or {}
        # A card may be priced in more than one unit. The ordering is driven by
        # whichever dominates, and the rest is said in the detail rather than
        # summed into a single fake number.
        if priced:
            unit = max(priced, key=lambda u: float(priced[u]) *
                       WEIGHTS.get(u, 1.0))
            amount = float(priced[unit])
        else:
            unit, amount = "decisions", None

        detail = c.get("detail") or "raised while working, and not yet settled"
        if c.get("kind") == "choice" and c.get("options"):
            detail += ". Options: " + "; ".join(
                o["name"] + (f" ({o['cost']})" if o.get("cost") else "")
                for o in c["options"])
        blocks = ", ".join(c.get("blocks") or []) or "nothing"

        out.append(_gap(
            key=f"doubt.{c['id']}", section="doubt",
            label=c["question"],
            state="in question", unit=unit, amount=amount,
            detail=f"{detail}. Blocks {blocks}",
            how=(c.get("how_to_settle")
                 or f"python3 -m lib.doubts {slug} --settle {c['id']} "
                    f"--answer \"...\""),
            effort=c.get("effort") or "unknown",
            probe=(c.get("probe") or {}).get("measured")))
    return out


def vision_gaps(vision):
    if not vision:
        return [_gap(key="vision.missing", section="vision",
                     label="no vision.json at all",
                     state="missing", unit="decisions", amount=8,
                     detail="the design has nothing to aim at, so it would be "
                            "the assistant's taste rather than theirs",
                     how="Run the yard-vision skill", effort="one conversation")]
    return [_gap(key=f"vision.{key}", section="vision", label=label,
                 state="missing", unit="decisions", amount=n, detail=why,
                 how="Ask, or read it out of the images they have collected",
                 effort="minutes")
            for key, label, n, why in VISION_GAPS if not vision.get(key)]


# ------------------------------------------------------------------ assembly

def _gap(key, section, label, state, unit, amount, detail, how, effort,
         probe=None):
    return {"key": key, "section": section, "label": label, "state": state,
            "unit": unit, "amount": amount, "detail": detail,
            "how_to_close": how, "effort": effort, "probe": probe}


def score(gap):
    """One number for ordering, from a stated and arguable exchange rate."""
    amount = gap.get("amount")
    if amount is None:
        # a gap whose consequence could not be measured is not therefore
        # unimportant; it sits mid-list rather than at the bottom
        return 12.0
    return float(amount) * WEIGHTS.get(gap["unit"], 1.0)


def native(gap):
    a = gap.get("amount")
    if a is None:
        return "not measured"
    if gap["unit"] == "hours_per_day":
        return f"{a:.1f} h/day of light"
    if gap["unit"] == "usd":
        return f"about ${a:,.0f} at risk"
    return f"{int(a)} decision{'s' if a != 1 else ''} blocked"


def audit(slug, quick=False):
    site = yards.load(slug, "site.json")
    cond = yards.load(slug, "conditions.json")
    vision = yards.load(slug, "vision.json")

    gaps = []
    if site is None:
        gaps.append(_gap(key="site.missing", section="site",
                         label="no site.json at all",
                         state="missing", unit="decisions", amount=10,
                         detail="no geometry, so no shade model, no drawings and "
                                "no design",
                         how="Run the yard-survey skill", effort="an afternoon"))
    else:
        gaps.extend(site_gaps(site, quick=quick))
    gaps.extend(condition_gaps(cond))
    gaps.extend(vision_gaps(vision))
    gaps.extend(doubt_gaps(slug))
    gaps.sort(key=score, reverse=True)

    known = {}
    if site:
        # Read twice is a different and stronger fact than measured, so it is
        # counted separately rather than folded into measured_fraction, which
        # cannot tell the two apart.
        twice = siteschema.confirmed_paths(site)
        known["site"] = {
            "measured_fraction": round(siteschema.measured_fraction(site), 3),
            "provenance_entries": len(site.get("provenance", {})),
            "trees": len(siteschema.trees(site)),
            "zones": len(site.get("zones") or {}),
            "read_more_than_once": len(twice),
            "reproduced": sum(1 for _, c in twice if c["reproduced"]),
            "corrected_on_re_read": sum(1 for _, c in twice
                                        if c["reproduced"] is False),
            "confirmed_paths": {p: c for p, c in twice},
        }
    if cond:
        known["conditions"] = conditions.soil_summary(cond)
    board = doubts.open_cards(slug)
    if board:
        known["doubts"] = {
            "open": len(board),
            "blocking": sorted({b for c in board for b in (c.get("blocks") or [])}),
            "unpriced": sum(1 for c in board if not c.get("priced")),
        }
    coverage = {
        "yard": slug,
        "have": {"site.json": site is not None,
                 "conditions.json": cond is not None,
                 "vision.json": vision is not None,
                 "sun-hours.json": yards.load(slug, "sun-hours.json") is not None,
                 "design.json": yards.load(slug, "design.json") is not None,
                 "doubts.json": yards.load(slug, "doubts.json") is not None},
        "known": known,
        "exchange_rate": WEIGHTS,
        "gaps": gaps,
    }
    # See `inputs.ARTIFACTS` for why the ranked gap report is stamped against
    # the shade model's declared input set rather than one of its own.
    if site is not None:
        coverage["inputs"] = inputs.stamp(
            site, inputs.ARTIFACTS["coverage.json"])
    yards.save(slug, "coverage.json", coverage)
    return coverage


def report(coverage, limit=12):
    slug = coverage["yard"]
    have = coverage["have"]
    print(f"{slug} — what is known and what is missing\n")
    print("  " + "  ".join(f"{k.split('.')[0]}:{'yes' if v else 'no'}"
                           for k, v in have.items()))
    site = (coverage.get("known") or {}).get("site")
    if site:
        print(f"  {site['measured_fraction'] * 100:.0f}% of recorded site values "
              f"were measured rather than assumed")
        if site.get("read_more_than_once"):
            print(f"  {site['read_more_than_once']} of them read a second time: "
                  f"{site['reproduced']} reproduced, "
                  f"{site['corrected_on_re_read']} corrected")
    soil = (coverage.get("known") or {}).get("conditions")
    if soil:
        print(f"  soil confidence: {soil['confidence']}"
              + (f" ({', '.join(soil['basis'])})" if soil["basis"] else ""))
    board = (coverage.get("known") or {}).get("doubts")
    if board:
        print(f"  {board['open']} open doubt"
              f"{'s' if board['open'] > 1 else ''}, blocking "
              f"{', '.join(board['blocking']) or 'nothing'}"
              + (f" ({board['unpriced']} unpriced — "
                 f"`python3 -m lib.doubts {slug} --price`)"
                 if board["unpriced"] else ""))

    gaps = coverage["gaps"]
    if not gaps:
        print("\n  Nothing outstanding. That is unusual; check the record is real.")
        return
    print(f"\n  {len(gaps)} gaps, worst first. Consequence is in each gap's own "
          f"units:\n")
    for i, g in enumerate(gaps[:limit], 1):
        print(f"  {i}. {g['label']}   [{g['section']}]")
        print(f"     costs      {native(g)}")
        if g.get("probe"):
            p = g["probe"]
            over = p.get("measured_over") or "the whole yard"
            print(f"     measured   over {over}, the model runs from "
                  f"{p['low']:.1f} to {p['high']:.1f} h/day across the "
                  f"plausible range")
        print(f"     why        {g['detail']}")
        print(f"     to close   {g['how_to_close']}  ({g['effort']})")
        print()
    if len(gaps) > limit:
        print(f"  ...and {len(gaps) - limit} more in coverage.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--quick", action="store_true",
                    help="skip the sun-model probes, which take a few seconds each")
    ap.add_argument("--json", action="store_true", help="write coverage.json only")
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    cov = audit(args.slug, quick=args.quick)
    if args.json:
        print(yards.path(args.slug, "coverage.json"))
        return
    report(cov, limit=args.limit)


if __name__ == "__main__":
    main()
