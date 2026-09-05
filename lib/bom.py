#!/usr/bin/env python3
"""What has to be bought, after subtracting what is already in the garage.

    python3 -m lib.bom <slug>                  the netted list and the total
    python3 -m lib.bom <slug> --cut            what to drop to fit the budget
    python3 -m lib.bom <slug> --prices p.json  local prices from sourcing-scout

Three things this exists to prevent.

**Buying what is already here.** Every unrecorded bag of compost is a bag bought
twice. `conditions.json` knows what is on site, so the requirement is netted
against it before anything is priced. This is the entire reason the conditions
stage exists.

**Bags when bulk is cheaper, and bulk when it is not.** The received wisdom is
that bulk wins above about a cubic yard. With a delivery fee it does not: at $75
delivered, the crossover is two cubic yards for compost and over three for mulch,
because the fee has to be earned back at roughly a dollar a cubic foot of saving.
So the crossover is computed per material from the actual numbers, including the
yard's minimum order, and `--crossover` prints it. Where delivery is free or the
person hauls it themselves, the folk rule is right again.

**A total that arrives as a surprise.** The cut list is produced at the same time
as the total, ordered by what the vision said mattered least, so the conversation
is about which things to drop rather than about whether the number is right.

Prices, and the line that used to disappear
-------------------------------------------
The defaults are national ballpark figures and are labelled as such wherever they
are printed. They exist so a plan has a number before anyone drives anywhere, not
so that number can be quoted. Real prices come from the `sourcing-scout` subagent
into `sourcing.json`, and `--prices` still overrides per item.

An item nobody had priced used to be flagged `unpriced` and left out of the
total. The flag was honest and the total was not: it looked complete, and it got
smaller the less anyone knew. On one real yard that hid about a third of the
plant list. Now every line goes through `lib.sourcing.price_for`, which returns a
figure from one of four rungs — a local quote, the median of several, the median
of the item's price class, or the national ballpark — and never returns nothing.
The total then carries `firm_usd` and `estimated_usd` separately, plus the range,
so the uncertainty is visible instead of being subtracted.

Volume, and the thing everyone gets wrong
-----------------------------------------
Bulk material is sold by the cubic yard and bags by the cubic foot, and there are
27 cubic feet in a cubic yard. Mulch and compost also settle: a three-inch layer
wants closer to three and a half inches of loose material delivered. Both are
handled here, and both are why hand-estimates come up short.
"""
import argparse
import json
import math

from . import (conditions as cond_mod, doubts, sourcing,
               vision as vision_mod, yards)

CU_FT_PER_YARD = 27.0
SETTLE = 1.15                     # loose material settles about this much
BAG_CU_FT = 2.0                   # the usual bag of mulch or compost

# National ballpark, 2026. Every one of these is overridden by --prices.
PRICES = {
    "compost":            {"bag_usd": 6.00, "bulk_usd_per_yard": 45.0},
    "topsoil":            {"bag_usd": 5.00, "bulk_usd_per_yard": 30.0},
    "garden soil":        {"bag_usd": 7.00, "bulk_usd_per_yard": 55.0},
    "mulch":              {"bag_usd": 4.50, "bulk_usd_per_yard": 38.0},
    "wood chips":         {"bag_usd": 4.00, "bulk_usd_per_yard": 0.0,
                           "note": "often free from a tree service or the city"},
    "gravel":             {"bag_usd": 6.00, "bulk_usd_per_yard": 60.0},
    "decomposed granite": {"bag_usd": 8.00, "bulk_usd_per_yard": 65.0},
    "sand":               {"bag_usd": 5.00, "bulk_usd_per_yard": 40.0},
    "edging":             {"unit_usd": 3.50, "unit": "linear ft"},
    "landscape fabric":   {"unit_usd": 0.35, "unit": "sq ft"},
    "cardboard":          {"unit_usd": 0.0, "unit": "sq ft",
                           "note": "free; ask any appliance shop"},
    "lumber":             {"unit_usd": 4.00, "unit": "linear ft"},
    "pavers":             {"unit_usd": 3.00, "unit": "each"},
    "block":              {"unit_usd": 4.00, "unit": "each"},
    "flagstone":          {"unit_usd": 6.00, "unit": "sq ft"},
    "drip line":          {"unit_usd": 0.55, "unit": "linear ft"},
    "emitters":           {"unit_usd": 0.75, "unit": "each"},
    "stakes":             {"unit_usd": 2.50, "unit": "each"},
    "trellis":            {"unit_usd": 25.0, "unit": "each"},
    "pots":               {"unit_usd": 18.0, "unit": "each"},
    "seed":               {"unit_usd": 3.50, "unit": "packet"},
}

