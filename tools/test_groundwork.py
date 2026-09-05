#!/usr/bin/env python3
"""Prove a bed that already exists is not dug, edged and tilled a second time.

    python3 tools/test_groundwork.py
    python3 tools/test_groundwork.py -v        show every check's detail

`lib.schedule` decides whether to schedule groundwork by asking
`_target_zones_established`, which reads `conditions.ground.areas`. One real yard
recorded ten built features under `ground.already_built` — a spelling it invented
and nothing reads — so `areas` was empty, an empty `areas` read as a bare lot, and
the plan billed twelve of its twenty-three hours to measure out, dig, edge and
till four beds that were already dug, edged and planted. Nobody noticed, because
a plan that says "dig and edge a bed (6 h)" looks exactly like a plan.

The fix was to move that yard's records onto the declared schema rather than
teach the schedule a second key name, and the argument for it is testable: an
`areas` entry turns on its `state`, which `already_built` entries do not carry,
so a fallback read would have to infer "edged" from the sentence "Four in-ground
beds, all edged". What replaces the fallback is a detector, and the detector is
the half most worth testing, because it is the half that has to fire on the
*next* yard.

What is proved here, and each of these is easy to pass by accident:

  the regression        beds recorded under `areas` with a worked state draw no
                        groundwork at all, and the hours drop by exactly the
                        groundwork
  it is the state,      an area whose state is not a worked one still draws the
  not the presence      groundwork. A fix that suppressed work whenever `areas`
                        was non-empty would pass the check above and be wrong
  silence is named      a yard with facts under a key nothing reads gets a bare
                        lot plan AND a warning naming the key and the count.
                        This is the one that would have caught the original
  no crying wolf        a yard that really is a bare lot gets no such warning,
                        because a detector that fires on every empty yard is one
                        somebody switches off inside a week
  prose is not a fact   a note, a status string and a tombstoned `null` are not
                        records, and flagging them would make the detector
                        useless on the very yard that has just been migrated

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

# Two beds and enough plants to imply real planting. No hardscape and no raised
# bed, so the only tasks in play are the four groundwork ones and the four that
# happen whether or not the ground is broken — which keeps the arithmetic
# legible when a total moves.
DESIGN = {
    "plants": [
        {"name": "autumn sage", "zone": "bed_a", "pot_size": "1gal"},
        {"name": "blackfoot daisy", "zone": "bed_b", "pot_size": "1gal"},
    ],
    "hardscape": [],
}

SITE = {
    "address": {"lat": 30.29, "lon": -97.70},
    "climate": {"last_frost": "Feb 20", "first_frost": "Dec 01"},
    "zones": {"bed_a": {"label": "bed a, rear wall", "area_sqft": 80.0},
              "bed_b": {"label": "bed b, west wall", "area_sqft": 40.0}},
}

VISION = {"target_date": "2027-04-10"}

#: The four tasks that exist only because the ground is assumed to be bare.
GROUNDWORK = ("measure and mark out", "kill turf", "dig and edge a bed",
              "amend and till")

#: What the yard looks like once the beds are on the schema.
ON_SCHEMA = [
    {"name": "bed a, rear wall", "state": "dug and edged"},
    {"name": "bed b, west wall", "state": "dug and edged"},
]

#: What it looked like before: the same ten facts, under a key nothing reads.
OFF_SCHEMA = [
    {"what": "Two in-ground beds, all edged",
     "detail": "bed a 232x51 in along the rear wall; bed b 85x28 in, west wall"},
    {"what": "Paver path", "detail": "around the beds"},
]


def make_yard(root, ground, water=None):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    cond = {"person": {"experience": "some", "hours_per_week": 4,
                       "done_before": ["plant", "mulch", "edge a bed"]},
            "water": {"irrigation": water or {"kind": "drip"}},
            "ground": ground}
    for name, payload in (("design.json", DESIGN), ("site.json", SITE),
                          ("vision.json", VISION), ("conditions.json", cond)):
        with open(os.path.join(d, name), "w") as fh:
            json.dump(payload, fh)
    return cond


def hours_for(schedule, root, ground):
    make_yard(root, ground)
    tasks = schedule.tasks_from_design(SLUG)
    return {t["task"]: t["hours"] for t in tasks}


# ------------------------------------------------------------------ the checks

def check_regression(schedule, root):
    """A bed on the schema is not dug twice, and a bare lot still is."""
    bare = hours_for(schedule, root, {"areas": [], "hardscape": []})
    built = hours_for(schedule, root, {"areas": ON_SCHEMA, "hardscape": []})

    drew = [t for t in GROUNDWORK if t in bare]
    ok(drew, "a bare lot draws groundwork, so the fixture can show it going",
       f"a yard with no areas drew none of {GROUNDWORK}")
    ok(not [t for t in GROUNDWORK if t in built],
       "a yard whose beds are recorded as dug and edged draws no groundwork",
       f"still drew {[t for t in GROUNDWORK if t in built]}")

    went = sum(bare[t] for t in drew)
    ok(sum(bare.values()) - sum(built.values()) == went,
       "the hours that go are exactly the groundwork, and nothing else moved",
       f"total fell by {sum(bare.values()) - sum(built.values())} h, "
       f"groundwork was {went} h; the rest of the plan should be untouched")
    ok(sum(built.values()) > 0 and "plant perennials" in built,
       "the planting itself survives — this suppresses groundwork, not work",
       f"built plan came out as {built}")


def check_state_not_presence(schedule, root):
    """The state is the gate. A non-empty `areas` is not on its own an answer.

    This is the check that separates the real fix from the cheap one. Deciding
    on `if areas:` would pass every check above, and would then read a bed
    somebody has only marked out on paper as a bed that is ready to plant into.
    """
    planned = hours_for(schedule, root, {
        "areas": [{"name": "bed a, rear wall", "state": "planned on paper"},
                  {"name": "bed b, west wall", "state": "planned on paper"}]})
    ok([t for t in GROUNDWORK if t in planned],
       "an area whose state is not a worked one still draws the groundwork",
       "a bed in the `areas` list but not yet dug was treated as ready")

    half = hours_for(schedule, root, {
        "areas": [ON_SCHEMA[0], {"name": "bed b, west wall", "state": "turf"}]})
    ok([t for t in GROUNDWORK if t in half],
       "one bed still to dig is enough to keep the groundwork on the plan",
       "a yard where only one of two target beds is worked was treated as done")


def check_detector(conditions, root):
    """The half that has to fire on the next yard."""
    stray = conditions.unread_ground(
        {"ground": {"areas": [], "already_built": OFF_SCHEMA}})
    ok([s["key"] for s in stray] == ["already_built"],
       "a list of ground records under an undeclared key is named",
       f"got {stray!r}")
    ok(stray and stray[0]["count"] == len(OFF_SCHEMA),
       "the detector says how many records are stranded",
       f"got {stray!r}")

    ok(not conditions.unread_ground({"ground": {"areas": [], "hardscape": []}}),
       "a yard that really is a bare lot is not flagged",
       "the detector fired on an empty but perfectly conformant ground record")
    ok(not conditions.unread_ground({"ground": {"areas": ON_SCHEMA}}),
       "a yard on the schema is not flagged",
       "the detector fired on a migrated yard")
    ok(not conditions.unread_ground({}),
       "a conditions file with no ground block at all does not raise")


def check_prose_is_not_a_fact(conditions):
    """A migrated yard keeps a note and a tombstone, and must stay clean.

    The migration leaves `already_built: None` behind on purpose, so a reader who
    remembers the key is told where its contents went. A detector that flagged
    that would fire forever on the one yard that has already been fixed, which is
    the fastest way to get a check ignored.
    """
    migrated = {"ground": {
        "areas": ON_SCHEMA, "hardscape": [],
        "status": "MEASURED on the site walk",
        "note": "substantially more is already built than a bare lot would be",
        "already_built": None,
        "already_built_note": "retired; its content is under areas and hardscape",
    }}
    ok(not conditions.unread_ground(migrated),
       "notes, status strings and a tombstoned key are not stranded facts",
       f"got {conditions.unread_ground(migrated)!r}")

    ok(not conditions.unread_ground({"ground": {"areas": [], "junk": []}}),
       "an empty list under an undeclared key is not a stranded fact",
       "an empty list was reported as records nobody reads")
    ok(not conditions.unread_ground(
        {"ground": {"areas": [], "sizes": [1, 2, 3]}}),
       "a list of numbers is not a list of records",
       "a bare list of scalars was reported as stranded records")


def check_plan_says_so(schedule, root):
    """The warning reaches the plan, with the key and the hours in it."""
    make_yard(root, {"areas": [], "already_built": OFF_SCHEMA})
    plan = schedule.build(SLUG)
    said = plan.get("ground_unread") or ""
    ok(said, "a plan drawn over an unread ground record says so",
       "build() returned no ground_unread on a yard with stranded ground facts")
    ok("already_built" in said, "the warning names the key",
       f"warning was: {said!r}")
    ok("areas" in said, "the warning names where the records have to go",
       f"warning was: {said!r}")

    make_yard(root, {"areas": ON_SCHEMA, "hardscape": []})
    ok(not schedule.build(SLUG).get("ground_unread"),
       "a migrated yard's plan carries no warning",
       "the warning survived the migration it was asking for")

    make_yard(root, {"areas": [], "hardscape": []})
    ok(not schedule.build(SLUG).get("ground_unread"),
       "a genuine bare lot draws groundwork with no warning attached",
       "the warning fired on a yard that has nothing recorded anywhere, which "
       "would make it noise on every new yard in the system")


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

    print("lib.schedule — is a bed that already exists dug a second time\n")
    try:
        print(" the regression")
        check_regression(schedule, root)
        print("\n the state is the gate, not the presence of a row")
        check_state_not_presence(schedule, root)
        print("\n the detector, which is what catches the next yard")
        check_detector(conditions, root)
        print("\n and what it must not flag")
        check_prose_is_not_a_fact(conditions)
        print("\n the warning reaches the plan")
        check_plan_says_so(schedule, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nGroundwork is being planned over ground that is already worked:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
