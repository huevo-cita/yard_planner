#!/usr/bin/env python3
"""Prove the reconciliation catches the divergence it was built for.

    python3 tools/test_reconcile.py
    python3 tools/test_reconcile.py -v        show every check's detail

`lib.schedule` derives a build from `design.json` and the hours on file.
`tasks.json` holds what somebody means to do on a day. Neither reads the other,
and for as long as that was true and nothing compared them, one of them put the
autumn's largest planting a month off the other and nothing anywhere noticed.

`lib.reconcile` is the thing that compares them. The acceptance test for it is
that specific historical failure, reconstructed from the figures the doubt card
d36 recorded at the time, and it is the first section below. A check that cannot
catch the bug it was written for is decorative, and the way to know is to point
it at the bug.

What is proved here

  the bridge holds      every entry in `schedule.ORDER` belongs to exactly one
                        stage, and a kind a yard uses that nobody has declared
                        is a finding rather than a silent omission
  the original bug      on the reconstructed October-against-November yard, the
                        planting stage diverges by three weekends and the
                        report names the 4.5 h job on 17 October that the
                        schedule has nothing against
  timing earns its keep the same divergence fires on a yard where the two sides
                        agree on hours to the minute. Totals alone would have
                        called that yard clean
  presence is loudest   work on one side and none on the other is reported as
                        such, naming which side is empty
  the asymmetry is declared, not tolerated
                        a hundred hours of pruning changes no total and raises
                        no finding, because `prune` is in `OUTSIDE` with a
                        reason. A kind in none of the three lists does raise one
  the resolution is read, not tuned
                        the hours threshold is one weekend of the yard's own
                        capacity, so the same difference is a finding on a
                        3.5 h yard and agreement on a 12 h one
  the gate still holds  a yard whose board is not clear for `schedule` gives a
                        `blocked` finding, and `build()` is not forced past it
  the pipeline is not inverted
                        `lib/schedule.py` names neither `tasks.json` nor
                        `lib.week`. This is the guarantee that makes agreement
                        between the two worth anything, and it is cheap to lose
                        by accident, so it is asserted on the source

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


# --------------------------------------------------------------- the fixtures

TARGET = "2026-12-13"

#: The planting cloverleaf-austin's tasks.json actually holds before the target,
#: verbatim from the record: id, kind, date and minutes. Reconstructed rather
#: than invented, because the divergence being tested for is a property of these
#: dates and a fixture with made-up ones would prove nothing about it.
#:
#: 1160 minutes over sixteen jobs, opening on 1 September with a tray sown
#: indoors and passing half its hours on 18 October. The 4.5 h "Plant g02" on
#: 17 October is the autumn's single biggest planting job and the one the
#: original finding was about.
REAL_PLANTING = [
    ("t004", "sow", "2026-09-01", 30, "Sow lettuce and calendula indoors"),
    ("t011", "transplant", "2026-09-05", 30, "Plant one broccoli into Row 1-W1"),
    ("t016", "sow", "2026-09-19", 45, "Direct-sow carrots"),
    ("t018", "sow", "2026-09-19", 20, "Sow the second tray"),
    ("t021", "transplant", "2026-09-26", 120, "The big transplant session"),
    ("t027", "sow", "2026-10-03", 20, "Sow the first radish"),
    ("t029", "sow", "2026-10-07", 25, "Sow cilantro and dill"),
    ("t033", "plant", "2026-10-17", 270, "Plant g02"),
    ("t035", "sow", "2026-10-18", 45, "The ideal-soil sowing session"),
    ("t032", "plant", "2026-10-24", 60, "Plant the Carex along the new band"),
    ("t036", "plant", "2026-10-24", 230, "Plant g03, and g01 and g04's perennials"),
    ("t037", "plant", "2026-10-25", 25, "Plant the garlic"),
    ("t041", "plant", "2026-10-31", 150, "Pot up the December containers"),
    ("t043", "sow", "2026-11-01", 25, "The last sowing that counts"),
    ("t057", "plant", "2026-11-28", 45, "Plant the annuals into the gaps"),
    ("t058", "plant", "2026-11-28", 20, "Plant the violas in the raised bed"),
]


def task(tid, kind, date, minutes, title, **kw):
    return dict({"id": tid, "kind": kind, "date": date, "minutes": minutes,
                 "title": title, "done": False}, **kw)


def real_planting_tasks():
    return [task(*row) for row in REAL_PLANTING]


def make_yard(root, slug, tasks, established=True, hours=3.5,
              target=TARGET, hardscape=None, plants=None):
    """A yard with just enough design to imply work, and a stated tasks.json.

    `established=False` reproduces the state cloverleaf-austin was in when the
    divergence was found: the built ground recorded under `ground.already_built`,
    a key `lib.schedule` never reads, so `build()` draws a bare-lot plan with
    twelve hours of groundwork over beds that were already dug.
    """
    d = os.path.join(root, slug)
    os.makedirs(d, exist_ok=True)
    ground = ({"areas": [{"name": "g02, the back border", "state": "planted"}],
               "hardscape": [], "surface_note": ""} if established else
              {"areas": [], "hardscape": [],
               "already_built": [{"name": "g02 back border",
                                  "note": "dug, edged, planted"}]})
    payload = {
        "design.json": {"plants": plants or [
            {"name": "autumn sage", "pot_size": "1gal", "role": "filler",
             "zone": "bed_g02"}],
            "hardscape": hardscape or []},
        "site.json": {
            "address": {"lat": 30.29, "lon": -97.70},
            "climate": {"local": {"last_spring_frost": "2027-02-28",
                                  "first_fall_frost": "2026-11-30"}},
            "zones": {"bed_g02": {"label": "g02, the back border"}}},
        "vision.json": {"target_date": {"date": target}},
        "conditions.json": {
            "person": {"hours_per_week": hours},
            "ground": ground,
            "water": {"irrigation": {"kind": "drip"}},
            "constraints": {"rules": [], "blackouts": [
                {"from": "2026-12-07", "to": "2026-12-13", "kind": "no-build",
                 "scope": {"bars": "build work",
                           "barred_kinds": ["build", "plant", "sow",
                                            "transplant"],
                           "permitted_kinds": ["water", "tidy", "event"],
                           "permits": ["keep-alive watering"]}}]}},
        "tasks.json": {"yard": slug, "schema_version": 1, "sources": {},
                       "shopping": [], "tasks": tasks},
    }
    for name, body in payload.items():
        with open(os.path.join(d, name), "w") as fh:
            json.dump(body, fh)
    return slug


def stage(r, name):
    return next((s for s in r["stages"] if s["stage"] == name), None)


def finding(r, kind, stage_name=None):
    for f in r["findings"]:
        if f["kind"] == kind and (stage_name is None
                                 or f.get("stage") == stage_name):
            return f
    return None


# ------------------------------------------------- the bug this was built for

def check_the_original_bug(reconcile, root):
    """The acceptance test: October in tasks.json against November in the plan.

    The historical inputs, from d36's own record of them — `ground.already_built`
    so `build()` reads a bare lot and yields 23 hours, 3.5 hours a weekend, the
    13 December display date — against the sixteen real planting jobs.
    """
    slug = make_yard(root, "origbug", real_planting_tasks(), established=False)
    r = reconcile.compare(slug)

    p = stage(r, "planting")
    ok(p is not None and p["schedule"]["hours"] == 4.0,
       "the reconstruction reproduces build()'s 4 h of planting",
       f"got {p and p['schedule']['hours']}")
    ok(r["schedule"]["total_hours"] == 23,
       "the reconstruction reproduces the 23 h bare-lot plan d36 recorded",
       f"got {r['schedule']['total_hours']} h")

    f = finding(r, "diverges", "planting")
    ok(f is not None,
       "THE CHECK FIRES on the planting stage",
       "no divergence reported on planting — the reconciliation would not have "
       "caught the failure it was written for, and is decorative")
    if not f:
        return

    timing = next((a for a in f["axes"] if a["axis"] == "timing"), None)
    ok(timing is not None and timing["verdict"] == "diverges",
       "it fires on the timing axis, which is the axis the bug lived on",
       f"timing axis came back {timing and timing['verdict']}")
    gap = abs(timing["gaps"]["bulk"]) if timing else 0
    ok(gap >= 21,
       "the divergence it measures is three weekends or more",
       f"the bulk of the planting is {gap} days apart, which is inside the "
       f"three weekends this was supposed to catch")
    record("pass" if gap >= 21 else "FAIL",
           f"measured divergence: {gap} days, bulk to bulk "
           f"({r and stage(r, 'planting')['schedule']['bulk']} on the schedule, "
           f"{stage(r, 'planting')['tasks']['bulk']} in tasks.json)",
           f"{gap} days")

    ids = [i["id"] for i in f["tasks"]["items"]]
    ok("t033" in ids,
       "the report names t033, the 4.5 h job the finding was about",
       f"tasks side listed {ids}")
    biggest = max(f["tasks"]["items"], key=lambda i: i["hours"])
    ok(biggest["id"] == "t033" and biggest["from"] == "2026-10-17",
       "and t033 is the biggest planting job on the tasks side, on 17 October",
       f"biggest was {biggest}")
    ok(f["schedule"]["opens"] > "2026-11-01",
       "while the schedule opens its planting in November",
       f"schedule opened planting {f['schedule']['opens']}")

    # The second half of the original finding: twelve hours of groundwork over
    # beds that already existed.
    st = stage(r, "structure")
    ok(st and st["kind"] == "absent" and st["schedule"]["hours"] == 12.0,
       "and the 12 h of phantom groundwork is reported as work only one side has",
       f"structure came back {st and st['kind']} with "
       f"{st and st['schedule']['hours']} h on the schedule")


def check_totals_would_not_have(reconcile, root):
    """The proof the timing axis is load-bearing rather than decorative.

    A yard where the two sides agree on how much planting there is, to the
    minute, and disagree by a month about when. A reconciliation that compared
    only totals would call this clean, which is why it compares three things.
    """
    tasks = [task("t1", "plant", "2026-10-17", 240, "Plant g02")]
    slug = make_yard(root, "agreehours", tasks)
    r = reconcile.compare(slug)
    p = stage(r, "planting")
    ok(p["schedule"]["hours"] == p["tasks"]["hours"] == 4.0,
       "a yard where both sides hold exactly 4 h of planting",
       f"{p['schedule']['hours']} h against {p['tasks']['hours']} h")
    hours_axis = next(a for a in p["axes"] if a["axis"] == "hours")
    ok(hours_axis["verdict"] == "agrees",
       "the hours axis calls that agreement, correctly",
       f"got {hours_axis['verdict']}")
    ok(p["kind"] == "diverges" and finding(r, "diverges", "planting"),
       "and the stage is still a finding, because the timing diverges",
       "the two agree on hours and are a month apart on dates, and this was "
       "reported as clean. Totals-only reconciliation is what that is")
    timing = next(a for a in p["axes"] if a["axis"] == "timing")
    ok(abs(timing["gaps"]["bulk"]) >= 21,
       "by three weekends or more",
       f"{abs(timing['gaps']['bulk'])} days")


# ------------------------------------------------------------------ the bridge

def check_bridge(reconcile, schedule_mod):
    b = reconcile.basis()
    ok(not b["orphan_archetypes"],
       "every entry in schedule.ORDER belongs to a stage",
       f"in ORDER and in no stage: {b['orphan_archetypes']}")
    ok(not b["double_claimed"],
       "no archetype is claimed by two stages, so nothing is counted twice",
       f"claimed twice: {b['double_claimed']}")
    ok(not b["phantom_archetypes"],
       "no stage claims an archetype ORDER no longer holds",
       f"claimed and gone: {b['phantom_archetypes']}")
    ok(len(schedule_mod.ORDER) == sum(len(s["archetypes"])
                                      for s in reconcile.STAGES),
       f"all {len(schedule_mod.ORDER)} archetypes are accounted for once",
       f"ORDER has {len(schedule_mod.ORDER)}, the stages claim "
       f"{sum(len(s['archetypes']) for s in reconcile.STAGES)}")

    staged = {k for s in reconcile.STAGES for k in s["kinds"]}
    overlap = (staged & set(reconcile.OUTSIDE)) | \
              (staged & set(reconcile.UNASSIGNED)) | \
              (set(reconcile.OUTSIDE) & set(reconcile.UNASSIGNED))
    ok(not overlap,
       "no task kind is in two of the three declarations",
       f"in more than one list: {sorted(overlap)}")
    ok(all(len(v) >= 20 for v in reconcile.OUTSIDE.values()),
       "every excluded kind carries a reason somebody could argue with",
       f"too short to disagree with: "
       f"{[k for k, v in reconcile.OUTSIDE.items() if len(v) < 20]}")


def check_undeclared_kind(reconcile, root):
    """Silence about a kind of work is not permission to leave it out."""
    tasks = real_planting_tasks() + [
        task("t9", "hauling", "2026-10-03", 300, "Barrow the soil round")]
    slug = make_yard(root, "newkind", tasks)
    r = reconcile.compare(slug)
    f = finding(r, "unmapped-kind")
    ok(f is not None and f["subject"] == "hauling",
       "a kind the bridge has never heard of is a finding, not a silent drop",
       f"found {f and f.get('subject')} — 5 h of work fell out of every total "
       f"and nothing said so")
    ok(f is not None and "no total" in f["message"],
       "and the finding says the hours are in no total",
       f"message was {f and f['message']!r}")


def check_no_kind(reconcile, root):
    tasks = real_planting_tasks() + [
        {"id": "t9", "date": "2026-10-03", "minutes": 60, "title": "Something"}]
    slug = make_yard(root, "nokind", tasks)
    f = finding(reconcile.compare(slug), "unmapped-kind")
    ok(f is not None and f["subject"] == "(no kind)",
       "a task with no kind at all is reported",
       f"got {f and f.get('subject')}")


# --------------------------------------------------- presence, hours, timing

def check_presence(reconcile, root):
    """Work one side does not know exists, in both directions."""
    slug = make_yard(root, "onlytasks", real_planting_tasks() + [
        task("t9", "build", "2026-10-10", 270, "Build the g03 river rock band")])
    f = finding(reconcile.compare(slug), "absent", "structure")
    ok(f is not None,
       "structure work in tasks.json and none in the plan is reported",
       "4.5 h of dated building was invisible to the reconciliation")
    ok(f is not None and "the schedule has none at all" in f["message"],
       "and the finding names which side is empty",
       f"message was {f and f['message']!r}")

    # And the other way: an established yard plans aftercare that tasks.json
    # has no dated equivalent for.
    slug = make_yard(root, "onlysched", [
        task("t1", "plant", "2026-11-14", 240, "Plant g02")])
    f = finding(reconcile.compare(slug), "absent", "aftercare")
    ok(f is not None and "the schedule holds" in f["message"],
       "and aftercare in the plan with none in tasks.json is reported the "
       "other way round",
       f"message was {f and f['message']!r}")


def check_resolution_is_read(reconcile, root):
    """One weekend of the yard's own capacity, not a number somebody picked.

    The same 4 h difference in the same two files: a finding on a yard with 3.5
    hour weekends and agreement on one with 12 hour weekends, because on the
    second it is a third of a weekend and the plan cannot resolve it.
    """
    tasks = [task("t1", "plant", "2026-11-14", 480, "Plant everything")]
    tight = make_yard(root, "tight", tasks, hours=3.5)
    loose = make_yard(root, "loose", tasks, hours=12)

    a = next(x for x in stage(reconcile.compare(tight), "planting")["axes"]
             if x["axis"] == "hours")
    b = next(x for x in stage(reconcile.compare(loose), "planting")["axes"]
             if x["axis"] == "hours")
    ok(a["verdict"] == "diverges",
       "4 h apart is a finding on a yard that has 3.5 h weekends",
       f"got {a['verdict']}: {a['message']}")
    ok(b["verdict"] == "agrees",
       "and agreement on one that has 12 h weekends, so the threshold is the "
       "plan's own resolution rather than a tuned tolerance",
       f"got {b['verdict']}: {b['message']}")


def check_timing_resolution(reconcile, root):
    """A week apart is the same week to a plan that places work in weekends."""
    close = [task("t1", "plant", "2026-11-15", 240, "Plant g02")]
    slug = make_yard(root, "closedates", close)
    p = stage(reconcile.compare(slug), "planting")
    timing = next(a for a in p["axes"] if a["axis"] == "timing")
    ok(timing["verdict"] == "agrees",
       "a date one day off the weekend the plan chose is agreement",
       f"got {timing['verdict']} on a {timing['gaps']['bulk']}-day gap")
    ok(p["kind"] == "agrees" and not finding(reconcile.compare(slug),
                                             "diverges", "planting"),
       "and that stage is not a finding at all",
       f"stage came back {p['kind']}")


def check_bulk_not_the_ends(reconcile, root):
    """`opens` is moved by one small job; the verdict is not.

    A single tray sown indoors on 1 September against a planting the plan puts
    in mid-November opens the stage seventy-odd days apart, and says nothing
    about where the work is. The verdict has to come off the bulk or this check
    fires on every yard that starts seed early.
    """
    tasks = [task("t0", "sow", "2026-09-01", 5, "Sow one tray indoors"),
             task("t1", "plant", "2026-11-14", 240, "Plant g02")]
    slug = make_yard(root, "earlytray", tasks)
    p = stage(reconcile.compare(slug), "planting")
    timing = next(a for a in p["axes"] if a["axis"] == "timing")
    ok(abs(timing["gaps"]["opens"]) > 60,
       "the fixture does open the stage more than two months apart",
       f"opens gap was {timing['gaps']['opens']} days")
    ok(timing["verdict"] == "agrees",
       "and the verdict is still agreement, because the bulk lands together",
       f"got {timing['verdict']} — the check is firing on the smallest job at "
       f"the front, which it will do on every yard that sows early")
    ok("opens it 1 Sep" in timing["message"],
       "the report still states the two-month gap at the front",
       f"message was {timing['message']!r}")


# ------------------------------------------- the asymmetry, declared not hidden

def check_declared_asymmetry(reconcile, root):
    """A hundred hours of work build() has no concept of moves nothing."""
    base = make_yard(root, "nopruning", real_planting_tasks())
    clean = reconcile.compare(base)
    loud = make_yard(root, "pruning", real_planting_tasks() + [
        task("t9", "prune", "2026-10-03", 3000, "Prune everything, twice"),
        task("t8", "inspect", "2026-10-04", 3000, "Look at it all day"),
        task("t7", "buy", "2026-10-05", 3000, "Buy the entire nursery")])
    noisy = reconcile.compare(loud)
    ok([f["kind"] for f in clean["findings"]] ==
       [f["kind"] for f in noisy["findings"]],
       "100 h of prune, inspect and buy changes not one finding",
       f"clean {[f['kind'] for f in clean['findings']]} vs "
       f"noisy {[f['kind'] for f in noisy['findings']]}")
    ok(all(stage(clean, s)["tasks"]["hours"] == stage(noisy, s)["tasks"]["hours"]
           for s in ("structure", "planting", "aftercare")),
       "and enters no stage total",
       "excluded kinds are being summed into a stage")
    ok(not finding(noisy, "unmapped-kind"),
       "and raises no unmapped-kind finding, because all three are declared",
       "a declared exclusion is being reported as undeclared")


def check_prep_unassigned(reconcile, root):
    """The kind that spans the bridge is named, and is in no total."""
    ok("prep" in reconcile.UNASSIGNED,
       "`prep` is declared as spanning the bridge rather than assigned",
       "prep has been quietly put on one side")
    ok(reconcile.stage_of_kind("prep") is None,
       "so it belongs to no stage")
    slug = make_yard(root, "prepped", real_planting_tasks() + [
        task("t9", "prep", "2026-10-03", 600, "Clear the weeds out of g05")])
    r = reconcile.compare(slug)
    ok(stage(r, "structure")["tasks"]["hours"] == 0.0,
       "10 h of prep does not land in the structure total",
       f"structure picked up {stage(r, 'structure')['tasks']['hours']} h")
    ok(not finding(r, "unmapped-kind"),
       "and is not reported as undeclared, because it is declared")


def check_repeats_not_summed(reconcile, root):
    """Per-occurrence minutes are jobs, not hours."""
    tasks = [task("t1", "plant", "2026-11-14", 240, "Plant g02"),
             {"id": "t2", "kind": "water", "minutes": 20, "done": False,
              "title": "Establishment watering for every new planting",
              "repeat": {"from": "2026-10-18", "to": "2026-12-16",
                         "every": "2 days"}}]
    slug = make_yard(root, "repeating", tasks)
    r = reconcile.compare(slug)
    after = stage(r, "aftercare")
    ok(after["tasks"]["hours"] == 0.0,
       "a repeating watering job contributes no hours to a total",
       f"aftercare picked up {after['tasks']['hours']} h from a job whose "
       f"minutes are per occurrence")
    ok([i["id"] for i in after["tasks"]["repeats"]] == ["t2"],
       "and is carried as a named repeating job instead",
       f"repeats came back {after['tasks']['repeats']}")
    ok("t2" in r["tasks"]["repeating"],
       "and counted in the excluded tally the report prints")


def check_beyond_target(reconcile, root):
    """build() plans up to the target and cannot see past it."""
    tasks = real_planting_tasks() + [
        task("t9", "plant", "2027-03-01", 600, "The spring planting")]
    slug = make_yard(root, "beyond", tasks)
    r = reconcile.compare(slug)
    ok([b["id"] for b in r["tasks"]["beyond_target"]] == ["t9"],
       "a task dated after the target is excluded and named",
       f"beyond_target came back {r['tasks']['beyond_target']}")
    ok("t9" not in [i["id"] for i in stage(r, "planting")["tasks"]["items"]],
       "and is in no stage total",
       "10 h of March planting is being counted against a December target")


# --------------------------------------------------------------- the gate

def check_gate_holds(reconcile, root, doubts):
    """A yard that is not clear for `schedule` has no second derivation.

    The refusal is reported, not overridden. `build(force=True)` would produce a
    plan stamped provisional and a reconciliation against a provisional plan is
    a number nobody should act on.
    """
    slug = make_yard(root, "gated", real_planting_tasks())
    real = doubts.gate
    forced = []

    def refuse(s, job, force=False):
        forced.append(force)
        if force:
            return "PROVISIONAL - forced past 1 open doubt"
        raise SystemExit("refusing to run schedule on gated: 1 open doubt "
                         "would change the answer.")
    doubts.gate = refuse
    try:
        r = reconcile.compare(slug)
    finally:
        doubts.gate = real

    f = finding(r, "blocked")
    ok(f is not None,
       "a gated yard gives a `blocked` finding rather than a traceback",
       "the gate's SystemExit escaped the reconciliation")
    ok(f is not None and "open doubt" in f["message"],
       "and the finding carries the gate's own reason",
       f"message was {f and f['message']!r}")
    ok(forced == [False],
       "and the gate was asked exactly once, without --force",
       f"gate was called with force={forced}")
    ok(r["tasks"] is None and r["stages"] == [],
       "and no stage numbers are reported off a plan that does not exist",
       f"stages came back {r['stages']}")


def check_no_plan_to_compare(reconcile, root):
    """The other ways there is no second derivation, reported the same way.

    `build()` returns an `error` rather than raising for these, and an error is
    as much "there is nothing to compare against" as a refusal is.
    """
    slug = make_yard(root, "notarget", real_planting_tasks())
    with open(os.path.join(root, slug, "vision.json"), "w") as fh:
        json.dump({}, fh)
    f = finding(reconcile.compare(slug), "blocked")
    ok(f is not None and "target date" in f["message"],
       "a yard with no target date gives a `blocked` finding naming that",
       f"got {f and f.get('message')!r}")
    ok(f is not None and "no second derivation" in f["message"],
       "and says what that means for the comparison",
       f"got {f and f.get('message')!r}")


# ------------------------------------------------- the independence guarantee

def check_pipeline_not_inverted():
    """`lib.schedule` must not learn to read `tasks.json`.

    This is the guarantee the whole module rests on, and it is one import away
    from being lost. Two independent derivations that agree is evidence; a copy
    that agrees is not, and a copy would have agreed perfectly on the month it
    was a month wrong.
    """
    src = open(os.path.join(ROOT, "lib", "schedule.py"), encoding="utf-8").read()
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    body = code.split('"""', 2)[-1]        # past the module docstring
    for needle, why in (("tasks.json", "the file"),
                        ("lib.week", "the module that renders it"),
                        ("import week", "the module that renders it"),
                        ("reconcile", "this comparison")):
        ok(needle not in body,
           f"lib/schedule.py does not reach for {needle} ({why})",
           f"{needle!r} appears in lib/schedule.py outside the docstring. "
           f"If build() reads tasks.json the two can no longer disagree, and "
           f"their agreement stops being evidence of anything")

    rec = open(os.path.join(ROOT, "lib", "reconcile.py"), encoding="utf-8").read()
    ok("from . import schedule, week" in rec,
       "and lib/reconcile.py is the only thing that imports both",
       "the reconciliation no longer reads both sides")


