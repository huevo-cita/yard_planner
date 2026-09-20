#!/usr/bin/env python3
"""Which plant a line of the plan is talking about.

    python3 -m lib.plants cloverleaf-austin            every name the design knows
    python3 -m lib.plants cloverleaf-austin --match    every placement, and what it names

A task says where things go in prose, because that is how a person reads it
standing in the bed:

    {"bed": "g03", "at": "with the above",
     "plant": "Turk's cap, inland sea oats, Texas sedge x5"}

Three plants, one string. Anything that wants to put a photograph or a link
beside that line has to work out which records it names, and the obvious way —
search the design's names and take the first hit — answers *Chasmanthium
latifolium* and drops the other two. So the match here is longest-first and
non-overlapping: every name is tried from the longest down, and the span it
claims is removed before the next is tried, so "cedar sedge" cannot also match
as "sedge" and "Four-nerve daisy" beats "daisy".

A name the design does not hold is reported as absent rather than guessed at.
That is the whole value of the exercise: "Texas sedge" appears in no bed of
this design, and finding that out is the point [d44].
"""
import argparse
import json
import os
import re

from . import yards

#: A name is written for a reader, so it carries asides the matcher must drop:
#: "Climbing Royal Gold (existing, east trellis)" and "Milkweed - ASK FOR
#: Asclepias tuberosa OR A. asperula" both name one plant.
PAREN = re.compile(r"\s*\([^)]*\)")
ASIDE = re.compile(r"\s+[-\u2013\u2014]\s+")
CULTIVAR = re.compile(r"\s*['\u2018\u2019][^'\u2018\u2019]*['\u2018\u2019]")

#: "Asclepias tuberosa / A. asperula" is one field naming two acceptable
#: species, and the second is abbreviated to the genus initial.
ABBREV = re.compile(r"^([A-Z])\.\s+(\w+)")


def clean_name(name):
    """The plant's name with the reader's asides taken off."""
    return ASIDE.split(PAREN.sub("", name))[0].strip()


def names_for(plant):
    """Every way the plan might write this plant's name, lowercased.

    A cultivar is indexed both ways. The design calls it "Rosemary 'Tuscan
    Blue'" because the form is the whole point of choosing it, and the
    placement line says "Rosemary" because that is what you say out loud.
    """
    base = clean_name(plant.get("name", ""))
    out = {base}
    plain = CULTIVAR.sub("", base).strip()
    if plain:
        out.add(plain)
    return {n.lower() for n in out if n}


def binomials(plant):
    """Every species this record accepts, expanded.

    Returns a list because one record can legitimately name two: the milkweed
    line takes *Asclepias tuberosa* or *A. asperula*, and both are correct
    plants to come home with.
    """
    raw = (plant.get("botanical") or "").strip()
    if not raw:
        return []
    out, genus = [], None
    for part in (p.strip() for p in raw.split("/")):
        if not part:
            continue
        m = ABBREV.match(part)
        if m and genus:
            part = f"{genus} {m.group(2)}"
        else:
            genus = part.split()[0]
        out.append(part)
    return out


def index(design):
    """Every name the design knows, to the records that answer to it."""
    idx = {}
    for p in design.get("plants", []):
        for name in names_for(p):
            idx.setdefault(name, []).append(p)
    return idx


def match(text, idx):
    """Every design plant named in a free-form string, in the order written.

    Longest-first and non-overlapping. A matched span is blanked before the
    next name is tried, so one stretch of text is claimed once and a short
    name cannot eat a longer one it sits inside.
    """
    low = text.lower()
    taken = [False] * len(low)
    hits = []
    for name in sorted(idx, key=len, reverse=True):
        start = 0
        while True:
            at = low.find(name, start)
            if at < 0:
                break
            end = at + len(name)
            if not any(taken[at:end]):
                for i in range(at, end):
                    taken[i] = True
                hits.append((at, name, idx[name]))
            start = at + 1
    hits.sort()
    return [(name, plants) for _, name, plants in hits]


def placements(task, idx):
    """A task's placement lines, each with the plants it names.

    Every line comes back whether or not anything matched. `unmatched` means
    nothing in the design answers to these words, and that is the finding, so
    dropping the line would hide it.

    `positional` separates the two kinds of line, which read the same and are
    not the same thing. A line carrying a bed and a foot-mark is an
    instruction to put a named plant in the ground at a named spot, and a name
    the design does not hold there is a real disagreement about what gets
    planted. A line carrying square references is about a square of the raised
    bed — "Cut the mesclun", "Check the four Buttercrunch" — where the words
    are a job rather than a purchase, and the crops belong to the rotation
    rather than to `design.json`. Holding the second kind to the first kind's
    standard produces eight complaints for every real one, and a check that
    cries wolf is a check somebody switches off.
    """
    out = []
    for p in ((task.get("where") or {}).get("placements") or []):
        text = p.get("plant", "")
        hits = match(text, idx)
        out.append({
            "at": p.get("at"), "bed": p.get("bed"),
            "squares": p.get("squares"), "text": text,
            "positional": bool(p.get("bed") and p.get("at")),
            "named": [{"name": n, "plant": ps[0],
                       "binomials": binomials(ps[0])} for n, ps in hits],
            "unmatched": not hits,
        })
    return out


def credits(slug):
    """The photograph manifest, or an empty one if no photos were ever fetched."""
    path = os.path.join(yards.yard_dir(slug), "photos", "plants",
                        "credits.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def photo_for(binomial_list, creds):
    """The first verified photograph among these species, or None.

    None is a real answer and gets rendered as one. A picture of the wrong
    plant on a page whose job is stopping the wrong plant coming home is worse
    than no picture, so nothing is substituted from a neighbouring species.
    """
    for b in binomial_list:
        rec = creds.get(b)
        if rec and rec.get("image"):
            return dict(rec, binomial=b)
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--match", action="store_true",
                    help="every placement line, and what it names")
    args = ap.parse_args()

    design = yards.load(args.slug, "design.json") or {}
    idx = index(design)

    if not args.match:
        print(f"  {len(design.get('plants', []))} plants, "
              f"{len(idx)} names they answer to\n")
        for name in sorted(idx):
            p = idx[name][0]
            b = ", ".join(binomials(p)) or "no binomial in the record"
            where = ", ".join(sorted({q.get("zone", "?") for q in idx[name]}))
            print(f"      {name:34s} {b:46s} {where}")
        return

    tasks = (yards.load(args.slug, "tasks.json") or {}).get("tasks", [])
    lines = missed = 0
    for t in tasks:
        rows = placements(t, idx)
        if not rows:
            continue
        print(f"\n  {t['id']}  {t['title']}")
        for r in rows:
            lines += 1
            if r["unmatched"]:
                missed += 1
                print(f"      NO MATCH  {r['text'][:64]}")
                continue
            named = ", ".join(n["name"] for n in r["named"])
            print(f"      {len(r['named'])} named  {r['text'][:52]}")
            print(f"                -> {named}")
    print(f"\n  {lines} placement lines, {missed} naming nothing in design.json")


if __name__ == "__main__":
    main()