# What a plant costs, by the size it is bought at.
PLANT_PRICES = {"seed": 3.50, "plug": 4.00, "4in": 6.00, "1gal": 14.00,
                "3gal": 38.00, "5gal": 60.00, "7gal": 95.00, "15gal": 180.00,
                "b&b": 350.00}
DEFAULT_POT = "1gal"

DELIVERY = {"usd": 75.0, "minimum_yards": 1.0,
            "note": "typical; ask, because it varies more than the material does"}


def line(item, qty, unit, usd, why=None, have=0.0, optional=False):
    ln = {"item": item, "quantity": round(qty, 2), "unit": unit,
          "usd": round(usd, 2)}
    if have:
        ln["already_on_hand"] = round(have, 2)
    if why:
        ln["why"] = why
    if optional:
        ln["optional"] = True
    return ln


# ------------------------------------------------------------------ quantities

def mulch_volume(area_sqft, depth_in=3.0):
    """Cubic feet of loose material for a finished depth, allowing for settling."""
    return area_sqft * (depth_in / 12.0) * SETTLE


def bed_fill_volume(length_ft, width_ft, depth_in):
    return length_ft * width_ft * (depth_in / 12.0) * SETTLE


CAVEATS = "_caveats"     # reserved key on `need`; never a purchasable line


def mulched(site):
    """Zones asking to be mulched, whether or not the design has planted them.

    Everything else here is scoped to the zones the design puts a plant in,
    which is right for compost and for plant counts and wrong for exactly one
    case: a bed that exists, is edged, is being weeded this month and has no
    entry in the plant list yet. g05 on cloverleaf-austin was in neither of the
    two mulch figures d9 was arguing between, and the reason was structural
    rather than an oversight — no plants, so no zone, so no mulch.

    Declaring `mulch_topoff_in` on a zone is a statement that this bed gets
    mulch, which is a thing a person knows before the planting is designed. It
    is the declaration and not the bed's existence that brings it in, so a lawn
    or a gravel court cannot arrive here by accident.
    """
    return {k for k, z in (site.get("zones") or {}).items()
            if isinstance(z, dict) and z.get("mulch_topoff_in")}


def _caveat(need, say):
    need.setdefault(CAVEATS, []).append(say)


