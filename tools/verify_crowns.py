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
from lib import siteschema, solar, sunmodel, yards  # noqa: E402

SLUG = sys.argv[1] if len(sys.argv) > 1 else "cloverleaf-austin"
STEP_IN = 2.0            # march resolution
REACH_IN = 130 * 12      # 130 ft, past every tree on the lot

# When to fire the rays. The day of year is looked up from the label in
# `solar.DOY` and never written beside it, because it was written beside it
# once: three rows read `("21 Jun", 6, 21)`, `("21 Jun", 12, 21)` and
# `("21 Jun", 16, 21)`, and 21 is a perfectly valid day of year — 21 January.
# So the rows labelled high summer were computed for midwinter, printed a noon
# altitude of 39.6 degrees rather than 83.1, and nothing complained, because a
# plausible number in the column you expected a number in is invisible.
#
# High summer is the case a crown check most needs. A low sun puts the ray under
# the crown through the bare trunk; only a high sun puts it through the foliage,
# which is the geometry the analytic test exists to get right. The tool had
# therefore never once exercised it.
#
# A bare integer that has to agree with a string is the defect, not the 21. With
# the label as the only spelling of the date the two cannot disagree, and a
# label that is not a real date raises here instead of testing the wrong season.
TIMES = [("Jun 21", 6), ("Jun 21", 12), ("Jun 21", 16),
         ("Mar 20", 9), ("Mar 20", 12),
         ("Dec 21", 10), ("Dec 21", 12), ("Dec 21", 14)]

# Kept as a literal on purpose: this box is where the front bed used to be, and
# section 4 asks whether the pecans could ever have reached it. A retired
# location cannot be derived from a record it is no longer in.
RETIRED_FRONT_BED = (400.0, 180.0)


def inside(point, centre, radii):
    q = (np.asarray(point, float) - centre) / radii
    return float((q * q).sum()) <= 1.0


def doy_of(label):
    """The day of year for a test row's label. The label is the only spelling."""
    if label not in solar.DOY:
        raise SystemExit(
            f"{label!r} is not a date solar.DOY knows. One of: "
            + ", ".join(sorted(solar.DOY)))
    return solar.DOY[label]


def assert_outdoors(site, label, x, y):
    """Refuse to fire a test ray from inside the house.

    The two bed probes were hard-coded coordinates that went stale in place: the
    beds moved on 4 September and `g02 centre` and `g01 centre` kept their names
    while the points they held drifted inside the house footprint. `Model` drops
    those cells as indoors, so the marched and analytic tests went on agreeing
    perfectly about rays cast through a wall — which they do, reliably, and it
    means nothing. Silently testing indoor ground is how that survived; failing
    loudly is the cheapest thing that would have caught it on the first run.
    """
    walls = ((site.get("obstructions") or {}).get("house_walls") or {})
    poly = walls.get("polygon")
    if not poly:
        return
    if bool(siteschema.in_polygon(np.asarray(poly, float),
                                  np.array([float(x)]), np.array([float(y)]))[0]):
        raise SystemExit(
            f"probe {label!r} at ({x:.0f}, {y:.0f}) is inside "
            f"obstructions.house_walls, so it is indoors and not yard. A ray "
            f"from there tests nothing. Fix the rectangle it came from in "
            f"site.json, or drop the probe.")


def probe_cells(site):
    """Where to fire the rays, read out of `site.json` rather than typed in.

    Every zone that carries a rectangle contributes its centre, so the probes
    follow the record: move a bed and the point that claims to be its centre
    moves with it. The previous list was five hard-coded pairs, two of which had
    been wrong for as long as anybody had been reading the output.
    """
    cells = []
    for key, spec in (site.get("zones") or {}).items():
        if not (spec.get("x") and spec.get("y")):
            continue
        cx = (float(spec["x"][0]) + float(spec["x"][1])) / 2.0
        cy = (float(spec["y"][0]) + float(spec["y"][1])) / 2.0
        short = spec.get("label_short") or spec.get("label") or key
        cells.append((f"{short} centre (zones.{key})", (cx, cy)))
    cells.append(("retired front_bed centre (fixed)", RETIRED_FRONT_BED))
    for label, (cx, cy) in cells:
        assert_outdoors(site, label, cx, cy)
    return cells


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
    cells = probe_cells(site)

    print("3. analytic (the model) vs marched (independent), per cell and hour")
    print(f"   {len(cells)} probes, {len(TIMES)} times, "
          f"peak altitude tested {max(sun_at(m, doy_of(w), h)[0] for w, h in TIMES):.1f} deg")
    disagreements = 0
    total = 0
    below = []
    for label, (cx, cy) in cells:
        print(f"\n   {label}  at ({cx:.0f}, {cy:.0f}) in")
        point = np.array([cx, cy, sunmodel.EYE], float)
        for when, hour in TIMES:
            alt, az = sun_at(m, doy_of(when), hour)
            if alt <= 0:
                # Counted and reported rather than passed over. A row that
                # quietly evaporates is a test nobody knows they are not
                # running, and one of the June rows was doing exactly that.
                below.append(f"{when} {hour:02d}:00")
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
    if below:
        seen = sorted(set(below))
        print(f"   {len(below)} row{'s' if len(below) != 1 else ''} skipped, "
              f"sun below the horizon: {', '.join(seen)}")

    # -- 4. the specific claim: can the pecans reach the retired front_bed box?
    print("\n4. could the pecans ever have shaded the retired front_bed box?")
    fb = np.array([*RETIRED_FRONT_BED, sunmodel.EYE])
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
