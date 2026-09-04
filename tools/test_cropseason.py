#!/usr/bin/env python3
"""A plant judged over a season it is not alive in.

    python3 tools/test_cropseason.py

`design.check_light` falls back to `solar.GROWING_SEASON` when a plant names no
months of its own, and April to October is right for almost everything in a
garden. It is exactly wrong for the one bed that is planted in autumn and
emptied in spring.

On the yard this was written against, thirteen cool-season vegetables carried
neither `months` nor `bloom`. They were measured over 6.46 h April to October
when the season they actually occupy reads 5.41 h — the bed is over an hour
brighter in the months these plants are not there. That produced three
`serious` objections warning that spinach, lettuce and chives "will scorch in
July whatever the watering", against a bed harvested by March.

What makes this worth a suite of its own is the SHAPE of the fix, which is a
month list per plant and therefore has three ways to be wrong that all look
like success:

  the window comes out empty      a crop sown in September and harvested in
                                  March is `MONTHS[8:2]`, which is the empty
                                  list. `_series` then finds no months, returns
                                  nothing, and `check_light` reports that it
                                  could not run — which reads exactly like a
                                  mistyped zone name and gets chased as one.

  the window comes out truncated  the same span taken as `Sep..Dec` drops
                                  January to March, which on the fixture below
                                  is the darkest end of the season and the half
                                  that decides the verdict.

  the true objection goes too     the danger in silencing three wrong
                                  objections is silencing a right one with
                                  them. A crop that genuinely has too little
                                  light in the months it grows must still
                                  refuse, and an implementation that widened
                                  the scorch margin, or ignored `months`, or
                                  took the brightest month of the window,
                                  passes the first half of this file and fails
                                  the second.

So the fixture is one bed with two crops in it that disagree about the same
ground, taken from the real bed's measured profile rather than invented.

Runs entirely on dicts in memory. No yard is read or written.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import design, solar  # noqa: E402  (after sys.path)

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

# The raised vegetable bed on cloverleaf-austin, measured. Jan through Dec.
# It is the shape that makes this bug possible: bright enough in high summer to
# clear every threshold, and over an hour darker across the autumn and winter
# the crops are actually in it. October and November are its floor, because
# that is when the sun sits behind the neighbours; December rebounds as their
# hackberry drops.
#
#   Apr-Oct   6.46 h        the default, and the seven months nothing is sown
#   Sep-Mar   5.37 h        the window the autumn crops occupy
#   Sep-Dec   5.09 h        the truncated version, if a range stops at December
VEG_BED = [5.65, 5.97, 5.65, 6.26, 7.09, 7.40, 7.25, 6.63, 5.81, 4.76, 4.25,
           5.52]

# A second bed under the same roofline but deeper in the shade of the house, so
# that a winter crop in it is genuinely short of light rather than merely
# measured over the wrong months. Its summer clears part sun comfortably and
# its own autumn-to-spring window does not, which is what a real objection
# looks like: the crop is not fine and no change of window makes it fine.
#
#   Apr-Oct   4.94 h        clears the 4.0 h part-sun floor
#   Sep-Mar   2.60 h        does not, and is 1.4 h short of it
DARK_BED = [2.40, 2.60, 2.70, 3.90, 5.30, 6.20, 6.10, 5.20, 3.60, 2.60, 2.10,
            2.30]

# The brightest cell in the dark bed reaches 4.2 h in December — one patch by
# the corner of the house that the low winter sun gets under. It clears the
# part-sun floor on its own and the bed does not, so an implementation that
# rescued a refusal with `zone_best` would report that a winter crop "may work
# in one corner", which is a real corner and four square feet of it.
DARK_BEST = [4.2, 4.2, 4.0, 5.0, 6.4, 7.3, 7.2, 6.3, 4.7, 3.7, 3.6, 4.2]


def zone(hours, best=None):
    best = best or [h + 0.6 for h in hours]
    return {m: {"effective": h, "clear": h, "best_cell": b}
            for m, h, b in zip(solar.MONTHS, hours, best)}


SUN = {"by_zone_and_month": {"veg_bed": zone(VEG_BED),
                             "dark_bed": zone(DARK_BED, DARK_BEST)}}

SITE = {
    "zones": {
        "veg_bed": {"style": "bed", "kind": "grid", "squares": 32,
                    "area_sqft": 36.0, "usable_depth_ft": 4.0},
        "dark_bed": {"style": "bed", "kind": "border", "area_sqft": 30.0,
                     "usable_depth_ft": 3.5},
    },
    # The scorch branch needs a hot climate to fire at all. Austin's own figure,
    # so the false objections this file is about are reproduced rather than
    # approximated.
    "climate": {"heat": {"days_over_95f_per_year": 45.8}},
}

# Sown in September, cut until March. Seven months, and it crosses New Year,
# which is the whole difficulty: written as a slice of the calendar it is empty.
AUTUMN_TO_SPRING = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


def crop(zone_key, light="part shade", **kw):
    p = {"name": "Spinach (direct sown)", "zone": zone_key, "count": 2,
         "light": light, "water": "moderate", "annual": True,
         "mature_spread_ft": 0.8, "mature_height_ft": 0.7,
         "bloom": [], "source": "test fixture"}
    p.update(kw)
    return p


def light(p):
    return design.check_light(p, SUN, SITE)


def refused(objs):
    return [o for o in objs if o["level"] in ("blocking", "serious")]


def scorch(objs):
    return [o for o in objs if "scorch" in o["say"]]


def mean(hours, months):
    idx = [solar.MONTHS.index(m) for m in months]
    return round(sum(hours[i] for i in idx) / len(idx), 2)


def run():
    head("the fixtures disagree with themselves, or they prove nothing")
    ok("the veg bed clears the scorch bound Apr-Oct and misses it Sep-Mar",
       mean(VEG_BED, solar.GROWING_SEASON) > 6.0
       > mean(VEG_BED, AUTUMN_TO_SPRING),
       f"Apr-Oct {mean(VEG_BED, solar.GROWING_SEASON)}, "
       f"Sep-Mar {mean(VEG_BED, AUTUMN_TO_SPRING)}")
    ok("and the dark bed clears part sun Apr-Oct and misses it Sep-Mar",
       mean(DARK_BED, solar.GROWING_SEASON) >= 4.0
       > mean(DARK_BED, AUTUMN_TO_SPRING),
       f"Apr-Oct {mean(DARK_BED, solar.GROWING_SEASON)}, "
       f"Sep-Mar {mean(DARK_BED, AUTUMN_TO_SPRING)}")
    ok("a Sep-Dec truncation is a different number from the whole window",
       mean(VEG_BED, ["Sep", "Oct", "Nov", "Dec"])
       != mean(VEG_BED, AUTUMN_TO_SPRING),
       "if these agreed, nothing below would catch a truncated window")

    head("the fault, reproduced: a winter crop judged over the summer")
    objs = light(crop("veg_bed"))
    ok("with no months it is told it will scorch in July",
       len(scorch(objs)) == 1, show(objs))
    ok("on the summer figure, which is the one it should not be judged on",
       objs and f"{mean(VEG_BED, solar.GROWING_SEASON)} h" in objs[0]["say"],
       show(objs))

    head("and the fix: its own months, spanning the year boundary")
    objs = light(crop("veg_bed", months=AUTUMN_TO_SPRING))
    ok("the scorch objection is gone",
       not scorch(objs), show(objs))
    ok("and nothing replaced it — the crop has the light it needs",
       not objs, show(objs))
    ok("it was judged over its own seven months, not a slice of them",
       design.zone_hours(SUN, SITE, "veg_bed", AUTUMN_TO_SPRING)
       == mean(VEG_BED, AUTUMN_TO_SPRING),
       f"got {design.zone_hours(SUN, SITE, 'veg_bed', AUTUMN_TO_SPRING)}, "
       f"want {mean(VEG_BED, AUTUMN_TO_SPRING)}")
    ok("a window ending at December would have given a different figure",
       design.zone_hours(SUN, SITE, "veg_bed", ["Sep", "Oct", "Nov", "Dec"])
       != design.zone_hours(SUN, SITE, "veg_bed", AUTUMN_TO_SPRING),
       "a truncated season is the quiet way to get this wrong")
    ok("an empty window is not silently treated as the default either",
       light(crop("veg_bed", months=[]))
       and scorch(light(crop("veg_bed", months=[]))),
       "an empty list falls back, which is why the months are written out "
       "one by one rather than sliced out of the calendar")

    head("and the objection names the season it measured")
    objs = light(crop("veg_bed", months=AUTUMN_TO_SPRING, light="full sun"))
    ok("a refusal on a wrap-around window says which months",
       objs and "Sep, Oct, Nov, Dec, Jan, Feb, Mar" in objs[0]["say"],
       show(objs))
    ok("and does not call it the growing season",
       objs and "growing season" not in objs[0]["say"], show(objs))

    head("the objection that must NOT disappear with them")
    objs = light(crop("dark_bed", light="part sun", months=AUTUMN_TO_SPRING))
    ok("a crop short of light in its OWN months is still refused",
       refused(objs), show(objs))
    ok("and refused on its own winter figure, not on a summer one",
       objs and f"{mean(DARK_BED, AUTUMN_TO_SPRING)} h" in objs[0]["say"],
       show(objs))
    ok("the same crop passes over the default window, which is the trap",
       not refused(light(crop("dark_bed", light="part sun"))),
       "if this refused too, the fixture would not be testing the direction "
       "that matters — that giving a plant its own months can REFUSE it")
    fixes = " ".join(o.get("fix") or "" for o in objs)
    ok("the corner it is offered is one that is bright in the crop's months",
       f"{max(DARK_BEST[solar.MONTHS.index(m)] for m in AUTUMN_TO_SPRING)} h"
       in fixes, fixes or "(no fix offered)")
    ok("and not the June corner, which is the same bug in the escape hatch",
       f"{max(DARK_BEST)} h" not in fixes,
       "offering a winter crop a patch that is only bright in June is how a "
       "refusal gets talked out of by the wrong half of the year")
    ok("so zone_best answers over the crop's months, not over the year",
       design.zone_best(SUN, SITE, "dark_bed", AUTUMN_TO_SPRING)
       == max(DARK_BEST[solar.MONTHS.index(m)] for m in AUTUMN_TO_SPRING)
       != design.zone_best(SUN, SITE, "dark_bed", list(solar.MONTHS)),
       f"got {design.zone_best(SUN, SITE, 'dark_bed', AUTUMN_TO_SPRING)}")

    head("a window is a set of months, not an order of them")
    ok("Sep-first and Jan-first spellings of one season agree exactly",
       design.zone_hours(SUN, SITE, "veg_bed", AUTUMN_TO_SPRING)
       == design.zone_hours(SUN, SITE, "veg_bed",
                            sorted(AUTUMN_TO_SPRING,
                                   key=solar.MONTHS.index)),
       "otherwise tidying a list into calendar order moves the answer")
    ok("a year-round perennial gets all twelve months and is told so",
       design.window_label(list(solar.MONTHS)) == "the year"
       and design.zone_hours(SUN, SITE, "veg_bed", list(solar.MONTHS))
       == mean(VEG_BED, solar.MONTHS),
       "the one thing in a bed of annuals that IS there in July")

    head("the default stays the default, and stops being invisible")
    ok("a plant naming nothing is still judged over the growing season",
       design.zone_hours(SUN, SITE, "veg_bed")
       == mean(VEG_BED, solar.GROWING_SEASON),
       "the fix for this was data; changing the fallback would move every "
       "other bed on every yard")
    cov = design.check_coverage(
        {"plants": [crop("veg_bed"), crop("veg_bed", name="Lettuce")]},
        SITE, {}, SUN)
    lights = [o for o in cov if o["about"] == "light"]
    ok("but the objection list now says how many leaned on it",
       len(lights) == 1 and "2 plants" in lights[0]["say"], show(cov))
    ok("and names them, so the list is actionable rather than a count",
       lights and "Spinach (direct sown)" in lights[0]["say"]
       and "Lettuce" in lights[0]["say"], show(lights))
    quiet = design.check_coverage(
        {"plants": [crop("veg_bed", months=AUTUMN_TO_SPRING),
                    crop("veg_bed", name="Calendula", bloom=["Nov", "Dec"])]},
        SITE, {}, SUN)
    ok("a bed where every plant carries its season says nothing at all",
       not [o for o in quiet if o["about"] == "light"], show(quiet))


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
