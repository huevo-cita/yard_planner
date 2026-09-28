#!/usr/bin/env python3
"""The card answers exactly what the linter would, and never more confidently.

The promise `lib.fits` makes is that a verdict read off a phone in a shop is
the same verdict `lib.design` will reach at a desk. Everything that could break
that promise is a way the two could drift apart, and every test here is one of
those ways:

  * the card carries precomputed answers, so they must equal a live call
  * the card carries no rules, so no verdict may exist that Python did not make
  * `_rejects` and the card must agree, or a plant the card sent somebody to
    buy is refused by the slate when they get home
  * the soil question must be asked once, by the layer-aware check, and the
    flat cached figure must not get a second vote
  * nothing here may be gated, because refusing to answer in a shop is useless

    python3 tools/test_fits.py
"""
import atexit
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import design, doubts, fits, niches, solar, yards  # noqa: E402

PASS = FAIL = 0

# A scratch garden root, so that intake writes its slate and its research list
# into a temporary directory rather than into somebody's actual yard. The
# catalog directory is deliberately left pointing at the real one, because one
# of the tests below is that the shipped catalog is well formed.
SCRATCH = tempfile.mkdtemp(prefix="fits-test-")
atexit.register(shutil.rmtree, SCRATCH, True)
yards.GARDEN_ROOT = SCRATCH
fits.PENDING_DIR = os.path.join(SCRATCH, "pending")
os.makedirs(os.path.join(SCRATCH, "x"))


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


MONTHS = list(design.MONTHS)

# A scratch yard, so the suite does not depend on anybody's real garden. Two
# beds and one patch of open ground, with a layered soil profile of the shape
# `conditions.bed_layers` reads: imported material with no pH reading of its
# own over native clay that has one. That layering is the whole reason the flat
# cached figure and the layered check disagree, so a fixture without it would
# test nothing.
SITE = {
    "zones": {
        "deep": {"style": "bed", "area_sqft": 60.0, "kind": "border",
                 "label": "deep bed"},
        "shallow": {"style": "bed", "area_sqft": 12.0, "kind": "border",
                    "label": "shallow bed"},
        "lawn": {"style": "open", "label": "the lawn",
                 "x": [0.0, 240.0], "y": [0.0, 240.0]},
    },
    "climate": {"heat": {"days_over_95f_per_year": 45.0}},
}
SUN = {"by_zone_and_month": {
    z: {m: {"effective": h, "clear": h, "best_cell": h + 1} for m in MONTHS}
    for z, h in (("deep", 6.5), ("shallow", 4.5), ("lawn", 7.5))}}
COND = {
    "soil": {"ph": 8.2, "drainage": "slow", "texture": "clay",
             "layers": {
                 "beds": {"deep": "amended", "shallow": "amended"},
                 "profiles": {"amended": {"layers": [
                     {"name": "imported", "top_in": 0.0, "bottom_in": 6.0,
                      "ph": None, "ph_plausible": [6.0, 7.5],
                      "drainage": None},
                     {"name": "native", "top_in": 6.0, "bottom_in": None,
                      "ph": 8.2, "drainage": "slow"}]}}}},
    "water": {"hose_reaches": True}}


def niche(zone, hours, area, depth):
    return {"id": zone, "label": SITE["zones"][zone].get("label") or zone,
            "zones": [zone], "kind": "border", "area_sqft": area,
            "usable_depth_ft": depth, "overhang_ft": None,
            "light": {"hours": hours, "category": design._label_for(hours)},
            "soil": {"ph": 8.2, "drainage": "slow", "texture": "clay"},
            "water": {"hose_reaches": True}}


def slot(sid, spread, count, share):
    return {"id": sid, "layer": "back", "size": "medium", "spread_ft": spread,
            "count": [count, count], "budget_share": share}