def check_ungated():
    """A diagnostic that has to be approved is not a diagnostic."""
    from lib import doubts
    ok("reconcile" not in doubts.JOBS,
       "lib.reconcile is not a gated job",
       "the reconciliation has been added to the gate, so the cheapest way to "
       "settle a doubt about the schedule now needs the doubt settled first")
    conf = os.path.join(ROOT, ".cursor", "hooks.json")
    with open(conf) as fh:
        entries = json.load(fh)["hooks"]["beforeShellExecution"]
    matcher = next((e.get("matcher") for e in entries
                    if "doubt-gate.sh" in e.get("command", "")), "")
    ok("reconcile" not in matcher,
       "and the hook does not deny it either",
       f"the matcher mentions reconcile: {matcher!r}")


# ------------------------------------------------------------------- the report

def check_report_runs(reconcile, root, capture=True):
    """Every branch of the printed report, because a crash here is a dead check."""
    import io
    import contextlib
    cases = [
        ("a yard with findings", make_yard(root, "rep1", real_planting_tasks())),
        ("a yard with nothing dated", make_yard(root, "rep2", [])),
        ("a yard where a stage agrees",
         make_yard(root, "rep3", [task("t1", "plant", "2026-11-15", 240, "x")])),
    ]
    for label, slug in cases:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                reconcile.report(slug)
            out = buf.getvalue()
            ok(len(out.splitlines()) > 5 and "lib.schedule against tasks.json"
               in out, f"the report renders for {label}",
               f"output was {out[:200]!r}")
        except Exception as exc:            # noqa: BLE001 - a crash is the find
            ok(False, f"the report renders for {label}",
               f"{type(exc).__name__}: {exc}")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        reconcile.report_basis()
    text = buf.getvalue()
    ok("each in exactly one stage" in text,
       "--basis states that the bridge still covers ORDER",
       f"got {text[-200:]!r}")
    ok(all(k in text for k in reconcile.OUTSIDE),
       "and names every excluded kind with its reason",
       "an exclusion is not printed, so it is a tolerance rather than a "
       "declaration")


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yardtest-")
    os.environ["GARDEN_ROOT"] = root
    for mod in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[mod]
    from lib import doubts, reconcile, schedule

    # The gate is stubbed rather than satisfied, except in the one section that
    # tests the gate. Whether it holds is `tools/test_gate.py`'s job; repeating a
    # board and an all-clear in every fixture here would test that instead of
    # the comparison.
    doubts.gate = lambda *a, **k: False

    print("lib.reconcile — does the comparison catch the divergence it was "
          "built for\n")
    try:
        print(" the original bug, reconstructed")
        check_the_original_bug(reconcile, root)
        print("\n why totals alone were never going to be enough")
        check_totals_would_not_have(reconcile, root)
        print("\n the bridge between the two vocabularies")
        check_bridge(reconcile, schedule)
        check_undeclared_kind(reconcile, root)
        check_no_kind(reconcile, root)
        print("\n work one side does not know exists")
        check_presence(reconcile, root)
        print("\n the resolution of the comparison")
        check_resolution_is_read(reconcile, root)
        check_timing_resolution(reconcile, root)
        check_bulk_not_the_ends(reconcile, root)
        print("\n the asymmetry, declared rather than tolerated")
        check_declared_asymmetry(reconcile, root)
        check_prep_unassigned(reconcile, root)
        check_repeats_not_summed(reconcile, root)
        check_beyond_target(reconcile, root)
        print("\n the gate, which still holds")
        check_gate_holds(reconcile, root, doubts)
        check_no_plan_to_compare(reconcile, root)
        print("\n the independence the whole thing rests on")
        check_pipeline_not_inverted()
        check_ungated()
        print("\n the report itself")
        check_report_runs(reconcile, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nThe reconciliation is not comparing what it claims to:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
