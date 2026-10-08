#!/usr/bin/env python3
"""The mulch line of the bill of materials, on a yard held in memory.

    python3 tools/test_bom.py

It fails when a bed with a top-off of 0 in gets mulch, when a bed with a
top-off gets the standard depth, or when a bed with no top-off does not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import bom, yards  # noqa: E402

SLUG = "bom-test"
SITE = {"zones": {"bed a": {"area_sqft": 100, "mulch_topoff_in": 0.0},
                  "bed b": {"area_sqft": 60, "mulch_topoff_in": 1.0},
                  "bed c": {"area_sqft": 50}},
        "provenance": {}}
DESIGN = {"plants": [{"name": "Aster", "zone": z, "count": 1} for z in ("bed a", "bed b", "bed c")]}
FAILS = []


def check(ok, name):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        FAILS.append(name)


def main():
    real = yards.load
    files = {"site.json": SITE, "design.json": DESIGN}
    yards.load = lambda s, f, default=None: files.get(f, default) if s == SLUG else real(s, f, default)
    try:
        need = bom.requirements(SLUG)
    finally:
        yards.load = real
    mulch = need.get("mulch") or {}
    want = bom.mulch_volume(60, 1.0) + bom.mulch_volume(50, 3.0)
    check(abs(mulch.get("quantity", 0) - want) < 0.01,
          f"mulch is {mulch.get('quantity', 0):.2f} cu ft for beds b and c, want {want:.2f}")
    check(not any("bed a" in why for why in mulch.get("why") or []),
          "a bed with a top-off of 0 in gets no mulch")
    said = " ".join(str(c) for c in need.get(bom.CAVEATS) or [])
    check("bed a" in said, "the caveats name the bed that has no mulch by declaration")
    print(f"\n{len(FAILS)} failure{'' if len(FAILS) == 1 else 's'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
