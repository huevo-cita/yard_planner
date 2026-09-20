#!/usr/bin/env python3
"""Two independent derivations of the same build, put side by side.

    python3 -m lib.reconcile <slug>              where the two disagree
    python3 -m lib.reconcile <slug> --basis      what is compared, and what is not
    python3 -m lib.reconcile <slug> --json

Why a third thing rather than one of the two
--------------------------------------------
`lib.schedule` works forward from `design.json` and the hours on file: given
this much work and this many Saturdays, when does it have to start. `tasks.json`
is curated by hand from the plan documents and holds what somebody actually
intends to do on a day. They were built for different questions and they had
never been compared, which is how one of them came to put the autumn's largest
planting five weeks off the other with nothing anywhere noticing.

The obvious fix is to make `lib.schedule` read `tasks.json`. It is the wrong
fix, and the reason is the whole point of this module: **two independent
derivations that agree is evidence; a copy that agrees is not.** A schedule that
took its dates from `tasks.json` would have agreed with it perfectly on the
month it was a month wrong. `lib.schedule` also answers a question that exists
before `tasks.json` does — can this design be built in the hours available
before the date, on a yard with no tasks yet — and a module that depends on its
own downstream consumer cannot answer it.

So neither reads the other and this reads both. `lib.schedule` gains the reader
it never had, without gaining a dependency that would make its agreement
worthless.

Comparing like with like
------------------------
`build()` places archetype tasks and nothing else. All seventeen entries in its
`ORDER` are build work, which `tools/test_blackout.py` asserts rather than
assumes. `tasks.json` on a real yard holds ninety-odd tasks across twenty kinds,
most of which `build()` has no concept of — a pest walk, a supplier phone call, a
gutter clean every six months. Reconciling eleven hours against all of them
would produce a number nobody could act on.

So both sides are mapped into `STAGES` below, which is a declared table rather
than a tolerance. Every archetype in `schedule.ORDER` belongs to exactly one
stage. Every `kind` a yard's `tasks.json` uses belongs to exactly one stage, or
to `UNASSIGNED`, or to `OUTSIDE` — and a kind in none of the three is reported,
not quietly dropped. That is the same shape as `conditions.blackout_bars`
returning `unscoped` rather than `permitted`: silence about a kind of work is
not permission to leave it out of the sum.

Three axes, because they fail separately
----------------------------------------
    presence    a stage carrying hours on one side and none on the other. This
                is the loudest finding and usually the most useful: it means one
                of the two does not know the work exists
    hours       how much work each side thinks a stage is, expressed in
                weekends rather than hours, because a weekend is the unit
                `build()` plans in and "six hours apart" is not actionable
    timing      when each side puts the stage. This is the axis the original
                divergence lived on, and totals alone would never have caught
                it: the two could agree to the hour on how much planting there
                is and still disagree by a month about when it happens

All three of `opens`, `bulk` and `closes` are reported for timing and only
`bulk` — the day a stage passes half its hours — decides the verdict. The other
two are each set by one job at one end: a single tray sown indoors in September
drags a planting stage's `opens` two months earlier while saying nothing about
where the work is, and a check that fires on that fires on every yard that
starts seed early. `bulk` is the one of the three no small job can move.

The resolution of the comparison
--------------------------------
`build()` places work in whole weekends at a single hours-per-weekend figure. It
therefore cannot distinguish two dates less than a weekend apart, or two
quantities of work smaller than one weekend's capacity. Those two numbers are
what this reports against, and both are read off the plan rather than tuned: the
threshold is the coarser instrument's own resolution, not a tolerance somebody
picked to make the output quiet.

A difference inside the resolution is reported as agreement, and reported out
loud. Casey's argument for keeping both modules rests on agreement being
evidence, and evidence nobody prints is not evidence.

Not gated, deliberately
-----------------------
This produces no plan, writes no file and costs nothing, and it is one of the
ways a doubt about the schedule gets settled. But `schedule.build()` gates
itself, as it should — the gate has to hold for programmatic callers. So this
catches the refusal and reports it as a finding rather than forcing past it: a
yard whose board is not clear for `schedule` has no independent derivation to
compare against, and that is the honest answer rather than a `--force` stamp.
"""
import argparse
import datetime
import json

