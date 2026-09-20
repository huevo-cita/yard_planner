#!/usr/bin/env python3
"""Frost dates and season length, computed from thirty years of daily weather.

    python3 -m lib.climate <slug> [--years 30] [--write]
    python3 -m lib.climate --at 39.7392 -104.9903

Most frost-date advice is a station average from a weather station that may be
twenty miles away, quoted without saying what the spread was. This instead pulls
thirty years of daily minimum and maximum temperature for the actual coordinate
from the ERA5 reanalysis, via Open-Meteo's archive, and works out the dates
directly. That gives the thing a schedule actually needs, which is not the
average last frost but the risk curve around it:

    10% risk   plant after this and you lose a crop one year in ten
    50% risk   the average date, which is a coin flip and no basis for a plan
    90% risk   the year the frost came latest

Deriving them rather than looking them up also means the hardiness zone comes
out of the same data, since the USDA definition is the average annual extreme
minimum temperature over a period of years, which is a number this can compute.

What this is not
----------------
ERA5 is a reanalysis on a grid cell of roughly nine kilometres, and it has a
known bias in exactly the direction that matters here. Frost happens on calm
clear nights when the ground radiates heat away and a shallow cold layer forms
near the surface. That layer is thinner than the model's lowest level, so the
model does not fully resolve it, and daily minima come out too warm.

Measured against station normals, the median last-spring-frost date lands about
one to two weeks early. At the Austin test coordinate the model says mid
February where Camp Mabry's normals say the end of February. Which is why the
report leads with the 10% risk date rather than the median: the earlier date is
biased early and is a coin flip besides, and the risk date is both what a
schedule should use and far less sensitive to the bias.

Three more things move a particular yard off its grid cell:

    urban heat      a dense city runs several degrees warmer than its cell,
                    especially overnight, which is when frost happens
    cold air pools  a low spot or a hollow frosts days earlier and later than the
                    slope above it
    walls           a south-facing masonry wall is most of a zone warmer

The USDA zone from phzmapi, which comes off the 2023 map at 800 m, is fetched as
a cross-check. Where the two disagree by half a zone or more, that is worth
saying out loud rather than averaging away.

If the county extension office publishes a frost date for the actual town, that
beats all of this. Pass it with `--local-last-frost` and `--local-first-frost`
and it is recorded alongside, with the derived figures kept for the spread.
"""
import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request

from . import siteschema, solar, yards

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
PHZM = "https://phzmapi.org/{}.json"
UA = {"User-Agent": "yard-survey/1.0 (personal garden planning)"}

FROST = 32.0
HARD_FREEZE = 28.0
GDD_BASE = 50.0                          # the usual base for warm-season crops
SCORCH_F = 95.0                          # the threshold the heat counts use


def _get(url, params=None, timeout=180):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def daily(lat, lon, years=30, tz="auto"):
    end = dt.date.today().replace(month=12, day=31) - dt.timedelta(days=365)
    end = dt.date(end.year, 12, 31)
    start = dt.date(end.year - years + 1, 1, 1)
    d = _get(ARCHIVE, {"latitude": lat, "longitude": lon,
                       "start_date": start.isoformat(),
                       "end_date": end.isoformat(),
                       "daily": "temperature_2m_min,temperature_2m_max",
                       "temperature_unit": "fahrenheit", "timezone": tz})
    rows = []
    for t, lo, hi in zip(d["daily"]["time"], d["daily"]["temperature_2m_min"],
                         d["daily"]["temperature_2m_max"]):
        if lo is None or hi is None:
            continue
        rows.append((dt.date.fromisoformat(t), lo, hi))
    return rows, {"grid_elevation_ft": round(d.get("elevation", 0) * 3.28084),
                  "timezone": d.get("timezone"),
                  "span": f"{start.year}-{end.year}", "days": len(rows)}