def requirements(slug, mulch_depth_in=3.0, compost_depth_in=2.0):
    """Everything the design implies, before netting against what is on site.

    Anything this could not work out is recorded under `CAVEATS` rather than
    left out. A quantity that silently does not appear reads as a cheaper job,
    which is the one direction a bill of materials must never be wrong in.
    """
    site = yards.load(slug, "site.json") or {}
    design = yards.load(slug, "design.json") or {}
    need = {}

    def add(item, qty, unit, why):
        e = need.setdefault(item, {"quantity": 0.0, "unit": unit, "why": []})
        e["quantity"] += qty
        if why not in e["why"]:
            e["why"].append(why)

    from .design import resolve_site_zone, zone_areas
    areas = zone_areas(site)
    planted = {p.get("zone") for p in design.get("plants", []) if p.get("zone")}

    # A zone with no area recorded used to be skipped in silence, which is why
    # a yard whose zones carried no `area_sqft` produced a bill of materials
    # with no mulch and no compost on it at all — a shorter list reads as a
    # cheaper job rather than as an unanswered question. Uncheckable zones are
    # collected and reported on the record instead.
    #
    # `no_mulch` is the other half of it. Mulch is not wanted everywhere: a
    # self-sown seed bank cannot push through three inches of it, and a bed
    # whose whole front edge is a bluebonnet strip needs that stated on the
    # zone rather than subtracted from the total by hand afterwards.
    # Mulch and compost are declared independently, because a bed can want one
    # and not the other and usually does. A square-foot vegetable bed is
    # composted every turnover and never mulched; a container is neither.
    unpriced = []
    excluded = {"mulch": [], "compost": []}
    mulch_only = mulched(site) - planted
    for zone in sorted(planted | mulch_only):
        key = resolve_site_zone(site, zone) or zone
        z = (site.get("zones") or {}).get(key) or {}
        a = areas.get(key)
        if not a:
            unpriced.append(zone)
            continue
        # A bed that states its own top-off depth gets that instead of the
        # standard mulching depth. `mulch_depth_in` is what a bed wants when it
        # is bare, and on a yard where the owner has already spread three to six
        # inches of bought soil and mulch it is not what any bed wants: it costed
        # 33.1 cu ft of mulch for ground that needed a scatter, and then added
        # the nine bags he had said he would buy on top of it.
        for item, depth, verb in (("mulch",
                                   z.get("mulch_topoff_in") or mulch_depth_in,
                                   "topped off at" if z.get("mulch_topoff_in")
                                   else "at"),
                                  ("compost", compost_depth_in,
                                   "topdressed at")):
            # A bed that is here only because it asked for mulch gets mulch and
            # nothing else. Composting an undesigned bed is a different decision
            # from topping its mulch off, and quietly making it would have grown
            # the compost figure by a fifth on the way past.
            if item != "mulch" and zone in mulch_only:
                continue
            off = z.get(f"no_{item}")
            if off:
                excluded[item].append(f"{zone} — {off}" if isinstance(off, str)
                                      else zone)
                continue
            area = float(a) - float(z.get(f"no_{item}_sqft") or 0)
            if area <= 0:
                excluded[item].append(zone)
                continue
            less = ("" if abs(area - float(a)) < 0.05 else
                    f", less {float(a) - area:.1f} sq ft excluded")
            add(item, mulch_volume(area, depth), "cu ft",
                f"{area:.0f} sq ft of {zone} {verb} {depth} in{less}")

    if unpriced:
        _caveat(need, f"no area_sqft on {', '.join(unpriced)}, so no mulch or "
                      f"compost is costed for "
                      f"{'them' if len(unpriced) > 1 else 'it'}. This total is "
                      f"short by whatever they need — set the areas in "
                      f"site.json rather than reading the omission as zero")
    for item, zs in excluded.items():
        if zs:
            _caveat(need, f"no {item} by declaration: " + "; ".join(zs))

    for h in design.get("hardscape", []):
        if h.get("existing"):
            continue                      # already built; listing it buys it twice
        if h.get("superseded_by"):
            continue                      # kept for the record, not for buying
        kind = (h.get("kind") or h.get("item") or h.get("name") or "").lower()
        qty, unit = h.get("quantity"), h.get("unit")
        if kind:
            n = float(qty or 1)
            add(kind, n, unit or "each",
                h.get("why") or h.get("note") or "hardscape")
            # `cost_usd` is what the design costed the whole line at, and it is
            # the only figure that knows two toad abodes are broken pots off the
            # spoil heap rather than two of whatever else the yard buys singly.
            if h.get("cost_usd") is not None and n:
                try:
                    need[kind]["design_usd"] = float(h["cost_usd"]) / n
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
        if h.get("fill_cu_ft"):
            add(h.get("fill_material", "garden soil"), float(h["fill_cu_ft"]),
                "cu ft", f"filling {h.get('name', kind)}")

    for p in design.get("plants", []):
        if p.get("existing") or p.get("role") == "existing":
            continue
        n = int(p.get("count", 1))
        # Normalised here rather than at the price lookup, so that the item key
        # a quote has to match is the same string whichever spelling the design
        # used. `4 in` and `4in` priced as two classes is how twelve violas came
        # to be worth $456.
        size = sourcing.normalize_size(p.get("pot_size")) or DEFAULT_POT
        key = f"plant: {p['name']} ({size})"
        add(key, n, "each", f"{n} in {p.get('zone', 'the yard')}")
        # The design's own figure for this planting, where it gave one. It is
        # the only thing on file that knows a garlic clove is not a shrub and
        # that a direct-sown carrot is a seed, and without it every entry with
        # no `pot_size` was costed as a one-gallon pot: $31.50 of carrots,
        # $105 of garlic.
        if p.get("unit_price") is not None:
            try:
                need[key]["design_usd"] = float(p["unit_price"])
            except (TypeError, ValueError):
                pass

    for item, qty in (design.get("extra_materials") or {}).items():
        # A `note` sitting among the quantities is normal in these files and
        # must not take the whole bill of materials down with a ValueError.
        # Anything that will not read as a number is commentary, not an order.
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            continue
        # A material priced by the bag or the yard is sold by volume, whatever
        # its entry happens to say. Without this, mulch and compost arrive here
        # as `each`, miss `price_bulk` entirely, and get priced against whatever
        # else in the yard is sold one at a time — which is how eighteen cubic
        # feet of mulch came to be worth more than the fountain.
        p = PRICES.get(item, {})
        unit = p.get("unit") or ("cu ft" if p.get("bag_usd") or
                                 p.get("bulk_usd_per_yard") else "each")
        # Same item from two directions is a double count, and it is silent:
        # the quantity is simply larger and reads as a bigger job. It happens
        # for exactly one reason and it is a good one — somebody wrote down what
        # the owner actually said he would buy, back when the derived figure was
        # zero because no zone had an area. Now that both exist they are two
        # answers to the same question and a person has to pick.
        before = (need.get(item) or {}).get("quantity") or 0.0
        add(item, qty, unit, "listed in design.extra_materials")
        if before:
            _caveat(need, f"{item} is counted twice: {before:.1f} {unit} "
                          f"derived from the zone areas at the standard depth, "
                          f"plus {qty:g} {unit} listed in "
                          f"design.extra_materials, totalling "
                          f"{before + qty:.1f}. These are two answers to the "
                          f"same question, not two purchases. Decide which "
                          f"before this reaches a shopping list")
    return need


