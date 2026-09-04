#!/usr/bin/env python3
"""Plant a fabrication and check `tools/influence.py` sorts it into the right box.

    python3 tools/test_influence.py
    python3 tools/test_influence.py -v

A tool that decides which numbers are load-bearing is itself load-bearing, and
the way it fails is by going quiet: grade everything `maybe`, put nothing in the
believed-but-uncomputed quadrant, and it reads as a clean bill of health on a
record full of unbacked assertions. So the properties tested here are the ones
whose failure is silent.

  the fabrication is sorted    a free-text note asserting "sunniest ground on
                               the lot", carrying no provenance and quoted in
                               PLAN.md, has to come back as an unbacked
                               `judgement` claim in the believed-but-uncomputed
                               quadrant. This is the exact shape of
                               `zones.front_bed.note`, the value that cost this
                               yard five hours of imaginary sun.

  the note is not `named`      and specifically it must not grade as read by
                               code. Every leaf under `zones` is reached by
                               `site["zones"]`, so a scan that counts a
                               wholesale container read as proof grades the note
                               as consumed and agrees with the mistake. This is
                               the single assertion the tool turns on.

  a wildcard tail names nothing  `z.get(f"no_{item}")` reaches one key chosen at
                               runtime, not every key in the container. A list
                               index is the exception, because `spec["x"][i]`
                               genuinely does reach every element.

  iteration is followed        `for key, spec in site["zones"].items():
                               spec.get("label")` has to be recognised as a
                               read of `zones.*.label`. If that analysis breaks,
                               nothing is ever `named`, the load-bearing
                               quadrant empties, and the tool says nothing while
                               looking like it ran.

  short numbers are refused    `0.0` and `6` appear in any document by accident.
                               Reporting those as quoted manufactures evidence
                               that somebody believes a value, which is worse
                               than reporting nothing.

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "tools"))

from lib import yards  # noqa: E402
import influence  # noqa: E402

SLUG = "testyard-influence"

# One planted fabrication, one value nothing reads and nobody quotes, and one
# value that is genuinely both. The zone keys are real ones (`x`, `y`, `label`,
# `area_sqft`) because the point is to test discrimination *within* a container
# the code does read, which is where the failure was.
SITE = {
    "label": "scratch",
    "address": {"lat": 30.3103215, "lon": -97.6982286},
    "boundary": {"points": [[0, 0], [737, 0], [737, 500], [0, 500]]},
    "zones": {
        "planted_bed": {
            "x": [425.5, 534.0],
            "y": [436.6, 484.6],
            "label": "Planted bed",
            "area_sqft": 32.45,
            # THE FABRICATION. No provenance entry, no computation behind it,
            # quoted in PLAN.md below, and no job reads a zone note.
            "note": "sunniest ground on the lot, an evaluative claim with no "
                    "number in it that nothing can ever falsify",
            # Nothing reads this and nothing quotes it: the `neither` quadrant.
            "surveyors_initials": "RJH-1987-plat-sheet-4",
        },
    },
    "provenance": {
        "zones.planted_bed.x": {"source": "measured"},
        "zones.planted_bed.y": {"source": "measured"},
        "zones.planted_bed.area_sqft": {"source": "derived"},
    },
}

# `32.45` is distinctive enough to search for and is read by code through
# `design.zone_areas`, so it should land in `load-bearing`. The note's phrase is
# quoted verbatim, which is what puts it in `believed-but-uncomputed`.
PLAN = """# Scratch plan

The planted bed is 32.45 sq ft of soil inside the edging.

