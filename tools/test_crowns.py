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

  a crown is not a circle     cloverleaf-austin's t11 reaches 17 ft on the
                              property line and 22 ft on one limb, so it is
                              modelled as ellipsoid wedges. The wrong
                              implementations all produce plausible shade: a
                              22 ft circle over-shades 610 sq ft to cover one
                              limb, a wedge test that ignores the bearing
                              shades in every direction at once, and a
                              `true_bearing` read as a yard-frame angle points
                              the limb 118 degrees away from where it grows.

  the other thirteen          and the whole thing is opt-in, so a tree with no
                              `crown_plan` has to come out bit-for-bit as
                              before. That is a golden-hash test rather than an
                              argument, because "I only touched the new path"
                              is exactly what somebody says before they find
                              out otherwise.

Everything runs against dicts and a temporary GARDEN_ROOT. No real yard is read
or written.
"""
import argparse
import hashlib
import importlib.util
import json
import math
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


# ------------------------------------------------------- a crown that is not round
#
# Everything below hangs off `apart`, the control crown at (150, 150) with a
# 50 in radius that touches nothing else, so an arc bolted onto it cannot
# disturb any expectation above. The frame bears 117.8, so true bearing 117.8 is
# yard +x and 297.8 is yard -x.
#
# The arc reaches 150 in on one bearing against a 50 in bulk. Two probes sit
# 105.1 in from the trunk — past the bulk, inside the arc's reach — on opposite
# bearings, so they are the same distance out and differ only in direction:
#
#   (255, 155)   true 120.5, inside an arc centred on 117.8
#   ( 45, 145)   true 300.5, inside an arc centred on 297.8
#
# and (305, 155) is on the long bearing but 155.1 in out, past the arc's reach.
LIMB_EAST = {"arcs": [{"id": "limb", "true_bearing": 117.8, "width_deg": 20.0,
                       "radius": 150.0, "note": "yard +x"}]}
LIMB_WEST = {"arcs": [{"id": "limb", "true_bearing": 297.8, "width_deg": 20.0,
                       "radius": 150.0, "note": "yard -x"}]}

# The golden hashes are of `Model.day()` for the fixture exactly as it stands at
# the top of this file — five circular crowns, no plan profile anywhere. They
# were taken from the code as it was before crowns learned to be asymmetric.
# Nothing here is a claim about whether those numbers are RIGHT; the claim is
# that a tree with no `crown_plan` is modelled by the same arithmetic as
# before, to the last bit, and the only way to hold that down is to have
# written the bits down first.
GOLDEN_DAY = {
    79: ("a1d945153b7e8b56", "691777500b25b4fa"),
    172: ("56248a024098ba12", "024325975148591a"),
    355: ("89289d0819801d60", "93435c9d1febbf1b"),
}
GOLDEN_GROUPED_JUN = "1bd0400deed204f2"


def digest(a):
    return hashlib.sha256(
        np.ascontiguousarray(a, dtype="<f8").tobytes()).hexdigest()[:16]


def with_plan(plan, tree="apart", **over):
    """The fixture with one tree given a crown plan."""
    s = site_with(**over)
    for t in s["features"]["trees"]:
        if t["id"] == tree:
            t["crown_plan"] = plan
    return s


def test_untouched_trees_are_bit_identical():
    """The other thirteen. A golden hash, not an argument."""
    m = sunmodel.Model(SITE, cell=CELL)
    for doy, (want_eff, want_clear) in GOLDEN_DAY.items():
        eff, clear = m.day(doy)
        check(digest(eff) == want_eff and digest(clear) == want_clear,
              f"day {doy} on five circular crowns is bit-for-bit unchanged",
              f"got {digest(eff)}/{digest(clear)}, expected "
              f"{want_eff}/{want_clear}. Every crown here is a plain "
              f"crown_radius, so the wedge machinery must not be running at "
              f"all — not 'agreeing to five decimals', which is what a "
              f"refactor through the general path would give")

    g = sunmodel.Model(site_with(features={"canopy_groups": GROUP}), cell=CELL)
    eff, _ = g.day(172)
    check(digest(eff) == GOLDEN_GROUPED_JUN,
          "and unchanged with a declared canopy group, too",
          f"got {digest(eff)}, expected {GOLDEN_GROUPED_JUN}")

    check(sunmodel.Model(SITE, cell=CELL).crowns[0].wedges is None,
          "a tree with no crown_plan carries no wedges at all",
          "the circular path is a separate branch, not a one-wedge special "
          "case of the general one")


def test_a_uniform_plan_is_the_circle_it_generalises():
    """Wedges that all carry the bulk radius must tile back into the circle.

    This is the arithmetic check on the tiling itself — the gaps between arcs,
    the wrap past 360, the splitting of anything wider than a semicircle. Get
    any of those wrong and a sliver of crown goes missing, which shows up as a
    slightly brighter yard and nothing else.
    """
    uniform = {"arcs": [
        {"id": "a", "true_bearing": 117.8, "width_deg": 40.0, "radius": 50.0},
        {"id": "b", "true_bearing": 200.0, "width_deg": 30.0, "radius": 50.0}]}
    plain = sunmodel.Model(SITE, cell=CELL)
    same = sunmodel.Model(with_plan(uniform), cell=CELL)
    for doy in (79, 172, 355):
        a, _ = plain.day(doy)
        b, _ = same.day(doy)
        check(float(np.abs(a - b).max()) == 0.0,
              f"day {doy}: a plan describing one radius all round is the circle",
              f"worst cell differs by {float(np.abs(a - b).max())}. A gap "
              f"between two wedges, or a wrap past 360, loses a sliver of "
              f"crown and quietly brightens the yard")

    wedges = siteschema.crown_wedges(
        {"id": "u", "crown_radius": 50.0, "crown_plan": uniform}, 117.8)
    span = sum(hi - lo for lo, hi, _ in wedges)
    check(abs(math.degrees(span) - 360.0) < 1e-9,
          "the wedges cover the full circle exactly once",
          f"they cover {math.degrees(span):.6f} deg")
    widest = max(math.degrees(hi - lo) for lo, hi, _ in wedges)
    check(widest <= siteschema.MAX_WEDGE_DEG + 1e-9,
          "and none is wider than a semicircle, which a half-plane pair "
          "cannot describe", f"widest is {widest:.3f} deg")

    errs, warns = siteschema.validate(
        {"address": {"lat": 30.0, "lon": -97.0, "timezone": "America/Chicago"},
         "boundary": {"width_east_west": 700.0, "south_boundary_offset": 700.0,
                      "north_fence_slope": 0.0},
         "frame": {"true_bearing_of_plus_x": 117.8},
         "features": {"trees": [{"id": "u", "trunk_x": 1.0, "trunk_y": 1.0,
                                 "height": 240.0, "crown_radius": 50.0,
                                 "crown_plan": uniform}]}})
    check(any("one radius all round" in w for w in warns),
          "and a record that does this is told the plan is doing nothing",
          f"warnings were {warns}")


def test_the_limb_shades_where_the_bearing_says():
    """The whole point: 22 ft THERE, and 17 ft everywhere else.

    Two probes the same distance from the trunk, on opposite bearings. Swap
    which way the arc points and the two answers swap with it. A wedge test
    that has lost the bearing — one that takes the largest radius on every
    bearing, which is the obvious way to get this wrong — blocks both probes
    under both arcs and passes nothing here.
    """
    east = sunmodel.Model(with_plan(LIMB_EAST), cell=CELL)
    west = sunmodel.Model(with_plan(LIMB_WEST), cell=CELL)
    plain = sunmodel.Model(SITE, cell=CELL)

    for m, name, lit, dark in ((east, "+x", (45.0, 145.0), (255.0, 155.0)),
                               (west, "-x", (255.0, 155.0), (45.0, 145.0))):
        on, _ = straight_up(m, *dark)
        off, _ = straight_up(m, *lit)
        check(abs(on - 0.25) < 1e-12,
              f"the limb pointing {name} shades ground 8.8 ft out on its own "
              f"bearing", f"got {on}, expected the crown's tau of 0.25")
        check(abs(off - 1.0) < 1e-12,
              f"and leaves the same distance on the opposite bearing open",
              f"got {off}. A crown 8.8 ft out on every bearing is the 22 ft "
              f"circle this representation exists to avoid")

    for x, y in ((45.0, 145.0), (255.0, 155.0)):
        got, _ = straight_up(plain, x, y)
        check(abs(got - 1.0) < 1e-12,
              f"and with no plan at all, ({x:.0f}, {y:.0f}) is open sky",
              f"got {got}. Both probes are 8.8 ft from a trunk carrying a "
              f"4.2 ft bulk radius, so the arc is the only thing that can "
              f"reach them")

    past, _ = straight_up(east, 305.0, 155.0)
    check(abs(past - 1.0) < 1e-12,
          "the arc stops at its own radius, on its own bearing",
          f"got {past}. (305, 155) is 12.9 ft out where the limb reaches "
          f"12.5 ft, so a wedge that runs to infinity along the bearing "
          f"shows up here and nowhere else")


def test_the_bearing_is_true_not_yard_frame():
    """A compass reading is a compass reading. The frame converts it.

    The trap is quiet: read `true_bearing` as a yard angle and t11's limb points
    117.8 degrees away from where it grows, still 22 ft long, still shading
    something. Nothing about the output looks wrong.
    """
    turned = with_plan(LIMB_EAST)
    turned["frame"] = {"true_bearing_of_plus_x": 207.8}
    m = sunmodel.Model(turned, cell=CELL)

    got, _ = straight_up(m, 155.0, 45.0)
    check(abs(got - 0.25) < 1e-12,
          "turn the frame 90 deg and the limb stays put on the ground",
          f"got {got}. True bearing 117.8 is yard -y once +x bears 207.8, so "
          f"the shade has to move to (155, 45)")
    got, _ = straight_up(m, 255.0, 155.0)
    check(abs(got - 1.0) < 1e-12,
          "and is no longer where the yard frame alone would have put it",
          f"got {got}. 0.25 here means true_bearing was used as a yard angle")


def test_a_limb_composes_with_canopy_groups():
    """An asymmetric crown is still one crown, and still one member of a group.

    (245, 305) is covered by fused-a's bulk and by fused-b ONLY through an arc
    reaching past its own drip line. Three implementations, three numbers:

        0.5    the arc was never read, so only fused-a is in the way
        0.05   the arc was read but the group was bypassed — 0.5 x 0.1
        0.1    both right: min(0.5, 0.1), charged once      <- correct

    The middle one is the failure worth naming. A crown that answered for its
    wedges separately would hold several entries in `Model.crowns`, and a group
    binds tree ids, so the wedges would multiply against each other and against
    their own group-mate.
    """
    arc = {"arcs": [{"id": "reach", "true_bearing": 294.79, "width_deg": 20.0,
                     "radius": 100.0}]}
    ungrouped = sunmodel.Model(with_plan(arc, tree="fused-b"), cell=CELL)
    grouped = sunmodel.Model(
        with_plan(arc, tree="fused-b", features={"canopy_groups": GROUP}),
        cell=CELL)
    none = sunmodel.Model(SITE, cell=CELL)

    got, _ = straight_up(none, 245.0, 305.0)
    check(abs(got - 0.5) < 1e-12,
          "without the arc, only fused-a's bulk reaches (245, 305)",
          f"got {got}. 95.1 in from fused-b, which has a 60 in radius")
    got, _ = straight_up(ungrouped, 245.0, 305.0)
    check(abs(got - 0.05) < 1e-12,
          "the arc pulls fused-b over it, and undeclared the two multiply",
          f"got {got}, expected 0.5 x 0.1")
    got, hit = straight_up(grouped, 245.0, 305.0)
    check(abs(got - 0.1) < 1e-12,
          "declared one canopy, the limb and the bulk are charged once",
          f"got {got}, expected min(0.5, 0.1). 0.05 means an asymmetric crown "
          f"escaped its group; 0.5 means the arc stopped being read the moment "
          f"the group was declared")
    check(hit, "and the cell is still reported as canopy-hit")

    check(len(grouped.crowns) == len(none.crowns),
          "a profiled crown is still exactly one crown in the model",
          f"{len(grouped.crowns)} against {len(none.crowns)}. Anything else "
          f"and canopy_groups, leaf state and the crown captions all start "
          f"counting the same tree more than once")


def test_a_scalar_override_drops_the_plan():
    """`set_crowns(radius=...)` asks what the yard looks like with equal crowns.

    Both callers are sensitivity probes: the crown-shape grid, which sets every
    crown to one spread, and the open-sky baseline, which shrinks them to
    nothing. A 12.5 ft limb surviving a caller that has just set every radius to
    a hundredth of an inch answers neither question, and would put a phantom
    crown in the denominator every percentage in that figure is divided by.
    """
    m = sunmodel.Model(with_plan(LIMB_EAST), cell=CELL)
    got, _ = straight_up(m, 255.0, 155.0)
    check(abs(got - 0.25) < 1e-12, "the limb shades before the override",
          f"got {got}")

    m.set_crowns(base=120.0, radius=30.0, centre_x=300.0)
    check(all(c.wedges is None for c in m.crowns),
          "an explicit radius override leaves no wedges behind",
          f"{sum(c.wedges is not None for c in m.crowns)} crowns kept theirs")
    got, _ = straight_up(m, 255.0, 155.0)
    check(abs(got - 1.0) < 1e-12,
          "so the probe reads what a 30 in circle at x=300 would give",
          f"got {got}. 0.25 means the limb outlived the override")


def test_the_bounding_radii_never_lose_the_limb():
    """A caller that ignores the wedges must over-state, never under-state.

    `Model.crowns` unpacks as `(centre, radii, tree)` for the drawings, the
    captions and the distance checks in `verify_crowns`. None of those know
    about wedges. Handing them the bulk radius would silently drop the limb from
    every one of them; handing them the reach means they draw a crown too big,
    which is visible.
    """
    m = sunmodel.Model(with_plan(LIMB_EAST), cell=CELL)
    crown = [c for c in m.crowns if c.tree["id"] == "apart"][0]
    centre, radii, tree = crown
    check(float(radii[0]) == 150.0 and float(radii[1]) == 150.0,
          "the horizontal radii are the crown's furthest reach",
          f"got {radii[:2]}, expected the limb's 150 in and not the 50 in bulk")
    check(crown[2] is tree and len(crown) == 3,
          "and a crown still unpacks and indexes as (centre, radii, tree)",
          "fig_crown_sensitivity reads m.crowns[0][2]")
    check(siteschema.crown_reach(tree) == 150.0,
          "siteschema.crown_reach says the same without building a model",
          f"got {siteschema.crown_reach(tree)}")
    check(siteschema.crown_reach(TREES[4]) == 50.0,
          "and is just the radius for a circular crown",
          f"got {siteschema.crown_reach(TREES[4])}")


def test_a_plan_that_does_not_describe_a_shape_is_refused():
    """Two radii claiming one bearing is a record error, not a rounding one."""
    base = {"id": "x", "crown_radius": 50.0}

    def wedges(arcs, **kw):
        return siteschema.crown_wedges(
            dict(base, crown_plan={"arcs": arcs}, **kw), 117.8)

    for arcs, want, why in [
            ([{"true_bearing": 117.8, "width_deg": 40.0, "radius": 150.0},
              {"true_bearing": 137.8, "width_deg": 40.0, "radius": 90.0}],
             "overlap", "two arcs claiming the same bearing"),
            ([{"true_bearing": 117.8, "width_deg": 0.0, "radius": 150.0}],
             "width_deg", "an arc spanning nothing"),
            ([{"true_bearing": 117.8, "width_deg": 360.0, "radius": 150.0}],
             "width_deg", "an arc spanning the whole circle"),
            ([{"width_deg": 20.0, "radius": 150.0}],
             "true_bearing", "an arc pointing nowhere")]:
        try:
            wedges(arcs)
            check(False, f"refused: {why}", "it was accepted")
        except ValueError as e:
            check(want in str(e), f"refused: {why}, and says which",
                  f"raised, but with {str(e)!r}")

    try:
        siteschema.crown_wedges(
            {"id": "x", "crown_plan": LIMB_EAST}, 117.8)
        check(False, "refused: a plan on a crown with no radius",
              "the arcs say where the crown LEAVES the bulk, so there has to "
              "be a bulk")
    except ValueError as e:
        check("crown_radius" in str(e),
              "refused: a plan on a crown with no radius, and says which",
              f"raised, but with {str(e)!r}")

    check(siteschema.crown_wedges(TREES[4], 117.8) is None,
          "and a tree with no plan at all returns None rather than one wedge",
          "None is what selects the untouched circular path")

    touching = [{"true_bearing": 117.8, "width_deg": 40.0, "radius": 150.0},
                {"true_bearing": 157.8, "width_deg": 40.0, "radius": 90.0}]
    check(len(wedges(touching)) >= 3,
          "two arcs that share an edge and do not overlap are allowed",
          "the overlap test must not fire on arcs that merely touch")


def test_wedges_agree_with_a_marched_ray():
    """The algebra, against a method that shares none of it.

    `Crown.hits` clips an ellipsoid interval with two half-planes and never
    computes an angle. `verify_crowns.inside` takes an `atan2` bearing at every
    sample along the ray. Both answer 'does this ray reach the crown', and a
    sign slip in either would be invisible from inside that one.

    The sweep is deliberately dense around the arc's edges, where the two
    methods have every chance to disagree and where a wrong half-plane normal —
    the easiest mistake here — flips the answer for half the circle.
    """
    vc = load_verify_crowns()
    m = sunmodel.Model(with_plan(LIMB_EAST), cell=CELL)
    crown = [c for c in m.crowns if c.tree["id"] == "apart"][0]
    centre, radii, tree = crown

    def marched(p, d):
        for t in np.arange(0.25, 600.0, 0.25):
            if vc.inside(p + d * t, centre, radii, tree, 117.8):
                return True
        return False

    origins = [(x, y) for x in (40.0, 100.0, 160.0, 220.0, 280.0)
               for y in (40.0, 100.0, 160.0, 220.0, 280.0)]
    tested = blocked = bad = 0
    worst = None
    for ox, oy in origins:
        p = np.array([ox, oy, sunmodel.EYE])
        for alt in (25.0, 45.0, 65.0, 82.0):
            for az in range(60, 300, 15):
                d = sunmodel.sun_vector(alt, float(az), 117.8)
                a = bool(crown.hits(p, d))
                b = marched(p, d)
                tested += 1
                blocked += int(b)
                if a != b:
                    bad += 1
                    worst = worst or (ox, oy, alt, az, a, b)
    check(bad == 0,
          f"{tested} rays through a wedged crown agree with a marched ray",
          f"{bad} disagreements, first at {worst}")
    check(blocked > 40,
          f"and {blocked} of them actually reached the crown",
          "a sweep that never hits the geometry it is auditing agrees "
          "perfectly and means nothing — which is exactly how the stale "
          "indoor probes survived in verify_crowns")


def test_the_verifier_probes_the_limb():
    """The audit tool fires rays at an arc, derived from the record."""
    vc = load_verify_crowns()
    site = with_plan(LIMB_EAST)
    del site["zones"]["bed_indoors"]
    labels = [lab for lab, _ in vc.probe_cells(site)]
    check(sum("crown_plan" in lab for lab in labels) == 2,
          "a declared arc contributes a probe along it and one opposite it",
          f"got {labels}")

    xy = dict((lab, xy) for lab, xy in vc.probe_cells(site))
    along = [v for k, v in xy.items() if "along" in k][0]
    check(abs(along[0] - 250.0) < 1e-6 and abs(along[1] - 150.0) < 1e-6,
          "the along probe sits between the bulk drip line and the arc's reach",
          f"got {along}, expected 100 in out on yard +x from (150, 150)")

    check(not any("crown_plan" in lab for lab, _ in vc.probe_cells(
              {k: v for k, v in site.items() if k != "features"} |
              {"features": {"trees": TREES}})),
          "and a yard with no plan anywhere gains no probes from this",
          "the probe list must stay the zone centres for every other yard")


def test_the_maps_draw_the_limb_they_model():
    """A map that draws the circle disagrees with the model, quietly.

    Both maps flip y so north is up, which means a yard angle runs clockwise on
    the page. Forget that and every limb is drawn mirrored about the east-west
    line: still 22 ft, still plausible, pointing at the wrong bed.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tree = {"crown_center_x": 150.0, "crown_center_y": 150.0,
            "crown_radius": 50.0}
    for bearing, want, where in ((117.8, 0.0, "yard +x, across the page"),
                                 (297.8, 180.0, "yard -x"),
                                 (207.8, -90.0, "yard +y, DOWN the page")):
        fig, ax = plt.subplots()
        drawsite.draw_crown_arcs(
            ax, dict(tree, crown_plan={"arcs": [
                {"true_bearing": bearing, "width_deg": 20.0, "radius": 150.0}]}),
            117.8, "#000000", "#000000")
        w = [p for p in ax.patches][-1]
        mid = (w.theta1 + w.theta2) / 2.0
        plt.close(fig)
        check(abs(((mid - want + 180.0) % 360.0) - 180.0) < 1e-6,
              f"an arc on true bearing {bearing} is drawn toward {where}",
              f"drawn at page angle {mid:.1f}, expected {want:.1f}. A sign "
              f"slip on the y-flip mirrors every limb about the east-west line")
        check(abs(w.r - 150.0) < 1e-9 and abs(w.width - 100.0) < 1e-9,
              "and drawn as the ground between the drip line and the reach",
              f"got r {w.r} width {w.width}, expected the annulus 50 to 150")

    fig, ax = plt.subplots()
    drawsite.draw_crown_arcs(ax, tree, 117.8, "#000000", "#000000")
    check(len(ax.patches) == 0, "a crown with no plan draws no extra patch",
          f"{len(ax.patches)} patches for a plain circular crown")
    plt.close(fig)


