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
COMMONEST_POT = "1gal"

# Units whose members are close enough substitutes that one's price says
# something about another's. See `item_class` for why the list is this short.
COMMENSURABLE_UNITS = frozenset(["cu ft", "packet"])


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


def _variants(address):
    """Progressively looser queries for one address, with how exact each is.

    Real supplier addresses fail against OpenStreetMap for dull reasons: a suite
    number the geocoder reads as part of the street, a venue name before the
    street line, `Farm to Market 1626` where the map says `FM 1626`, or a rural
    lane nobody has ever traced. Giving up on the first miss leaves the supplier
    with no distance at all, which is worse than a postcode-level fix — provided
    the postcode-level fix admits to being one."""
    a = " ".join(str(address or "").split())
    if not a:
        return
    seen = {a}
    yield a, "address"

    for pattern, repl in (
            (r",?\s*(?:suite|ste\.?|unit|apt\.?|bldg\.?|building|#)\s*[\w-]+", ""),
            (r"\bfarm[- ]to[- ]market\b", "FM")):
        alt = " ".join(re.sub(pattern, repl, a, flags=re.I).split()).strip(", ")
        if alt and alt not in seen:
            seen.add(alt)
            yield alt, "address"

    parts = [p.strip() for p in a.split(",") if p.strip()]
    # A leading venue name rather than a house number.
    if len(parts) > 2 and not re.match(r"^\d", parts[0]):
        alt = ", ".join(parts[1:])
        if alt not in seen:
            seen.add(alt)
            yield alt, "address"
    if len(parts) >= 2:
        alt = ", ".join(parts[-2:])
        if alt not in seen:
            yield alt, "locality"


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
            hit, precision, failed = None, None, None
            for query, level in _variants(addr):
                try:
                    hit = _geocode(query)
                except Exception as exc:                  # network, not logic
                    failed = f"geocode failed: {exc}"
                    break
                if hit:
                    precision = level
                    break
            if not hit:
                done.append((s.get("id"), None, failed or "address not found"))
                continue
            s["lat"], s["lon"] = round(hit["lat"], 6), round(hit["lon"], 6)
            s["geocoded"] = {"as_of": _today().isoformat(),
                             "matched": hit.get("display_name"),
                             "precision": precision}
        s["distance_mi"] = round(haversine_mi(ylat, ylon, s["lat"], s["lon"]), 1)
        level = (s.get("geocoded") or {}).get("precision") or "address"
        s["distance_from"] = (
            f"haversine to site.address, geocoded {_today().isoformat()}"
            + ("" if level == "address" else
               f", to the {level} only because the street would not resolve"))
        done.append((s.get("id"), s["distance_mi"],
                     None if level == "address" else f"{level}-level fix only"))
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


# ------------------------------------------------- moving a yard onto the board

