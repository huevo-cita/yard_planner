#!/usr/bin/env python3
"""conditions.json — the current state of a yard and of the person working it.

    python3 -m lib.conditions <slug>              what is recorded, what is stale
    python3 -m lib.conditions <slug> --init       start an empty record
    python3 -m lib.conditions <slug> --check      only what needs re-confirming

site.json says what the yard *is*. conditions.json says what is *already true*
about it today: what ground is dug, what is in the shed, what the person knows
how to do, how many hours they have, and what they can spend. Without it a
schedule invents work that is already done and a budget buys compost that is
already in the garage.

Sections
--------
    soil          the USDA baseline plus whatever was actually tested
    ground        what is dug, edged, bordered, mulched, irrigated, paved
    water         spigots, hose reach, irrigation, rain capture
    materials     what is on hand, with quantities, so the BOM can net against it
    tools         what can be done without renting or buying
    person        experience, physical limits, hours a week, travel gaps
    budget        the ceiling, and whether it is a lump or a monthly trickle
    constraints   HOA, landlord, pets, children, deer, deadlines

Every section carries `last_verified`. Conditions decay: compost gets used, beds
get weedy, a borrowed tiller goes home. Anything past its window is re-confirmed
rather than trusted, and the freshness is reported rather than assumed.
"""
import argparse
import datetime
import json
import sys

from . import yards

TODAY = datetime.date.today().isoformat()

# how long each kind of fact stays believable, in months
DECAY = {
    "soil": 36,          # texture is forever, pH and nutrients drift
    "ground": 12,        # a bed edged last spring is probably still edged
    "water": 24,
    "materials": 3,      # the fastest-moving of the lot
    "tools": 12,
    "person": 12,
    "budget": 6,
    "constraints": 12,
}

EXPERIENCE = ["none", "beginner", "some", "confident", "expert"]

# What a person at each level can reasonably take on unaided.
#
# Levels are cumulative: `can` is built up from every level below, because
# someone confident has not forgotten how to mulch. Written flat, the higher
# levels ended up shorter than the lower ones and the gate inverted — a
# confident gardener was told to read the how-to for spreading compost.
_GATES = {
    "none": {"can": ["plant from a pot", "water", "mulch", "weed"],
             "guide": ["sow seed", "edge a bed", "spread compost"],
             "hire": ["build a raised bed", "lay a path", "run irrigation",
                      "install drip", "prune a tree", "move flagstone",
                      "spread and grade soil", "any electrical"]},
    "beginner": {"can": ["plant", "sow seed", "spread compost"],
                 "guide": ["edge a bed", "install edging",
                           "build a simple raised bed", "divide perennials",
                           "install drip", "spread and grade soil"],
                 "hire": ["lay a mortared path", "lay a path",
                          "prune anything structural", "move heavy stone",
                          "any electrical", "fell a tree"]},
    "some": {"can": ["edge a bed", "install edging", "build a raised bed",
                     "divide perennials", "spread and grade soil",
                     "install drip"],
             "guide": ["lay a dry-laid path", "lay a path", "build a low wall",
                       "prune shrubs", "graft or take cuttings"],
             "hire": ["structural pruning", "tree felling",
                      "retaining walls over about 2 ft", "any electrical"]},
    "confident": {"can": ["lay a dry-laid path", "lay a path", "build a low wall",
                          "prune shrubs", "run irrigation", "graft or take "
                          "cuttings"],
                  "guide": ["retaining walls", "drainage design",
                            "structural pruning"],
                  "hire": ["tree work at height", "any electrical",
                           "anything needing a permit"]},
    "expert": {"can": ["retaining walls", "drainage design", "structural "
                       "pruning"],
               "guide": [],
               "hire": ["licensed trades", "tree work at height",
                        "any electrical"]},
}


def _cumulative(gates, order):
    """Each level can do everything the levels below it can, and the `guide` and
    `hire` lists shed anything a higher level has been promoted past."""
    out, acquired = {}, []
    for level in order:
        acquired = acquired + gates[level]["can"]
        can = list(dict.fromkeys(acquired))
        out[level] = {
            "can": can,
            "guide": [t for t in gates[level]["guide"] if t not in can],
            "hire": [t for t in gates[level]["hire"] if t not in can],
        }
    return out


SKILL_GATES = _cumulative(_GATES, EXPERIENCE)

# the unit each material is bought and used in, so the BOM can net cleanly
MATERIAL_UNITS = {
    "compost": "cu ft", "topsoil": "cu ft", "garden soil": "cu ft",
    "mulch": "cu ft", "wood chips": "cu ft", "gravel": "cu ft",
    "sand": "cu ft", "decomposed granite": "cu ft",
    "edging": "linear ft", "landscape fabric": "sq ft", "cardboard": "sq ft",
    "lumber": "linear ft", "pavers": "each", "block": "each",
    "flagstone": "sq ft", "pots": "each", "stakes": "each",
    "trellis": "each", "drip line": "linear ft", "emitters": "each",
    "fertilizer": "lb", "lime": "lb", "sulphur": "lb", "seed": "packet",
}