from . import schedule, week

#: How many days one weekend is, for the resolution argument above. Not a
#: tolerance: it is the width of `build()`'s own placement unit, and two dates
#: inside it are the same date as far as a weekend-granular plan can tell.
WEEKEND_DAYS = 7

#: The bridge between the two vocabularies. `archetypes` are `schedule.ORDER`
#: entries; `kinds` are `tasks.json` `kind` values.
#:
#: Three stages and not seventeen, because the resolution of the comparison is
#: set by the coarser of the two vocabularies and that is `kind`. `prep` alone
#: covers pre-moistening a seed tray at the kitchen sink and clearing the weeds
#: out of a bed, and splitting `structure` into marking-out, digging and tilling
#: would mean assigning that kind to one of them on a guess. Where a guess is
#: the only way to a finer answer, the finer answer is not worth having.
STAGES = [
    {
        "stage": "structure",
        "what": "moving earth, soil, stone, timber or pipe",
        "archetypes": ["measure and mark out", "kill turf", "sheet mulch",
                       "dig and edge a bed", "install edging",
                       "build a raised bed", "spread and grade soil",
                       "amend and till", "run drip irrigation", "lay a path",
                       "stake and trellis"],
        "kinds": ["build"],
        "why": "`build` is the one kind a yard uses for work that puts "
               "structure into the ground, and every archetype here does that. "
               "`stake and trellis` is in this stage rather than with the "
               "planting it supports because a trellis is timber: it is the "
               "kind of work, not the week it happens in, that decides which "
               "side of the bridge a job stands on.",
    },
    {
        "stage": "planting",
        "what": "putting a plant or a seed in the ground",
        "archetypes": ["sow seed", "plant shrubs", "plant perennials"],
        "kinds": ["plant", "sow", "transplant"],
        "why": "the three task kinds are the same act at three ages — a seed, "
               "a plug moved on, a plant out of a pot — and `build()` has one "
               "archetype for each of the first and third and none for the "
               "middle. Comparing them as one stage is what makes the totals "
               "answer the same question.",
    },
    {
        "stage": "aftercare",
        "what": "settling in what has just gone in, and making it read",
        "archetypes": ["mulch", "water in", "grooming and gap-fill"],
        "kinds": ["water", "tidy"],
        "why": "`water in` is the watering that belongs to a planting day, and "
               "it is the only watering `build()` puts a date on. The standing "
               "regime that follows leaves `build()` as "
               "`establishment_watering`, a decay cadence with no dates and no "
               "hours, so a repeating watering job on the other side has "
               "nothing to be compared against — see `REPEATS` below.",
    },
]

#: Kinds a yard uses that no stage claims, and that are not an oversight.
#: `build()` has no archetype for any of them, and inventing one to make the
#: sums balance would be the copy this module exists to avoid.
OUTSIDE = {
    "prune": "a standing maintenance calendar. `build()` models a build, and "
             "nothing in `ORDER` prunes anything.",
    "pest": "watching for something that may not happen. There is no hours "
            "figure a design could imply for it.",
    "inspect": "looking at the yard. `build()` has no concept of a visit that "
               "produces no change.",
    "harvest": "taking food out of a bed the build put in. It is downstream of "
               "everything here.",
    "thin": "editing a planting after it has grown, sometimes years later. "
            "`build()` plans up to a date, not through the seasons after it.",
    "feed": "feeding an established planting, which is maintenance rather than "
            "build.",
    "protect": "a contingent response to a forecast. It has a window rather "
               "than a date because nobody knows whether it happens at all.",
    "timer": "operating an irrigation controller that already exists. "
             "`run drip irrigation` is installing one, which is a different "
             "job and is in `structure`.",
    "call": "a phone call to a supplier. Sourcing is `lib.sourcing`'s job.",
    "buy": "buying. `build()` costs nothing and buys nothing; that is "
           "`lib.bom` and the `shopping` block of tasks.json.",
    "decide": "a decision somebody has to make. If it blocks an expensive job "
              "it is a doubt card, not a build hour.",
    "deadline": "a date with no work on it — a sale window closing, a "
                "delivery. Zero minutes by construction.",
    "event": "the party itself. It is what the whole plan is for and it is not "
             "work on the garden.",
}

