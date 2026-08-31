#!/usr/bin/env python3
"""Prove the supplier ranking follows its stated rules, and that no line ever
leaves the bill.

    python3 tools/test_sourcing.py
    python3 tools/test_sourcing.py -v        show every check's detail

This repo tests its guardrails rather than asserting them — `test_gate.py` for
the doubt gate, `test_changelog.py` for the prose lint, `test_week.py` for the
calendar. Ranking is the fourth, and it needs testing for a particular reason:
every rule in it is one that an implementation can appear to follow while
quietly not. A ranking that puts the good shop first for the wrong reason looks
exactly like one that works.

The properties, each easy to pass by accident:

  locality holds       a supplier in another city is excluded and the exclusion
                       names the distance, however good its reviews are
  mail order survives  a mail-order house is ranked in its own list and can
                       still supply what nothing local carries. This is the rule
                       most likely to be broken by a well-meaning tightening of
                       the locality filter, and it would silently delete the
                       only source of half a plant list
  volume counts        5.0 from eight people does not outrank 4.7 from nine
                       hundred. Tested on the ordering, not on the arithmetic,
                       because shrinkage that moves the score without moving the
                       tier changes nothing
  silence is not good  a supplier nobody checked is unassessed, not ranked. The
                       failure this catches is subtle: shrinking toward a local
                       mean makes an unrated shop *average*, and where the local
                       average is excellent that reads as an endorsement
  distance is a        nearer wins inside a quality tier and never across one.
  tiebreak             Both halves are checked, because an implementation that
                       blends distance into the score passes the first
  access is named      a membership bump is applied and appears in words. A
                       bonus folded invisibly into a number is unarguable
  the ladder holds     an item nobody quotes is estimated from its price class
                       rather than priced at zero
  no line is lost      every requirement reaches the bill, firm and estimated
                       sum to the total, and an item nothing has ever heard of
                       still costs something. This is the regression that
                       matters most: the old code dropped it, and the total
                       looked complete while getting smaller

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SLUG = "testyard"

results = []          # (state, label, detail) — state in pass/FAIL
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    print(f"  {'ok  ' if state == 'pass' else 'FAIL'}  {label}")
    if detail and (state != "pass" or verbose):
        for line in str(detail).strip().splitlines():
            print(f"          {line}")


def ok(cond, label, detail=""):
    record("pass" if cond else "FAIL", label, "" if cond else detail)


# --------------------------------------------------------------- the fixture

# An Austin yard. The suppliers are shaped so that each rule has exactly one
# supplier whose placement depends on it, and getting the rule wrong reorders
# the board visibly rather than by a decimal.
SITE = {"yard": SLUG, "schema_version": 2,
        "address": {"street": "a street", "lat": 30.27, "lon": -97.70},
        "zones": {"bed a": {"area_sqft": 100}},
        "climate": {}, "boundary": {}, "frame": {}, "features": {},
        "obstructions": {}, "provenance": {}}

DESIGN = {"yard": SLUG,
          "plants": [
              # quoted by two local shops -> local median, firm
              {"name": "Big muhly", "zone": "bed a", "count": 3,
               "pot_size": "1gal"},
              # quoted by nobody, but 1gal is a quoted class -> class median
              {"name": "Fall aster", "zone": "bed a", "count": 5,
               "pot_size": "1gal"},
              # a size nothing local carries -> national ballpark
              {"name": "Live oak", "zone": "bed a", "count": 1,
               "pot_size": "15gal"},
              # nothing local carries it at all; mail order does
              {"name": "Yucca pallida", "zone": "bed a", "count": 2,
               "pot_size": "1gal"},
              # No pot size, because it is not sold in a pot. Left to the pot
              # ladder it becomes a one-gallon shrub at ten times the money.
              {"name": "Softneck garlic (cloves)", "zone": "bed a",
               "count": 10, "unit_price": 1.2},
          ],
          "hardscape": [
              # quoted outright -> published, firm
              {"kind": "still pond basin", "quantity": 1, "unit": "each"},
              # a cubic-foot material the ballpark has never heard of. This one
              # used to fall out of the bill entirely.
              {"kind": "raised bed", "quantity": 1, "unit": "each",
               "fill_cu_ft": 20, "fill_material": "moon dust"},
              # Free, and the design says so. A zero here has to survive being
              # read as "no figure given".
              {"kind": "toad abodes", "quantity": 2, "unit": "each",
               "cost_usd": 0},
          ],
          # an `each` item nothing anywhere knows about. Also used to vanish.
          "extra_materials": {"unobtanium": 4}}

CONDITIONS = {"yard": SLUG}

SUPPLIERS = {
    "yard": SLUG,
    "radius": {"local_mi": 30.0, "metro_mi": 60.0},
    "suppliers": [
        # Nearest of the excellent ones. Must come first.
        {"id": "near_good", "name": "Near Good", "categories": ["nursery"],
         "address": "near", "lat": 30.28, "lon": -97.71, "distance_mi": 1.0,
         "reviews": [{"platform": "google", "rating": 4.7, "count": 500,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"},
         "quotes": [{"item": "plant: Big muhly (1gal)", "usd": 14.0,
                     "as_of": "2026-08-01"},
                    {"item": "still pond basin", "usd": 25.48, "unit": "each",
                     "as_of": "2026-08-01"}]},
        # Excellent but further. Must come after near_good and before tiny.
        {"id": "far_excellent", "name": "Far Excellent",
         "categories": ["nursery"], "address": "far",
         "lat": 30.40, "lon": -97.85, "distance_mi": 12.0,
         "reviews": [{"platform": "google", "rating": 4.8, "count": 900,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"},
         "quotes": [{"item": "plant: Big muhly (1gal)", "usd": 16.0,
                     "as_of": "2026-08-01"}]},
        # Five stars, eight people, two miles away. Must not reach the top tier.
        {"id": "tiny", "name": "Tiny Five Star", "categories": ["nursery"],
         "address": "tiny", "lat": 30.29, "lon": -97.72, "distance_mi": 2.0,
         "reviews": [{"platform": "google", "rating": 5.0, "count": 8,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"}},
        # Good, not excellent, until the membership and the sale are counted.
        {"id": "sale_place", "name": "Botanic Garden",
         "categories": ["nursery"], "address": "garden",
         "lat": 30.35, "lon": -97.80, "distance_mi": 9.0,
         "reviews": [{"platform": "google", "rating": 4.3, "count": 600,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "access": {"membership": {"preview": True, "discount_pct": 10,
                                   "cost_usd": 60},
                    "sales": [{"name": "Fall native sale",
                               "window": "2026-09-25/2026-10-25",
                               "member_preview": True, "discount_pct": 10}]},
         "verified_open": {"as_of": "2026-08-01", "how": "site"}},
        # Mediocre and closest of all. Distance must not save it.
        {"id": "mediocre", "name": "Near Mediocre", "categories": ["nursery"],
         "address": "med", "lat": 30.275, "lon": -97.705, "distance_mi": 0.5,
         "reviews": [{"platform": "google", "rating": 3.9, "count": 400,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"}},
        # In Queens. Better reviewed than anything in Austin. Must be excluded.
        {"id": "wrongcity", "name": "Wrong City Nursery",
         "categories": ["nursery"], "address": "queens",
         "lat": 40.76, "lon": -73.92, "distance_mi": 1500.0,
         "reviews": [{"platform": "google", "rating": 4.9, "count": 500,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"}},
        # No shop to drive to, and the only source of one plant on the list.
        {"id": "mailco", "name": "Mail Order Co", "categories": ["nursery"],
         "mail_only": True,
         "reviews": [{"platform": "google", "rating": 4.6, "count": 300,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"},
         "quotes": [{"item": "plant: Yucca pallida (1gal)", "usd": 13.99,
                     "as_of": "2026-08-01"}]},
        # Far enough to be a holiday, but it ships. Must be mail, not excluded.
        {"id": "distant_shipper", "name": "Distant Shipper",
         "categories": ["nursery"], "address": "far away",
         "lat": 32.78, "lon": -96.80, "distance_mi": 180.0, "ships": True,
         "reviews": [{"platform": "google", "rating": 4.5, "count": 200,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"}},
        # The only irrigation counter. Nothing better-ranked shares its trade,
        # so no reassignment may ever take its orders.
        {"id": "drip", "name": "Drip Counter", "categories": ["irrigation"],
         "address": "trade", "lat": 30.29, "lon": -97.69, "distance_mi": 4.0,
         "reviews": [{"platform": "google", "rating": 4.0, "count": 150,
                      "as_of": "2026-08-01", "url": "u", "via": "web search"}],
         "verified_open": {"as_of": "2026-08-01", "how": "site"}},
        # Nobody looked this one up.
        {"id": "unchecked", "name": "Unchecked Place",
         "categories": ["nursery"], "address": "somewhere",
         "lat": 30.30, "lon": -97.73, "distance_mi": 3.0},
    ],
}

# Buying from the worst-ranked nursery on the board, so every nursery line has
# somewhere better to go and the question is only which moves are safe.
TASKS = {
    "yard": SLUG, "target_date": "2027-03-01",
    "suppliers": {
        "mediocre": {"name": "Near Mediocre", "distance_mi": 99,
                     "note": "holds paid orders for a week, which is the only "
                             "thing making the September window work"},
        "drip": {"name": "Drip Counter", "distance_mi": 99},
        "unchecked": {"name": "Unchecked Place", "distance_mi": 99},
    },
    # The critical purchase is deliberately given the last id, so that sorting
    # by risk and sorting by id disagree. With them in agreement, a build that
    # ignores risk entirely still comes back in the right order.
    "shopping": [
        {"id": "b01", "item": "Compost", "supplier": "mediocre"},
        {"id": "b02", "item": "Drip emitters", "supplier": "drip"},
        {"id": "b03", "item": "Broccoli transplants", "supplier": "mediocre"},
        {"id": "b04", "item": "A pot", "supplier": "unchecked"},
        {"id": "b05", "item": "Seed potatoes", "supplier": "mediocre",
         "pin": "the only shop in the county that sells certified seed stock"},
        # Two categories, one of which the better shop carries. Declaring only
        # `edibles` would leave an any-overlap test passing by luck, since it
        # does not overlap `nursery` either.
        {"id": "b06", "item": "Chard seedlings", "supplier": "mediocre",
         "category": ["nursery", "edibles"]},
    ],
    "tasks": [
        {"id": "t001", "date": "2026-10-01", "title": "Top up the beds",
         "gate": {"kind": "soil_temp", "below_f": 85}, "buy": ["b01"]},
        {"id": "t002", "date": "2026-09-20", "title": "Run the drip line",
         "where": {"supplier": "drip"}, "buy": ["b02"]},
        {"id": "t003", "date": "2026-09-19", "title": "Plant the broccoli",
         "critical": True, "where": {"supplier": "mediocre"}, "buy": ["b03"]},
        # Buys a line that moves, but is not a trip to the shop it moves off:
        # a call to the one supplier that publishes a part number, about one
        # item inside somebody else's order. It must be left alone.
        {"id": "t004", "date": "2026-09-18", "title": "Phone about the part number",
         "where": {"supplier": "drip"}, "buy": ["b03"]},
    ],
}

TODAY = None          # filled in from datetime once lib is importable


def make_yard(root):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    for name, obj in (("site.json", SITE), ("design.json", DESIGN),
                      ("conditions.json", CONDITIONS),
                      ("sourcing.json", SUPPLIERS), ("tasks.json", TASKS),
                      ("doubts.json", {"yard": SLUG, "doubts": []})):
        with open(os.path.join(d, name), "w") as f:
            json.dump(obj, f, indent=2)
    return d


def board_ids(board, key="ranked"):
    return [a["id"] for a in board[key]]


def find(board, key, sid):
    for a in board[key]:
        if a["id"] == sid:
            return a
    return None


def _tier_rank(name):
    return ["excellent", "good", "acceptable", "last resort"].index(name)


def quiet(fn, *a, **kw):
    """Run something that prints a gate warning, without the warning."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a, **kw)


