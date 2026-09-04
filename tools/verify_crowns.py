#!/usr/bin/env python3
"""Independently verify the sun model's crown geometry, by a different method.

The model tests ray-vs-crown analytically: an exact ray-ellipsoid intersection
with a discriminant, plus two sign conditions. This marches along the same ray
in small steps and asks whether any sample point is inside the ellipsoid.

Numerical against analytic is a real second opinion. It catches a sign error, a
radius-for-diameter slip, a frame rotation, and a wrong branch on the
discriminant — all of which would leave the analytic test confidently wrong and
silent. It does not re-derive the solar position, which is a separate concern
with its own tests.

Read-only. Nothing is written.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import solar, sunmodel, yards  # noqa: E402

SLUG = sys.argv[1] if len(sys.argv) > 1 else "cloverleaf-austin"
STEP_IN = 2.0            # march resolution
REACH_IN = 130 * 12      # 130 ft, past every tree on the lot


def inside(point, centre, radii):
    q = (np.asarray(point, float) - centre) / radii
    return float((q * q).sum()) <= 1.0


def marched_block(m, point, d):
    """Any sample along the ray inside any crown. The independent answer."""
    p = np.asarray(point, float)
    for t in np.arange(STEP_IN, REACH_IN, STEP_IN):
        s = p + d * t
        if s[2] > 80 * 12:
            break
        for centre, radii, tree in m.crowns:
            if inside(s, centre, radii):
                return True, tree.get("id", "?")
    return False, None


def main():
    site = yards.load_site(SLUG)
    m = sunmodel.Model(site)
    xb = float(site["frame"]["true_bearing_of_plus_x"])

    print(f"{SLUG}: {len(m.crowns)} crowns, +x bearing {xb} deg, "
          f"EYE {sunmodel.EYE} in\n")

    # -- 1. the frame convention, against a fact that needs no code
    #    At solar noon the sun is due south, azimuth 180. In yard coordinates
    #    that must point somewhere between +x (117.8) and +y (207.8).
    d_noon = sunmodel.sun_vector(60.0, 180.0, xb)
    print("1. frame convention")
    print(f"   az 180 (due south), alt 60 -> d = "
          f"[{d_noon[0]:+.3f}, {d_noon[1]:+.3f}, {d_noon[2]:+.3f}]")
    ok = d_noon[0] > 0 and d_noon[1] > 0
    print(f"   +x bears {xb}, +y bears {(xb + 90) % 360}; due south lies "
          f"between them, so both components should be positive: "
          f"{'ok' if ok else 'FAIL'}\n")

    # -- 2. the trees, as modelled
    print("2. crowns as modelled")
    for centre, radii, t in m.crowns:
        prov = "assumed" if t.get("crown_base_height") is None else ""
        print(f"   {t.get('id','?'):<6} centre ({centre[0]:6.1f},"
              f"{centre[1]:6.1f},{centre[2]:6.1f}) in   "
              f"radii ({radii[0]:5.1f},{radii[1]:5.1f},{radii[2]:5.1f})   "
              f"h {t.get('height')} base {t.get('crown_base_height')} {prov}")
    print()

    # -- 3. analytic vs marched, over cells and sun positions that matter
    cells = [
        ("g05 centre (the new front bed)", (480.0, 460.0)),
        ("retired front_bed centre", (400.0, 180.0)),
        ("front yard, mid-lawn", (350.0, 250.0)),
        ("g02 centre (rear house bed)", (300.0, 700.0)),
        ("g01 centre", (150.0, 640.0)),
    ]
    times = [("21 Jun", 6, 21), ("21 Jun", 12, 21), ("21 Jun", 16, 21),
             ("21 Mar", 9, 80), ("21 Mar", 12, 80),
             ("21 Dec", 10, 355), ("21 Dec", 12, 355), ("21 Dec", 14, 355)]

    print("3. analytic (the model) vs marched (independent), per cell and hour")
    disagreements = 0
    total = 0
    for label, (cx, cy) in cells:
        print(f"\n   {label}  at ({cx:.0f}, {cy:.0f}) in")
        point = np.array([cx, cy, sunmodel.EYE], float)
        for when, hour, doy in times:
            alt, az = sun_at(m, doy, hour)
            if alt <= 0:
                continue
            d = sunmodel.sun_vector(alt, az, xb)
            a = m.crown_blocks_point(point, d)
            b, who = marched_block(m, point, d)
            total += 1
            flag = "" if a == b else "   <-- DISAGREE"
            if a != b:
                disagreements += 1
            print(f"      {when} {hour:02d}:00  alt {alt:5.1f} az {az:6.1f}  "
                  f"analytic {'BLOCKED' if a else 'clear  '}  "
                  f"marched {'BLOCKED' if b else 'clear  '}"
                  f"{' by ' + who if who else ''}{flag}")

    print(f"\n   {total} ray tests, {disagreements} disagreements")

    # -- 4. the specific claim: can the pecans reach the retired front_bed box?
    print("\n4. could the pecans ever have shaded the retired front_bed box?")
    fb = np.array([400.0, 180.0, sunmodel.EYE])
    for centre, radii, t in m.crowns:
        horiz = math.hypot(centre[0] - fb[0], centre[1] - fb[1])
        if horiz < radii[0] + 300:
            # the altitude at which a ray from the cell grazes the crown's
            # lower near edge: below this the ray passes under the crown
            near = max(horiz - radii[0], 1.0)
            base = centre[2] - radii[2]
            graze = math.degrees(math.atan2(base - sunmodel.EYE, near))
            print(f"   {t.get('id','?'):<6} {horiz/12:5.1f} ft away, crown "
                  f"radius {radii[0]/12:4.1f} ft, base {base/12:4.1f} ft: a "
                  f"ray clears under it below alt {graze:4.1f} deg")


def sun_at(m, doy, hour):
    """Altitude and azimuth at local standard hour on a day of year."""
    s = m.sun
    for fn in ("alt_az", "altaz", "position", "sun_position"):
        f = getattr(s, fn, None)
        if f:
            try:
                return f(doy, hour)
            except TypeError:
                pass
    raise SystemExit("could not find the solar position accessor; "
                     f"SolarSite has {[a for a in dir(s) if not a.startswith('_')]}")


if __name__ == "__main__":
    main()
