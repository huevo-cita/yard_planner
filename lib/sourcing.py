#!/usr/bin/env python3
"""Which suppliers, in what order, and what a thing costs when nobody publishes
a price.

    python3 -m lib.sourcing <slug>                  the ranked board
    python3 -m lib.sourcing <slug> --rank nursery   one category
    python3 -m lib.sourcing <slug> --geocode        real distances, from addresses
    python3 -m lib.sourcing <slug> --check          what the evidence is missing
    python3 -m lib.sourcing <slug> --price mulch    what it costs, and how we know

Four failures this exists to prevent.

**A supplier in the wrong city.** The sourcing brief used to be prose, so nothing
in code knew where the yard was. An Austin nursery in a Queens plan was a typo
nobody could catch. Here every supplier is geocoded and carries a real distance
to the yard's own coordinate, and one that lands outside the metro is reported
under `excluded` with the mileage — visible, rather than absent.

**Ranking by whoever answered the phone.** Reputation was recorded nowhere: no
rating, no review count, no thread, no date. A supplier now needs dated evidence
to be ranked at all. Without it, it lands in `unassessed`, which is the honest
description of a place nobody checked.

**A five-star shop with eight reviews.** Raw ratings reward obscurity. The rating
is shrunk toward the local mean by review volume, and then a supplier is tiered
on the *bottom* of its confidence interval rather than on the estimate. Both are
needed: shrinkage alone pulls an unrated shop toward whatever the neighbourhood
scores, so in a town full of good nurseries an unknown one inherits a good score
and lands in the top tier on no evidence. The confidence floor is what separates
"we know this is excellent" from "we know nothing, and around here that usually
turns out fine".

**A budget that gets smaller as it gets less certain.** An item nobody prices
locally used to be dropped from the total, which made the number look complete
and small at the same time. The ladder below always returns a figure, always
says which rung it came off, and the total carries the firm and estimated parts
separately.

The division of labour
----------------------
Judgement about a nursery needs a person or an agent reading reviews and forum
threads. Arithmetic over that judgement should be reproducible. So the
`sourcing-scout` subagent gathers dated evidence into `sourcing.json`, and every
rule that turns evidence into an order lives here where it can be argued with and
tested.

Every rating carries a `via` naming how it was obtained. That is the seam for a
later Google Places fetch: it is free at this volume but wants a billing account,
and it would only cover the ratings half, so it is not here yet.

Why this module does not import `lib.parcel`
--------------------------------------------
It wants exactly one function from it, `geocode`. Importing it would pull
`parcel` and `frame` into `lib.bom`'s import closure, and `lib.inputs` would then
— correctly — hold the bill of materials answerable for `obstructions` and
`frame`, which it does not read. Widening a job's all-clear to save twelve lines
is how an all-clear becomes something nobody reads. So the Nominatim call is
repeated here.
"""
import argparse
import datetime
import json
import math
import re
import statistics
import time
import urllib.parse
import urllib.request

from . import yards

FILENAME = "sourcing.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "yard-sourcing/1.0 (personal garden planning)"}

# How far is worth driving. Local is a stop on the way home; regional is a
# Saturday; past the metro radius a place is not a supplier, it is a holiday.
DEFAULT_RADII = {"local_mi": 30.0, "metro_mi": 60.0}

# The shrinkage prior. At 50, a shop needs about 150 reviews before three
# quarters of its own rating survives, which is roughly where a rating stops
# moving when the next twenty customers arrive.
PRIOR_WEIGHT = 50.0
PRIOR_MEAN_FALLBACK = 4.0

# Tiering happens on the bottom of the interval, not the estimate. Business
# ratings are bimodal — people arrive to rave or to complain — so the spread of
# individual reviews is wide, nearer 1.2 stars than the 0.5 an intuition about
# averages suggests. One sigma rather than two: at two, nothing under a few
# hundred reviews could ever reach the top tier, and most good independents in a
# given town have fewer than that.
RATING_SD = 1.2
CONFIDENCE_Z = 1.0

