#!/usr/bin/env python3
"""A bed has a depth, and rows add up.

    python3 tools/test_rows.py

The bug this suite is aimed at is not an arithmetic slip. `lib.niches` budgeted
`bed_g05` three rows of 2.5, 2.5 and 1.5 ft of spread in a bed the tape says is
3.708 ft deep, and `design.check_space` passed it at 1.10x. Both were right
about area. Neither had a way to be wrong about depth, because area was the only
question either of them asked, and `lib.niches` asked it against
`check_space`'s own coverage band — so the two agreed by construction and their
agreement was mistaken for a check.

That is the same shape as three other faults found on this yard in one day: a
driveway recorded 14.5 ft from a bed the plan said it abutted with nothing
comparing the coordinates; seven `lib.schedule` archetypes unreachable because a
guard read `hardscape["kind"]` against a design that writes `item`; a yard-wide
pH applied to imported soil nobody had recorded. In each one, two things agreed
because they shared an assumption.

So the tests here come in three groups, and the third is the one that matters:

  the rule          summing the ranks is what a layered bed consumes, and the
                    arithmetic of it
  the constructor   `lib.niches` cannot propose a stack deeper than the bed,
                    whatever the area says
  the falsifier     the two can now disagree. `check_space` measures the plants
                    somebody actually bought, `niches.buildable` reads the rows
                    back off the file and puts them against the tape, and each
                    can catch the other being wrong
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import design, niches  # noqa: E402

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


def plant(name, spread, layer, **kw):
    p = {"name": name, "mature_spread_ft": spread, "layer": layer,
         "mature_height_ft": 2.0, "count": 1, "zone": "bed"}
    p.update(kw)
    return p


def site(depth, area=32.4, overhang=None, **kw):
    z = {"style": "bed", "kind": "border", "area_sqft": area,
         "usable_depth_ft": depth}
    if overhang:
        z["canopy_overhang_ft"] = overhang
    z.update(kw)
    return {"zones": {"bed": z}}


def niche(depth, area=32.4, overhang=None, kind="border"):
    n = {"id": "bed", "label": "bed", "zones": ["bed"], "kind": kind,
         "area_sqft": area, "usable_depth_ft": depth,
         "overhang_ft": overhang,
         "light": {"hours": 5.0, "category": "part sun"},
         "soil": {"ph": 8.2, "drainage": "slow"}, "water": {},
         "constraints": []}
    n["signature"] = niches.signature(n)
    return n


# --------------------------------------------------------------- the rule

head("what a layered bed consumes is the sum of its ranks")
ok("three ranks at 2.5, 2.5 and 1.5 need 6.5 ft",
   abs(design.row_stack_depth([2.5, 2.5, 1.5]) - 6.5) < 1e-9)
ok("one rank needs its own spread",
   abs(design.row_stack_depth([2.5]) - 2.5) < 1e-9)
ok("no ranks need nothing", design.row_stack_depth([]) == 0)

G05 = [plant("Back", 2.5, "back"), plant("Middle", 2.5, "middle"),
       plant("Front", 1.5, "front")]
stack, ranks = design.row_stack(G05)
ok("g05's derived stack is 6.5 ft", abs(stack - 6.5) < 1e-9, stack)
ok("and it is three ranks", len(ranks) == 3)
ok("ranks come back back-to-front",
   [k for k, _d, _n, _c in ranks] == ["back", "middle", "front"])

head("a rank is as deep as its widest member, which is the lenient reading")
WIDE = [plant("Narrow", 1.2, "back"), plant("Wide", 3.0, "back"),
        plant("Mid", 1.8, "back"), plant("Edge", 1.5, "front")]
stack, ranks = design.row_stack(WIDE)
ok("six plants in one rank are one band", len(ranks) == 2)
ok("and the band is the widest of them, not the mean or the sum",
   abs(stack - 4.5) < 1e-9, stack)
ok("the widest plant is named, because that is the one to move",
   ranks[0][2] == "Wide")

head("a vine is carried overhead, exactly as `footprint` already has it")
VINE = [plant("Rose", 3.0, "vine"), plant("Edge", 1.5, "front")]
stack, ranks = design.row_stack(VINE)
ok("a trellised vine occupies no rank", len(ranks) == 1 and stack == 1.5)

head("an unrecognised layer is counted and named, never skipped")
ACCENT = [plant("Yucca", 2.0, "accent"), plant("Daisy", 0.9, "front")]
stack, ranks = design.row_stack(ACCENT)
ok("an `accent` still occupies depth", abs(stack - 2.9) < 1e-9, stack)
ok("it lands in one band of its own rather than one band each",
   len(design.row_stack([plant("A", 1.0, "accent"), plant("B", 1.2, "accent"),
                         plant("C", 0.9, "front")])[1]) == 2)
objs = design._check_row_depth("bed", ACCENT, site(2.417, 9.9), "bed")
ok("and the objection says which word it did not recognise",
   objs and "'accent'" in objs[0]["say"], objs and objs[0]["say"])
ok("and says the number falls if it is really inside another rank",
   objs and "this number falls" in objs[0]["say"])

head("depth room is usable depth plus whatever overhang is DECLARED")
ok("no declaration means no allowance",
   design.depth_room(site(2.167), "bed") == 2.167)
ok("a declared apron is credited",
   abs(design.depth_room(site(2.167, overhang=1.167), "bed") - 3.334) < 1e-9)
ok("a zone with no measured depth has no room to report",
   design.depth_room({"zones": {"bed": {"area_sqft": 9.0}}}, "bed") is None)

# --------------------------------------------------- the check, on real shapes

head("check_space sees the stack, which no area figure could")
D = {"plants": [dict(p, zone="bed") for p in G05]}
S = site(3.708, 32.4)
SUN = {"by_zone_and_month": {}}
objs = design.check_space(D, S, SUN)
say = " ".join(o["say"] for o in objs)
ok("g05's slate is objected to", any("ranks add up" in o["say"] for o in objs))
ok("as serious, not as a note",
   all(o["level"] == "serious" for o in objs if "ranks add up" in o["say"]))
ok("the objection quotes the sum and the bed", "6.5 ft" in say
   and "3.708" in say, say)
ok("and it says area cannot see it, because that is the lesson",
   "Area is not the constraint" in say)
# The whole reason this was invisible: it passes the area arm comfortably.
ok("while the area arm is happy at 1.10x",
   not any("overplanted" in o["say"] for o in objs),
   [o["say"] for o in objs])
ok("and no individual plant is wider than the bed either, which is why "
   "_check_depth stayed quiet",
   not design._check_depth("bed", D["plants"], S, "bed"))

head("a bed that does fit is not objected to")
FITS = {"plants": [dict(plant("Back", 1.5, "back"), zone="bed"),
                   dict(plant("Middle", 1.5, "middle"), zone="bed"),
                   dict(plant("Front", 0.5, "front"), zone="bed")]}
ok("small, small and edging in 3.708 ft passes",
   not any("ranks add up" in o["say"]
           for o in design.check_space(FITS, S, SUN)))
ok("and exactly filling the depth passes",
   not design._check_row_depth("bed", FITS["plants"], site(3.5), "bed"))
ok("while a hair over does not",
   design._check_row_depth("bed", FITS["plants"], site(3.4), "bed"))

head("one rank is _check_depth's question and is left to it")
SOLO = [plant("Wide", 4.0, "back"), plant("Also", 3.5, "back")]
ok("a single rank raises no stack objection",
   not design._check_row_depth("bed", SOLO, site(3.708), "bed"))
ok("because the individual arm already has it",
   design._check_depth("bed", [dict(p, count=1) for p in SOLO],
                       site(3.708), "bed"))

head("the declared apron is honoured on the stack arm as well as the plant arm")
G03 = [plant("Mistflower", 3.0, "middle"), plant("Sedge", 1.2, "front")]
ok("4.2 ft of ranks over 2.167 ft of soil is objected to",
   design._check_row_depth("bed", G03, site(2.167, 41.5), "bed"))
ok("and still is with 1.167 ft of apron, which only gets it to 3.334",
   design._check_row_depth("bed", G03, site(2.167, 41.5, overhang=1.167),
                           "bed"))
ok("but the objection says the apron was counted",
   "overhang this zone allows" in design._check_row_depth(
       "bed", G03, site(2.167, 41.5, overhang=1.167), "bed")[0]["say"])
ok("and a stack the apron does rescue passes",
   not design._check_row_depth(
       "bed", [plant("A", 1.5, "back"), plant("B", 1.5, "front")],
       site(2.167, 41.5, overhang=1.167), "bed"))

head("a grid and a pot bed are measured in their own units, not in depth")
GRID = {"plants": [dict(p, zone="bed") for p in G05]}
ok("a square-foot bed gets no rank objection",
   not any("ranks add up" in o["say"] for o in design.check_space(
       GRID, site(4.083, 33.0, kind="grid", squares=32), SUN)))
ok("nor does a barrel bed",
   not any("ranks add up" in o["say"] for o in design.check_space(
       GRID, site(None, 9.4, kind="container",
                  containers={"count": 3}), SUN)))

# --------------------------------------------------------- the constructor

head("lib.niches cannot propose a stack deeper than the bed")
for depth, area in ((3.708, 32.4), (3.958, 74.2), (2.417, 9.9), (2.042, 13.3),
                    (2.167, 20.8), (6.5, 60.0), (1.9, 8.0), (1.2, 5.0),
                    (4.5, 50.0), (3.0, 30.0), (3.4, 30.0)):
    n = niche(depth, area)
    slots = niches._border_slots(n)
    rows = [s for s in slots if not s.get("excluded")]
    stack = design.row_stack_depth([s["spread_ft"] for s in rows])
    ok(f"a {depth} ft bed of {area:g} sq ft is offered {stack:g} ft of rows",
       stack <= depth + 1e-9,
       f"{[(s['layer'], s['spread_ft']) for s in rows]}")

head("the g05 case specifically, which is what this is all for")
N05 = niche(3.708, 32.4)
S05 = niches._border_slots(N05)
live = [s for s in S05 if not s.get("excluded")]
ok("it still gets three ranks — the bed is deep enough for three",
   len(live) == 3, [s["layer"] for s in live])
ok("but nothing over 1.5 ft of spread in any of them",
   all(s["spread_ft"] <= 1.5 for s in live),
   [(s["layer"], s["spread_ft"]) for s in live])
ok("they sum to 3.5 ft, inside the 3.708 the tape measured",
   abs(design.row_stack_depth([s["spread_ft"] for s in live]) - 3.5) < 1e-9)
ok("the budget records the room and the stack, so the file can be audited",
   N05["budget"]["depth_room_ft"] == 3.708
   and N05["budget"]["rows_ft"] == 3.5, N05.get("budget"))
ok("and the count is capped by the bed's own length, not by its area share",
   # 8.74 ft of run holds 17 edging plants in a line. The area share pays for
   # 47, which is three lines deep in a rank half a foot deep.
   next(s for s in live if s["layer"] == "front")["count"][1] == 17,
   [(s["layer"], s["count"]) for s in live])

head("the row count follows from the size classes, not from a threshold")
ok("the shallowest three-rank stack the classes allow is 3.5 ft",
   abs(niches._min_stack(["back", "middle", "front"], 10.0) - 3.5) < 1e-9)
ok("so a 3.4 ft bed gets two ranks, not three",
   niches._rows_for(3.4) == ["back", "front"], niches._rows_for(3.4))
ok("and a 3.5 ft bed gets three", len(niches._rows_for(3.5)) == 3)
ok("the shallowest two-rank stack is 2.0 ft, so a 2.0 ft bed gets two",
   niches._rows_for(2.0) == ["back", "front"])
ok("and a 1.9 ft bed gets one, an inch short of a second rank",
   niches._rows_for(1.9) == ["front"], niches._rows_for(1.9))
ok("a bed too shallow for any rank gets none", niches._rows_for(0.3) == [])
ok("and an unmeasured depth is not a shallow bed",
   len(niches._rows_for(None)) == 3)
ok("the exclusion says the sum, not just the row count",
   "need 3.5 ft of depth" in niches._no_row("middle", 2.4,
                                            ["back", "front"]))

head("the declared apron reaches lib.niches too")
# It read `overhang_ft` from the first version and `derive` never wrote it, so
# g03's declared 1.167 ft counted for nothing and this module was quietly
# stricter than the linter it budgets against.
BARE = [s for s in niches._border_slots(niche(2.167, 20.8))
        if not s.get("excluded")]
APRON = [s for s in niches._border_slots(niche(2.167, 20.8, overhang=1.167))
         if not s.get("excluded")]
ok("an apron buys the front rank a bigger size class",
   next(s for s in APRON if s["layer"] == "front")["spread_ft"]
   > next(s for s in BARE if s["layer"] == "front")["spread_ft"],
   [(s["layer"], s["spread_ft"]) for s in APRON])
ok("and the stack still fits the room it was given",
   design.row_stack_depth([s["spread_ft"] for s in APRON])
   <= 2.167 + 1.167 + 1e-9)

head("depth is shared out, not taken back-first")
# Back-first greed hands the back rank of a 6.5 ft bed a 4 ft class and leaves
# the front row six inches, which is not what anybody laying out a border does.
DEEP = niches._border_slots(niche(6.5, 60.0))
by = {s["layer"]: s for s in DEEP if not s.get("excluded")}
ok("a 6.5 ft bed gives its back rank 2.5 ft rather than 4",
   by["back"]["spread_ft"] == 2.5, [(k, v["spread_ft"]) for k, v in by.items()])
ok("and its front rank a real size class rather than the leftovers",
   by["front"]["spread_ft"] >= 1.5)
ok("and the three of them still fit",
   abs(design.row_stack_depth([s["spread_ft"] for s in by.values()])
       - 6.5) < 1e-9)

head("a rank set tighter than its spread says so rather than being dropped")
# 9.9 sq ft over 2.417 ft is a 4.1 ft run, and three small plants at 1.5 ft is
# 4.5 ft of row. Tight along the length is not the same kind of wrong as deeper
# than the bed: those plants grow together, they do not stand in the wall.
TIGHT = niches._border_slots(niche(2.417, 9.9))
back = next(s for s in TIGHT if s["layer"] == "back")
ok("the rank is not excluded", not back.get("excluded"))
ok("the count holds at the minimum group", back["count"][0] == 3)
ok("and the reason says the spacing gives, not the bed",
   "grow together into one mass" in back["why"], back["why"])

# ------------------------------------------------------------- the falsifier

head("the rows on record, against the bed as measured")
BAD = {"niches": [dict(niche(3.708, 32.4), slots=[
    {"id": "bed.back", "layer": "back", "spread_ft": 2.5, "count": [3, 3]},
    {"id": "bed.middle", "layer": "middle", "spread_ft": 2.5, "count": [3, 3]},
    {"id": "bed.front", "layer": "front", "spread_ft": 1.5, "count": [3, 4]},
])]}
import lib.yards as _y  # noqa: E402

_real = _y.load_site
try:
    _y.load_site = lambda s: site(3.708, 32.4)
    faults = niches.buildable("x", BAD)
    ok("g05 as it sat on disk is caught", len(faults) == 1, faults)
    ok("and the fault names the sum and the measurement",
       "6.5 ft" in faults[0][1] and "3.708" in faults[0][1], faults)
    ok("and says nothing chosen from those slots will fit",
       "will fit" in faults[0][1])

    # This is the property the whole exercise is about. The audit reads the
    # TAPE, not the copy of it the module cached at derive time, so re-measuring
    # a bed catches a slate that was budgeted against the old figure.
    _y.load_site = lambda s: site(2.0, 32.4)
    faults = niches.buildable("x", BAD)
    ok("a bed re-measured shallower than niches.json remembers is reported",
       any("still carries" in why for _id, why in faults), faults)
    ok("and it names both figures",
       any("2 ft deep" in why and "3.708" in why for _id, why in faults),
       faults)

    # And the case the staleness line alone does NOT cover, which is the one
    # that decides whether this is an audit or a formality. These rows fit the
    # depth niches.json cached and do not fit the depth the tape now reads. If
    # the check consults the cached copy it reports a stale figure and nothing
    # else, and the slate stays on the ballot; the fault has to come out of the
    # MEASUREMENT.
    STALE = {"niches": [dict(niche(3.708, 32.4), slots=[
        {"id": "bed.back", "layer": "back", "spread_ft": 1.5, "count": [3, 5]},
        {"id": "bed.middle", "layer": "middle", "spread_ft": 1.5,
         "count": [3, 5]},
        {"id": "bed.front", "layer": "front", "spread_ft": 0.5,
         "count": [5, 17]},
    ])]}
    _y.load_site = lambda s: site(3.708, 32.4)
    ok("that stack is fine against the depth the file remembers",
       not niches.buildable("x", STALE), niches.buildable("x", STALE))
    _y.load_site = lambda s: site(2.4, 32.4)
    faults = niches.buildable("x", STALE)
    ok("and is caught the moment the tape says the bed is 2.4 ft",
       any("rows on record" in why for _id, why in faults), faults)
    ok("so the fault comes from the measurement and not from the file's copy "
       "of it",
       any("2.4 ft" in why for _id, why in faults
           if "rows on record" in why), faults)

    # The other direction, because a check that only ever objects is not
    # measuring anything: re-measuring a bed DEEPER has to clear the fault.
    _y.load_site = lambda s: site(7.0, 32.4)
    ok("and a bed re-measured deeper clears the stack fault",
       not any("rows on record" in why
               for _id, why in niches.buildable("x", BAD)),
       niches.buildable("x", BAD))

    # And the good case, so the audit is not simply always loud.
    _y.load_site = lambda s: site(3.708, 32.4)
    GOOD = {"niches": [dict(niche(3.708, 32.4),
                            slots=niches._border_slots(niche(3.708, 32.4)))]}
    ok("what the constructor produces now passes the audit",
       not niches.buildable("x", GOOD), niches.buildable("x", GOOD))

    # The property that makes this an audit rather than a restatement: it must
    # not re-run the thing it is auditing. Re-deriving and comparing would only
    # ever prove `capacity` agrees with itself, which is exactly how g05 got
    # through — so `derive` is made to explode and the audit still has to work.
    _real_derive = niches.derive
    try:
        def _boom(_slug):
            raise AssertionError("buildable re-derived, which measures nothing")

        niches.derive = _boom
        ok("the audit runs without re-deriving, so it can catch the "
           "constructor being wrong",
           len(niches.buildable("x", BAD)) == 1)
    finally:
        niches.derive = _real_derive
finally:
    _y.load_site = _real

head("a grid and a container are not audited on depth")
GRIDN = {"niches": [dict(niche(4.083, 33.0, kind="grid"), slots=[
    {"id": "bed.a", "layer": "tall end", "size": "square", "count": [10, 10]},
    {"id": "bed.b", "layer": "middle", "size": "square", "count": [10, 10]},
])]}
try:
    _y.load_site = lambda s: site(4.083, 33.0, kind="grid", squares=32)
    ok("a square-foot bed raises no depth fault",
       not niches.buildable("x", GRIDN))
finally:
    _y.load_site = _real

head("the two arms disagree where they should, which is the whole point")
# `lib.niches` works in the MIDPOINT spread of a size class; `check_space`
# works in the spread of the plant somebody actually bought. A slot that fits
# at the midpoint of `small` fails at the top of it, and that is not the two
# modules being inconsistent — it is the linter being able to falsify the
# proposal.
SLOTS = niches._border_slots(niche(3.708, 32.4))
mid = [s["spread_ft"] for s in SLOTS if not s.get("excluded")]
ok("the proposal fits at the class midpoints",
   design.row_stack_depth(mid) <= 3.708)
top = [plant(f"Top {i}", 2.0, lay) for i, lay in enumerate(
    s["layer"] for s in SLOTS if not s.get("excluded"))]
ok("and the linter objects once each row is filled at the top of its class",
   design._check_row_depth("bed", top, site(3.708, 32.4), "bed"),
   design.row_stack_depth([p["mature_spread_ft"] for p in top]))
ok("which is a disagreement the shared coverage band could never produce",
   design.COVER_CEILING == 1.15)

print(f"\n{PASS} of {PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
