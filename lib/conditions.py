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
    constraints   HOA, landlord, pets, children, deer, standing rules, and the
                  three different things a date can mean here: the display
                  milestone the garden has to look right on, the blackouts when
                  no work happens, and whether the project ends at all

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
                        "deadlines": [], "rules": [],
                        "display_milestone": None, "blackouts": [],
                        "project_end": None},
    }


#: The keys `blank()` declares under `ground`. See `unread_ground`.
GROUND_SCHEMA = ("last_verified", "areas", "hardscape", "surface_note")


def unread_ground(cond):
    """Ground facts filed under a key nothing reads.

    An empty `ground.areas` is read by `lib.schedule` as a bare lot — measure
    it, mark it out, dig it, edge it, till it. That is the right reading of
    "nothing is built here" and the wrong reading of "nobody wrote it down under
    this key", and the two are indistinguishable from the key alone. One yard
    recorded ten built features under `ground.already_built`, a spelling it
    invented, and drew twelve hours of groundwork for four beds that were
    already dug, edged and planted.

    This deliberately does not read the stray key and carry on. An `areas` entry
    turns on its `state`, which is what the schedule gates against, and reading
    "edged" out of the sentence "Four in-ground beds, all edged" is a guess
    rather than a rename. So this names the key and the count and stops, and the
    migration onto the schema stays a written act with somebody's word behind
    each state.

    A note or a status string is prose and is not flagged; a non-empty list of
    records is.
    """
    ground = cond.get("ground") or {}
    out = []
    for key, value in ground.items():
        if key in GROUND_SCHEMA:
            continue
        if (isinstance(value, list) and value
                and all(isinstance(v, dict) for v in value)):
            out.append({"key": key, "count": len(value)})
    return sorted(out, key=lambda r: r["key"])


# ------------------------------------------------ what a date on a yard means

def _as_date(v):
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def display_milestone(cond):
    """The date the garden has to *look* right on, or None.

    Deliberately not called a deadline. A deadline is a date work runs up to,
    and reading a display date that way is what put the largest planting of one
    yard's autumn three weeks before the party it was meant to be settled for.
    """
    return (cond.get("constraints") or {}).get("display_milestone")


def blackouts(cond):
    """Periods when no work happens at all, as (from, to) inclusive.

    Distinct from `person.travel_gaps`, which says where somebody is. A blackout
    says only that the yard gets no hours, whatever the reason, and a week that
    is spoken for is not the same fact as a week spent away from home.
    """
    out = []
    for b in (cond.get("constraints") or {}).get("blackouts") or []:
        a, z = _as_date(b.get("from")), _as_date(b.get("to") or b.get("from"))
        if a and z:
            out.append((a, z))
    return out


def in_blackout(cond, day):
    """Whether a date falls inside a blackout, and which one."""
    day = _as_date(day)
    for a, z in blackouts(cond):
        if day and a <= day <= z:
            return {"from": a.isoformat(), "to": z.isoformat()}
    return None


def project_end(cond):
    """The date the project ends, and whether anybody has actually said.

    Three-valued on purpose. A recorded `null` means somebody was asked and the
    answer was that there is no end — which is not the same as nobody having
    been asked, and the difference decides whether work after the display
    milestone may be treated as out of scope. It may not, unless it says so.
    """
    rec = (cond.get("constraints") or {}).get("project_end")
    if rec is None:
        return {"stated": False, "date": None}
    return {"stated": True, "date": _as_date(rec.get("date")),
            "source": rec.get("source"), "note": rec.get("note")}


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


def weekly_hours(cond):
    """Working hours a week as one number, from either shape the record uses.

    `person.hours_per_week` is written as a figure by some yards and as a
    `{"low": 1, "high": 6}` band by others, because "one to six" is what a
    person actually says about their own Saturdays. Both are legitimate and
    `lib.niches` already reads either, so a caller that assumes the scalar
    crashes on a perfectly well-formed yard.

    The two ends of a band are not interchangeable to a caller sizing a build.
    The low end stretches a sixty-hour job over sixty weekends; the high end
    books every weekend of the autumn at a ceiling the record generally only
    claims for the good ones. So a band reads as its midpoint, which is the
    figure it is a band around, and callers that want either end can ask.
    """
    per = (cond.get("person") or {}).get("hours_per_week")
    if isinstance(per, dict):
        ends = [v for v in (per.get("low"), per.get("high"))
                if isinstance(v, (int, float))]
        if ends:
            return sum(ends) / len(ends)
        per = per.get("value")
    return float(per) if isinstance(per, (int, float)) else None


def hours_available(cond, weeks):
    per = weekly_hours(cond)
    if not per:
        return None
    gaps = len((cond.get("person") or {}).get("travel_gaps", []))
    return max(weeks - gaps, 0) * per


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

    mile = display_milestone(cond)
    if mile:
        print(f"\n  display milestone: {mile.get('date')} — "
              f"{mile.get('what') or 'the garden has to look right'}")
    for a, z in blackouts(cond):
        print(f"  blackout: {a} to {z}, no work at all")
    end = project_end(cond)
    if end["stated"]:
        print(f"  project end: {end['date'] or 'none — the project is open-ended'}")

    stray = unread_ground(cond)
    for s in stray:
        print(f"\n  ground.{s['key']} holds {s['count']} records and nothing "
              f"reads it.\n  Every tool sees ground.areas, which is empty, so "
              f"this yard plans as a bare lot.\n  Move them to `areas` and "
              f"`hardscape`, deciding each area's `state` as you go.")

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