def blank(slug):
    return {
        "yard": slug,
        "schema_version": 1,
        "soil": {"last_verified": None, "usda": None, "tests": [],
                 "amendment_history": [], "lab_test": None},
        "ground": {"last_verified": None, "areas": [], "hardscape": [],
                   "surface_note": None},
        "water": {"last_verified": None, "spigots": [], "hose_reach_ft": None,
                  "irrigation": None, "rain_capture": None},
        "materials": {"last_verified": None, "on_hand": []},
        "tools": {"last_verified": None, "owned": [], "borrowable": [],
                  "rentable_nearby": []},
        "person": {"last_verified": None, "experience": None,
                   "done_before": [], "physical_limits": [],
                   "hours_per_week": None, "preferred_days": [],
                   "travel_gaps": []},
        "budget": {"last_verified": None, "ceiling_usd": None,
                   "cadence": None, "spent_so_far_usd": 0,
                   "willing_to_phase": None},
        "constraints": {"last_verified": None, "hoa": None, "landlord": None,
                        "pets": [], "children": None, "wildlife": [],
                        "deadlines": []},
    }


# ------------------------------------------------------------------ freshness

def staleness(cond):
    """Every section, with how old it is and whether that still counts."""
    out = []
    for name, months in DECAY.items():
        sec = cond.get(name) or {}
        when = sec.get("last_verified")
        empty = _is_empty(sec)
        if when:
            try:
                d = datetime.date.fromisoformat(str(when)[:10])
                age = (datetime.date.today() - d).days
            except ValueError:
                d, age = None, None
        else:
            d, age = None, None
        out.append({
            "section": name,
            "last_verified": when,
            "age_days": age,
            "window_months": months,
            "state": ("never recorded" if empty and not when else
                      "no date" if not when else
                      "stale" if age is not None and age > months * 30 else
                      "current"),
        })
    return out


def _is_empty(sec):
    for k, v in (sec or {}).items():
        if k == "last_verified":
            continue
        if v not in (None, [], {}, 0, ""):
            return False
    return True


def verify(cond, section, when=None):
    cond.setdefault(section, {})["last_verified"] = when or TODAY
    return cond


# --------------------------------------------------------------- soil records

def record_usda(slug, res):
    """Store the survey's answer, without letting it masquerade as a measurement."""
    cond = yards.load(slug, "conditions.json") or blank(slug)
    soil = cond.setdefault("soil", {})
    soil["usda"] = {
        "map_unit": res.get("map_unit"), "symbol": res.get("symbol"),
        "mukey": res.get("mukey"), "survey_area": res.get("survey_area"),
        "disturbed": res.get("disturbed"),
        "verdict": res.get("verdict"),
        "components": res.get("components"),
        "retrieved": TODAY,
        "confidence": "low — the survey maps this as made ground"
        if res.get("disturbed") else "moderate — undisturbed map unit",
    }
    yards.save(slug, "conditions.json", cond)
    print(f"recorded the USDA baseline in {yards.path(slug, 'conditions.json')}")
    if res.get("disturbed"):
        print("  flagged low confidence: a jar test and a percolation test are "
              "worth more than this map unit on a lot like yours")
    return cond


def record_test(slug, result, where=None):
    """Add a hands-on test result and stamp the soil section fresh."""
    cond = yards.load(slug, "conditions.json") or blank(slug)
    entry = dict(result)
    entry["date"] = TODAY
    if where:
        entry["where"] = where
    cond.setdefault("soil", {}).setdefault("tests", []).append(entry)
    verify(cond, "soil")
    yards.save(slug, "conditions.json", cond)
    return cond


def soil_summary(cond):
    """The best answer available, and how much weight it can carry."""
    soil = cond.get("soil") or {}
    # A hand-written observation is a legitimate entry here and carries no test
    # name, so an unnamed entry is skipped rather than treated as a failure.
    tests = {t["test"]: t for t in soil.get("tests", []) if t.get("test")}
    out = {"texture": None, "drainage": None, "ph": None, "compaction": None,
           "basis": [], "confidence": "none"}
    if tests.get("jar"):
        out["texture"] = tests["jar"]["texture"]
        out["basis"].append("jar test")
    elif (soil.get("usda") or {}).get("components"):
        for c in soil["usda"]["components"]:
            for h in c.get("horizons") or []:
                if h.get("texture") and h.get("top_in") == 0:
                    out["texture"] = h["texture"]
                    out["basis"].append("USDA surface horizon")
                    break
            if out["texture"]:
                break
    if tests.get("percolation"):
        out["drainage"] = tests["percolation"]["drainage_class"]
        out["basis"].append("percolation test")
    elif (soil.get("usda") or {}).get("components"):
        d = soil["usda"]["components"][0].get("drainage_class")
        if d:
            out["drainage"] = d
            out["basis"].append("USDA drainage class")
    if soil.get("lab_test"):
        out["ph"] = soil["lab_test"].get("ph")
        out["basis"].append("lab test")
    elif tests.get("pH"):
        out["ph"] = tests["pH"]["value"]
        out["basis"].append("pH strip")
    if tests.get("compaction probe"):
        out["compaction"] = tests["compaction probe"]["class"]
        out["basis"].append("compaction probe")

    hands = sum(1 for b in out["basis"] if "USDA" not in b)
    out["confidence"] = ("good" if soil.get("lab_test") else
                         "workable" if hands >= 2 else
                         "thin" if hands == 1 else
                         "map only" if out["basis"] else "none")
    return out


