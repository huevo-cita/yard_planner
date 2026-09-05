#!/usr/bin/env python3
"""Back-planning a build from the date it has to be right by.

    python3 -m lib.schedule <slug>
    python3 -m lib.schedule <slug> --target 2027-04-15
    python3 -m lib.schedule <slug> --seed-start "tomato,pepper,zinnia"
    python3 -m lib.schedule <slug> --harvest-by 2027-06-01 --crop "bush bean"

Counts backwards from the target date in weekends, checks the plan against the
hours the person actually has, and refuses to put heavy work in a week the record
says is unavailable.

What `build()` does and does not do
-----------------------------------
`build()` places archetype tasks into weekends and nothing else. In particular it
does **no frost arithmetic**: `frost_dates()` is called after the plan is already
assembled, only to print alongside it, and the two functions below that do the
real counting are reachable from the command line and from `raised-bed-rotation`,
never from `build()`. So a plan from this module is fitted to the hours and to the
calendar, and is not checked against a planting window. Read the dates as "this
much work fits before that date", not as "this is when to plant".

The deadline arithmetic, which lives here but runs on its own
-------------------------------------------------------------
    seed start      tomatoes and peppers want 6-8 weeks indoors before the last
                    frost; brassicas 5-6; cucurbits 3-4 and they resent being
                    started earlier. Counting backwards from the frost date is
                    what turns "start seeds in spring" into a dated task
    days to matu-   a harvest date minus days to maturity gives a sow-by date,
    rity            plus a fortnight because catalogue figures assume ideal
                    conditions and nobody has those

A third kind is named in the design skill and is not implemented here: a bloom
window, where the date the yard has to look right decides which plants can
possibly be in flower. That constraint travels backwards into the plant list
rather than into this schedule.

Three things a date can mean, and why they are separate
-------------------------------------------------------
    display         the garden has to LOOK right on this day. Work may run past
    milestone       it, and the project does not end there
    blackout        no work happens in this period at all. Read from
                    `constraints.blackouts` alongside `person.travel_gaps`
    project end     when the work stops, if it ever does. Usually it does not

`vision.target_date` is the first of these. Back-planning up to a display date as
though it were the last day work is allowed is what packs a planting into the
three weeks before a party, and it is the reason those three are kept apart.

Why weekends
------------
Most people do this work on weekends and the honest planning unit is therefore a
weekend, not a week. A schedule in weeks quietly assumes Wednesday evenings
exist, and they do not.

Establishment watering is included because it is the task that actually kills
plantings. It decays: daily for the first week, every other day for two to three
weeks, then twice weekly, then weekly through the first summer. That is a real
commitment and it belongs in the schedule where it can be seen, not in a footnote.
"""
import argparse
import datetime
import json
import re

from . import conditions as cond_mod, doubts, yards

# Weeks indoors before the last frost. Ranges because varieties differ and
# because a warm windowsill is not a greenhouse.
SEED_START_WEEKS = {
    "tomato": (6, 8), "pepper": (8, 10), "eggplant": (8, 10),
    "broccoli": (5, 6), "cabbage": (5, 6), "cauliflower": (5, 6),
    "kale": (5, 6), "brussels sprout": (5, 6),
    "cucumber": (3, 4), "squash": (3, 4), "melon": (3, 4), "pumpkin": (3, 4),
    "basil": (6, 8), "zinnia": (4, 6), "marigold": (6, 8), "cosmos": (4, 6),
    "onion": (10, 12), "leek": (10, 12), "celery": (10, 12),
    "lettuce": (4, 6), "chard": (4, 6), "parsley": (8, 10),
}
DIRECT_SOW = {"bean", "pea", "carrot", "radish", "beet", "turnip", "corn",
              "okra", "spinach", "cilantro", "dill", "sunflower", "nasturtium"}