# Forum evidence can lift a shop nobody rates on Google. It cannot overturn a
# thousand reviews, so it saturates.
COMMUNITY_CAP = 0.3
SENTIMENT = {"positive": 1.0, "mixed": 0.0, "negative": -1.0}

# Access is deliberately worth a lot: a members-only preview at a sale that sells
# out in hours is the difference between getting the plants and not.
ACCESS_MEMBERSHIP = 0.4
ACCESS_SALE = 0.4
ACCESS_CAP = 0.8

# Absolute bands, not quantiles. A band that moves when a bad supplier is added
# to the file is not something anyone can reason about.
TIERS = [(4.5, "excellent"), (4.2, "good"), (3.8, "acceptable")]
LAST_TIER = "last resort"

EVIDENCE_STALE_DAYS = 365
QUOTE_STALE_DAYS = 180

# How much wider a national ballpark is than a local quote. Nothing measured this
# — it is a statement that a figure with no local evidence behind it should print
# as a range too loose to quote, which is the honest presentation of a guess.
NATIONAL_SPREAD = 0.4

EARTH_R_MI = 3958.8

# The sizes a plant is bought at, which are also its price classes. Kept here
# rather than imported from `lib.bom` so the ladder does not depend on the bill
# of materials; `tools/test_sourcing.py` checks the two still agree.
POT_SIZES = frozenset(["seed", "plug", "4in", "1gal", "3gal", "5gal", "7gal",
                       "15gal", "b&b"])


# ------------------------------------------------------------------ the record

def load(slug):
    data = yards.load(slug, FILENAME) or {}
    data.setdefault("suppliers", [])
    radii = dict(DEFAULT_RADII)
    radii.update(data.get("radius") or {})
    data["radius"] = radii
    return data


def save(slug, data):
    return yards.save(slug, FILENAME, data)


def supplier(data, sid):
    for s in data.get("suppliers", []):
        if s.get("id") == sid:
            return s
    return None


def _today(today=None):
    return today or datetime.date.today()


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _age_days(value, today=None):
    d = _date(value)
    return None if d is None else (_today(today) - d).days


# ------------------------------------------------------------------- geography

def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_MI * math.asin(math.sqrt(a))


def _geocode(address, limit=1):
    """Address to a coordinate, through Nominatim. See the module docstring for
    why this is not `lib.parcel.geocode`."""
    time.sleep(1.0)                       # Nominatim's published rate limit
    url = NOMINATIM + "?" + urllib.parse.urlencode(
        {"q": address, "format": "json", "limit": limit})
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as fh:
        res = json.load(fh)
    if not res:
        return None
    r = res[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]),
            "display_name": r.get("display_name")}


def geocode_suppliers(slug, write=True, force=False):
    """Fill in every supplier's coordinate and its distance to the yard.

    Replaces a hand-typed `distance_mi`, which is a number with no provenance and
    is wrong about as often as it is right."""
    data = load(slug)
    site = yards.load_site(slug)
    ylat, ylon = yards.latlon(site)
    done = []
    for s in data["suppliers"]:
        if s.get("lat") is None or s.get("lon") is None or force:
            addr = s.get("address")
            if not addr:
                done.append((s.get("id"), None, "no address on file"))
                continue
            try:
                hit = _geocode(addr)
            except Exception as exc:                      # network, not logic
                done.append((s.get("id"), None, f"geocode failed: {exc}"))
                continue
            if not hit:
                done.append((s.get("id"), None, "address not found"))
                continue
            s["lat"], s["lon"] = round(hit["lat"], 6), round(hit["lon"], 6)
            s["geocoded"] = {"as_of": _today().isoformat(),
                             "matched": hit.get("display_name")}
        s["distance_mi"] = round(haversine_mi(ylat, ylon, s["lat"], s["lon"]), 1)
        s["distance_from"] = ("haversine to site.address, geocoded "
                              f"{_today().isoformat()}")
        done.append((s.get("id"), s["distance_mi"], None))
    if write:
        save(slug, data)
    return done


