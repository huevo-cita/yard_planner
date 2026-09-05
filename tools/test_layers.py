#!/usr/bin/env python3
"""Layered soil: which layer rules a plant, and which one rules the water.

    python3 tools/test_layers.py
    python3 tools/test_layers.py -v      print the objections in full

WHAT WENT WRONG

`conditions.soil.ph` was one number for a whole property — 8.2, the USDA map
value for the native ground — and `design.check_soil` read it for every plant.
Every bed on cloverleaf-austin carries about six inches of imported garden soil
over that ground, and the raised box is imported for its full fourteen. So
twenty-eight plantings were refused against soil none of them is growing in,
fourteen of them by 0.2 of a unit, which is inside the assumed band's own
spread. The number was not wrong. It was answering a question nobody asked.

The fix is not a different global number. It is that pH is a property of a
LAYER, and which layer governs depends on how deep the plant roots.

THE TRAP THIS FILE EXISTS TO CATCH

A depth-aware check is a machine for making objections disappear, and the ways
it goes wrong all look like success:

  * the native layer stops being consulted at all, and the twelve plantings
    that genuinely root through into clay go quiet with the shallow annuals
  * a plant with no researched depth gets a default — six inches, say — and is
    then judged on it. That is the original bug one field along: an assumed
    number applied to ground it does not describe
  * the unmeasured imported layer inherits 8.2 from the layer below, which is
    the original bug with an extra step
  * or it is treated as fine because nobody has said otherwise, which is the
    same bug in the friendly direction
  * DRAINAGE follows pH through the same accessor and becomes shallow-local.
    It is not. Water leaves through the slowest layer whatever the roots do,
    and it perches upward from that interface, so six inches of good soil over
    group D clay is inside the wet zone rather than above it. Making drainage
    depth-aware would have silenced four real objections and the four grit
    mounds already funded to answer them

Every one of those has a test below, and each one is a mutation in
`tools/mutate.py --suite layers`.

Runs entirely on dicts in memory. No yard is read or written.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import conditions, design  # noqa: E402  (after sys.path)

PASS = FAIL = 0
verbose = False


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok    {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")
        if detail:
            for line in str(detail).strip().splitlines():
                print(f"          {line}")


def head(t):
    print(f"\n{t}")


def show(objs):
    return "\n".join(f"[{o['level']}] {o['about']}: {o['say']}"
                     for o in objs) or "(no objections)"


# --------------------------------------------------------------- the fixtures

# cloverleaf-austin's own profile, cut down to the fields the checks read. The
# imported layer's `ph` is None and its `ph_plausible` is a band, and those two
# facts together are most of what this file is testing: a band is not a reading
# and must never be quoted as one.
IMPORTED = {"name": "imported", "top_in": 0.0, "bottom_in": 6.0,
            "material": "bagged garden soil and mulch",
            "ph": None, "ph_plausible": [6.0, 7.5],
            "drainage": None, "provenance": "reported"}
NATIVE = {"name": "native", "top_in": 6.0, "bottom_in": None,
          "material": "Central Texas alkaline clay",
          "ph": 8.2, "drainage": "slow", "provenance": "assumed"}

# The raised box: fourteen inches of imported soil on the same ground.
BOX = {"name": "imported", "top_in": 0.0, "bottom_in": 14.0,
       "ph": None, "ph_plausible": [6.0, 7.5], "drainage": None}
BOX_NATIVE = dict(NATIVE, top_in=14.0)


def cond(layers=(IMPORTED, NATIVE), bed="bed_g02", ph=8.2, drainage="slow"):
    """A yard whose flat reading and layered reading disagree on purpose.

    `soil.ph` stays 8.2 and `soil.drainage` stays "slow" in every fixture, so a
    check that has quietly gone back to reading the flat field cannot pass by
    coincidence — it has to be caught by the cases where the layered answer
    differs.
    """
    c = {"soil": {"ph": ph, "drainage": drainage}}
    if layers:
        c["soil"]["layers"] = {
            "profiles": {"p": {"layers": list(layers)}},
            "beds": {bed: "p"},
        }
    return c


def plant(name="Viola", zone="bed_g02", ph_range=(6.0, 7.5), depth=None, **kw):
    p = {"name": name, "zone": zone, "ph_range": list(ph_range)}
    if depth is not None:
        p["rooting_depth_in"] = depth
        p["rooting_depth_source"] = "a real source string would go here"
    p.update(kw)
    return p


def ph_objs(p, c=None):
    return [o for o in design.check_soil(p, c or cond()) if "pH" in o["say"]]


def drain_objs(p, c=None):
    return [o for o in design.check_soil(p, c or cond()) if "drain" in o["say"]]


# ------------------------------------------------- the shallow half of the fix

def test_a_shallow_plant_is_not_judged_on_the_subsoil():
    """A viola in six inches of garden soil is not standing in caliche."""
    got = ph_objs(plant(depth=6.0))
    ok("a 6 in root zone in a 0-6 in layer is not refused by the 8.2 below it",
       got == [], show(got))


def test_the_boundary_is_exclusive():
    """`bottom_in` is exclusive, so 6 in of root occupies 0-6 and stops.

    Off by one here is the difference between the whole shallow palette passing
    and the whole shallow palette being refused, and it is invisible in prose.
    """
    certain, possible = conditions.reached([IMPORTED, NATIVE], 6.0)
    ok("6 in of root reaches the 0-6 layer and not the one starting at 6",
       [l["name"] for l in certain] == ["imported"] and possible == [],
       f"certain={[l['name'] for l in certain]} possible={possible}")
    certain, _ = conditions.reached([IMPORTED, NATIVE], 6.5)
    ok("6.5 in of root reaches both",
       [l["name"] for l in certain] == ["imported", "native"],
       [l["name"] for l in certain])


def test_the_raised_box_holds_almost_everything_inside_it():
    got = ph_objs(plant("Lettuce", "bed_raised", depth=6.0),
                  cond((BOX, BOX_NATIVE), bed="bed_raised"))
    ok("a 6 in crop in a 14 in box never meets the native layer", got == [],
       show(got))


# --------------------------------------------- the half that must NOT go quiet

def test_a_deep_plant_is_still_refused_by_the_layer_it_reaches():
    """The point of the exercise. Twelve plantings depend on this staying loud."""
    got = ph_objs(plant("Turk's cap", ph_range=(6.0, 8.0), depth=24.0))
    ok("a 24 in root zone is still refused by the 8.2 six inches down",
       [o["level"] for o in got] == ["serious"], show(got))


def test_the_objection_says_which_layer_and_how_much_of_the_root_zone():
    """An objection that does not say where is not better than the old one."""
    got = ph_objs(plant("Turk's cap", ph_range=(6.0, 8.0), depth=24.0))
    say = got[0]["say"] if got else ""
    ok("it names the layer, the depth it starts at and the share of the roots",
       "native" in say and "6 in down" in say and "75 percent" in say, say)


def test_a_crop_that_breaches_the_box_still_objects():
    """18 in of broccoli in a 14 in box is four inches into the clay."""
    got = ph_objs(plant("Broccoli", "bed_raised", ph_range=(6.0, 7.5),
                        depth=18.0),
                  cond((BOX, BOX_NATIVE), bed="bed_raised"))
    ok("a root zone deeper than the box is judged on what is under the box",
       [o["level"] for o in got] == ["serious"], show(got))
    ok("and it states the share rather than deciding whether 22 percent matters",
       got and "22 percent" in got[0]["say"],
       got[0]["say"] if got else "(nothing)")


def test_a_bed_with_no_profile_falls_back_to_the_flat_reading():
    """Undisturbed ground still works, and this is every other yard in the repo."""
    got = ph_objs(plant("Turk's cap", ph_range=(6.0, 8.0), depth=24.0),
                  cond(layers=None))
    ok("a yard with no layers behaves exactly as it did before",
       [o["level"] for o in got] == ["serious"], show(got))


# ------------------------------------------- what an unmeasured layer may say

def test_the_imported_layer_does_not_inherit_the_native_reading():
    """The original bug with an extra step, and the one most likely to be
    reintroduced by somebody 'filling in the missing value'."""
    got = ph_objs(plant("Lettuce", ph_range=(6.0, 7.5), depth=6.0))
    ok("a layer with ph null is not given the layer below it", got == [],
       show(got))


def test_an_unmeasured_layer_is_not_treated_as_fine_either():
    """The same bug in the friendly direction. A plant whose range covers part
    of the plausible band is UNSETTLED, and the report has to say so."""
    p = plant("Blackfoot daisy", ph_range=(6.5, 8.5), depth=18.0)
    verdicts = [v for _, v, _ in design.ph_by_layer(p, [IMPORTED, NATIVE])]
    ok("part-covered by the plausible band reads as `depends`, not `ok`",
       verdicts == [design.PH_DEPENDS, design.PH_OK], verdicts)
    notes = [o for o in design.check_layer_coverage([p], None, cond())
             if "never been measured" in o["say"]]
    ok("and check_coverage says so, naming the plant",
       len(notes) == 1 and "Blackfoot daisy" in notes[0]["say"], show(notes))


def test_a_plausible_band_is_never_quoted_as_a_reading():
    """Wholly inside the band passes, wholly outside is refused, and the two
    are different answers from the same field."""
    inside = plant("Anything", ph_range=(5.0, 9.0), depth=6.0)
    outside = plant("Blueberry", ph_range=(4.5, 5.5), depth=6.0)
    ok("a range containing the whole band passes",
       ph_verdict_of(inside) == design.PH_OK, ph_verdict_of(inside))
    ok("a range excluding the whole band is refused",
       ph_verdict_of(outside) == design.PH_OUT, ph_verdict_of(outside))


def ph_verdict_of(p):
    return design.ph_by_layer(p, [IMPORTED])[0][1]


def test_a_layer_with_nothing_at_all_is_its_own_answer():
    bare = {"name": "imported", "top_in": 0.0, "bottom_in": 6.0}
    v = design.ph_verdict(bare, [6.0, 7.5])
    ok("no reading and no plausible band is `unknown`, not `ok`",
       v == design.PH_UNKNOWN, v)


def test_the_native_reading_is_not_softened_into_its_own_band():
    """8.2 is assumed and its note quotes 7.8-8.3, and turning the value into
    that interval would drop every remaining pH objection to a shrug. A
    plausible band is consulted only where there is no reading."""
    hedged = dict(NATIVE, ph_plausible=[7.8, 8.3])
    v = design.ph_verdict(hedged, [6.0, 8.0])
    ok("a layer that has a value is judged on the value, band or no band",
       v == design.PH_OUT, v)


# ------------------------------------------------- an unresearched depth

def test_no_depth_is_not_a_shallow_depth():
    """The whole point. Four plantings on cloverleaf-austin have no depth and
    the honest answer for them is a third one."""
    certain, possible = conditions.reached([IMPORTED, NATIVE], None)
    ok("with no depth the surface layer is certain and the rest is possible",
       [l["name"] for l in certain] == ["imported"]
       and [l["name"] for l in possible] == ["native"],
       f"{[l['name'] for l in certain]} / {[l['name'] for l in possible]}")


def test_no_depth_raises_no_objection_it_cannot_stand_behind():
    p = plant("Dill", ph_range=(6.0, 7.5))          # no depth
    got = ph_objs(p)
    ok("a plant with no researched depth is not refused by a layer it may "
       "not reach", got == [], show(got))


def test_but_it_is_reported_by_name():
    """Silence would be the bug. The gap has to be visible and nameable."""
    p = plant("Dill", ph_range=(6.0, 7.5))
    notes = [o for o in design.check_layer_coverage([p], None, cond())
             if "rooting_depth_in" in o["say"]]
    ok("and it is reported by name as a coverage gap",
       len(notes) == 1 and "Dill" in notes[0]["say"], show(notes))


def test_a_depth_that_changes_nothing_is_not_reported():
    """A gap report that lists every plant without a depth is one nobody reads.
    Only a plant a layer would REFUSE is worth a line."""
    p = plant("Gulf muhly", ph_range=(6.0, 8.5))    # no depth, and 8.2 suits it
    notes = [o for o in design.check_layer_coverage([p], None, cond())
             if "rooting_depth_in" in o["say"]]
    ok("a missing depth that could not change the answer is left alone",
       notes == [], show(notes))


def test_a_bad_depth_is_no_depth():
    for bad in (0, -3, "18 in", True, None):
        if design.rooting_depth({"rooting_depth_in": bad}) is not None:
            ok(f"rooting_depth rejects {bad!r}", False,
               design.rooting_depth({"rooting_depth_in": bad}))
            return
    ok("rooting_depth rejects zero, negatives, strings and booleans", True)


# ------------------------------------------------------------- drainage

def test_drainage_does_not_follow_ph_down_the_profile():
    """The mistake that would have looked like a clean generalisation.

    A shallow-rooted plant does not escape the clay by staying above it: water
    perches at the interface and stands upward from it. If this ever goes
    quiet, four funded grit mounds lose their reason.
    """
    got = drain_objs(plant("Damianita", soil_drainage="sharp", depth=4.0))
    ok("a 4 in root zone over slow clay at 6 in still gets the objection",
       [o["level"] for o in got] == ["blocking"], show(got))


def test_the_limiting_layer_is_the_shallowest_slow_one():
    lim = conditions.limiting_layer([IMPORTED, NATIVE])
    ok("the clay is the limiting layer even though it is the deeper one",
       lim is NATIVE, lim and lim.get("name"))
    ok("a profile with nothing slow in it has no limiting layer",
       conditions.limiting_layer([IMPORTED, dict(NATIVE, drainage="well")])
       is None)
    # Two slow layers, because with one the shallowest and the deepest are the
    # same layer and the rule under test is invisible. A perched table stands
    # on the FIRST thing water cannot get through; everything below is already
    # behind it.
    pan = {"name": "pan", "top_in": 6.0, "bottom_in": 9.0, "drainage": "poor"}
    deep = {"name": "marl", "top_in": 9.0, "bottom_in": None,
            "drainage": "slow"}
    lim = conditions.limiting_layer([IMPORTED, pan, deep])
    ok("with two slow layers it is the shallower that governs", lim is pan,
       lim and lim.get("name"))


def test_the_clay_under_a_raised_box_still_governs_the_box():
    got = drain_objs(plant("Rosemary", "bed_raised", soil_drainage="sharp",
                           depth=18.0),
                     cond((BOX, BOX_NATIVE), bed="bed_raised"))
    ok("14 in of imported soil does not make the box free-draining",
       [o["level"] for o in got] == ["blocking"], show(got))


def test_the_drainage_message_names_the_interface():
    got = drain_objs(plant("Damianita", soil_drainage="sharp", depth=18.0))
    say = got[0]["say"] if got else ""
    ok("it says where the water perches rather than asserting 'the soil is slow'",
       "6 in" in say and "perch" in say.lower(), say)


def test_an_unrecorded_layer_drainage_is_not_read_as_free():
    """The imported layer records drainage null on purpose, so that
    limiting_layer reaches past it to the clay instead of stopping at a
    convenient answer."""
    ok("a null drainage on the surface layer does not shadow the clay below",
       conditions.limiting_layer([IMPORTED, NATIVE]) is NATIVE)


def test_a_plant_that_wants_no_sharp_drainage_is_never_asked():
    got = drain_objs(plant("Turk's cap", soil_drainage="average", depth=24.0))
    ok("an average-drainage plant gets no drainage objection", got == [],
       show(got))


# --------------------------------------------------------------- housekeeping

def test_an_unprofiled_bed_is_reported_rather_than_assumed_described():
    p = plant("Turk's cap", zone="bed_nobody_described", ph_range=(6.0, 8.0),
              depth=24.0)
    notes = [o for o in design.check_layer_coverage([p], None, cond())
             if "soil.layers.beds" in o["say"]]
    ok("a bed with plants and no profile is named as a gap", len(notes) == 1,
       show(notes))


def test_a_profile_that_does_not_join_up_is_reported():
    """`bottom_in` is the redundant half of each boundary — everything is
    decided from `top_in` — so perturbing it moved no objection on the real
    yard. That is the "believed but never computed" quadrant, and the answer
    is to check the two halves against each other rather than delete one."""
    gappy = [dict(IMPORTED, bottom_in=3.0), NATIVE]
    said = conditions.layer_gaps(gappy)
    ok("three inches belonging to no layer is a finding",
       len(said) == 1 and "stops at 3 in" in said[0], said)
    ok("a profile that does join up says nothing",
       conditions.layer_gaps([IMPORTED, NATIVE]) == [],
       conditions.layer_gaps([IMPORTED, NATIVE]))
    ok("a deepest layer with a floor under it is a finding too",
       len(conditions.layer_gaps([IMPORTED, dict(NATIVE, bottom_in=40.0)])) == 1)

    notes = [o for o in design.check_layer_coverage(
        [plant(depth=6.0)], None,
        cond(layers=(dict(IMPORTED, bottom_in=3.0), NATIVE)))
        if "join up" in o["say"]]
    ok("and check_layer_coverage carries it, naming the bed", len(notes) == 1,
       show(notes))


def test_the_gap_report_is_wired_into_check_coverage():
    """Calling `check_layer_coverage` directly proves it works and proves
    nothing about whether anybody calls it. Everything the narrower pH check
    stops saying lands here or nowhere, and a check that answers fewer
    questions looks exactly like a yard with fewer problems."""
    p = plant("Blackfoot daisy", ph_range=(6.5, 8.5), depth=18.0)
    site = {"zones": {"bed_g02": {"area_sqft": 200.0}}}
    got = design.check_coverage({"plants": [p]}, site, cond(), {})
    notes = [o for o in got if "never been measured" in o["say"]]
    ok("check_coverage carries the layered soil gaps", len(notes) == 1,
       show(got))


def test_a_container_is_not_the_ground():
    """A pot holds whatever went into it, and the yard's profile does not rule
    there. Unchanged by any of this, and worth a line because the layer code
    runs before the container guard would have."""
    site = {"zones": {"pot_a": {"kind": "container"}}}
    got = design.check_soil(plant("Star jasmine", zone="pot_a", depth=12.0),
                            cond(), site)
    ok("a container gets no soil objection at all", got == [], show(got))


# ------------------------------------- the probe that could not have measured it

# This lives here rather than beside the gate tests because it is a finding of
# this change and not of that one. `--price` was the obvious way to ask what the
# unmeasured imported pH is worth, and it would have answered — with 0.00 h/day,
# because `--price` measures LIGHT. It writes the value into a copy of
# `site.json` and re-runs the shade model, `set_path` creates a key that was
# never there, the model runs identically for every value in the range, and the
# card settles itself `probed-immaterial` on a measurement that never looked at
# it. An unanswerable doubt closed by a number. So the imported pH got a card
# with no probe, and `price` got a guard.

def test_a_probe_on_a_path_the_model_cannot_see_is_refused():
    from lib import doubts
    site = {"obstructions": {"fences": [{"height": 72.0}]}}
    bad = {"path": "soil.layers.profiles.in_ground_amended.layers.0.ph",
           "values": [6.0, 6.75, 7.5]}
    why = doubts._unprobeable(site, bad)
    ok("a probe naming a path absent from site.json is reported, not measured",
       why and "not in site.json" in why, why)
    ok("and the reason says what would otherwise have happened",
       why and "spread of zero" in why, why)


def test_a_real_geometric_probe_is_left_alone():
    from lib import doubts
    site = {"obstructions": {"fences": [{"height": 72.0}]}}
    good = {"path": "obstructions.fences.0.height", "values": [36.0, 96.0]}
    ok("a path the shade model does read is priced as before",
       doubts._unprobeable(site, good) is None,
       doubts._unprobeable(site, good))


def test_a_tree_probe_is_not_a_path_and_is_not_touched():
    from lib import doubts
    ok("a tree-field probe carries no path and is left to the tree mutator",
       doubts._unprobeable({}, {"tree": "t11", "field": "height_ft",
                                "values": [30, 50]}) is None)


def test_price_leaves_such_a_card_open_and_says_why():
    """Through `price` rather than the guard, because the guard existing and
    the guard being called are different claims and only the second one keeps
    a card from settling itself."""
    from lib import doubts, yards
    card = {"id": "d99", "status": "open", "kind": "fact",
            "question": "what pH is the imported soil?",
            "probe": {"path": "soil.imported_ph", "values": [6.0, 7.5]}}
    board = {"cards": [card]}
    site = {"obstructions": {"fences": [{"height": 72.0}]}}
    saved = []
    load, save = yards.load, yards.save
    try:
        yards.load = lambda slug, name=None: site
        yards.save = lambda slug, name, data: saved.append(data)
        doubts.load = lambda slug: board
        results = doubts.price("scratch")
    finally:
        yards.load, yards.save = load, save
        del doubts.load

    ok("the card is left open", card["status"] == "open", card.get("status"))
    ok("no spread is written against it", "priced" not in card,
       card.get("priced"))
    ok("and price reports the path it could not measure",
       len(results) == 1 and "not in site.json" in (results[0][2] or ""),
       results)


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    head("a shallow plant is judged on the soil it is in")
    test_a_shallow_plant_is_not_judged_on_the_subsoil()
    test_the_boundary_is_exclusive()
    test_the_raised_box_holds_almost_everything_inside_it()

    head("and a deep one is still judged on the soil it reaches")
    test_a_deep_plant_is_still_refused_by_the_layer_it_reaches()
    test_the_objection_says_which_layer_and_how_much_of_the_root_zone()
    test_a_crop_that_breaches_the_box_still_objects()
    test_a_bed_with_no_profile_falls_back_to_the_flat_reading()

    head("what an unmeasured layer is allowed to say")
    test_the_imported_layer_does_not_inherit_the_native_reading()
    test_an_unmeasured_layer_is_not_treated_as_fine_either()
    test_a_plausible_band_is_never_quoted_as_a_reading()
    test_a_layer_with_nothing_at_all_is_its_own_answer()
    test_the_native_reading_is_not_softened_into_its_own_band()

    head("an unresearched rooting depth is a third answer")
    test_no_depth_is_not_a_shallow_depth()
    test_no_depth_raises_no_objection_it_cannot_stand_behind()
    test_but_it_is_reported_by_name()
    test_a_depth_that_changes_nothing_is_not_reported()
    test_a_bad_depth_is_no_depth()

    head("drainage is a property of the profile, not of the root zone")
    test_drainage_does_not_follow_ph_down_the_profile()
    test_the_limiting_layer_is_the_shallowest_slow_one()
    test_the_clay_under_a_raised_box_still_governs_the_box()
    test_the_drainage_message_names_the_interface()
    test_an_unrecorded_layer_drainage_is_not_read_as_free()
    test_a_plant_that_wants_no_sharp_drainage_is_never_asked()

    head("the gaps the record still has")
    test_an_unprofiled_bed_is_reported_rather_than_assumed_described()
    test_a_profile_that_does_not_join_up_is_reported()
    test_the_gap_report_is_wired_into_check_coverage()
    test_a_container_is_not_the_ground()

    head("--price does not answer a question it cannot measure")
    test_a_probe_on_a_path_the_model_cannot_see_is_refused()
    test_a_real_geometric_probe_is_left_alone()
    test_a_tree_probe_is_not_a_path_and_is_not_touched()
    test_price_leaves_such_a_card_open_and_says_why()

    print(f"\n{PASS} of {PASS + FAIL} passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
