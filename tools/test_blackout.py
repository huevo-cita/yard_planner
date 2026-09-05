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


def cond_with(blackouts=None, travel=None):
    c = {"person": {"experience": "some", "hours_per_week": 4,
                    "done_before": ["plant", "mulch"],
                    "travel_gaps": travel or []},
         "ground": {"areas": [], "hardscape": []},
         "constraints": {"blackouts": blackouts or []}}
    return c


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

    with open(os.path.join(d, "conditions.json"), "w") as fh:
        json.dump(cond_with(), fh)
    ok(week.blackout_conflicts(SLUG) == [],
       "a yard with no blackout recorded reports nothing",
       "conflicts were reported against a yard that has no blackout")


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
        print("\n the plan honours it")
        check_schedule_honours_it(schedule, root)
        print("\n and honours it where the hours are not counted")
        check_grooming_weekend(schedule, root)
        print("\n without breaking travel")
        check_travel_still_works(schedule, root)
        print("\n what --check reports")
        check_conflicts(week, root)
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