def classify(sup, radii):
    """local, regional, mail, unplaced or excluded — and why.

    Mail order is a class, never an exclusion. Some things genuinely have no
    local source, and a rule that removed them would quietly delete the only way
    to buy them."""
    if sup.get("mail_only") or sup.get("reach") == "mail":
        return "mail", "mail order"
    d = sup.get("distance_mi")
    if d is None:
        return "unplaced", "no coordinate yet — run --geocode"
    if d <= radii["local_mi"]:
        return "local", f"{d:g} mi"
    if d <= radii["metro_mi"]:
        return "regional", f"{d:g} mi — a trip in its own right"
    if sup.get("ships"):
        return "mail", (f"{d:g} mi away, too far to drive, but it ships")
    return "excluded", (f"{d:g} mi from the yard, past the "
                        f"{radii['metro_mi']:g} mi metro radius")


# ------------------------------------------------------------------ reputation

def _rating_of(sup):
    """One rating and one volume for a supplier, across whatever platforms rated
    it. Weighted by count, because that is what the shrinkage will use."""
    revs = [r for r in (sup.get("reviews") or [])
            if r.get("rating") is not None and r.get("count")]
    if not revs:
        return None, 0.0
    v = sum(float(r["count"]) for r in revs)
    if v <= 0:
        return None, 0.0
    r = sum(float(x["rating"]) * float(x["count"]) for x in revs) / v
    return r, v


def prior_mean(data):
    """The mean rating across this yard's own candidates.

    A local mean rather than a global constant, because review cultures differ by
    trade and by city, and the shrinkage should pull an unknown shop toward what
    a shop around here normally scores."""
    vals = [r for r, _ in (_rating_of(s) for s in data.get("suppliers", []))
            if r is not None]
    return statistics.mean(vals) if vals else PRIOR_MEAN_FALLBACK


def shrunk_rating(sup, mean):
    r, v = _rating_of(sup)
    if r is None:
        return None
    return (v / (v + PRIOR_WEIGHT)) * r + (PRIOR_WEIGHT / (v + PRIOR_WEIGHT)) * mean


def confidence_floor(sup, mean):
    """The shrunk rating less one standard error — what the evidence will bear.

    Shrinkage alone is not enough. It pulls a shop with eight reviews toward the
    local mean, so where the local mean is high, knowing nothing about a place
    makes it look good. Tiering on the floor instead means a thin record cannot
    reach the top tier however flattering its eight reviews were, and a shop with
    nine hundred is barely penalised."""
    r = shrunk_rating(sup, mean)
    if r is None:
        return None
    _, v = _rating_of(sup)
    return r - CONFIDENCE_Z * RATING_SD / math.sqrt(max(v, 1.0))


def community_adjustment(sup):
    """What the local forums say, bounded so it can lift but not overturn."""
    cites = sup.get("community") or []
    scored = [SENTIMENT.get(str(c.get("sentiment", "")).lower())
              for c in cites]
    scored = [s for s in scored if s is not None]
    if not scored:
        return 0.0, []
    net = sum(scored)
    adj = COMMUNITY_CAP * math.tanh(net / 2.0)
    return adj, cites


def _window_overlaps(spec, start, end):
    """Does a `YYYY-MM-DD/YYYY-MM-DD` sale window touch the planning window."""
    if not spec:
        return False
    parts = str(spec).split("/")
    a = _date(parts[0])
    b = _date(parts[1]) if len(parts) > 1 else a
    if a is None or b is None:
        return False
    return a <= end and b >= start


