#!/usr/bin/env python3
"""An evergreen judged on the months it flowers in, which are the bright ones.

    python3 tools/test_winterlight.py
    python3 tools/test_winterlight.py -v      print the objections in full

`design.check_light` judges a plant over `months`, or failing that over
`bloom`. For anything that dies back that is exactly right — a dormant crown
does not care what December is doing. For a plant still in leaf it is the wrong
window, and it is wrong in the way that hides itself: bloom months are SELECTED
for being bright, so winter is not ignored, it is diluted. The four-nerve daisy
in g04 on cloverleaf-austin blooms Mar-Jun and Sep-Dec, reads 4.25 h over that
list, clears its 4.0 h part-sun floor by a quarter of an hour, and stands in a
bed averaging 3.66 h across the five months it is the only green thing in it.

WHY THIS FILE IS MOSTLY ABOUT THE PLANTS THAT MUST STAY QUIET

The obvious implementation keys off `evergreen: true`, and it is wrong twice
over. `evergreen` is a statement about leaves not falling off. The question is
whether the plant is photosynthesising and expected to look like something
while everything around it is dormant, and on a real yard those come apart in
both directions at once:

  inland sea oats      the best thing in g03 on 13 December — flat papery seed
                       heads standing over straw foliage — and `evergreen:
                       false`, because none of it is alive. A check that
                       decided from how a plant READS in winter would object
                       about a grass that wants no December light at all.

  Turk's cap           "ratty to dormant" after the first frost, by its own
                       entry. Lindheimer's senna: "brown, deliberately", left
                       standing because cutting a host plant destroys what
                       overwinters in it. Pride of Barbados: three 12-18 in
                       stubs under mulch, "absent by design, which is different
                       from absent by accident".

All four sit under their own light need across Nov-Feb, which is the window
d29 measured, and all four are correct passes. A check that objects about them
is wrong four times for every once it is right, and a check that cries wolf
four times out of five is the one somebody switches off — which costs more
than never having written it. (Over the Nov-Mar window this check actually
uses, three of the four clear their floor by 0.06 h anyway. That is luck, not
a safeguard: Pride of Barbados is still 0.34 h under, and the fixtures below
are built so the predicate is the only thing keeping any of them quiet.)

So the predicate is a declared field, `winter_active`, and the fixtures below
are built so that the ONLY difference between the plant that must object and
the plant that must stay silent is that field. Same bed, same hours, same
light rating, same bloom list. An implementation reading `evergreen`, or the
`december` prose, or the bloom list, fails at least one of them.

Runs entirely on dicts in memory. No yard is read or written.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import design, niches, solar  # noqa: E402  (after sys.path)

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

# g04 on cloverleaf-austin, measured, Jan through Dec. This is the bed the
# whole card is about and it is used rather than invented because it disagrees
# with itself by exactly the margin that makes the fault survivable:
#
#   Mar-Jun, Sep-Dec   4.25 h    the four-nerve daisy's bloom list — passes
#   Apr-Oct            4.60 h    the default window — passes
#   Nov-Mar            3.66 h    the months it is standing — 0.34 h short
#
# Nothing here is dramatic. A bed that failed winter by three hours would be
# caught by any implementation and by a person reading the table; a bed that
# fails by a third of an hour on one window and passes on the other two is the
# one that gets through.
G04 = [3.25, 4.01, 4.68, 5.10, 4.60, 4.15, 4.38, 4.91, 5.07, 3.99, 3.59, 2.78]

# g04's sunniest cell by month, also measured, and it is a trap rather than a
# detail. The primary light check rescues a refusal with "the sunniest cell
# does reach X h, so this may work in one corner". Over Nov-Mar the sunniest
# cell in g04 is 5.67 h and it is MARCH's — the brightest month in a window
# whose entire point is that it contains the dark ones. Offering it would be
# this check's own failure mode reappearing inside its escape hatch.
G04_BEST = [4.38, 4.77, 5.67, 6.25, 5.67, 5.42, 5.50, 5.92, 6.00, 4.95, 4.50,
            3.87]

# g03, measured. Dark enough that a part-sun plant is refused on ANY window,
# which is what makes it the fixture for the second-objection question: the
# rosemary in it blooms Nov-Mar, so its own window IS the standing season and
# its two figures are the same 3.06 h to the hundredth.
#
#   Nov-Mar   3.06 h    both the bloom figure and the winter figure
G03 = [2.97, 3.47, 3.68, 4.17, 4.34, 4.56, 4.47, 4.26, 3.81, 3.46, 2.32, 2.87]

# A bed on the north side of a two-storey neighbour: from April the sun clears
# their roof and from November it never does. Invented, because no bed on
# cloverleaf-austin collapses this hard, and needed for one question the real
# beds cannot ask — whether a catastrophic winter shortfall escalates.
#
#   Apr-Oct   6.90 h    clears full sun comfortably, so the primary check is
#                       silent and the winter branch is the only one talking
#   Nov-Mar   1.18 h    4.82 h short of full sun, which on the primary check's
#                       own scale is three times over the blocking threshold
WINTER_CLIFF = [1.0, 1.2, 1.8, 6.5, 7.2, 7.6, 7.5, 7.0, 6.4, 6.1, 1.1, 0.8]

# A bed that is fine in both halves of the year, so that "the check said
# nothing" can be distinguished from "the check never ran".
EVEN_BED = [5.4, 5.8, 6.1, 6.4, 6.8, 7.0, 6.9, 6.6, 6.2, 5.7, 5.2, 5.1]


def zone(hours, best=None):
    best = best or [h + 0.7 for h in hours]
    return {m: {"effective": h, "clear": h, "best_cell": b}
            for m, h, b in zip(solar.MONTHS, hours, best)}


SUN = {"by_zone_and_month": {
    "g04": zone(G04, G04_BEST),
    "g03": zone(G03),
    "cliff": zone(WINTER_CLIFF),
    "even": zone(EVEN_BED),
}}

SITE = {
    "zones": {
        "g04": {"style": "bed", "kind": "border", "area_sqft": 45.0,
                "usable_depth_ft": 3.0},
        "g03": {"style": "bed", "kind": "border", "area_sqft": 41.5,
                "usable_depth_ft": 2.2},
        "cliff": {"style": "bed", "kind": "border", "area_sqft": 40.0,
                  "usable_depth_ft": 3.0},
        "even": {"style": "bed", "kind": "border", "area_sqft": 40.0,
                 "usable_depth_ft": 3.0},
    },
    "climate": {"heat": {"days_over_95f_per_year": 45.8}},
}

# The four-nerve daisy's own bloom list. Eight months, and five of them are in
# the growing season, which is what pulls the mean back over the floor.
DAISY_BLOOM = ["Mar", "Apr", "May", "Jun", "Sep", "Oct", "Nov", "Dec"]

# Turk's cap's, which stops in November. The plant is ratty by December.
TURKS_BLOOM = ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]


def plant(zone_key, **kw):
    """One entry, with everything the light checks read and nothing else."""
    p = {"name": "Four-nerve daisy", "botanical": "Tetraneuris scaposa",
         "zone": zone_key, "count": 3, "light": "part sun", "water": "low",
         "mature_spread_ft": 1.0, "mature_height_ft": 0.8,
         "bloom": list(DAISY_BLOOM), "source": "test fixture"}
    p.update(kw)
    return p


def light(p):
    return design.check_light(p, SUN, SITE)


def refused(objs):
    return [o for o in objs if o["level"] in ("blocking", "serious")]


def wintery(objs):
    return [o for o in objs if "winter-active" in o["say"]]


def mean(hours, months):
    idx = [solar.MONTHS.index(m) for m in months]
    return round(sum(hours[i] for i in idx) / len(idx), 2)


def first(objs):
    """The first objection, or a blank one.

    Every assertion below that reaches into an objection is also an assertion
    that there IS one, and an implementation that emits nothing should be
    reported by the suite rather than crash it — a traceback tells you the
    test file broke, which is the wrong place to go looking.
    """
    return objs[0] if objs else {"level": "", "about": "", "say": "", "fix": ""}


STANDING = list(solar.STANDING_SEASON)


def run():
    head("the fixture disagrees with itself, or nothing below proves anything")
    ok("g04 clears the part-sun floor on the daisy's bloom list",
       mean(G04, DAISY_BLOOM) >= 4.0,
       f"bloom {mean(G04, DAISY_BLOOM)}")
    ok("and clears it over the growing season too, so the default is no help",
       mean(G04, solar.GROWING_SEASON) >= 4.0,
       f"Apr-Oct {mean(G04, solar.GROWING_SEASON)}")
    ok("and misses it over the months the plant is standing",
       mean(G04, STANDING) < 4.0, f"Nov-Mar {mean(G04, STANDING)}")
    ok("by a margin small enough that only a check would find it",
       0 < 4.0 - mean(G04, STANDING) < 0.5,
       f"short by {round(4.0 - mean(G04, STANDING), 2)} h")

    head("the fault, reproduced: an evergreen passes on its bloom months")
    objs = light(plant("g04"))
    ok("with no winter claim on the entry, nothing objects",
       not objs, show(objs))
    ok("and the bed it stands in is genuinely short of light Nov-Mar",
       design.zone_hours(SUN, SITE, "g04", STANDING) < 4.0,
       design.zone_hours(SUN, SITE, "g04", STANDING))

    head("and the fix: a declared claim, not a guessed one")
    objs = light(plant("g04", winter_active=True))
    ok("a winter-active plant short of winter light objects",
       len(wintery(objs)) == 1, show(objs))
    ok("exactly once, not once per window it could have been judged over",
       len(objs) == 1, show(objs))

    head("THE TRAP: the four that must stay silent")
    # Same bed, same hours, same rating. Only the claim differs.
    dormant = light(plant("g04", name="Pride of Barbados", evergreen=True,
                          winter_active=False,
                          december="ABSENT BY DESIGN. Root-hardy, top-killed "
                                   "by frost; three 12-18 in stubs under mulch"))
    ok("a plant marked evergreen but not winter-active says nothing",
       not dormant, show(dormant))
    ok("`evergreen: true` alone never triggers the check",
       not wintery(light(plant("g04", evergreen=True))),
       show(light(plant("g04", evergreen=True))))
    ok("and `evergreen: false` never suppresses it either",
       len(wintery(light(plant("g04", evergreen=False,
                               winter_active=True)))) == 1,
       "the two fields make different claims and neither implies the other")
    ok("a grass holding dry seed heads is silent on the same numbers",
       not light(plant("g04", name="Inland sea oats", evergreen=False,
                       winter_active=False, bloom=["Jul", "Aug", "Sep"])),
       "it reads beautifully in December and photosynthesises none of it")
    ok("so does a host plant left standing brown on purpose",
       not light(plant("g04", name="Lindheimer's senna", winter_active=False,
                       bloom=["Sep", "Oct"])), "brown, deliberately")
    ok("and one that goes ratty to dormant after the first frost",
       not light(plant("g04", name="Turk's cap", winter_active=False,
                       bloom=list(TURKS_BLOOM))), "ratty to dormant")

    head("the December prose is evidence, and must not be the mechanism")
    ratty = plant("g04", winter_active=True,
                  december="RATTY TO DORMANT. Not a December plant.")
    performs = plant("g04", winter_active=True,
                     december="PERFORMS. Evergreen rosette, flowers in mild "
                              "winters.")
    ok("two entries differing only in their December note get one verdict",
       [o["say"] for o in light(ratty)] == [o["say"] for o in light(performs)],
       "free text written for a person will be reworded, and a check that "
       "turns on the word 'ratty' fails silently and says nothing")
    ok("and a false December note cannot silence a true objection",
       len(wintery(light(ratty))) == 1, show(light(ratty)))

    head("the objection names the plant, the bed, the figure and the window")
    o = first(wintery(light(plant("g04", winter_active=True))))
    say = o["say"]
    ok("the plant, in the field the reader scans first",
       o["about"] == "Four-nerve daisy", o["about"])
    ok("the bed", "zone g04" in say, say)
    ok("the winter figure, to the hundredth",
       f"{mean(G04, STANDING)} h" in say, say)
    ok("the need it is measured against", "4.0 h" in say, say)
    ok("the shortfall, computed rather than left to the reader",
       f"{round(4.0 - mean(G04, STANDING), 2)} h short" in say, say)
    ok("and the window, named the way every other hour figure now is",
       "the standing season, Nov-Mar" in say, say)
    ok("which is not the growing season wearing a winter label",
       "growing season" not in say
       and f"{mean(G04, solar.GROWING_SEASON)} h" not in say, say)
    ok("nor the bloom figure it passed on",
       f"{mean(G04, DAISY_BLOOM)} h" not in say, say)

    head("no corner is offered, because the sunniest one is March's")
    fixes = " ".join(o.get("fix") or ""
                     for o in wintery(light(plant("g04", winter_active=True))))
    best = design.zone_best(SUN, SITE, "g04", STANDING)
    ok("the fixture's sunniest winter cell would clear the floor on its own",
       best >= 4.0, f"best cell Nov-Mar is {best} h")
    ok("and it is March's, the brightest month in the dark window",
       best == max(G04_BEST[solar.MONTHS.index(m)] for m in STANDING)
       == G04_BEST[solar.MONTHS.index("Mar")], best)
    ok("so no 'may work in one corner' is offered",
       "one corner" not in fixes and f"{best} h" not in fixes,
       fixes or "(no fix offered)")
    ok("but a fix is still given, because an objection with no move is a shrug",
       fixes.strip(), fixes or "(no fix offered)")

    head("it never speaks twice about the same shortfall")
    # Rosemary in g03: blooms Nov-Mar, which IS the standing season, so the
    # bloom figure and the winter figure are the same number.
    rosemary = plant("g03", name="Rosemary 'Tuscan Blue' (upright)",
                     bloom=list(STANDING), evergreen=True, winter_active=True)
    objs = light(rosemary)
    ok("a plant whose bloom list already spans winter is refused once",
       len(refused(objs)) == 1, show(objs))
    ok("on the ordinary light objection, not the winter one",
       not wintery(objs) and "wants part sun" in first(objs)["say"], show(objs))
    ok("and the two figures it could have quoted are the same number anyway",
       design.zone_hours(SUN, SITE, "g03", STANDING)
       == design.zone_hours(SUN, SITE, "g03", list(STANDING)),
       "a second line here would repeat a number and offer no new decision")
    dark = light(plant("g03", winter_active=True))
    ok("a winter-active plant already refused on its own window gets one line",
       len(refused(dark)) == 1 and not wintery(dark), show(dark))

    head("a plant with no bloom list at all is still checked")
    bare = plant("g04", winter_active=True, bloom=[])
    bare.pop("bloom")
    objs = light(bare)
    ok("judged over the growing season by default, and it passes there",
       design.zone_hours(SUN, SITE, "g04") >= 4.0,
       design.zone_hours(SUN, SITE, "g04"))
    ok("and the winter branch still objects",
       len(wintery(objs)) == 1, show(objs))
    ok("on the standing-season figure, not the default one",
       f"{mean(G04, STANDING)} h" in first(objs)["say"], show(objs))
    empty = light(plant("g04", winter_active=True, bloom=[], months=[]))
    ok("an empty months list falls back and does not lose the winter check",
       len(wintery(empty)) == 1, show(empty))

    head("a plant carrying its own winter months is not double-counted")
    kale = plant("even", name="Dino kale (transplants)", light="part sun",
                 evergreen=True, winter_active=True, bloom=[],
                 months=["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"])
    ok("a winter crop in a bed that holds its light says nothing",
       not light(kale), show(light(kale)))
    ok("and the bed really is fine in winter, so that is a pass not a skip",
       design.zone_hours(SUN, SITE, "even", STANDING) >= 4.0,
       design.zone_hours(SUN, SITE, "even", STANDING))

    head("severity is a judgement, and it is the same one every time")
    o = first(wintery(light(plant("g04", winter_active=True))))
    ok("a third of an hour short is serious, not blocking",
       o["level"] == "serious", o["level"])
    cliff = plant("cliff", light="full sun", winter_active=True, bloom=[])
    cliff.pop("bloom")
    objs = wintery(light(cliff))
    ok("the cliff bed passes full sun over the growing season",
       design.zone_hours(SUN, SITE, "cliff") >= 6.0,
       design.zone_hours(SUN, SITE, "cliff"))
    ok("and is nearly five hours short of it Nov-Mar",
       6.0 - design.zone_hours(SUN, SITE, "cliff", STANDING) > 4.0,
       design.zone_hours(SUN, SITE, "cliff", STANDING))
    ok("which on the primary check's scale would be blocking three times over",
       design.zone_hours(SUN, SITE, "cliff", STANDING) < 6.0 - 1.5,
       "so this is the case that would escalate if the level were copied")
    ok("and it is still serious, because winter light cannot kill a plant "
       "that has its growing-season hours",
       len(objs) == 1 and first(objs)["level"] == "serious", show(objs))

    head("the plants nobody has decided about are named, not guessed at")
    undecided = design.check_coverage(
        {"plants": [plant("g04", evergreen=True),
                    plant("g04", name="Texas sedge", evergreen=True,
                          light="shade")]},
        SITE, {}, SUN)
    notes = [o for o in undecided if o["about"] == "winter"]
    ok("two evergreens with no winter claim raise one note between them",
       len(notes) == 1, show(notes))
    ok("which counts them and names them",
       notes and "2 plants" in notes[0]["say"]
       and "Texas sedge" in notes[0]["say"], show(notes))
    ok("and says what to set rather than what is missing",
       notes and "winter_active" in (notes[0].get("fix") or ""), show(notes))
    decided = design.check_coverage(
        {"plants": [plant("g04", evergreen=True, winter_active=False,
                          winter_active_why="absent by design, cut to the "
                                            "ground in November")]},
        SITE, {}, SUN)
    ok("an entry that was asked and answered no raises nothing",
       not [o for o in decided if o["about"] == "winter"], show(decided))
    unsourced = design.check_coverage(
        {"plants": [plant("g04", evergreen=True, winter_active=True)]},
        SITE, {}, SUN)
    reasons = [o for o in unsourced if o["about"] == "winter"
               and "no reason" in o["say"]]
    ok("a claim declared with no reason beside it is reported too",
       len(reasons) == 1, show(unsourced))
    ok("because it is a judgement about a plant, not a measurement of the yard",
       reasons and "disagree" in reasons[0]["say"], show(reasons))

    head("one winter, in one place")
    ok("design's winter window IS solar.STANDING_SEASON, not a copy",
       design.WINTER_LIGHT_MONTHS is solar.STANDING_SEASON,
       f"{design.WINTER_LIGHT_MONTHS!r} vs {solar.STANDING_SEASON!r}")
    ok("niches reports a bed's winter over the same constant",
       niches.WINTER == list(solar.STANDING_SEASON), f"{niches.WINTER!r}")
    ok("so the figure a person is shown is the one the linter then judges on",
       design.zone_hours(SUN, SITE, "g04", niches.WINTER)
       == design.zone_hours(SUN, SITE, "g04",
                            list(design.WINTER_LIGHT_MONTHS)),
       "two winter figures for one bed is the fault GROWING was merged to fix")
    ok("and it is not the growing season, which would make it no window at all",
       not set(solar.STANDING_SEASON) & set(solar.GROWING_SEASON),
       f"{solar.STANDING_SEASON!r} overlaps {solar.GROWING_SEASON!r}")
    ok("between them the two windows cover the calendar exactly once",
       sorted(set(solar.STANDING_SEASON) | set(solar.GROWING_SEASON),
              key=solar.MONTHS.index) == list(solar.MONTHS)
       and len(solar.STANDING_SEASON) + len(solar.GROWING_SEASON) == 12,
       f"{solar.STANDING_SEASON!r} + {solar.GROWING_SEASON!r}")
    ok("the standing season is derived, so moving the growing one moves both",
       tuple(m for m in solar.MONTHS if m not in solar.GROWING_SEASON)
       == tuple(sorted(solar.STANDING_SEASON, key=solar.MONTHS.index)),
       "a hand-written winter is the fourth spelling of a season this repo "
       "has had, and the other three drifted")
    ok("and it reads in the order somebody lives it, not from January",
       list(solar.STANDING_SEASON)[0] == "Nov", f"{solar.STANDING_SEASON!r}")
    ok("window_label names it rather than listing five months",
       design.window_label(list(solar.STANDING_SEASON))
       == "the standing season, Nov-Mar",
       design.window_label(list(solar.STANDING_SEASON)))


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose
    run()
    print(f"\n{PASS} of {PASS + FAIL} passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