#: Kinds that genuinely span the bridge and cannot be put on one side of it.
#: Declared rather than silently folded into a stage, because a kind counted
#: into `structure` here would move the hours by more than the finding is worth
#: and the mis-assignment would be invisible.
UNASSIGNED = {
    "prep": "spans the bridge. Pre-moistening a germination tray and clearing "
            "the weeds out of a bed are both `prep`, and one of them is "
            "structure work while the other is not. This is the same "
            "ambiguity that kept `prep` out of both of the December "
            "blackout's kind lists, and for the same reason: assigning it "
            "would be a guess with hours riding on it.",
}

#: Why a repeating task's minutes are left out of every total. Its `minutes` are
#: per occurrence, so summing them is meaningless and multiplying them out
#: quotes a figure against a cadence that runs past the target date. `lib.week`
#: leaves them out of a weekly total for the same reason.
REPEATS = ("a repeating job's minutes are per occurrence, so they are counted "
           "as jobs and not as hours. On the schedule side the matching thing "
           "is `establishment_watering`, which carries a cadence and no hours "
           "at all.")


# ------------------------------------------------------------------ the bridge


def basis():
    """The declared bridge, and whether it still covers both vocabularies.

    Recovered against `schedule.ORDER` rather than restated, so an archetype
    added to the schedule and not to a stage is a finding here instead of a
    silent omission from the sums. This is the same argument `lib.inputs` makes
    for deriving its map from the source and comparing.
    """
    claimed = {}
    for s in STAGES:
        for a in s["archetypes"]:
            claimed.setdefault(a, []).append(s["stage"])
    order = list(schedule.ORDER)
    return {
        "stages": [s["stage"] for s in STAGES],
        "archetypes": order,
        "orphan_archetypes": [a for a in order if a not in claimed],
        "double_claimed": {a: v for a, v in claimed.items() if len(v) > 1},
        "phantom_archetypes": [a for a in claimed if a not in order],
        "kinds": {s["stage"]: list(s["kinds"]) for s in STAGES},
        "unassigned": dict(UNASSIGNED),
        "outside": dict(OUTSIDE),
    }


def stage_of_kind(kind):
    """Which stage a `tasks.json` kind belongs to, or None."""
    for s in STAGES:
        if kind in s["kinds"]:
            return s["stage"]
    return None


# --------------------------------------------------------- the schedule's side

def _archetype_stage(task):
    for s in STAGES:
        if task in s["archetypes"]:
            return s["stage"]
    return None


def from_schedule(slug, target=None, hours=None):
    """`build()`'s plan, collapsed onto the stages.

    The gate is allowed to refuse. `build()` calls `doubts.gate()` and that has
    to hold for programmatic callers, so the refusal is caught and returned as a
    fact about the yard rather than overridden with `force=True`. A yard that is
    not clear for `schedule` has no second derivation, and saying so is a better
    answer than a provisional one.
    """
    try:
        plan = schedule.build(slug, target=target, hours_per_weekend=hours)
    except SystemExit as exc:
        return {"blocked": str(exc).splitlines()[0] if str(exc) else
                "schedule refused to run", "stages": {}}
    if plan.get("error"):
        return {"blocked": plan["error"], "stages": {}}

    per = plan["hours_per_weekend"]
    stages = {}
    for w in plan["weekends"]:
        day = datetime.date.fromisoformat(w["weekend_of"])
        for t in w["tasks"]:
            st = _archetype_stage(t["task"])
            if st is None:
                continue
            rec = stages.setdefault(st, {"hours": 0.0, "days": [], "items": []})
            rec["hours"] += t["hours"]
            rec["days"].append((day, t["hours"]))
            rec["items"].append({"task": t["task"], "hours": t["hours"],
                                 "day": day.isoformat()})
    unplaced = [t for t in plan.get("unscheduled") or []]
    return {
        "blocked": None,
        "target": plan["target_date"],
        "hours_per_weekend": per,
        "total_hours": plan["total_hours"],
        "stages": stages,
        "unscheduled": unplaced,
        "watering_regime": bool(plan.get("establishment_watering")),
        "ground_unread": plan.get("ground_unread"),
        "warning": plan.get("warning"),
    }


