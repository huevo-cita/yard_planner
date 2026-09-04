#!/usr/bin/env python3
"""Which months a 6 h threshold is measured over, and whether the text says so.

    python3 tools/test_lightwindow.py
    python3 tools/test_lightwindow.py -v      print the objections in full

`LIGHT_NEED` says full sun is 6 hours. Six hours of what was never stated, and
the two modules that answer it answered differently: `lib.sunmodel` classed a
whole yard on its growing-season mean while `lib.design` compared every plant
against a mean over all twelve months. Same number, same word, two different
claims, and nothing in either output said which.

The twelve-month mean is not a conservative version of the summer one. It is a
different statistic, and it is biased in one direction by the length of the day
alone: open sky at 30 N is 11.92 h averaged over the year against 13.11 h in
summer, so every bed on earth loses over an hour before a fence or a tree is
counted against it. On a real yard that gap withdrew four full-sun plants from
a bed that cleared 6 h in every month they would have been alive in.

So the fixtures here are two beds that disagree with themselves, because a bed
that clears the threshold on either window proves nothing:

  the summer bed      5.62 h over the year, 6.71 h April to October. A full-sun
                      plant in it is refused on the old basis and accepted on
                      the new one. This is the bug, reproduced.

  the deciduous bed   6.43 h over the year, 5.03 h April to October — a crown
                      that leafs out over it in May and drops in November. A
                      full-sun plant here is accepted on the old basis and
                      refused on the new one, which is the half a test can skip
                      and should not: an implementation that lowered the
                      threshold, or took the sunniest months, or took a maximum,
                      passes the summer bed and fails this one.

And the labelling, which is half the fix. An hour figure a reader is going to
hold against a nursery tag has to say what season it averaged, and the message
this replaced said "over the year" whatever it had actually measured.

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

# Hours by month, in solar.MONTHS order. Both profiles are shaped like real
# beds rather than chosen to make arithmetic tidy, and both straddle the 6.0 h
# line in opposite directions depending on which window is taken.
SUMMER_BED = [3.4, 4.3, 5.4, 6.3, 6.9, 7.3, 7.4, 7.0, 6.4, 5.7, 4.1, 3.2]
DECIDUOUS_BED = [8.6, 8.6, 8.0, 5.4, 5.0, 4.6, 4.6, 4.8, 5.2, 5.6, 8.0, 8.8]

# The sunniest cell in the deciduous bed is a winter figure: bare ground under
# a bare crown in January, at 12.2 h. No cell in it reaches 6 h between April
# and October. A `zone_best` reading the wrong window offers that January
# figure as "this may work in one corner", which is advice to plant a summer
# perennial in a patch that is only bright while it is dormant.
DECIDUOUS_BEST = [12.0, 11.8, 10.5, 5.9, 5.6, 5.3, 5.3, 5.5, 5.8, 5.9, 10.6,
                  12.2]


def zone(hours, best=None):
    best = best or [h + 0.8 for h in hours]
    return {m: {"effective": h, "clear": h, "best_cell": b}
            for m, h, b in zip(solar.MONTHS, hours, best)}


SUN = {"by_zone_and_month": {
    "summer_bed": zone(SUMMER_BED),
    "deciduous_bed": zone(DECIDUOUS_BED, DECIDUOUS_BEST),
}}

SITE = {
    "zones": {
        "summer_bed": {"style": "bed", "area_sqft": 74.0, "kind": "border",
                       "usable_depth_ft": 4.0},
        "deciduous_bed": {"style": "bed", "area_sqft": 60.0, "kind": "border",
                          "usable_depth_ft": 3.5},
    },
    "climate": {"heat": {"days_over_95f_per_year": 45.8}},
}


def plant(zone_key, light="full sun", **kw):
    p = {"name": "Damianita", "botanical": "Chrysactinia mexicana",
         "zone": zone_key, "count": 4, "light": light, "water": "low",
         "mature_spread_ft": 1.5, "mature_height_ft": 1.25,
         "source": "test fixture"}
    p.update(kw)
    return p


def light(p):
    return design.check_light(p, SUN, SITE)


def blocked(objs):
    return [o for o in objs if o["level"] in ("blocking", "serious")]


def mean(hours, months):
    idx = [solar.MONTHS.index(m) for m in months]
    return round(sum(hours[i] for i in idx) / len(idx), 2)


def run():
    head("the fixtures disagree with themselves, or they prove nothing")
    ok("the summer bed misses 6 h over the year and clears it Apr-Oct",
       mean(SUMMER_BED, solar.MONTHS) < 6.0
       <= mean(SUMMER_BED, solar.GROWING_SEASON),
       f"year {mean(SUMMER_BED, solar.MONTHS)}, "
       f"growing {mean(SUMMER_BED, solar.GROWING_SEASON)}")
    ok("and the deciduous bed does the opposite",
       mean(DECIDUOUS_BED, solar.GROWING_SEASON) < 6.0
       <= mean(DECIDUOUS_BED, solar.MONTHS),
       f"year {mean(DECIDUOUS_BED, solar.MONTHS)}, "
       f"growing {mean(DECIDUOUS_BED, solar.GROWING_SEASON)}")

    head("a plant naming no months is judged over the growing season")
    objs = light(plant("summer_bed"))
    ok("the bed that clears 6 h all summer is not refused for December light",
       not blocked(objs), show(objs))
    ok("and the twelve-month mean, which is what refused it, would still",
       blocked(design.check_light(
           plant("summer_bed", months=list(solar.MONTHS)), SUN, SITE)),
       "if this passes too, the fixture is not testing anything")

    objs = light(plant("deciduous_bed"))
    ok("a bed bright only out of season IS refused, though the year says 6.43",
       blocked(objs), show(objs))
    ok("and it is refused on the summer figure, not on some lowered threshold",
       any("5.03" in o["say"] for o in objs), show(objs))
    ok("nor is it rescued by the sunniest cell, which is a January reading",
       not any("one corner of it" in (o.get("fix") or "") for o in objs),
       show(objs))

    head("a plant that names its own months keeps them")
    winter = {"months": ["Nov", "Dec", "Jan", "Feb"]}
    ok("a winter annual under a bare crown passes on its own months",
       not blocked(light(plant("deciduous_bed", **winter))),
       show(light(plant("deciduous_bed", **winter))))
    ok("and the same annual in the summer bed still fails on them",
       blocked(light(plant("summer_bed", **winter))),
       show(light(plant("summer_bed", **winter))))
    ok("bloom months are still the fallback when `months` is absent",
       blocked(light(plant("summer_bed", bloom=["Dec", "Jan", "Feb"]))),
       "bloom is the second fallback and this change did not touch it")

    head("every hour figure says which season it is a mean of")
    objs = light(plant("deciduous_bed"))
    ok("the default window is named rather than called 'the year'",
       all("growing season, Apr-Oct" in o["say"] for o in objs)
       and not any("over the year" in o["say"] for o in objs),
       show(objs))
    objs = light(plant("summer_bed", **winter))
    ok("and a plant's own months are named one by one",
       all("Nov, Dec, Jan, Feb" in o["say"] for o in objs), show(objs))
    ok("window_label still calls all twelve months the year",
       design.window_label(list(solar.MONTHS)) == "the year",
       design.window_label(list(solar.MONTHS)))

    head("the afternoon-exposure objection quotes the same window")
    timed = dict(SUN, sun_timing={
        "summer_bed": {"after_1pm_share": 0.93, "first_sun_clock": 13.1}})
    objs = design.check_sun_timing(
        {"plants": [plant("summer_bed")]}, timed, SITE)
    ok("it fires on a bed taking 93 percent of its sun after one o'clock",
       len(objs) == 1, show(objs))
    ok("and its hour figure says what it averaged too",
       objs and "growing season, Apr-Oct" in objs[0]["say"], show(objs))
    ok("which is the growing-season number, not the annual one",
       objs and f"{mean(SUMMER_BED, solar.GROWING_SEASON)} h" in objs[0]["say"],
       show(objs))

    head("one definition, in one place")
    ok("design's default IS solar.GROWING_SEASON, not a copy of it",
       design.DEFAULT_LIGHT_MONTHS is solar.GROWING_SEASON,
       f"{design.DEFAULT_LIGHT_MONTHS!r} vs {solar.GROWING_SEASON!r}")
    ok("so zone_hours with no months equals zone_hours over that constant",
       design.zone_hours(SUN, SITE, "deciduous_bed")
       == design.zone_hours(SUN, SITE, "deciduous_bed",
                            list(solar.GROWING_SEASON)),
       "a second hard-coded window is the same bug in a new place")
    ok("and zone_best answers over the same window as zone_hours",
       design.zone_best(SUN, SITE, "deciduous_bed")
       == max(DECIDUOUS_BEST[solar.MONTHS.index(m)]
              for m in solar.GROWING_SEASON),
       f"got {design.zone_best(SUN, SITE, 'deciduous_bed')}")
    ok("the caller who wants the annual mean has to ask for it by name",
       design.zone_hours(SUN, SITE, "deciduous_bed", list(solar.MONTHS))
       == mean(DECIDUOUS_BED, solar.MONTHS),
       "a figure whose window nobody stated is how this went wrong")


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
