#!/usr/bin/env python3
"""Prove the checks that cannot run say so, instead of passing.

    python3 tools/test_silence.py
    python3 tools/test_silence.py -v        show every objection raised

Three of the checks in `lib/design.py` read a flat scalar off `conditions.json`
or `site.json`, and each of them used to answer a missing input by moving on to
the next plant. That is the failure this file exists for, and it is worse than a
wrong answer, because an empty objection list means both "the site supports
this" and "I could not look" and reads as the first one.

It was not hypothetical. On the yard this was written against, all three were
inert simultaneously — no zone carried an `area_sqft`, `soil` carried no `ph`,
`water` carried no `hose_reaches` — so the space, soil and water checks had
never run once, while the bed maps carried sums somebody had done by hand in
prose. Fifty-one plants, three checks, no objections, and nothing anywhere
saying why.

So there are two halves to this, and the second is the one that would rot:

  it reports          a missing input produces a `note` naming the field, once
                      per input rather than once per plant.
  it still checks     with the inputs present, the objections disappear AND the
                      real check fires. A "could not check" that never clears is
                      the same silence with more words, and a test that only
                      asserted the notes appear would pass just as happily
                      against a check_coverage that always fires.

And the three modelling rules the space check now carries, each of which was a
wrong answer on a real bed rather than a hypothetical:

  a vine takes no ground       a climbing rose on a trellis counted as 7 sq ft
                               of soil, reading a bed at 1.49x overplanted whose
                               own notes said the ground beneath it still plants.
  pots are counted as pots     the same bed measured as area, with its vines
                               excluded, covers 0 percent and trips the *sparse*
                               branch, which is the opposite of true.
  unplantable comes off once   `area_sqft` used to skip the deduction that a
                               `box` got, so a bed stating its area outright kept
                               its river rock band in the plantable figure.

Runs entirely on dicts in memory. No yard is read or written.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import design  # noqa: E402  (after sys.path)

results = []
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    print(f"  {'ok  ' if state == 'pass' else 'FAIL'}  {label}")
    if detail and (state != "pass" or verbose):
        for line in str(detail).strip().splitlines():
            print(f"          {line}")


def check(label, cond, detail=""):
    record("pass" if cond else "FAIL", label, detail)


def says(objs, *words):
    """An objection mentioning all of these. Matching on the wording is the
    point: a note that does not name the field it could not read is not
    actionable, and "could not check" on its own is another kind of silence."""
    for o in objs:
        text = (o.get("about", "") + " " + o.get("say", "") + " "
                + o.get("fix", "")).lower()
        if all(w.lower() in text for w in words):
            return o
    return None


def show(objs):
    return "\n".join(f"[{o['level']}] {o['about']}: {o['say']}" for o in objs) \
        or "(no objections)"


# --------------------------------------------------------------- the fixtures

# One plant carrying every field the checks read, so a missing input is the only
# reason any of them could fail to run. `ph_range` makes the pH branch
# applicable, `soil_drainage` the drainage branch, `water: high` the hose
# branch. Without those the checks are inapplicable rather than blind, which is
# a different thing and must not report.
#
# `bloom` is here for the same reason and is the newest of them: a plant naming
# neither `months` nor `bloom` is judged over `DEFAULT_LIGHT_MONTHS`, and
# check_coverage now says so. That note is about a missing field on the PLANT,
# where every other note in this file is about a missing field on the SITE or
# the CONDITIONS, so leaving it to fire here would put a sixth objection in
# every count below and test nothing this file is for. It is trapped properly in
# tools/test_cropseason.py, which owns the light window.
PLANT = {"name": "Rosmarinus officinalis", "zone": "West bed", "count": 6,
         "light": "full sun", "water": "high", "ph_range": [6.0, 7.5],
         "soil_drainage": "sharp", "mature_spread_ft": 2.5,
         "mature_height_ft": 2.0, "bloom": ["Apr", "May"],
         "source": "test fixture"}


def blind_site():
    return {"zones": {"West bed": {"label": "West bed along the fence"}}}


def seeing_site():
    return {"zones": {"West bed": {"label": "West bed along the fence",
                                   "area_sqft": 40.0}}}


BLIND_COND = {"soil": {}, "water": {}}
SEEING_COND = {"soil": {"ph": 8.1, "drainage": "slow, poorly drained clay"},
               "water": {"hose_reaches": False, "rain_shadow_zones": []}}


def one_plant():
    return {"plants": [dict(PLANT)]}


# --------------------------------------------------------------------- the tests

def test_blind_reports():
    print("\na yard with none of the three inputs")
    objs = design.check_coverage(one_plant(), blind_site(), BLIND_COND, {})
    check("space reports the missing area", says(objs, "area_sqft", "West bed"),
          show(objs))
    check("soil reports the missing pH", says(objs, "soil", "ph"), show(objs))
    check("water reports the missing hose flag",
          says(objs, "hose_reaches"), show(objs))
    check("every one of them is a note, not a blocker",
          all(o["level"] == "note" for o in objs), show(objs))
    check("one per input, not one per plant", len(objs) <= 5,
          f"{len(objs)} objections for 1 plant\n" + show(objs))


def test_many_plants_one_objection():
    print("\nfifty plants blind, which is the case that actually happened")
    d = {"plants": [dict(PLANT, name=f"plant {i}") for i in range(50)]}
    objs = design.check_coverage(d, blind_site(), BLIND_COND, {})
    check("still one objection per input", len(objs) <= 5,
          f"{len(objs)} objections for 50 plants")
    check("and it counts the plants it could not check for",
          says(objs, "50"), show(objs))


def test_seeing_clears():
    print("\nthe same yard with the inputs present")
    objs = design.check_coverage(one_plant(), seeing_site(), SEEING_COND, {})
    check("nothing left to report", not objs, show(objs))

    # And the checks it was standing in for now actually fire. This is the half
    # that would rot: coverage notes that never clear prove nothing.
    real = (design.check_space(one_plant(), seeing_site(), {})
            + design.check_soil(dict(PLANT), SEEING_COND)
            + design.check_water(dict(PLANT), SEEING_COND, seeing_site()))
    check("the pH check fires", says(real, "8.1"), show(real))
    check("the drainage check fires", says(real, "sharp drainage"), show(real))
    check("the hose check fires", says(real, "no hose reaches"), show(real))


def test_inapplicable_is_not_blind():
    print("\na plant that states none of those needs")
    plain = {"plants": [{"name": "Muhlenbergia capillaris", "zone": "West bed",
                         "count": 3, "light": "full sun", "water": "low",
                         "mature_spread_ft": 3.0}]}
    objs = design.check_coverage(plain, seeing_site(), {"soil": {}, "water": {}},
                                 {})
    check("no pH note, because nothing asked about pH",
          not says(objs, "soil", "ph"), show(objs))
    check("no hose note, because nothing needs regular water",
          not says(objs, "hose_reaches"), show(objs))
    # rain shadow is the exception on purpose: an absent list is not the same
    # statement as an empty one, and no plant has to opt in for it to matter.
    check("rain shadow still reported", says(objs, "rain-shadow"), show(objs))


def test_zone_named_by_label():
    print("\na design naming the bed by its label rather than its key")
    d = {"plants": [dict(PLANT, zone="West bed along the fence")]}
    site = seeing_site()
    check("resolves to the site key",
          design.resolve_site_zone(site, "West bed along the fence")
          == "West bed")
    objs = design.check_coverage(d, site, SEEING_COND, {})
    check("so it does not report itself blind",
          not says(objs, "area_sqft"), show(objs))
    space = design.check_space(d, site, {})
    check("and the space check runs on it",
          says(space, "overplanted") or not space, show(space))


def test_vine_takes_no_ground():
    print("\na vine on a trellis")
    site = {"zones": {"g01": {"area_sqft": 9.9}}}
    rose = {"name": "Peggy Martin rose", "zone": "g01", "count": 1,
            "layer": "vine", "mature_spread_ft": 3.0}
    ground = {"name": "Salvia greggii", "zone": "g01", "count": 3,
              "layer": "front", "mature_spread_ft": 1.75}

    check("a vine's footprint is zero", design.footprint(rose) == 0.0)
    check("a shrub's is not", design.footprint(ground) > 0)

    with_vine = design.check_space({"plants": [rose, ground]}, site, {})
    check("the bed is not called overplanted for its trellis",
          not says(with_vine, "overplanted"), show(with_vine))

    # The reason this is a fix and not a fudge: counted as ground the same bed
    # reads 1.49x, which is a `serious` objection somebody would have acted on.
    as_ground = design.check_space(
        {"plants": [dict(rose, layer="back"), ground]}, site, {})
    check("whereas counting it as ground would have objected",
          says(as_ground, "overplanted"), show(as_ground))


def test_containers_counted_as_containers():
    print("\nthree barrels")
    site = {"zones": {"bed_barrels": {"area_sqft": 9.4, "containers":
                                      {"count": 3, "each_sqft": 3.1}}}}
    vines = [{"name": "Crossvine", "zone": "bed_barrels", "count": 1,
              "layer": "vine", "mature_spread_ft": 6.0},
             {"name": "Star jasmine", "zone": "bed_barrels", "count": 2,
              "layer": "vine", "mature_spread_ft": 4.0}]

    check("three containers found", design.zone_containers(site, "bed_barrels")
          == 3)
    objs = design.check_space({"plants": vines}, site, {})
    check("one plant per barrel raises nothing", not objs, show(objs))
    check("and it is emphatically not reported as sparse",
          not says(objs, "sparse"), show(objs))

    crowded = design.check_space(
        {"plants": [dict(vines[0], count=5)]}, site, {})
    check("five plants in three barrels does object",
          says(crowded, "5 plants", "3 containers"), show(crowded))

    empty = design.check_space(
        {"plants": [dict(vines[0], count=1)]}, site, {})
    check("one plant in three barrels says two stand empty",
          says(empty, "2 containers"), show(empty))


def test_unplantable_subtracted_once():
    print("\na bed with a river rock band inside it")
    site = {"zones": {"bed_g03": {"area_sqft": 41.5, "unplantable_sqft": 14.5}}}
    areas = design.zone_areas(site)
    got = round(areas.get("bed_g03", 0), 1)
    check("the rock comes off the stated area", got == 27.0,
          f"got {got}, wanted 27.0")

    # Both routes to an area have to net it, or which key the yard happened to
    # use decides whether its gravel counts as plantable.
    boxed = {"zones": {"b": {"box": [0, 0, 144, 144], "unplantable_sqft": 4.0}}}
    check("and off a box-derived one too",
          round(design.zone_areas(boxed).get("b", 0), 1) == 140.0)


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    print("the checks that could not run say so")
    for fn in (test_blind_reports, test_many_plants_one_objection,
               test_seeing_clears, test_inapplicable_is_not_blind,
               test_zone_named_by_label, test_vine_takes_no_ground,
               test_containers_counted_as_containers,
               test_unplantable_subtracted_once):
        fn()

    bad = [r for r in results if r[0] != "pass"]
    print(f"\n{len(results) - len(bad)} of {len(results)} passed")
    if bad:
        print("\nfailed:")
        for _, label, _ in bad:
            print(f"  {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