# ------------------------------------------------------------------ pricing

def price_bulk(item, cu_ft, prices):
    """Bags or bulk, decided by which is actually cheaper for this quantity."""
    p = prices.get(item, {})
    bag_usd = p.get("bag_usd")
    bulk_yd = p.get("bulk_usd_per_yard")
    yards_needed = cu_ft / CU_FT_PER_YARD

    options = []
    if bag_usd is not None:
        bags = math.ceil(cu_ft / BAG_CU_FT)
        options.append({"how": "bags", "count": bags, "usd": bags * bag_usd,
                        "detail": f"{bags} bags at ${bag_usd:.2f}"})
    if bulk_yd is not None:
        billed = max(yards_needed, DELIVERY["minimum_yards"])
        billed = math.ceil(billed * 2) / 2.0          # yards sell in half units
        usd = billed * bulk_yd + (DELIVERY["usd"] if bulk_yd > 0 else 0.0)
        detail = f"{billed:g} cu yd at ${bulk_yd:.0f}"
        if bulk_yd > 0:
            detail += f" plus ${DELIVERY['usd']:.0f} delivery"
        if billed > yards_needed + 0.1:
            detail += (f" — {billed:g} is the minimum, so about "
                       f"{billed - yards_needed:.1f} cu yd more than needed")
        options.append({"how": "bulk", "count": billed, "usd": usd,
                        "detail": detail})
    if not options:
        return None
    options.sort(key=lambda o: o["usd"])
    best = options[0]
    if len(options) > 1:
        other = options[1]
        best["instead_of"] = f"{other['how']} at ${other['usd']:.0f}"
        best["saves_usd"] = round(other["usd"] - best["usd"], 2)
    if p.get("note"):
        best["note"] = p["note"]
    return best


def crossover(item, prices=None):
    """The volume above which bulk beats bags for this material.

    Bags cost a flat rate per cubic foot. Bulk costs less per cubic foot but
    carries a delivery fee and a minimum order, so the saving has to earn the fee
    back before bulk is worth anything."""
    p = {**PRICES, **(prices or {})}.get(item, {})
    bag, bulk_yd = p.get("bag_usd"), p.get("bulk_usd_per_yard")
    if bag is None or bulk_yd is None:
        return None
    per_ft_bag = bag / BAG_CU_FT
    per_ft_bulk = bulk_yd / CU_FT_PER_YARD
    fee = DELIVERY["usd"] if bulk_yd > 0 else 0.0
    if per_ft_bulk >= per_ft_bag:
        return {"item": item, "bulk_never_wins": True,
                "say": "bulk is not cheaper per cubic foot here"}
    cu_ft = fee / (per_ft_bag - per_ft_bulk)
    cu_ft = max(cu_ft, DELIVERY["minimum_yards"] * CU_FT_PER_YARD)
    return {"item": item, "cu_ft": round(cu_ft, 1),
            "cu_yd": round(cu_ft / CU_FT_PER_YARD, 2),
            "bag_usd_per_cu_ft": round(per_ft_bag, 2),
            "bulk_usd_per_cu_ft": round(per_ft_bulk, 2),
            "delivery_usd": fee,
            "say": f"bulk {item} beats bags above about "
                   f"{cu_ft / CU_FT_PER_YARD:.1f} cu yd, given a "
                   f"${fee:.0f} delivery. Below that, buy bags"}