def moves(slug, today=None):
    """Where the ranking disagrees with who this yard is currently buying from.

    A reassignment is proposed when a better-ranked supplier shares a category
    with the incumbent — the category test is what stops a plant order being
    moved to an irrigation trade counter because the counter reviews well.

    Ranked by risk rather than by size, because the dangerous move is not the
    expensive one. It is the one under a task that cannot slip. `gives_up` names
    what the yard was leaning on the old supplier for, which is the sentence
    somebody has to actually read: a shorter drive is a poor trade for a policy
    of holding paid orders for a week when the purchase has a three-day window.
    """
    tasks = yards.load(slug, "tasks.json") or {}
    board = rank(slug, today=today)
    ladder = board["ranked"] + board["mail"]
    pos = {a["id"]: i for i, a in enumerate(ladder)}
    by_id = {a["id"]: a for a in ladder}

    # Which dated tasks each shopping entry is holding up.
    needs = {}
    for t in tasks.get("tasks", []):
        for b in t.get("buy") or []:
            needs.setdefault(b, []).append(t)

    out, unranked = [], []
    for entry in tasks.get("shopping", []):
        sid = entry.get("supplier")
        if not sid:
            continue
        old = by_id.get(sid)
        if old is None:
            unranked.append({"shopping": entry.get("id"),
                             "item": entry.get("item"), "supplier": sid,
                             "why": "not on the board — unassessed, excluded, "
                                    "or absent from sourcing.json"})
            continue
        cats = set(old["categories"])
        better = [a for a in ladder
                  if pos[a["id"]] < pos[sid] and cats & set(a["categories"])]
        if not better:
            continue
        new = better[0]

        affected = needs.get(entry.get("id"), [])
        critical = [t for t in affected if t.get("critical")]
        gated = [t for t in affected if t.get("gate")]
        risk = (2 if critical else 0) + (1 if gated else 0)
        why_risk = []
        if critical:
            why_risk.append(f"{len(critical)} task"
                            f"{'s' if len(critical) > 1 else ''} marked critical")
        if gated:
            why_risk.append(f"{len(gated)} gated on a condition")
        if not affected:
            why_risk.append("no dated task depends on it")

        out.append({
            "shopping": entry.get("id"), "item": entry.get("item"),
            "from": sid, "from_name": old["name"],
            "to": new["id"], "to_name": new["name"],
            "risk": risk, "risk_why": "; ".join(why_risk),
            "why": (f"{new['name']} is {new['tier']} at "
                    f"{_dist(new)}, {old['name']} is {old['tier']} at "
                    f"{_dist(old)}"),
            "access": new.get("access") or [],
            "gives_up": (tasks.get("suppliers", {}).get(sid) or {}).get("note"),
            "tasks": [{"id": t["id"], "title": t.get("title"),
                       "date": t.get("date"), "critical": bool(t.get("critical")),
                       "gate": bool(t.get("gate"))} for t in affected],
        })

    out.sort(key=lambda m: (-m["risk"], -len(m["tasks"]), m["shopping"] or ""))
    return {"yard": slug, "moves": out, "unranked": unranked}


def _dist(a):
    d = a.get("distance_mi")
    return f"{d:g} mi" if d is not None else "mail order"


def apply_moves(slug, today=None, write=True):
    """Refresh the yard's supplier table from the record and act on the moves.

    Two things, because they are the same edit: the hand-typed distances in
    `tasks.json` are replaced by geocoded ones, and every shopping entry the
    ranking wants to move, moves."""
    data = load(slug)
    tasks = yards.load(slug, "tasks.json") or {}
    found = moves(slug, today)
    board = rank(slug, today=today)
    assessed = {a["id"]: a for a in board["ranked"] + board["mail"]}

    table = tasks.setdefault("suppliers", {})
    for sup in data["suppliers"]:
        sid = sup.get("id")
        row = table.setdefault(sid, {})
        row["name"] = sup.get("name") or row.get("name")
        for key in ("address", "phone", "hours"):
            if sup.get(key):
                row[key] = sup[key]
        if sup.get("distance_mi") is not None:
            row["distance_mi"] = sup["distance_mi"]
        elif assessed.get(sid, {}).get("reach") == "mail":
            row.pop("distance_mi", None)
        a = assessed.get(sid)
        row["rank"] = ({"tier": a["tier"], "reach": a["reach"],
                        "score": a["score"], "access": a["access"]} if a else
                       {"tier": None, "reach": "unassessed"})
        if sup.get("note"):
            row["note"] = sup["note"]

    by_shopping = {m["shopping"]: m for m in found["moves"]}
    for entry in tasks.get("shopping", []):
        m = by_shopping.get(entry.get("id"))
        if m:
            entry["supplier"] = m["to"]
    if write:
        yards.save(slug, "tasks.json", tasks)
    return found


# ----------------------------------------------------------- the price ladder

def _norm(item):
    s = str(item or "").strip().lower()
    s = re.sub(r"^plant:\s*", "", s)
    return re.sub(r"\s+", " ", s)


