#!/usr/bin/env python3
"""From an address to a lot, and to the buildings that shade it.

    python3 -m lib.parcel --geocode "1600 Pennsylvania Ave NW, Washington, DC"
    python3 -m lib.parcel --elevation 39.7392 -104.9903
    python3 -m lib.parcel <slug> --context [--radius 80]

Sources, all free and none needing a key:

    Nominatim      address to lon/lat. One request a second, and it wants a real
                   User-Agent
    Overpass       OpenStreetMap building footprints with height tags. In US
                   cities these are frequently imported straight from municipal
                   data, so the heights are real rather than guessed
    USGS EPQS      bare-earth elevation at any coordinate, 1 m where 3DEP covers

Neighbouring buildings matter more than people expect. A three storey row house
across a narrow street takes the whole morning off a side yard, and no amount of
measuring your own fence will reveal that.

Registration and its honest error
---------------------------------
Footprints arrive in lon/lat and have to land in the yard's plan frame. That
frame is pinned by `frame.anchor`, which is a real corner of the yard whose
position is known both ways. Expect roughly a foot of slop in the neighbours,
which is well inside what matters for a shade model: a foot of error in a
building forty feet away moves a shadow edge by about a degree.

Where a footprint is a merged block covering several attached houses, OSM gives
the whole row one height. If yours is the short one in a tall row, that is a
building-sized error in the wrong direction, so the yard's own house is always
modelled explicitly under `obstructions.house` and excluded from the imported
set. Use `--exclude-way` and `--clip-x` for the rest of the row.
"""
import argparse
import json
import math
import time
import urllib.parse
import urllib.request

from . import frame, siteschema, yards