# ------------------------------------------------------------ tasks.json's side

def _when(t):
    """A task's first and last day, whatever shape its date is in.

    A window's two ends are used as they are written. Unlike `lib.week`, which
    has to name one day a repeating or windowed job asks for work on, this is
    asking how wide a stage is, and a window is genuinely that wide.
    """
    if t.get("date"):
        d = datetime.date.fromisoformat(t["date"])
        return d, d
    if t.get("window"):
        return (datetime.date.fromisoformat(t["window"][0]),
                datetime.date.fromisoformat(t["window"][1]))
    r = t.get("repeat") or {}
    if r.get("from"):
        return (datetime.date.fromisoformat(r["from"]),
                datetime.date.fromisoformat(r["to"]))
    return None, None


def from_tasks(slug, target=None):
    """The dated work in `tasks.json`, collapsed onto the same stages.

    Restricted to work on or before the target date, because `build()` plans up
    to that date and cannot see past it. What falls outside is counted and named
    rather than dropped, so the restriction is legible instead of being a
    silently smaller total.
    """
    data = week.load(slug) or {}
    end = datetime.date.fromisoformat(target) if target else None

    stages, kinds_seen = {}, {}
    beyond, repeating, undated = [], [], []
    for t in data.get("tasks", []):
        kind = t.get("kind")
        kinds_seen.setdefault(kind, 0)
        kinds_seen[kind] += 1
        first, last = _when(t)
        if first is None:
            undated.append(t["id"])
            continue
        if end and first > end:
            beyond.append({"id": t["id"], "kind": kind,
                           "date": first.isoformat()})
            continue
        st = stage_of_kind(kind)
        if st is None:
            continue
        rec = stages.setdefault(st, {"hours": 0.0, "days": [], "items": [],
                                     "repeats": []})
        if t.get("repeat"):
            rec["repeats"].append(
                {"id": t["id"], "title": t["title"], "kind": kind,
                 "every": (t.get("repeat") or {}).get("every")})
            repeating.append(t["id"])
            continue
        hours = t.get("minutes", 0) / 60.0
        rec["hours"] += hours
        rec["days"].append((first, hours))
        rec["items"].append({"id": t["id"], "title": t["title"], "kind": kind,
                             "hours": round(hours, 2),
                             "from": first.isoformat(),
                             "to": last.isoformat()})
    return {"stages": stages, "kinds_seen": kinds_seen, "beyond_target": beyond,
            "repeating": repeating, "undated": undated,
            "n_tasks": len(data.get("tasks", [])),
            "shopping": len(data.get("shopping", []))}


# ------------------------------------------------------------------ the measure

def _span(days):
    """`opens`, `bulk` and `closes` for a list of (day, hours).

    `bulk` is the day the work passes half its hours. It is the figure to read
    when asking "when does this stage actually happen", because `opens` is moved
    by the smallest job at the front — a single tray sown indoors in September
    puts the planting stage's start two months before any planting worth the
    name, and says nothing true about where the work is.
    """
    if not days:
        return None
    ordered = sorted(days)
    total = sum(h for _, h in ordered)
    bulk = ordered[0][0]
    if total > 0:
        run = 0.0
        for day, h in ordered:
            run += h
            if run >= total / 2.0:
                bulk = day
                break
    return {"opens": ordered[0][0], "bulk": bulk,
            "closes": max(d for d, _ in ordered)}