def _price_each(item, unit, overlay, merged, src, index, order, design_usd=None):
    """One unit of this, and where the figure came from.

    The sourcing record is asked first, because a quote there carries a supplier,
    a date and a URL. A price in the `--prices` overlay is also a real local
    figure and counts as firm, so it is used whenever the ladder could only
    manage an estimate. The ladder's own estimate is the floor, and it always
    returns something."""
    got = sourcing.price_for(item, unit, src, defaults=merged,
                             plant_defaults=PLANT_PRICES, index=index,
                             order=order)
    if got and got.get("firm"):
        return got
    each = sourcing._entry(overlay, item).get("unit_usd")
    if each is not None:
        return {"usd": float(each), "low": float(each), "high": float(each),
                "rung": "published", "firm": True, "n": 1,
                "supplier": None, "supplier_name": None,
                "as_of": None, "url": None,
                "basis": "local price file"}
    # The design's figure beats anything derived from a pot size, because the
    # design is the only record that knows what form the plant is bought in. It
    # is still an estimate: nobody quoted it and it carries no date.
    if design_usd is not None:
        return {"usd": design_usd, "low": design_usd * 0.75,
                "high": design_usd * 1.5, "rung": "design", "firm": False,
                "n": 1, "supplier": None, "supplier_name": None,
                "as_of": None, "url": None,
                "basis": "the design's own figure for this planting, which is "
                         "not a quote"}
    return got


def net(slug, prices=None, mulch_depth_in=3.0, compost_depth_in=2.0,
        force=False):
    """The requirement, minus what is on site, priced."""
    # A yard that has been sourced has a price file, and it is the best evidence
    # about that yard there is. Waiting to be handed it with `--prices` meant the
    # default run quietly costed Austin against national ballparks while a file
    # of real Austin prices sat unread in the same directory.
    overlay = dict(prices if prices is not None
                   else (yards.load(slug, "local-prices.json") or {}))
    local = bool(overlay)
    # A total is the most actionable thing this repo produces — someone reads it
    # and drives to a yard. An open doubt about a bed's size prices the soil, the
    # compost, the mulch and the plant count all wrong at once.
    provisional = doubts.gate(slug, "bom", force=force)
    prices = {**PRICES, **overlay}
    cond = yards.load_conditions(slug)
    need = requirements(slug, mulch_depth_in, compost_depth_in)
    caveats = need.pop(CAVEATS, [])

    src = sourcing.load(slug)
    local = local or bool(src.get("suppliers"))
    index = sourcing.quotes_index(src)
    order = sourcing.rank_order(slug)

    lines, total, saved = [], 0.0, 0.0
    firm_total, low_total, high_total = 0.0, 0.0, 0.0
    for item in sorted(need):
        e = need[item]
        qty, unit = e["quantity"], e["unit"]
        why = "; ".join(e["why"])

        if item.startswith("plant: "):
            got = _price_each(item, "each", overlay, prices, src, index, order,
                              design_usd=e.get("design_usd"))
            ln = line(item[7:], qty, "plants", qty * got["usd"], why)
            ln["unit_usd"] = got["usd"]
            ln["kind"] = "plant"
            _stamp(ln, got, qty)
            lines.append(ln)
            total += ln["usd"]
            firm_total += ln["usd"] if got["firm"] else 0.0
            low_total += ln["low_usd"]
            high_total += ln["high_usd"]
            continue

        have, have_unit = cond_mod.on_hand(cond, item)
        if have and (have_unit or unit) == unit:
            saved_qty = min(have, qty)
            qty -= saved_qty
        else:
            saved_qty = 0.0

        if qty <= 0.01:
            ln = line(item, 0, unit, 0.0,
                      f"{why} — all {saved_qty:g} {unit} already on site",
                      have=saved_qty)
            ln["kind"] = "material"
            ln["low_usd"] = ln["high_usd"] = 0.0
            lines.append(ln)
            continue

        if unit == "cu ft":
            firm = bool(sourcing._entry(overlay, item).get("bag_usd") or
                        sourcing._entry(overlay, item).get("bulk_usd_per_yard"))
            rates = prices
            basis = ("local rates" if firm else
                     f"national ballpark rate for {item}")
            best = price_bulk(item, qty, rates)
            if best is None:
                # A material the ballpark has never heard of used to fall out of
                # the bill here. Synthesise a rate from the ones it knows rather
                # than lose the line.
                est = sourcing.bulk_estimate(item, prices)
                if est is None:
                    continue
                rates = {**prices, item: est}
                best = price_bulk(item, qty, rates)
                firm, basis = False, est["note"]
            ln = line(item, qty, unit, best["usd"], why, have=saved_qty)
            ln.update({"buy_as": best["how"], "detail": best["detail"],
                       "kind": "material"})
            if best.get("instead_of"):
                ln["instead_of"] = best["instead_of"]
                ln["saves_usd"] = best["saves_usd"]
            if best.get("note"):
                ln["note"] = best["note"]
            # A bulk line is priced as a basket of bags or yards rather than per
            # cubic foot, so the range is stamped against the whole line.
            spread = 0.0 if firm else sourcing.NATIONAL_SPREAD
            _stamp(ln, {"firm": firm, "rung": "published" if firm else "national",
                        "basis": basis, "n": 0,
                        "low": best["usd"] * (1 - spread),
                        "high": best["usd"] * (1 + spread)}, 1.0)
        else:
            got = _price_each(item, unit, overlay, prices, src, index, order,
                              design_usd=e.get("design_usd"))
            ln = line(item, qty, unit, qty * got["usd"], why, have=saved_qty)
            ln["unit_usd"] = got["usd"]
            ln["kind"] = "material"
            if (prices.get(item) or {}).get("note"):
                ln["note"] = prices[item]["note"]
            _stamp(ln, got, qty)

        lines.append(ln)
        total += ln["usd"]
        firm_total += ln["usd"] if ln["pricing"]["firm"] else 0.0
        low_total += ln["low_usd"]
        high_total += ln["high_usd"]
        if saved_qty:
            saved += saved_qty * _rough_unit_cost(item, unit, prices)

    estimated = total - firm_total
    out = {"yard": slug, "lines": lines, "total_usd": round(total, 2),
           "firm_usd": round(firm_total, 2),
           "estimated_usd": round(estimated, 2),
           "estimated_share_pct": round(100.0 * estimated / total, 1) if total
           else 0.0,
           "low_usd": round(low_total, 2), "high_usd": round(high_total, 2),
           "saved_by_using_what_is_here_usd": round(saved, 2),
           "prices": "local" if local else "national ballpark"}
    if caveats:
        out["caveats"] = caveats
    if provisional:
        out["provenance"] = provisional
    return out


