#!/usr/bin/env python3
"""Prove the build plan reads a stated hours band instead of crashing on it.

    python3 tools/test_schedule.py
    python3 tools/test_schedule.py -v        show every check's detail

`person.hours_per_week` is written two ways across real yards. Some record a
figure. Others record `{"low": 1, "high": 6, "note": "..."}`, because a band is
what somebody actually says about their own Saturdays, and `lib.niches` has read
either shape from the start. `lib.schedule` did not: it passed the value
straight into `entry["hours"] < per_weekend` and died with a TypeError on a
yard whose conditions file was entirely well formed. Nothing caught it because
this module had no tests at all, which is the more useful half of the finding.

What is proved here, and each of these is easy to pass by accident:

  both shapes work     a figure and a band both produce a numeric capacity, so
                       the plan builds either way
  a band is not an end the midpoint is used rather than `low` or `high`. This
                       matters: `low` would stretch this fixture's work over
                       four times as many weekends and `high` would book every
                       weekend at a ceiling the yards that write a band
                       generally reserve for the good ones
  the cap is honoured  no weekend in the plan exceeds the capacity, which is
                       the arithmetic the raw dict used to reach
  --hours still wins   an explicit figure overrides whatever is on file, so the
                       band is a default and not a policy
  junk does not crash  a band with no numbers in it, or no person block at all,
                       falls back rather than raising

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
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


# --------------------------------------------------------------- the fixture

# Enough design to imply real work and no more. Four bare-ground tasks plus
# planting comes to more hours than one weekend holds, which is what makes the
# capacity figure observable in the output rather than merely stored.
DESIGN = {
    "plants": [
        {"name": "autumn sage", "pot_size": "1gal", "role": "filler"},
        {"name": "yaupon", "pot_size": "5gal", "role": "structure"},
    ],
    "hardscape": [],
}

SITE = {
    "address": {"lat": 30.29, "lon": -97.70},
    "climate": {"last_frost": "Feb 20", "first_frost": "Dec 01"},
    "zones": {"bed_a": {"label": "a bed", "area_sqft": 80.0, "kind": "border"}},
}

VISION = {"target_date": "2027-04-10"}


def make_yard(root, hours):
    """A yard whose only interesting property is the shape of its hours."""
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    person = {"experience": "some", "done_before": ["plant", "mulch"]}
    if hours is not None:
        person["hours_per_week"] = hours
    for name, payload in (("design.json", DESIGN), ("site.json", SITE),
                          ("vision.json", VISION),
                          ("conditions.json", {"person": person})):
        with open(os.path.join(d, name), "w") as fh:
            json.dump(payload, fh)
    return d


def build(schedule, root, hours, **kw):
    """A plan for a yard with `hours` on file. The gate is not what is tested.

    `doubts.gate` is stubbed rather than satisfied. Whether the gate holds is
    `test_gate.py`'s job and it tests it against this same module; repeating a
    board and an all-clear here would test that instead of the arithmetic.
    """
    make_yard(root, hours)
    return schedule.build(SLUG, **kw)


# ------------------------------------------------------------------ the checks

def check_shapes(conditions):
    """Every shape the record uses, read straight."""
    cases = [
        ({"low": 1, "high": 6, "note": "fun, so the top is real"}, 3.5,
         "a band with a note reads as its midpoint"),
        ({"low": 2, "high": 4}, 3.0, "a bare band reads as its midpoint"),
        ({"low": 3}, 3.0, "a band with one end reads as that end"),
        ({"value": 2}, 2.0, "the `value` spelling is honoured"),
        (4, 4.0, "a plain integer is a figure"),
        (4.5, 4.5, "a plain float is a figure"),
        ({"note": "no numbers here at all"}, None,
         "a band with no numbers falls back rather than raising"),
        (None, None, "no figure on file falls back"),
    ]
    for shape, want, label in cases:
        got = conditions.weekly_hours(
            {"person": {"hours_per_week": shape}} if shape is not None else {})
        ok(got == want, label, f"{shape!r} gave {got!r}, wanted {want!r}")
    ok(conditions.weekly_hours({}) is None,
       "no person block at all falls back", "an empty conditions file raised")


def check_band_builds(schedule, root):
    """The regression itself: a band used to be a TypeError."""
    try:
        plan = build(schedule, root, {"low": 1, "high": 6, "note": "x"})
    except TypeError as e:
        ok(False, "a stated band builds a plan", f"TypeError: {e}")
        return None
    ok(isinstance(plan.get("hours_per_weekend"), (int, float)),
       "a stated band builds a plan",
       f"hours_per_weekend came out as {plan.get('hours_per_weekend')!r}")
    ok(plan["hours_per_weekend"] == 3.5,
       "1-6 on file is scheduled at 3.5 h a weekend",
       f"got {plan.get('hours_per_weekend')!r}")
    return plan


def check_not_an_end(schedule, root):
    """The midpoint is a choice, so both ends are shown to be worse.

    Reading `low` is not merely pessimistic, which is what it looks like on
    paper. At 1 h a weekend nothing in this fixture fits at all — a task larger
    than the remaining room is only split when at least 2 h of room is left, so
    the queue never empties and the whole plan comes back as a warning. That is
    the concrete argument against the low end, and it is worth a test rather
    than a comment.
    """
    band = build(schedule, root, {"low": 1, "high": 6})
    low = build(schedule, root, 1)
    high = build(schedule, root, 6)

    ok(1 < band["hours_per_weekend"] < 6,
       "a band's capacity lands strictly between its own two ends",
       f"got {band['hours_per_weekend']!r} from a 1-6 band")
    ok(low.get("unscheduled") and low.get("warning"),
       "the low end would not fit the work at all",
       "1 h a weekend placed everything, so the fixture is too small to show "
       "why the low end is the wrong reading")
    ok(not band.get("unscheduled"),
       "the midpoint does fit the work",
       f"{len(band.get('unscheduled') or [])} tasks left over at "
       f"{band['hours_per_weekend']} h a weekend")
    n_band = len([w for w in band["weekends"] if w.get("hours")])
    n_high = len([w for w in high["weekends"] if w.get("hours")])
    ok(n_band > n_high,
       "the midpoint spreads the work over more weekends than the high end",
       f"band {n_band} working weekends, high end {n_high}")


def check_cap_honoured(schedule, root):
    """The comparison the raw dict used to break."""
    plan = build(schedule, root, {"low": 1, "high": 6})
    cap = plan["hours_per_weekend"]
    over = [w for w in plan["weekends"] if w.get("hours", 0) > cap]
    ok(not over, "no weekend is planned over the capacity",
       f"cap {cap} h, but " + ", ".join(
           f"{w['weekend_of']} at {w['hours']} h" for w in over))
    ok(all(isinstance(w.get("hours", 0), (int, float))
           for w in plan["weekends"]),
       "every weekend carries a numeric hour count")


def check_explicit_wins(schedule, root):
    plan = build(schedule, root, {"low": 1, "high": 6}, hours_per_weekend=2)
    ok(plan["hours_per_weekend"] == 2,
       "--hours overrides the band on file",
       f"got {plan['hours_per_weekend']!r}")


def check_junk_builds(schedule, root):
    for hours, label in (({"note": "no numbers"}, "a band with no numbers"),
                         (None, "no hours on file at all")):
        try:
            plan = build(schedule, root, hours)
        except TypeError as e:
            ok(False, f"{label} still builds", f"TypeError: {e}")
            continue
        ok(plan["hours_per_weekend"] == 6,
           f"{label} still builds, on the 6 h fallback",
           f"got {plan.get('hours_per_weekend')!r}")


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yardtest-")
    os.environ["GARDEN_ROOT"] = root
    for mod in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[mod]
    from lib import conditions, doubts, schedule

    doubts.gate = lambda *a, **k: None

    print("lib.schedule — does a stated hours band build a plan\n")
    try:
        print(" the shapes conditions.json actually uses")
        check_shapes(conditions)
        print("\n the regression")
        check_band_builds(schedule, root)
        print("\n the midpoint is a choice, not an accident")
        check_not_an_end(schedule, root)
        print("\n the arithmetic that used to break")
        check_cap_honoured(schedule, root)
        print("\n the overrides")
        check_explicit_wins(schedule, root)
        check_junk_builds(schedule, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nThe build plan is not reading its hours:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