def access_bonus(sup, start, end):
    """Memberships and sales, as a bounded bump that always says what it was for.

    Folding this invisibly into a score would make the ranking unarguable, which
    is the failure mode of every score anybody has ever ignored."""
    a = sup.get("access") or {}
    bonus, reasons = 0.0, []

    mem = a.get("membership")
    if mem:
        bits = []
        if mem.get("preview") or mem.get("first_pick"):
            bits.append("member preview")
        if mem.get("discount_pct"):
            bits.append(f"{float(mem['discount_pct']):g}% member discount")
        if mem.get("cost_usd") is not None:
            bits.append(f"${float(mem['cost_usd']):,.0f} a year")
        if not bits:
            bits.append("membership")
        bonus += ACCESS_MEMBERSHIP
        reasons.append(", ".join(bits))

    for sale in a.get("sales") or []:
        if not _window_overlaps(sale.get("window"), start, end):
            continue
        bits = [sale.get("name") or "sale"]
        if sale.get("window"):
            bits.append(str(sale["window"]).replace("/", " to "))
        if sale.get("discount_pct"):
            bits.append(f"{float(sale['discount_pct']):g}% off")
        if sale.get("member_preview"):
            bits.append("members in first")
        if sale.get("confidence"):
            bits.append(f"({sale['confidence']})")
        bonus += ACCESS_SALE
        reasons.append(" — ".join(bits[:2]) + (", " + ", ".join(bits[2:])
                                               if bits[2:] else ""))

    return min(bonus, ACCESS_CAP), reasons


def tier_of(score):
    for cut, name in TIERS:
        if score >= cut:
            return name
    return LAST_TIER


def _tier_index(name):
    names = [n for _, n in TIERS] + [LAST_TIER]
    return names.index(name)


def assess(sup, data, start, end, mean=None):
    """One supplier's score, with every component kept separate."""
    mean = prior_mean(data) if mean is None else mean
    reach, why_reach = classify(sup, data["radius"])
    rating = shrunk_rating(sup, mean)
    floor = confidence_floor(sup, mean)
    comm, cites = community_adjustment(sup)
    acc, acc_reasons = access_bonus(sup, start, end)

    raw, count = _rating_of(sup)
    out = {"id": sup.get("id"), "name": sup.get("name"),
           "categories": sup.get("categories") or [],
           "reach": reach, "reach_why": why_reach,
           "distance_mi": sup.get("distance_mi"),
           "rating": raw, "review_count": count or None,
           "reputation": None if rating is None else round(rating, 3),
           "confidence_floor": None if floor is None else round(floor, 3),
           "community_adjustment": round(comm, 3),
           "community_citations": len(cites),
           "access_bonus": round(acc, 3), "access": acc_reasons,
           "quotes": len(sup.get("quotes") or [])}

    # No dated evidence, no ranking. An empty board is not a good review, and
    # ranking on silence is how a place nobody checked ends up at the top.
    if rating is None and not cites:
        out["assessed"] = False
        out["why"] = "no dated rating and no forum evidence"
        return out

    # A supplier carried only by forum evidence has no interval to take a floor
    # of, so it sits at the local mean and rises or falls on what was said.
    base = floor if floor is not None else mean
    out["assessed"] = True
    out["quality"] = round(base + comm, 3)
    out["score"] = round(base + comm + acc, 3)
    out["quality_tier"] = tier_of(out["quality"])
    out["tier"] = tier_of(out["score"])
    if acc and out["tier"] != out["quality_tier"]:
        out["ranked_up"] = (f"{out['quality_tier']} on reputation, ranked up to "
                            f"{out['tier']} by access")
    return out


def rank(slug, category=None, today=None, months=6):
    """The board: ranked local and regional suppliers, mail order beside them,
    and everything that could not be ranked or could not be reached."""
    data = load(slug)
    start = _today(today)
    end = _plan_end(slug, start, months)
    mean = prior_mean(data)

    ranked, mail, unassessed, excluded = [], [], [], []
    for sup in data["suppliers"]:
        a = assess(sup, data, start, end, mean)
        if category and category not in a["categories"]:
            continue
        if a["reach"] == "excluded":
            excluded.append(a)
        elif not a["assessed"]:
            unassessed.append(a)
        elif a["reach"] == "mail":
            mail.append(a)
        else:
            ranked.append(a)

    # Distance is a tiebreak inside a tier, never across one. Blending the two
    # into a single number is what puts a mediocre shop two miles away above an
    # excellent one at twelve.
    def order(a):
        d = a.get("distance_mi")
        return (_tier_index(a["tier"]),
                d if d is not None else 9e9,
                -a["score"])

    ranked.sort(key=order)
    mail.sort(key=lambda a: (_tier_index(a["tier"]), -a["score"]))
    unassessed.sort(key=lambda a: a.get("name") or "")
    excluded.sort(key=lambda a: a.get("distance_mi") or 9e9)
    return {"yard": slug, "window": [start.isoformat(), end.isoformat()],
            "prior_mean": round(mean, 3), "radius": data["radius"],
            "ranked": ranked, "mail": mail,
            "unassessed": unassessed, "excluded": excluded}