# Catalogue days to maturity, from transplant unless noted as from seed.
DAYS_TO_MATURITY = {
    "bush bean": (50, "seed"), "pole bean": (65, "seed"), "pea": (60, "seed"),
    "radish": (28, "seed"), "carrot": (70, "seed"), "beet": (55, "seed"),
    "lettuce": (50, "seed"), "spinach": (40, "seed"), "okra": (55, "transplant"),
    "tomato": (75, "transplant"), "pepper": (75, "transplant"),
    "cucumber": (55, "seed"), "squash": (50, "seed"), "zucchini": (50, "seed"),
    "broccoli": (65, "transplant"), "cabbage": (70, "transplant"),
    "kale": (55, "transplant"), "corn": (75, "seed"), "melon": (85, "seed"),
}
MATURITY_SLOP_DAYS = 14      # catalogue figures assume conditions nobody has

# Anything here dies at 32 F, so a sow-by date that lands before the last frost
# is not a date, it is a conflict. This is the check that catches the classic
# error of back-planning a July harvest into an April that is still freezing.
FROST_TENDER = {"tomato", "pepper", "eggplant", "bean", "bush bean", "pole bean",
                "cucumber", "squash", "zucchini", "melon", "pumpkin", "corn",
                "okra", "basil", "zinnia", "marigold", "cosmos", "sunflower",
                "nasturtium"}
COLD_HARDY = {"pea", "radish", "carrot", "beet", "turnip", "lettuce", "spinach",
              "kale", "broccoli", "cabbage", "cauliflower", "chard", "onion",
              "leek", "brussels sprout", "cilantro", "parsley"}

# Hours for a task, and what it depends on being done first.
TASK_HOURS = {
    "measure and mark out": 2, "kill turf": 3, "sheet mulch": 4,
    "dig and edge a bed": 6, "install edging": 4, "spread and grade soil": 5,
    "build a raised bed": 5, "amend and till": 4, "run drip irrigation": 6,
    "lay a path": 10, "plant shrubs": 3, "plant perennials": 4,
    "sow seed": 1, "mulch": 3, "stake and trellis": 2, "water in": 1,
    "grooming and gap-fill": 3,
}
# The gate vocabulary in conditions.py is phrased the way a person describes
# what they have done. These are the build tasks, phrased the way a schedule
# describes them, so they have to be mapped onto it or every task falls through
# to "include the how-to" and the gating stops meaning anything.
TASK_ALIASES = {
    "measure and mark out": "weed",
    "kill turf": "spread compost",
    "sheet mulch": "mulch",
    "dig and edge a bed": "edge a bed",
    "install edging": "edge a bed",
    "spread and grade soil": "spread and grade soil",
    "build a raised bed": "build a raised bed",
    "amend and till": "spread compost",
    "run drip irrigation": "install drip",
    "lay a path": "lay a dry-laid path",
    "plant shrubs": "plant",
    "plant perennials": "plant",
    "sow seed": "sow seed",
    "mulch": "mulch",
    "stake and trellis": "plant",
    "water in": "water",
    "grooming and gap-fill": "weed",
}

ORDER = ["measure and mark out", "kill turf", "sheet mulch", "dig and edge a bed",
         "install edging", "build a raised bed", "spread and grade soil",
         "amend and till", "run drip irrigation", "lay a path", "sow seed",
         "plant shrubs", "plant perennials", "stake and trellis", "mulch",
         "water in", "grooming and gap-fill"]

WATERING_DECAY = [
    (7, "every day"),
    (21, "every other day"),
    (56, "twice a week"),
    (365, "once a week, deeply, through the first summer"),
]


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _date(v):
    """A date, from any of the shapes the record actually holds it in.

    `vision.json` stores a target date as a recorded preference with a strength
    and the sentence it came from, so the date arrives wrapped in a dict and
    with prose around it.
    """
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, dict):
        v = v.get("want") or v.get("date") or v.get("value") or ""
    if isinstance(v, list) and v:
        v = v[0]
        if isinstance(v, dict):
            v = v.get("want") or v.get("date") or ""
    hit = _ISO.search(str(v))
    if not hit:
        raise ValueError(f"no date in {v!r}")
    return datetime.date.fromisoformat(hit.group(0))


def _saturdays_back(target, count):
    """The `count` Saturdays on or before the target, most recent first."""
    d = _date(target)
    d -= datetime.timedelta(days=(d.weekday() - 5) % 7)
    return [d - datetime.timedelta(weeks=i) for i in range(count)]


