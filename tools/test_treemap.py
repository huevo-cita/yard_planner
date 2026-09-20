#!/usr/bin/env python3
"""Check the tree map's ranking and its north arrow on a yard built to trap them.

    python3 tools/test_treemap.py
    python3 tools/test_treemap.py -v

The drawing exists to be carried outside and disagreed with, so the ways it can
fail are the ways a person outside would not notice:

  north is derived            `frame.yard_north_true_bearing` is a copy of a
                              number `frame.true_bearing_of_plus_x` already
                              fixes. A stale copy points the arrow somewhere
                              plausible and wrong, and every comparison made
                              against the ground is then wrong with it. So the
                              angle is recomputed and the copy is only a
                              fallback. A yard whose two fields disagree has to
                              come back with the derived answer and say which
                              stored value it overrode.

  the cut is not arbitrary    the measure/skip threshold is the narrowest gap
                              between two of `design.LIGHT_NEED`'s categories,
                              because "this crown matters" can only honestly
                              mean "its own radius can move a bed from one
                              nursery label to the next". A hard-coded number
                              would be the one thing on the drawing nobody
                              could argue with on the merits.

  the ranking is about cast    not about radius, and not about overhang. The
                              largest crown in the trap yard stands due north
                              of the bed and can never be between it and the
                              sun; the tree that shades it most does not
                              overhang it at all. Each of the two obvious
                              proxies picks a different wrong tree, and both
                              look sensible in the output.

  grazing sun is not cast      shadow length goes as 1/tan(altitude), so with
                              no altitude floor every crown reaches every bed
                              at dawn and the ranking degenerates into a list
                              of tree sizes. This is how the check found its
                              own first version wrong.

  paces carry their stride    a distance in paces with no stride behind it
                              cannot be checked or corrected, so `PACE_FT` has
                              to divide the radius and has to be printed.

  overhanging is not shading  a crown standing over a bed and a crown that
                              casts onto it are different claims. Only the
                              first can be verified by looking up, which is why
                              both are reported.

  engulfed crowns are named   under `canopy_stacking: multiply` a crown wholly
                              inside another attenuates the shared ground
                              twice. Nobody can pace the inner one as a
                              separate canopy either, so asking for it is
                              asking for something that does not exist.

  panels do not overflow      text is wrapped to a column measured off the
                              glyphs, and the scale that converts inches of
                              ground to inches of paper has to account for an
                              equal-aspect axis shrinking its width to fit its
                              height. Get that wrong and prose prints out
                              through the border of its own box, which reads as
                              a font fault rather than an overflow.

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written.
"""
import argparse
import json
import math
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matplotlib  # noqa: E402
matplotlib.use("Agg")

from lib import design, drawsite, yards  # noqa: E402

SLUG = "testyard-treemap"