def _plan_end(slug, start, months):
    """The planning window's far end, which is what makes a sale relevant."""
    tasks = yards.load(slug, "tasks.json") or {}
    target = _date(tasks.get("target_date"))
    if target and target > start:
        return target
    return start + datetime.timedelta(days=int(30.5 * months))


def best_for(slug, category=None, reach=("local", "regional"), today=None):
    """The top-ranked supplier for a category, or None. What a reassignment uses."""
    board = rank(slug, category, today)
    for a in board["ranked"]:
        if a["reach"] in reach:
            return a
    return None


# ----------------------------------------------------------- the price ladder

def _norm(item):
    s = str(item or "").strip().lower()
    s = re.sub(r"^plant:\s*", "", s)
    return re.sub(r"\s+", " ", s)


def pot_size(item):
    """The size a plant line is bought at, from `plant: Name (1gal)`."""
    m = re.search(r"\(([^()]*)\)\s*$", str(item or ""))
    return m.group(1).strip().lower() if m else None


def item_class(item, unit):
    """The set of things whose prices are evidence about this one.

    Pot size for plants, because a 1-gallon perennial is a real price class in
    any given town. Otherwise the unit, which is weaker — a paver and a trellis
    are both sold `each` — and the width of the resulting range says so."""
    size = pot_size(item)
    if str(item or "").startswith("plant: ") or size in POT_SIZES:
        return f"plant {size or 'unsized'}"
    return f"per {unit}"


def quotes_index(data, reaches=("local", "regional", "mail")):
    """Every quote in the file, keyed by normalised item name, carrying the reach
    of the supplier that gave it."""
    out = {}
    radii = data.get("radius") or DEFAULT_RADII
    for sup in data.get("suppliers", []):
        reach, _ = classify(sup, radii)
        if reach not in reaches:
            continue
        for q in sup.get("quotes") or []:
            if q.get("usd") is None or not q.get("item"):
                continue
            out.setdefault(_norm(q["item"]), []).append((sup, q, reach))
    return out


def _from_quotes(hits, order):
    """One or more real quotes for the exact item.

    Both rungs are firm: somebody published each of these numbers for this exact
    thing. With several, the median is the figure, the spread is reported, and
    the best-ranked shop carrying it is named with its own price — because the
    median is what to budget and that shop is where you would actually go."""
    usds = sorted(float(q["usd"]) for _, q, _r in hits)
    sup, q, _r = min(hits, key=lambda h: order.get(h[0].get("id"), 9e9))
    out = {"low": round(usds[0], 2), "high": round(usds[-1], 2),
           "firm": True, "n": len(usds),
           "supplier": sup.get("id"), "supplier_name": sup.get("name"),
           "as_of": q.get("as_of"), "url": q.get("url")}
    if len(usds) == 1:
        out.update({"usd": round(usds[0], 2), "rung": "published",
                    "basis": f"quoted by {sup.get('name')}"})
        return out
    out.update({"usd": round(statistics.median(usds), 2),
                "rung": "local median",
                "supplier_usd": round(float(q["usd"]), 2),
                "basis": (f"median of {len(usds)} local quotes, "
                          f"${usds[0]:,.2f}–${usds[-1]:,.2f}; "
                          f"{sup.get('name')} wants ${float(q['usd']):,.2f}")})
    return out


def _quote_class(q, unit):
    return q.get("class") or item_class(q.get("item"), q.get("unit") or unit)