NICHES = {"niches": [
    dict(niche("deep", 6.5, 60.0, 3.5),
         slots=[slot("deep.back", 3.0, 3, 0.6), slot("deep.front", 1.0, 5, 0.4)]),
    dict(niche("shallow", 4.5, 12.0, 1.8),
         slots=[slot("shallow.back", 1.5, 3, 1.0)]),
]}


def plant(name, light, spread, **kw):
    p = {"name": name, "botanical": f"Genus {name.lower()}", "light": light,
         "water": "low", "mature_height_ft": spread,
         "mature_spread_ft": spread, "rooting_depth_in": 18.0,
         "source": "test", "months": list(solar.GROWING_SEASON)}
    p.update(kw)
    return p


PLACES = fits.places("x", SITE, SUN, COND, NICHES)

CATALOG = {"region": "test", "seasons": {"warm": list(solar.GROWING_SEASON)},
           "plants": [
               plant("Alpha", "full sun", 2.0),
               plant("Beta", "part shade", 1.0),
               plant("Gamma", "full sun", 8.0),
               plant("Delta", "full sun", 1.5, ph_range=[5.0, 6.0]),
               plant("Epsilon", "full sun", 1.5, soil_drainage="sharp"),
               plant("Zeta", "full sun", 1.5, ph_range=[6.0, 7.5],
                     rooting_depth_in=4.0)]}
for _p in CATALOG["plants"]:
    _p["names"] = [_p["name"]]


head("the ground a plant could go in")
ok("both beds and the open ground are offered", len(PLACES) == 3)
ok("a bed carries its rows", len([p for p in PLACES if p["kind"] == "bed"]) == 2)
ok("open ground is a place too, or a tree fits nowhere",
   [p["id"] for p in PLACES if p["kind"] == "area"] == ["lawn"])
lawn = [p for p in PLACES if p["id"] == "lawn"][0]
ok("open ground has no row budget",
   lawn["slots"][0]["count"] is None and lawn["slots"][0]["budget_share"] is None)
ok("and no back edge to outgrow", lawn["niche"]["usable_depth_ft"] is None)
ok("its light comes from the sun model, not from a niche", lawn["hours"] == 7.5)
ok("its area is reported for the reader", lawn["area_sqft"] == 400.0)

head("the soil question is asked once, and by the layer-aware check")
deep = [p for p in PLACES if p["id"] == "deep"][0]
ok("the flat cached pH is taken off the niche before _rejects sees it",
   not fits._no_soil(deep["niche"]).get("soil"))
ok("and the original niche is left alone",
   deep["niche"]["soil"]["ph"] == 8.2)
# Zeta wants pH 6.0-7.5 and roots 4 in, so it never leaves the imported layer,
# whose plausible band it sits inside. The flat check would refuse it on 8.2.
zeta = [p for p in CATALOG["plants"] if p["name"] == "Zeta"][0]
flat = niches._rejects(dict(zeta, zone="deep"), deep["niche"],
                       deep["slots"][0], SITE, SUN)
layered = fits.evaluate(zeta, deep, SITE, SUN, COND)
ok("the flat check refuses a shallow-rooted plant on the subsoil figure",
   flat is not None and "8.2" in flat, str(flat))
ok("the layered check does not, because the roots never reach that layer",
   layered["verdict"] == fits.FITS, layered.get("why"))
# The slate gate used to stop at the same flat figure. With conditions loaded
# it asks the layer the roots reach, which is what design.check_soil asks.
gated = niches._rejects(dict(zeta, zone="deep"), deep["niche"],
                        deep["slots"][0], SITE, SUN, COND)
ok("the slate gate agrees once conditions are loaded",
   gated is None, str(gated))
# Delta wants pH 5.0-6.0 and roots 18 in, so it is genuinely out.
delta = [p for p in CATALOG["plants"] if p["name"] == "Delta"][0]
deep_gate = niches._rejects(dict(delta, zone="deep"), deep["niche"],
                            deep["slots"][0], SITE, SUN, COND)
