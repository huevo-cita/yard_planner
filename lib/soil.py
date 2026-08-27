#!/usr/bin/env python3
"""What the soil is, from the survey and from the hands.

    python3 -m lib.soil --point 39.7392 -104.9903
    python3 -m lib.soil <slug> [--write]
    python3 -m lib.soil --jar 12 18 6          sand, silt, clay layers in mm
    python3 -m lib.soil --perc 4 55            inches dropped, over minutes

Two sources, and the free one is often the weaker one
-----------------------------------------------------
**USDA Soil Data Access** publishes the national soil survey and will answer for
any coordinate in the country, no key and no quota. For farmland it is excellent.
For a house lot it very often returns "Urban land", which is the survey saying,
honestly, that the original soil was scraped off, built on, and backfilled with
whatever was to hand. Both yards in this system return exactly that. When it
does, the map unit is still worth recording, because it names the parent
material the fill was probably made from and the drainage the site sits in, but
it is context, not an answer.

**Hands in the dirt** is then the real measurement: a jar test for texture, a
percolation test for drainage, a probe for compaction, a strip for pH. All are
free or nearly so and all beat a map unit on a disturbed lot.

**A mail-in lab test** through the county extension, roughly $15-30 and one to
two weeks, is the only way to get actual nutrient levels, salts and a reliable
pH. It is worth raising when, and only when, the design turns on it: blueberries
or azaleas needing acid, a vegetable bed being fed for the first time, a site
with suspected contamination, or a persistent problem nothing else explains.
"""
import argparse
import json
import math
import urllib.request

SDA = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"

DISTURBED = ("urban land", "udorthents", "made land", "fill", "pits",
             "dumps", "psamments")

# USDA texture triangle, as a set of tests applied in order
TEXTURES = [
    ("sand", lambda s, si, c: s >= 85 and si + 1.5 * c <= 15),
    ("loamy sand", lambda s, si, c: 70 <= s <= 91 and si + 1.5 * c >= 15
     and si + 2 * c <= 30),
    ("sandy clay", lambda s, si, c: c >= 35 and s >= 45),
    ("silty clay", lambda s, si, c: c >= 40 and si >= 40),
    ("clay", lambda s, si, c: c >= 40 and s <= 45 and si < 40),
    ("silty clay loam", lambda s, si, c: 27 <= c < 40 and s <= 20),
    ("clay loam", lambda s, si, c: 27 <= c < 40 and 20 < s <= 45),
    ("sandy clay loam", lambda s, si, c: 20 <= c < 35 and s > 45 and si < 28),
    ("silt", lambda s, si, c: si >= 80 and c < 12),
    ("silt loam", lambda s, si, c: si >= 50 and c < 27),
    ("sandy loam", lambda s, si, c: s >= 43 and c < 20 and si < 50),
    ("loam", lambda s, si, c: 7 <= c < 27 and 28 <= si < 50 and s <= 52),
]


def texture_class(sand, silt, clay):
    """USDA texture name from the three percentages."""
    total = sand + silt + clay
    if total <= 0:
        return None
    s, si, c = (100.0 * v / total for v in (sand, silt, clay))
    for name, test in TEXTURES:
        try:
            if test(s, si, c):
                return name
        except Exception:
            continue
    return "loam"


TEXTURE_NOTES = {
    "sand": "drains fast and holds neither water nor nutrients; needs organic "
            "matter and frequent watering",
    "loamy sand": "drains fast, easy to dig, dries out quickly; compost is the fix",
    "sandy loam": "the easy one — drains well, warms early, takes most plants",
    "loam": "the one everyone wants; hold onto it and do not over-till",
    "silt loam": "holds water and nutrients well but crusts and compacts; keep it "
                 "mulched and stay off it wet",
    "silt": "holds water, compacts badly, erodes; mulch and never walk on it wet",
    "clay loam": "holds water and nutrients, slow to drain and slow to warm in "
                 "spring; work it only when it crumbles, never when it smears",
    "silty clay loam": "heavy and slow-draining; raised beds are usually easier "
                       "than amending it",
    "sandy clay loam": "an awkward mix, drains unevenly; organic matter helps most",
    "sandy clay": "hard when dry, sticky when wet; raise the beds",
    "silty clay": "very slow drainage; raise the beds and choose plants that "
                  "tolerate wet feet",
    "clay": "holds nutrients, drains badly, cracks when dry, sets like brick if "
            "worked wet. Do not add sand, you get adobe. Add compost, or build up",
}