def _away_ranges(cond):
    """Every weekend the yard gets no hours, as date ranges.

    Two sources, because they are two different facts. `person.travel_gaps` says
    where somebody is. `constraints.blackouts` says only that a period is spoken
    for, whatever the reason — and a week that is booked solid at home is not
    travel, so recording it as travel to get it honoured would be the same class
    of error this module was already making with the ground record.
    """
    out = []
    for g in (cond.get("person") or {}).get("travel_gaps", []):
        if isinstance(g, dict):
            a = _date(g.get("from") or g.get("start"))
            b = _date(g.get("to") or g.get("end") or a)
        else:
            a = b = _date(g)
        out.append((a, b, "away"))
    return out + [(a, b, "blacked out") for a, b in cond_mod.blackouts(cond)]


def _is_away(sat, ranges):
    """Why this weekend is lost, or None. Either of its two days is enough."""
    sun = sat + datetime.timedelta(days=1)
    for a, b, why in ranges:
        if any(a <= d <= b for d in (sat, sun)):
            return why
    return None


# ------------------------------------------------------------------ deadlines

def seed_start(crop, last_frost, year=None):
    """When to start this crop indoors, counting back from the last frost."""
    crop = crop.strip().lower()
    for name in DIRECT_SOW:
        if name in crop:
            return {"crop": crop, "direct_sow": True,
                    "say": f"{crop} is direct-sown. Starting it indoors sets it "
                           f"back rather than forward, because the taproot "
                           f"resents transplanting"}
    weeks = None
    for name, w in SEED_START_WEEKS.items():
        if name in crop or crop in name:
            weeks, matched = w, name
            break
    if weeks is None:
        return {"crop": crop, "unknown": True,
                "say": f"no seed-start figure for {crop}. Look it up on the "
                       f"packet; it is printed there as weeks before last frost"}
    frost = _date(last_frost)
    early = frost - datetime.timedelta(weeks=weeks[1])
    late = frost - datetime.timedelta(weeks=weeks[0])
    return {"crop": crop, "matched": matched, "weeks_before_frost": list(weeks),
            "start_between": [early.isoformat(), late.isoformat()],
            "transplant_after": frost.isoformat(),
            "say": f"start {crop} indoors between {early:%b %d} and {late:%b %d}, "
                   f"{weeks[0]}-{weeks[1]} weeks before the {frost:%b %d} frost "
                   f"date. Transplant after it"}


def sow_by(crop, harvest_by, last_frost=None):
    """Working backwards from a date something has to be ready to eat.

    Where a frost date is known, the answer is checked against it. A sow-by date
    that falls before the last frost for a tender crop is not a schedule, it is a
    conflict, and it is the single most common way a back-planned harvest fails."""
    crop = crop.strip().lower()
    dtm = None
    for name, v in DAYS_TO_MATURITY.items():
        if name in crop or crop in name:
            dtm, matched = v, name
            break
    if dtm is None:
        return {"crop": crop, "unknown": True,
                "say": f"no days-to-maturity figure for {crop}; it is on the "
                       f"packet"}
    days, frm = dtm
    target = _date(harvest_by)
    latest = target - datetime.timedelta(days=days + MATURITY_SLOP_DAYS)
    out = {"crop": crop, "matched": matched, "days_to_maturity": days,
           "counted_from": frm, "sow_by": latest.isoformat(),
           "say": f"to eat {crop} by {target:%b %d}, get it in the ground by "
                  f"{latest:%b %d} — {days} days to maturity from {frm}, plus "
                  f"a fortnight because catalogue figures assume conditions "
                  f"nobody has"}

    if not last_frost:
        return out
    frost = _parse_frost(last_frost)
    tender = any(t in crop or crop in t for t in FROST_TENDER)
    if tender and latest < frost:
        short = (frost - latest).days
        moved = frost + datetime.timedelta(days=days + MATURITY_SLOP_DAYS)
        direct = any(t in crop for t in DIRECT_SOW)
        if direct:
            ways = (f"warm the soil and cover with fabric or a low tunnel to get "
                    f"in a fortnight early; or move the harvest to "
                    f"{moved:%b %d}. Starting {crop} indoors is not the answer — "
                    f"it is direct-sown and transplanting sets it back further "
                    f"than the head start gains")
        else:
            ways = (f"start it indoors and transplant the day after the frost "
                    f"date; buy transplants rather than sowing; cover with "
                    f"fabric and accept the risk; or move the harvest to "
                    f"{moved:%b %d}")
        out["conflict"] = True
        out["say"] += (
            f".\n  But {crop} is frost-tender and the last frost is {frost:%b %d}, "
            f"{short} days after that, so this harvest date is not reachable "
            f"outdoors from seed. The ways out: {ways}")
    elif tender and (latest - frost).days < 7:
        out["say"] += (f". That is only {(latest - frost).days} days after the "
                       f"{frost:%b %d} frost date, so there is no room for a "
                       f"late one — have fabric ready")
    return out