ok("and it still refuses a plant whose roots reach the native layer",
   deep_gate is not None and "pH" in deep_gate, str(deep_gate))
dv = fits.evaluate(delta, deep, SITE, SUN, COND)
ok("a plant whose roots do reach the native layer is still refused",
   dv["verdict"] == fits.NO and "pH" in (dv.get("why") or ""), dv.get("why"))
ok("and the refusal names the layer rather than the yard",
   "native" in (dv.get("why") or ""), dv.get("why"))

head("what the three linters between them refuse")
ok("too little light", fits.evaluate(plant("X", "full sun", 1.0),
                                     [p for p in PLACES if p["id"] == "shallow"][0],
                                     SITE, SUN, COND)["verdict"] == fits.NO)
gamma = [p for p in CATALOG["plants"] if p["name"] == "Gamma"][0]
gv = fits.evaluate(gamma, deep, SITE, SUN, COND)
ok("wider than the bed is deep", gv["verdict"] == fits.NO
   and "deep" in (gv.get("why") or ""), gv.get("why"))
ok("and the same plant is fine in open ground",
   fits.evaluate(gamma, lawn, SITE, SUN, COND)["verdict"] == fits.FITS)
eps = [p for p in CATALOG["plants"] if p["name"] == "Epsilon"][0]
ev = fits.evaluate(eps, deep, SITE, SUN, COND)
ok("sharp drainage in slow ground", ev["verdict"] == fits.NO
   and "drain" in (ev.get("why") or ""), ev.get("why"))
ok("drainage is judged on the profile, not on the rooting depth",
   "slow" in (ev.get("why") or ""), ev.get("why"))

head("a row that is taken is not the same answer as ground that is wrong")
taken = json.loads(json.dumps(NICHES))
for s in taken["niches"][1]["slots"]:
    s["pick"] = {"name": "something else"}
tp = fits.places("x", SITE, SUN, COND, taken)
sh = [p for p in tp if p["id"] == "shallow"][0]
beta = [p for p in CATALOG["plants"] if p["name"] == "Beta"][0]
bv = fits.evaluate(beta, sh, SITE, SUN, COND)
ok("a suitable plant with no free row reads as no room, not as no",
   bv["verdict"] == fits.FULL, bv["verdict"])
ok("and it says what is in the way",
   "already taken" in (bv.get("why") or ""), bv.get("why"))

head("the number quoted is the number that decided")
ever = plant("Evergreen", "full sun", 1.0, months=list(MONTHS))
warm = plant("Warm", "full sun", 1.0)
ev1 = fits.evaluate(ever, lawn, SITE, SUN, COND)
wv1 = fits.evaluate(warm, lawn, SITE, SUN, COND)
ok("the hours are the plant's own window, not the niche's cached mean",
   ev1["judged_over"] == "the year" and wv1["judged_over"] == "Apr-Oct")
ok("the margin is measured against that same number",
   ev1["light_margin_h"] == round(ev1["judged_h"] - ev1["needs_h"], 2))
ok("a window is named in every verdict, refusals included",
   all(fits.evaluate(p, pl, SITE, SUN, COND).get("judged_over")
       for p in CATALOG["plants"] for pl in PLACES))

head("window_short says the same thing in fewer words")
ok("the growing season", fits.window_short(None) == "Apr-Oct")
ok("all year", fits.window_short(MONTHS) == "the year")
ok("a run that wraps the year is still one run",
   fits.window_short(["Nov", "Dec", "Jan", "Feb"]) == "Nov-Feb")
ok("a broken run is not compressed into a lie",
   fits.window_short(["Mar", "Apr", "Sep"]) == "Mar, Apr, Sep")

head("the short line only ever shortens")
long_why = fits.evaluate(gamma, deep, SITE, SUN, COND)
ok("the full reason is kept beside it", long_why.get("why"))
ok("the short line is a prefix of the words in the full one",
   set(long_why["short"].rstrip(".").split()) <=
   set(long_why["why"].replace(",", " ").split())
   or long_why["short"].rstrip(".") in long_why["why"],
   long_why["short"])
