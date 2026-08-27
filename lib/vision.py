#!/usr/bin/env python3
"""What the person actually wants, in a form a design can be checked against.

    python3 -m lib.vision <slug>            what is recorded
    python3 -m lib.vision <slug> --init     start an empty one
    python3 -m lib.vision <slug> --check    contradictions worth raising

`site.json` and `conditions.json` are facts. This is taste, and taste is not a
fact, so it is recorded differently: never as a measurement, always as a stated
preference with a strength attached, and with the images or words it came from
kept alongside so it can be re-read rather than re-argued.

The strength matters more than the content. A design that violates a `must` has
failed. A design that violates a `nice_to_have` has made a trade, which is a
normal thing for a design to do, and it should say so.

    must            non-negotiable. Violating it means starting over
    strong          they will notice and mind
    nice_to_have    they would enjoy it, and it loses to any real constraint

The point of writing taste down
-------------------------------
Two failures this exists to prevent.

The first is the assistant's taste quietly substituting for theirs. Left
unrecorded, a design drifts toward whatever the model has seen most of, which is
a particular kind of tasteful grass-and-gravel minimalism that many people
actively dislike.

The second is the contradiction that nobody notices until the plants are in. A
person can sincerely want a cottage garden, no maintenance, and a tidy edge, and
those three do not coexist. Finding that in conversation costs a question.
Finding it in August costs the planting.
"""
import argparse
import datetime
import json

from . import yards

STRENGTHS = ["must", "strong", "nice_to_have"]

# Every field, what it is for, and whether a design can proceed without it.
FIELDS = [
    ("purpose", "what the yard is for, in their words", True),
    ("style", "the look, with the words they used rather than a category", True),
    ("maintenance_appetite", "hours a week they want to spend once it is in, "
                             "and how they feel about that number", True),
    ("must_keep", "what stays, whatever else changes", True),
    ("dislikes", "what they do not want, and why if they said", True),
    ("target_date", "the date it has to be right by, and what happens then", True),
    ("palette", "colours wanted and colours refused", False),
    ("privacy", "what they want screened, and from where", False),
    ("wildlife", "pollinators, birds, and whether deer or rabbits are a problem",
     False),
    ("edibles", "what they want to eat out of it", False),
    ("water", "how they feel about watering, and whether a hose reaches", False),
    ("pets_and_children", "who uses the yard and what that rules out", False),
    ("budget_feel", "not the number, which lives in conditions.json, but "
                    "whether this is a splurge or a squeeze", False),
    ("references", "boards, images and links, with what was drawn from each",
     False),
]

REQUIRED = [k for k, _, req in FIELDS if req]

# Wants that routinely turn out to be incompatible. Each is a real trade rather
# than a mistake, so the check names the trade and does not refuse anything.
TENSIONS = [
    (["cottage", "wildflower", "meadow", "naturalistic", "informal"],
     ["low maintenance", "no maintenance", "tidy", "manicured", "neat", "crisp"],
     "A cottage or meadow planting is high-input for the first two years and "
     "never looks crisp. The version that works is a loose planting inside a "
     "hard edge — steel, stone or a mown strip — because the eye reads the edge "
     "as intent and forgives the middle"),
    (["lawn", "grass", "turf"],
     ["drought", "no watering", "xeriscape", "low water", "native only"],
     "A lawn is the thirstiest thing in most yards. Either keep it small and "
     "deliberate as a place to stand, or replace it with a walkable groundcover "
     "or gravel. Half-hearted lawn in a dry climate looks bad and costs the most"),
    (["shade garden", "woodland", "ferns", "hosta"],
     ["vegetables", "tomatoes", "cut flowers", "roses"],
     "These want opposite light. Both are possible in one yard, in different "
     "zones — which is what the sun model is for — but not in the same bed"),
    (["evergreen", "year-round", "always green", "structure"],
     ["pollinator", "native", "wildflower", "prairie"],
     "Most native pollinator plants die back and look like nothing from November "
     "to March. The fix is a structural spine of evergreens or a few shrubs, "
     "with the perennials among them, not either one alone"),
    (["fast", "instant", "this season", "quick"],
     ["cheap", "budget", "inexpensive", "on a shoestring"],
     "Instant costs money because it means buying size. Cheap costs time because "
     "it means buying small and waiting two to three years. Pick which one is "
     "the real constraint; a plan that pretends both are is a plan that "
     "disappoints on both"),
    (["fruit trees", "orchard", "fruit"],
     ["low maintenance", "no spraying", "no maintenance"],
     "Most tree fruit needs pruning, thinning and some pest management. Figs, "
     "persimmons, pomegranates and jujubes are the genuinely low-input ones "
     "where climate allows"),
    (["deer"],
     ["hosta", "tulip", "roses", "daylily"],
     "Those are the four things deer eat first. Either the fence is the design "
     "or the plant list changes"),
]


