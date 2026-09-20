#!/usr/bin/env python3
"""A sharp-drainage plant in slow ground, and whether the plan already answers it.

    python3 tools/test_drainage.py
    python3 tools/test_drainage.py -v      print the objections in full

`design.check_soil` refuses a plant that wants sharp drainage where the soil
reads slow, and it is right to: this is the way rosemary dies, over two summers,
so slowly that nobody connects it to the soil. The fault was not the objection.
It was that the objection printed *plant it on a mound with grit* as its fix,
and on cloverleaf-austin that mound had been designed, dated, funded and put on
the shopping list before the objection was ever raised — 17 October, a 3-4 in
mound of soil cut with grit, nine plants, two bags, `tasks.json` t033. The check
could not see it, so it refused nine plants and recommended the thing the plan
already said to do, on every run, forever.

An objection nobody can satisfy by doing the right thing is one people learn to
scroll past, and the next real one goes past with it. That is the failure this
file exists to prevent, and it has two halves.

WHAT MUST GO QUIET, AND WHAT MUST NOT

The amendment is a recorded fact about a PLANTING POSITION, never about a
plant. The same rosemary is a different proposition on a grit mound and flush
in clay, and the tempting shortcut — a list of plant names known to be mounded,
or a keyword hunted through the bed's prose — gets exactly this wrong, silently,
the first time somebody moves a plant. Several fixtures below are two entries
for the SAME plant in the SAME slow ground where the only difference is the
recorded amendment, so an implementation keyed to the name fails both ways at
once.

The second half is that going quiet is not the same as being safe, and the
check must not claim more than it knows. Nobody has measured the drainage here:
`conditions.soil.drainage` is provenance `assumed` and the percolation test has
been declined twice. Whether 3-4 in of grit over group-D clay on a flat lot is
enough is genuinely unknown, and d26 records that as risk ACCEPTED rather than
as risk answered. So the amendment moves the objection from a claim about the
soil, which the plan cannot change, to a claim about a task, which can be
checked and can slip — and the note has to say so and name the task. A silent
pass would be the original fault wearing the other hat.

Hence three levels, separated by evidence and not by severity:

    blocking   nothing recorded. Unchanged.
    serious    an amendment asserted with no `source`. Called out rather than
               believed, because an answer resting on nobody reads like one.
    note       an amendment with a source. Answered; what is left is doing it.

Runs entirely on dicts in memory. No yard is read or written.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import design  # noqa: E402  (after sys.path)

PASS = FAIL = 0
verbose = False


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok    {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")
        if detail:
            for line in str(detail).strip().splitlines():
                print(f"          {line}")


def head(t):
    print(f"\n{t}")


def show(objs):
    return "\n".join(f"[{o['level']}] {o['about']}: {o['say']}"
                     for o in objs) or "(no objections)"


# --------------------------------------------------------------- the fixtures

# cloverleaf-austin's own reading, and the word matters: `check_soil` matches
# "slow" or "poor" inside whatever prose the yard recorded, so the fixture is
# the real string rather than a tidy enum.
SLOW = {"soil": {"drainage": "slow"}}
FAST = {"soil": {"drainage": "sharp, gravelly fill"}}

# The real amendment, transcribed from design.json after d26 was settled.
MOUND = {
    "describe": "a 3-4 in mound of soil cut with grit, built as you go rather "
                "than as a second pass, with the crown set high",
    "kind": "mound",
    "depth_in": 3.5,
    "material": "native soil cut with bagged grit (b14, b15 — two bags, $16)",
    "built_on": "2026-10-17",
    "source": ["tasks.json#t033", "PLAN.md#239", "CALENDAR.md"],
    "why": "settled as d26: build the mounds and accept.",
}


def plant(name="Blackfoot daisy", **kw):
    p = {"name": name, "zone": "bed_g02", "soil_drainage": "sharp"}
    p.update(kw)
    return p


# A sentinel, because two of the cases below ARE `{}` and `None` — the yard that
# has never had its drainage read — and `cond or SLOW` would quietly test the
# slow fixture instead and pass.
UNSET = object()


def soil_objs(p, cond=UNSET):
    return [o for o in design.check_soil(p, SLOW if cond is UNSET else cond)
            if "drain" in o["say"]]


def levels(p, cond=UNSET):
    return [o["level"] for o in soil_objs(p, cond)]


# ------------------------------------------------------------------ the tests

def test_slow_ground_with_nothing_recorded_still_blocks():
    """The whole check must not be softened by teaching it about mounds.

    This is the one that matters most. Everything else here makes an objection
    quieter, and the way that goes wrong is that it goes quiet everywhere.
    """
    ok("a sharp-drainage plant in slow ground still blocks when nothing is done",
       levels(plant()) == ["blocking"],
       show(soil_objs(plant())))


def test_the_amendment_answers_the_objection():
    p = plant(drainage_amendment=MOUND)
    ok("a recorded mound with a source drops it to a note",
       levels(p) == ["note"], show(soil_objs(p)))


def test_the_note_names_the_task_it_depends_on():
    """A note that does not say where the mound is written down is a shrug.

    The point of the amendment is that the risk moved from the soil to a task.
    A reader who cannot find the task cannot check whether it survived.
    """
    say = soil_objs(plant(drainage_amendment=MOUND))[0]["say"]
    ok("the note cites the task that builds it",
       "tasks.json#t033" in say, say)
    ok("the note says what is actually built",
       "grit" in say and "mound" in say, say)


def test_the_note_does_not_claim_the_plant_is_safe():
    """d26 accepted the risk; it did not answer it.

    Nobody has measured this soil. If the note reads as an all-clear then the
    check has replaced an objection nobody could satisfy with a reassurance
    nobody earned, which is worse — the first at least kept the question open.
    """
    o = soil_objs(plant(drainage_amendment=MOUND))[0]
    ok("the note says the plant depends on the mound being built",
       "lives or dies" in o["say"], o["say"])
    ok("the note says what happens if the step is skipped",
       "skipped" in (o.get("fix") or "") or "dropped" in (o.get("fix") or ""),
       o.get("fix"))


def test_an_amendment_with_no_source_is_not_believed():
    """An answer resting on nobody.

    This is weaker than recording nothing, because it READS like an answer.
    Left at `note` it would be the cheapest possible way to silence the check:
    write a sentence, get a pass.
    """
    p = plant(drainage_amendment={"describe": "a mound, probably"})
    ok("an amendment with no source is serious, not a note",
       levels(p) == ["serious"], show(soil_objs(p)))
    p2 = plant(drainage_amendment={"describe": "a mound", "source": ["", "  "]})
    ok("a source list of blank strings does not count as a source",
       levels(p2) == ["serious"], show(soil_objs(p2)))


def test_an_amendment_with_no_description_is_not_an_amendment():
    """`drainage_amendment: true` must not buy anything.

    The field has to say what was built. A bare flag is a plant asserting it is
    fine, which is the thing the check exists to disbelieve.
    """
    for bad in (True, {}, {"source": ["tasks.json#t033"]}, "a mound", None):
        p = plant(drainage_amendment=bad)
        ok(f"drainage_amendment={bad!r} does not answer the objection",
           levels(p) == ["blocking"], show(soil_objs(p)))


def test_it_is_the_position_and_not_the_plant():
    """Two blackfoot daisies, same soil, same name, different ground.

    A shortcut keyed to plant names passes the mounded one and ALSO passes the
    flush one, which is the failure that shows up months later when somebody
    adds a tenth plant to a bed budgeted for nine.
    """
    mounded = plant("Blackfoot daisy", drainage_amendment=MOUND)
    flush = plant("Blackfoot daisy")
    ok("the mounded one passes and the flush one blocks, on the same name",
       levels(mounded) == ["note"] and levels(flush) == ["blocking"],
       show(soil_objs(mounded) + soil_objs(flush)))


def test_a_plant_that_does_not_need_sharp_drainage_is_never_asked():
    p = plant("Gulf muhly", soil_drainage="average")
    ok("slow ground says nothing about a plant that does not want sharp drainage",
       levels(p) == [], show(soil_objs(p)))


def test_good_ground_needs_no_amendment():
    ok("sharp ground raises nothing, amendment or not",
       levels(plant(), FAST) == []
       and levels(plant(drainage_amendment=MOUND), FAST) == [],
       show(soil_objs(plant(), FAST)))


def test_unrecorded_drainage_is_not_treated_as_slow():
    """Silence about the soil is not evidence about the soil.

    `check_coverage` reports the missing reading separately; this check must not
    invent it. A yard with no percolation test would otherwise have every
    sharp-drainage plant refused on nothing at all.
    """
    for cond in ({}, {"soil": {}}, {"soil": {"drainage": ""}}, None):
        ok(f"drainage {cond!r} raises no drainage objection",
           levels(plant(), cond) == [], show(soil_objs(plant(), cond)))


def test_a_container_is_not_the_ground():
    """The pre-existing container escape must survive the rewrite.

    A pot's medium is whatever gets put in it, so the yard's drainage does not
    apply. This passes `site` and so exercises the early return the new branch
    sits behind.
    """
    site = {"zones": {"bed_barrels": {"kind": "container", "containers": 3}}}
    p = plant("Rosemary", zone="bed_barrels")
    got = [o for o in design.check_soil(p, SLOW, site) if "drain" in o["say"]]
    ok("a sharp-drainage plant in a container is not judged on the yard's soil",
       got == [], show(got))


def test_the_accessor_is_strict_about_shape():
    ok("drainage_amendment() returns None for anything without a describe",
       all(design.drainage_amendment(plant(drainage_amendment=b)) is None
           for b in (True, {}, "mound", None, {"kind": "mound"})),
       "one of the malformed shapes was accepted")
    ok("drainage_amendment() returns the dict when it is well formed",
       design.drainage_amendment(plant(drainage_amendment=MOUND)) is MOUND)


def test_the_ph_check_is_untouched():
    """The other half of check_soil, in case the rewrite took it with it."""
    p = plant("Blueberry", ph_range=[4.5, 5.5], soil_drainage="average")
    got = design.check_soil(p, {"soil": {"ph": 7.9}})
    ok("a pH mismatch is still raised", [o["level"] for o in got] == ["serious"],
       show(got))


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    head("slow ground, and what it takes to answer it")
    test_slow_ground_with_nothing_recorded_still_blocks()
    test_the_amendment_answers_the_objection()
    test_the_note_names_the_task_it_depends_on()
    test_the_note_does_not_claim_the_plant_is_safe()

    head("what does not count as an amendment")
    test_an_amendment_with_no_source_is_not_believed()
    test_an_amendment_with_no_description_is_not_an_amendment()
    test_the_accessor_is_strict_about_shape()

    head("a fact about the position, not about the plant")
    test_it_is_the_position_and_not_the_plant()
    test_a_plant_that_does_not_need_sharp_drainage_is_never_asked()

    head("ground the check must stay off")
    test_good_ground_needs_no_amendment()
    test_unrecorded_drainage_is_not_treated_as_slow()
    test_a_container_is_not_the_ground()
    test_the_ph_check_is_untouched()

    print(f"\n{PASS} of {PASS + FAIL} passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