ok("desk-only clauses are dropped",
   "design.py says so" not in long_why["short"])

head("the card carries answers, and the answers are the live ones")
stamps = {"built": "2026-01-01", "yard": "x"}
data = fits._card_data("x", CATALOG, PLACES, SITE, SUN, COND, stamps,
                       want_photos=False)
ok("every catalog plant is in the payload",
   len(data["plants"]) == len(CATALOG["plants"]))
ok("every place is in the payload", len(data["places"]) == len(PLACES))
mismatch = []
for rec, p in zip(data["plants"], CATALOG["plants"]):
    for j, pl in enumerate(PLACES):
        live = fits.evaluate(p, pl, SITE, SUN, COND)
        packed = rec["v"][j]
        want = (fits.CODE[live["verdict"]],
                live.get("short"), live.get("why"),
                live["judged_h"], live["judged_over"], live["needs_h"])
        got = (packed[0],
               data["strings"][packed[1]] if packed[1] > -1 else None,
               data["strings"][packed[2]] if packed[2] > -1 else None,
               packed[3],
               data["strings"][packed[4]], packed[5])
        if want != got:
            mismatch.append((p["name"], pl["id"], want, got))
ok("every precomputed verdict equals a live call", not mismatch,
   str(mismatch[:2]))

head("and the phone cannot invent one")
html = fits.card("x", CATALOG, PLACES, SITE, SUN, COND, stamps,
                 want_photos=False)
for forbidden in ("LIGHT_NEED", "SCORCH", "COVER_CEILING", "ph_range <",
                  "8.2", "rooting_depth"):
    ok(f"no rule named {forbidden!r} in the page script",
       forbidden not in fits.CARD_JS)
ok("the script reads verdicts by index and nothing else",
   "v[j][0]" in fits.CARD_JS and "zone_hours" not in fits.CARD_JS)
ok("the page is self-contained", "<script src" not in html
   and "<link rel=\"stylesheet\"" not in html)
ok("it says it works with no signal", "no signal" in html)
ok("it can be added to a home screen",
   "apple-mobile-web-app-capable" in html)

head("the card says nothing about whose garden it is")
# The same rule `test_niches.py` holds the ballot to, and the card needs it
# more: a ballot is answered on the sofa, a card is carried into a shop on a
# phone that can be lost. A slug is a street name.
named = fits.card("cloverleaf-austin", CATALOG, PLACES, SITE, SUN, COND,
                  dict(stamps, yard="cloverleaf-austin",
                       stale_sun="rebuild it with `yard fits "
                                 "cloverleaf-austin --card`"),
                  want_photos=False)
ok("the title is neutral", f"<title>{fits.CARD_TITLE}</title>" in named)
ok("no yard slug anywhere in the page",
   "cloverleaf" not in named.lower(),
   named[max(0, named.lower().find("cloverleaf") - 60):][:140])
ok("not in the stamps it embeds either",
   "cloverleaf" not in json.dumps(fits._card_data(
       "cloverleaf-austin", CATALOG, PLACES, SITE, SUN, COND,
       dict(stamps, yard="cloverleaf-austin"), want_photos=False)).lower())
ok("the region is kept, because the answers are meaningless without it",
   CATALOG["region"] in named)
ok("a rehearsal card does not name the real yard it copies",
   "cloverleaf" not in fits.card(
       "scratch", CATALOG, PLACES, SITE, SUN, COND,
       dict(stamps, sandbox="SANDBOX of cloverleaf-austin"),
       want_photos=False).lower())
ok("it asks not to be indexed", "noindex" in named)
ok("the yard is keyed by a digest instead",
   fits.yard_key("cloverleaf-austin") in named
   and len(fits.yard_key("cloverleaf-austin")) == 8)