# ------------------------------------------------------------------ the checks

def check_locality(sourcing):
    board = sourcing.rank(SLUG, today=TODAY)

    excluded = board_ids(board, "excluded")
    ok(excluded == ["wrongcity"],
       "a supplier in another city is excluded, however good its reviews",
       f"excluded: {excluded}")

    entry = find(board, "excluded", "wrongcity")
    ok(entry and "1500" in entry["reach_why"] and "metro" in entry["reach_why"],
       "the exclusion names the distance and the radius it broke",
       entry and entry["reach_why"])

    ok("wrongcity" not in board_ids(board),
       "and it does not also appear among the suppliers to drive to")


def check_mail(sourcing, bom):
    board = sourcing.rank(SLUG, today=TODAY)
    mail = board_ids(board, "mail")

    ok("mailco" in mail,
       "a mail-order house is ranked, in its own list", f"mail: {mail}")
    ok("mailco" not in board_ids(board),
       "and it does not compete with the shops you could drive to")

    ok("distant_shipper" in mail and
       "distant_shipper" not in board_ids(board, "excluded"),
       "a supplier too far to drive is mail order, not excluded, when it ships",
       f"mail: {mail}, excluded: {board_ids(board, 'excluded')}")

    # The rule that matters: mail order still supplies what nothing local has.
    src = sourcing.load(SLUG)
    got = sourcing.price_for("plant: Yucca pallida (1gal)", "each", src,
                             defaults=bom.PRICES,
                             plant_defaults=bom.PLANT_PRICES,
                             order=sourcing.rank_order(SLUG))
    ok(got["rung"] == "published" and got["supplier"] == "mailco"
       and abs(got["usd"] - 13.99) < 0.01,
       "and it prices an item nothing local carries",
       f"{got['rung']} ${got['usd']} from {got['supplier']}")


