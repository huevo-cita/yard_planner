#!/usr/bin/env python3
"""Height, wildlife, and color checks. They do not rewrite a design."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import design


def plant(**kwargs):
    base = {"count": 1, "zone": "bed_g02", "layer": "back", "role": "fill",
            "mature_height_ft": 2.0, "bloom": []}
    base.update(kwargs)
    return base


VISION = {"purpose": ["wildlife habitat - specifically butterflies and frogs"]}


def says(objs, about, needle):
    return any(obj["about"] == about and needle in obj["say"] for obj in objs)


def check(ok, name):
    print(("  ok   " if ok else "  FAIL ") + name)
    return 0 if ok else 1


def main():
    failed = 0
    stepped = {"plants": [
        plant(name="Short", layer="front", mature_height_ft=0.8),
        plant(name="Tall", layer="back", mature_height_ft=3.0),
    ]}
    failed += check(
        not design.check_layers(stepped),
        "a short front row passes")

    jumped = {"plants": [
        plant(name="Tall front", layer="front", mature_height_ft=4.0),
        plant(name="Short back", layer="back", mature_height_ft=1.0),
    ]}
    failed += check(
        says(design.check_layers(jumped), "height", "taller layer"),
        "a tall front row fails")

    bare = {"plants": [
        plant(name="Gulf muhly", botanical="Muhlenbergia capillaris",
              role="back-row structure", mature_height_ft=2.8,
              bloom=["Oct", "Nov"]),
    ]}
    wildlife = design.check_wildlife(bare, VISION)
    failed += check(
        says(wildlife, "wildlife", "no nectar plant"),
        "a structure grass does not count as nectar")
    failed += check(
        says(wildlife, "wildlife", "no larval host"),
        "a bed with no host fails")
    failed += check(
        design.check_wildlife(bare, {"purpose": ["curb appeal"]}) == [],
        "a yard with no wildlife ask skips the check")

    fed = {"plants": [
        plant(name="Mealy blue sage", botanical="Salvia farinacea",
              role="long-season nectar", count=3, mature_height_ft=2.5,
              bloom=["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]),
        plant(name="Lindheimer's senna", botanical="Senna lindheimeriana",
              layer="middle", role="butterfly nursery", mature_height_ft=4.0,
              bloom=["Sep", "Oct"]),
    ]}
    fed_out = design.check_wildlife(fed, VISION)
    failed += check(
        not any(obj["level"] == "serious" for obj in fed_out),
        "nectar plus a host passes")

    missing = {"plants": [
        plant(name="Mystery nectar", botanical="Nonesuch inventa",
              nectar=True, bloom=["Apr"]),
    ]}
    failed += check(
        says(design.check_color(missing, VISION), "color", "no flower color"),
        "a missing flower color is named")

    window = {"limits": [{
        "zone": "bed_g02", "max_height_ft": 5, "max_spread_ft": 5,
        "hard_height_ft": 6, "hard_spread_ft": 6,
        "exempt": ["Rosa 'KORwest'"], "short": "It would cover the window."}]}
    sized = {"plants": [
        plant(name="Under", mature_height_ft=3.0, mature_spread_ft=3.0),
        plant(name="Near", mature_height_ft=5.5, mature_spread_ft=2.0),
        plant(name="Over", mature_height_ft=2.0, mature_spread_ft=8.0),
        plant(name="Rose", botanical="Rosa 'KORwest'", mature_height_ft=11.0),
        plant(name="Elsewhere", zone="bed_g05", mature_height_ft=9.0),
    ]}
    limits = design.check_limits(sized, window)
    named = {obj["say"].split(" in ")[0]: obj["level"] for obj in limits}
    failed += check(named.get("Near") == "note",
                    "a plant between the design and hard limits is a note")
    failed += check(named.get("Over") == "serious",
                    "a plant past the hard width limit is serious")
    failed += check("Under" not in named and "Rose" not in named,
                    "a plant under the limit and an exempt rose pass")
    failed += check("Elsewhere" not in named,
                    "the limit holds only for its own zone")
    failed += check(says(limits, "limit", "It would cover the window."),
                    "the finding gives the reason from the vision")

    print()
    print("FAILED" if failed else "all passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