# Five trees placed so that ranking by crown radius, or by distance, or by
# whether the crown stands over the bed, each gets a different answer — and
# only one of the three is right. The bed is a 4 ft square on an otherwise
# empty lot, with no house and no fences, so nothing but a crown can cast on
# it. Positions are in the yard frame, whose +x bears 117.8 true, so "due
# south" is neither +x nor +y and cannot be eyeballed from the numbers.
#
#   far-huge    the LARGEST crown in the yard, 25 ft, on a 50 ft trunk — and
#               167 ft due NORTH of the bed, where the sun at this latitude
#               never puts it between the bed and the light. Sorting by radius
#               ranks it first. It should be skipped.
#   near-tall   a 15 ft crown 33 ft due SOUTH, whose shadow sweeps the bed
#               through the middle of every day. It does not overhang the bed
#               at all, so a check based on overhang skips it. It is the one
#               tree here worth walking out to.
#   over-bed    a 3 ft crown standing directly ON the bed, which is what makes
#               it checkable by looking up, and which is not the same as
#               shading it: a short crown's shadow lands well off to the side
#               for most of the day.
#   engulfed    a 2 ft crown wholly inside `over-bed`'s, to be named as
#               double-counted rather than sent out to be paced.
#   holly       evergreen, so the leaf-state branch is exercised and the
#               legend has something to say about December.
SITE = {
    "yard": SLUG,
    "label": "scratch tree map",
    "address": {"lat": 30.3103215, "lon": -97.6982286, "timezone": "America/Chicago"},
    "frame": {
        "true_bearing_of_plus_x": 117.8,
        # Deliberately WRONG by 90 degrees. The derived answer is 27.8.
        "yard_north_true_bearing": 117.8,
    },
    "boundary": {"width_east_west": 700.0, "south_boundary_offset": 700.0,
                 "north_fence_slope": 0.0, "area_sqft": 3403},
    "zones": {
        "bed_target": {"x": [330.0, 378.0], "y": [330.0, 378.0],
                       "label": "target bed", "label_short": "target",
                       "style": "bed"},
        "bed_spare": {"x": [40.0, 88.0], "y": [40.0, 88.0],
                      "label": "spare bed", "label_short": "spare",
                      "style": "bed"},
    },
    "features": {
        "canopy_stacking": "multiply",
        "trees": [
            {"id": "far-huge", "species": "deciduous oak", "deciduous": True,
             "leaf_on": "03-15", "leaf_off": "12-05", "trunk_x": -578.8,
             "trunk_y": -1415.2, "height": 600.0, "crown_radius": 300.0,
             "crown_base_height": 270.0},
            {"id": "near-tall", "species": "pecan", "deciduous": True,
             "leaf_on": "03-25", "leaf_off": "11-15", "trunk_x": 540.6,
             "trunk_y": 707.8, "height": 480.0, "crown_radius": 180.0,
             "crown_base_height": 216.0},
            {"id": "over-bed", "species": "crape myrtle", "deciduous": True,
             "leaf_on": "04-01", "leaf_off": "11-25", "trunk_x": 354.0,
             "trunk_y": 354.0, "height": 216.0, "crown_radius": 36.0,
             "crown_base_height": 97.2},
            {"id": "engulfed", "species": "hackberry", "deciduous": True,
             "leaf_on": "03-10", "leaf_off": "11-20", "trunk_x": 354.0,
             "trunk_y": 354.0, "height": 144.0, "crown_radius": 24.0,
             "crown_base_height": 64.8},
            {"id": "holly", "species": "yaupon holly", "deciduous": False,
             "trunk_x": 60.0, "trunk_y": 60.0, "height": 240.0,
             "crown_radius": 48.0, "crown_base_height": 108.0},
        ],
    },
    "obstructions": {},
    "provenance": {
        "features.trees.0.height": {"source": "reported", "note": "by eye"},
        "features.trees.0.crown_radius": {"source": "reported", "note": "by eye"},
        "features.trees.1.height": {"source": "measured", "note": "taped"},
        "features.trees.1.crown_radius": {"source": "reported", "note": "by eye"},
    },
    "drawings": {
        "tree_map": {"decisive_zones": {"zones": ["bed_target"],
                                        "cites": "d99"}},
    },
}

FAILURES = []