def check_volume(sourcing):
    board = sourcing.rank(SLUG, today=TODAY)
    ids = board_ids(board)
    tiny, far = find(board, "ranked", "tiny"), find(board, "ranked",
                                                    "far_excellent")

    ok(tiny["reputation"] < far["reputation"],
       "5.0 from eight people shrinks below 4.8 from nine hundred",
       f"tiny {tiny['reputation']} vs far_excellent {far['reputation']}")

    # The ordering, not the arithmetic. Shrinkage that moves the score without
    # moving the tier leaves distance in charge, and tiny is ten miles nearer.
    ok(ids.index("far_excellent") < ids.index("tiny"),
       "and it ranks below it, despite being ten miles nearer",
       f"order: {ids}")

    ok(tiny["tier"] != "excellent",
       "a thin record cannot reach the top tier on eight flattering reviews",
       f"tiny is {tiny['tier']} at {tiny['confidence_floor']}")


def check_unassessed(sourcing):
    board = sourcing.rank(SLUG, today=TODAY)
    ok(board_ids(board, "unassessed") == ["unchecked"],
       "a supplier with no dated evidence is not ranked",
       f"unassessed: {board_ids(board, 'unassessed')}")
    ok("unchecked" not in board_ids(board),
       "and it does not inherit the neighbourhood's good name")
    entry = find(board, "unassessed", "unchecked")
    ok(entry and "no dated rating" in entry["why"],
       "and the board says why", entry and entry.get("why"))