def _from_class(item, unit, index):
    """Nobody quotes this item, but its class is quoted.

    Local and regional quotes first, because the point of the class median is
    that it is what this class costs *here*. A basket of mail-order prices is a
    different claim and is only used when there is nothing nearby to average."""
    want = item_class(item, unit)
    near, anywhere = [], []
    for hits in index.values():
        for _sup, q, reach in hits:
            if _quote_class(q, unit) != want:
                continue
            anywhere.append(float(q["usd"]))
            if reach in ("local", "regional"):
                near.append(float(q["usd"]))
    vals, where = (near, "local") if len(near) >= 2 else (anywhere, "mail-order")
    if len(vals) < 2:
        return None
    vals.sort()
    return {"usd": round(statistics.median(vals), 2),
            "low": round(vals[0], 2), "high": round(vals[-1], 2),
            "rung": "class median", "firm": False, "n": len(vals),
            "supplier": None, "supplier_name": None, "as_of": None, "url": None,
            "basis": (f"no quote for this item; median of {len(vals)} {where} "
                      f"'{want}' prices, ${vals[0]:,.2f}–${vals[-1]:,.2f}")}


def _from_national(item, unit, defaults, plant_defaults):
    """The last rung, which must always return something.

    A known material takes its own ballpark. Anything else takes the median of
    the ballparks sharing its unit, which is thin evidence and prints as a wide
    range — but it is a number in the total rather than a hole in it."""
    size = pot_size(item)
    if str(item or "").startswith("plant: ") and plant_defaults:
        each = plant_defaults.get(size)
        if each is None:
            vals = sorted(float(v) for v in plant_defaults.values() if v)
            each = statistics.median(vals) if vals else None
            basis = (f"no local evidence and no ballpark for a {size or 'plant'}; "
                     f"median of {len(vals)} national plant sizes")
        else:
            basis = f"national ballpark for a {size} plant, not a local quote"
        if each is None:
            return None
        return _national(each, basis)

    p = (defaults or {}).get(item) or {}
    each = p.get("unit_usd")
    if each is not None:
        return _national(float(each),
                         f"national ballpark for {item}, not a local quote")

    vals = sorted(float(v.get("unit_usd")) for v in (defaults or {}).values()
                  if v.get("unit") == unit and v.get("unit_usd"))
    if not vals:
        return None
    return _national(statistics.median(vals),
                     f"nothing local and no ballpark for {item}; median of "
                     f"{len(vals)} national prices sold by the {unit}")


def _national(each, basis):
    return {"usd": round(float(each), 2),
            "low": round(float(each) * (1 - NATIONAL_SPREAD), 2),
            "high": round(float(each) * (1 + NATIONAL_SPREAD), 2),
            "rung": "national", "firm": False, "n": 0,
            "supplier": None, "supplier_name": None, "as_of": None, "url": None,
            "basis": basis}


def price_for(item, unit, data=None, defaults=None, plant_defaults=None,
              index=None, order=None):
    """What one of these costs, and how we know.

    Four rungs, and no fifth. The first two are published prices for the exact
    item and count as firm; the last two are derived and count as estimated.
    There is deliberately no rung that returns nothing, because the rung that
    returned nothing is what used to make a line disappear from the total."""
    data = data or {"suppliers": [], "radius": dict(DEFAULT_RADII)}
    index = quotes_index(data) if index is None else index
    order = order or {}

    hits = index.get(_norm(item))
    if hits:
        return _from_quotes(hits, order)
    got = _from_class(item, unit, index)
    if got:
        return got
    return _from_national(item, unit, defaults, plant_defaults)


def rank_order(slug, today=None):
    """supplier id -> its position on the board, for picking between quotes."""
    try:
        board = rank(slug, today=today)
    except FileNotFoundError:
        return {}
    out = {}
    for i, a in enumerate(board["ranked"] + board["mail"]):
        out[a["id"]] = i
    return out