def normalize_size(size):
    """One spelling for a pot size, because a design and a price list rarely
    agree on it.

    `4 in`, `4in`, `4 inch` and `#1` are the same shelf. Left unnormalised they
    are four separate price classes, each with too little evidence to median,
    and every one of them falls through to a national guess. `#3` is the trade's
    own shorthand for a three-gallon."""
    s = re.sub(r"[\s._-]+", "", str(size or "").lower())
    if not s:
        return None
    m = re.fullmatch(r"#(\d+)", s)
    if m:
        return f"{m.group(1)}gal"
    m = re.fullmatch(r"(\d+)(?:in|inch|inches|\")", s)
    if m:
        return f"{m.group(1)}in"
    m = re.fullmatch(r"(\d+)(?:gal|gallon|gallons|g)", s)
    if m:
        return f"{m.group(1)}gal"
    return {"bb": "b&b", "b&b": "b&b", "balled": "b&b",
            "bareroot": "bare root", "seeds": "seed"}.get(s, s)


def pot_size(item):
    """The size a plant line is bought at, from `plant: Name (1gal)`."""
    m = re.search(r"\(([^()]*)\)\s*$", str(item or ""))
    return normalize_size(m.group(1)) if m else None


def item_class(item, unit):
    """The set of things whose prices are real evidence about this one, or None.

    Pot size for plants, because a 1-gallon perennial is a genuine price class in
    any given town. Bulk media by the cubic foot and seed by the packet likewise:
    within each, one is much like another.

    Deliberately nothing else. Sharing a unit is not sharing a price — a dripper
    and a trellis are both sold `each`, and taking their median priced eighteen
    cubic feet of mulch off a $459 fountain on the first real yard this ran
    against. An item outside these classes goes to the national ballpark, which
    is at least a curated list rather than an accident of what got quoted."""
    size = pot_size(item)
    if str(item or "").startswith("plant: ") or size in POT_SIZES:
        return f"plant {size or 'unsized'}"
    if unit in COMMENSURABLE_UNITS:
        return f"per {unit}"
    return None


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
    if want is None:
        return None
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


def _entries(defaults):
    """The priced entries in a price map, skipping its prose.

    A hand-written `local-prices.json` carries underscore-prefixed keys holding
    the research notes — where the figures came from, what the delivery finding
    was — beside the items. Anything reading the map by key never noticed; this
    module reads it by value, to take medians across a class."""
    return [v for v in (defaults or {}).values() if isinstance(v, dict)]


def _entry(defaults, item):
    got = (defaults or {}).get(item)
    return got if isinstance(got, dict) else {}


def _from_national(item, unit, defaults, plant_defaults):
    """The last rung, which must always return something.

    A known material takes its own ballpark. Anything else takes the median of
    the ballparks sharing its unit, which is thin evidence and prints as a wide
    range — but it is a number in the total rather than a hole in it."""
    size = pot_size(item)
    if str(item or "").startswith("plant: ") and plant_defaults:
        each = plant_defaults.get(size)
        if each is not None:
            basis = f"national ballpark for a {size} plant, not a local quote"
            return _national(each, basis)
        if plant_defaults.get(COMMONEST_POT) is None:
            return None
        # Not the median across sizes: those run from a seed packet to a balled
        # tree, so their middle is not an estimate of anything. The commonest
        # retail size is at least a shelf somebody has seen — and because this
        # is now a guess about the size as well as the price, the range covers
        # the neighbouring sizes rather than the figure.
        vals = sorted(float(v) for v in plant_defaults.values() if v)
        i = vals.index(float(plant_defaults[COMMONEST_POT]))
        return _national(
            plant_defaults[COMMONEST_POT],
            f"pot size {size!r} is not one this prices; treated as a "
            f"{COMMONEST_POT}, which is a guess about the size as well as the "
            f"price",
            low=vals[max(i - 1, 0)], high=vals[min(i + 1, len(vals) - 1)])

    each = _entry(defaults, item).get("unit_usd")
    if each is not None:
        return _national(float(each),
                         f"national ballpark for {item}, not a local quote")

    vals = sorted(float(v["unit_usd"]) for v in _entries(defaults)
                  if v.get("unit") == unit and v.get("unit_usd"))
    if not vals:
        return None
    # The range spans the whole basket rather than sitting ±40% around its
    # middle. Things sold by the same unit are not the same kind of thing, and a
    # narrow range around a figure with no basis is the more misleading of the
    # two errors available here: it reads as knowledge.
    return _national(statistics.median(vals),
                     f"nothing quoted and no ballpark for {item}; the middle of "
                     f"{len(vals)} prices on file sold by the {unit}, which run "
                     f"${vals[0]:,.2f} to ${vals[-1]:,.2f}. A figure of this "
                     f"kind says the line exists, not what it costs",
                     low=vals[0], high=vals[-1], n=len(vals))