def check_tiebreak(sourcing):
    board = sourcing.rank(SLUG, today=TODAY)
    ids = board_ids(board)
    near = find(board, "ranked", "near_good")
    far = find(board, "ranked", "far_excellent")

    ok(near["tier"] == far["tier"] == "excellent",
       "two suppliers of the same quality tier, one near and one far",
       f"{near['tier']} / {far['tier']}")
    ok(ids.index("near_good") < ids.index("far_excellent"),
       "inside a tier, the nearer one wins", f"order: {ids}")

    # The other half. An implementation that blends distance into the score
    # passes the check above and fails this one.
    med = find(board, "ranked", "mediocre")
    ok(med["distance_mi"] < near["distance_mi"] and
       ids.index("mediocre") > ids.index("near_good"),
       "across tiers it does not: the closest shop of all still ranks last",
       f"mediocre at {med['distance_mi']} mi is {med['tier']}, order: {ids}")

    # Checked as a property of the whole list rather than of one pair, because a
    # blend with a small enough coefficient reorders nothing on any particular
    # fixture and passes every pairwise check written against it. Tier must never
    # go backwards, and distance must never go backwards within a tier.
    tiers = [a["tier"] for a in board["ranked"]]
    steps = [(tiers[i], board["ranked"][i]["distance_mi"],
              tiers[i + 1], board["ranked"][i + 1]["distance_mi"])
             for i in range(len(tiers) - 1)]
    bad = [s for s in steps
           if _tier_rank(s[0]) > _tier_rank(s[2])
           or (s[0] == s[2] and (s[1] or 0) > (s[3] or 0))]
    ok(not bad,
       "and the whole board reads as tier first, distance second, throughout",
       f"out of order: {bad}")