def bulk_estimate(item, defaults):
    """A bag and bulk rate for a cubic-foot material nobody has priced.

    `lib.bom` drops a bulk line whose material it has never heard of. Rather than
    lose it, synthesise a rate from the materials it does know and let the line
    through labelled as an estimate."""
    bags = sorted(float(p["bag_usd"]) for p in (defaults or {}).values()
                  if p.get("bag_usd"))
    bulk = sorted(float(p["bulk_usd_per_yard"]) for p in (defaults or {}).values()
                  if p.get("bulk_usd_per_yard"))
    if not bags and not bulk:
        return None
    out = {}
    if bags:
        out["bag_usd"] = round(statistics.median(bags), 2)
    if bulk:
        out["bulk_usd_per_yard"] = round(statistics.median(bulk), 2)
    out["note"] = (f"no price anywhere for {item}; the median of "
                   f"{max(len(bags), len(bulk))} known bulk materials, so treat "
                   f"the figure as an order of magnitude")
    return out


# ---------------------------------------------------------------- the checking

def check(slug, today=None):
    """What the evidence is missing. Noisy findings are worse than none, so this
    reports only what would change a ranking or a price."""
    data = load(slug)
    start = _today(today)
    out = []

    seen = {}
    for sup in data["suppliers"]:
        sid = sup.get("id")
        name = sup.get("name") or sid or "?"
        if not sid:
            out.append(f"a supplier named {name!r} has no id, so nothing can "
                       f"cite it")
        elif sid in seen:
            out.append(f"two suppliers share the id {sid!r}: {seen[sid]} and "
                       f"{name}")
        else:
            seen[sid] = name

        if sup.get("lat") is None or sup.get("lon") is None:
            out.append(f"{name}: no coordinate, so its distance is unknown and "
                       f"it cannot be placed. Run --geocode")

        rated = False
        for r in sup.get("reviews") or []:
            if r.get("rating") is None:
                continue
            rated = True
            if not r.get("count"):
                out.append(f"{name}: a {r.get('platform', '?')} rating of "
                           f"{r['rating']} with no review count, so it cannot be "
                           f"weighted and is being ignored")
            if not r.get("as_of"):
                out.append(f"{name}: a {r.get('platform', '?')} rating with no "
                           f"date")
            else:
                age = _age_days(r["as_of"], start)
                if age is not None and age > EVIDENCE_STALE_DAYS:
                    out.append(f"{name}: the {r.get('platform', '?')} rating is "
                               f"{age} days old")
            if not r.get("via"):
                out.append(f"{name}: a rating with no `via` saying how it was "
                           f"obtained")

        if not rated and not (sup.get("community") or []):
            out.append(f"{name}: no dated rating and no forum evidence, so it "
                       f"cannot be ranked at all")

        for c in sup.get("community") or []:
            if not c.get("url"):
                out.append(f"{name}: a {c.get('platform', 'forum')} citation "
                           f"with no url, which is an opinion with no source")

        vo = sup.get("verified_open") or {}
        if not vo.get("as_of"):
            out.append(f"{name}: nobody has confirmed it still trades. A closed "
                       f"nursery in a schedule costs somebody a Saturday")
        else:
            age = _age_days(vo["as_of"], start)
            if age is not None and age > EVIDENCE_STALE_DAYS:
                out.append(f"{name}: last confirmed open {age} days ago")

        for q in sup.get("quotes") or []:
            if q.get("usd") is None:
                continue
            age = _age_days(q.get("as_of"), start)
            if age is None:
                out.append(f"{name}: a quote for {q.get('item')} with no date, "
                           f"which is a number nobody can check")
            elif age > QUOTE_STALE_DAYS:
                out.append(f"{name}: the quote for {q.get('item')} is {age} days "
                           f"old")

        for sale in (sup.get("access") or {}).get("sales") or []:
            spec = str(sale.get("window") or "")
            end = _date(spec.split("/")[-1])
            if end and end < start:
                out.append(f"{name}: the {sale.get('name', 'sale')} window ended "
                           f"{start - end} ago and is still in the file")
    return out


# --------------------------------------------------------------- the reporting

def _line(a):
    bits = [f"{a['name'][:38]:38s}"]
    d = a.get("distance_mi")
    bits.append(f"{d:5.1f} mi" if d is not None else "   —   ")
    if a.get("assessed"):
        bits.append(f"{a['score']:5.2f}  {a['tier']:<12s}")
    else:
        bits.append(f"{'—':>5s}  {'unassessed':<12s}")
    return "  ".join(bits)


