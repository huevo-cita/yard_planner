#!/usr/bin/env python3
"""The design and drawing practice that every yard shares.

    python3 -m lib.practice                 every rule, with its sources
    python3 -m lib.practice --cite <key>    one rule and the text that supports it
    python3 -m lib.practice --check         the source rules that tools/test_practice.py enforces

The rules live in `practice/rules.json`. The sources live in
`practice/sources.json`. The prose lives in `practice/design.md`,
`practice/drawing.md` and `practice/wildlife.md`. A module reads a number with
`practice.rule("design.mass_sizes")` and does not keep its own copy.

A plant fact goes in the catalog. A yard fact goes in the yard's own files.
This folder holds only how to design and how to draw, so it holds no address.
"""

import argparse
import functools
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "practice")
RULES = os.path.join(ROOT, "rules.json")
SOURCES = os.path.join(ROOT, "sources.json")

# A rule that changes what gets planted or how the map reads needs this many
# independent sources of tier 1 or tier 2.
CRITICAL_MIN_SOURCES = 2
ACCEPTED_TIERS = (1, 2)


@functools.lru_cache(maxsize=1)
def _load():
    with open(RULES) as fh:
        rules = json.load(fh)
    with open(SOURCES) as fh:
        sources = json.load(fh)
    by_id = {src["id"]: src for src in sources.get("sources") or []}
    return rules.get("rules") or {}, by_id


def rules():
    return _load()[0]


def sources():
    return _load()[1]


def rule(key):
    """The value of one rule. A missing rule stops the job and names the key."""
    table = rules()
    if key not in table:
        raise KeyError(f"practice/rules.json has no rule {key!r}")
    return table[key].get("value")


def regional(key, region=None):
    """A rule whose value differs by region. "default" covers the rest."""
    value = rule(key)
    if not isinstance(value, dict):
        return value
    if region and region in value:
        return value[region]
    return value.get("default")


def entry(key):
    table = rules()
    if key not in table:
        raise KeyError(f"practice/rules.json has no rule {key!r}")
    return table[key]


def cite(key):
    """A short citation for one rule, for a finding or a page."""
    item = entry(key)
    names = []
    for ref in item.get("sources") or []:
        src = sources().get(ref.get("id")) or {}
        names.append(src.get("short") or src.get("citation") or ref.get("id"))
    section = item.get("section") or ""
    doc = item.get("doc") or ""
    where = f"{doc}#{section}" if doc and section else doc or section
    return f"{key} ({'; '.join(names)})" + (f" [{where}]" if where else "")


def problems():
    """Every way the rule file falls short of the source rules."""
    out = []
    by_id = sources()
    for src_id, src in by_id.items():
        if src.get("tier") not in ACCEPTED_TIERS:
            out.append(f"source {src_id} is tier {src.get('tier')}, which cannot back a rule")
        if not (src.get("url") or src.get("doi")):
            out.append(f"source {src_id} has no url or doi")
    for key, item in rules().items():
        refs = item.get("sources") or []
        if not refs:
            out.append(f"{key} has no source")
        if not item.get("section"):
            out.append(f"{key} has no section")
        if not item.get("statement"):
            out.append(f"{key} has no statement")
        good = set()
        for ref in refs:
            src = by_id.get(ref.get("id"))
            if src is None:
                out.append(f"{key} cites {ref.get('id')}, which sources.json does not hold")
                continue
            if not (ref.get("support") or "").strip():
                out.append(f"{key} cites {ref.get('id')} with no supporting text")
            if src.get("tier") in ACCEPTED_TIERS:
                good.add(src.get("group") or src["id"])
        if item.get("critical") and len(good) < CRITICAL_MIN_SOURCES:
            out.append(f"{key} is critical and has {len(good)} independent "
                       f"tier 1 or 2 source{'' if len(good) == 1 else 's'}")
    return out


def main():
    ap = argparse.ArgumentParser(description="The shared design and drawing practice.")
    ap.add_argument("--cite", metavar="KEY")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.cite:
        item = entry(args.cite)
        print(f"  {args.cite} = {json.dumps(item.get('value'))}")
        print(f"  {item.get('statement')}")
        for ref in item.get("sources") or []:
            src = sources().get(ref.get("id")) or {}
            print(f"    - tier {src.get('tier')}: {src.get('citation')}")
            print(f"      {src.get('url') or src.get('doi')}")
            print(f"      \"{ref.get('support')}\"")
        return
    if args.check:
        bad = problems()
        for line in bad:
            print(f"  {line}")
        if bad:
            sys.exit(1)
        print(f"  {len(rules())} rules and {len(sources())} sources meet the source rules")
        return
    for key, item in sorted(rules().items()):
        flag = "critical" if item.get("critical") else "        "
        print(f"  {flag}  {key} = {json.dumps(item.get('value'))}")
        print(f"            {cite(key)}")


if __name__ == "__main__":
    main()