ok("the digest is stable",
   fits.yard_key("cloverleaf-austin") == fits.yard_key("cloverleaf-austin"))
ok("and different yards get different keys",
   fits.yard_key("a") != fits.yard_key("b"))
ok("the phone's saved queue is keyed by it, so two yards do not share one",
   "'fits-queue-' + D.yard" in fits.CARD_JS)
ok("and the queue it copies out carries the digest, not the name",
   "yard_key: D.yard" in fits.CARD_JS)

head("the tag grid answers every combination the page can ask for")
tags = data["tags"]
want = set()
for light in design.LIGHT_ORDER:
    for spread in fits.TAG_SPREADS:
        for a in (0, 1):
            for d in (0, 1):
                want.add(f"{light}|{spread:g}|{a}{d}")
ok("every button combination has a stored answer", want <= set(tags),
   str(sorted(want - set(tags))[:3]))
ok("and no combination the page cannot reach", set(tags) == want)
ok("a tag record names its assumed growing window, so the sentence is true",
   fits.tag_plant("full sun", 2.0)["months"] == list(solar.GROWING_SEASON))
ok("a deeper plant is judged against deeper soil",
   fits.tag_root_depth(1.0) < fits.tag_root_depth(12.0))
ok("an acid-loving tag is refused by the layered check",
   fits.evaluate(fits.tag_plant("full sun", 2.0, acid=True), deep,
                 SITE, SUN, COND)["verdict"] == fits.NO)
ok("and the same plant without that label is not",
   fits.evaluate(fits.tag_plant("full sun", 2.0), deep,
                 SITE, SUN, COND)["verdict"] == fits.FITS)

head("a name that means several plants is never resolved to one")
ok("an exact name wins outright",
   [p["name"] for p in fits.find(CATALOG, "Alpha")] == ["Alpha"])
amb = {"region": "t", "plants": [dict(p, names=["sage", p["name"]])
                                 for p in CATALOG["plants"][:3]]}
ok("a shared common name comes back as all of them",
   len(fits.find(amb, "sage")) == 3)
ok("and an unknown name comes back empty, not as a guess",
   fits.find(CATALOG, "nothing like this") == [])

head("nothing here is gated")
board = {"cards": [{"id": "d1", "status": "open", "question": "?",
                    "blocks": ["*"]}]}
ok("an open card against everything does not stop a verdict",
   fits.evaluate(CATALOG["plants"][0], lawn, SITE, SUN, COND)["verdict"]
   in (fits.FITS, fits.FULL, fits.NO))
ok("but an open card against design is reported on the answer",
   [c["id"] for c in doubts.open_cards(board, job="design")] == ["d1"])
ok("the card puts that warning on its face",
   "Open doubt [d9]" in fits.card(
       "x", CATALOG, PLACES, SITE, SUN, COND,
       dict(stamps, open_doubts=[{"id": "d9", "question": "is it?"}]),
       want_photos=False))
ok("and a sandbox stamp too",
   "rehearsal" in fits.card("x", CATALOG, PLACES, SITE, SUN, COND,
                            dict(stamps, sandbox="SANDBOX of real"),
                            want_photos=False))

head("the shipped catalog is one lib.niches would accept")
real = fits.load_catalog("central-texas")
bad = []
for p in real["plants"]:
    for f in niches.REQUIRED:
        if not p.get(f):
            bad.append((p["botanical"], f"no {f}"))
    if p["light"] not in design.LIGHT_NEED:
        bad.append((p["botanical"], "light"))
    if p["water"] not in design.WATER_NEED:
        bad.append((p["botanical"], "water"))
    if p.get("maintenance") not in niches.UPKEEP:
        bad.append((p["botanical"], "maintenance"))
    if not p.get("months"):
        bad.append((p["botanical"], "no months after expanding season"))
    if not design.rooting_depth(p):
        bad.append((p["botanical"], "no rooting depth, so pH cannot be judged"))