def _pct(sorted_vals, q):
    if not sorted_vals:
        return None
    i = (len(sorted_vals) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def _mmdd(doy, year=2001):
    return (dt.date(year, 1, 1) + dt.timedelta(days=int(round(doy)) - 1)) \
        .strftime("%b %d")


def frost_dates(rows, threshold=FROST):
    """Per year, the last cold morning of spring and the first of autumn.

    Split at 1 July, which works in the northern hemisphere and would need
    inverting south of the equator."""
    by_year = {}
    for d, lo, _ in rows:
        by_year.setdefault(d.year, []).append((d, lo))

    last_spring, first_fall, season = [], [], []
    for year, days in sorted(by_year.items()):
        if len(days) < 300:
            continue
        mid = dt.date(year, 7, 1)
        sp = [d for d, lo in days if lo <= threshold and d < mid]
        fa = [d for d, lo in days if lo <= threshold and d >= mid]
        ls = max(sp).timetuple().tm_yday if sp else None
        ff = min(fa).timetuple().tm_yday if fa else None
        if ls is not None:
            last_spring.append(ls)
        if ff is not None:
            first_fall.append(ff)
        if ls is not None and ff is not None:
            season.append(ff - ls)
        elif not sp and not fa:
            season.append(365)

    def band(vals, late_is_risky):
        if not vals:
            return None
        v = sorted(vals)
        # a 10% risk of being caught means the date only 10% of years exceeded
        q10, q90 = (0.9, 0.1) if late_is_risky else (0.1, 0.9)
        return {"risk_10_pct": _mmdd(_pct(v, q10)),
                "median": _mmdd(_pct(v, 0.5)),
                "risk_90_pct": _mmdd(_pct(v, q90)),
                "earliest": _mmdd(min(v)), "latest": _mmdd(max(v)),
                "years_observed": len(v)}

    out = {"last_spring": band(last_spring, True),
           "first_fall": band(first_fall, False)}
    if season:
        s = sorted(season)
        out["frost_free_days"] = {"median": int(_pct(s, 0.5)),
                                  "shortest": min(s), "longest": max(s)}
    frostless = len(by_year) - len(last_spring)
    if frostless:
        out["years_with_no_spring_frost"] = frostless
    return out


def heat_by_month(rows, threshold=SCORCH_F):
    """Days a month tops `threshold`, per month, averaged over the years.

    The annual count beside this one — 45.8 days over 95 F at the Austin test
    coordinate — answers "is this a hot climate" and cannot answer "is this a
    hot month", which is a different question and the one a plant standing in a
    bed actually poses. Anything judged over a window that excludes summer got
    the annual figure quoted at it: a winter cyclamen was told that 5.45 h of
    December-to-March sun meant it would scorch in July.

    Averaged over the years each month was actually observed rather than over
    the span, so a record that starts in March or ends in October does not
    quietly halve January. Every month is present in the output even where the
    count is zero, because a month absent from a series and a month that never
    tops 95 F are different claims and the reader cannot tell them apart.
    """
    hits, seen = {m: 0 for m in solar.MONTHS}, {m: set() for m in solar.MONTHS}
    for d, _, hi in rows:
        m = solar.MONTHS[d.month - 1]
        seen[m].add(d.year)
        if hi >= threshold:
            hits[m] += 1
    return {m: round(hits[m] / len(seen[m]), 1) if seen[m] else None
            for m in solar.MONTHS}


def summarize(lat, lon, years=30, zip_code=None):
    rows, meta = daily(lat, lon, years)
    if not rows:
        return {"error": "no daily data returned"}

    annual_min = {}
    for d, lo, _ in rows:
        annual_min[d.year] = min(annual_min.get(d.year, 999), lo)
    mins = sorted(annual_min.values())
    mean_extreme_min = sum(mins) / len(mins)

    hot95 = hot100 = 0.0
    gdd_by_year = {}
    for d, lo, hi in rows:
        if hi >= 95:
            hot95 += 1
        if hi >= 100:
            hot100 += 1
        gdd_by_year[d.year] = gdd_by_year.get(d.year, 0.0) + \
            max(0.0, (min(hi, 86.0) + max(lo, GDD_BASE)) / 2.0 - GDD_BASE)
    n_years = len(annual_min)

    out = {
        "source": "ERA5 reanalysis via Open-Meteo archive",
        "span": meta["span"], "days": meta["days"],
        "grid_elevation_ft": meta["grid_elevation_ft"],
        "frost_32f": frost_dates(rows, FROST),
        "hard_freeze_28f": frost_dates(rows, HARD_FREEZE),
        "annual_extreme_min_f": {
            "mean": round(mean_extreme_min, 1),
            "coldest_year": round(mins[0], 1),
            "mildest_year": round(mins[-1], 1),
            "zone_from_data": zone_of(mean_extreme_min)},
        "heat": {"days_over_95f_per_year": round(hot95 / n_years, 1),
                 "days_over_100f_per_year": round(hot100 / n_years, 1),
                 "days_over_95f_by_month": heat_by_month(rows)},
        "growing_degree_days_base_50f": int(
            sum(gdd_by_year.values()) / len(gdd_by_year)),
        "known_bias": ("ERA5 does not resolve the shallow cold layer that forms "
                       "on calm clear nights, so daily minima run warm and the "
                       "median last-frost date lands one to two weeks early "
                       "against station normals. Plan from the 10% risk date, "
                       "not the median"),
        "caveat": ("ERA5 is a ~9 km grid cell. It gives the regional signal, not "
                   "this yard. A city runs warmer, a low spot runs colder, and a "
                   "south wall is most of a zone warmer than either"),
    }

    if zip_code:
        try:
            z = _get(PHZM.format(zip_code), timeout=30)
            out["usda_zone_2023"] = {"zone": z.get("zone"),
                                     "temperature_range_f": z.get("temperature_range"),
                                     "source": "USDA PHZM 2023 via phzmapi, 800 m"}
            a, b = zone_number(out["annual_extreme_min_f"]["zone_from_data"]), \
                zone_number(z.get("zone"))
            if a and b and abs(a - b) >= 0.5:
                out["usda_zone_2023"]["disagreement"] = (
                    f"the published map says {z.get('zone')} and thirty years of "
                    f"ERA5 says {out['annual_extreme_min_f']['zone_from_data']}. "
                    f"Trust the published map for buying plants; it is at 800 m "
                    f"and sees terrain this does not")
        except Exception as exc:
            out["usda_zone_2023"] = {"error": str(exc)}
    return out


def zone_of(mean_extreme_min_f):
    """USDA zones: 10 F bands from -60, each split into a and b half-zones."""
    if mean_extreme_min_f is None:
        return None
    z = (mean_extreme_min_f + 60.0) / 10.0
    n = max(1, min(13, int(z) + 1))
    half = "a" if (mean_extreme_min_f + 60.0) % 10.0 < 5.0 else "b"
    return f"{n}{half}"


def zone_number(zone):
    if not zone:
        return None
    try:
        n = int("".join(c for c in zone if c.isdigit()))
    except ValueError:
        return None
    return n + (0.5 if zone.strip().endswith("b") else 0.0)


def report(c):
    if "error" in c:
        return c["error"]
    L = []
    f = c["frost_32f"]
    L.append(f"  {c['span']}, {c['days']} days, {c['source']}")
    z = c["annual_extreme_min_f"]
    line = (f"  zone {z['zone_from_data']} from the data "
            f"(mean annual low {z['mean']} F, coldest year {z['coldest_year']} F)")
    if c.get("usda_zone_2023", {}).get("zone"):
        line += f"; published map says {c['usda_zone_2023']['zone']}"
    L.append(line)
    if c.get("usda_zone_2023", {}).get("disagreement"):
        L.append(f"    they disagree: {c['usda_zone_2023']['disagreement']}")
    if f.get("last_spring"):
        s = f["last_spring"]
        L.append(f"  plant tender after  {s['risk_10_pct']}   "
                 f"(10% risk; median is {s['median']}, latest ever {s['latest']})")
    if f.get("first_fall"):
        s = f["first_fall"]
        L.append(f"  expect frost by     {s['risk_10_pct']}   "
                 f"(10% risk; median is {s['median']}, earliest ever "
                 f"{s['earliest']})")
    if f.get("frost_free_days"):
        s = f["frost_free_days"]
        L.append(f"  frost-free season   {s['median']} days median, "
                 f"{s['shortest']} to {s['longest']}")
    if f.get("years_with_no_spring_frost"):
        L.append(f"  {f['years_with_no_spring_frost']} of the years never hit 32 F "
                 f"at all")
    h = c["heat"]
    L.append(f"  heat                {h['days_over_95f_per_year']} days over 95 F "
             f"a year, {h['days_over_100f_per_year']} over 100 F")
    if h.get("days_over_95f_by_month"):
        by = h["days_over_95f_by_month"]
        hot = [m for m in solar.MONTHS if (by.get(m) or 0) > 0]
        L.append("  and by month        "
                 + ", ".join(f"{m} {by[m]:g}" for m in hot))
    L.append(f"  GDD base 50 F       {c['growing_degree_days_base_50f']} a year")
    if c.get("local"):
        for k, v in c["local"].items():
            L.append(f"  local figure        {k.replace('_', ' ')}: {v}")
    L.append(f"  bias:   {c['known_bias']}")
    L.append(f"  caveat: {c['caveat']}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--at", nargs=2, type=float, metavar=("LAT", "LON"))
    ap.add_argument("--zip")
    ap.add_argument("--years", type=int, default=30)
    ap.add_argument("--local-last-frost", help="e.g. 'Mar 01', from the county "
                                               "extension office")
    ap.add_argument("--local-first-frost")
    ap.add_argument("--local-source", default="county extension office")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--heat-months", action="store_true",
                    help="add the monthly hot-day series to a yard that "
                         "already has a climate block, and touch nothing else")
    args = ap.parse_args()

    def add_local(c):
        if args.local_last_frost or args.local_first_frost:
            c["local"] = {k: v for k, v in
                          (("last_spring_frost", args.local_last_frost),
                           ("first_fall_frost", args.local_first_frost),
                           ("source", args.local_source)) if v}
            c["local"]["note"] = ("a published local figure beats a reanalysis "
                                  "grid cell; the derived dates above are kept "
                                  "for the spread, which the local figure "
                                  "usually does not give")
        return c

    if args.at:
        print(report(add_local(summarize(args.at[0], args.at[1], args.years,
                                         args.zip))))
        return
    if not args.slug:
        print(__doc__)
        return

    site = yards.load_site(args.slug)
    lat, lon = yards.latlon(site)
    if args.heat_months:
        print(heat_months(args.slug, site, lat, lon, args.years))
        return

    zc = args.zip or site.get("address", {}).get("zip")
    c = add_local(summarize(lat, lon, args.years, zc))
    print(f"{args.slug} — climate at {lat:.4f}, {lon:.4f}")
    print(report(c))
    if args.write:
        # A refetch that does not supply the county figure keeps the one already
        # on record. `local` is the only part of this block that does not come
        # out of the archive, so replacing the whole thing silently threw away
        # the published extension date the planting recommendation rests on.
        held = (site.get("climate") or {}).get("local")
        if held and not c.get("local"):
            c["local"] = held
        site["climate"] = c
        siteschema.set_provenance(site, "climate", "derived",
                                  note=f"ERA5 {c.get('span')} via Open-Meteo, "
                                       f"~9 km grid")
        yards.save(args.slug, "site.json", site)
        print(f"\n  wrote {yards.path(args.slug, 'site.json')}")