def _weekends(hours, per):
    return round(hours / per, 1) if per else None


def _side(rec, per):
    """One side of one stage, as the numbers the report and the tests both read."""
    span = _span(rec["days"])
    return {"hours": round(rec["hours"], 2),
            "weekends": _weekends(rec["hours"], per),
            "opens": span["opens"].isoformat() if span else None,
            "bulk": span["bulk"].isoformat() if span else None,
            "closes": span["closes"].isoformat() if span else None,
            "items": rec["items"],
            "repeats": rec.get("repeats") or []}


def _vocabulary(tasks):
    """Findings about the bridge itself, which come before any number.

    A vocabulary that has outgrown the table makes every total quietly wrong, so
    it is reported first rather than discovered afterwards.
    """
    out, b = [], basis()
    for a in b["orphan_archetypes"]:
        out.append({
            "kind": "unmapped-archetype", "stage": None, "subject": a,
            "message": f"schedule.ORDER places {a!r} and no stage claims it, "
                       f"so its hours are in the plan and in neither total "
                       f"below. Put it in a stage."})
    for a, claims in sorted(b["double_claimed"].items()):
        out.append({
            "kind": "unmapped-archetype", "stage": None, "subject": a,
            "message": f"{a!r} is claimed by {' and '.join(claims)}, so its "
                       f"hours are counted twice."})
    for a in sorted(b["phantom_archetypes"]):
        out.append({
            "kind": "unmapped-archetype", "stage": None, "subject": a,
            "message": f"a stage claims {a!r}, which schedule.ORDER no longer "
                       f"holds. The name moved and the bridge did not."})
    if tasks is None:
        return out
    for kind, n in sorted(tasks["kinds_seen"].items(), key=lambda kv: str(kv[0])):
        many = "s" if n > 1 else ""
        if kind is None:
            out.append({
                "kind": "unmapped-kind", "stage": None, "subject": "(no kind)",
                "message": f"{n} task{many} in tasks.json carr"
                           f"{'y' if n > 1 else 'ies'} no `kind`, so nothing "
                           f"can say which stage they belong to."})
            continue
        if stage_of_kind(kind) or kind in UNASSIGNED or kind in OUTSIDE:
            continue
        out.append({
            "kind": "unmapped-kind", "stage": None, "subject": kind,
            "message": f"this yard uses kind {kind!r} on {n} task{many} and no "
                       f"stage, exclusion or unassigned entry mentions it. "
                       f"Nobody has said whether it is build work, so it is in "
                       f"no total. Declare it in STAGES, OUTSIDE or "
                       f"UNASSIGNED."})
    return out


def _hours_axis(name, s, t, per):
    """How much work each side thinks a stage is, in weekends."""
    gap = t["hours"] - s["hours"]
    apart = _weekends(abs(gap), per)
    if abs(gap) < per:
        return {"axis": "hours", "verdict": "agrees", "apart_weekends": apart,
                "message": f"{s['hours']:.2f} h on the schedule against "
                           f"{t['hours']:.2f} h in tasks.json — {apart} of a "
                           f"weekend apart, inside what a weekend-granular "
                           f"plan can tell."}
    more, less = ("tasks.json", "the schedule") if gap > 0 \
        else ("the schedule", "tasks.json")
    return {"axis": "hours", "verdict": "diverges", "apart_weekends": apart,
            "message": f"{more} holds {apart} more weekends of it than "
                       f"{less} does — {s['hours']:.2f} h on the schedule "
                       f"against {t['hours']:.2f} h in tasks.json, at {per} h "
                       f"a weekend."}