def check(ok, name, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        if detail:
            print(f"          {detail}")
        FAILURES.append(name)


def build(root):
    d = os.path.join(root, SLUG)
    os.makedirs(d)
    with open(os.path.join(d, "site.json"), "w") as fh:
        json.dump(SITE, fh, indent=2)
    return d


def by_id(rows):
    return {r["id"]: r for r in rows}


# ------------------------------------------------------------------- north

def test_north():
    """The arrow is recomputed, and a disagreeing copy is reported not used."""
    angle, overridden = drawsite.north_plot_angle(SITE)
    check(abs(angle - 27.8) < 1e-6,
          "north is derived from the +x bearing, not read from the copy",
          f"got {angle}, expected 27.8 from a +x bearing of 117.8. The stored "
          f"yard_north_true_bearing is 117.8 and is wrong")
    check(overridden == 117.8,
          "the stale stored value comes back so a caller can say so",
          f"got {overridden!r}")

    # The derived angle has to point where the frame says north is: the arrow
    # is drawn as (-sin a, cos a) and north lies at the +x bearing measured
    # anticlockwise from the drawn x axis.
    a = math.radians(angle)
    b = math.radians(SITE["frame"]["true_bearing_of_plus_x"])
    check(abs(-math.sin(a) - math.cos(b)) < 1e-9
          and abs(math.cos(a) - math.sin(b)) < 1e-9,
          "the drawn arrow points along the frame's own north",
          f"arrow ({-math.sin(a):.4f}, {math.cos(a):.4f}) vs frame "
          f"({math.cos(b):.4f}, {math.sin(b):.4f})")

    agree = dict(SITE, frame={"true_bearing_of_plus_x": 95.69,
                              "yard_north_true_bearing": 5.69})
    check(drawsite.north_plot_angle(agree)[1] is None,
          "a copy that agrees is not reported as an override")

    bare = dict(SITE, frame={"yard_north_true_bearing": 42.0})
    check(drawsite.north_plot_angle(bare) == (42.0, None),
          "with no bearing to derive from, the stored value is used",
          "a yard whose frame predates the bearing field still gets an arrow")

    # Every real yard should already agree; if one stops, that is the drift
    # this exists to catch.
    for slug in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, slug, "site.json")
        if not os.path.isfile(p):
            continue
        with open(p) as fh:
            site = json.load(fh)
        _, bad = drawsite.north_plot_angle(site)
        check(bad is None,
              f"{slug}'s stored north agrees with its +x bearing",
              f"stored {bad}, derived "
              f"{drawsite.north_plot_angle(site)[0]:.2f}")


# ---------------------------------------------------------------- the cut

def test_threshold():
    """The measure/skip cut is read off the light categories, not chosen."""
    band = drawsite._light_band()
    floors = sorted({v[0] for v in design.LIGHT_NEED.values()})
    want = min(b - a for a, b in zip(floors, floors[1:]))
    check(abs(band - want) < 1e-9,
          "the threshold is the narrowest gap between two light categories",
          f"got {band}, expected {want} from {floors}")
    check(band > 0, "and it is a real distance", f"got {band}")
    check(drawsite.CHECK_ALT_FLOOR >= 5.0,
          "and grazing sun is refused rather than cast",
          f"CHECK_ALT_FLOOR is {drawsite.CHECK_ALT_FLOOR}; near the horizon a "
          f"shadow is arbitrarily long and every tree governs every bed")


# --------------------------------------------------------------- the ranking

