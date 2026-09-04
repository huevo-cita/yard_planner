#!/usr/bin/env python3
"""Check crown stacking and the crown verifier, on a yard built to trap them.

    python3 tools/test_crowns.py
    python3 tools/test_crowns.py -v

Three pieces of crown geometry, and each is here because the obvious wrong
implementation of it produces a plausible number rather than an error:

  a fused pair costs once     two trunks whose crowns grew together are one
                              canopy, and a beam crossing the join passes
                              through one mass of leaves. Under
                              `canopy_stacking: multiply` the model charged it
                              twice, to tau squared — 0.01 in leaf where the
                              crown gives 0.10. Nothing looks wrong about a bed
                              being dark; it is what a tree is for.

  grouping is not `single`    the fix is per-group, not global. Collapsing the
                              whole yard to `single` also stops two genuinely
                              separate trees attenuating in turn, which is a
                              second wrong answer bought with the first. The
                              fixture is arranged so the grouped answer, the
                              global-`single` answer and the ungrouped
                              `multiply` answer are three different numbers.

  engulfment is 3D            crowns float clear of the ground, so two that sit
                              one inside the other in plan can occupy separate
                              bands of height and share no volume at all. The
                              plan-only test reported cloverleaf-austin's t10
                              as double-counted inside t11 when t10 tops out at
                              14 ft and t11's crown starts at 18 ft.

  a label is a date           `verify_crowns.py` carried its day of year as a
                              bare integer beside a string label, and the two
                              disagreed: rows labelled 21 June ran on day 21,
                              which is January. So the tool had never once
                              tested high summer — the case that matters most,
                              because only a high sun puts the ray through the
                              crown instead of under it through the trunk.

  a probe is outdoors         the same tool held hard-coded bed centres that
                              went stale in place and ended up inside the house
                              footprint. Indoor cells agree perfectly between
                              the analytic and marched tests, so the check went
                              on reporting success while testing nothing.

Everything runs against dicts and a temporary GARDEN_ROOT. No real yard is read
or written.
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import drawsite, siteschema, solar, sunmodel, yards  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))
SLUG = "crowns-scratch"

# ---------------------------------------------------------------- the fixture
#
# All five trees are evergreen, so `transmissivity_leaf_on` is the whole story
# and no test turns on a leaf date. Every ray fired below goes straight up from
# a cell, so "which crowns are in the way" is just "whose plan circle covers the
# cell" and can be read off the coordinates by hand.
#
#   fused-a   r 60 at (300, 300), 10-20 ft up, tau 0.5
#   fused-b   r 60 at (340, 300), 10-20 ft up, tau 0.1   <- the more opaque
#             the declared pair. 80 in of plan overlap, identical height band.
#             Their taus DIFFER on purpose: with both at 0.1, taking the
#             minimum, taking the first and taking the last all agree, and the
#             test would pass against three different implementations.
#
#   above     r 40 at (320, 300), 25-33 ft up, tau 0.4
#             genuinely separate — it shares no height with the pair — and it
#             stands over them, so one upward ray crosses the group AND it.
#             This is the probe that separates the three candidate rules.
#
#   inner     r 20 at (300, 300), 11.7-16.7 ft up, tau 0.3
#             wholly inside fused-a in plan AND sharing 60 in of height, so it
#             is a real engulfment and has to be reported.
#
#   apart     r 50 at (150, 150), 10-20 ft up, tau 0.25
#             touches nothing. The control.
#
# Note what `above` does double duty as: in plan it sits wholly inside fused-a
# (20 in of centre offset plus a 40 in radius is exactly fused-a's 60), but its
# crown starts 60 in above where fused-a's ends. A plan-only engulfment test
# reports it and a 3D one does not. That is the t10/t11 case in miniature.
TREES = [
    {"id": "fused-a", "species": "pecan", "deciduous": False,
     "trunk_x": 300.0, "trunk_y": 300.0, "height": 240.0,
     "crown_radius": 60.0, "crown_base_height": 120.0,
     "transmissivity_leaf_on": 0.5, "transmissivity_leaf_off": 0.5},
    {"id": "fused-b", "species": "pecan", "deciduous": False,
     "trunk_x": 340.0, "trunk_y": 300.0, "height": 240.0,
     "crown_radius": 60.0, "crown_base_height": 120.0,
     "transmissivity_leaf_on": 0.1, "transmissivity_leaf_off": 0.1},
    {"id": "above", "species": "deciduous oak", "deciduous": False,
     "trunk_x": 320.0, "trunk_y": 300.0, "height": 400.0,
     "crown_radius": 40.0, "crown_base_height": 300.0,
     "transmissivity_leaf_on": 0.4, "transmissivity_leaf_off": 0.4},
    {"id": "inner", "species": "hackberry", "deciduous": False,
     "trunk_x": 300.0, "trunk_y": 300.0, "height": 200.0,
     "crown_radius": 20.0, "crown_base_height": 140.0,
     "transmissivity_leaf_on": 0.3, "transmissivity_leaf_off": 0.3},
    {"id": "apart", "species": "crape myrtle", "deciduous": False,
     "trunk_x": 150.0, "trunk_y": 150.0, "height": 240.0,
     "crown_radius": 50.0, "crown_base_height": 120.0,
     "transmissivity_leaf_on": 0.25, "transmissivity_leaf_off": 0.25},
]

GROUP = [{"id": "the-pair", "trees": ["fused-a", "fused-b"],
          "note": "grown together, one canopy"}]

SITE = {
    "yard": SLUG,
    "label": "scratch crowns",
    "address": {"lat": 30.3103215, "lon": -97.6982286,
                "timezone": "America/Chicago"},
    "frame": {"true_bearing_of_plus_x": 117.8},
    "boundary": {"width_east_west": 700.0, "south_boundary_offset": 700.0,
                 "north_fence_slope": 0.0},
    "zones": {
        # A bed whose rectangle is real ground, and a bed whose rectangle has
        # drifted inside the house. The second is the failure `assert_outdoors`
        # exists for, recorded here as data rather than described in a comment.
        "bed_outside": {"x": [600.0, 660.0], "y": [600.0, 660.0],
                        "label": "outside bed", "label_short": "out",
                        "style": "bed"},
        "bed_indoors": {"x": [120.0, 180.0], "y": [520.0, 580.0],
                        "label": "indoor bed", "label_short": "in",
                        "style": "bed"},
        "no_rectangle": {"label": "whole lot", "label_short": "lot"},
    },
    "features": {"canopy_stacking": "multiply", "trees": TREES},
    "obstructions": {
        "house_walls": {"polygon": [[100.0, 500.0], [400.0, 500.0],
                                    [400.0, 620.0], [100.0, 620.0],
                                    [100.0, 500.0]]},
    },
    "provenance": {},
}

# The grid step is chosen so that a cell centre lands exactly on each probe
# point below — centres sit at 5 + 10k inches. A test that had to settle for
# the nearest cell would be reasoning about a point it did not choose.
CELL = 10.0
DOY = 172

FAILURES = []
VERBOSE = False


def check(ok, name, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        if detail:
            print(f"          {detail}")
        FAILURES.append(name)


def site_with(**over):
    """A copy of the fixture, with `features` merged rather than replaced."""
    s = json.loads(json.dumps(SITE))
    for k, v in over.items():
        if k == "features":
            s["features"].update(v)
        else:
            s[k] = v
    return s


def straight_up(m, x, y):
    """The canopy multiplier for a ray fired vertically from (x, y).

    Vertical because it makes the geometry checkable by eye: the crowns in the
    way are exactly those whose plan circle covers the point, so the expected
    answer in each test below is arithmetic on the numbers in TREES and not a
    second implementation of the thing being tested.
    """
    d = np.array([0.0, 0.0, 1.0])
    i = int(np.argmin((m.px - x) ** 2 + (m.py - y) ** 2))
    if abs(m.px[i] - x) > 1e-9 or abs(m.py[i] - y) > 1e-9:
        raise AssertionError(
            f"no cell centre at ({x}, {y}); nearest is "
            f"({m.px[i]}, {m.py[i]}). The probe points and the grid step have "
            f"parted company, and every expectation below is about a point "
            f"that is no longer being sampled")
    mult, hit = m.canopy(d, DOY)
    return float(mult[i]), bool(hit[i])


def rows_from(site):
    """`engulfed_crowns` input, built straight from the record."""
    return [{"id": t["id"], "tree": t} for t in siteschema.trees(site)]


def load_verify_crowns():
    """Import the verifier as a module. It is a script, so it needs coaxing."""
    path = os.path.join(TOOLS, "verify_crowns.py")
    spec = importlib.util.spec_from_file_location("verify_crowns", path)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["verify_crowns.py"]          # it reads a slug off argv at import
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


# ----------------------------------------------------------- reading the group

def test_group_map():
    """The declaration is read, and an absent one means no groups at all."""
    g = sunmodel.canopy_groups(SITE)
    check(g == {}, "a record declaring no groups produces an empty map",
          f"got {g!r}. Anything else would change the meaning of every yard "
          f"that has never heard of canopy_groups")

    g = sunmodel.canopy_groups(site_with(features={"canopy_groups": GROUP}))
    check(g == {"fused-a": "the-pair", "fused-b": "the-pair"},
          "a declared group maps each member to the group id", f"got {g!r}")

    anon = [{"trees": ["fused-a", "fused-b"]}]
    g = sunmodel.canopy_groups(site_with(features={"canopy_groups": anon}))
    check(len(set(g.values())) == 1 and len(g) == 2,
          "a group with no id still binds its members together", f"got {g!r}")

    two = [{"id": "one", "trees": ["fused-a"]}, {"id": "two", "trees": ["above"]}]
    g = sunmodel.canopy_groups(site_with(features={"canopy_groups": two}))
    check(g == {"fused-a": "one", "above": "two"},
          "two one-member groups stay two groups, not one",
          f"got {g!r}. Members of different groups must still multiply")

    m = sunmodel.Model(site_with(features={"canopy_groups": GROUP}), cell=CELL)
    check(m.canopy_group == {"fused-a": "the-pair", "fused-b": "the-pair"},
          "the model exposes the same map it was built from",
          f"got {m.canopy_group!r}")


# ------------------------------------------------------------ what a beam pays

def test_fused_pair_pays_once():
    """A beam crossing the join is charged for one canopy, not two."""
    plain = sunmodel.Model(SITE, cell=CELL)
    grouped = sunmodel.Model(site_with(features={"canopy_groups": GROUP}),
                             cell=CELL)

    # (325, 345) is inside fused-a and fused-b and nothing else.
    was, _ = straight_up(plain, 325.0, 345.0)
    now, hit = straight_up(grouped, 325.0, 345.0)
    check(abs(was - 0.05) < 1e-12,
          "ungrouped, the overlap is charged twice — 0.5 x 0.1",
          f"got {was}. This is the bug, recorded so the fix has something to "
          f"be a fix of")
    check(abs(now - 0.1) < 1e-12,
          "grouped, the more opaque of the two wins — 0.1, not 0.05",
          f"got {now}, expected min(0.5, 0.1). 0.05 means the group is not "
          f"being read; 0.5 means the wrong end of the min")
    check(hit, "and the cell is still reported as canopy-hit",
          "a grouped crown still shades; only the arithmetic changed")


def test_grouped_is_not_global_single():
    """Groups multiply against each other. Collapsing them all is a second bug.

    (325, 305) lies under fused-a, fused-b and `above`. The three candidate
    rules give three different numbers, so this probe alone identifies which
    one is running:

        grouped         min(0.5, 0.1) x 0.4  = 0.04     <- right
        global single   min(0.5, 0.1, 0.4)   = 0.1
        plain multiply  0.5 x 0.1 x 0.4      = 0.02
    """
    grouped = sunmodel.Model(site_with(features={"canopy_groups": GROUP}),
                             cell=CELL)
    got, _ = straight_up(grouped, 325.0, 305.0)
    check(abs(got - 0.04) < 1e-12,
          "a group and a separate tree still multiply against each other",
          f"got {got}. 0.1 means grouping collapsed the whole yard to "
          f"`single`; 0.02 means the group was ignored")

    single = sunmodel.Model(
        site_with(features={"canopy_stacking": "single",
                            "canopy_groups": GROUP}), cell=CELL)
    got, _ = straight_up(single, 325.0, 305.0)
    check(abs(got - 0.1) < 1e-12,
          "`single` stacking still means the most opaque crown on the lot wins",
          f"got {got}, expected min(0.5, 0.1, 0.4). A declared group must not "
          f"change what `single` has always meant")


def test_ungrouped_record_is_untouched():
    """The generalisation has to be exactly free for every record without one.

    This is the check that lets the change ship: a yard that has never declared
    a group must produce bit-identical numbers, or the fix has quietly re-lit
    every other yard in the garden while nobody was reading.
    """
    m = sunmodel.Model(SITE, cell=CELL)
    for x, y, want, why in [
            (325.0, 345.0, 0.5 * 0.1, "two crowns in the way multiply"),
            (325.0, 305.0, 0.5 * 0.1 * 0.4, "three crowns in the way multiply"),
            (305.0, 305.0, 0.5 * 0.1 * 0.4 * 0.3, "four, including the inner"),
            (155.0, 155.0, 0.25, "one crown alone is just its own tau"),
            (655.0, 655.0, 1.0, "open sky is unattenuated")]:
        got, _ = straight_up(m, x, y)
        check(abs(got - want) < 1e-12,
              f"undeclared, ({x:.0f}, {y:.0f}) is unchanged: {why}",
              f"got {got}, expected {want}")


def test_group_of_one_and_unknown_ids():
    """A group naming a tree that is not there must not swallow the others."""
    odd = [{"id": "ghost", "trees": ["not-a-tree", "fused-a"]}]
    m = sunmodel.Model(site_with(features={"canopy_groups": odd}), cell=CELL)
    got, _ = straight_up(m, 325.0, 345.0)
    check(abs(got - 0.05) < 1e-12,
          "a group with one real member behaves as no group at all",
          f"got {got}, expected 0.5 x 0.1. A missing id must not pull fused-b "
          f"into the group by accident")


# --------------------------------------------------------------- engulfment

def test_engulfment_needs_shared_height():
    """Plan containment is not containment. Crowns float."""
    rows = rows_from(SITE)
    pairs = drawsite.engulfed_crowns(rows, "multiply")

    check(("inner", "fused-a") in pairs,
          "a crown inside another in plan AND in height is reported",
          f"got {pairs}. inner sits at 140-200 in inside fused-a's 120-240, so "
          f"a ray really can cross both")
    check(("above", "fused-a") not in pairs,
          "one inside another in plan but not in height is NOT reported",
          f"got {pairs}. `above` starts at 300 in and fused-a stops at 240, so "
          f"they share no volume and nothing is attenuated twice. This is "
          f"cloverleaf-austin's t10-inside-t11 in miniature")
    check(("fused-a", "inner") not in pairs,
          "and the relation is reported in one direction only", f"got {pairs}")

    check(drawsite._height_overlap(TREES[3], TREES[0]) == 60.0,
          "shared height is measured in inches, not asserted as a boolean",
          f"got {drawsite._height_overlap(TREES[3], TREES[0])}")
    check(drawsite._height_overlap(TREES[2], TREES[0]) == -60.0,
          "and comes back negative for a gap, naming how big the gap is",
          f"got {drawsite._height_overlap(TREES[2], TREES[0])}")


def test_engulfment_skips_declared_groups():
    """A fused pair is not a double count any more, so it is not reported."""
    fused_inner = json.loads(json.dumps(SITE))
    # Put `inner` in a group with the crown that swallows it.
    fused_inner["features"]["canopy_groups"] = [
        {"id": "one-mass", "trees": ["inner", "fused-a"]}]
    rows = rows_from(fused_inner)
    groups = sunmodel.canopy_groups(fused_inner)

    check(("inner", "fused-a") in drawsite.engulfed_crowns(rows, "multiply"),
          "the pair is a double count while it is undeclared",
          "the group has to be what silences it, not the geometry")
    check(("inner", "fused-a")
          not in drawsite.engulfed_crowns(rows, "multiply", groups),
          "and is silent once declared, because the model now charges it once",
          f"got {drawsite.engulfed_crowns(rows, 'multiply', groups)}")
    check(drawsite.engulfed_crowns(rows, "single", groups) == [],
          "`single` stacking has nothing to report either way",
          "the most opaque crown wins, so an overlap costs nothing")


# --------------------------------------------------- the verifier's own inputs

def test_day_of_year_comes_from_the_label():
    """The bug: rows labelled 21 June were computed for 21 January."""
    vc = load_verify_crowns()

    check(vc.doy_of("Jun 21") == 172,
          "the June label resolves to midsummer, not to day 21",
          f"got {vc.doy_of('Jun 21')}. Day 21 is 21 January, which is what the "
          f"three June rows were actually testing")

    # The consequence, in the units the tool prints. Noon altitude is what a
    # reader would have had to notice to catch this, and 39.6 is not obviously
    # wrong unless you know it should be 83.1.
    lat = SITE["address"]["lat"]
    summer = solar.position(vc.doy_of("Jun 21"), 12.0, lat)[0]
    winter = solar.position(21, 12.0, lat)[0]
    check(summer > 80.0,
          "so the June rows now run on high summer sun, above 80 degrees",
          f"got {summer:.1f} deg")
    check(winter < 45.0,
          "where day 21 gives a midwinter noon under 45 degrees",
          f"got {winter:.1f} deg — the number the tool used to print for June")

    for label, _ in vc.TIMES:
        if label not in solar.DOY:
            check(False, f"every label in TIMES is a real date ({label})",
                  f"{label!r} is not in solar.DOY")
            break
    else:
        check(True, "every label in TIMES is a real date solar.DOY knows")

    peak = max(solar.position(vc.doy_of(w), h, lat)[0] for w, h in vc.TIMES)
    check(peak > 80.0,
          "and the set as a whole still exercises high sun through a crown",
          f"peak altitude {peak:.1f} deg. A crown check that never fires a "
          f"steep ray never tests the geometry it exists for: a low sun goes "
          f"under the crown through the bare trunk")

    try:
        vc.doy_of("21 Jun")
        check(False, "a label that is not a real date is refused",
              "the old spelling '21 Jun' was accepted and paired with a "
              "hand-written integer; it has to fail loudly now")
    except SystemExit as e:
        check("solar.DOY" in str(e) or "not a date" in str(e),
              "a label that is not a real date is refused, and says so",
              f"raised, but with {str(e)!r}")


def test_probes_are_outdoors_and_derived():
    """Probe points follow the record, and never point inside the house."""
    vc = load_verify_crowns()

    outdoor_only = json.loads(json.dumps(SITE))
    del outdoor_only["zones"]["bed_indoors"]
    cells = vc.probe_cells(outdoor_only)
    got = dict(cells)

    labels = [lab for lab, _ in cells]
    check(any("zones.bed_outside" in lab for lab in labels),
          "every zone carrying a rectangle contributes a probe", f"got {labels}")
    check(not any("no_rectangle" in lab for lab in labels),
          "a zone with no rectangle has no centre and contributes none",
          f"got {labels}")
    check(any("retired front_bed" in lab for lab in labels),
          "the retired front_bed probe survives, being a place not in the record",
          f"got {labels}")

    centre = [xy for lab, xy in cells if "bed_outside" in lab][0]
    check(centre == (630.0, 630.0),
          "a probe is the centre of the rectangle site.json holds",
          f"got {centre}, expected the centre of x [600, 660] y [600, 660]")

    moved = json.loads(json.dumps(outdoor_only))
    moved["zones"]["bed_outside"]["x"] = [660.0, 680.0]
    shifted = [xy for lab, xy in vc.probe_cells(moved) if "bed_outside" in lab][0]
    check(shifted == (670.0, 630.0),
          "move the bed and the probe moves with it, which is the whole point",
          f"got {shifted}. The two that went stale were hard-coded pairs that "
          f"kept their names for weeks after the beds moved")

    # And the trap: the indoor bed is in the real fixture, so the full record
    # must be refused rather than quietly probed.
    try:
        vc.probe_cells(SITE)
        check(False, "a probe that lands inside the house is refused",
              "bed_indoors centres on (150, 550), inside the wall polygon. "
              "Model drops that cell as indoors, so analytic and marched agree "
              "perfectly and the check reports success while testing nothing")
    except SystemExit as e:
        check("house_walls" in str(e) and "indoors" in str(e),
              "a probe that lands inside the house is refused, and says which",
              f"raised, but with {str(e)!r}")

    check(vc.assert_outdoors(outdoor_only, "fine", 630.0, 630.0) is None,
          "and a point on real ground passes without comment")

    no_walls = json.loads(json.dumps(outdoor_only))
    no_walls["obstructions"] = {}
    check(vc.assert_outdoors(no_walls, "anywhere", 150.0, 550.0) is None,
          "a record with no house polygon cannot be checked, and does not fail",
          "the assertion is evidence when it fires, not a requirement that "
          "every yard describe its house")


def test_verifier_probes_the_real_yard_outdoors():
    """The regression, on the record the bug was found in.

    A unit test on a fixture cannot catch the failure that actually happened,
    which was a real yard's beds moving under a hard-coded list. This asserts
    the derived probes on the shipped yard are all outdoors — the property that
    was silently false for as long as anyone had been reading the output.
    """
    root = os.path.join(os.path.dirname(TOOLS), "cloverleaf-austin")
    if not os.path.isdir(root):
        check(True, "cloverleaf-austin is not present; skipped")
        return
    vc = load_verify_crowns()
    site = json.load(open(os.path.join(root, "site.json")))
    try:
        cells = vc.probe_cells(site)
        check(len(cells) > 5,
              f"the real yard yields {len(cells)} probes, none of them indoors")
    except SystemExit as e:
        check(False, "every derived probe on cloverleaf-austin is outdoors",
              str(e))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    globals()["VERBOSE"] = args.verbose

    root = tempfile.mkdtemp(prefix="crowns-test-")
    was = yards.GARDEN_ROOT
    try:
        yards.GARDEN_ROOT = root
        print("\nreading the group declaration")
        test_group_map()
        print("\nwhat a beam pays crossing a fused pair")
        test_fused_pair_pays_once()
        test_grouped_is_not_global_single()
        test_ungrouped_record_is_untouched()
        test_group_of_one_and_unknown_ids()
        print("\nengulfment, in three dimensions")
        test_engulfment_needs_shared_height()
        test_engulfment_skips_declared_groups()
        print("\nthe verifier's own inputs")
        test_day_of_year_comes_from_the_label()
        test_probes_are_outdoors_and_derived()
        test_verifier_probes_the_real_yard_outdoors()
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed:")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("all passed.")


if __name__ == "__main__":
    main()
