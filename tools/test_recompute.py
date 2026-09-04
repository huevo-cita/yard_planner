#!/usr/bin/env python3
"""Plant known errors in a yard and fail if `tools/recompute.py` misses them.

    python3 tools/test_recompute.py
    python3 tools/test_recompute.py -v        show every finding

A checker nobody has tried to fool is not evidence of anything. So this builds a
yard whose numbers are wrong in specific, named ways — each one an error that
actually happened on a real yard in this repo — and asserts they come back.

  summed annuals        a doubt card quoting a ratio reached by adding the
                        annual spread to the perennial. `design.check_space`
                        takes the larger of the two, because annuals and
                        perennials in one bed are a succession rather than a
                        crowd. This is the `1.78x` error, and it had already
                        been settled with the wrong figure on the record.

  inflated area_sqft    a derivation string whose own dimensions do not
                        multiply out to the area it produced. Every quantity
                        that scales with bed area then inherits the gap.

  fabricated provenance a provenance entry claiming `measured` for a path with
                        no value behind it. `zones.front_bed.x` did exactly
                        this, and the claim outlived the value it described.

  a note against the model  sun hours written into a zone's `note`, disagreeing
                        with `sun-hours.json`. Four beds on the real yard were
                        out by up to 4.2 h.

  a units slip          inches recorded in a `_ft` field, which makes the depth
                        check pass every plant there is.

  a dead citation       a `[cNN]` in a plan document with no such changelog
                        entry, so the reason for a line is unfindable.

And three negative controls, because a checker that fires on everything is the
same as one that fires on nothing:

  a correct derivation reproduces silently; a price is not swept, because it
  carries no unit the table carries; and a two-significant-digit figure is not
  swept at all.

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
import recompute  # noqa: E402

SLUG = "testyard-recompute"

# Two beds. `good_bed` is right in every respect and must stay silent.
# `bad_bed` carries the planted errors.
#
# good_bed: 24 x 48 in outside, edged all four sides at 3.5 in per edge, so
# 17 x 41 in = 4.84 sq ft. That reproduces, so nothing should be reported.
#
# bad_bed: the derivation says 20 x 36 in, which is 5.0 sq ft, and area_sqft
# says 8.0. The gap is the planted error.
SITE = {
    "label": "scratch",
    "address": {"lat": 30.31, "lon": -97.7},
    "boundary": {"points": [[0, 0], [400, 0], [400, 400], [0, 400]]},
    "zones": {
        "good_bed": {
            "x": [10, 58], "y": [10, 34],
            "label": "Good bed", "label_short": "good",
            "kind": "border",
            "area_sqft": 4.84,
            "area_derivation": "features.beds.good size_in [24, 48], edged all "
                               "four sides so each axis loses 3.5 in twice: "
                               "17 x 41 in.",
            "usable_depth_ft": 1.417,
            "usable_depth_derivation": "24 in outside, edged both sides",
        },
        "bad_bed": {
            "x": [100, 136], "y": [100, 120],
            "label": "Bad bed", "label_short": "bad",
            "kind": "border",
            "area_sqft": 8.0,
            "area_derivation": "features.beds.bad size_in [24, 40], edged all "
                               "four sides: 20 x 36 in.",
            # PLANTED: inches in a feet field.
            "usable_depth_ft": 20.5,
            "usable_depth_derivation": "24 in outside, edged both sides",
            # PLANTED: contradicts sun-hours.json below, which says 2.0 h Jun.
            "note": "full sun, 7.5 h Jun / 6.0 h Dec",
        },
    },
    "features": {
        "beds": {
            "good": {"size_in": [24, 48]},
            "bad": {"size_in": [24, 40]},
        },
    },
    "provenance": {
        "zones.good_bed.x": {"source": "measured"},
        "zones.bad_bed.x": {"source": "measured"},
        # PLANTED: a hard claim about a value that is not in the file.
        "zones.retired_bed.x": {"source": "measured",
                                "note": "from the measured bed dimensions"},
    },
}

# `bad_bed`: perennial 2 x pi x (2/2)^2 = 6.28, annual 1 x pi x (1.5/2)^2 =
# 1.77. `need` is max = 6.28, and the summed figure is 8.05. Over the 8.0 sq ft
# area that is a ratio of 0.79 the right way and 1.01 the wrong way, and the
# card below quotes the wrong one.
DESIGN = {
    "plants": [
        {"name": "Perennial A", "zone": "bad_bed", "count": 2,
         "mature_spread_ft": 2.0, "annual": False},
        {"name": "Annual B", "zone": "bad_bed", "count": 1,
         "mature_spread_ft": 1.5, "annual": True},
        {"name": "Perennial C", "zone": "good_bed", "count": 1,
         "mature_spread_ft": 2.0, "annual": False},
        # PLANTED: a zone site.json does not have.
        {"name": "Orphan D", "zone": "vanished_bed", "count": 1,
         "mature_spread_ft": 1.0, "annual": False},
    ],
}

SUN = {
    "by_zone_and_month": {
        "good": {"Jun": {"effective": 4.0}, "Dec": {"effective": 3.0}},
        "bad": {"Jun": {"effective": 2.0}, "Dec": {"effective": 1.0}},
    },
}

# PLANTED: the ratio and the spread are both the summed figures, and the card is
# already settled carrying them — which is the failure exactly as it happened.
DOUBTS = {
    "cards": [
        {"id": "d1", "status": "settled", "kind": "fact",
         "question": "Is bad_bed overplanted?",
         "detail": "bad_bed needs 8.05 sq ft of mature spread in 8.0 sq ft of "
                   "soil, so it is planted 1.01x over its area.",
         "answer": "accepted at 1.01x",
         "options": []},
        # A NEGATIVE CONTROL: a price carries no unit the table carries, so it
        # must not be swept however unmatched it looks.
        {"id": "d2", "status": "open", "kind": "fact",
         "question": "Is the 1-gallon class median really $10.50?",
         "detail": "Built from exactly two local quotes, 127 days old.",
         "options": []},
    ],
}

# PLANTED: [c99] does not exist. [c1] does.
PLAN = """# Scratch plan