# ------------------------------------------------------------------ inventory

def on_hand(cond, material):
    """How much of something is already here, in its usual unit."""
    for m in (cond.get("materials") or {}).get("on_hand", []):
        if m.get("item", "").lower() == material.lower():
            return float(m.get("quantity") or 0), m.get("unit")
    return 0.0, MATERIAL_UNITS.get(material.lower())


def has_tool(cond, tool):
    t = cond.get("tools") or {}
    tool = tool.lower()
    for key in ("owned", "borrowable"):
        for item in t.get(key, []):
            name = item if isinstance(item, str) else item.get("name", "")
            if tool in name.lower():
                return key
    return None


def can_do(cond, task):
    """Whether the person can take a task on, needs the how-to, or should hire it.

    Explicit experience with a specific task beats the general level: someone who
    has built a raised bed before has built a raised bed before, whatever they
    call their overall skill.
    """
    person = cond.get("person") or {}
    done = [d.lower() for d in person.get("done_before", [])]
    if any(task.lower() in d or d in task.lower() for d in done):
        return "can", "done it before"
    level = person.get("experience")
    if level not in SKILL_GATES:
        return "unknown", "no experience level recorded"
    gate = SKILL_GATES[level]
    # hire before guide before can, so the most cautious verdict that matches
    # wins rather than the first one found
    for verdict in ("hire", "guide", "can"):
        for pattern in gate[verdict]:
            if pattern.lower() in task.lower() or task.lower() in pattern.lower():
                return verdict, f"{level}: {pattern}"
    return "guide", f"not on the {level} list, so write the how-to in"


def hours_available(cond, weeks):
    per = (cond.get("person") or {}).get("hours_per_week")
    if not per:
        return None
    gaps = len((cond.get("person") or {}).get("travel_gaps", []))
    return max(weeks - gaps, 0) * float(per)


# --------------------------------------------------------------------- report

def report(slug, only_stale=False):
    cond = yards.load(slug, "conditions.json")
    if cond is None:
        print(f"{slug} has no conditions.json yet. Run the yard-conditions "
              f"skill, or `python3 -m lib.conditions {slug} --init`.")
        return None

    rows = staleness(cond)
    if only_stale:
        rows = [r for r in rows if r["state"] != "current"]
        if not rows:
            print(f"{slug}: everything current")
            return cond

    print(f"{slug} — conditions\n")
    print(f"  {'section':14s} {'state':16s} {'verified':12s} {'window'}")
    for r in rows:
        age = (f"{r['age_days']}d ago" if r["age_days"] is not None else "—")
        print(f"  {r['section']:14s} {r['state']:16s} {age:12s} "
              f"{r['window_months']} months")

    s = soil_summary(cond)
    print(f"\n  soil: texture {s['texture'] or 'unknown'}, drainage "
          f"{s['drainage'] or 'unknown'}, pH {s['ph'] or 'unknown'} "
          f"— confidence {s['confidence']}")
    if s["basis"]:
        print(f"        from {', '.join(s['basis'])}")

    mats = (cond.get("materials") or {}).get("on_hand", [])
    if mats:
        print(f"\n  on hand ({len(mats)} items):")
        for m in mats[:12]:
            print(f"    {m.get('item', '?'):24s} {m.get('quantity', '?')} "
                  f"{m.get('unit', '')}")
    person = cond.get("person") or {}
    if person.get("experience"):
        print(f"\n  person: {person['experience']}, "
              f"{person.get('hours_per_week') or '?'} h/week")
    b = cond.get("budget") or {}
    if b.get("ceiling_usd"):
        print(f"  budget: ${b['ceiling_usd']:,.0f} {b.get('cadence') or ''}, "
              f"${b.get('spent_so_far_usd') or 0:,.0f} spent")

    missing = [r["section"] for r in staleness(cond)
               if r["state"] == "never recorded"]
    if missing:
        print(f"\n  never recorded: {', '.join(missing)}")
    return cond


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--check", action="store_true", help="only stale sections")
    args = ap.parse_args()

    if args.init:
        if yards.load(args.slug, "conditions.json") is not None:
            print(f"{args.slug} already has a conditions.json; not overwriting")
            return
        yards.save(args.slug, "conditions.json", blank(args.slug))
        print(f"created {yards.path(args.slug, 'conditions.json')}")
        return
    report(args.slug, only_stale=args.check)


if __name__ == "__main__":
    main()