def _timing_axis(name, s, t):
    """When each side puts a stage. Judged on the bulk and nothing else.

    All three dates are reported and only `bulk` decides the verdict. `opens`
    and `closes` are each set by a single job at one end — one tray sown indoors
    in September moves a planting stage's `opens` by two months and says nothing
    about where the work is — and a check that fires on that fires on every yard
    that starts seed early, which is the linter crying wolf that AGENTS.md warns
    about for the date check. `bulk`, the day a stage passes half its hours, is
    the one figure of the three that no single small job can move.
    """
    if not (s["bulk"] and t["bulk"]):
        return None
    gaps = {k: (datetime.date.fromisoformat(t[k])
                - datetime.date.fromisoformat(s[k])).days
            for k in ("opens", "bulk", "closes")}
    where = (f"the schedule opens it {_say(s['opens'])}, does the bulk "
             f"{_say(s['bulk'])} and closes {_say(s['closes'])}; tasks.json "
             f"opens it {_say(t['opens'])}, does the bulk {_say(t['bulk'])} "
             f"and closes {_say(t['closes'])}")
    bulk = gaps["bulk"]
    if abs(bulk) <= WEEKEND_DAYS:
        return {"axis": "timing", "verdict": "agrees", "gaps": gaps,
                "message": f"both put the bulk of it within {abs(bulk)} day"
                           f"{'s' if abs(bulk) != 1 else ''} — {where}."}
    way = "later" if bulk > 0 else "earlier"
    return {"axis": "timing", "verdict": "diverges", "gaps": gaps,
            "message": f"tasks.json does the bulk of it {abs(bulk)} days "
                       f"{way} than the schedule — {abs(bulk) // WEEKEND_DAYS} "
                       f"weekends apart. In full: {where}."}


def _say(iso):
    return f"{datetime.date.fromisoformat(iso):%-d %b}" if iso else "never"


def compare(slug, target=None, hours=None):
    """Everything the two derivations say differently, and what they agree on.

    One entry per stage rather than one per axis, because "planting" is the
    subject somebody acts on and printing it twice under two headings is how a
    report stops being read.
    """
    sched = from_schedule(slug, target=target, hours=hours)
    if sched["blocked"]:
        return {"yard": slug, "target": target, "schedule": sched,
                "tasks": None, "basis": basis(), "stages": [], "agreements": [],
                "findings": [{"kind": "blocked", "stage": None,
                              "message": f"there is no second derivation to "
                                         f"compare against. "
                                         f"{sched['blocked']}"}]}

    target = target or sched["target"]
    tasks = from_tasks(slug, target=target)
    per = sched["hours_per_weekend"]
    empty = {"hours": 0.0, "days": [], "items": [], "repeats": []}

    findings = _vocabulary(tasks)
    results, agreements = [], []

    for spec in STAGES:
        name = spec["stage"]
        s = _side(sched["stages"].get(name) or empty, per)
        t = _side(tasks["stages"].get(name) or empty, per)
        rec = {"stage": name, "what": spec["what"], "schedule": s, "tasks": t,
               "axes": []}

        if not s["hours"] and not t["hours"]:
            rec["kind"] = "empty"
            rec["message"] = (f"neither side has any {name} work"
                              + (f", though tasks.json has "
                                 f"{len(t['repeats'])} repeating "
                                 f"job{'s' if len(t['repeats']) != 1 else ''} "
                                 f"of that kind" if t["repeats"] else ""))
            results.append(rec)
            continue

        if not s["hours"] or not t["hours"]:
            have, lack = ("tasks.json", "the schedule") if t["hours"] \
                else ("the schedule", "tasks.json")
            got, n = ((t["hours"], len(t["items"])) if t["hours"]
                      else (s["hours"], len(s["items"])))
            rec["kind"] = "absent"
            rec["message"] = (
                f"{have} holds {got:.2f} h of it over {n} "
                f"job{'s' if n != 1 else ''} and {lack} has none at all. One "
                f"of the two does not know this work exists, which is a "
                f"stronger finding than any difference of degree.")
            findings.append(rec)
            results.append(rec)
            continue

        for axis in (_hours_axis(name, s, t, per), _timing_axis(name, s, t)):
            if axis:
                rec["axes"].append(axis)
                if axis["verdict"] == "agrees":
                    agreements.append(dict(axis, stage=name))
        bad = [a for a in rec["axes"] if a["verdict"] == "diverges"]
        rec["kind"] = "diverges" if bad else "agrees"
        rec["message"] = "; ".join(a["axis"] for a in bad) + " disagree" \
            if bad else "both axes agree inside the resolution"
        results.append(rec)
        if bad:
            findings.append(rec)

    return {"yard": slug, "target": target, "schedule": sched, "tasks": tasks,
            "basis": basis(), "stages": results, "findings": findings,
            "agreements": agreements}