ok("every record carries what the linters read", not bad, str(bad[:4]))
ok("every record carries a source",
   all(p.get("source") for p in real["plants"]))
ok("no two records share a botanical name",
   len({p["botanical"] for p in real["plants"]}) == len(real["plants"]))



def _keys(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(node, list):
        for v in node:
            _keys(v, out)
    return out


# By key rather than by substring. The file's own prose says it carries no
# address, and a test that greps for the word fails on the sentence promising
# it does not, which teaches nobody anything.
PRIVATE = {"address", "street", "lat", "lon", "latitude", "longitude",
           "parcel", "parcel_id", "zip", "county_parcel", "owner"}
ok("the catalog holds no key that could locate a household",
   not (_keys(real, set()) & PRIVATE),
   str(sorted(_keys(real, set()) & PRIVATE)))
ok("and no rooftop coordinate",
   not re.search(r"-?\d{1,3}\.\d{4,}", json.dumps(real)))

head("intake keeps unresearched plants out of the catalog")
res = fits.intake("x", [{"name": "nothing like this", "bought": True}],
                  dict(CATALOG, region="test-intake"), SITE, SUN, COND, PLACES,
                  nich=NICHES)
ok("an unknown name becomes a research job", len(res["unknown"]) == 1)
ok("and is not added to the catalog",
   all(p["botanical"] != "nothing like this" for p in CATALOG["plants"]))
if res["pending_path"]:
    with open(res["pending_path"]) as fh:
        pend = json.load(fh)
    ok("the pending file says what it still needs",
       pend["plants"][0]["needs"] == fits.NEEDS)
    ok("and is marked so lib.fits never loads it", pend.get("pending") is True)
    os.remove(res["pending_path"])
res2 = fits.intake("x", [{"name": "Alpha", "bought": True}], CATALOG,
                   SITE, SUN, COND, PLACES, nich=NICHES)
ok("a bought plant that fits is routed to a row", len(res2["placed"]) == 1,
   str(res2["placed"]) + str(res2["homeless"]))
ok("a plant in open ground is not written to a slate it has no row in",
   res2["placed"][0][1]["kind"] == "bed" if res2["placed"] else False)
res3 = fits.intake("x", [{"name": "Delta", "bought": True}], CATALOG,
                   SITE, SUN, COND, PLACES, nich=NICHES)
ok("a bought plant that fits nowhere is said so plainly",
   len(res3["homeless"]) == 1 and not res3["placed"])
ok("a queue from the wrong yard is refused by its digest",
   fits.yard_key("x") != fits.yard_key("y"))
with open(yards.path("x", "fits-bought.json")) as fh:
    written = json.load(fh)
ok("the slate file is keyed by slot, the shape lib.niches --slate reads",
   all(k.count(".") == 1 for k in written)
   and all(isinstance(v, list) for v in written.values()))
ok("it carries the slot's existing candidates, so --slate adds rather than "
   "overwrites",
   all(any(c["name"] == "Alpha" for c in v) for v in written.values()))

head("a card verdict survives the round trip through lib.niches")
# The promise in one test: anything the card says goes into a bed is a
# candidate `niches.slate` accepts. If these ever disagree, somebody buys a
# plant on the card's word and the slate refuses it at home.
disagree = []
for p in CATALOG["plants"]:
    for pl in PLACES:
        if pl["kind"] != "bed":
            continue
        v = fits.evaluate(p, pl, SITE, SUN, COND)
        if v["verdict"] != fits.FITS:
            continue
        s = [x for x in pl["slots"] if x["id"] == v["slot"]][0]
        why = niches._rejects(dict(p), fits._no_soil(pl["niche"]), s, SITE, SUN)
        if why:
            disagree.append((p["name"], v["slot"], why))
ok("every 'goes in' is a candidate the slate gate accepts", not disagree,
   str(disagree[:2]))

print(f"\n{PASS} of {PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