def _national(each, basis, low=None, high=None, n=0):
    each = float(each)
    low = each if low is None else float(low)
    high = each if high is None else float(high)
    return {"usd": round(each, 2),
            "low": round(low * (1 - NATIONAL_SPREAD), 2),
            "high": round(high * (1 + NATIONAL_SPREAD), 2),
            "rung": "national", "firm": False, "n": n,
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
    bags = sorted(float(p["bag_usd"]) for p in _entries(defaults)
                  if p.get("bag_usd"))
    bulk = sorted(float(p["bulk_usd_per_yard"]) for p in _entries(defaults)
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

        placed = sup.get("lat") is not None and sup.get("lon") is not None
        if not placed and not (sup.get("mail_only") or sup.get("reach") == "mail"):
            out.append(f"{name}: no coordinate, so its distance is unknown and "
                       f"it cannot be placed. Run --geocode")
        elif (sup.get("geocoded") or {}).get("precision") == "locality":
            out.append(f"{name}: the street would not resolve, so its "
                       f"{sup.get('distance_mi')} mi is measured to the town "
                       f"rather than the door. Fine for ranking, wrong for a "
                       f"route")

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


def moves_report(found):
    """The moves, worst risk first. Printed as its own thing rather than left to
    be found among thirty otherwise routine changelog entries."""
    ms, un = found["moves"], found["unranked"]
    if not ms and not un:
        print(f"{found['yard']}: the ranking agrees with every supplier already "
              f"chosen")
        return
    if ms:
        risky = sum(1 for m in ms if m["risk"])
        print(f"{found['yard']} — {len(ms)} reassignment"
              f"{'s' if len(ms) > 1 else ''}, {risky} touching a task that "
              f"cannot slip. Read from the top.\n")
    for m in ms:
        mark = "!!" if m["risk"] >= 2 else ("! " if m["risk"] else "  ")
        print(f"{mark}  {m['shopping']}  {str(m['item'])[:48]:48s}")
        print(f"        {m['from_name']} -> {m['to_name']}")
        print(f"        {m['why']}")
        for r in m["access"]:
            print(f"        the new one also has: {r}")
        print(f"        risk: {m['risk_why']}")
        for t in m["tasks"]:
            flags = ", ".join([f for f, on in
                               (("critical", t["critical"]), ("gated", t["gate"]))
                               if on]) or "routine"
            print(f"          {t['id']} {t['date']} {str(t['title'])[:44]:44s} "
                  f"({flags})")
        if m["gives_up"]:
            print(f"        giving up: {m['gives_up']}")
        print()
    if un:
        print(f"  {len(un)} supplier assignment"
              f"{'s' if len(un) > 1 else ''} the board cannot speak to\n")
        for u in un:
            print(f"    {u['shopping']}  {u['supplier']}: {u['why']}")


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
    ap.add_argument("--moves", action="store_true",
                    help="where the ranking disagrees with tasks.json, "
                         "worst risk first")
    ap.add_argument("--apply-moves", action="store_true",
                    help="act on them, and refresh the supplier table with real "
                         "distances")
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

    if args.moves or args.apply_moves:
        found = (apply_moves(args.slug) if args.apply_moves
                 else moves(args.slug))
        if args.json:
            print(json.dumps(found, indent=2))
        else:
            moves_report(found)
            if args.apply_moves:
                print(f"  applied to tasks.json. Every move above needs a "
                      f"changelog entry: yard changelog {args.slug} --add")
        return

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