def check_access(sourcing):
    board = sourcing.rank(SLUG, today=TODAY)
    sale = find(board, "ranked", "sale_place")

    ok(sale["quality_tier"] == "good" and sale["tier"] == "excellent",
       "a membership and a dated sale move a supplier up a tier",
       f"{sale['quality_tier']} -> {sale['tier']}")
    ok(sale["access_bonus"] > 0 and sale["access"],
       "the bump is recorded", f"{sale['access_bonus']}: {sale['access']}")

    # Checked as two separate reasons rather than as keywords in one string:
    # the sale's own text mentions members getting in first, so a single
    # substring search for "member" passes with the membership reason deleted.
    reasons = sale["access"]
    ok(len(reasons) == 2
       and any("member discount" in r for r in reasons)
       and any("Fall native sale" in r for r in reasons),
       "and each bump says in words what it was for, separately",
       reasons)
    ok(sale.get("ranked_up") and "access" in sale["ranked_up"],
       "and the promotion itself is stated", sale.get("ranked_up"))

    # A sale outside the planning window is not a reason to drive anywhere.
    data = sourcing.load(SLUG)
    for s in data["suppliers"]:
        if s["id"] == "sale_place":
            s["access"]["sales"][0]["window"] = "2019-09-25/2019-10-25"
            s["access"].pop("membership")
    sourcing.save(SLUG, data)
    after = find(sourcing.rank(SLUG, today=TODAY), "ranked", "sale_place")
    ok(after["access_bonus"] == 0,
       "a sale that already happened earns nothing",
       f"bonus {after['access_bonus']}")
    sourcing.save(SLUG, json.loads(json.dumps(SUPPLIERS)))


def check_ladder(sourcing, bom):
    src = sourcing.load(SLUG)
    order = sourcing.rank_order(SLUG)

    def price(item, unit="each"):
        return sourcing.price_for(item, unit, src, defaults=bom.PRICES,
                                  plant_defaults=bom.PLANT_PRICES, order=order)

    one = price("still pond basin")
    ok(one["rung"] == "published" and one["firm"] and one["n"] == 1,
       "one quote for the exact item is a published price", one["basis"])

    two = price("plant: Big muhly (1gal)")
    ok(two["rung"] == "local median" and two["firm"]
       and abs(two["usd"] - 15.0) < 0.01
       and (two["low"], two["high"]) == (14.0, 16.0),
       "several quotes give the median, and the spread is reported",
       f"${two['usd']} over {two['low']}-{two['high']}")

    cls = price("plant: Fall aster (1gal)")
    ok(cls["rung"] == "class median" and not cls["firm"] and cls["usd"] > 0,
       "an item nobody quotes is estimated from its price class, not zeroed",
       cls["basis"])
    ok(cls["n"] >= 2 and "1gal" in cls["basis"],
       "and the estimate says how many comparables it rests on", cls["basis"])

    # The class median has to be local. A basket of mail-order prices is a
    # different claim, and 13.99 from mailco is not evidence about Austin.
    ok(abs(cls["usd"] - 15.0) < 0.01,
       "and it averages the local quotes rather than the mail-order one",
       f"${cls['usd']}, local quotes are 14 and 16, mail order is 13.99")

    nat = price("plant: Live oak (15gal)")
    ok(nat["rung"] == "national" and not nat["firm"] and nat["usd"] > 0,
       "a size nothing local carries falls to the national ballpark",
       nat["basis"])
    ok(nat["low"] < nat["usd"] < nat["high"],
       "which prints as a range too wide to quote",
       f"${nat['low']}-${nat['high']}")

    unknown = price("unobtanium")
    ok(unknown is not None and unknown["usd"] > 0,
       "and a thing nobody has ever heard of still gets a number",
       unknown and unknown["basis"])

    # A hand-written local-prices.json carries underscore-prefixed prose keys
    # beside the items. Reading the map by key never met them; taking a median
    # across its values does, and did, on the first real yard it was pointed at.
    prosey = {"_source": "sourcing research, Austin TX, 2026-08-30",
              "_delivery_finding": "bulk delivery never earns back its fee here",
              **bom.PRICES}
    try:
        got = sourcing.price_for("unobtanium", "each", src, defaults=prosey,
                                 plant_defaults=bom.PLANT_PRICES, order=order)
        crashed = None
    except Exception as exc:
        got, crashed = None, f"{type(exc).__name__}: {exc}"
    ok(got and got["usd"] > 0,
       "and a price file carrying research notes among its items does not "
       "bring the bill down", crashed)