def blank(slug):
    return {"yard": slug, "recorded": datetime.date.today().isoformat(),
            "purpose": None, "style": None, "maintenance_appetite": None,
            "must_keep": [], "dislikes": [], "target_date": None,
            "references": [], "notes": []}


def want(text, strength="strong", source=None, applies_to=None):
    """One recorded preference. `source` is where it came from — an image, a
    board, or a sentence they said — so it can be re-read later."""
    if strength not in STRENGTHS:
        raise ValueError(f"strength must be one of {', '.join(STRENGTHS)}")
    w = {"want": text, "strength": strength}
    if source:
        w["source"] = source
    if applies_to:
        w["applies_to"] = applies_to
    return w


def _texts(vision):
    """Every string anywhere in the vision, lowered, for tension matching."""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v.lower())
        elif isinstance(v, dict):
            for k, sub in v.items():
                if k not in ("source", "yard", "recorded"):
                    walk(sub)
        elif isinstance(v, list):
            for sub in v:
                walk(sub)
    walk(vision)
    return out


def check(vision):
    """Contradictions and thin spots. Raises questions; refuses nothing."""
    issues = []
    for key, what, required in FIELDS:
        if required and not vision.get(key):
            issues.append({"kind": "missing", "field": key,
                           "say": f"nothing recorded for {what}"})

    blob = " | ".join(_texts(vision))
    for a_words, b_words, resolution in TENSIONS:
        a = [w for w in a_words if w in blob]
        b = [w for w in b_words if w in blob]
        if a and b:
            issues.append({"kind": "tension", "between": [a[0], b[0]],
                           "say": f"they have asked for both {a[0]} and {b[0]}",
                           "resolution": resolution})

    musts = [w for w in _wants(vision) if w.get("strength") == "must"]
    if len(musts) > 8:
        issues.append({"kind": "too_many_musts", "count": len(musts),
                       "say": f"{len(musts)} things are marked must. When "
                              f"everything is non-negotiable the design has no "
                              f"room to trade, and the first real constraint "
                              f"breaks the whole plan rather than one part of it. "
                              f"Ask which three actually are"})
    return issues


def _wants(vision):
    out = []
    for v in vision.values():
        if isinstance(v, list):
            out += [w for w in v if isinstance(w, dict) and "want" in w]
        elif isinstance(v, dict) and "want" in v:
            out.append(v)
    return out


def summary(vision):
    if not vision:
        return "no vision recorded"
    L = [f"  purpose      {vision.get('purpose') or '-'}",
         f"  style        {vision.get('style') or '-'}",
         f"  maintenance  {vision.get('maintenance_appetite') or '-'}",
         f"  target date  {vision.get('target_date') or '-'}"]
    for key in ("must_keep", "dislikes"):
        vals = vision.get(key) or []
        if vals:
            L.append(f"  {key:12s} " + "; ".join(
                v.get("want", str(v)) if isinstance(v, dict) else str(v)
                for v in vals))
    refs = vision.get("references") or []
    if refs:
        L.append(f"  references   {len(refs)} recorded")
    musts = [w for w in _wants(vision) if w.get("strength") == "must"]
    if musts:
        L.append("  musts:")
        for w in musts:
            L.append(f"    - {w['want']}")
    return "\n".join(L)


def report(slug):
    vision = yards.load_vision(slug)
    print(f"{slug} — what they want\n")
    print(summary(vision))
    issues = check(vision)
    if not issues:
        print("\n  nothing contradictory, nothing missing")
        return
    print(f"\n  {len(issues)} things to raise:\n")
    for i in issues:
        print(f"  - {i['say']}")
        if i.get("resolution"):
            for line in _wrap(i["resolution"], 72):
                print(f"      {line}")


def _wrap(text, width):
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.init:
        if yards.load(args.slug, "vision.json"):
            print(f"{args.slug} already has a vision.json; not overwriting")
            return
        print(f"wrote {yards.save(args.slug, 'vision.json', blank(args.slug))}")
        return
    if args.json:
        print(json.dumps(check(yards.load_vision(args.slug)), indent=2))
        return
    report(args.slug)


if __name__ == "__main__":
    main()