def test_ranking(verbose=False):
    root = tempfile.mkdtemp(prefix="treemap-test-")
    was = yards.GARDEN_ROOT
    try:
        yards.GARDEN_ROOT = root
        build(root)
        site = yards.load_site(SLUG)
        rows, meta = drawsite.crown_field_check(site, SLUG)
        if verbose:
            for r in rows:
                print(f"        {r['id']:<12} r {r['radius_ft']:5.1f} ft  "
                      f"{r['paces']:5.1f} paces  {r['tier']:<8} "
                      f"worst {r['worst']:5.2f}  governs "
                      f"{','.join(r['governs']) or '-':<10} over "
                      f"{','.join(r['overhangs']) or '-'}")

        check(meta["zones"] == ["target"],
              "the decisive zone comes from the yard's own drawings block",
              f"got {meta['zones']}")
        check("d99" in meta["source"],
              "and it says which card it was measured for",
              f"got {meta['source']!r}")

        r = by_id(rows)
        check(set(r) == {"far-huge", "near-tall", "over-bed", "engulfed",
                         "holly"},
              "every tree gets a row", f"got {sorted(r)}")

        biggest = max(rows, key=lambda q: q["radius_ft"])
        check(biggest["id"] == "far-huge" and biggest["tier"] == "skip",
              "the largest crown in the yard is the one marked skip",
              f"largest is {biggest['id']!r} at tier {biggest['tier']} "
              f"(worst {biggest['worst']:.3f}). It stands due north of the "
              f"bed, where it can never be between the bed and the sun; a "
              f"ranking by radius would send somebody out to measure it first")
        check(r["far-huge"]["governs"] == [] and r["far-huge"]["worst"] == 0.0,
              "and it governs nothing, exactly",
              f"got {r['far-huge']['governs']} worst "
              f"{r['far-huge']['worst']:.3f}")

        check(r["near-tall"]["tier"] == "measure",
              "the tree whose shadow crosses the bed is worth measuring",
              f"got tier={r['near-tall']['tier']} worst="
              f"{r['near-tall']['worst']:.3f}")
        check(rows[0]["id"] == "near-tall",
              "and it sorts to the top, worst first",
              f"got {rows[0]['id']!r} first")
        check(r["near-tall"]["worst"] > r["far-huge"]["worst"],
              "cast beats radius in the ranking",
              f"{r['near-tall']['worst']:.3f} vs "
              f"{r['far-huge']['worst']:.3f}")

        # Both directions of the distinction, because each one alone is a
        # plausible-looking check that gets a tree wrong.
        check(r["over-bed"]["overhangs"] == ["target"],
              "a crown standing over the bed says so",
              f"got {r['over-bed']['overhangs']}. This is the only claim on "
              f"the drawing that can be checked by looking up")
        check(r["near-tall"]["overhangs"] == []
              and r["near-tall"]["worst"] > r["over-bed"]["worst"],
              "and the tree that shades it most overhangs it not at all",
              f"near-tall overhangs {r['near-tall']['overhangs']} and scores "
              f"{r['near-tall']['worst']:.3f} against over-bed's "
              f"{r['over-bed']['worst']:.3f}. Ranking by overhang would skip "
              f"the tree that matters")
        check(r["far-huge"]["overhangs"] == [],
              "and a crown nowhere near the bed claims neither")

        for row in rows:
            check(abs(row["paces"] * drawsite.PACE_FT - row["radius_ft"]) < 1e-9,
                  f"{row['id']}'s paces are its radius over the stated stride",
                  f"{row['paces']:.3f} paces x {drawsite.PACE_FT} != "
                  f"{row['radius_ft']:.3f} ft")

        check(r["near-tall"]["height_src"] == "measured"
              and r["far-huge"]["height_src"] == "reported",
              "provenance is carried through per tree, per field",
              f"got {r['near-tall']['height_src']!r} and "
              f"{r['far-huge']['height_src']!r}")
        check(r["holly"]["height_src"] == "—",
              "a tree with no provenance entry is not silently promoted",
              f"got {r['holly']['height_src']!r}")
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)


def test_engulfed():
    """A crown wholly inside another is named, and only when stacking counts."""
    root = tempfile.mkdtemp(prefix="treemap-test-")
    was = yards.GARDEN_ROOT
    try:
        yards.GARDEN_ROOT = root
        build(root)
        site = yards.load_site(SLUG)
        rows, _ = drawsite.crown_field_check(site, SLUG)
        pairs = drawsite.engulfed_crowns(rows, "multiply")
        check(("engulfed", "over-bed") in pairs,
              "a crown wholly inside another is reported under multiply",
              f"got {pairs}. Under canopy_stacking: multiply the shared ground "
              f"is attenuated twice and nobody can pace the inner canopy")
        check(("over-bed", "engulfed") not in pairs,
              "and only in the one direction that is true",
              f"got {pairs}")
        check(drawsite.engulfed_crowns(rows, "single") == [],
              "under `single` stacking there is nothing to report",
              "the most opaque crown wins, so the overlap costs nothing")
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)