def _stamp(ln, got, qty):
    """Record how a line was priced, on the line, in money rather than per unit.

    Kept on every line and not only the estimated ones, because a reader
    comparing two lines needs to know that one is a quote and the other is a
    class median, and a field that only appears sometimes is one that gets
    missed."""
    ln["pricing"] = {"rung": got["rung"], "firm": bool(got["firm"]),
                     "basis": got["basis"], "comparables": got.get("n", 0)}
    for key in ("supplier", "supplier_name", "as_of", "url"):
        if got.get(key):
            ln["pricing"][key] = got[key]
    ln["low_usd"] = round(qty * got["low"], 2)
    ln["high_usd"] = round(qty * got["high"], 2)
    if not got["firm"]:
        ln["estimated"] = True


def _rough_unit_cost(item, unit, prices):
    p = prices.get(item, {})
    if unit == "cu ft" and p.get("bag_usd"):
        return p["bag_usd"] / BAG_CU_FT
    return p.get("unit_usd", 0.0)


# ------------------------------------------------------------------ the budget

def cut_list(slug, bom=None, ceiling=None, force=False):
    """What to drop to fit, worst value first.

    Order comes from the vision, not from price. The cheapest line is often the
    edging, and dropping the edging is what makes the whole planting look
    unfinished — so the ranking is by how much the person said each thing
    mattered, and structural items are protected."""
    bom = bom or net(slug, force=force)
    cond = yards.load_conditions(slug)
    vis = yards.load_vision(slug)
    ceiling = ceiling or (cond.get("budget") or {}).get("ceiling_usd")
    total = bom["total_usd"]

    if not ceiling:
        return {"ceiling_usd": None, "total_usd": total,
                "say": "no budget ceiling recorded, so nothing can be checked "
                       "against it. Ask, and ask whether it is a lump sum or "
                       "spread over months — the answer changes the schedule as "
                       "much as the list"}
    if total <= ceiling:
        return {"ceiling_usd": ceiling, "total_usd": total,
                "under_by_usd": round(ceiling - total, 2),
                "say": f"${total:,.0f} against a ${ceiling:,.0f} ceiling, with "
                       f"${ceiling - total:,.0f} of room. Hold some of it: "
                       f"something always costs more than this says"}

    must_words = " ".join(w.get("want", "").lower()
                          for w in vision_mod._wants(vis)
                          if w.get("strength") == "must")
    # Soil prep, edging and irrigation are protected because they are what makes
    # the rest survive and read as finished. Skimping here is what turns a
    # planting into a patch of ground with plants in it.
    protected = ("edging", "drip line", "emitters", "compost", "lumber")

    def rank(ln):
        name = ln["item"].lower()
        if any(t in must_words for t in name.split() if len(t) > 4):
            return (0, -ln["usd"])                  # they said it is a must
        if any(k in name for k in protected):
            return (1, -ln["usd"])
        if ln.get("kind") == "plant":
            return (3, -ln["usd"])                  # plants give before structure
        return (2, -ln["usd"])

    cuts, running = [], total
    for ln in sorted(bom["lines"], key=rank, reverse=True):
        if running <= ceiling:
            break
        if ln["usd"] <= 0 or rank(ln)[0] <= 1:
            continue
        action, instead, saves = _substitute(ln)
        cuts.append({"item": ln["item"], "action": action,
                     "saves_usd": round(ln["usd"] * saves, 2), "instead": instead})
        running -= ln["usd"] * saves

    return {"ceiling_usd": ceiling, "total_usd": total,
            "over_by_usd": round(total - ceiling, 2),
            "cuts": cuts, "after_cuts_usd": round(running, 2),
            "say": f"${total:,.0f} against a ${ceiling:,.0f} ceiling, over by "
                   f"${total - ceiling:,.0f}"}


