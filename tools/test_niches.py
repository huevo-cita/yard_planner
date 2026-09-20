#!/usr/bin/env python3
"""A slate only offers what the linter will accept, and a pick is revisable.

The promise this stage makes is narrow and easy to break: everything on the
ballot already fits, so a person who chooses from it cannot be told afterwards
that their choice was never possible. Every test here is a way that promise
broke during the rehearsal, on a real yard, before it was fixed.

    python3 tools/test_niches.py
"""
import datetime
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


SITE = {
    "zones": {
        "border": {"style": "bed", "area_sqft": 40.0, "usable_depth_ft": 3.5,
                   "kind": "border"},
        "shallow": {"style": "bed", "area_sqft": 12.0, "usable_depth_ft": 1.8,
                    "kind": "border"},
        "pots": {"style": "bed", "area_sqft": 9.0, "kind": "container",
                 "containers": {"count": 3, "each_sqft": 3.0}},
    },
    "climate": {"heat": {"days_over_95f_per_year": 45.0},
                "frost_32f": {"first_fall": {"median": "Dec 13"},
                              "last_spring": {"median": "Feb 13"}}},
}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
          "Nov", "Dec"]
SUN = {"by_zone_and_month": {
    z: {m: {"effective": h, "clear": h, "best_cell": h + 1}
        for m in MONTHS}
    for z, h in (("border", 6.5), ("shallow", 4.5), ("pots", 5.0))}}
COND = {"soil": {"ph": 8.2, "drainage": "slow", "texture": "clay"},
        "water": {"hose_reaches": True}}


def niche(zone, hours, area, depth, kind="border", **kw):
    n = {"id": zone, "label": zone, "zones": [zone], "kind": kind,
         "area_sqft": area, "usable_depth_ft": depth,
         "light": {"hours": hours, "category": niches.light_band(hours)},
         "soil": ({"ph": None} if kind == "container"
                  else {"ph": 8.2, "drainage": "slow"}),
         "water": {}, "constraints": []}
    n.update(kw)
    n["signature"] = niches.signature(n)
    return n


def plant(name, light, spread, **kw):
    p = {"name": name, "botanical": "Genus species", "light": light,
         "water": "low", "mature_spread_ft": spread, "mature_height_ft": 2.0,
         "source": "test"}
    p.update(kw)
    return p


head("a slate refuses what the linter would refuse")
N = niche("shallow", 4.5, 12.0, 1.8)
SLOT = {"id": "shallow.back", "layer": "back", "size": "small",
        "spread_ft": 1.5, "count": [3, 4], "budget_share": 0.6,
        "decisions": []}

ok("a plant wider than the bed is deep is refused",
   "nowhere for it to go" in (niches._rejects(
       plant("Wide", "part sun", 3.0), N, SLOT, SITE, SUN) or ""))
ok("and design.py agrees, which is the point",
   any("wider than the bed" in o["say"] for o in design._check_depth(
       "shallow", [plant("Wide", "part sun", 3.0, count=1)], SITE, "shallow")))

ok("a plant short of light is refused",
   "would use" in (niches._rejects(
       plant("Bright", "full sun", 1.0), N, SLOT, SITE, SUN) or "")
   or "averages" in (niches._rejects(
       plant("Bright", "full sun", 1.0), N, SLOT, SITE, SUN) or ""))
ok("light is judged over the plant's OWN months, not the growing season",
   # the bed is 4.5 h year-round here, so a bloom-month restriction that the
   # niche figure hides has to still be read off the zone
   niches._rejects(plant("Bright", "full sun", 1.0), N, SLOT, SITE,
                   SUN) is not None)
ok("a shade plant in a hot bright bed is refused too, not just a dark one",
   "scorch" in (niches._rejects(
       plant("Shady", "part shade", 1.0),
       niche("border", 6.5, 40.0, 3.5), SLOT, SITE, SUN) or ""))
ok("wrong pH is refused",
   "pH" in (niches._rejects(
       plant("Acid", "part sun", 1.0, ph_range=[5.0, 6.5]),
       N, SLOT, SITE, SUN) or ""))
ok("sharp drainage in slow soil is refused",
   "sharp drainage" in (niches._rejects(
       plant("Grit", "part sun", 1.0, soil_drainage="sharp"),
       N, SLOT, SITE, SUN) or ""))
ok("a candidate missing a field the linter reads is refused",
   "cannot be checked" in (niches._rejects(
       {"name": "Vague", "light": "part sun"}, N, SLOT, SITE, SUN) or ""))
ok("and something that fits is not refused",
   niches._rejects(plant("Fine", "part sun", 1.2), N, SLOT, SITE,
                   SUN) is None)