# ------------------------------------------------------------------ reporting

def _wrap(text, width=68):
    out, line = [], ""
    for word in str(text).split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


def _say_lines(text, indent, width=None):
    for line in _wrap(text, width or (78 - len(indent))):
        print(f"{indent}{line}")


def _field(label, text):
    """A labelled line with a hanging indent, so the labels read as a column."""
    lines = _wrap(text, 63)
    print(f"  {label:<11}{lines[0]}")
    for line in lines[1:]:
        print(f"  {'':<11}{line}")


def _n(count, word):
    return f"{count} {word}{'s' if count != 1 else ''}"


def report_basis():
    print("what is compared, and what is not\n")
    for s in STAGES:
        print(f"  {s['stage']} — {s['what']}")
        _say_lines("schedule: " + ", ".join(s["archetypes"]), "      ")
        print(f"      tasks.json kinds: {', '.join(s['kinds'])}")
        _say_lines(s["why"], "      ")
        print()
    print("  in tasks.json and outside build()'s vocabulary entirely:")
    for kind, why in sorted(OUTSIDE.items()):
        for i, line in enumerate(_wrap(why, 58)):
            print(f"      {kind if i == 0 else '':<10} {line}")
    print("\n  in tasks.json and deliberately assigned to no stage:")
    for kind, why in sorted(UNASSIGNED.items()):
        for i, line in enumerate(_wrap(why, 58)):
            print(f"      {kind if i == 0 else '':<10} {line}")
    print("\n  repeating jobs, on either side:")
    _say_lines(REPEATS, "      ")

    b = basis()
    print()
    if b["orphan_archetypes"] or b["double_claimed"] or b["phantom_archetypes"]:
        print("  THE BRIDGE NO LONGER COVERS schedule.ORDER:")
        for a in b["orphan_archetypes"]:
            print(f"      {a!r} is in ORDER and in no stage")
        for a, v in sorted(b["double_claimed"].items()):
            print(f"      {a!r} is claimed by {', '.join(v)}")
        for a in sorted(b["phantom_archetypes"]):
            print(f"      {a!r} is claimed by a stage and not in ORDER")
    else:
        print(f"  the bridge covers all {len(schedule.ORDER)} entries of "
              f"schedule.ORDER, each in exactly one stage")


def _items_line(label, items, fmt, indent="          "):
    text = ", ".join(fmt(i) for i in items[:6]) or "nothing"
    if len(items) > 6:
        text += f", and {len(items) - 6} more"
    _say_lines(f"{label} {text}", indent)


