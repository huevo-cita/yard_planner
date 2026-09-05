#!/usr/bin/env python3
"""Prove the build archetypes are derived from what a design actually writes.

    python3 tools/test_archetypes.py
    python3 tools/test_archetypes.py -v      show every check's detail

`schedule.tasks_from_design` turns a design into the seventeen archetypes
`ORDER` holds. On the first real yard it emitted four of them, and the reason
was not judgement — it was field names. Three guards consulted
`hardscape["kind"]`, which `design.json` writes on about a third of its lines
and has never filled with one of the paving words the path guard tested for; one
consulted `hardscape["name"]`, which `design.json` writes never; one tested
`pot_size` against `"3gal"` while the file holds `"1 gal"`; one required
`pot_size == "seed"` on a yard with seven sowing tasks; and one required a
`needs_support` field no plant in this repo has ever set.

A guard reading a key nobody writes is indistinguishable from a guard that is
correctly quiet, and that is the whole reason this file exists rather than a
comment.

What is proved here

  the label is read     a hardscape line with no `kind` at all is matched on
                        `item`, up to the first comma or dash. `kind` still
                        wins where it is written
  and only the label    "Frost cloth, 1.5 oz, plus pins, stored AT the raised
                        bed" schedules no bed-building. This is the trap in
                        reading `item` naively, and it costs ten hours
  the ground is asked   a design naming a raised bed schedules the building of
                        one on bare ground and not on a yard whose ground
                        record says one was built. Same for edging
  superseded is not work
                        a hardscape line carrying `superseded_by` is the
                        reasoning of record for a reversed decision, and
                        nobody is going to build it
  stock size is read straight
                        "5 gal", "5gal", "#5" and "b&b" are one stock class.
                        "1 gal" and "4 in" are not shrubs and do not become
                        them
  seed is read from the record
                        `pot_size: "seed"` is the field for it; where it is
                        empty the name is read, and the crop is checked against
                        this module's own DIRECT_SOW list. A record naming a
                        pot is not sown, however its name reads
  nothing is planted twice
                        a design of nothing but `existing` records schedules
                        no planting, no sowing and no staking
  every archetype says why
                        each emitted entry carries a `because` naming the fact
                        that put it there, because "lay a path (10 h)" reads
                        identically over a patio and over fifteen square feet
                        of cobble
  reachability is declared both ways
                        every entry in `ORDER` outside `UNREACHABLE` is emitted
                        by some design, and everything inside it by none. A new
                        archetype wired in and left unreachable is a failure
                        here rather than a silence
  the guards do not reach past the readers
                        `tasks_from_design` names no hardscape field directly.
                        Asserted on the source, because it is the exact
                        regression and it is cheap to lose by accident

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import inspect
import json
import os
import re
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

SITE = {
    "address": {"lat": 30.29, "lon": -97.70},
    "climate": {"last_frost": "Feb 20", "first_frost": "Dec 01"},
    "zones": {"bed_a": {"label": "a bed", "area_sqft": 80.0, "kind": "border"}},
}

#: A yard whose beds are all working ground: no marking out, no turf, no
#: edging, no tilling, and a drip system already in.
BUILT = {
    "areas": [{"name": "a bed", "state": "dug and edged"},
              {"name": "the raised bed", "state": "built"}],
    "hardscape": [], "surface_note": "",
}

#: The opposite: bare lawn with nothing done to it and no water laid on.
BARE = {"areas": [], "hardscape": [], "surface_note": "mown lawn"}


def make_yard(root, ground, plants, hardscape, irrigation=True,
              extra_materials=None):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    cond = {"person": {"experience": "some", "hours_per_week": 6},
            "ground": ground,
            "water": ({"irrigation": {"installed": True}} if irrigation
                      else {})}
    design = {"plants": plants, "hardscape": hardscape}
    if extra_materials:
        design["extra_materials"] = extra_materials
    for name, payload in (("design.json", design), ("site.json", SITE),
                          ("vision.json", {"target_date": "2027-04-10"}),
                          ("conditions.json", cond)):
        with open(os.path.join(d, name), "w") as fh:
            json.dump(payload, fh)
    return d


def emitted(schedule, root, ground=None, plants=None, hardscape=None,
            irrigation=True, extra_materials=None):
    """The archetype names one design produces, as a set."""
    make_yard(root, ground if ground is not None else BUILT,
              plants if plants is not None else [], hardscape or [],
              irrigation=irrigation, extra_materials=extra_materials)
    return {t["task"] for t in schedule.tasks_from_design(SLUG)}


PERENNIAL = {"name": "autumn sage", "pot_size": "1 gal", "role": "filler",
             "zone": "bed_a", "layer": "middle"}


# ------------------------------------------------------------------ the checks

def check_label_is_read(schedule, root):
    """A line with no `kind` is matched on its label, and `kind` still wins."""
    band = {"item": "River rock band, g03 - 1.5 to 3 in cobble on filter "
                    "fabric", "zone": "bed_a", "cost_usd": 50}
    got = emitted(schedule, root, hardscape=[band], plants=[PERENNIAL])
    ok("lay a path" in got,
       "a hardscape line with no `kind` is matched on its `item` label",
       f"{band['item'][:40]!r} produced {sorted(got)}")

    kinded = {"item": "Front walk", "kind": "flagstone"}
    got = emitted(schedule, root, hardscape=[kinded], plants=[PERENNIAL])
    ok("lay a path" in got,
       "an explicit `kind` is still honoured where a design writes one",
       f"kind 'flagstone' produced {sorted(got)}")

    quiet = {"item": "Two-zone drip timer plus a 25 PSI pressure regulator"}
    got = emitted(schedule, root, hardscape=[quiet], plants=[PERENNIAL])
    ok("lay a path" not in got and "run drip irrigation" not in got,
       "a line naming no element of a stage schedules nothing from it",
       f"a drip timer produced {sorted(got)}")


def check_only_the_label(schedule, root):
    """The trap: `item` holds a paragraph, and the paragraph mentions things.

    This is the ten-hour version of the bug the fix could have introduced.
    """
    cloth = {"item": "Frost cloth, 1.5 oz, plus pins, stored AT the raised bed",
             "cost_usd": 25}
    got = emitted(schedule, root, hardscape=[cloth], plants=[PERENNIAL],
                  ground=BARE)
    ok("build a raised bed" not in got and "spread and grade soil" not in got,
       "a note mentioning a raised bed does not schedule the building of one",
       f"frost cloth stored at the raised bed produced {sorted(got)}")

    pots = {"item": "Portable pots for December colour, moved to the gravel "
                    "court for the party"}
    got = emitted(schedule, root, hardscape=[pots], plants=[PERENNIAL])
    ok("lay a path" not in got,
       "a note mentioning a gravel court does not schedule a path",
       f"portable pots produced {sorted(got)}")


def check_ground_is_asked(schedule, root):
    """The same design, on ground that has the thing and ground that does not."""
    box = {"item": "Raised bed, 4 x 8 ft, 2x10 cedar"}
    bare = emitted(schedule, root, hardscape=[box], plants=[PERENNIAL],
                   ground=BARE)
    built = emitted(schedule, root, hardscape=[box], plants=[PERENNIAL],
                    ground=BUILT)
    ok("build a raised bed" in bare and "spread and grade soil" in bare,
       "a raised bed in the design is built on bare ground",
       f"bare ground produced {sorted(bare)}")
    ok("build a raised bed" not in built and "spread and grade soil" not in built,
       "and is not built again on a yard whose ground record says `built`",
       f"built ground produced {sorted(built)}")

    edge = {"item": "Pavestone Edgestone edging, 40 ft"}
    bare = emitted(schedule, root, hardscape=[edge], plants=[PERENNIAL],
                   ground=BARE)
    built = emitted(schedule, root, hardscape=[edge], plants=[PERENNIAL],
                    ground=BUILT)
    ok("install edging" in bare,
       "edging in the design is installed on unedged ground",
       f"bare ground produced {sorted(bare)}")
    ok("install edging" not in built,
       "and is not installed again where the ground record says `edged`",
       f"built ground produced {sorted(built)}")


def check_superseded_is_not_work(schedule, root):
    dead = {"item": "DIY flagstone path (SUPERSEDED)",
            "superseded_by": ["gravel court"]}
    got = emitted(schedule, root, hardscape=[dead], plants=[PERENNIAL])
    ok("lay a path" not in got,
       "a hardscape line carrying `superseded_by` schedules nothing",
       f"a superseded path produced {sorted(got)}")

    marked = {"item": "Container fountain (SUPERSEDED), flagstone surround"}
    got = emitted(schedule, root, hardscape=[marked], plants=[PERENNIAL])
    ok("lay a path" not in got,
       "a line calling itself superseded in its own label likewise",
       f"produced {sorted(got)}")


def check_stock_size(schedule, root):
    """One stock class, however somebody typed it."""
    for size in ("5 gal", "5gal", "#5", "B&B", " 15 gal "):
        got = emitted(schedule, root,
                      plants=[dict(PERENNIAL, pot_size=size, name="yaupon")])
        ok("plant shrubs" in got,
           f"{size!r} is read as shrub or tree stock",
           f"produced {sorted(got)}")
    for size in ("1 gal", "4 in", "4in", "2 gal"):
        got = emitted(schedule, root,
                      plants=[dict(PERENNIAL, pot_size=size)])
        ok("plant shrubs" not in got,
           f"{size!r} is not shrub stock and does not become one",
           f"produced {sorted(got)}")
    got = emitted(schedule, root,
                  plants=[dict(PERENNIAL, pot_size=None,
                               role="back-row shrub", name="yaupon")])
    ok("plant shrubs" in got,
       "a role naming a shrub counts even with no pot size on file",
       f"produced {sorted(got)}")


def check_seed_is_read(schedule, root):
    cases = [
        ({"name": "carrots", "pot_size": "seed"}, True,
         "`pot_size: \"seed\"` is still the field for it"),
        ({"name": "Carrots (direct sown)"}, True,
         "a name saying direct sown, with no pot size"),
        ({"name": "Radish"}, True,
         "a crop in this module's own DIRECT_SOW list"),
        ({"name": "Broccoli (transplants)"}, False,
         "a transplant is not sown, whatever else its name says"),
        ({"name": "Softneck garlic (cloves)"}, False,
         "cloves are planted rather than sown"),
        ({"name": "Radish", "pot_size": "4 in"}, False,
         "a record naming a pot is not sown, however its name reads"),
    ]
    for extra, want, label in cases:
        rec = dict(PERENNIAL, pot_size=None)
        rec.update(extra)
        got = emitted(schedule, root, plants=[rec])
        ok(("sow seed" in got) == want, label,
           f"{extra} produced {sorted(got)}")


def check_nothing_planted_twice(schedule, root):
    old = [
        {"name": "Climbing Westerland (existing, west trellis)",
         "existing": True, "layer": "vine", "role": "vertical structure"},
        {"name": "Bluebonnet (existing self-sown seed bank)", "existing": True,
         "layer": "front", "role": "spring, and a protected seed bank"},
        {"name": "Star jasmine", "role": "existing", "layer": "vine"},
    ]
    got = emitted(schedule, root, plants=old)
    for task in ("plant perennials", "plant shrubs", "sow seed",
                 "stake and trellis"):
        ok(task not in got,
           f"a design of nothing but existing records schedules no {task!r}",
           f"produced {sorted(got)}")


def check_support_is_read(schedule, root):
    vine = dict(PERENNIAL, name="crossvine", layer="vine")
    ok("stake and trellis" in emitted(schedule, root, plants=[vine]),
       "a new plant filed `layer: \"vine\"` needs support put up",
       f"produced {sorted(emitted(schedule, root, plants=[vine]))}")
    ok("stake and trellis" not in emitted(
           schedule, root, plants=[dict(vine, existing=True)]),
       "the same vine already on its trellis does not",
       "an existing climber was scheduled for staking")
    flagged = dict(PERENNIAL, needs_support=True)
    ok("stake and trellis" in emitted(schedule, root, plants=[flagged]),
       "an explicit `needs_support` is still honoured",
       "the declared field stopped being read")
    ok("stake and trellis" not in emitted(schedule, root, plants=[PERENNIAL]),
       "and a plant that climbs nothing is not staked",
       "a filler perennial was scheduled for staking")


def check_drip(schedule, root):
    got = emitted(schedule, root, plants=[PERENNIAL], irrigation=False)
    ok("run drip irrigation" in got,
       "a yard with no irrigation on record gets a drip run installed",
       f"produced {sorted(got)}")
    got = emitted(schedule, root, plants=[PERENNIAL], irrigation=True)
    ok("run drip irrigation" not in got,
       "and a yard whose record says it is installed does not",
       f"produced {sorted(got)}")
    got = emitted(schedule, root, plants=[PERENNIAL], irrigation=True,
                  extra_materials={"drip line": 40})
    ok("run drip irrigation" in got,
       "unless the design is buying more drip line",
       f"produced {sorted(got)}")
    # `extra_materials` is keyed by whatever the design called the material, so
    # an exact `"drip line"` lookup is the hardscape bug in a second place.
    # `tools/influence.py --unwritten` found this one: the real design writes
    # `compost`, `garden soil` and `grit or decomposed granite for mounding`,
    # and would have written `1/4 in drip tubing` just as readily.
    got = emitted(schedule, root, plants=[PERENNIAL], irrigation=True,
                  extra_materials={"1/4 in drip tubing, 100 ft": 1})
    ok("run drip irrigation" in got,
       "and the key is read by word, not matched exactly",
       f"produced {sorted(got)}")
    got = emitted(schedule, root, plants=[PERENNIAL], irrigation=True,
                  extra_materials={"compost": 12, "garden soil": 8})
    ok("run drip irrigation" not in got,
       "while soil and compost are not irrigation",
       f"produced {sorted(got)}")


def check_because(schedule, root):
    """Every entry names the fact that put it there."""
    make_yard(root, BARE,
              [PERENNIAL, dict(PERENNIAL, pot_size="5 gal", name="yaupon"),
               {"name": "Carrots (direct sown)"},
               dict(PERENNIAL, name="crossvine", layer="vine")],
              [{"item": "Raised bed, 4 x 8 ft"},
               {"item": "Pavestone Edgestone edging"},
               {"item": "Flagstone path to the gate"}],
              irrigation=False)
    tasks = schedule.tasks_from_design(SLUG)
    missing = [t["task"] for t in tasks if not str(t.get("because") or "").strip()]
    ok(not missing, "every emitted archetype carries a `because`",
       f"no reason given for {missing}")
    stray = [t["task"] for t in tasks if t["task"] not in schedule.ORDER]
    ok(not stray, "every emitted archetype is an entry in ORDER",
       f"emitted and not in ORDER: {stray}")
    ok(len(tasks) == len({t["task"] for t in tasks}),
       "no archetype is emitted twice",
       f"{len(tasks)} entries, {len({t['task'] for t in tasks})} distinct")
    return {t["task"] for t in tasks}


def check_reachability(schedule, root, maximal):
    """`UNREACHABLE`, asserted in both directions."""
    for task in schedule.ORDER:
        if task in schedule.UNREACHABLE:
            continue
        ok(task in maximal,
           f"{task!r} is reachable from a design",
           f"no guard in tasks_from_design emitted it on the maximal yard. "
           f"Either wire it up or declare it in schedule.UNREACHABLE with a "
           f"reason")
    for task, why in sorted(schedule.UNREACHABLE.items()):
        ok(task in schedule.ORDER,
           f"{task!r} is declared unreachable and is still in ORDER",
           "UNREACHABLE names an archetype ORDER no longer holds")
        ok(task not in maximal,
           f"{task!r} is declared unreachable and stays that way",
           f"it was emitted after all, so the declaration is now false: {why}")
        ok(len(str(why)) > 40,
           f"{task!r}'s unreachability carries a reason somebody can argue with",
           f"the reason is {len(str(why))} characters, which is not one")


def check_no_direct_field_reads():
    """On the source: the guards go through the readers and not past them.

    The regression was three guards reaching into a hardscape entry for a field
    the file does not write. Reading `item` and `kind` in exactly one place is
    what makes that a one-line fix next time instead of a four-line hunt.
    """
    from lib import schedule
    src = inspect.getsource(schedule.tasks_from_design)
    bad = re.findall(r"\bh\s*(?:\.get\(|\[)", src)
    ok(not bad,
       "tasks_from_design reads no hardscape field directly",
       f"{len(bad)} direct reads of a hardscape entry are back in the guards; "
       f"they belong in hardscape_lines")
    ok("hardscape_says" in src,
       "it goes through hardscape_says instead",
       "the reader is no longer called, so the label rules have moved back "
       "into the guards")
    for gone in ('h.get("name"', "h.get('name'", 'get("needs_support")'):
        ok(gone not in src,
           f"the guards no longer consult {gone!r}",
           "a field design.json does not write is being read again")


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yardtest-")
    os.environ["GARDEN_ROOT"] = root
    for mod in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[mod]
    from lib import schedule

    print("lib.schedule — the archetypes, against what a design writes\n")
    try:
        print(" the hardscape label, read and not overread")
        check_label_is_read(schedule, root)
        check_only_the_label(schedule, root)
        check_superseded_is_not_work(schedule, root)
        print("\n what the ground already has")
        check_ground_is_asked(schedule, root)
        check_drip(schedule, root)
        print("\n the plant records")
        check_stock_size(schedule, root)
        check_seed_is_read(schedule, root)
        check_support_is_read(schedule, root)
        check_nothing_planted_twice(schedule, root)
        print("\n what every entry has to say for itself")
        maximal = check_because(schedule, root)
        print("\n reachability, declared in both directions")
        check_reachability(schedule, root, maximal)
        print("\n the shape of the fix, on the source")
        check_no_direct_field_reads()
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nThe archetypes are not derived from what the design says:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
