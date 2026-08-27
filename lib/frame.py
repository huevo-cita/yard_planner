#!/usr/bin/env python3
"""Moving between the world and a yard's plan frame.

    python3 -m lib.frame <slug> <lon> <lat>      where that point lands in the yard
    python3 -m lib.frame <slug> --corners        the yard's corners as lon/lat

A yard plan frame is defined by three numbers in site.json:

    frame.anchor.lon / .lat        where the frame's origin sits in the world
    frame.true_bearing_of_plus_x   which way +X points, as a true bearing

+Y is 90 degrees clockwise from +X, which for a yard measured off a house wall
usually means "away from the street". Units are inches.

Everything is a local tangent-plane approximation: one degree of latitude is
treated as a constant, and longitude is scaled by the cosine of the anchor
latitude. Over a yard, and over the block of neighbours around it, the error is
well under an inch — far smaller than the foot or so of slop in the footprint
data being registered.
"""
import json
import math
import sys

FT_PER_DEG_LAT = 364637.0        # 69.06 statute miles, close enough at any US latitude
IN_PER_FT = 12.0


def scales(lat):
    """Feet per degree of latitude and of longitude at this latitude."""
    return FT_PER_DEG_LAT, FT_PER_DEG_LAT * math.cos(math.radians(lat))


def anchor_of(site):
    f = site.get("frame", {})
    a = f.get("anchor")
    if not a:
        raise ValueError(
            "site.json has no frame.anchor, so the yard is not registered to the "
            "world and neighbouring buildings cannot be placed. Record the lon/lat "
            "of the yard's origin corner.")
    return float(a["lon"]), float(a["lat"]), float(f["true_bearing_of_plus_x"])


def to_yard(site, lon, lat, round_to=1):
    """lon/lat -> yard plan frame, inches."""
    olon, olat, bearing = anchor_of(site)
    ft_lat, ft_lon = scales(olat)
    e = (lon - olon) * ft_lon
    n = (lat - olat) * ft_lat
    b = math.radians(bearing)
    x = (e * math.sin(b) + n * math.cos(b)) * IN_PER_FT
    y = (e * math.cos(b) - n * math.sin(b)) * IN_PER_FT
    if round_to is None:
        return x, y
    return round(x, round_to), round(y, round_to)


def to_world(site, x, y):
    """Yard plan frame, inches -> lon/lat."""
    olon, olat, bearing = anchor_of(site)
    ft_lat, ft_lon = scales(olat)
    b = math.radians(bearing)
    xf, yf = x / IN_PER_FT, y / IN_PER_FT
    e = xf * math.sin(b) + yf * math.cos(b)
    n = xf * math.cos(b) - yf * math.sin(b)
    return olon + e / ft_lon, olat + n / ft_lat


def to_yard_from_projected(site, ex, ny, origin_ex, origin_ny, bearing=None):
    """Projected metres (any CRS whose axes are east/north) -> yard inches.

    Lidar arrives in a state-plane or UTM system, not lon/lat. Grid north in a
    projected system is not quite true north, but the convergence over a single
    lot is a small fraction of a degree and is absorbed by the same registration
    slop as everything else.
    """
    olon, olat, brg = anchor_of(site)
    b = math.radians(bearing if bearing is not None else brg)
    e_ft = (ex - origin_ex) * 3.280839895
    n_ft = (ny - origin_ny) * 3.280839895
    x = (e_ft * math.sin(b) + n_ft * math.cos(b)) * IN_PER_FT
    y = (e_ft * math.cos(b) - n_ft * math.sin(b)) * IN_PER_FT
    return x, y


def corners(site):
    """The yard outline as (label, x, y, lon, lat)."""
    b = site["boundary"]
    W = b["width_east_west"]
    C = b["south_boundary_offset"]
    s = b.get("north_fence_slope") or 0.0
    pts = [("origin", 0.0, 0.0), ("far side, north", W, s * W),
           ("far side, south", W, C), ("origin side, south", 0.0, C)]
    return [(lab, x, y) + to_world(site, x, y) for lab, x, y in pts]


def derive_anchor(site, known_lon, known_lat, known_x, known_y):
    """Set frame.anchor from any point whose lon/lat and yard coordinates are both
    known. Useful when a survey pins a corner other than the origin."""
    bearing = float(site["frame"]["true_bearing_of_plus_x"])
    ft_lat, ft_lon = scales(known_lat)
    b = math.radians(bearing)
    xf, yf = known_x / IN_PER_FT, known_y / IN_PER_FT
    e = xf * math.sin(b) + yf * math.cos(b)
    n = xf * math.cos(b) - yf * math.sin(b)
    site.setdefault("frame", {})["anchor"] = {
        "lon": round(known_lon - e / ft_lon, 9),
        "lat": round(known_lat - n / ft_lat, 9),
        "note": f"back-solved from a point known to be at yard "
                f"({known_x:.1f}, {known_y:.1f})",
    }
    return site["frame"]["anchor"]


def main():
    from . import yards
    if len(sys.argv) < 2:
        print(__doc__)
        return
    site = yards.load_site(sys.argv[1])
    if "--corners" in sys.argv:
        print(f"{'corner':22s} {'x':>8s} {'y':>8s}   {'lon':>13s} {'lat':>11s}")
        for lab, x, y, lon, lat in corners(site):
            print(f"{lab:22s} {x:8.1f} {y:8.1f}   {lon:13.8f} {lat:11.7f}")
        return
    lon, lat = float(sys.argv[2]), float(sys.argv[3])
    x, y = to_yard(site, lon, lat)
    print(f"{lon}, {lat}  ->  yard x={x:.1f}\"  y={y:.1f}\"")


if __name__ == "__main__":
    main()