def report(slug, target=None, hours=None):
    r = compare(slug, target=target, hours=hours)
    sched, tasks = r["schedule"], r["tasks"]

    print(f"{slug} — lib.schedule against tasks.json\n")
    _say_lines(
        "Two derivations of the same build that do not read each other. "
        "lib.schedule works forward from design.json and the hours on file; "
        "tasks.json is curated by hand from the plan documents. Neither is the "
        "other's source, which is what makes agreement worth something.", "  ")
    print()

    blocked = [f for f in r["findings"] if f["kind"] == "blocked"]
    if blocked:
        for f in blocked:
            _say_lines(f["message"], "  ")
        print(f"\n      python3 -m lib.doubts {slug} --open")
        return r

    used = [k for k in tasks["kinds_seen"] if k]
    bridged = [k for k in used if stage_of_kind(k)]
    out_here = sorted(k for k in used if k in OUTSIDE)
    un_here = sorted(k for k in used if k in UNASSIGNED)
    _field("basis", f"{_n(len(STAGES), 'stage')}, bridging all "
                    f"{len(schedule.ORDER)} schedule archetypes onto "
                    f"{len(bridged)} of the {len(used)} task kinds this yard "
                    f"uses")
    _field("excluded", f"{_n(len(out_here), 'kind')} build() has no concept of "
                       f"({', '.join(out_here) or 'none'}); "
                       f"{len(un_here)} that cannot be assigned to one side "
                       f"({', '.join(un_here) or 'none'}); "
                       f"{_n(len(tasks['repeating']), 'repeating job')}; "
                       f"{_n(len(tasks['beyond_target']), 'task')} dated after "
                       f"{r['target']}; and the "
                       f"{_n(tasks['shopping'], 'line')} of shopping list. "
                       f"`--basis` says why for each.")
    _field("resolution", f"one weekend = {sched['hours_per_weekend']} h and "
                         f"{WEEKEND_DAYS} days. Inside that the two cannot be "
                         f"told apart.")
    n_rec = sum(len(v["items"]) for v in tasks["stages"].values())
    _field("totals", f"schedule {sched['total_hours']} h of build work; "
                     f"tasks.json {tasks['n_tasks']} tasks, {n_rec} of them "
                     f"reconcilable")
    if sched.get("ground_unread"):
        print()
        _say_lines("NOTE the schedule says: " + sched["ground_unread"], "  ")
    print()

    for f in r["findings"]:
        if f["kind"] in ("unmapped-archetype", "unmapped-kind"):
            print(f"  {f['kind'].upper()} — {f['subject']}")
            _say_lines(f["message"], "      ")
            print()

    stage_findings = [f for f in r["findings"] if f.get("axes") is not None
                      or f["kind"] == "absent"]
    if not stage_findings:
        print("  Nothing disagrees outside the resolution of the comparison.\n")

    for rec in stage_findings:
        print(f"  {rec['kind'].upper()} — {rec['stage']}, "
              f"{rec['what']}")
        if rec["kind"] == "absent":
            _say_lines(rec["message"], "      ")
        for a in rec.get("axes", []):
            if a["verdict"] == "diverges":
                _say_lines(f"{a['axis']}: {a['message']}", "      ")
        _items_line("schedule:  ", rec["schedule"]["items"],
                    lambda i: f"{i['task']} {i['hours']} h {i['day'][5:]}")
        _items_line("tasks.json:", rec["tasks"]["items"],
                    lambda i: f"{i['id']} {i['kind']} {i['hours']} h "
                              f"{i['from'][5:]}")
        if rec["tasks"]["repeats"]:
            _items_line("repeating: ", rec["tasks"]["repeats"],
                        lambda i: f"{i['id']} every {i['every']}")
        print()

    if r["agreements"]:
        print("  Where they agree, which is the whole reason both survive:")
        for a in r["agreements"]:
            _say_lines(f"{a['stage']} {a['axis']}: {a['message']}", "      ")
        print()

    _say_lines("This reports and does not block. lib.schedule is a "
               "feasibility answer derived from a design; tasks.json is what "
               "somebody means to do on a day. Some of the gap above is "
               "legitimate and some is drift, and telling them apart is a "
               "judgement rather than an edit.", "  ")
    print(f"      python3 -m lib.reconcile {slug} --basis    what was and was "
          f"not compared, and why")
    return r


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--basis", action="store_true",
                    help="the declared bridge between the two vocabularies")
    ap.add_argument("--target", help="override the target date")
    ap.add_argument("--hours", type=float, help="hours per weekend")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.basis:
        report_basis()
        return
    if not args.slug:
        print(__doc__)
        return
    if args.json:
        r = compare(args.slug, target=args.target, hours=args.hours)
        print(json.dumps(r, indent=2, default=str))
    else:
        r = report(args.slug, target=args.target, hours=args.hours)
    raise SystemExit(1 if r["findings"] else 0)


if __name__ == "__main__":
    main()