def check_bill(bom, sourcing):
    need = quiet(bom.requirements, SLUG)
    bill = quiet(bom.net, SLUG, force=True)

    billed = {ln["item"] for ln in bill["lines"]}
    wanted = {k[len("plant: "):] if k.startswith("plant: ") else k
              for k in need}
    missing = sorted(wanted - billed)
    ok(not missing,
       f"every one of the {len(wanted)} requirements reaches the bill",
       f"lost: {missing}")

    ok(round(bill["firm_usd"] + bill["estimated_usd"], 2) == bill["total_usd"],
       "firm and estimated sum to the total",
       f"{bill['firm_usd']} + {bill['estimated_usd']} != {bill['total_usd']}")

    ok(bill["firm_usd"] > 0 and bill["estimated_usd"] > 0,
       "and both parts are non-zero on a yard that has some of each",
       f"firm {bill['firm_usd']}, estimated {bill['estimated_usd']}")

    ok(bill["low_usd"] <= bill["total_usd"] <= bill["high_usd"],
       "the total sits inside its own range",
       f"{bill['low_usd']} / {bill['total_usd']} / {bill['high_usd']}")

    by_item = {ln["item"]: ln for ln in bill["lines"]}

    # The regression this whole change exists for. Both of these were dropped by
    # the old code, and the total looked complete without them.
    ok(by_item.get("unobtanium") and by_item["unobtanium"]["usd"] > 0,
       "an item with no price anywhere costs something rather than vanishing",
       by_item.get("unobtanium"))
    ok(by_item.get("moon dust") and by_item["moon dust"]["usd"] > 0,
       "and so does a bulk material the ballpark has never heard of",
       by_item.get("moon dust"))

    ok(all("pricing" in ln for ln in bill["lines"]),
       "every line says which rung its price came off",
       [ln["item"] for ln in bill["lines"] if "pricing" not in ln])

    ok(not by_item["still pond basin"].get("estimated")
       and by_item["Fall aster (1gal)"].get("estimated"),
       "a quoted line is firm and a derived one is marked estimated")

    # A clove is not a shrub. The design is the only file that knows which of
    # its plants arrive in pots, and it says so with a price rather than a size.
    garlic = by_item.get("Softneck garlic (cloves) (1gal)") or {}
    ok(garlic.get("unit_usd") == 1.2,
       "a plant with no pot size is costed at the design's own figure",
       f"${garlic.get('unit_usd')}: {garlic.get('pricing', {}).get('basis')}")
    ok(garlic.get("estimated"),
       "and that figure is still an estimate, because nobody quoted it",
       garlic.get("pricing"))

    toads = by_item.get("toad abodes") or {}
    ok(toads.get("usd") == 0 and toads.get("high_usd") == 0,
       "a hardscape line the design costs at nothing costs nothing",
       f"${toads.get('usd')} up to ${toads.get('high_usd')}: "
       f"{toads.get('pricing', {}).get('basis')}")

    gaps = quiet(bom.price_gaps, SLUG, bom=bill)
    ok(gaps["gaps"] and gaps["gaps"] == sorted(
        gaps["gaps"], key=lambda g: -g["at_risk_usd"]),
       "the estimated lines come back ordered by dollars at risk",
       [(g["item"], g["at_risk_usd"]) for g in gaps["gaps"]])