head("a row is budgeted against its own share, not the whole bed")
# A deep bed, so depth is not what refuses this. 12 sq ft, this row's share
# 0.6, so 8.3 sq ft of ceiling for three plants. At 1.7 ft they need 6.8 and
# fit; at 2.0 ft they need 9.4 and do not. Against the WHOLE bed's ceiling of
# 13.8 both pass, which is the bug: every row clears on its own and the bed is
# overplanted once they are added up.
DEEP = niche("border", 6.5, 12.0, 4.0)
ok("a row that only fits by eating the other rows' room is refused",
   "the other rows are counting on" in (niches._rejects(
       plant("Hoggish", "part sun", 2.0), DEEP, SLOT, SITE, SUN) or ""),
   niches._rejects(plant("Hoggish", "part sun", 2.0), DEEP, SLOT, SITE, SUN))
ok("while one that fits its own share passes",
   niches._rejects(plant("Modest", "part sun", 1.7), DEEP, SLOT, SITE,
                   SUN) is None)

head("a pot is not the ground")
POTS = niche("pots", 5.0, 9.0, None, kind="container", containers=3)
ok("the yard's pH does not rule a container",
   niches._soil(COND, "container")["ph"] is None)
ok("so an acid-loving plant is offered for a pot",
   niches._rejects(plant("Acid", "part sun", 1.0, ph_range=[5.0, 6.5]),
                   POTS, {"id": "pots.pot1", "count": [1, 1],
                          "decisions": []}, SITE, SUN) is None)
ok("and design.check_soil skips a container zone as well",
   not design.check_soil(
       plant("Acid", "part sun", 1.0, ph_range=[5.0, 6.5], zone="pots"),
       COND, SITE))
ok("but still judges an in-ground zone",
   design.check_soil(
       plant("Acid", "part sun", 1.0, ph_range=[5.0, 6.5], zone="border"),
       COND, SITE))

head("the count follows the plant, not its size class")
BIG = niche("border", 6.5, 40.0, 3.5)
S2 = {"id": "border.front", "layer": "front", "size": "small",
      "spread_ft": 1.5, "count": [5, 8], "budget_share": 0.25,
      "decisions": []}
few = niches.count_for(BIG, S2, plant("Chunky", "part sun", 1.5))
many = niches.count_for(BIG, S2, plant("Tiny", "part sun", 0.7))
ok("a smaller plant gets a bigger count", many > few, f"{many} vs {few}")
ok("never below the minimum group", niches.count_for(
    BIG, S2, plant("Huge", "part sun", 2.0)) >= 3)
ok("and the coverage lands inside the band the linter enforces",
   design.COVER_FLOOR <= (many * niches._footprint(0.7)) / (40.0 * 0.25)
   <= design.COVER_CEILING)

head("a bed is cut where its light genuinely changes, and not otherwise")
flat = [(0, 3, 5.0, "a"), (3, 6, 5.1, "b"), (6, 9, 5.2, "c")]
pieces, cut = niches.split(flat)
ok("an even bed stays one niche", len(pieces) == 1 and cut is None)

steep = [(0, 5, 5.0, "a"), (5, 10, 3.2, "b")]
pieces, cut = niches.split(steep)
ok("a bed straddling a threshold is cut", len(pieces) == 2 and cut)
ok("and each piece carries its own hours",
   pieces[0][1] != pieces[1][1])

sliver = [(0, 9.5, 5.0, "a"), (9.5, 10, 3.2, "b")]
pieces, cut = niches.split(sliver)
ok("a cut that would leave a sliver is not made", len(pieces) == 1)

head("rows across a bed are not positions along it")
overlapping = [(0, 3, 5.4, "g02 ft 0-3 wall"),
               (0, 3, 6.4, "g02 FRONT ft 0-3 edge"),
               (3, 9, 5.5, "g02 ft 3-9 wall")]
kept, dropped = niches.along_the_bed(overlapping)
ok("the second reading of the same feet is set aside", len(dropped) == 1)
ok("and it is reported rather than lost", dropped[0][2] == 6.4)
ok("what is left does not double back",
   all(kept[i][1] <= kept[i + 1][0] for i in range(len(kept) - 1)))

head("the weighted mean, because a long stretch counts for more")
ok("two feet at 5 and one at 2 is not 3.5",
   abs(niches._mean([(0, 2, 5.0, "a"), (2, 3, 2.0, "b")]) - 4.0) < 0.01)

head("a bed only gets the rows it is deep enough for")
ok("a shallow bed has two rows", niches._rows_for(2.0) == ["back", "front"])
ok("a deep one has three", len(niches._rows_for(4.0)) == 3)
ok("a very shallow one has one", niches._rows_for(1.0) == ["front"])

head("the season warns rather than refusing, and says when")
closed = niches._window_closed(SITE, datetime.date(2027, 1, 20))
ok("January is inside the frost gap, across the new year", closed is not None,
   "this is the wrap that the first version got wrong")
ok("and it says when the next window opens", "Feb 13" in (closed[1] if closed
                                                          else ""))
ok("high summer is closed too", niches._window_closed(
    SITE, datetime.date(2027, 7, 15)) is not None)
ok("and it says that one is a rule of thumb, not a measurement",
   "rule of thumb" in niches._window_closed(
       SITE, datetime.date(2027, 7, 15))[0])
ok("October is open", niches._window_closed(
    SITE, datetime.date(2026, 10, 20)) is None)