def test_leaf_dates():
    check(drawsite.leaf_date("11-20") == "20 Nov",
          "a leaf-off date is written the way a person reads one",
          f"got {drawsite.leaf_date('11-20')!r}")
    check(drawsite.leaf_date(None) == "None",
          "and a missing one does not raise",
          "an unlabelled tree still has to appear on the map")


# ------------------------------------------------------------------ layout

def test_scale_honours_aspect():
    """Inches of ground per inch of paper, with an equal-aspect axis in play.

    The failure this guards is silent: too small a figure means every column
    is believed wider than it is, and the prose measured against it prints out
    through the border of its own panel.
    """
    ext = [0.0, 1000.0, -3000.0, 0.0]
    fig, ax = drawsite.frame(ext, [8.0, 8.0])
    got = drawsite.data_per_inch(fig, ax, ext)
    pos = ax.get_position()
    fw, fh = fig.get_size_inches()
    naive = (ext[1] - ext[0]) / (pos.width * fw)
    tall = (ext[3] - ext[2]) / (pos.height * fh)
    check(abs(got - max(naive, tall)) < 1e-9,
          "the scale is whichever axis binds, not always the width",
          f"got {got:.3f}, width says {naive:.3f}, height says {tall:.3f}")
    check(got >= naive,
          "and it is never optimistic, which is the direction that overflows",
          f"got {got:.3f} against {naive:.3f}")

    grown = (ext[2] - 800.0, ext[3])
    check(drawsite.data_per_inch(fig, ax, ext, ylim=grown)
          > drawsite.data_per_inch(fig, ax, ext),
          "growing the y range for a header rescales the drawing",
          "a caller that measures before the header is added and wraps after "
          "it has wrapped to a column that no longer exists")
    matplotlib.pyplot.close(fig)


def test_width_cache():
    """Cached glyph widths still scale exactly with type size."""
    s = "the west fence is 72 in of solid board — or 36 in of open rail"
    one = drawsite.text_width_in(s, 1.0)
    for size in (5.4, 7.4, 9.0, 16.0):
        check(abs(drawsite.text_width_in(s, size) - one * size) < 1e-9,
              f"width at {size} pt is the width at 1 pt times {size}",
              f"got {drawsite.text_width_in(s, size)}, expected {one * size}")
    check(drawsite.text_width_in("", 9.0) == 0.0,
          "and an empty string has no width")
    check(drawsite._wrap_ceiling([s], 4.0, 7.4) > len(s) * 0.3,
          "the wrap ceiling is not below the answer it is meant to bound",
          "a ceiling under the true wrap width silently narrows the column")


def test_draws(verbose=False):
    """The whole drawing renders, on a yard with no house and no fences."""
    root = tempfile.mkdtemp(prefix="treemap-test-")
    was = yards.GARDEN_ROOT
    try:
        yards.GARDEN_ROOT = root
        build(root)
        site = yards.load_site(SLUG)
        out = os.path.join(root, "tree-map.png")
        drawsite.draw_tree_map(site, out, SLUG)
        check(os.path.isfile(out) and os.path.getsize(out) > 20000,
              "the tree map renders to a real file",
              f"size {os.path.getsize(out) if os.path.isfile(out) else 0}")
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print("\nnorth is derived, not trusted")
    test_north()
    print("\nthe measure/skip cut comes from the light categories")
    test_threshold()
    print("\nranking is about cast, not radius and not overhang")
    test_ranking(args.verbose)
    print("\ncrowns swallowed by other crowns")
    test_engulfed()
    print("\ndates a person can read")
    test_leaf_dates()
    print("\nground per inch of paper")
    test_scale_honours_aspect()
    print("\nglyph widths, cached")
    test_width_cache()
    print("\nthe drawing itself")
    test_draws(args.verbose)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: " + ", ".join(FAILURES))
        raise SystemExit(1)
    print("all passed.")


if __name__ == "__main__":
    main()