def heat_months(slug, site, lat, lon, years=30):
    """Add the monthly hot-day series to a climate block that predates it.

    A full `--write` would answer this too, and it would also refetch and
    rewrite thirty other numbers that the whole record — a schedule, two
    all-clears, a set of doubt cards — is currently quoting. So this asks the
    archive the same question over the same span and writes one key.

    The annual figure already on record is recomputed from the same rows and
    printed beside the stored one, because that is the only available check
    that the refetch is looking at the same weather: if the two agree, the
    monthly series is a decomposition of a number the yard already believes,
    and if they do not, that is worth seeing before anything reads it.
    """
    old = ((site.get("climate") or {}).get("heat") or {})
    rows, meta = daily(lat, lon, years)
    if not rows:
        return "no daily data returned; nothing written"
    by_month = heat_by_month(rows)
    n_years = len({d.year for d, _, _ in rows})
    again = round(sum(1 for _, _, hi in rows if hi >= SCORCH_F) / n_years, 1)

    L = [f"{slug} — days over {SCORCH_F:g} F by month, {meta['span']}, "
         f"{meta['days']} days"]
    L.append("  " + "  ".join(f"{m} {by_month[m]:g}" for m in solar.MONTHS
                              if by_month.get(m)))
    stored = old.get("days_over_95f_per_year")
    L.append(f"  annual, recomputed  {again}   on record {stored}   "
             + ("agrees" if stored == again else
                "DISAGREES — the archive has moved under the record"))

    siteschema.set_path(site, "climate.heat.days_over_95f_by_month", by_month)
    siteschema.set_provenance(
        site, "climate.heat.days_over_95f_by_month", "derived",
        date=dt.date.today().isoformat(),
        note=f"ERA5 {meta['span']} via Open-Meteo, ~9 km grid, the same rows "
             f"and the same span the annual count beside it was computed from; "
             f"the annual figure recomputes to {again} against {stored} on "
             f"record. Mean days a month tops {SCORCH_F:g} F, which is what "
             f"lets an objection about scorching name the months it means")
    yards.save(slug, "site.json", site)
    L.append(f"  wrote {yards.path(slug, 'site.json')}")
    return "\n".join(L)


if __name__ == "__main__":
    main()
