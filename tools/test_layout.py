#!/usr/bin/env python3
"""The bed maps and the plant records are two representations, and they must agree.

    python3 tools/test_layout.py

`lib.drawbeds` draws every bed map from `design.json`'s `layout` block. That
block is a SECOND, hand-authored account of the same planting — its own
positions, its own counts, its own written labels — and nothing compared it
against `design.plants`. The raised bed had been showing the symptom for as long
as both existed: 32 cells against 45 plant entries, with the linter's only
comment being that a count is the wrong way to read a grid.

That comment is true. It is also not an answer, and the difference between the
two is what this suite is for. The 13 are three crops sown several to the
square, which is the method; saying so is a reconciliation, and shrugging is not.

This is the fifth instance of one failure found on this yard in a day. A driveway
recorded 14.5 ft from a bed the plan said it abutted, with nothing comparing the
coordinates. Seven `lib.schedule` archetypes unreachable because a guard read
`hardscape["kind"]` against a design writing `item`. An `overhang_ft` read by one
module and written by none. Ranks never summed against depth. Every one of them:
two representations of the same fact, and no third thing looking at both.

Three groups, and the third is the one that matters:

  the asymmetry     a grid square may hold several plants and a border circle
                    may not. Declared per zone kind, so the raised bed's 13 and
                    g02's missing bluebonnet cannot be swallowed by one margin
  the matcher       what a label may be abbreviated to and still be readable,
                    and — more important — what it may not, because a matcher
                    that resolves `V` to `Viola` reports a map as reconciled on
                    the strength of one letter
  the falsifier     the two can now disagree. Move a count on either side and
                    the check has to notice, from either direction
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import design  # noqa: E402

PASS = FAIL = 0


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok    {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f"\n          {detail}" if detail else ""))


def head(t):
    print(f"\n{t}")


def plant(name, zone="bed_g01", count=1, **kw):
    p = {"name": name, "zone": zone, "count": count, "layer": "front",
         "mature_spread_ft": 1.0, "mature_height_ft": 1.0}
    p.update(kw)
    return p


def border(name="g01-southeast-corner", labels=(), **kw):
    b = {"type": "border", "name": name, "length": 4.0, "depth": 2.4,
         "plants": [{"x": i, "y": 1.0, "r": 0.4, "label": lab}
                    for i, lab in enumerate(labels)]}
    b.update(kw)
    return b


def grid(name="raised-bed", cells=(), **kw):
    b = {"type": "grid", "name": name, "width": 4, "length": 8,
         "cells": [dict({"x": i, "y": 0, "w": 1, "h": 1, "label": lab}, **extra)
                   for i, (lab, extra) in enumerate(cells)]}
    b.update(kw)
    return b


def site(kind="border", key="bed_g01", short="g01", **kw):
    z = {"style": "bed", "kind": kind, "label": f"{short} bed",
         "label_short": short, "area_sqft": 9.9, "usable_depth_ft": 2.417}
    if kind == "grid":
        z["squares"] = 32
    if kind == "container":
        z["containers"] = {"count": 3}
    z.update(kw)
    return {"zones": {key: z}}


def says(objs, text):
    return [o for o in objs if text in o["say"]]


# ------------------------------------------------------------ the asymmetry

head("what one mark means is declared per zone kind, not averaged over the yard")
ok("a border circle is one plant", design.LAYOUT_UNIT["border"] == "plant")
ok("a grid cell is one square", design.LAYOUT_UNIT["grid"] == "square")
ok("and nothing draws a container, stated rather than left out",
   design.LAYOUT_UNIT["container"] is None)
ok("the three kinds the space check knows are the three declared here",
   set(design.LAYOUT_UNIT) == set(design.ZONE_KINDS),
   (sorted(design.LAYOUT_UNIT), sorted(design.ZONE_KINDS)))

head("a grid square may hold several of one crop; that is the method")
D = {"plants": [plant("Softneck garlic (cloves)", "bed_raised", 10),
                plant("Radish", "bed_raised", 2)],
     "layout": {"beds": [grid(cells=[("Garlic", {}), ("Garlic", {}),
                                     ("Radish", {}), ("Radish", {})])]}}
S = site("grid", "bed_raised", "raised")
objs = design.check_layout(D, S)
ok("10 cloves in 2 squares raises no serious objection",
   not [o for o in objs if o["level"] == "serious"], objs)
ok("but it is reported, with the crop named and the difference counted",
   says(objs, "8-plant difference") and says(objs, "Softneck garlic"),
   [o["say"] for o in objs])
ok("and it says the shrug it replaces is not the answer",
   says(objs, "the grid check can only shrug at"))

head("a square with no plant to fill it is the failure, and it is serious")
OVER = {"plants": [plant("Radish", "bed_raised", 1)],
        "layout": {"beds": [grid(cells=[("Radish", {}), ("Radish", {})])]}}
objs = design.check_layout(OVER, S)
ok("2 squares of radish against 1 radish is serious",
   any(o["level"] == "serious" and "more squares" in o["say"] for o in objs),
   [(o["level"], o["say"]) for o in objs])
ok("and it says a square cannot hold a fraction of a plant",
   says(objs, "cannot hold a fraction"))

head("a wide cell is the squares it covers, not one square")
WIDE = {"plants": [plant("Radish", "bed_raised", 2)],
        "layout": {"beds": [grid(cells=[("Radish", {"w": 2, "h": 1})])]}}
rec = design.reconcile_layout(WIDE, S)[0]
ok("a 2x1 cell counts as two squares", rec["marks"] == 2, rec["marks"])
ok("so it balances against two plants rather than reading as one",
   not says(design.check_layout(WIDE, S), "difference"))

head("a border circle is one plant, and it is wrong in either direction")
TOO_FEW = {"plants": [plant("Damianita", "bed_g01", 4)],
           "layout": {"beds": [border(labels=["Damianita"] * 3)]}}
objs = design.check_layout(TOO_FEW, site())
ok("3 circles against 4 plants is serious, and it names the plant",
   any(o["level"] == "serious" and "draws 3 plants" in o["say"]
       and "Damianita: 3 on the map, 4 on the list" in o["say"] for o in objs),
   [(o["level"], o["say"]) for o in objs])
TOO_MANY = {"plants": [plant("Damianita", "bed_g01", 3)],
            "layout": {"beds": [border(labels=["Damianita"] * 4)]}}
ok("and so is 4 against 3, which a grid rule would have allowed",
   any(o["level"] == "serious" and "draws 4 plants" in o["say"]
       for o in design.check_layout(TOO_MANY, site())))
ok("the objection says the map is what somebody plants from",
   says(design.check_layout(TOO_MANY, site()), "somebody plants from"))

head("totals that agree while the plants do not is its own finding")
# The case a total-only comparison is blind to, and the one g02 is one mark
# away from: two errors of opposite sign in the same bed.
SWAP = {"plants": [plant("Damianita", "bed_g01", 3),
                   plant("Blackfoot daisy", "bed_g01", 3)],
        "layout": {"beds": [border(labels=["Damianita"] * 4
                                          + ["Blackfoot daisy"] * 2)]}}
objs = design.check_layout(SWAP, site())
ok("six marks against six plants still objects",
   any(o["level"] == "serious" and "totals agree" in o["say"] for o in objs),
   [(o["level"], o["say"]) for o in objs])
ok("and it names the plant and both figures",
   says(objs, "Damianita: 4 on the map, 3 on the list"), [o["say"] for o in objs])

head("a container bed is exempt by declaration, not by omission")
POTS = {"plants": [plant("Crossvine", "bed_barrels", 1)], "layout": {"beds": []}}
ok("three barrels and no bed map raises nothing",
   not design.check_layout(POTS, site("container", "bed_barrels", "barrels")),
   design.check_layout(POTS, site("container", "bed_barrels", "barrels")))

head("a border with plants and no map at all is serious")
NOMAP = {"plants": [plant("Damianita", "bed_g01", 3)], "layout": {"beds": []}}
objs = design.check_layout(NOMAP, site())
ok("nothing to plant from is reported",
   any(o["level"] == "serious" and "no bed map draws" in o["say"]
       for o in objs), [(o["level"], o["say"]) for o in objs])

# -------------------------------------------------------------- the matcher

head("a label is matched to a record, or reported — never guessed")
RECS = [plant("Cedar sedge", botanical="Carex planostachys"),
        plant("Sweet alyssum"), plant("Viola"),
        plant("Milkweed - ASK FOR Asclepias tuberosa OR A. asperula BY NAME"),
        plant("Mexican bush sage"), plant("Mealy blue sage"),
        plant("Plateau goldeneye"), plant("Gregg's mistflower")]


def how(label):
    return design.resolve_mark(label, RECS)[1]


def hit(label):
    p, _ = design.resolve_mark(label, RECS)
    return p and p["name"]


ok("the name itself matches as the name", how("Cedar sedge") == "name")
ok("the whole binomial matches as the binomial",
   how("Carex planostachys") == "botanical")
ok("a truncation matches as an abbreviation",
   how("Gregg's\nmistfl.") == "abbreviation"
   and hit("Gregg's\nmistfl.") == "Gregg's mistflower")
ok("a hyphen at a line break is a hyphenation, not two words",
   hit("Golden-\neye") == "Plateau goldeneye", design._label_tokens("Golden-\neye"))
ok("Milk-\\nweed reads as one word too", hit("Milk-\nweed").startswith("Milkweed"))
ok("a shortened first word still resolves",
   hit("Mex.\nbush\nsage") == "Mexican bush sage")
ok("and a dropped middle word does",
   hit("Mealy\nsage") == "Mealy blue sage")
ok("a plural is not a different plant", hit("Violas") == "Viola")

head("what the matcher REFUSES to do, which is the part that keeps it honest")
ok("one letter resolves nothing, even where exactly one name starts with it",
   hit("V") is None and hit("A") is None,
   (hit("V"), hit("A")))
ok("because a legend in a side_notes line is a legend for a person",
   design.LABEL_ABBREV_MIN == 3)
ok("a digit standing in for a word resolves nothing",
   design.resolve_mark("4-nerve",
                       [plant("Four-nerve daisy")])[0] is None)
ok("a label two records could be is reported ambiguous, not assigned",
   design.resolve_mark("sage", [plant("Autumn sage"), plant("Rock sage")])
   == (None, "ambiguous"))
ok("and a caption is not a name",
   design.resolve_mark("ROYAL GOLD  -  5-7 ft, the bed's only vertical",
                       [plant("Climbing Royal Gold (existing)")])[0] is None)
ok("an empty label resolves to nothing rather than to the first record",
   design.resolve_mark("", RECS) == (None, None))

head("a state word describes the day, not the plant, so it is dropped")
ok("g02's legend defines hatching as dormant, cut back or bare",
   set(design.LAYOUT_STATES) >= {"cut", "dormant", "bare", "existing"})
ok("'Mint marigold CUT' still names a plant that is bought and planted",
   design.resolve_mark("Mint\nmarigold\nCUT",
                       [plant("Mexican mint marigold")])[1] == "abbreviation")
ok("and 'SENNA (existing)' names the existing clump",
   design.resolve_mark("SENNA\n(existing)",
                       [plant("Lindheimer's senna (existing, ft 3.25-5.5)")])[0]
   is not None)

head("a genus is not a plant, and that is reported at serious")
FRAG = {"plants": [plant("Cedar sedge", "bed_g01", 2,
                        botanical="Carex planostachys")],
        "layout": {"beds": [border(labels=["Carex", "Carex"])]}}
objs = design.check_layout(FRAG, site())
ok("'Carex' against 'Cedar sedge' is caught even though the counts agree",
   any(o["level"] == "serious" and "part of its botanical name" in o["say"]
       for o in objs), [(o["level"], o["say"]) for o in objs])
ok("it names the label, the bed and the record",
   says(objs, "'Carex' in bed_g01 for Cedar sedge"), [o["say"] for o in objs])
ok("and says why it costs money — the wrong species comes home",
   says(objs, "wrong species comes home"))
ok("while the full binomial on the label is not objected to",
   not any("botanical name rather than" in o["say"] for o in design.check_layout(
       {"plants": FRAG["plants"],
        "layout": {"beds": [border(labels=["Carex planostachys"] * 2)]}},
       site())))

head("an unresolvable label is reported as blindness, not as a wrong map")
BLIND = {"plants": [plant("Pansy and viola", "bed_g01", 4)],
         "layout": {"beds": [border(labels=["V"] * 4)]}}
objs = design.check_layout(BLIND, site())
ok("it is a note, because nothing here says the map is wrong",
   objs and all(o["level"] == "note" for o in objs),
   [(o["level"], o["say"]) for o in objs])
ok("reported from both ends at once — the mark and the record",
   says(objs, "'V' x4") and says(objs, "Pansy and viola"),
   [o["say"] for o in objs])
ok("it says what it is: the point past which nothing can tell",
   says(objs, "nothing can tell whether it is"))
ok("and the remedy is a `plant` key, which is the thing that would fix it",
   objs and "`plant` key" in objs[0]["fix"])
ok("one line per distinct label, not one per marker",
   len(objs) == 1, len(objs))

head("a `plant` key, once present, is what is read")
KEYED = {"plants": [plant("Pansy and viola", "bed_g01", 4)],
         "layout": {"beds": [border(
             labels=["V"] * 4,
             plants=[{"x": i, "y": 1.0, "r": 0.3, "label": "V",
                      "plant": "Pansy and viola"} for i in range(4)])]}}
ok("the shorthand stops being a problem the moment the mark names its record",
   not design.check_layout(KEYED, site()), design.check_layout(KEYED, site()))
ok("and the label on the drawing stays 'V', because a circle is 0.3 ft wide",
   [m[0] for m in design.layout_marks(KEYED["layout"]["beds"][0])] == ["V"] * 4)


head("`plant` has three states, and collapsing two of them is the bug")
# The remedy this module PRINTS is "put a `plant` key on each mark, and
# `\"plant\": null` on anything that is deliberately not a plant". It printed
# that while `mark.get("plant") or mark.get("label")` quietly turned a declared
# non-plant back into an undeclared one — advice to write a key half of which
# nothing read. That is this suite's own subject matter, so it is tested rather
# than described.
ok("a missing key says nothing and leaves the label to be matched",
   design.mark_declares({"label": "V"}) is None)
ok("a key naming a record is a claim about which record",
   design.mark_declares({"label": "V", "plant": "Viola"}) == "Viola")
ok("and `null` is a claim that this is not a planting at all",
   design.mark_declares({"label": "FROG", "plant": None})
   is design.NOT_A_PLANT)
ok("the three are distinguishable, which `.get` alone cannot do",
   len({id(design.mark_declares(m)) for m in
        ({"label": "x"}, {"label": "x", "plant": None})}) == 2)

ORNAMENT = {"plants": [plant("Damianita", "bed_g01", 2)],
            "layout": {"beds": [border(
                labels=["Damianita", "Damianita", "FROG"],
                plants=[{"x": 0, "y": 1.0, "r": 0.4, "label": "Damianita"},
                        {"x": 1, "y": 1.0, "r": 0.4, "label": "Damianita"},
                        {"x": 2, "y": 1.0, "r": 0.2, "label": "FROG",
                         "plant": None}])]}}
rec = design.reconcile_layout(ORNAMENT, site())[0]
ok("a declared ornament is not counted as a plant on the map",
   rec["marks"] == 2 and rec["plants"] == 2, (rec["marks"], rec["plants"]))
ok("it is not counted as a missing plant either — it is counted as itself",
   rec["not_plants"] == {"FROG": 1} and not rec["unresolved"], rec)
ok("so the bed reconciles, and the pond frog stays on the drawing",
   not design.check_layout(ORNAMENT, site()),
   design.check_layout(ORNAMENT, site()))

# The asymmetry that matters here: an unresolved LABEL is silence, and a wrong
# DECLARATION is a false statement that reads as verified. Reporting them at the
# same level would make marking a map up strictly safer than leaving it alone.
WRONG = {"plants": [plant("Damianita", "bed_g01", 1)],
         "layout": {"beds": [border(
             labels=["D"],
             plants=[{"x": 0, "y": 1.0, "r": 0.4, "label": "D",
                      "plant": "Damianta"}])]}}
objs = design.check_layout(WRONG, site())
ok("a typo'd declaration is serious, where an unreadable label is a note",
   [o["level"] for o in says(objs, "declares a plant this zone")] == ["serious"],
   [(o["level"], o["say"][:60]) for o in objs])
ok("and it quotes the claim, so the typo is visible without opening the file",
   "'Damianta'" in says(objs, "declares a plant this zone")[0]["say"])
ok("a mark that lies is not also counted as drawing its plant",
   design.reconcile_layout(WRONG, site())[0]["unmarked"] == [("Damianita", 1)])

# ----------------------------------------------------------- joining the two

head("a layout bed is joined to a zone, or reported — never guessed")
ok("the bed's own `zone` key wins",
   design.layout_zone(site(), {"name": "anything", "zone": "bed_g01"})
   == "bed_g01")
ok("a name that is the zone key resolves directly",
   design.layout_zone(site(), {"name": "bed_g01"}) == "bed_g01")
ok("a hyphenated file name resolves through label_short",
   design.layout_zone(site(), {"name": "g01-southeast-corner"}) == "bed_g01")
ok("and so does the raised bed's",
   design.layout_zone(site("grid", "bed_raised", "raised"),
                      {"name": "raised-bed"}) == "bed_raised")
TWO = {"zones": {"a": {"label_short": "bed"}, "b": {"label_short": "corner"}}}
ok("a name matching two zones resolves to neither",
   design.layout_zone(TWO, {"name": "bed-corner"}) is None)
ok("a name matching none resolves to none",
   design.layout_zone(site(), {"name": "somewhere-else"}) is None)
UNJOINED = {"plants": [], "layout": {"beds": [border(name="mystery-bed")]}}
objs = design.check_layout(UNJOINED, site())
ok("a map joined to nothing is serious, because it renders perfectly anyway",
   any(o["level"] == "serious" and "names no zone" in o["say"] for o in objs),
   [(o["level"], o["say"]) for o in objs])
ok("and the objection says exactly that",
   says(objs, "renders perfectly and could say anything"))

# --------------------------------------------------------- against the yard

head("cloverleaf-austin as it stands today")
from lib import yards  # noqa: E402

REAL = yards.load("cloverleaf-austin", "design.json")
RSITE = yards.load("cloverleaf-austin", "site.json")
if not REAL or not RSITE:
    print("  --    no cloverleaf-austin on disk, skipped")
else:
    recs = {r["bed"]: r for r in design.reconcile_layout(REAL, RSITE)}
    ok("all five bed maps join to a zone",
       len(recs) == 5 and all(r["zone"] for r in recs.values()),
       [(k, v["zone"]) for k, v in recs.items()])
    raised = recs["raised-bed"]
    ok("the raised bed is 32 squares against 45 plants",
       (raised["marks"], raised["plants"]) == (32, 45),
       (raised["marks"], raised["plants"]))
    multi = {n: (m, c) for n, m, c in raised["matched"] if c > m}
    ok("and the whole 13 is three crops several to the square",
       sum(c - m for m, c in multi.values()) == 13 and len(multi) == 3, multi)
    ok("named: garlic, viola and calendula",
       set(multi) == {"Softneck garlic (cloves)", "Viola", "Calendula"}, multi)
    ok("no crop has more squares than plants, so nothing is serious there",
       not [1 for n, m, c in raised["matched"] if m > c])
    ok("every border map's totals balance",
       all(r["marks"] == r["plants"] for r in recs.values()
           if r["unit"] == "plant"),
       [(k, v["marks"], v["plants"]) for k, v in recs.items()])
    ok("g02 holds a plant record no mark draws — the bluebonnet seed bank",
       any("Bluebonnet" in n for n, _c in recs["g02-rear-wall"]["unmarked"]),
       recs["g02-rear-wall"]["unmarked"])
    ok("and a mark that is not a plant at all, which no count could reveal",
       "FROG" in recs["g02-rear-wall"]["unresolved"],
       recs["g02-rear-wall"]["unresolved"])
    ok("the sedge is labelled 'Carex' on both maps it appears on",
       [k for k, v in recs.items() if "Carex" in v["fragments"]]
       == ["g03-seating", "g04-west-wall"],
       {k: v["fragments"] for k, v in recs.items()})
    ok("and it points at the record renamed this morning",
       recs["g03-seating"]["fragments"]["Carex"] == "Cedar sedge")
    objs = design.check_layout(REAL, RSITE)
    ok("no bed map disagrees with the records on a count today",
       not [o for o in objs if "draws" in o["say"] or "totals agree" in o["say"]
            or "more squares" in o["say"]],
       [o["say"] for o in objs])
    serious = [o for o in objs if o["level"] == "serious"]
    ok("so the one serious finding today is the genus label",
       len(serious) == 1 and "part of its botanical name" in serious[0]["say"],
       [(o["level"], o["say"][:60]) for o in objs])
    ok("and everything else it has to say is a note",
       {o["level"] for o in objs} == {"serious", "note"},
       sorted({o["level"] for o in objs}))

    # ------------------------------------------------------- the falsifier
    head("the two can now disagree, which is the point of keeping both")
    import copy

    CUT = copy.deepcopy(REAL)
    for p in CUT["plants"]:
        if p["name"] == "Gulf muhly":
            p["count"] = 3                      # the map still draws five
    ok("cutting two muhly from the records and not from the map is caught",
       any("Gulf muhly" in o["say"] and o["level"] == "serious"
           for o in design.check_layout(CUT, RSITE)),
       [o["say"] for o in design.check_layout(CUT, RSITE)
        if o["level"] == "serious"])

    ADD = copy.deepcopy(REAL)
    for b in ADD["layout"]["beds"]:
        if b["name"] == "g02-rear-wall":
            b["plants"].append({"x": 5.0, "y": 1.0, "r": 0.6,
                                "label": "Damianita"})
    ok("and adding a damianita to the map and not to the records is caught",
       any("Damianita" in o["say"] and o["level"] == "serious"
           for o in design.check_layout(ADD, RSITE)),
       [o["say"] for o in design.check_layout(ADD, RSITE)
        if o["level"] == "serious"])

    MOVED = copy.deepcopy(REAL)
    for p in MOVED["plants"]:
        if p["name"] == "Rock rose":
            p["zone"] = "bed_g01"               # drawn in g02, recorded in g01
    objs = design.check_layout(MOVED, RSITE)
    ok("a plant moved to another zone is caught in both beds at once",
       len([o for o in objs
            if o["level"] == "serious"
            and ("bed_g01" in o["about"] or "bed_g02" in o["about"])]) == 2,
       [(o["about"], o["say"][:70]) for o in objs if o["level"] == "serious"])

    RENAMED = copy.deepcopy(REAL)
    for p in RENAMED["plants"]:
        if p["name"] == "Cedar sedge":
            p["name"] = "Texas sedge"           # this morning's error, restored
            p["botanical"] = "Carex texensis"
    ok("and the map's 'Carex' follows the record wherever the record goes, "
       "which is why the label is the fault",
       all(r["fragments"].get("Carex") == "Texas sedge"
           for r in design.reconcile_layout(RENAMED, RSITE)
           if r["fragments"]),
       [r["fragments"] for r in design.reconcile_layout(RENAMED, RSITE)])

    head("and the linter actually runs it")
    # The failure this whole check is an instance of, one more time: a thing
    # that is written and never read. `check_layout` passing its own tests
    # while nothing calls it would be `overhang_ft` again — written by no
    # module, read by one.
    try:
        wired = design.check("cloverleaf-austin")
    except SystemExit as e:
        wired = None
        print(f"  --    design is gated on this yard right now ({e}), skipped")
    if wired is not None:
        ok("`python3 -m lib.design` reports the layout findings",
           any("name nothing in the plant records" in o["say"] for o in wired))
        ok("including the genus label, at serious",
           any(o["level"] == "serious" and "part of its botanical name"
               in o["say"] for o in wired))
        ok("and the raised bed's count now has an answer beside the shrug",
           any("sown several to the square" in o["say"] for o in wired)
           and any("worth a look at the map" in o["say"] for o in wired),
           [o["say"][:50] for o in wired if "square" in o["say"]])

    head("the check reads the files and re-derives neither")
    # An audit that regenerated the layout from the plant records would agree
    # with itself perfectly and measure nothing — the same fault that let g05's
    # rows through. So `reconcile_layout` must not build a layout of its own.
    import lib.drawbeds as _db  # noqa: E402

    _real_render = _db.render
    try:
        def _boom(*_a, **_k):
            raise AssertionError("reconcile_layout rendered a map")

        _db.render = _boom
        ok("nothing is drawn on the way to comparing them",
           len(design.reconcile_layout(REAL, RSITE)) == 5)
    finally:
        _db.render = _real_render

print(f"\n{PASS} of {PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