Plant the perennials in bad_bed [c1].

Water them weekly [c99].
"""

CHANGELOG = {"entries": [{"id": "c1", "kind": "rationale",
                          "headline": "why bad_bed", "why": "it was there"}]}

FAILURES = []


def check(ok, name, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        if detail:
            print(f"          {detail}")
        FAILURES.append(name)


def build(root):
    d = os.path.join(root, SLUG)
    os.makedirs(os.path.join(d, "maps"))
    for name, data in (("design.json", DESIGN), ("sun-hours.json", SUN),
                       ("doubts.json", DOUBTS), ("changelog.json", CHANGELOG),
                       ("conditions.json", {"soil": {"ph": 8.2}}),
                       ("vision.json", {})):
        with open(os.path.join(d, name), "w") as fh:
            json.dump(data, fh, indent=2)
    with open(os.path.join(d, "PLAN.md"), "w") as fh:
        fh.write(PLAN)
    # site.json written last and stamped newest, so every derived file above is
    # stale against it. That is the planted staleness.
    with open(os.path.join(d, "site.json"), "w") as fh:
        json.dump(SITE, fh, indent=2)
    now = os.path.getmtime(os.path.join(d, "site.json"))
    for name in ("sun-hours.json", "design.json"):
        os.utime(os.path.join(d, name), (now - 86400 * 3, now - 86400 * 3))
    return d


def has(findings, check_name, needle):
    return [f for f in findings
            if f["check"] == check_name
            and (needle in f["what"] or needle in f["detail"])]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    root = tempfile.mkdtemp(prefix="recompute-test-")
    was = yards.GARDEN_ROOT
    try:
        yards.GARDEN_ROOT = root
        build(root)
        table, checks, numbers = recompute.run(SLUG)
        if args.verbose:
            print("\n  -- table")
            for name, e in sorted(table.items()):
                print(f"     {e['value']:10.3f}  {name}")
            print("\n  -- checks")
            for f in checks:
                print(f"     [{f['check']}] {f['what']}: {f['detail']}")
            print("\n  -- numbers")
            for f in numbers:
                print(f"     [{f['kind']}] {f['where']}: {f['number']} "
                      f"{f['unit']} -> {f['nearest']}")

        print("\nthe table goes through lib.design, not its own arithmetic")
        need = table.get("bad_bed need sq ft")
        summed = table.get("bad_bed WRONG: perennial + annual summed sq ft")
        check(need is not None and abs(need["value"] - 6.283) < 0.01,
              "need is max(perennial, annual), not the sum",
              f"got {need and need['value']}. If this is 8.05 the table has "
              f"its own copy of check_space and has drifted from it")
        check(summed is not None and abs(summed["value"] - 8.06) < 0.02,
              "the summed figure is carried too, labelled WRONG",
              f"got {summed and summed['value']}")

        print("\nplanted errors")
        check(bool([f for f in numbers if f["kind"] == "wrong method"
                    and f["unit"] == "ratio"]),
              "a ratio reached by summing the annuals is caught",
              f"numbers: {[(f['kind'], f['number'], f['unit']) for f in numbers]}")
        check(bool([f for f in numbers if f["kind"] == "wrong method"
                    and f["unit"] == "sq ft"]),
              "a spread figure reached by summing the annuals is caught")
        wrong = [f for f in numbers if f["kind"] == "wrong method"]
        check(all(f["instead"] for f in wrong),
              "every wrong-method finding carries the corrected figure",
              "a finding that says only 'this is wrong' leaves the reader "
              "exactly where they started")

        check(bool(has(checks, "derivations", "bad_bed")),
              "a derivation whose dimensions do not multiply out is caught",
              "20 x 36 in is 5.0 sq ft and area_sqft says 8.0")
        check(bool(has(checks, "provenance", "retired_bed")),
              "a `measured` claim about an absent value is caught")
        check(bool(has(checks, "zone notes", "bad_bed")),
              "a zone note disagreeing with sun-hours.json is caught")
        check(bool(has(checks, "units", "bad_bed.usable_depth_ft")),
              "inches in a feet field are caught")
        check(bool(has(checks, "cross-file", "Orphan D")),
              "a plant in a zone site.json does not have is caught",
              "check_space finds no area for it and silently passes")
        check(bool(has(checks, "staleness", "c99")),
              "a citation with no changelog entry is caught")
        check(bool(has(checks, "staleness", "sun-hours.json")),
              "a derived file older than site.json is caught")

        print("\nnegative controls")
        check(not has(checks, "derivations", "good_bed"),
              "the correct derivation reproduces silently",
              f"got {has(checks, 'derivations', 'good_bed')}")
        check(not has(checks, "units", "good_bed"),
              "the correct bed raises no units finding")
        check(not [f for f in numbers if f["number"] in ("10.50", "127")],
              "a price and a day count are not swept",
              "neither carries a unit the table carries, so matching them "
              "against bed areas would be a coincidence dressed as a lead")
        check(not [f for f in numbers if f["number"] == "8.0"],
              "a two-significant-digit figure is not swept")
    finally:
        yards.GARDEN_ROOT = was
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: " + ", ".join(FAILURES))
        raise SystemExit(1)
    print("all passed.")


if __name__ == "__main__":
    main()