def check_moves(sourcing, root):
    found = sourcing.moves(SLUG, today=TODAY)
    ids = [m["shopping"] for m in found["moves"]]

    ok("b02" not in ids,
       "an irrigation order is not reassigned to a better-reviewed nursery",
       f"proposed moves: {ids}")

    # `mediocre` and `near_good` are both tagged `nursery`, so an any-overlap
    # test hands the chard to a shop with no evidence of ever selling a
    # vegetable. What the line needs has to be carried in full.
    ok("b06" not in ids,
       "a line whose category the better shop does not carry stays where it is",
       f"proposed moves: {ids}")
    ok(set(ids) == {"b01", "b03"},
       "the two nursery orders at the worst-ranked shop both move",
       f"proposed moves: {ids}")

    ok(ids == ["b03", "b01"],
       "and the one under a critical task is read first, id order notwithstanding",
       f"order: {[(m['shopping'], m['risk']) for m in found['moves']]}")

    crit = found["moves"][0]
    ok(crit["risk"] > found["moves"][1]["risk"],
       "a critical task outranks a gated one",
       [(m["shopping"], m["risk"], m["risk_why"]) for m in found["moves"]])

    # The sentence somebody has to read. A shorter drive is a poor trade for a
    # week-long hold when the purchase has a three-day window.
    ok(crit["gives_up"] and "holds paid orders" in crit["gives_up"],
       "and the move names what the yard was leaning on the old supplier for",
       crit.get("gives_up"))
    ok(crit["tasks"] and crit["tasks"][0]["id"] == "t003"
       and crit["tasks"][0]["critical"],
       "and which dated task is affected", crit["tasks"])
    ok(crit["to"] == "near_good",
       "and it moves to the top of the board, not merely somewhere better",
       f"{crit['from']} -> {crit['to']}")

    ok([u["shopping"] for u in found["unranked"]] == ["b04"],
       "an order pointing at an unassessed supplier is reported, not moved",
       found["unranked"])

    # Reputation and distance are the only things this module can measure, and
    # they are not the only things that pick a supplier. Without this, the shop
    # that holds a paid order for a week loses the order to a shorter drive
    # every single time the board is re-run.
    held = {h["shopping"]: h for h in found["held"]}
    ok("b05" in held and "b05" not in ids,
       "a pinned order is held against the ranking rather than moved",
       f"held {list(held)}, moved {ids}")
    ok("certified seed stock" in (held.get("b05", {}).get("pin") or ""),
       "and the report carries the reason it was held", held.get("b05"))

    mute = json.loads(json.dumps(TASKS))
    for e in mute["shopping"]:
        if e["id"] == "b05":
            e["pin"] = "no"
    with open(os.path.join(root, SLUG, "tasks.json"), "w") as f:
        json.dump(mute, f, indent=2)
    try:
        sourcing.moves(SLUG, today=TODAY)
        refused = None
    except SystemExit as exc:
        refused = str(exc)
    ok(refused and "b05" in refused,
       "a pin with nothing worth disagreeing with is refused, and named",
       refused)
    with open(os.path.join(root, SLUG, "tasks.json"), "w") as f:
        json.dump(TASKS, f, indent=2)

    # And it actually writes.
    sourcing.apply_moves(SLUG, today=TODAY)
    after = json.load(open(os.path.join(root, SLUG, "tasks.json")))
    got = {e["id"]: e["supplier"] for e in after["shopping"]}
    ok(got["b01"] == "near_good" and got["b03"] == "near_good"
       and got["b02"] == "drip" and got["b04"] == "unchecked",
       "applying the moves rewrites exactly those assignments",
       got)
    # The order and the trip have to move together. A shopping entry reassigned
    # while the dated task still names the old shop sends somebody to the wrong
    # side of town on the right day.
    where = {t["id"]: (t.get("where") or {}).get("supplier") for t in after["tasks"]}
    ok(where.get("t003") == "near_good",
       "and the task that buys it is redirected to the same shop", where)
    ok(where.get("t002") == "drip",
       "while a task nobody moved keeps the shop it had", where)
    ok(where.get("t004") == "drip",
       "and a task that buys the moved line somewhere else on purpose is left "
       "where it is", where)

    ok(after["suppliers"]["drip"]["distance_mi"] == 4.0,
       "and the hand-typed distances are replaced by the geocoded ones",
       after["suppliers"]["drip"])
    ok(after["suppliers"]["mediocre"]["rank"]["tier"] == "acceptable",
       "and every supplier row carries the tier it was ranked at",
       after["suppliers"]["mediocre"].get("rank"))

    ok(not sourcing.moves(SLUG, today=TODAY)["moves"],
       "and running it again proposes nothing, because it has settled")

    with open(os.path.join(root, SLUG, "tasks.json"), "w") as f:
        json.dump(TASKS, f, indent=2)


