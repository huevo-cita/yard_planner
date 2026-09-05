#!/usr/bin/env python3
"""Prove a week nobody is available for gets no work put in it.

    python3 tools/test_blackout.py
    python3 tools/test_blackout.py -v        show every check's detail

A yard's record held one date, 13 December, and made it mean three things at
once: the day the garden has to look right, the last day work may run, and the
day the project ends. It is only the first. `lib.schedule` read it as the second
and back-planned into it, which is how the largest planting of an autumn came out
three weeks before the party it was meant to be settled for; and the owner's
actual constraint — that he cannot work the yard at all in the week containing
that date — was in no file, so nothing could honour it.

So `constraints` now carries the three separately: `display_milestone`,
`blackouts`, and `project_end` recorded as an explicit null rather than left
absent, because "we asked and there is no end" and "nobody asked" decide
different things about work after the milestone.

What is proved here, and each of these is easy to pass by accident:

  it is read at all     a blackout with no travel gap beside it still loses the
                        weekend, and the plan says which of the two it was
  the grooming weekend  the last working weekend is placed before any capacity
                        check runs, walking back from the target — so a blackout
                        consulted only when filling hours would still land it
                        inside. This is the check that traps that
  travel still works    the older mechanism is not broken by the newer one
  both ends included    a blackout is inclusive at both ends. An off-by-one here
                        silently books the Monday or the Sunday
  every occurrence      a standing job is reported by the days it actually falls
                        on inside the window, not by its span
  the unit is read      "6 months" is not six days. Reading the number and
                        ignoring the unit puts a twice-yearly gutter clean inside
                        every week anybody asks about
  three-valued end      an absent `project_end` and one recorded as null are
                        different answers, and the difference is whether work
                        after the milestone may be treated as out of scope
  the schema declares   `blank()` creates all three keys. A reader pointed at a
                        key the schema never makes cannot fire on any conformant
                        yard, which is how `constraints.rules` sat dead
  what it bars          "no work at all" turned out to be too strong: the answer
                        was no BUILD work, with keep-alive watering, a contingent
                        freeze response and party-eve setup all standing. A
                        blackout with no `scope` still bars everything; a scoped
                        one bars what it names, permits what it names, and calls
                        anything in neither list unscoped rather than allowed
  and does not suppress a scope narrows the finding, it does not delete it. A
                        digging session inside the week is still a finding, and
                        the eleven permitted jobs are still printed, because
                        eleven jobs nobody looked at and eleven somebody ruled on
                        are indistinguishable if the report is silent

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SLUG = "testyard"

results = []          # (state, label, detail) — state in pass/FAIL
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    print(f"  {'ok  ' if state == 'pass' else 'FAIL'}  {label}")
    if detail and (state != "pass" or verbose):
        for line in str(detail).strip().splitlines():
            print(f"          {line}")


def ok(cond, label, detail=""):
    record("pass" if cond else "FAIL", label, "" if cond else detail)


def D(s):
    return datetime.date.fromisoformat(s)


# --------------------------------------------------------------- the fixture

TARGET = "2027-04-10"          # a Saturday, so the grooming weekend lands on it
BLACKOUT = ("2027-04-05", "2027-04-11")     # the Mon-Sun week containing it

DESIGN = {"plants": [{"name": "autumn sage", "zone": "bed_a", "pot_size": "1gal"}],
          "hardscape": []}
SITE = {"address": {"lat": 30.29, "lon": -97.70},
        "climate": {"last_frost": "Feb 20", "first_frost": "Dec 01"},
        "zones": {"bed_a": {"label": "bed a", "area_sqft": 80.0}}}
VISION = {"target_date": TARGET}


#: A blackout narrowed the way one real yard's owner narrowed his: no BUILD work
#: that week, but watering, a freeze response and setting up for his own party
#: are all fine. `prune` is in neither list on purpose — see `check_scope`.
SCOPE = {"bars": "build work",
         "barred_kinds": ["build", "plant", "sow"],
         "permitted_kinds": ["water", "protect", "event"],
         "permits": ["keep-alive watering", "party-eve setup"],
         "settled": "d37"}


def cond_with(blackouts=None, travel=None):
    c = {"person": {"experience": "some", "hours_per_week": 4,
                    "done_before": ["plant", "mulch"],
                    "travel_gaps": travel or []},
         "ground": {"areas": [], "hardscape": []},
         "constraints": {"blackouts": blackouts or []}}
    return c


def scoped(scope=SCOPE):
    """The week under test, narrowed to bar one kind of work rather than all."""
    return cond_with([{"from": BLACKOUT[0], "to": BLACKOUT[1], "scope": scope}])


def make_yard(root, cond):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    for name, payload in (("design.json", DESIGN), ("site.json", SITE),
                          ("vision.json", VISION), ("conditions.json", cond)):
        with open(os.path.join(d, name), "w") as fh:
            json.dump(payload, fh)


def weekends_in(plan, lo, hi):
    return [w for w in plan["weekends"] if lo <= D(w["weekend_of"]) <= hi]


# ------------------------------------------------------------------ the checks

def check_reader(conditions):
    c = cond_with([{"from": BLACKOUT[0], "to": BLACKOUT[1]}])
    ok(conditions.blackouts(c) == [(D(BLACKOUT[0]), D(BLACKOUT[1]))],
       "a recorded blackout reads back as a pair of dates",
       f"got {conditions.blackouts(c)!r}")

    ok(conditions.in_blackout(c, "2027-04-05") and
       conditions.in_blackout(c, "2027-04-11"),
       "a blackout includes both of its own end days",
       "the Monday or the Sunday fell outside a week that names them")
    ok(not conditions.in_blackout(c, "2027-04-04") and
       not conditions.in_blackout(c, "2027-04-12"),
       "and stops there — the day either side is available",
       "a blackout leaked into the days around it")

    one = conditions.blackouts(cond_with([{"from": "2027-04-05"}]))
    ok(one == [(D("2027-04-05"), D("2027-04-05"))],
       "a blackout with no end is a single day, not an open-ended one",
       f"got {one!r}")
    ok(conditions.blackouts(cond_with([{"note": "no dates at all"}])) == [],
       "a malformed record is dropped rather than raising")
    ok(conditions.blackouts({}) == [],
       "a conditions file with no constraints block does not raise")


def check_scope(conditions):
    """What a blackout bars, once "no work at all" turns out to be too strong.

    The week under test began life as total unavailability and was narrowed by
    the person whose week it is: no BUILD work, but keep-alive watering, a
    contingent freeze response and setting up for his own party all stand. The
    eleven jobs left inside it are then a decision rather than an oversight, and
    the point of these checks is that the difference is legible to a reader who
    was not there — including the reader who is a check.
    """
    total = cond_with([{"from": BLACKOUT[0], "to": BLACKOUT[1]}])
    ok(conditions.blackout_bars(total, "2027-04-07", "build") ==
       conditions.BARRED,
       "a blackout with no scope bars build work")
    ok(conditions.blackout_bars(total, "2027-04-07", "water") ==
       conditions.BARRED,
       "and bars watering too — with nothing recorded it bars everything",
       "silence in the record was read as permission, which is the reading that "
       "lets a narrowing nobody wrote down be assumed")
    ok(conditions.blackout_bars(total, "2027-04-07", None) == conditions.BARRED,
       "and bars a task with no kind at all")

    c = scoped()
    ok(conditions.blackout_bars(c, "2027-04-07", "build") == conditions.BARRED,
       "a scope that bars build work still bars build work",
       "the narrowing suppressed the finding wholesale, so a planting session "
       "inside the week nobody is available for now reports clean")
    ok(conditions.blackout_bars(c, "2027-04-07", "water") ==
       conditions.PERMITTED,
       "and watering inside it is permitted, on the record")
    ok(conditions.blackout_bars(c, "2027-04-07", "prune") ==
       conditions.UNSCOPED,
       "a kind in neither list is unscoped — not quietly permitted",
       "a kind nobody ruled on came back permitted, so the next task kind "
       "somebody invents walks into the week unexamined")
    ok(conditions.blackout_bars(c, "2027-04-07", None) == conditions.UNSCOPED,
       "and a task with no kind is unscoped rather than allowed")

    both = dict(SCOPE, barred_kinds=["build", "water"],
                permitted_kinds=["water"])
    ok(conditions.blackout_bars(cond_with(
        [{"from": BLACKOUT[0], "to": BLACKOUT[1], "scope": both}]),
        "2027-04-07", "water") == conditions.BARRED,
       "a kind listed as both barred and permitted is barred",
       "a record contradicting itself resolved to permission")

    ok(conditions.blackout_bars(c, "2027-04-04", "build") is None,
       "the day before the blackout has no verdict, because it is not in one")
    ok(conditions.blackout_bars(cond_with(), "2027-04-07", "build") is None,
       "and neither does any day on a yard with no blackout recorded")

    rec = conditions.blackout_records(c)
    ok(len(rec) == 1 and rec[0]["scope"]["bars"] == "build work"
       and rec[0]["from"] == D(BLACKOUT[0]),
       "the scope comes back with the record, for whatever has to report it",
       f"got {rec!r}")
    ok(conditions.blackout_records(total)[0]["scope"] is None,
       "and an unscoped blackout reports its scope as None rather than {}",
       "an empty dict is truthy enough to be mistaken for a narrowing")
    ok((conditions.in_blackout(c, "2027-04-07") or {}).get("scope") is not None,
       "in_blackout carries the scope, so one lookup answers both questions")


def check_schema(conditions):
    """The lesson from `constraints.rules`, which no yard ever had."""
    made = conditions.blank(SLUG)["constraints"]
    for key in ("display_milestone", "blackouts", "project_end", "rules"):
        ok(key in made, f"blank() declares constraints.{key}",
           f"a reader of constraints.{key} could never fire on a new yard")


def check_project_end(conditions):
    ok(conditions.project_end(cond_with())["stated"] is False,
       "an absent project_end reads as nobody having been asked",
       "an unrecorded end date was reported as a stated one")

    c = cond_with()
    c["constraints"]["project_end"] = {"date": None, "source": "he said so"}
    end = conditions.project_end(c)
    ok(end["stated"] is True and end["date"] is None,
       "a recorded null reads as a stated answer with no end date",
       f"got {end!r} — this is what stops work after the milestone being "
       f"treated as out of scope")

    c["constraints"]["project_end"] = {"date": "2028-01-01"}
    ok(conditions.project_end(c)["date"] == D("2028-01-01"),
       "a real end date reads back as a date",
       f"got {conditions.project_end(c)!r}")


def check_milestone(conditions):
    c = cond_with()
    c["constraints"]["display_milestone"] = {"date": "2026-12-13",
                                             "kind": "display"}
    ok(conditions.display_milestone(c)["date"] == "2026-12-13",
       "the display milestone reads back")
    ok(conditions.display_milestone(cond_with()) is None,
       "a yard with no milestone recorded returns None rather than raising")


def check_schedule_honours_it(schedule, root):
    """The plan puts nothing in the week, and says which mechanism did it."""
    lo, hi = D(BLACKOUT[0]), D(BLACKOUT[1])

    make_yard(root, cond_with())
    before = schedule.build(SLUG)
    inside = weekends_in(before, lo, hi)
    ok(any(w.get("tasks") or w.get("note") for w in inside),
       "without the blackout the plan does use that weekend",
       "the fixture never puts anything in the week under test, so the check "
       "below would pass whatever the code did")

    make_yard(root, cond_with([{"from": BLACKOUT[0], "to": BLACKOUT[1]}]))
    after = schedule.build(SLUG)
    inside = weekends_in(after, lo, hi)
    ok(inside and not any(w.get("tasks") for w in inside),
       "no weekend inside a blackout carries any task",
       f"still scheduled {[(w['weekend_of'], w.get('tasks')) for w in inside]}")
    ok(any("blacked out" in (w.get("note") or "") for w in inside),
       "the plan says the weekend was lost to a blackout, not to travel",
       f"notes were {[w.get('note') for w in inside]}")

    ok(before["total_hours"] == after["total_hours"],
       "a blackout moves the work, it does not delete it",
       f"{before['total_hours']} h became {after['total_hours']} h")


def check_grooming_weekend(schedule, root):
    """The trap: grooming is placed before any hours are counted.

    `build()` reserves the last working weekend for grooming on the first pass
    of the loop, walking back from the target, and it does that before it ever
    compares hours against capacity. So a blackout honoured only where the hours
    are filled would leave the grooming weekend sitting inside it — three hours
    of work in the week somebody said they were not available.
    """
    lo, hi = D(BLACKOUT[0]), D(BLACKOUT[1])
    make_yard(root, cond_with())
    plain = schedule.build(SLUG)
    groom = [w for w in plain["weekends"]
             if any(t["task"] == "grooming and gap-fill" for t in w["tasks"])]
    ok(groom and lo <= D(groom[0]["weekend_of"]) <= hi,
       "without the blackout the grooming weekend does land inside that week",
       f"grooming was on {groom and groom[0]['weekend_of']}, so this fixture "
       f"does not actually exercise the trap")

    make_yard(root, cond_with([{"from": BLACKOUT[0], "to": BLACKOUT[1]}]))
    plan = schedule.build(SLUG)
    groom = [w for w in plan["weekends"]
             if any(t["task"] == "grooming and gap-fill" for t in w["tasks"])]
    ok(groom, "the grooming weekend still exists",
       "honouring the blackout lost the grooming weekend altogether")
    ok(groom and not (lo <= D(groom[0]["weekend_of"]) <= hi),
       "and it has moved out of the blackout rather than staying in it",
       f"grooming is still on {groom and groom[0]['weekend_of']}, inside "
       f"{BLACKOUT[0]} to {BLACKOUT[1]}")


def check_scoped_schedule(schedule, root):
    """A blackout that bars only build work still empties the weekend here.

    This is the check behind the claim that `_away_ranges` did not need rewiring
    when "no work at all" became "no BUILD work". The claim rests on two facts,
    and both are asserted rather than argued: everything `build()` can put on a
    weekend is build work, so there is nothing for a narrowed blackout to leave
    behind; and keep-alive watering leaves `build()` as an undated regime, so
    emptying a weekend never touches it.

    If someone later teaches this module to place a watering visit or a party
    setup on a dated weekend, the first of these fails and the wiring genuinely
    is wrong. That is the point of pinning it.
    """
    lo, hi = D(BLACKOUT[0]), D(BLACKOUT[1])

    make_yard(root, cond_with())
    before = schedule.build(SLUG)

    make_yard(root, scoped())
    plan = schedule.build(SLUG)
    inside = weekends_in(plan, lo, hi)
    ok(inside and not any(w.get("tasks") for w in inside),
       "a blackout that bars only build work still empties its weekend",
       f"still scheduled {[(w['weekend_of'], w.get('tasks')) for w in inside]} — "
       f"either a non-build task has been added to ORDER, in which case the "
       f"scope has to be honoured task by task, or the blackout stopped being "
       f"read at all")

    placed = {t["task"] for w in before["weekends"] for t in w["tasks"]}
    ok(placed and placed <= set(schedule.ORDER),
       "everything the plan places comes out of ORDER, which is all build work",
       f"{sorted(placed - set(schedule.ORDER))} was placed on a weekend from "
       f"outside the build vocabulary, so 'the blackout bars build work' and "
       f"'the blackout empties the weekend' are no longer the same statement")

    ok(plan.get("establishment_watering") == before.get("establishment_watering"),
       "keep-alive watering survives the blackout, because it carries no dates",
       f"got {plan.get('establishment_watering')!r} — the work the blackout "
       f"explicitly permits was dropped along with the work it bars")

    note = " ".join(w.get("note") or "" for w in inside)
    ok("blacked out" in note,
       "the weekend still reads as blacked out rather than as travel",
       f"note was {note!r}")
    ok("build work" in note and "keep-alive watering" in note,
       "and the note says what the blackout bars and what it permits",
       f"note was {note!r} — a reader auditing the week is told only that "
       f"nothing is scheduled, which is how a decision looks like an omission")

    groom = [w for w in plan["weekends"]
             if any(t["task"] == "grooming and gap-fill" for t in w["tasks"])]
    ok(groom and not (lo <= D(groom[0]["weekend_of"]) <= hi),
       "and grooming-and-gap-fill is still moved out of the week",
       f"grooming is on {groom and groom[0]['weekend_of']}. It reads like the "
       f"party-eve setup the scope permits and it is not: its own note is "
       f"filling gaps with something already in flower, which is planting")


def check_travel_still_works(schedule, root):
    """The older mechanism, which the newer one sits beside rather than on."""
    lo, hi = D(BLACKOUT[0]), D(BLACKOUT[1])
    make_yard(root, cond_with(travel=[{"from": BLACKOUT[0], "to": BLACKOUT[1]}]))
    plan = schedule.build(SLUG)
    inside = weekends_in(plan, lo, hi)
    ok(inside and not any(w.get("tasks") for w in inside),
       "a travel gap still empties its weekend",
       "adding blackouts broke the mechanism that was already there")
    ok(any("away" in (w.get("note") or "") for w in inside),
       "and a travel gap still reads as away, not as blacked out",
       f"notes were {[w.get('note') for w in inside]}")


def check_conflicts(week, root):
    """What `--check` reports: the days, not the spans."""
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "conditions.json"), "w") as fh:
        json.dump(cond_with([{"from": "2026-12-07", "to": "2026-12-13"}]), fh)
    tasks = {"yard": SLUG, "tasks": [
        {"id": "t01", "date": "2026-12-09", "minutes": 20, "critical": True,
         "title": "inside, on a day"},
        {"id": "t02", "date": "2026-12-05", "minutes": 20,
         "title": "outside, two days before"},
        {"id": "t03", "date": "2026-11-07", "minutes": 5, "title": "every 2 days",
         "repeat": {"every": "2 days", "from": "2026-11-07", "to": "2026-12-13"}},
        {"id": "t04", "date": "2026-11-16", "minutes": 20,
         "title": "twice a year",
         "repeat": {"every": "6 months", "from": "2026-11-16",
                    "to": "2027-04-30"}},
        {"id": "t05", "window": ["2026-12-07", "2026-12-11"], "minutes": 15,
         "title": "a window inside it"},
        {"id": "t06", "window": ["2026-11-01", "2026-11-20"], "minutes": 15,
         "title": "a window outside it"},
    ], "shopping": [], "sources": {}}
    with open(os.path.join(d, "tasks.json"), "w") as fh:
        json.dump(tasks, fh)

    found = {c["id"]: c for c in week.blackout_conflicts(SLUG)}
    ok(set(found) == {"t01", "t03", "t05"},
       "exactly the tasks that ask for work inside the window are reported",
       f"got {sorted(found)}, wanted t01, t03, t05")
    ok(found.get("t01", {}).get("critical") is True,
       "a critical task inside a blackout is marked as one")
    ok(found.get("t03", {}).get("dates") ==
       ["2026-12-07", "2026-12-09", "2026-12-11", "2026-12-13"],
       "a standing job is reported by each occurrence, not by its span",
       f"got {found.get('t03', {}).get('dates')!r}")
    ok("t04" not in found,
       "a job repeating every 6 months does not land in a week in December",
       "the cadence's unit was ignored and 6 months was read as 6 days, which "
       "puts a twice-yearly job inside every window anybody asks about")

    ok(all(c["verdict"] == "barred" for c in week.blackout_conflicts(SLUG)),
       "with no scope recorded every one of them is barred",
       f"got {[(c['id'], c['verdict']) for c in week.blackout_conflicts(SLUG)]}")

    with open(os.path.join(d, "conditions.json"), "w") as fh:
        json.dump(cond_with(), fh)
    ok(week.blackout_conflicts(SLUG) == [],
       "a yard with no blackout recorded reports nothing",
       "conflicts were reported against a yard that has no blackout")


def check_scoped_conflicts(week, conditions, root):
    """What `--check` says once the blackout says what it bars.

    The failure this guards is the obvious over-correction: recording that the
    week permits watering, and thereby quietly permitting the digging session
    that is also in it.
    """
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    scope = dict(SCOPE)
    with open(os.path.join(d, "conditions.json"), "w") as fh:
        json.dump(cond_with([{"from": "2026-12-07", "to": "2026-12-13",
                              "scope": scope}]), fh)
    tasks = {"yard": SLUG, "tasks": [
        {"id": "t01", "date": "2026-12-09", "minutes": 20, "kind": "water",
         "title": "establishment watering", "critical": True},
        {"id": "t02", "date": "2026-12-12", "minutes": 120, "kind": "event",
         "title": "the party"},
        {"id": "t03", "date": "2026-12-10", "minutes": 240, "kind": "build",
         "title": "dig and edge the west bed"},
        {"id": "t04", "date": "2026-12-11", "minutes": 30, "kind": "harvest",
         "title": "pick the last of the lettuce"},
        {"id": "t05", "date": "2026-12-08", "minutes": 15,
         "title": "a task with no kind"},
        {"id": "t06", "window": ["2026-11-20", "2026-12-09"], "minutes": 90,
         "kind": "plant", "title": "a planting window reaching into the week"},
    ], "shopping": [], "sources": {}}
    with open(os.path.join(d, "tasks.json"), "w") as fh:
        json.dump(tasks, fh)

    found = {c["id"]: c for c in week.blackout_conflicts(SLUG)}
    ok(set(found) == {"t01", "t02", "t03", "t04", "t05", "t06"},
       "every task inside the week is still returned, scope or no scope",
       f"got {sorted(found)} — a permitted task that disappears from the report "
       f"makes 'nothing is in that week' and 'everything in it was ruled on' "
       f"look the same from outside")
    ok(found["t03"]["verdict"] == conditions.BARRED,
       "the digging session inside the week is barred",
       "a blackout containing build work stopped being a finding, which is the "
       "whole thing the scope was not supposed to do")
    ok(found["t01"]["verdict"] == conditions.PERMITTED
       and found["t02"]["verdict"] == conditions.PERMITTED,
       "the watering and the party are permitted")
    ok(found["t04"]["verdict"] == conditions.UNSCOPED
       and found["t05"]["verdict"] == conditions.UNSCOPED,
       "harvesting and a task with no kind are unscoped, and get asked about",
       f"got {found['t04']['verdict']} and {found['t05']['verdict']}")
    ok(found["t06"]["verdict"] == conditions.BARRED
       and found["t06"]["dates"] == ["2026-12-07"],
       "a window reaching into the week is judged on the day inside it",
       f"got {found['t06']['verdict']} on {found['t06']['dates']} — the "
       f"window's own start is 20 November, which is outside the blackout and "
       f"has no verdict at all")
    ok("bars build work" in found["t03"]["blackout"],
       "and each one carries the sentence naming what its blackout bars",
       f"got {found['t03']['blackout']!r}")


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yardtest-")
    os.environ["GARDEN_ROOT"] = root
    for mod in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[mod]
    from lib import conditions, doubts, schedule, week

    doubts.gate = lambda *a, **k: None

    print("a week nobody is available for — is any work put in it\n")
    try:
        print(" the record")
        check_reader(conditions)
        print("\n the schema declares what the readers read")
        check_schema(conditions)
        print("\n three meanings, kept apart")
        check_project_end(conditions)
        check_milestone(conditions)
        print("\n what the blackout bars, and what it says may still happen")
        check_scope(conditions)
        print("\n the plan honours it")
        check_schedule_honours_it(schedule, root)
        print("\n and honours it where the hours are not counted")
        check_grooming_weekend(schedule, root)
        print("\n and honours a narrowed one for the right reason")
        check_scoped_schedule(schedule, root)
        print("\n without breaking travel")
        check_travel_still_works(schedule, root)
        print("\n what --check reports")
        check_conflicts(week, root)
        print("\n and what it reports once the blackout has a scope")
        check_scoped_conflicts(week, conditions, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nWork is being planned into a week nobody is available for:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