def _substitute(ln):
    """The cheaper way to still get it. Returns the action, the advice, and the
    fraction of the line it saves — because most of these are downsizing rather
    than dropping, and saying "drop the tree" when the answer is "buy a smaller
    tree" loses the design for no reason."""
    name = ln["item"].lower()
    if ln.get("kind") == "plant":
        if any(s in name for s in ("15gal", "b&b", "7gal", "5gal")):
            return ("downsize",
                    "buy it in a 1-gallon. It catches a 5-gallon in about three "
                    "years and costs a quarter as much, and it establishes "
                    "better because the root ball is not circling", 0.75)
        return ("halve",
                "halve the count and space the rest at mature spread, which the "
                "bed wants anyway, or grow from seed where the plant allows it",
                0.5)
    if "mulch" in name:
        return ("substitute",
                "wood chips, free from a tree service or the municipal yard. "
                "Coarser and less tidy, and it does the same job", 0.9)
    if "compost" in name:
        return ("substitute",
                "municipal compost is usually a third the price. Ask what the "
                "feedstock is before spreading it on an edible bed", 0.6)
    if "flagstone" in name or "paver" in name:
        return ("substitute",
                "gravel or decomposed granite for a fraction, and it can be "
                "upgraded in place later", 0.7)
    return ("defer", "push to the next phase", 1.0)


# ---------------------------------------------------------------- price gaps

def price_gaps(slug, prices=None, bom=None, force=False):
    """The estimated lines, worst first, measured in dollars at risk.

    "A third of the list has no local price" is true and unusable. What a person
    can act on is a short list ordered by how much the total moves if the guess
    is wrong, because that is the order to make phone calls in."""
    bom = bom or net(slug, prices, force=force)
    gaps = []
    for ln in bom["lines"]:
        if not ln.get("estimated") or ln["usd"] <= 0:
            continue
        gaps.append({"item": ln["item"], "usd": ln["usd"],
                     "low_usd": ln["low_usd"], "high_usd": ln["high_usd"],
                     "at_risk_usd": round(ln["high_usd"] - ln["low_usd"], 2),
                     "rung": ln["pricing"]["rung"],
                     "basis": ln["pricing"]["basis"]})
    gaps.sort(key=lambda g: -g["at_risk_usd"])
    return {"yard": slug, "gaps": gaps,
            "estimated_usd": bom["estimated_usd"],
            "at_risk_usd": round(sum(g["at_risk_usd"] for g in gaps), 2)}


# ------------------------------------------------------------------ reporting