UA = {"User-Agent": "yard-survey/1.0 (personal garden planning)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# The main Overpass instance returns 504 under load often enough that a single
# endpoint is not a dependency worth having. Tried in order.
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.osm.ch/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
EPQS = "https://epqs.nationalmap.gov/v1/json"

M_TO_IN = 39.3700787
DEFAULT_STOREY_IN = 10.5 * 12
DEFAULT_HEIGHT_IN = 30.0 * 12
GARAGE_HEIGHT_IN = 10.0 * 12


def _get_json(url, params=None, timeout=60, data=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


# ------------------------------------------------------------------ geocoding

def geocode(address, limit=3):
    """Address to coordinates. Returns every candidate, because addresses are
    ambiguous and picking silently is how a yard ends up in the wrong state."""
    time.sleep(1.0)                      # Nominatim's published rate limit
    res = _get_json(NOMINATIM, {"q": address, "format": "json", "limit": limit,
                                "addressdetails": 1})
    out = []
    for r in res:
        out.append({
            "lat": float(r["lat"]), "lon": float(r["lon"]),
            "display_name": r.get("display_name"),
            "type": r.get("type"), "class": r.get("class"),
            "importance": r.get("importance"),
            "bounding_box": [float(v) for v in r.get("boundingbox", [])],
            "address": r.get("address", {}),
        })
    return out


def elevation(lat, lon):
    """Bare-earth elevation, feet. Useful for slope across a yard and for
    checking that a lidar ground surface is anchored sensibly."""
    try:
        r = _get_json(EPQS, {"x": lon, "y": lat, "units": "Feet",
                             "wkid": 4326, "includeDate": "true"})
    except Exception as exc:
        return {"found": False, "error": str(exc)}
    val = r.get("value")
    if val in (None, "", -1000000):
        return {"found": False, "note": "no EPQS coverage at this coordinate"}
    return {"found": True, "elevation_ft": float(val),
            "source": r.get("rasterName") or "USGS 3DEP",
            "date": r.get("date")}


def slope(site, samples=None):
    """Elevation at the yard's corners, and the fall across it."""
    pts = samples or [(lab, x, y) for lab, x, y, _, _ in frame.corners(site)]
    out = []
    for lab, x, y in pts:
        lon, lat = frame.to_world(site, x, y)
        e = elevation(lat, lon)
        out.append({"label": lab, "x": x, "y": y,
                    "elevation_ft": e.get("elevation_ft")})
        time.sleep(0.2)
    vals = [o["elevation_ft"] for o in out if o["elevation_ft"] is not None]
    if len(vals) < 2:
        return {"corners": out, "fall_ft": None}
    fall = max(vals) - min(vals)
    return {"corners": out, "fall_ft": round(fall, 2),
            "note": ("EPQS is a bare-earth model on a 1 m grid, so it will not "
                     "see a low retaining wall or a raised bed. It is a check on "
                     "the overall lie of the land, not a substitute for a level "
                     "and a string line")}


# ------------------------------------------------------------------ buildings

def height_inches(tags):
    """OSM height, in order of how much it can be trusted."""
    if tags.get("height"):
        try:
            return round(float(str(tags["height"]).split()[0]) * M_TO_IN, 1), \
                "OSM height tag"
        except ValueError:
            pass
    if tags.get("building:levels"):
        try:
            return round(float(tags["building:levels"]) * DEFAULT_STOREY_IN, 1), \
                "levels x 10.5 ft"
        except ValueError:
            pass
    if tags.get("building") in ("garage", "shed", "carport", "roof"):
        return GARAGE_HEIGHT_IN, "assumed, outbuilding"
    return DEFAULT_HEIGHT_IN, "assumed, no height or levels tagged"


def overpass(query):
    payload = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    for url in OVERPASS:
        try:
            return _get_json(url, data=payload)
        except Exception as exc:
            errors.append(f"{url.split('/')[2]}: {exc}")
            time.sleep(1.0)
    raise RuntimeError("every Overpass mirror failed:\n  " + "\n  ".join(errors))


def fetch_buildings(lat, lon, radius_m=80):
    query = ("[out:json][timeout:60];"
             f'way(around:{radius_m},{lat},{lon})["building"];'
             "out geom;")
    data = overpass(query)
    out = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        h, how = height_inches(tags)
        name = tags.get("name") or " ".join(
            v for v in (tags.get("addr:housenumber"), tags.get("addr:street"))
            if v) or f"way/{el['id']}"
        out.append({"osm_way": el["id"], "name": name, "height": h,
                    "height_source": how, "tags": tags,
                    "lonlat": [(g["lon"], g["lat"]) for g in el["geometry"]]})
    return out


def context(slug, radius_m=80, exclude_ways=(), clip=None, max_x=1200,
            max_y=1600, write=True):
    """Neighbouring footprints, in the yard's plan frame, ready to cast shade."""
    site = yards.load_site(slug)
    lat, lon = yards.latlon(site)
    raw = fetch_buildings(lat, lon, radius_m)
    print(f"{slug}: {len(raw)} building footprints within {radius_m} m")

    out = []
    for b in raw:
        poly = [frame.to_yard(site, x, y) for x, y in b["lonlat"]]
        if poly and poly[0] == poly[-1]:
            poly = poly[:-1]
        if len(poly) < 3:
            continue
        name, height = b["name"], b["height"]

        if b["osm_way"] in exclude_ways:
            print(f"  excluded way/{b['osm_way']} ({name})")
            continue
        if clip and b["osm_way"] == clip.get("way"):
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            cut = float(clip["from_x"])
            if max(xs) <= cut:
                print(f"  way/{b['osm_way']} lies entirely inside the clip; dropped")
                continue
            poly = [(cut, min(ys)), (max(xs), min(ys)),
                    (max(xs), max(ys)), (cut, max(ys))]
            name = clip.get("name", name + " (clipped)")
            height = clip.get("height", height)

        # anything so far away in every direction that even a tall wall could
        # not reach the yard is dropped, to keep the ray casting cheap
        if min(abs(p[0]) for p in poly) > max_x or \
                min(abs(p[1]) for p in poly) > max_y:
            continue
        out.append({"name": name, "osm_way": b["osm_way"], "height": height,
                    "height_source": b["height_source"],
                    "polygon": [list(p) for p in poly]})

    out.sort(key=lambda b: min(p[0] ** 2 + p[1] ** 2 for p in b["polygon"]))
    print(f"  {len(out)} kept, nearest first:")
    for b in out[:12]:
        xs = [p[0] for p in b["polygon"]]
        ys = [p[1] for p in b["polygon"]]
        print(f"    {b['name'][:40]:40s} {b['height'] / 12:5.1f} ft  "
              f"X[{min(xs):6.0f},{max(xs):6.0f}] Y[{min(ys):6.0f},{max(ys):6.0f}]"
              f"  {b['height_source']}")

    if write:
        site.setdefault("obstructions", {})["context_buildings"] = out
        site["obstructions"]["context_note"] = (
            f"{len(out)} neighbouring buildings within {radius_m} m, from OSM "
            f"footprints with city height tags, as vertical prisms in yard-frame "
            f"inches. The yard's own house is modelled separately under "
            f"obstructions.house.")
        siteschema.set_provenance(site, "obstructions.context_buildings", "osm",
                                  note="footprints registered through "
                                       "frame.anchor; about a foot of slop")
        yards.save(slug, "site.json", site)
        print(f"  wrote {yards.path(slug, 'site.json')}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--geocode")
    ap.add_argument("--elevation", nargs=2, type=float, metavar=("LAT", "LON"))
    ap.add_argument("--context", action="store_true")
    ap.add_argument("--slope", action="store_true")
    ap.add_argument("--radius", type=int, default=80)
    ap.add_argument("--exclude-way", type=int, action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.geocode:
        for c in geocode(args.geocode):
            print(f"  {c['lat']:.6f}, {c['lon']:.6f}   {c['display_name']}")
        return
    if args.elevation:
        print(json.dumps(elevation(*args.elevation), indent=2))
        return
    if args.slug and args.slope:
        print(json.dumps(slope(yards.load_site(args.slug)), indent=2))
        return
    if args.slug and args.context:
        context(args.slug, radius_m=args.radius,
                exclude_ways=set(args.exclude_way), write=not args.dry_run)
        return
    print(__doc__)


if __name__ == "__main__":
    main()