def frost_dates(site):
    """The 10% risk dates, which is what a schedule should plan from."""
    c = (site or {}).get("climate") or {}
    local = c.get("local") or {}
    f = (c.get("frost_32f") or {})
    spring = local.get("last_spring_frost") or \
        (f.get("last_spring") or {}).get("risk_10_pct")
    fall = local.get("first_fall_frost") or \
        (f.get("first_fall") or {}).get("risk_10_pct")
    return spring, fall, bool(local)


# ------------------------------------------------------------------ the plan

def _cautions(plan, cond):
    """Standing rules that contradict a task actually on the calendar.

    A rule like "never mulch the bluebonnet strip" is worthless sitting in a
    constraints list if the plan says "mulch (3 h)" and nothing connects the
    two. This pairs them by verb so the rule appears on the weekend it matters.

    Reads `constraints.rules`, which `conditions.blank()` declares. It has to:
    a reader pointed at a key the schema never creates cannot fire on any
    conformant yard, and silently returning nothing looks exactly like a yard
    with no standing rules.
    """
    scheduled = {t["task"] for w in plan for t in w.get("tasks", [])}
    verbs = {t: TASK_ALIASES.get(t, t).split()[0] for t in scheduled}
    out = []
    for rule in (cond.get("constraints") or {}).get("rules", []):
        low = str(rule).lower()
        # On a word boundary: "weed" is inside "milkweed", and matching it there
        # attaches a monarch rule to the grooming weekend. And a rule can bear
        # on more than one task, so every match is reported rather than the
        # first one the dictionary happened to yield.
        hits = [t for t, v in sorted(verbs.items())
                if v and re.search(r"\b" + re.escape(v) + r"\w{0,3}\b", low)]
        if hits:
            out.append({"task": ", ".join(hits), "rule": rule})
    return out


def _target_zones_established(design, site, cond):
    """Whether every zone being planted into is already a working bed.

    Matched by name between the design's zones, the site's zone labels and the
    ground areas recorded in conditions.json, because the three are written by
    three different hands and rarely agree on wording.
    """
    zones = {p["zone"] for p in design.get("plants", [])
             if p.get("zone") and not p.get("existing")
             and p.get("role") != "existing"}
    if not zones:
        return False
    areas = (cond.get("ground") or {}).get("areas", [])
    if not areas:
        return False
    ready = ("planted", "dug", "built", "edged")
    for z in zones:
        spec = (site.get("zones") or {}).get(z) or {}
        names = [n for n in (z, spec.get("label"), spec.get("label_short")) if n]
        words = {w for n in names for w in str(n).lower()
                 .replace("_", " ").replace("-", " ").replace(",", " ").split()
                 if len(w) > 2 and w not in ("the", "and", "two", "for")}
        best, best_score = None, 0
        for a in areas:
            an = str(a.get("name", "")).lower()
            score = sum(1 for w in words if w in an)
            if score > best_score:
                best, best_score = a, score
        if not best or not any(r in str(best.get("state", "")).lower()
                               for r in ready):
            return False
    return True


