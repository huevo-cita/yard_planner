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

Prices
------
The defaults are national ballpark figures and are labelled as such wherever they
are printed. They exist so a plan has a number before anyone drives anywhere, not
so that number can be quoted. Real prices come from the `sourcing-scout` subagent
and are passed in with `--prices`, which overrides per item.

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

from . import conditions as cond_mod, doubts, vision as vision_mod, yards

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


def requirements(slug, mulch_depth_in=3.0, compost_depth_in=2.0):
    """Everything the design implies, before netting against what is on site."""
    site = yards.load(slug, "site.json") or {}
    design = yards.load(slug, "design.json") or {}
    need = {}

    def add(item, qty, unit, why):
        e = need.setdefault(item, {"quantity": 0.0, "unit": unit, "why": []})
        e["quantity"] += qty
        if why not in e["why"]:
            e["why"].append(why)

    from .design import zone_areas
    areas = zone_areas(site)
    planted = {p.get("zone") for p in design.get("plants", []) if p.get("zone")}

    for zone in sorted(planted):
        a = areas.get(zone)
        if not a:
            continue
        add("mulch", mulch_volume(a, mulch_depth_in), "cu ft",
            f"{a:.0f} sq ft of {zone} at {mulch_depth_in} in")
        add("compost", mulch_volume(a, compost_depth_in), "cu ft",
            f"{a:.0f} sq ft of {zone} topdressed at {compost_depth_in} in")

    for h in design.get("hardscape", []):
        if h.get("existing"):
            continue                      # already built; listing it buys it twice
        kind = (h.get("kind") or h.get("item") or h.get("name") or "").lower()
        qty, unit = h.get("quantity"), h.get("unit")
        if kind:
            add(kind, float(qty or 1), unit or "each",
                h.get("why") or h.get("note") or "hardscape")
        if h.get("fill_cu_ft"):
            add(h.get("fill_material", "garden soil"), float(h["fill_cu_ft"]),
                "cu ft", f"filling {h.get('name', kind)}")

    for p in design.get("plants", []):
        if p.get("existing") or p.get("role") == "existing":
            continue
        n = int(p.get("count", 1))
        size = p.get("pot_size", DEFAULT_POT)
        add(f"plant: {p['name']} ({size})", n, "each",
            f"{n} in {p.get('zone', 'the yard')}")

    for item, qty in (design.get("extra_materials") or {}).items():
        add(item, float(qty), PRICES.get(item, {}).get("unit", "each"),
            "listed in design.extra_materials")
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


def net(slug, prices=None, mulch_depth_in=3.0, compost_depth_in=2.0,
        force=False):
    """The requirement, minus what is on site, priced."""
    local = bool(prices)
    # A total is the most actionable thing this repo produces — someone reads it
    # and drives to a yard. An open doubt about a bed's size prices the soil, the
    # compost, the mulch and the plant count all wrong at once.
    provisional = doubts.gate(slug, "bom", force=force)
    prices = {**PRICES, **(prices or {})}
    cond = yards.load_conditions(slug)
    need = requirements(slug, mulch_depth_in, compost_depth_in)

    lines, total, saved = [], 0.0, 0.0
    for item in sorted(need):
        e = need[item]
        qty, unit = e["quantity"], e["unit"]
        why = "; ".join(e["why"])

        if item.startswith("plant: "):
            size = item.rsplit("(", 1)[-1].rstrip(")")
            each = PLANT_PRICES.get(size, PLANT_PRICES[DEFAULT_POT])
            usd = qty * each
            ln = line(item[7:], qty, "plants", usd, why)
            ln["unit_usd"] = each
            ln["kind"] = "plant"
            lines.append(ln)
            total += usd
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
            lines.append(ln)
            continue

        if unit == "cu ft":
            best = price_bulk(item, qty, prices)
            if best is None:
                continue
            ln = line(item, qty, unit, best["usd"], why, have=saved_qty)
            ln.update({"buy_as": best["how"], "detail": best["detail"],
                       "kind": "material"})
            if best.get("instead_of"):
                ln["instead_of"] = best["instead_of"]
                ln["saves_usd"] = best["saves_usd"]
            if best.get("note"):
                ln["note"] = best["note"]
        else:
            each = prices.get(item, {}).get("unit_usd")
            ln = line(item, qty, unit, qty * (each or 0.0), why, have=saved_qty)
            ln["unit_usd"] = each or 0.0
            ln["kind"] = "material"
            # An unpriced line quietly costing nothing is worse than no line at
            # all, because the total looks complete and is not.
            if each is None:
                ln["unpriced"] = True
                ln["note"] = ("no price on file, so this is missing from the "
                              "total. The sourcing-scout can quote it")
            elif prices.get(item, {}).get("note"):
                ln["note"] = prices[item]["note"]

        lines.append(ln)
        total += ln["usd"]
        if saved_qty:
            saved += saved_qty * _rough_unit_cost(item, unit, prices)

    out = {"yard": slug, "lines": lines, "total_usd": round(total, 2),
           "saved_by_using_what_is_here_usd": round(saved, 2),
           "prices": "local" if local else "national ballpark"}
    if provisional:
        out["provenance"] = provisional
    return out


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
        money = "unpriced" if ln.get("unpriced") else f"${ln['usd']:,.2f}"
        print(f"  {ln['item']:44s} {ln['quantity']:8g} {ln['unit']:<8s} "
              f"{money:>10s}")
        if ln.get("detail"):
            print(f"      {ln['detail']}")
        if ln.get("saves_usd"):
            print(f"      saves ${ln['saves_usd']:,.0f} against {ln['instead_of']}")
        if ln.get("already_on_hand"):
            print(f"      {ln['already_on_hand']:g} {ln['unit']} already here, "
                  f"netted out")
        if ln.get("note"):
            print(f"      {ln['note']}")

    print(f"\n  {'total':44s} {'':17s} " + f"${bom['total_usd']:,.2f}".rjust(10))
    missing = [ln["item"] for ln in bom["lines"] if ln.get("unpriced")]
    if missing:
        print(f"  that total excludes {len(missing)} unpriced item"
              f"{'s' if len(missing) > 1 else ''}: {', '.join(missing)}")
    if bom["saved_by_using_what_is_here_usd"]:
        print(f"  about ${bom['saved_by_using_what_is_here_usd']:,.0f} of that "
              f"avoided by using what was already on site")
    if bom["prices"] != "local":
        print("  prices are national ballpark figures, not quotes. Run the "
              "sourcing-scout subagent for real local numbers")
    if bom.get("provenance"):
        print(f"  {bom['provenance']}: quantities above rest on assumptions "
              f"still in question")

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
    report(args.slug, prices, force=args.force)


if __name__ == "__main__":
    main()