It is the sunniest ground on the lot, an evaluative claim with no number in it
that nothing can ever falsify, so the full-sun palette goes here.
"""

FAILURES = []


def check(ok, name, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        if detail:
            print(f"          {detail}")
        FAILURES.append(name)


def build(root):
    d = os.path.join(root, SLUG)
    os.makedirs(d)
    with open(os.path.join(d, "site.json"), "w") as fh:
        json.dump(SITE, fh, indent=2)
    with open(os.path.join(d, "PLAN.md"), "w") as fh:
        fh.write(PLAN)


def row(rows, path):
    for r in rows:
        if r["path"] == path:
            return r
    return None


def test_sorting(verbose=False):
    root = tempfile.mkdtemp(prefix="influence-test-")
    was = yards.GARDEN_ROOT
    try:
        yards.GARDEN_ROOT = root
        build(root)
        rows = influence.analyse(SLUG)
        if verbose:
            for r in sorted(rows, key=lambda r: r["path"]):
                print(f"        {r['path']:<44} code={r['code']:<6} "
                      f"prose={bool(r['prose'])} "
                      f"quadrant={influence.quadrant(r)}")

        note = row(rows, "zones.planted_bed.note")
        check(note is not None, "the planted note is enumerated at all")
        if note:
            check(note["claim"] == "judgement",
                  "the planted note is classified as a judgement claim",
                  f"got claim={note['claim']!r}")
            check(note["provenance"] is None,
                  "the planted note is reported as unbacked",
                  f"got provenance={note['provenance']!r}")
            check(note["code"] != "named",
                  "the planted note does NOT grade as read by code",
                  f"got code={note['code']!r} via {note['code_evidence']}. A "
                  f"wholesale `zones` read is being counted as proof the leaf "
                  f"is consumed, which is the original bug")
            check(note["prose"] is not None,
                  "the planted note is found quoted in PLAN.md")
            check(influence.quadrant(note) == "believed-but-uncomputed",
                  "the planted note lands in believed-but-uncomputed",
                  f"got {influence.quadrant(note)}")

        area = row(rows, "zones.planted_bed.area_sqft")
        check(area is not None and area["code"] == "named",
              "a zone area is recognised as read by code",
              f"got {area and area['code']!r}. If this fails the iteration "
              f"analysis has broken and nothing will ever grade `named`")
        check(area is not None and
              influence.quadrant(area) == "load-bearing",
              "a read-and-quoted area lands in load-bearing",
              f"got {area and influence.quadrant(area)}")

        dead = row(rows, "zones.planted_bed.surveyors_initials")
        check(dead is not None and influence.quadrant(dead) == "neither",
              "a value nothing reads and nobody quotes lands in neither",
              f"got {dead and influence.quadrant(dead)}")

        targets = influence.targets(rows)
        check("zones.planted_bed.note" in targets,
              "the fabrication is handed to recompute as a target",
              "a value people believe has to be audited even though — "
              "especially though — no code computes it")
        check("zones.planted_bed.surveyors_initials" not in targets,
              "dead weight is not handed to recompute as a target")
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)


def test_wildcard_tail():
    """A runtime-chosen key names nothing; a list index names everything."""
    check(not influence._names_leaf("zones.*.*", "zones.bed.note".split(".")),
          "a wildcard tail on a dict key does not name the leaf",
          "`z.get(f\"no_{item}\")` would otherwise grade every key in the "
          "container as consumed")
    check(influence._names_leaf("zones.*.x.*", "zones.bed.x.1".split(".")),
          "a wildcard tail on a list index does name the leaf",
          "`spec[\"x\"][i]` genuinely reaches every element")
    check(influence._names_leaf("zones.*.label", "zones.bed.label".split(".")),
          "a literal tail names the leaf")
    check(not influence._names_leaf("zones", "zones.bed.label".split(".")),
          "a bare section read does not name a leaf three levels down")


def test_iteration_followed():
    """The real lib, scanned: per-zone and per-tree reads have to be visible.

    This is the assertion that the tool has not gone quiet. `lib.inputs` stops
    at the section, and if this analysis regressed to that granularity every
    grade would collapse to `maybe` with no error anywhere.
    """
    per_job, keys = influence.code_reads()
    everything = {p for pats in per_job.values() for p in pats}
    zone_leaf = sorted(p for p in everything
                       if p.startswith("zones.*.") and not p.endswith("*"))
    check(bool(zone_leaf),
          "per-zone leaf reads are recovered from the source",
          "no `zones.*.<key>` pattern was found in any job's closure, so "
          "container iteration is no longer being followed")
    if zone_leaf:
        print(f"          found {len(zone_leaf)}: "
              + ", ".join(zone_leaf[:6])
              + ("..." if len(zone_leaf) > 6 else ""))
    check("note" in keys,
          "key literals are collected repo-wide for the weaker grade",
          "without this a leaf whose key is read somewhere unrelated would "
          "grade `no`, which overstates the finding")


def test_short_numbers():
    """Numbers too common to search for are refused rather than answered."""
    corpus = {"PLAN.md": {"text": "the bed is 0.0 ft and 6 in and 630.34 ft",
                          "lower": "", "shingles": set()}}
    for value in (0.0, 6, 12):
        where, why = influence.prose_hit("boundary.slope.fall_ft", value,
                                         corpus)
        check(where is None and why == "too common to match",
              f"{value} is refused as too common to match",
              f"got where={where!r} why={why!r}")
    where, why = influence.prose_hit("boundary.slope.fall_ft", 630.34, corpus)
    check(where is not None, "a distinctive number is still matched",
          f"got where={where!r} why={why!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print("\nsorting a planted fabrication")
    test_sorting(args.verbose)
    print("\nwhat counts as code naming a leaf")
    test_wildcard_tail()
    print("\nthe scan has not gone quiet")
    test_iteration_followed()
    print("\nnumbers too common to search for")
    test_short_numbers()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: " + ", ".join(FAILURES))
        raise SystemExit(1)
    print("all passed.")


if __name__ == "__main__":
    main()