def test_a_bed_a_limb_reaches_counts_as_reached():
    """The tree map ranks by what a tree stands over. A limb stands over it."""
    zone = {"x": [250.0, 300.0], "y": [140.0, 160.0]}       # 100 in from (150,150)
    plain = {"crown_center_x": 150.0, "crown_center_y": 150.0,
             "crown_radius": 50.0}
    check(not drawsite._reaches(plain, zone),
          "a 50 in bulk does not reach a bed 100 in away")
    check(drawsite._reaches(dict(plain, crown_plan=LIMB_EAST), zone),
          "and a 150 in limb does",
          "measuring to crown_radius drops the limb from the ranking, so the "
          "one tree worth going out to look at is the one not listed")


def test_a_reading_history_cannot_drift_from_its_value():
    """`readings` is only worth having if it is checked against the number.

    Four crown radii on cloverleaf-austin had been paced twice and reproduced,
    and `site.json` recorded all four as a single reading on one date. The fact
    of confirmation - the strongest evidence on that lot - lived in the doubt
    board and the change log where no model and no fingerprint could reach it.

    The failure mode of fixing that is a reading history that becomes decoration:
    somebody corrects the crown radius, the `readings` list still says two people
    measured the old figure, and the record now corroborates a number nobody
    took. So the check is the load-bearing half of the feature, not the store.
    """
    site = site_with()
    path = "features.trees.0.crown_radius"
    r = site["features"]["trees"][0]["crown_radius"]
    siteschema.set_provenance(
        site, path, "measured", date="2026-09-04",
        readings=[{"date": "2026-09-04", "value": r, "how": "re-walked"},
                  {"date": "2026-08-30", "value": r, "how": "paced"}])

    entry = siteschema.provenance_of(site, path)
    check([x["date"] for x in entry["readings"]] == ["2026-08-30", "2026-09-04"],
          "readings are stored oldest first however they were passed in",
          entry["readings"])

    c = siteschema.confirmations(entry)
    check(c["readings"] == 2 and c["reproduced"] is True
          and c["last"] == "2026-09-04",
          "two agreeing readings report as reproduced, dated by the later one", c)
    check(dict(siteschema.confirmed_paths(site)).get(path),
          "and the path is listed as read more than once")
    check(not [e for e in siteschema.validate(site)[0] if path in e],
          "a history that agrees with its value raises nothing",
          siteschema.validate(site)[0])

    moved = site_with()
    moved["features"]["trees"][0]["crown_radius"] = r + 24.0
    moved["provenance"] = dict(site["provenance"])
    errs = siteschema.validate(moved)[0]
    check(any(path in e and "nobody took" in e for e in errs),
          "correcting the value behind a reading history is an ERROR, not a warning",
          errs)

    # The distinction that carries the weight. Two readings that disagree are a
    # correction, which is more interesting than a confirmation and must never be
    # reported as one - t11's crown was 9 ft out on its second reading.
    disagree = site_with()
    siteschema.set_provenance(
        disagree, path, "measured", date="2026-09-04",
        readings=[{"date": "2026-08-30", "value": r + 108.0, "how": "eyeballed"},
                  {"date": "2026-09-04", "value": r, "how": "taped"}])
    c = siteschema.confirmations(siteschema.provenance_of(disagree, path))
    check(c["readings"] == 2 and c["reproduced"] is False,
          "two readings that disagree are two readings and NOT a confirmation", c)
    check(not [e for e in siteschema.validate(disagree)[0] if path in e],
          "and the value still matches the latest of them, so nothing is wrong",
          siteschema.validate(disagree)[0])

    stale = site_with()
    siteschema.set_provenance(
        stale, path, "measured", date="2026-08-30",
        readings=[{"date": "2026-08-30", "value": r},
                  {"date": "2026-09-04", "value": r}])
    check(any(path in w and "last time somebody looked" in w
              for w in siteschema.validate(stale)[1]),
          "an entry dated before its own newest reading is flagged",
          siteschema.validate(stale)[1])

    try:
        siteschema.set_provenance(site, path, "measured",
                                  readings=[{"value": r, "how": "paced"}])
        check(False, "a reading with no date is refused")
    except ValueError as exc:
        check("needs at least a date" in str(exc),
              "a reading with no date is refused", str(exc))
    try:
        siteschema.set_provenance(site, path, "measured",
                                  readings=[{"date": "2026-09-04", "vaule": r}])
        check(False, "and so is a misspelt field, rather than silently dropped")
    except ValueError as exc:
        check("unknown reading field" in str(exc),
              "and so is a misspelt field, rather than silently dropped", str(exc))