head("a substitute is neither the pick nor something just turned down")
SLOT3 = {"id": "x", "count": [3, 3], "candidates": [
    plant("First", "part sun", 1.0), plant("Second", "part sun", 1.0),
    plant("Third", "part sun", 1.0)], "decisions": []}
ok("not the chosen plant",
   niches._substitute(SLOT3, "First", []) != "First")
ok("not a vetoed one",
   niches._substitute(SLOT3, "First", ["Second"]) == "Third")
ok("an explicit second choice is honoured",
   niches._substitute(SLOT3, "First", [], "Third") == "Third")
ok("unless it is the pick itself",
   niches._substitute(SLOT3, "First", [], "First") != "First")

head("photos: open licences only, and a plant without one is kept")
usable = niches._usable({"taxon_photos": [
    {"photo": {"medium_url": "https://static.inaturalist.org/x.jpg",
               "license_code": None, "attribution": "all rights reserved"}},
    {"photo": {"medium_url": f"https://{niches.OPEN_HOST}/y.jpg",
               "license_code": "cc-by-nc", "attribution": "(c) Someone"}},
    {"photo": {"medium_url": f"https://{niches.OPEN_HOST}/z.jpg",
               "license_code": "c", "attribution": "(c) Someone else"}},
]})
ok("the all-rights-reserved host is dropped", len(usable) == 1)
ok("as is a closed licence on the open host",
   all("z.jpg" not in p["url"] for p in usable))
ok("and the attribution is kept with the photo", usable[0]["attribution"])

head("nothing is final")
RO = {"series": niches.series_note(), "niches": [dict(BIG, slots=[dict(
    S2, id="border.front", candidates=[plant("Alpha", "part sun", 1.0),
                                       plant("Beta", "part sun", 1.0)],
    ruled_out=None,  # a slot written before anything was ever ruled out of it
    pick={"name": "Alpha", "count": 5, "chosen_by": "decided"})])]}
data, warned = niches.reopen("x", "border.front", "changed his mind", RO)
slot = data["niches"][0]["slots"][0]
ok("the pick is cleared", slot["pick"] is None)
ok("a null ruled_out does not crash it", slot["ruled_out"] == ["Alpha"])
ok("what was moved off is no longer recommended",
   niches._substitute(slot, None, slot["ruled_out"]) != "Alpha")
ok("but it stays on the slate, in case they decide it was fine",
   any(c["name"] == "Alpha" for c in slot["candidates"]))
ok("the reason is on the record with the reopening",
   slot["decisions"][-1]["by"] == "reopened"
   and slot["decisions"][-1]["why"] == "changed his mind")
ok("and the plant it moved off is named there too",
   slot["decisions"][-1]["was"] == "Alpha")
try:
    niches.reopen("x", "border.front", "", RO)
    ok("a reopening with no reason is refused", False)
except SystemExit as e:
    ok("a reopening with no reason is refused", "reason" in str(e).lower())

head("export says what it could not write, rather than a smaller number")
EX = {"series": niches.series_note(), "niches": [dict(BIG, slots=[
    dict(S2, id="border.front", candidates=[plant("Alpha", "part sun", 1.0)],
         pick={"name": "Alpha", "count": 5, "chosen_by": "decided"}),
    dict(S2, id="border.back", candidates=[plant("Beta", "part sun", 1.0)],
         pick=None),
    dict(S2, id="border.middle", candidates=[], pick=None),
    dict(S2, id="border.gone", candidates=[plant("Beta", "part sun", 1.0)],
         pick={"name": "Vanished", "count": 3, "chosen_by": "decided"}),
])]}
import lib.yards as _y  # noqa: E402

_real = _y.load
_y.load = lambda s, f: {"plants": []} if f == "design.json" else _real(s, f)
try:
    d, added, updated, waiting = niches.export("x", EX)
finally:
    _y.load = _real
ok("only the decided slot is written", added == 1 and updated == 0)
why = {sid: reason for sid, reason, _pending in waiting}
ok("all three of the others are named", len(waiting) == 3)
ok("an undecided slot with a slate says so",
   "nobody has chosen" in why["border.back"])
ok("a slot with no slate is distinguished from it",
   "no candidates researched" in why["border.middle"])
ok("a pick that has fallen off its own slate is reported, not skipped",
   "no longer on this slot's slate" in why["border.gone"])

head("the ballot says nothing about whose garden it is")
DATA = {"series": niches.series_note(), "niches": [dict(
    BIG, slots=[dict(S2, candidates=[plant("Alpha", "part sun", 1.0)],
                     recommended={"name": "Alpha", "because": "fits"})])]}
page = niches.ballot_html(DATA, "tok123")
ok("the title is neutral", niches.BALLOT_TITLE in page)
ok("no street name, no yard label",
   "cloverleaf" not in page.lower() and "austin" not in page.lower())
ok("a veto is a separate tick from not choosing", "__veto" in page)
ok("and it asks why", "__no" in page)

print(f"\n{PASS} of {PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