def check_sizes(sourcing, bom):
    """A design and a price list rarely spell a pot size the same way."""
    want = {"4 in": "4in", "4in": "4in", "4 inch": "4in", "4 INCHES": "4in",
            "1 gal": "1gal", "1gal": "1gal", "1 gallon": "1gal", "#3": "3gal",
            "15 gal": "15gal", "B&B": "b&b", "bb": "b&b", "seeds": "seed",
            "plug": "plug", None: None, "": None}
    wrong = {k: sourcing.normalize_size(k) for k, v in want.items()
             if sourcing.normalize_size(k) != v}
    ok(not wrong, "every spelling of a pot size resolves to one price class",
       wrong)

    ok(all(sourcing.normalize_size(s) in sourcing.POT_SIZES
           for s in sourcing.POT_SIZES),
       "and the canonical spellings survive normalising unchanged")

    # The bug this was written for. `4 in` missed the ballpark table, so twelve
    # 4-inch violas were priced off a median that spanned seed to balled tree
    # and came to $456.
    small = sourcing.price_for("plant: Viola (4 in)", "each", {},
                               defaults=bom.PRICES,
                               plant_defaults=bom.PLANT_PRICES)
    ok(small["usd"] == bom.PLANT_PRICES["4in"],
       "a spaced pot size is priced as the shelf it actually is",
       f"${small['usd']} against ${bom.PLANT_PRICES['4in']}: {small['basis']}")

    odd = sourcing.price_for("plant: Something (bare root)", "each", {},
                             defaults=bom.PRICES,
                             plant_defaults=bom.PLANT_PRICES)
    ok(odd and odd["usd"] == bom.PLANT_PRICES[sourcing.COMMONEST_POT]
       and "guess about the size" in odd["basis"],
       "and a size nothing recognises says so rather than averaging a seed "
       "packet against a balled tree", odd and odd["basis"])


def check_agreement(sourcing, bom):
    """The two modules keep one list of pot sizes between them."""
    ok(set(bom.PLANT_PRICES) == set(sourcing.POT_SIZES),
       "lib.sourcing and lib.bom agree on what sizes a plant is sold in",
       f"only in bom: {sorted(set(bom.PLANT_PRICES) - set(sourcing.POT_SIZES))}, "
       f"only in sourcing: {sorted(set(sourcing.POT_SIZES) - set(bom.PLANT_PRICES))}")
    ok(sourcing.COMMONEST_POT in bom.PLANT_PRICES,
       "and on the size an unrecognised one falls back to")


def check_evidence(sourcing):
    """--check is the thing that keeps the file honest, so it has to fire."""
    findings = " | ".join(sourcing.check(SLUG, today=TODAY))
    ok("Unchecked Place" in findings,
       "the checker names the supplier nobody looked up", findings)

    data = sourcing.load(SLUG)
    for s in data["suppliers"]:
        if s["id"] == "near_good":
            s["reviews"][0].pop("count")
            s["reviews"][0].pop("via")
    sourcing.save(SLUG, data)
    findings = " | ".join(sourcing.check(SLUG, today=TODAY))
    ok("cannot be weighted" in findings,
       "a rating with no review count is reported, not quietly averaged in",
       findings)
    ok("`via`" in findings,
       "and so is one that does not say how it was obtained", findings)

    board = sourcing.rank(SLUG, today=TODAY)
    ok(find(board, "unassessed", "near_good") is not None,
       "an unweightable rating leaves the supplier unassessed rather than ranked")
    sourcing.save(SLUG, json.loads(json.dumps(SUPPLIERS)))


def main():
    global verbose, TODAY
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yard-sourcing-test-")
    os.environ["GARDEN_ROOT"] = root
    for mod in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[mod]
    import datetime
    from lib import bom, sourcing
    TODAY = datetime.date(2026, 8, 31)

    print("lib.sourcing — does the ranking follow its own rules\n")
    try:
        make_yard(root)
        print(" locality")
        check_locality(sourcing)
        print("\n mail order")
        check_mail(sourcing, bom)
        print("\n review volume")
        check_volume(sourcing)
        print("\n silence")
        check_unassessed(sourcing)
        print("\n distance")
        check_tiebreak(sourcing)
        print("\n access")
        check_access(sourcing)
        print("\n the price ladder")
        check_ladder(sourcing, bom)
        print("\n the bill")
        check_bill(bom, sourcing)
        print("\n the moves")
        check_moves(sourcing, root)
        print("\n the evidence check")
        check_evidence(sourcing)
        print("\n pot sizes")
        check_sizes(sourcing, bom)
        print("\n drift")
        check_agreement(sourcing, bom)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nThe ranking is not following its rules:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