def tasks_from_design(slug):
    """What the design implies has to happen, in the order it has to happen."""
    design = yards.load(slug, "design.json") or {}
    cond = yards.load_conditions(slug)
    ground = (cond.get("ground") or {})
    done = " ".join(str(a) for a in ground.get("areas", [])).lower()

    site = yards.load(slug, "site.json") or {}
    established = _target_zones_established(design, site, cond)

    # A mature bed being added to does not get marked out, stripped of turf,
    # edged or tilled. Scheduling those anyway is how a plan loses its
    # credibility on the first line.
    wanted = [] if established else ["measure and mark out"]
    if not established and (
            "turf" in done or
            "lawn" in (ground.get("surface_note") or "").lower()):
        wanted += ["kill turf"]
    if not established and not any(
            "edged" in str(a).lower() for a in ground.get("areas", [])):
        wanted += ["dig and edge a bed"]
    if any((h.get("kind") or "").lower() == "edging"
           for h in design.get("hardscape", [])):
        wanted += ["install edging"]
    if any("raised" in str(h.get("name", "")).lower()
           for h in design.get("hardscape", [])):
        wanted += ["build a raised bed", "spread and grade soil"]
    if any((h.get("kind") or "") in ("pavers", "flagstone", "gravel",
                                     "decomposed granite")
           for h in design.get("hardscape", [])):
        wanted += ["lay a path"]
    if (design.get("extra_materials") or {}).get("drip line") or \
            not (cond.get("water") or {}).get("irrigation"):
        wanted += ["run drip irrigation"]
    if not established:
        wanted += ["amend and till"]

    plants = design.get("plants", [])
    if any(p.get("pot_size") in ("3gal", "5gal", "7gal", "15gal", "b&b")
           or p.get("role") in ("structure", "tree") for p in plants):
        wanted += ["plant shrubs"]
    if plants:
        wanted += ["plant perennials"]
    if any(p.get("pot_size") == "seed" for p in plants):
        wanted += ["sow seed"]
    if any(p.get("needs_support") for p in plants):
        wanted += ["stake and trellis"]
    wanted += ["mulch", "water in", "grooming and gap-fill"]

    seen, out = set(), []
    for t in ORDER:
        if t in wanted and t not in seen:
            seen.add(t)
            out.append({"task": t, "hours": TASK_HOURS.get(t, 3)})
    return out


def _label_parts(plan):
    """Number split tasks in the order they will actually be worked.

    The plan is assembled backwards from the target, so a task split across
    weekends comes out with its last chunk first. Numbering happens here, after
    the reverse, or the labels read backwards to the person doing the work."""
    counts, totals = {}, {}
    for w in plan:
        for t in w["tasks"]:
            if t.get("split"):
                counts[t["task"]] = counts.get(t["task"], 0) + 1
                totals[t["task"]] = totals.get(t["task"], 0) + t["hours"]
    seen = {}
    for w in plan:
        for t in w["tasks"]:
            if not t.get("split"):
                continue
            seen[t["task"]] = seen.get(t["task"], 0) + 1
            t["part_note"] = (f"part {seen[t['task']]} of {counts[t['task']]} — "
                              f"{t['hours']} h of {totals[t['task']]}")


