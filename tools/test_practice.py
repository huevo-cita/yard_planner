#!/usr/bin/env python3
"""The shared practice holds up to its own source rules.

    python3 tools/test_practice.py

The test fails when one of these conditions is true:

- A rule has no source, no section or no statement.
- A rule rests on a tier 3 source.
- A critical rule has fewer than two independent tier 1 or 2 sources.
- The section of a rule is not a heading in its document.
- No module in lib/ reads a rule.
- A module still holds its own copy of a practice number.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lib import practice  # noqa: E402

FAILS = []


def check(ok, message):
    if ok:
        print(f"  ok    {message}")
    else:
        print(f"  FAIL  {message}")
        FAILS.append(message)


def _lib_text():
    out = {}
    for name in sorted(os.listdir(os.path.join(HERE, "lib"))):
        if name.endswith(".py") and name != "practice.py":
            with open(os.path.join(HERE, "lib", name)) as fh:
                out[name] = fh.read()
    return out


def _anchors(doc):
    """The section numbers and heading words of one practice document."""
    path = os.path.join(practice.ROOT, doc)
    if not os.path.exists(path):
        return None
    found = set()
    with open(path) as fh:
        for line in fh:
            match = re.match(r"#{2,4}\s+(\d+(?:\.\d+)*)?\.?\s*(.*)", line)
            if not match:
                continue
            number, words = match.groups()
            if number:
                found.add(number)
            slug = re.sub(r"[^a-z0-9]+", "-", words.lower()).strip("-")
            if slug:
                found.add(slug)
            found.update(re.findall(r"`([a-z_.]+)`", words))
    return found


# A literal that a module held before practice/ existed. It must not come back.
RETIRED = [
    ("design.py", "max(heights) - min(heights) < 0.4"),
    ("design.py", "if feet < 0.5:"),
    ("design.py", "len(colors) > 3"),
    ("niches.py", '("edging", 0.0, 1.0, 5)'),
    ("scheme.py", "spacing_fraction"),
    ("scheme.py", "stroke-dasharray:5 3"),
]


def main():
    problems = practice.problems()
    for line in problems:
        check(False, line)
    check(not problems, f"{len(practice.rules())} rules and "
                        f"{len(practice.sources())} sources meet the source rules")

    for src_id, src in practice.sources().items():
        check(src.get("tier") in practice.ACCEPTED_TIERS,
              f"source {src_id} is tier {src.get('tier')}")

    anchors = {}
    for key, item in practice.rules().items():
        doc = item.get("doc")
        if not doc:
            check(False, f"{key} names no document")
            continue
        if doc not in anchors:
            anchors[doc] = _anchors(doc)
        if anchors[doc] is None:
            check(False, f"{key} names {doc}, which does not exist")
            continue
        check(str(item.get("section")) in anchors[doc],
              f"{key} section {item.get('section')} is a heading in {doc}")

    text = _lib_text()
    joined = "\n".join(text.values())
    for key in practice.rules():
        check(f'"{key}"' in joined or f"'{key}'" in joined,
              f"{key} is read by a module in lib/")

    for name, literal in RETIRED:
        check(literal not in text.get(name, ""),
              f"{name} no longer holds {literal!r}")

    for key, item in practice.rules().items():
        value = item.get("value")
        if isinstance(value, list) and len(value) >= 3 and all(
                isinstance(v, (int, float)) for v in value):
            spelled = json.dumps(value)
            holders = [name for name, body in text.items() if spelled in body]
            check(not holders, f"no module copies {key} = {spelled}")

    print()
    print(f"{len(FAILS)} failure{'' if len(FAILS) == 1 else 's'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
