#!/usr/bin/env python3
"""Run the whole plant-picking pipeline and hold it to its one promise.

    python3 tools/test_pipeline.py
    python3 tools/test_pipeline.py -v      print the objections in full

The promise is that everything reaching the ballot has already passed the
checks `lib.design` applies, so nobody can choose a plant and be told
afterwards it was never possible. `tools/test_niches.py` tests the pieces that
promise is built from. This tests the promise itself, end to end, because that
is a different thing: every bug found the first time this ran on real data was
an *integration* bug, where two defensible pieces disagreed about what they
were computing.

Those five are the reason this file exists, and each has a test here:

  the scorch bound      the slate checked that a bed had enough light and not
                        that it had too much, and offered a part-shade plant
                        for the brightest bed in a yard with a real summer
  container pH          a pot holds its own medium, and the soil check was
                        ruling pots by the yard's pH
  the per-row budget    each row was measured against the whole bed, so every
                        row passed alone and the bed was overplanted once they
                        were added up
  the count and the     the count stayed at the size class while the plant
  plant                 varied inside it, so picking the smaller of two
                        candidates quietly produced a sparse bed
  the export tally      export wrote sixteen plants, said seventeen, and said
                        nothing at all about the slot it had skipped

Both routes through are exercised — somebody choosing, and somebody declining
to — because they build `plants[]` by different paths and only one of them was
checked by hand.

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SLUG = "testyard-pipeline"
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
            for line in str(detail).splitlines():
                print(f"          {line}")


def head(t):
    print(f"\n{t}")


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
          "Nov", "Dec"]

# A yard with the three shapes that behave differently, and a bright bed and a
# dim one, because the interesting refusals happen at the extremes.
HOURS = {"sunny_border": 7.4, "shady_border": 3.1, "raised": 6.2, "pots": 5.4}

SITE = {
    "label": "scratch",
    "boundary": {"points": [[0, 0], [40, 0], [40, 30], [0, 30]]},
    "zones": {
        "sunny_border": {"x": [2, 22], "y": [2, 5], "area_sqft": 60.0,
                         "kind": "border", "usable_depth_ft": 3.5,
                         "style": "bed"},
        "shady_border": {"x": [2, 14], "y": [24, 26], "area_sqft": 24.0,
                         "kind": "border", "usable_depth_ft": 2.0,
                         "style": "bed"},
        "raised": {"x": [26, 34], "y": [10, 14], "area_sqft": 32.0,
                   "kind": "grid", "usable_depth_ft": 4.0, "style": "bed",
                   "squares": 32},
        "pots": {"x": [24, 27], "y": [2, 5], "area_sqft": 9.0,
                 "kind": "container", "style": "bed",
                 "containers": {"count": 3, "each_sqft": 3.0}},
    },
    "climate": {
        "zone": "8b",
        "heat": {"days_over_95f_per_year": 45.0},
        "frost_32f": {"first_fall": {"median": "Dec 1"},
                      "last_spring": {"median": "Mar 1"}},
    },
    "provenance": {f"zones.{z}.area_sqft": {"source": "measured",
                                            "date": "2026-01-01",
                                            "note": "scratch fixture"}
                   for z in HOURS},
}

CONDITIONS = {
    "soil": {"texture": "clay", "ph": 8.1, "drainage": "slow"},
    "water": {"hose_reaches": True, "irrigation": None},
    "person": {"maintenance_appetite": "low", "hours_per_week": 4},
    "tools": {},
    "inventory": {},
}

VISION = {"purpose": "a low-maintenance front garden",
          "style": ["native", "informal"], "dislikes": [], "musts": [],
          "target_date": "2027-04-01"}

SUN = {"by_zone_and_month": {
    z: {m: {"effective": h, "clear": h, "best_cell": h + 0.8}
        for m in MONTHS} for z, h in HOURS.items()}}


def plant(name, light, spread, height=2.0, **kw):
    p = {"name": name, "botanical": f"Genus {name.lower().replace(' ', '')}",
         "light": light, "water": "low", "mature_spread_ft": spread,
         "mature_height_ft": height, "native": True,
         "maintenance": "low", "source": "fixture"}
    p.update(kw)
    return p


# Deliberately includes the plants that SHOULD be refused, because a slate that
# only contains good candidates cannot show that the checks run at all.
SLATE = {
    "sunny_border.back": [
        plant("Tall Native", "full sun", 3.0, 5.0),
        plant("Tall Other", "full sun", 2.8, 4.5),
        plant("Shade Lover", "part shade", 2.5, 4.0),      # scorch
    ],
    "sunny_border.middle": [
        plant("Mid One", "full sun", 2.0, 3.0),
        plant("Mid Two", "full sun", 1.8, 2.5),
        plant("Acid Mid", "full sun", 1.9, 2.5, ph_range=[5.0, 6.0]),  # pH
    ],
    "sunny_border.front": [
        plant("Small One", "full sun", 1.2, 1.0),
        plant("Tiny One", "full sun", 0.7, 0.8),
        plant("Gritty", "full sun", 1.1, 1.0, soil_drainage="sharp"),  # drains
    ],
    "shady_border.back": [
        plant("Shade Tall", "part shade", 1.8, 3.0),
        plant("Shade Tall Two", "shade", 1.6, 2.8),
        plant("Sun Hog", "full sun", 1.5, 2.0),            # not enough light
    ],
    "shady_border.front": [
        plant("Shade Small", "part shade", 1.0, 0.8),
        plant("Shade Small Two", "shade", 1.1, 1.0),
        plant("Too Wide", "part shade", 3.5, 1.0),         # deeper than bed
    ],
    "raised.tall-end": [
        plant("Peas", "part sun", 0.5, 5.0, annual=True),
        plant("Beans", "part sun", 0.6, 6.0, annual=True),
    ],
    "raised.middle": [
        plant("Lettuce", "part sun", 0.6, 0.6, annual=True),
        plant("Parsley", "part sun", 0.8, 0.8, annual=True),
    ],
    "raised.colour-end": [
        plant("Calendula", "part sun", 0.9, 1.2, annual=True),
        plant("Nasturtium", "part sun", 1.0, 0.8, annual=True),
    ],
    "pots.pot1": [
        plant("Pot Acid", "part sun", 1.4, 3.0, ph_range=[5.0, 6.0]),
        plant("Pot Other", "part sun", 1.3, 2.8),
    ],
    "pots.pot2": [
        plant("Pot Two A", "part sun", 1.4, 3.0),
        plant("Pot Two B", "part sun", 1.2, 2.5),
    ],
    "pots.pot3": [
        plant("Pot Three A", "part sun", 1.3, 2.6),
        plant("Pot Three B", "part sun", 1.1, 2.2),
    ],
}


def build(root):
    """A yard on disk, with the sun model already run."""
    from lib import yards
    os.makedirs(os.path.join(root, SLUG), exist_ok=True)
    for name, blob in (("site.json", SITE), ("conditions.json", CONDITIONS),
                       ("vision.json", VISION), ("sun-hours.json", SUN),
                       ("design.json", {"plants": [], "hardscape": []}),
                       ("tasks.json", {"tasks": []})):
        yards.save(SLUG, name, blob)


def objections(data=None):
    """Every objection lib.design would raise about the exported design."""
    from lib import design, yards
    S, U = yards.load_site(SLUG), yards.load(SLUG, "sun-hours.json")
    C, V = yards.load_conditions(SLUG), yards.load_vision(SLUG)
    D = data or yards.load(SLUG, "design.json")
    out = []
    for p in D.get("plants") or []:
        out += design.check_light(p, U, S)
        out += design.check_soil(p, C, S)
        out += design.check_water(p, C, S)
    out += design.check_space(D, S, U)
    out += design.check_grouping(D)
    out += design.check_vision(D, V)
    return out


def show(objs):
    return "\n".join(f"[{o['level']}] {o['about']}: {o['say']}" for o in objs)


def pipeline(root, route):
    """derive -> capacity -> slate -> rank -> pick -> sync -> export."""
    from lib import niches, yards
    yards.save(SLUG, "design.json", {"plants": [], "hardscape": []})
    v = dict(VISION)
    yards.save(SLUG, "vision.json", v)

    data = niches.derive(SLUG)
    niches.save(SLUG, data)
    data = niches.capacity(SLUG)
    niches.save(SLUG, data)
    data, kept, refused = niches.slate(SLUG, SLATE)
    niches.save(SLUG, data)
    data, _ = niches.rank(SLUG)
    niches.save(SLUG, data)

    if route == "deferred":
        data, took = niches.recommend_all(SLUG)
        niches.save(SLUG, data)
    else:
        # A person choosing, and specifically NOT always the recommendation:
        # the second candidate wherever there is one. That is the case that
        # produced the sparse beds, because the second is often smaller.
        picks = {}
        for n in data["niches"]:
            for s in niches._slots(n):
                cs = s.get("candidates") or []
                if cs:
                    picks[s["id"]] = cs[min(1, len(cs) - 1)]["name"]
        data, *_ = niches.sync(SLUG, picks)
        niches.save(SLUG, data)

    d, added, updated, waiting = niches.export(SLUG)
    yards.save(SLUG, "design.json", d)
    return data, refused, d, waiting


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yard-pipeline-test-")
    os.environ["GARDEN_ROOT"] = root
    try:
        run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{PASS} of {PASS + FAIL} passed")
    return 1 if FAIL else 0


def run(root):
    from lib import design, niches, yards
    build(root)

    head("the pipeline runs on a yard it has never seen")
    data = niches.derive(SLUG)
    niches.save(SLUG, data)
    ok("every zone becomes at least one niche",
       len(data["niches"]) >= 4, [n["id"] for n in data["niches"]])
    ok("the light figure it used is on the record",
       bool(data.get("series", {}).get("why")))
    ok("a container niche does not inherit the yard's pH",
       all(n["soil"].get("ph") is None for n in data["niches"]
           if n["kind"] == "container"))
    ok("an in-ground niche does",
       all(n["soil"].get("ph") == 8.1 for n in data["niches"]
           if n["kind"] == "border"))

    data = niches.capacity(SLUG)
    niches.save(SLUG, data)
    slots = [s for n in data["niches"] for s in niches._slots(n)]
    ok("every niche is given slots", len(slots) >= 8, len(slots))
    def rows(prefix):
        return [s for n in data["niches"] if n["id"].startswith(prefix)
                for s in niches._slots(n) if not s.get("excluded")]
    ok("a 2 ft border gets fewer plantable rows than a 3.5 ft one",
       len(rows("shady")) < len(rows("sunny")),
       f"shady {[s['id'] for s in rows('shady')]}, "
       f"sunny {[s['id'] for s in rows('sunny')]}")
    ok("and the row it cannot hold says why, rather than looking unresearched",
       all("no " + s["layer"] in s["excluded"] or "not three" in s["excluded"]
           for n in data["niches"] for s in niches._slots(n)
           if s.get("excluded")))
    ok("every plantable border row carries the share it may spend",
       all(s.get("budget_share") for n in data["niches"]
           if n["kind"] == "border"
           for s in niches._slots(n) if not s.get("excluded")))
    shares = {}
    for n in data["niches"]:
        tot = sum(s.get("budget_share") or 0 for s in niches._slots(n))
        if tot:
            shares[n["id"]] = tot
    ok("and the shares within a bed do not exceed the whole bed",
       all(v <= 1.0001 for v in shares.values()), shares)

    head("the five refusals, each of which was once a bug")
    data, kept, refused = niches.slate(SLUG, SLATE)
    niches.save(SLUG, data)
    by_name = {name: why for _slot, name, why in refused}
    if verbose:
        for nm, why in by_name.items():
            print(f"        {nm}: {why}")
    ok("a part-shade plant is refused for the BRIGHTEST bed, not just the dim "
       "one", "scorch" in by_name.get("Shade Lover", ""),
       by_name.get("Shade Lover", "was not refused at all"))
    ok("a full-sun plant is refused for the dim bed",
       "Sun Hog" in by_name, by_name.get("Sun Hog", "was not refused"))
    ok("a plant wider than the bed is deep is refused",
       "nowhere for it to go" in by_name.get("Too Wide", ""),
       by_name.get("Too Wide", "was not refused"))
    ok("wrong pH is refused in the GROUND",
       "pH" in by_name.get("Acid Mid", ""),
       by_name.get("Acid Mid", "was not refused"))
    ok("sharp drainage in slow soil is refused",
       "drainage" in by_name.get("Gritty", ""),
       by_name.get("Gritty", "was not refused"))
    ok("but the same wrong pH is ACCEPTED in a pot, which has its own medium",
       "Pot Acid" not in by_name, by_name.get("Pot Acid"))
    ok("nothing good was refused",
       not [n for n in by_name if n in ("Tall Native", "Mid One", "Small One",
                                        "Shade Tall", "Shade Small", "Peas",
                                        "Lettuce", "Calendula")],
       {n: w for n, w in by_name.items()})

    data, how_many = niches.rank(SLUG)
    niches.save(SLUG, data)
    ranked = [s for n in data["niches"] for s in niches._slots(n)
              if s.get("candidates")]
    ok("every slot with candidates gets a recommendation",
       all(s.get("recommended") for s in ranked))
    ok("and the recommendation says why, in words",
       all(len((s["recommended"].get("because") or "")) > 20 for s in ranked))
    ok("no slot is left with a single choice",
       all(len(s["candidates"]) >= 2 for s in ranked),
       {s["id"]: len(s["candidates"]) for s in ranked
        if len(s["candidates"]) < 2})

    head("somebody chooses, and design has nothing to object to")
    data, refused, d, waiting = pipeline(root, "decided")
    objs = objections(d)
    ok("every plant written carries the slot it came from",
       all(p.get("from_slot") for p in d["plants"]))
    ok("and is recorded as chosen, not deferred",
       all(p.get("chosen_by") == "decided" for p in d["plants"]))
    ok("nothing was silently skipped",
       not [w for w in waiting if w[2]], waiting)
    ok("design raises no objection at all", not objs, show(objs))

    head("nobody chooses, and design still has nothing to object to")
    data, refused, d2, waiting2 = pipeline(root, "deferred")
    objs2 = objections(d2)
    ok("the plants are recorded as deferred, not as decisions",
       all(p.get("chosen_by") == "deferred" for p in d2["plants"]),
       {p["name"]: p.get("chosen_by") for p in d2["plants"]})
    ok("design raises no objection at all", not objs2, show(objs2))

    head("the count follows the plant, which is what keeps a bed from reading "
         "sparse")
    # The two routes pick differently on purpose. If the count were pinned to
    # the size class, the route that picks the smaller candidate would come out
    # thinner, and check_space would call it sparse.
    def cover(des, zone):
        area = SITE["zones"][zone]["area_sqft"]
        return sum(niches._footprint(float(p["mature_spread_ft"])) * p["count"]
                   for p in des["plants"] if p.get("zone") == zone) / area
    for zone in ("sunny_border", "shady_border"):
        a, b = cover(d, zone), cover(d2, zone)
        ok(f"{zone} lands inside the coverage band whichever route was taken",
           design.COVER_FLOOR <= a <= design.COVER_CEILING
           and design.COVER_FLOOR <= b <= design.COVER_CEILING,
           f"chosen {a:.2f}, deferred {b:.2f}, band "
           f"{design.COVER_FLOOR}-{design.COVER_CEILING}")
    picked = {p["from_slot"]: p for p in d["plants"]}
    deferred = {p["from_slot"]: p for p in d2["plants"]}
    differing = [s for s in picked if s in deferred
                 and picked[s]["name"] != deferred[s]["name"]]
    ok("the two routes really did choose different plants somewhere",
       differing, "otherwise the test above proves nothing")
    moved = [s for s in differing
             if picked[s]["count"] != deferred[s]["count"]
             and picked[s]["mature_spread_ft"]
             != deferred[s]["mature_spread_ft"]]
    ok("and where the plant differed in size, the count moved with it",
       moved, {s: (picked[s]["name"], picked[s]["count"],
                   deferred[s]["name"], deferred[s]["count"])
               for s in differing})

    head("export is answerable for what it did not write")
    data = niches.load(SLUG)
    # A border row specifically. Dropping a pot leaves a pot empty, which is
    # a different objection; the claim being tested is that a bed left short
    # of plants gets reported short.
    target = next(s for n in data["niches"] if n["kind"] == "border"
                  for s in niches._slots(n)
                  if s.get("pick") and s.get("candidates"))
    target["pick"] = None
    niches.save(SLUG, data)
    yards.save(SLUG, "design.json", {"plants": [], "hardscape": []})
    d3, added, updated, waiting3 = niches.export(SLUG)
    named = {sid: why for sid, why, _pending in waiting3}
    pending = {sid for sid, _w, pend in waiting3 if pend}
    ok("the undecided slot is named", target["id"] in named,
       list(named))
    ok("and it says nobody has chosen, not that it lacks candidates",
       "nobody has chosen" in named.get(target["id"], ""))
    ok("the tally counts what was written, not what exists",
       added == len(d3["plants"]), f"{added} added, {len(d3['plants'])} present")
    ok("it is counted as pending, not as a row the bed cannot hold",
       target["id"] in pending, sorted(pending))
    # The point of reporting it: the bed really is short now, and design says
    # so. A pipeline that hid the empty slot would leave somebody reading a
    # sparse-bed objection with no idea which slot caused it.
    short = [o for o in objections(d3) if "sparse" in o["say"]]
    ok("and design independently reports the bed it left short as sparse",
       short, [o["about"] for o in objections(d3)])

    head("the things a person actually reads")
    data, kept, refused = niches.slate(SLUG, SLATE)
    niches.save(SLUG, data)
    data, _ = niches.rank(SLUG)
    niches.save(SLUG, data)

    data, asked, skipped = niches.compositions(SLUG)
    niches.save(SLUG, data)
    big = [n for n in data["niches"] if n.get("compositions")]
    ok("an arrangement is offered for the bed big enough for it to matter",
       [n["id"] for n in big] == ["sunny_border"],
       [n["id"] for n in big])
    ok("and every bed passed over says why, in a sentence about that bed",
       all(reason and len(reason) > 20 for _n, reason in skipped),
       [(n["id"], r) for n, r in skipped])
    ok("a grid bed is passed over because squares are the arrangement",
       any("squares" in r for n, r in skipped if n["kind"] == "grid"))
    ok("and a small border because there is nothing to choose between",
       any("nothing to choose" in r or "one sensible answer" in r
           for n, r in skipped if n["kind"] == "border"))

    opts = big[0]["compositions"]["options"]
    ok("the options are real alternatives, not one dressed three ways",
       len({o["name"] for o in opts}) == len(opts) >= 3,
       [o["name"] for o in opts])
    ok("each says what it costs to keep, not only what it looks like",
       all(o.get("con") and o.get("pro") for o in opts))
    ok("and what it costs in plants, against the plain reading of the area",
       all("plants" in (o.get("roughly") or "") for o in opts))
    ok("one is recommended, with a reason referring to this person's hours",
       big[0]["compositions"]["recommended"].get("because"),
       big[0]["compositions"]["recommended"])
    ok("but nothing is chosen for them",
       big[0]["compositions"]["chosen"] is None)

    # `photos` needs the network, so it does not run here. What check should
    # therefore report is exactly one class of finding and no other, and it
    # should say the plants are still offered rather than dropped.
    bad = niches.check(SLUG)
    ok("with no photographs fetched, every finding is about photographs",
       bad and all("photograph" in why for _sid, why in bad),
       [w for _s, w in bad if "photograph" not in w])
    ok("and it says they are still offered, not dropped",
       all("still offered" in why for _sid, why in bad))

    # Give every candidate a photograph, as a successful fetch would, and the
    # board should then be clean. Doing it by hand keeps the test off the
    # network without letting the clean case go unchecked.
    lit = niches.load(SLUG)
    for n in lit["niches"]:
        for s in niches._slots(n):
            for c in s.get("candidates") or []:
                c["photos"] = [{"url": f"https://{niches.OPEN_HOST}/x.jpg",
                                "attribution": "(c) somebody",
                                "license_code": "cc-by"}]
    niches.save(SLUG, lit)
    ok("with photographs, the board checks clean", not niches.check(SLUG),
       niches.check(SLUG))

    # A slot with a single candidate is the failure --check exists for: a
    # ballot offering one option is not a choice, it is an announcement.
    thin = niches.load(SLUG)
    victim = next(s for n in thin["niches"] for s in niches._slots(n)
                  if len(s.get("candidates") or []) > 1)
    victim["candidates"] = victim["candidates"][:1]
    niches.save(SLUG, thin)
    bad = niches.check(SLUG)
    ok("and it flags a slot left with only one option",
       any(victim["id"] in str(b) for b in bad), bad)

    data, took = niches.recommend_all(SLUG)
    niches.save(SLUG, data)
    text = niches.review(SLUG)
    picks = [s["pick"]["name"] for n in niches.load(SLUG)["niches"]
             for s in niches._slots(n) if s.get("pick")]
    missing = [nm for nm in picks if nm not in text]
    ok("review names every plant that was picked", not missing, missing)
    ok("and says plainly that nobody looked at the alternatives",
       "nobody looked at the alternatives" in text,
       text[:300])
    ok("it also says what was NOT taken, so a decision can be second-guessed",
       "not taken" in text or "runner" in text or "instead" in text,
       text[:400])

    head("asking gates the expensive jobs, which is the point of asking")
    from lib import doubts
    # Re-slate first: the --check block above deliberately trimmed one slot to
    # a single candidate, and a card carrying one option is a different test.
    fresh, _kept, _ref = niches.slate(SLUG, SLATE)
    niches.save(SLUG, fresh)
    fresh, _ = niches.rank(SLUG)
    for n in fresh["niches"]:
        for s in niches._slots(n):
            s["pick"], s["decisions"], s["card"] = None, [], None
    niches.save(SLUG, fresh)
    for name in ("doubts.json", "all-clear.json"):
        yards.save(SLUG, name, {"cards": []} if "doubts" in name else {})

    fresh, filed = niches.ask(SLUG)
    niches.save(SLUG, fresh)
    ok("a card is filed for each slot with a real choice on it", filed,
       filed)
    board = yards.load(SLUG, "doubts.json") or {"cards": []}
    mine = [c for c in board["cards"] if c.get("kind") == "choice"]
    ok("they are choices, not facts — nobody can measure a preference",
       len(mine) == len(filed), f"{len(mine)} choice cards, {len(filed)} filed")
    ok("each blocks design, so it cannot be planned around silently",
       all("design" in (c.get("blocks") or []) for c in mine),
       [c.get("blocks") for c in mine])
    ok("and each carries its options rather than just a question",
       all(len(c.get("options") or []) >= 2 for c in mine),
       [len(c.get("options") or []) for c in mine])
    ok("every slot remembers the card it filed, so it can settle it later",
       all(s.get("card") for n in fresh["niches"]
           for s in niches._slots(n) if s.get("candidates")))
    try:
        doubts.gate(SLUG, "design")
        ok("design is now gated", False, "the gate let it through")
    except SystemExit as e:
        ok("design is now gated", "open" in str(e).lower() or mine)

    picks = {}
    for n in fresh["niches"]:
        for s in niches._slots(n):
            if s.get("candidates"):
                picks[s["id"]] = s["candidates"][0]["name"]
    fresh, *_ = niches.sync(SLUG, picks)
    niches.save(SLUG, fresh)
    board = yards.load(SLUG, "doubts.json") or {"cards": []}
    still = [c for c in board["cards"]
             if c.get("kind") == "choice" and c.get("status") != "settled"]
    ok("choosing settles the cards it filed, rather than leaving them open",
       not still, [c["id"] for c in still])
    settled = [c for c in board["cards"] if c.get("status") == "settled"]
    ok("and each records what was chosen, not just that something was",
       all(c.get("answer") for c in settled))
    # The whole point. A gate that still refuses after the person has done
    # exactly what it asked is a gate that teaches people to force past it,
    # and the fork card sat open through both routes until this test ran.
    open_now = [c for c in board["cards"]
                if c.get("status") == "open"
                and "design" in (c.get("blocks") or [])]
    ok("and design is no longer blocked by anything this stage filed",
       not open_now, [c["question"] for c in open_now])
    ok("the fork is settled as a decision, not as a deferral, because "
       "declining to choose is still choosing",
       any(c.get("question") == niches.FORK
           and c.get("settled_by") == "decided" for c in board["cards"]),
       [(c.get("status"), c.get("settled_by")) for c in board["cards"]
        if c.get("question") == niches.FORK])
    ok("the card a person reads does not say '1 plants' or '? ft'",
       not [c for c in board["cards"]
            if "1 plants" in (c.get("detail") or "")
            or "? ft" in (c.get("detail") or "")],
       [c.get("detail", "")[:60] for c in board["cards"]
        if "1 plants" in (c.get("detail") or "")
        or "? ft" in (c.get("detail") or "")])

    head("and the whole thing is revisable")
    data, refused, d, waiting = pipeline(root, "decided")
    slot = next(s for n in data["niches"] for s in niches._slots(n)
                if s.get("pick"))
    was = slot["pick"]["name"]
    data, warned = niches.reopen(SLUG, slot["id"],
                                 "he saw it in flower and changed his mind")
    niches.save(SLUG, data)
    again = niches.find(data, slot["id"])[1]
    ok("the pick is cleared", again["pick"] is None)
    ok("what was moved off is on the record", was in (again["ruled_out"] or []))
    data, _ = niches.rank(SLUG)
    niches.save(SLUG, data)
    again = niches.find(data, slot["id"])[1]
    ok("and it is not handed straight back as the recommendation",
       (again.get("recommended") or {}).get("name") != was,
       f"reopened away from {was}, offered {again.get('recommended')}")
    ok("but it is still on the slate, in case they decide it was fine",
       any(c["name"] == was for c in again["candidates"]))

    head("a canopy is judged against ground a canopy can occupy, roots "
         "against soil")
    # check_space sums mature SPREADS — canopy footprints — and used to compare
    # them against zone_areas, which nets off the river rock. So a bed with a
    # stone apron was called overplanted on the strength of its own hardscape,
    # while `canopy_overhang_ft` was honoured on the depth arm and ignored on
    # the area arm. Half the constraint used the allowance and half did not.
    from lib import design
    S = yards.load_site(SLUG)
    z = S["zones"]["sunny_border"]
    z["area_sqft"] = 40.0
    z["unplantable_sqft"] = 14.0
    z["usable_depth_ft"] = 2.2
    soil, _ = design.zone_areas(S)["sunny_border"], None
    ok("with no overhang declared, canopy room is just the soil",
       design.zone_canopy_room(S, "sunny_border", soil) == (soil, 0.0),
       design.zone_canopy_room(S, "sunny_border", soil))

    z["canopy_overhang_ft"] = 1.2
    room, allow = design.zone_canopy_room(S, "sunny_border", soil)
    ok("declaring an overhang adds room, and never more than the apron there is",
       room > soil and allow <= z["unplantable_sqft"],
       f"soil {soil:.1f}, room {room:.1f}, allowance {allow:.1f}, "
       f"apron {z['unplantable_sqft']}")

    z["canopy_overhang_ft"] = 99.0
    room2, allow2 = design.zone_canopy_room(S, "sunny_border", soil)
    ok("an absurd overhang is capped at the apron, not extrapolated past it",
       abs(allow2 - z["unplantable_sqft"]) < 1e-6,
       f"allowance {allow2:.2f} against a {z['unplantable_sqft']} sq ft apron")

    z["canopy_overhang_ft"] = 1.2
    plants = [{"name": "wide thing", "zone": "sunny_border", "count": 6,
               "mature_spread_ft": 3.0}]
    says = " ".join(o["say"] for o in
                    design.check_space({"plants": plants}, S, {}))
    ok("a bed passing only on the allowance says so, and still reports the "
       "ratio against soil alone",
       "lean out over the apron" in says and "against soil alone" in says,
       says or "(no objection raised at all)")
    ok("and it names where the roots actually are",
       "roots are all still" in says, says)


if __name__ == "__main__":
    sys.exit(main())