def build(slug, target=None, hours_per_weekend=None, start_from=None,
          force=False):
    # A schedule is a set of instructions with dates on it, and someone will act
    # on the first weekend of it before anyone re-reads the caveats. An open doubt
    # about what a bed is or where it goes reorders the whole calendar.
    provisional = doubts.gate(slug, "schedule", force=force)
    site = yards.load(slug, "site.json") or {}
    cond = yards.load_conditions(slug)
    vis = yards.load_vision(slug)
    target = target or vis.get("target_date")
    if not target:
        return {"error": "no target date, in vision.json or on the command line. "
                         "Nothing can be back-planned without one"}

    tasks = tasks_from_design(slug)
    if not tasks:
        return {"error": "no design.json to schedule"}

    # Groundwork is the expensive half of a plan and the half most likely to be
    # already done. Drawing it because the ground record is filed under a key
    # nothing reads is the one failure here that costs whole weekends, so it is
    # named rather than left to be noticed in the totals.
    stray = cond_mod.unread_ground(cond)
    groundwork = [t["task"] for t in tasks
                  if t["task"] in ("measure and mark out", "kill turf",
                                   "dig and edge a bed", "amend and till")]

    per_weekend = hours_per_weekend or cond_mod.weekly_hours(cond) or 6
    away = _away_ranges(cond)
    start_no_earlier = _date(start_from or datetime.date.today())

    total_hours = sum(t["hours"] for t in tasks)
    queue = [t for t in tasks if t["task"] != "grooming and gap-fill"]

    # Walk backwards from the target one weekend at a time until the work is
    # placed or we run out of calendar. Blocked weekends do not consume work, so
    # travel makes the plan reach further back rather than quietly dropping the
    # tasks that fall off the end.
    plan, index = [], 0
    groomed = caught_up = False
    while True:
        sat = _saturdays_back(target, index + 1)[-1]
        index += 1
        if sat < start_no_earlier:
            break
        entry = {"weekend_of": sat.isoformat(), "tasks": [], "hours": 0}

        why = _is_away(sat, away)
        if why:
            entry["note"] = (f"{why} — nothing scheduled. Anything already "
                             f"planted still needs water; leave a note for "
                             f"whoever is covering, scoped to keeping things "
                             f"alive. Keeping a planting alive is not work in "
                             f"the sense this weekend is lost for")
            plan.append(entry)
            continue
        if not groomed:
            groomed = True
            entry["tasks"].append(
                {"task": "grooming and gap-fill", "hours": 3,
                 "note": "the last working weekend before the date is for "
                         "tidying and filling gaps with something already in "
                         "flower. Nothing structural goes in here"})
            entry["hours"] = 3
            plan.append(entry)
            continue
        if not caught_up:
            caught_up = True
            entry["note"] = ("deliberately empty: the catch-up weekend. "
                             "Something always slips, and a plan with no slack "
                             "fails on the first rainy Saturday")
            plan.append(entry)
            continue

        while queue and entry["hours"] < per_weekend:
            room = per_weekend - entry["hours"]
            t = queue[-1]
            if t["hours"] > room:
                # A task bigger than one weekend gets split rather than
                # abandoned. Laying a path takes ten hours whether or not a
                # Saturday has ten hours in it
                if room < 2:
                    break
                queue[-1] = dict(t, hours=t["hours"] - room, split=True)
                t = dict(t, hours=room, split=True)
            else:
                queue.pop()
            gate, why = cond_mod.can_do(
                cond, TASK_ALIASES.get(t["task"], t["task"]))
            item = dict(t)
            if gate == "hire":
                item["hire_out"] = why
            elif gate in ("guide", "unknown"):
                item["needs_how_to"] = why
            entry["tasks"].append(item)
            entry["hours"] += t["hours"]
        # tasks came off the queue in reverse dependency order, since the plan is
        # assembled backwards; within a weekend they have to read forwards
        entry["tasks"].reverse()
        plan.append(entry)
        if not queue:
            break

    plan.reverse()
    _label_parts(plan)
    spring, fall, local = frost_dates(site)
    out = {"yard": slug, "target_date": _date(target).isoformat(),
           "total_hours": total_hours,
           "hours_per_weekend": per_weekend,
           "weekends": [p for p in plan if p["tasks"] or p.get("note")],
           "unscheduled": queue,
           "last_frost": spring, "first_frost": fall,
           "frost_source": "local figure" if local
                           else "derived from reanalysis; runs early",
           "establishment_watering": [
               {"through_day": d, "frequency": how} for d, how in WATERING_DECAY],
           "cautions": _cautions(plan, cond),
           }
    if stray and groundwork:
        keys = ", ".join(f"ground.{s['key']} ({s['count']} records)"
                         for s in stray)
        out["ground_unread"] = (
            f"{sum(TASK_HOURS.get(t, 3) for t in groundwork)} of these hours "
            f"are groundwork — {', '.join(groundwork)} — and this yard records "
            f"{keys}, which nothing reads. ground.areas is empty, so the plan "
            f"above is a bare-lot plan. If those beds already exist, move the "
            f"records onto `areas` with a `state` each and re-run; the "
            f"groundwork will drop out on its own")
    if provisional:
        out["provenance"] = provisional
    restriction = ((cond.get("water") or {}).get("irrigation") or {}) \
        .get("restriction")
    if restriction:
        out["watering_restriction"] = restriction
    if queue:
        short_h = sum(t["hours"] for t in queue)
        # queue holds the earliest tasks, which are the prerequisites, so what
        # does not fit is the groundwork rather than the finishing
        need_weeks = int(-(-short_h // per_weekend))
        earliest = _date(target) - datetime.timedelta(
            weeks=len(plan) + need_weeks)
        out["unscheduled"] = queue
        out["warning"] = (
            f"{short_h} hours do not fit before {target} at {per_weekend} hours a "
            f"weekend, and what does not fit is the groundwork the rest depends "
            f"on: {', '.join(t['task'] for t in queue)}. Planting into a bed that "
            f"was never edged or amended is worse than not planting. Three real "
            f"options: start by {earliest:%b %d} instead, which needs "
            f"{need_weeks} more weekends; hire out the heavy items; or cut the "
            f"scope to what fits and phase the rest")
    return out


def report(slug, target=None, hours=None, force=False):
    p = build(slug, target, hours, force=force)
    if "error" in p:
        print(f"  {p['error']}")
        return
    print(f"{slug} — {p['total_hours']} hours of work, back-planned from "
          f"{p['target_date']}\n")
    if p.get("provenance"):
        print(f"  {p['provenance']}: the dates below rest on assumptions still "
              f"in question\n")
    if p.get("ground_unread"):
        print(f"  {p['ground_unread']}\n")
    if p.get("warning"):
        print(f"  {p['warning']}\n")
    if p["last_frost"]:
        print(f"  last frost {p['last_frost']}, first frost {p['first_frost']} "
              f"({p['frost_source']})\n")

    for w in p["weekends"]:
        head = f"  weekend of {w['weekend_of']}"
        if w["tasks"]:
            head += f"   {w['hours']} h"
        print(head)
        if w.get("note"):
            print(f"      {w['note']}")
        for t in w["tasks"]:
            line = f"      {t['task']} ({t['hours']} h)"
            if t.get("hire_out"):
                line += f"   HIRE — {t['hire_out']}"
            elif t.get("needs_how_to"):
                line += f"   include the how-to — {t['needs_how_to']}"
            print(line)
            for key in ("note", "part_note"):
                if t.get(key):
                    print(f"          {t[key]}")

    if p.get("cautions"):
        print("\n  standing rules that touch a task on this calendar:")
        for c in p["cautions"]:
            print(f"      {c['task']}: {c['rule']}")

    print("\n  establishment watering, which is what actually kills plantings:")
    for w in p["establishment_watering"]:
        print(f"      through day {w['through_day']:>3}   {w['frequency']}")
    if p.get("watering_restriction"):
        print(f"      {p['watering_restriction']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--target")
    ap.add_argument("--hours", type=float, help="hours per weekend")
    ap.add_argument("--seed-start", help="comma-separated crops")
    ap.add_argument("--last-frost")
    ap.add_argument("--harvest-by")
    ap.add_argument("--crop")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="plan a yard whose board still has open doubts; the "
                         "result is stamped provisional")
    args = ap.parse_args()

    if args.seed_start:
        frost = args.last_frost
        if not frost and args.slug:
            frost = frost_dates(yards.load(args.slug, "site.json"))[0]
        if not frost:
            print("  need a last-frost date: --last-frost, or a slug whose "
                  "site.json has a climate block")
            return
        for crop in args.seed_start.split(","):
            print("  " + seed_start(crop, _parse_frost(frost))["say"])
        return
    if args.harvest_by and args.crop:
        frost = args.last_frost
        if not frost and args.slug:
            frost = frost_dates(yards.load(args.slug, "site.json"))[0]
        print("  " + sow_by(args.crop, args.harvest_by, frost)["say"])
        return
    if not args.slug:
        print(__doc__)
        return
    if args.json:
        print(json.dumps(build(args.slug, args.target, args.hours,
                               force=args.force), indent=2))
        return
    report(args.slug, args.target, args.hours, force=args.force)


def _parse_frost(v):
    """Frost dates arrive as 'Apr 16' from the climate module or as ISO."""
    s = str(v).strip()
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        pass
    year = datetime.date.today().year + 1
    for fmt in ("%b %d", "%B %d", "%m/%d"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            return datetime.date(year, d.month, d.day)
        except ValueError:
            continue
    raise SystemExit(f"could not read {v!r} as a date")


if __name__ == "__main__":
    main()
