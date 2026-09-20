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


# ----------------------------------------- which months the scorch branch means

# The same fault as the rest of this file, one level down and found after it was
# fixed. `check_light` learned to judge a plant over its own window; the scorch
# branch underneath it did not follow. It kept reading
# `climate.heat.days_over_95f_per_year`, an ANNUAL count, and kept asserting "it
# will scorch in July whatever the watering" under an hour figure that was a mean
# over whatever window the plant happened to name. A cyclamen lifted in March was
# told that 5.45 h of December-to-March sun proved it would burn in July.
#
# Austin's own monthly series, from thirty years of ERA5 daily maxima. Jun, Jul
# and Aug clear the six-day bar; September's 4.3 does not, and neither does May.
AUSTIN_HEAT = {"Jan": 0.0, "Feb": 0.0, "Mar": 0.0, "Apr": 0.2, "May": 1.6,
               "Jun": 7.1, "Jul": 14.1, "Aug": 18.2, "Sep": 4.3, "Oct": 0.2,
               "Nov": 0.0, "Dec": 0.0}

# A climate with MORE days over 95 F in the year than Austin and not one hot
# month in it — four a month, every month, which is a place with no summer and no
# winter. The old branch fired here, because 48 > 20 was the whole of its test.
# Anything still reading the annual count passes every fixture below except this
# one.
EVEN_HEAT = {m: 4.0 for m in solar.MONTHS}

# Three beds, each shaped to break a different plausible version of the fix.
#
#   blazing       hot all summer and blazing in August. The plain case, and the
#                 bed the winter annual stands in — so a silence here has to come
#                 from the plant's window and cannot come from the bed.
#   june_peak     brightest in June at 9.0 h and hottest in August at 5.0 h. An
#                 implementation that picks the brightest hot month quotes 9.0 h
#                 and names June, in a month with 7.1 hot days rather than 18.2.
#   august_only   June 3.8, July 4.2, August 5.2. The mean of its hot months is
#                 4.4 h, under the 4.5 h line a shade plant draws, and August is
#                 over it. Averaging the hot months together lets this bed off,
#                 and the plant still burns in August.
BLAZING = [5.6, 6.0, 4.6, 6.9, 8.8, 9.0, 8.9, 8.0, 5.4, 3.7, 3.5, 5.6]
JUNE_PEAK = [3.0, 3.2, 6.0, 6.0, 7.0, 9.0, 6.0, 5.0, 4.0, 3.0, 2.8, 2.9]
AUGUST_ONLY = [2.0, 2.2, 2.4, 3.0, 3.4, 3.8, 4.2, 5.2, 3.6, 2.6, 2.0, 1.9]

SCORCH_SUN = {"by_zone_and_month": {"blazing": zone(BLAZING),
                                    "june_peak": zone(JUNE_PEAK),
                                    "august_only": zone(AUGUST_ONLY)}}


def scorch_site(heat=None):
    return {
        "yard": "fixture",
        "zones": {k: {"style": "bed", "kind": "border", "area_sqft": 60.0,
                      "usable_depth_ft": 3.5}
                  for k in ("blazing", "june_peak", "august_only")},
        "climate": {"heat": dict({"days_over_95f_per_year": 45.8},
                                 **({"days_over_95f_by_month": heat}
                                    if heat is not None else {}))},
    }


SCORCH_SITE = scorch_site(AUSTIN_HEAT)


def shade_plant(zone_key, light="shade", **kw):
    p = {"name": "Texas sedge", "zone": zone_key, "count": 5, "light": light,
         "water": "low", "mature_spread_ft": 1.0, "mature_height_ft": 0.8,
         "source": "test fixture"}
    p.update(kw)
    return p