def test_the_real_yards_confirmations_are_recorded():
    """cloverleaf-austin's four re-walked crowns, on the real record."""
    site = yards.load_site("cloverleaf-austin")
    if not site:
        return
    twice = dict(siteschema.confirmed_paths(site))
    want = {f"features.trees.{i}.crown_radius": tid
            for i, tid in ((1, "t02"), (2, "t03"), (3, "t04"), (11, "t12"))}
    missing = [tid for p, tid in want.items() if p not in twice]
    check(not missing,
          "the four crowns that were re-walked say so in site.json",
          f"{missing} still read as a single reading, so nothing but prose "
          f"knows they were confirmed")
    check(all(twice[p]["reproduced"] for p in want if p in twice),
          "and all four are recorded as having reproduced")
    fused = [p for p, tid in want.items()
             if tid in ("t02", "t03") and p in twice]
    check(all(twice[p]["caveats"] for p in fused),
          "with the fused-canopy caveat on the pecan pair and not overstated",
          "t02/t03 reproduced as a COMBINED spread; their individual 17.5 ft "
          "radii were fitted to it, so an uncaveated confirmation claims more "
          "than the walk supports")
    check(not any(twice[p]["caveats"] for p in want
                  if p in twice and p not in fused),
          "and no caveat on the two that were read as single crowns")
    # The one that failed belongs here as much as the four that passed. Four out
    # of four reproducing is only worth reading beside a re-read that did not,
    # and t11 moved by 9 ft. Left out, the register says the walk confirms
    # everything it looks at.
    t11 = twice.get("features.trees.10.crown_radius")
    check(t11 is not None and t11["reproduced"] is False,
          "and the one crown the tape caught out is recorded as a correction",
          "t11 went from 312 in to 204 in on the re-walk and the record says so "
          "only in prose, so `confirmed_paths` reports 4 of 4 reproducing and "
          "nothing can see the one that did not")


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
        print("\na crown that is not a circle")
        test_untouched_trees_are_bit_identical()
        test_a_uniform_plan_is_the_circle_it_generalises()
        test_the_limb_shades_where_the_bearing_says()
        test_the_bearing_is_true_not_yard_frame()
        test_a_limb_composes_with_canopy_groups()
        test_a_scalar_override_drops_the_plan()
        test_the_bounding_radii_never_lose_the_limb()
        test_a_plan_that_does_not_describe_a_shape_is_refused()
        test_wedges_agree_with_a_marched_ray()
        test_the_verifier_probes_the_limb()
        test_the_maps_draw_the_limb_they_model()
        test_a_bed_a_limb_reaches_counts_as_reached()
        print("\nread once, or read twice")
        test_a_reading_history_cannot_drift_from_its_value()
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)

    # Outside the temporary root, because this one reads the real record.
    test_the_real_yards_confirmations_are_recorded()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed:")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("all passed.")


if __name__ == "__main__":
    main()
