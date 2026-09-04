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
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import design, gaps, niches, solar, sunmodel  # noqa: E402

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


# ------------------------------------------------- the yard the summary lies about

# A yard shaped so that April-September and April-October give DIFFERENT nursery
# labels, because a yard clearing 6 h on either window cannot tell the two
# implementations apart. October is the pivot: the bed holds 6 h through
# September and then the sun drops behind something to the south-west, which is
# the ordinary shape of an autumn in a built-up lot and is exactly what the real
# raised bed on cloverleaf-austin does, less steeply — 5.81 h in September
# against 4.76 h in October.
#
#   Apr-Sep   6.45 h   full sun     <- what the old headline published
#   Apr-Oct   5.97 h   part sun     <- what design.check_light judges against
#   the year  5.14 h   part sun
#
# The annual mean lands on the same LABEL as the correct answer and on a
# different NUMBER, so the assertions below check both. An implementation that
# quietly fell back to twelve months would otherwise pass on the category alone.
OCTOBER_CLIFF = [4.0, 4.4, 5.0, 6.1, 6.6, 6.9, 6.8, 6.3, 6.0, 3.1, 2.9, 3.6]


def yard_table(hours):
    return {"Whole yard": {m: {"effective": h, "clear": h, "best_cell": h + 0.5}
                           for m, h in zip(solar.MONTHS, hours)}}


# ---------------------------------------------- a season written out somewhere else

_MONTH_LITERAL = re.compile(
    r"""['"](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)['"]""")
_JOIN = re.compile(r",\s*")


def season_literals(path):
    """Runs of five to eleven consecutive months written out in a source file.

    This is the shape of the bug rather than any one instance of it. Twelve
    months in a row is the calendar and means one thing to everybody; four
    scattered months is a figure's caption. A run of five to eleven CONSECUTIVE
    months is somebody spelling out a season, and the only file entitled to do
    that is `solar.py`.

    Written as a scan of the source rather than as a list of the four constants
    that were wrong, because naming them catches the four that have already been
    found and this catches the fifth.
    """
    src = open(path).read()
    toks = [(m.start(), m.end(), m.group(1))
            for m in _MONTH_LITERAL.finditer(src)]
    runs, run = [], []
    for t in toks:
        if run and _JOIN.fullmatch(src[run[-1][1]:t[0]]):
            run.append(t)
        else:
            runs.append(run)
            run = [t]
    runs.append(run)
    out = []
    for r in runs:
        names = [x[2] for x in r]
        if not 5 <= len(names) <= 11:
            continue
        i = solar.MONTHS.index(names[0])
        if names == [solar.MONTHS[(i + k) % 12] for k in range(len(names))]:
            out.append((src[:r[0][0]].count("\n") + 1, names))
    return out


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

    head("the fixture disagrees with itself, or the summary proves nothing")
    ok("Apr-Sep calls the October-cliff yard full sun",
       sunmodel.light_category(
           mean(OCTOBER_CLIFF, ["Apr", "May", "Jun", "Jul", "Aug", "Sep"]))
       == "full sun",
       mean(OCTOBER_CLIFF, ["Apr", "May", "Jun", "Jul", "Aug", "Sep"]))
    ok("and Apr-Oct calls the same yard part sun",
       sunmodel.light_category(mean(OCTOBER_CLIFF, solar.GROWING_SEASON))
       == "part sun",
       mean(OCTOBER_CLIFF, solar.GROWING_SEASON))

    head("sunmodel publishes the window design judges on, not one of its own")
    s = sunmodel.summary(yard_table(OCTOBER_CLIFF))
    ok("the headline category is the Apr-Oct one",
       s["light_category"] == "part sun",
       f"{s['light_category']} at {s['growing_season_mean_hours']} h")
    ok("and the headline figure is the Apr-Oct mean, to the hundredth",
       s["growing_season_mean_hours"]
       == mean(OCTOBER_CLIFF, solar.GROWING_SEASON),
       f"got {s['growing_season_mean_hours']}, "
       f"Apr-Sep is {mean(OCTOBER_CLIFF, ['Apr','May','Jun','Jul','Aug','Sep'])}"
       f", the year is {mean(OCTOBER_CLIFF, solar.MONTHS)}")
    ok("which is not the annual mean wearing the right label",
       s["growing_season_mean_hours"] != mean(OCTOBER_CLIFF, solar.MONTHS),
       "the year lands on 'part sun' too, so the category alone proves nothing")
    ok("the figure carries the months it averaged, so nothing has to guess",
       s["growing_season_months"] == list(solar.GROWING_SEASON),
       s.get("growing_season_months"))
    ok("and sunmodel and design agree to the hundredth on the same table",
       s["growing_season_mean_hours"]
       == design.zone_hours({"by_zone_and_month": yard_table(OCTOBER_CLIFF)},
                            {"zones": {}}, "Whole yard"),
       "two published growing-season figures for one yard is the whole bug")

    head("the three-month probe is a sample, and says so")
    ok("gaps probes over solar.SEASON_SAMPLE, not a copy of it",
       gaps.PROBE_MONTHS is solar.SEASON_SAMPLE,
       f"{gaps.PROBE_MONTHS!r} vs {solar.SEASON_SAMPLE!r}")
    ok("and zone_timing samples the same three months",
       sunmodel.zone_timing.__defaults__[0] is solar.SEASON_SAMPLE,
       f"{sunmodel.zone_timing.__defaults__[0]!r}")
    ok("the sample is drawn from the window",
       set(solar.SEASON_SAMPLE) < set(solar.GROWING_SEASON),
       "a sample of months the window excludes is not a sample of it")
    ok("but it is not the window, and a test that let it become one is no test",
       len(solar.SEASON_SAMPLE) < len(solar.GROWING_SEASON),
       "these are different objects on purpose: one is for spreads, one for "
       "levels, and they differ by 0.28 h on the real yard")

    head("niches budgets slots against the series the linter judges them on")
    ok("niches.GROWING is solar.GROWING_SEASON, spelt as a list",
       niches.GROWING == list(solar.GROWING_SEASON),
       f"{niches.GROWING!r}")
    ok("so a niche's hours ARE what zone_hours answers with no months given",
       design.zone_hours(SUN, SITE, "deciduous_bed", niches.GROWING)
       == design.zone_hours(SUN, SITE, "deciduous_bed"),
       "a slot budgeted on one window and linted on another offers candidates "
       "the linter then rejects — which is what the module's own docstring "
       "says it must not do")
    ok("and winter stays a separate claim rather than being averaged in",
       not set(niches.WINTER) & set(niches.GROWING),
       f"{niches.WINTER!r} overlaps {niches.GROWING!r}")

    head("nowhere else in the engine spells a season out")
    libdir = os.path.join(ROOT, "lib")
    found = []
    for fn in sorted(os.listdir(libdir)):
        if fn.endswith(".py"):
            found += [(fn, n, ms)
                      for n, ms in season_literals(os.path.join(libdir, fn))]
    ok("exactly one five-to-eleven-month run of consecutive months in lib/",
       len(found) == 1,
       "\n".join(f"{fn}:{n} {ms}" for fn, n, ms in found) or "(none at all)")
    ok("and it is solar.GROWING_SEASON itself",
       found and found[0][0] == "solar.py"
       and found[0][2] == list(solar.GROWING_SEASON),
       f"{found!r}")


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