def report(slug, category=None, today=None):
    board = rank(slug, category, today)
    what = f" — {category}" if category else ""
    print(f"{slug} — suppliers{what}\n")
    print(f"  local within {board['radius']['local_mi']:g} mi, metro to "
          f"{board['radius']['metro_mi']:g} mi. Sales counted between "
          f"{board['window'][0]} and {board['window'][1]}.")
    print(f"  ratings shrunk toward {board['prior_mean']:.2f}, this yard's own "
          f"mean, at a prior of {PRIOR_WEIGHT:g} reviews.\n")

    if not any(board[k] for k in ("ranked", "mail", "unassessed", "excluded")):
        print("  nothing in sourcing.json yet. The sourcing-scout subagent "
              "fills it.")
        return board

    if board["ranked"]:
        print("  drive to these, best tier first and nearest within a tier\n")
        for a in board["ranked"]:
            print("    " + _line(a))
            if a.get("rating"):
                print(f"        {a['rating']:.1f} over {a['review_count']:,.0f} "
                      f"reviews, shrunk to {a['reputation']:.2f}, and "
                      f"{a['confidence_floor']:.2f} at the bottom of the interval"
                      + (f". {a['community_adjustment']:+.2f} from "
                         f"{a['community_citations']} forum citation"
                         f"{'s' if a['community_citations'] != 1 else ''}"
                         if a["community_citations"] else ""))
            if a.get("access"):
                print(f"        ranked up {a['access_bonus']:+.2f} for access: "
                      + "; ".join(a["access"]))
            if a.get("ranked_up"):
                print(f"        {a['ranked_up']}")

    if board["mail"]:
        print("\n  mail order — for what nothing local carries\n")
        for a in board["mail"]:
            print("    " + _line(a))

    if board["unassessed"]:
        print("\n  not ranked, because nobody checked them\n")
        for a in board["unassessed"]:
            print(f"    {a['name'][:38]:38s}  {a.get('why', '')}")

    if board["excluded"]:
        print("\n  not local to this yard\n")
        for a in board["excluded"]:
            print(f"    {a['name'][:38]:38s}  {a['reach_why']}")

    findings = check(slug, today)
    if findings:
        print(f"\n  {len(findings)} thing{'s' if len(findings) > 1 else ''} the "
              f"evidence is missing — run --check")
    return board


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--rank", metavar="CATEGORY",
                    help="only suppliers in this category")
    ap.add_argument("--geocode", action="store_true",
                    help="fill coordinates and real distances from addresses")
    ap.add_argument("--regeocode", action="store_true",
                    help="re-geocode even where a coordinate already exists")
    ap.add_argument("--check", action="store_true",
                    help="what the evidence is missing")
    ap.add_argument("--price", metavar="ITEM",
                    help="what this costs, and which rung it came off")
    ap.add_argument("--unit", default="each", help="the unit for --price")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.geocode or args.regeocode:
        for sid, dist, err in geocode_suppliers(args.slug, force=args.regeocode):
            if err:
                print(f"  {sid:16s} {err}")
            else:
                print(f"  {sid:16s} {dist:5.1f} mi")
        return

    if args.check:
        findings = check(args.slug)
        if not findings:
            print(f"{args.slug}: the sourcing evidence is complete and current")
            return
        print(f"{args.slug} — {len(findings)} finding"
              f"{'s' if len(findings) > 1 else ''}\n")
        for f in findings:
            print(f"  {f}")
        raise SystemExit(1)

    if args.price:
        from . import bom                       # only for its national ballparks
        data = load(args.slug)
        got = price_for(args.price, args.unit, data,
                        defaults=bom.PRICES, plant_defaults=bom.PLANT_PRICES,
                        order=rank_order(args.slug))
        print(json.dumps(got, indent=2))
        return

    if args.json:
        print(json.dumps(rank(args.slug, args.rank), indent=2))
        return
    report(args.slug, args.rank)


if __name__ == "__main__":
    main()