def burns(p, site=None):
    return [o for o in design.check_light(p, SCORCH_SUN, site or SCORCH_SITE)
            if "scorch" in o["say"]]


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

    head("the fixtures disagree about which month is worst, or prove nothing")
    ok("the June-peak bed is brightest in June and hottest in August",
       max(solar.MONTHS, key=lambda m: JUNE_PEAK[solar.MONTHS.index(m)]) == "Jun"
       and max(AUSTIN_HEAT, key=lambda m: AUSTIN_HEAT[m]) == "Aug",
       f"June {JUNE_PEAK[5]} h, August {JUNE_PEAK[7]} h")
    ok("and the August-only bed clears the shade line on the mean of Jun-Aug",
       mean(AUGUST_ONLY, ["Jun", "Jul", "Aug"]) < 4.5 <= AUGUST_ONLY[7],
       f"mean {mean(AUGUST_ONLY, ['Jun', 'Jul', 'Aug'])}, "
       f"August {AUGUST_ONLY[7]}")
    ok("the even climate has more hot days a year than Austin",
       sum(EVEN_HEAT.values()) > sum(AUSTIN_HEAT.values()),
       f"{sum(EVEN_HEAT.values())} against {sum(AUSTIN_HEAT.values())}")
    ok("and not one month in it clears the bar Austin's June clears",
       design.hot_months(scorch_site(EVEN_HEAT)) == []
       and design.hot_months(SCORCH_SITE) == ["Jun", "Jul", "Aug"],
       f"{design.hot_months(scorch_site(EVEN_HEAT))!r} vs "
       f"{design.hot_months(SCORCH_SITE)!r}")

    head("a winter annual is not told it will scorch in the summer")
    winter_bulb = shade_plant("blazing", annual=True,
                              months=["Dec", "Jan", "Feb", "Mar"],
                              bloom=["Dec", "Jan", "Feb", "Mar"])
    ok("it says nothing at all, in the brightest bed on the fixture",
       not burns(winter_bulb),
       show(design.check_light(winter_bulb, SCORCH_SUN, SCORCH_SITE)))
    ok("and the bed itself would still scorch something that stayed in it",
       burns(shade_plant("blazing")),
       "if this were quiet too, the silence above would be the bed and not "
       "the window, and the fixture would be proving nothing")
    ok("the annual's own window is over the line, so it is not passing on hours",
       design.zone_hours(SCORCH_SUN, SCORCH_SITE, "blazing",
                         ["Dec", "Jan", "Feb", "Mar"]) > 4.5,
       design.zone_hours(SCORCH_SUN, SCORCH_SITE, "blazing",
                         ["Dec", "Jan", "Feb", "Mar"]))

    head("an evergreen judged on a spring bloom is judged on August instead")
    spring_bloom = shade_plant("june_peak", evergreen=True,
                               bloom=["Mar", "Apr"])
    objs = burns(spring_bloom)
    ok("it still objects, because it is standing in the bed all summer",
       len(objs) == 1, show(objs))
    ok("and the figure is August's, not the bloom window's",
       objs and f"{JUNE_PEAK[7]} h in Aug" in objs[0]["say"]
       and f"{mean(JUNE_PEAK, ['Mar', 'Apr'])} h" not in objs[0]["say"],
       show(objs))
    ok("bloom is not consulted for presence at all: Mar-Apr is not hot here",
       design.standing_months(spring_bloom) == list(design.MONTHS),
       design.standing_months(spring_bloom))
    ok("and the month the sentence names is the month it measured",
       objs and objs[0]["say"].count("Aug") >= 2
       and "Jun," in objs[0]["say"] and " in Jun " not in objs[0]["say"],
       show(objs))
    ok("so the brightest hot month, June at 9.0 h, is not what it quotes",
       objs and f"{JUNE_PEAK[5]} h" not in objs[0]["say"], show(objs))

    head("a plant whose own window already contains the summer is unchanged")
    long_bloom = shade_plant("blazing", light="part shade",
                             bloom=["Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                    "Oct", "Nov"])
    ok("it objects, as it did before any of this",
       len(burns(long_bloom)) == 1, show(burns(long_bloom)))
    ok("at the part shade threshold rather than the shade one",
       burns(long_bloom) and "3.0 h its part shade rating" in
       burns(long_bloom)[0]["say"], show(burns(long_bloom)))

    head("the hot months are not averaged together")
    objs = burns(shade_plant("august_only", evergreen=True))
    ok("a bed under the line on the mean of Jun-Aug still objects on August",
       len(objs) == 1, show(objs))
    ok("quoting August's own 5.2 h and not the 4.4 h mean of the three",
       objs and f"{AUGUST_ONLY[7]} h in Aug" in objs[0]["say"]
       and f"{mean(AUGUST_ONLY, ['Jun', 'Jul', 'Aug'])} h" not in objs[0]["say"],
       show(objs))

    head("the hot months come from the yard, and an annual count is not one")
    even = scorch_site(EVEN_HEAT)
    ok("a climate with no hot month scorches nothing, at 48 hot days a year",
       not burns(shade_plant("blazing"), even),
       show(design.check_light(shade_plant("blazing"), SCORCH_SUN, even)))
    ok("and the same plant in the same bed burns under Austin's months",
       burns(shade_plant("blazing")),
       "if both were quiet the fixture would not separate the two climates")
    ok("September is not a hot month here, at 4.3 days",
       "Sep" not in design.hot_months(SCORCH_SITE),
       design.hot_months(SCORCH_SITE))
    ok("the threshold is a policy constant and the series is per-yard data",
       isinstance(design.HOT_MONTH_DAYS, float)
       and design.hot_months({"climate": {}}) is None,
       "a yard that has never been asked answers None, not an empty list")

    head("and a yard with no monthly series says so instead of going quiet")
    blind = scorch_site(None)
    ok("no scorch objection is raised, because none can be honestly made",
       not burns(shade_plant("blazing"), blind),
       show(design.check_light(shade_plant("blazing"), SCORCH_SUN, blind)))
    cov = design.check_coverage(
        {"plants": [shade_plant("blazing"),
                    shade_plant("june_peak", name="Cyclamen")]},
        blind, {}, SCORCH_SUN)
    heat = [o for o in cov if o["about"] == "heat"]
    ok("but the objection list names what that disabled, and for how many",
       len(heat) == 1 and "2 shade-rated plants" in heat[0]["say"], show(cov))
    ok("and the fix says how to derive it rather than what to guess",
       heat and "--heat-months" in (heat[0].get("fix") or ""), show(heat))
    ok("a yard that HAS the series says nothing about it",
       not [o for o in design.check_coverage(
           {"plants": [shade_plant("blazing")]}, SCORCH_SITE, {}, SCORCH_SUN)
            if o["about"] == "heat"],
       "a note that never goes away is one nobody reads")

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