def report(slug, prices=None, force=False):
    bom = net(slug, prices, force=force)
    print(f"{slug} — bill of materials\n")
    if not bom["lines"]:
        print("  nothing in design.json to price yet")
        return
    for ln in bom["lines"]:
        if ln["usd"] == 0 and ln.get("already_on_hand"):
            print(f"  {ln['item']:44s} {'—':>10s}   already on site "
                  f"({ln['already_on_hand']:g} {ln['unit']})")
            continue
        money = f"${ln['usd']:,.2f}" + ("~" if ln.get("estimated") else " ")
        print(f"  {ln['item']:44s} {ln['quantity']:8g} {ln['unit']:<8s} "
              f"{money:>11s}")
        if ln.get("detail"):
            print(f"      {ln['detail']}")
        if ln.get("saves_usd"):
            print(f"      saves ${ln['saves_usd']:,.0f} against {ln['instead_of']}")
        if ln.get("already_on_hand"):
            print(f"      {ln['already_on_hand']:g} {ln['unit']} already here, "
                  f"netted out")
        if ln.get("estimated"):
            print(f"      ~ estimated: {ln['pricing']['basis']}")
        if ln.get("note"):
            print(f"      {ln['note']}")

    print(f"\n  {'total':44s} {'':17s} " + f"${bom['total_usd']:,.2f}".rjust(11))
    if bom["estimated_usd"]:
        print(f"  ${bom['firm_usd']:,.2f} of that is quoted and "
              f"${bom['estimated_usd']:,.2f} — {bom['estimated_share_pct']:.0f}% "
              f"— is estimated from comparable prices")
        print(f"  the range across those estimates is "
              f"${bom['low_usd']:,.0f} to ${bom['high_usd']:,.0f}")
    if bom["saved_by_using_what_is_here_usd"]:
        print(f"  about ${bom['saved_by_using_what_is_here_usd']:,.0f} of that "
              f"avoided by using what was already on site")
    if bom["prices"] != "local":
        print("  nothing local on file, so every figure above is a national "
              "ballpark. Run the sourcing-scout subagent for real numbers")
    if bom.get("provenance"):
        print(f"  {bom['provenance']}: quantities above rest on assumptions "
              f"still in question")
    for c in bom.get("caveats") or []:
        print()
        for i, w in enumerate(vision_mod._wrap(c, 68)):
            print(f"  {'not costed:' if i == 0 else '           '} {w}")

    for ln in bom["lines"]:
        if ln["unit"] != "cu ft" or ln["usd"] <= 0:
            continue
        x = crossover(ln["item"], prices)
        if x and not x.get("bulk_never_wins"):
            print(f"  {x['say']}")

    c = cut_list(slug, bom)
    print(f"\n  {c['say']}")
    for x in c.get("cuts", []):
        print(f"    {x['action']} {x['item']} (saves ${x['saves_usd']:,.0f}) — "
              f"{x['instead']}")
    if c.get("cuts"):
        print(f"    that lands at ${c['after_cuts_usd']:,.0f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--prices", help="JSON of local prices, overriding defaults")
    ap.add_argument("--mulch-depth", type=float, default=3.0)
    ap.add_argument("--compost-depth", type=float, default=2.0)
    ap.add_argument("--cut", action="store_true", help="only the cut list")
    ap.add_argument("--price-gaps", action="store_true",
                    help="the estimated lines, ranked by dollars at risk")
    ap.add_argument("--crossover", action="store_true",
                    help="bags-versus-bulk crossover for every bulk material")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="price a yard whose board still has open doubts; the "
                         "result is stamped provisional")
    args = ap.parse_args()

    prices = None
    if args.prices:
        with open(args.prices) as fh:
            prices = json.load(fh)
    if args.crossover:
        for item in sorted(PRICES):
            x = crossover(item, prices)
            if x:
                print(f"  {x['say']}" if not x.get("bulk_never_wins")
                      else f"  {item}: {x['say']}")
        return
    if args.json:
        print(json.dumps(net(args.slug, prices, force=args.force), indent=2))
        return
    if args.cut:
        print(json.dumps(cut_list(args.slug, force=args.force), indent=2))
        return
    if args.price_gaps:
        g = price_gaps(args.slug, prices, force=args.force)
        if not g["gaps"]:
            print(f"{args.slug}: every line is a quoted price")
            return
        print(f"{args.slug} — {len(g['gaps'])} estimated line"
              f"{'s' if len(g['gaps']) > 1 else ''}, "
              f"${g['estimated_usd']:,.0f} of the total, "
              f"${g['at_risk_usd']:,.0f} of spread. Call in this order.\n")
        for x in g["gaps"]:
            print(f"  {x['item'][:40]:40s} ${x['usd']:>9,.2f}   "
                  f"${x['low_usd']:,.0f}–${x['high_usd']:,.0f}")
            print(f"      {x['basis']}")
        return
    report(args.slug, prices, force=args.force)


if __name__ == "__main__":
    main()