# ---------------------------------------------------------------- USDA query

def _query(sql, timeout=60):
    body = json.dumps({"query": sql, "format": "JSON+COLUMNNAME"}).encode()
    req = urllib.request.Request(SDA, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        data = json.load(fh)
    table = data.get("Table") or []
    if len(table) < 2:
        return []
    cols = table[0]
    return [dict(zip(cols, row)) for row in table[1:]]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def lookup(lat, lon):
    """The soil survey's answer for one coordinate."""
    mus = _query(f"""
        SELECT mu.mukey, mu.musym, mu.muname, l.areaname
        FROM mapunit mu INNER JOIN legend l ON l.lkey = mu.lkey
        WHERE mu.mukey IN (SELECT * FROM
            SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon} {lat})'))
    """)
    if not mus:
        return {"found": False,
                "note": "no soil survey coverage at this coordinate"}
    mu = mus[0]
    comps = _query(f"""
        SELECT c.cokey, c.compname, c.comppct_r, c.drainagecl, c.hydgrp,
               c.runoff, c.slope_r, c.taxclname
        FROM component c WHERE c.mukey = '{mu['mukey']}'
        ORDER BY c.comppct_r DESC
    """)
    out = {
        "found": True,
        "mukey": mu["mukey"], "symbol": mu["musym"], "map_unit": mu["muname"],
        "survey_area": mu["areaname"],
        "components": [], "source": "USDA Soil Data Access",
    }
    for c in comps[:4]:
        hz = _query(f"""
            SELECT ch.hzname, ch.hzdept_r, ch.hzdepb_r, ch.sandtotal_r,
                   ch.silttotal_r, ch.claytotal_r, ch.om_r, ch.ph1to1h2o_r,
                   ch.awc_r, ch.ksat_r, ch.dbthirdbar_r, ch.cec7_r
            FROM chorizon ch WHERE ch.cokey = '{c['cokey']}'
            ORDER BY ch.hzdept_r
        """) if c.get("cokey") else []
        horizons = []
        for h in hz:
            sand, silt, clay = (_num(h["sandtotal_r"]), _num(h["silttotal_r"]),
                                _num(h["claytotal_r"]))
            horizons.append({
                "name": h["hzname"],
                "top_in": round((_num(h["hzdept_r"]) or 0) / 2.54, 1),
                "bottom_in": round((_num(h["hzdepb_r"]) or 0) / 2.54, 1),
                "sand_pct": sand, "silt_pct": silt, "clay_pct": clay,
                "texture": texture_class(sand, silt, clay)
                if None not in (sand, silt, clay) else None,
                "organic_matter_pct": _num(h["om_r"]),
                "ph": _num(h["ph1to1h2o_r"]),
                "available_water_capacity": _num(h["awc_r"]),
                "ksat_um_s": _num(h["ksat_r"]),
                "bulk_density": _num(h["dbthirdbar_r"]),
                "cec": _num(h["cec7_r"]),
            })
        out["components"].append({
            "name": c["compname"], "percent": _num(c["comppct_r"]),
            "drainage_class": c["drainagecl"],
            "hydrologic_group": c["hydgrp"], "runoff": c["runoff"],
            "slope_pct": _num(c["slope_r"]), "taxonomy": c["taxclname"],
            "horizons": horizons,
        })

    name = (mu["muname"] or "").lower()
    comp_names = " ".join((c["name"] or "").lower() for c in out["components"])
    out["disturbed"] = any(k in name or k in comp_names for k in DISTURBED)
    if out["disturbed"]:
        out["verdict"] = (
            f"The survey calls this '{mu['muname']}'. That is the survey saying "
            f"the original soil was scraped, built on and backfilled, and it will "
            f"not tell you what is actually in the ground here. Treat every number "
            f"below as context about the neighbourhood, not a measurement of this "
            f"yard, and get your hands in the dirt.")
    else:
        surf = next((h for c in out["components"] for h in c["horizons"]
                     if h["top_in"] == 0), None)
        detail = ""
        if surf:
            detail = ", surface horizon " + str(surf.get("texture") or "unnamed")
            if surf.get("ph"):
                detail += ", pH {:.1f}".format(surf["ph"])
        out["verdict"] = (
            "The survey maps this as " + str(mu["muname"]) + detail +
            ". Worth confirming with a jar test, but this is a real starting point.")
    return out


# ------------------------------------------------------------- hands-on tests

def jar_test(sand_mm, silt_mm, clay_mm):
    """Texture from a jar of soil, water and time.

    A jar two-thirds full of water, a third soil, a squirt of dish soap, shaken
    hard and left to stand. Sand settles in a minute, silt over a couple of
    hours, clay over a day or two. Measure the three bands with a ruler.

    Organic matter floats and is not part of the three bands. Read the bands, not
    the total, and do not include the floating raft.
    """
    total = sand_mm + silt_mm + clay_mm
    if total <= 0:
        raise ValueError("all three bands cannot be zero")
    sand, silt, clay = (100.0 * v / total for v in (sand_mm, silt_mm, clay_mm))
    name = texture_class(sand, silt, clay)
    return {
        "test": "jar",
        "sand_pct": round(sand), "silt_pct": round(silt), "clay_pct": round(clay),
        "texture": name,
        "implication": TEXTURE_NOTES.get(name, ""),
        "accuracy": ("good to about a texture class either side. Layer boundaries "
                     "are hard to read, and very fine sand reads as silt"),
    }


def percolation(drop_in, minutes, presoaked=True):
    """Drainage from a hole in the ground.

    Dig a hole a foot across and a foot deep, fill it, let it drain away
    completely, then fill it again and time the second one. The first fill wets
    the surrounding soil; timing it instead of the second gives an answer that
    is too fast, sometimes by half.
    """
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    rate = drop_in / minutes * 60.0
    if rate < 0.1:
        cls, note = "very poorly drained", (
            "water stands. Almost nothing but a bog or rain garden planting will "
            "live here without raising the bed or fixing the drainage")
    elif rate < 0.5:
        cls, note = "poorly drained", (
            "slow. Raise beds at least 8 in, avoid anything that hates wet feet, "
            "and do not overwater")
    elif rate < 1.0:
        cls, note = "somewhat poorly drained", (
            "workable but slow. Raised beds help; most vegetables will manage")
    elif rate <= 4.0:
        cls, note = "well drained", (
            "the range you want. Nearly anything will grow given light and food")
    elif rate <= 8.0:
        cls, note = "somewhat excessively drained", (
            "fast. Water more often, mulch heavily, and add organic matter")
    else:
        cls, note = "excessively drained", (
            "very fast, probably sand or coarse fill. Water will run straight "
            "through and take nutrients with it; compost is the whole job here")
    return {
        "test": "percolation",
        "rate_in_per_hour": round(rate, 2),
        "drainage_class": cls,
        "implication": note,
        "valid": bool(presoaked),
        "caveat": None if presoaked else (
            "this was the first fill into dry ground, so it reads faster than "
            "the truth. Re-run it on a pre-soaked hole"),
    }


def compaction(depth_in, tool="screwdriver"):
    """How far a probe pushes into moist soil before it stops.

    A long screwdriver or a piece of rebar, pushed with steady hand pressure into
    ground that is moist but not wet. Dry ground reads hard whatever its
    structure, so this test is meaningless in a drought.
    """
    if depth_in >= 12:
        cls, note = "loose", "roots can go where they like; leave it alone"
    elif depth_in >= 8:
        cls, note = "workable", "normal for a garden bed; compost and mulch keep it there"
    elif depth_in >= 4:
        cls, note = "compacted", (
            "roots will struggle below this. Broadfork or double-dig once, then "
            "keep off it and let roots and worms do the rest")
    else:
        cls, note = "severely compacted", (
            "this is closer to a path than a bed. Either build up on top of it "
            "with 10-12 in of imported soil, or break it up mechanically. Do not "
            "simply plant into it")
    return {"test": "compaction probe", "depth_in": depth_in, "tool": tool,
            "class": cls, "implication": note,
            "caveat": "only meaningful on moist soil; dry ground reads hard"}


def ph_reading(value, method="strip"):
    if value < 5.0:
        band, note = "strongly acid", (
            "blueberries and azaleas are happy; most vegetables are not. Lime "
            "raises it, slowly, and only after a lab test says how much")
    elif value < 6.0:
        band, note = "moderately acid", (
            "fine for potatoes, blueberries and most acid-lovers; a little low "
            "for brassicas and beans")
    elif value <= 7.3:
        band, note = "near neutral", "the range nearly everything wants"
    elif value <= 8.0:
        band, note = "moderately alkaline", (
            "iron and manganese start locking up; expect yellowing on acid-lovers. "
            "Sulphur lowers it slowly, and not at all against limestone bedrock")
    else:
        band, note = "strongly alkaline", (
            "common over caliche and limestone. Fighting it is a losing game; "
            "choose plants that like it, or build raised beds with imported soil")
    return {"test": "pH", "value": value, "method": method, "band": band,
            "implication": note,
            "accuracy": "strips read to about half a pH unit; a probe is no better "
                        "unless calibrated. A lab test is the only precise answer"
            if method in ("strip", "probe") else None}


# ------------------------------------------------------------------- the yard

def survey(slug, write=False):
    from . import yards
    site = yards.load_site(slug)
    lat, lon = yards.latlon(site)
    print(f"{slug}: querying the USDA soil survey at {lat}, {lon}")
    res = lookup(lat, lon)
    if not res.get("found"):
        print("  " + res["note"])
        return res

    print(f"\n  map unit  {res['symbol']}  {res['map_unit']}")
    print(f"  survey    {res['survey_area']}  (mukey {res['mukey']})")
    for c in res["components"]:
        pct = f"{c['percent']:.0f}%" if c["percent"] else "?"
        drain = c["drainage_class"] or "drainage not stated"
        grp = (", hydrologic group " + c["hydrologic_group"]
               if c["hydrologic_group"] else "")
        print(f"\n  {c['name']} — {pct} of the map unit, {drain}{grp}")
        if not c["horizons"]:
            print("    no horizon data — normal for urban land and made ground")
        for h in c["horizons"][:5]:
            bits = [f"{h['top_in']:.0f}-{h['bottom_in']:.0f} in"]
            if h["texture"]:
                bits.append(f"{h['texture']} "
                            f"({h['sand_pct']:.0f}/{h['silt_pct']:.0f}/{h['clay_pct']:.0f})")
            if h["ph"]:
                bits.append(f"pH {h['ph']:.1f}")
            if h["organic_matter_pct"]:
                bits.append(f"OM {h['organic_matter_pct']:.1f}%")
            print("    " + "   ".join(bits))
    print(f"\n  {res['verdict']}")

    if write:
        from . import conditions
        conditions.record_usda(slug, res)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--point", nargs=2, type=float, metavar=("LAT", "LON"))
    ap.add_argument("--jar", nargs=3, type=float, metavar=("SAND", "SILT", "CLAY"))
    ap.add_argument("--perc", nargs=2, type=float, metavar=("INCHES", "MINUTES"))
    ap.add_argument("--probe", type=float, metavar="INCHES")
    ap.add_argument("--ph", type=float)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    did = False
    if args.jar:
        print(json.dumps(jar_test(*args.jar), indent=2))
        did = True
    if args.perc:
        print(json.dumps(percolation(*args.perc), indent=2))
        did = True
    if args.probe is not None:
        print(json.dumps(compaction(args.probe), indent=2))
        did = True
    if args.ph is not None:
        print(json.dumps(ph_reading(args.ph), indent=2))
        did = True
    if args.point:
        print(json.dumps(lookup(*args.point), indent=2))
        did = True
    if args.slug:
        survey(args.slug, write=args.write)
        did = True
    if not did:
        print(__doc__)


if __name__ == "__main__":
    main()
