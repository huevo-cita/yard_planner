#!/usr/bin/env python3
"""Re-derive every number a yard asserts, from the data it claims to come from.

    python3 tools/recompute.py <slug>              everything
    python3 tools/recompute.py <slug> --table      the canonical quantities
    python3 tools/recompute.py <slug> --numbers    only the prose sweep
    python3 tools/recompute.py <slug> --checks     only the deterministic checks
    python3 tools/recompute.py <slug> --json

Exits non-zero when there are findings, like `lib.sourcing --check`. Read-only:
it computes and reports, and files nothing. Never gated, because this is how a
doubt gets settled rather than something that needs settling first.

Why this exists
---------------
A spot-check of four doubt cards on this repo's own yard found arithmetic errors
in three of them. Not disputed judgements — arithmetic. One card said a bed was
1.78x overplanted; the figure was reached by adding the annuals to the
perennials, which is the one thing `design.check_space` does not do, because
annuals and perennials in a bed are a succession rather than a crowd. The real
number is 1.58x. It had already been settled, and the settlement carried the
wrong figure forward.

Every one of those errors was in a document, and every one of them was
reproducible from data that was sitting right there. So this recomputes.

How the number sweep works, and why it is a heuristic on purpose
---------------------------------------------------------------
First a canonical table is built: every quantity the yard could legitimately be
quoting, computed **through `design.footprint` and `design.zone_areas`**, not
reimplemented. That matters more than it looks. A checker with its own copy of
the spacing arithmetic drifts from the real check, and then agrees with the code
on nothing and with the documents on nothing, and gets switched off. Computing
through the same functions means a finding here is a real disagreement.

The table deliberately includes the *wrong* methods alongside the right ones —
`ratio if annuals are summed` sits next to `ratio` — because the useful output
is not "47.9 matches nothing" but "47.9 is the perennial and annual spreads
added together, and the check takes the larger of the two."

Then every number in every doubt card and every plan document is matched against
that table. Anything matching nothing is reported **with its nearest
recomputed neighbour**, which is what turned `47.9` and `33.1` from anomalies
into diagnoses.

This is a heuristic and the output says so. A number can legitimately come from
somewhere the table does not reach — a supplier's price, a catalogue spacing, a
date. So an unmatched number is reported as "unmatched, nearest is X" and never
as "wrong". Numbers carrying fewer than three significant digits are skipped
entirely: `6`, `12` and `3.5` appear in any document by accident, and a checker
that cries wolf on those is one nobody reads twice.

The deterministic checks
------------------------
Six things that are either right or wrong, with no judgement in them:

    derivations   every `area_derivation` and `usable_depth_derivation` string
                  re-multiplied against the `size_in` it cites, and against the
                  `area_sqft` it produced
    provenance    claims of `measured`, `lidar`, `parcel` or `survey` on values
                  that are not there. `zones.front_bed.x` claimed `measured`
                  for a fabricated box, and the entry outlived the value
    zone notes    the sun figures written into a zone's `note` against
                  `sun-hours.json`, which is the file that actually knows
    units         the inches / feet / square-feet boundaries, which is the
                  likeliest remaining bug class and the hardest to see
    cross-file    zones named in `design.json` and `sun-hours.json` that
                  `site.json` no longer has, and plant counts across files
    staleness     derived files older than the inputs they were derived from,
                  and `[cNN]` citations pointing at changelog entries that do
                  not exist

What this cannot do
-------------------
It cannot tell you a measurement is wrong, only that it disagrees with another
number in the record. Where two sources disagree it reports both and does not
adjudicate. It does not check prices against suppliers — that is
`lib.sourcing --check`. And it says nothing about whether the design is any
good.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from lib import design as design_mod  # noqa: E402
from lib import inputs, siteschema, solar, yards  # noqa: E402
import influence  # noqa: E402

# Provenance sources that assert somebody observed the thing. An entry making
# one of these claims about a value that is not in the file is the failure this
# was written for.
HARD_SOURCES = ("measured", "lidar", "parcel", "survey", "photo", "osm")

# Edging conventions the record uses, in inches per edged axis. A deduction that
# is not one of these and is not itself cited in the derivation string is worth
# a human's attention.
EDGE_DEDUCTIONS = (0.0, 1.5, 3.0, 3.5, 7.0)

DOCS = ("PLAN.md", "SCHEDULE.md", "SOWING-CALENDAR.md", "SOURCING.md",
        "SITE-WALK.md", "CALENDAR.md")

MULCH_DEPTHS = (2.0, 3.0, 4.0)

# Match tolerance for the prose sweep: half a percent, or a twentieth of a unit,
# whichever is looser. Tighter than this and every rounded figure in every
# document is a finding.
def _matches(a, b):
    return abs(a - b) <= max(0.005 * max(abs(a), abs(b)), 0.05)


# ------------------------------------------------------- the canonical table

def canonical(slug):
    """Every quantity the yard could legitimately be quoting, recomputed.

    Keyed by a human-readable name, because the name is what makes an unmatched
    number into a diagnosis. Computed through `lib.design` throughout, so this
    cannot drift from the check it is auditing.
    """
    site = yards.load(slug, "site.json") or {}
    dsn = yards.load(slug, "design.json") or {}
    sun = yards.load(slug, "sun-hours.json") or {}
    cond = yards.load(slug, "conditions.json") or {}
    table = {}

    def put(name, value, how, instead=None):
        """`instead` names the right way to compute a deliberately-wrong entry."""
        if value is None:
            return
        table[name] = {"value": float(value), "how": how, "instead": instead}

    areas = design_mod.zone_areas(site)
    zones = site.get("zones") or {}

    by_zone = {}
    for p in dsn.get("plants", []):
        if p.get("zone") and p.get("mature_spread_ft"):
            by_zone.setdefault(p["zone"], []).append(p)

    for zname, plants in sorted(by_zone.items()):
        key = design_mod.resolve_site_zone(site, zname) or zname
        net = areas.get(key)
        perennial = sum(design_mod.footprint(p) for p in plants
                        if not p.get("annual"))
        annual = sum(design_mod.footprint(p) for p in plants if p.get("annual"))
        need = max(perennial, annual)
        put(f"{key} perennial spread sq ft", perennial,
            "design.footprint over the non-annuals, vines excluded")
        put(f"{key} annual spread sq ft", annual,
            "design.footprint over the annuals")
        put(f"{key} need sq ft", need,
            "max(perennial, annual) — what design.check_space uses")
        put(f"{key} WRONG: perennial + annual summed sq ft", perennial + annual,
            "the two added rather than maxed. NOT the check. Here so that a "
            "number arrived at this way is recognised rather than merely "
            "unmatched",
            instead=f"{key} need sq ft")
        if net:
            put(f"{key} net area sq ft", net,
                "design.zone_areas: area_sqft less unplantable_sqft")
            put(f"{key} ratio", need / net, "need / net area")
            put(f"{key} WRONG: ratio with annuals summed",
                (perennial + annual) / net,
                "the 1.78x-class error: summed numerator over net area",
                instead=f"{key} ratio")
            put(f"{key} coverage pct", 100 * need / net, "need / net area x 100")

    for key, z in sorted(zones.items()):
        if not isinstance(z, dict):
            continue
        gross = z.get("area_sqft")
        net = areas.get(key)
        put(f"{key} gross area sq ft", gross, "zones.{}.area_sqft".format(key))
        if net is not None and gross is not None and abs(net - gross) > 0.01:
            put(f"{key} unplantable sq ft", float(gross) - float(net),
                "gross less net, from zone_areas")
        depth = z.get("usable_depth_ft")
        put(f"{key} usable depth ft", depth, "zones.{}.usable_depth_ft"
            .format(key))
        if depth:
            put(f"{key} usable depth in", float(depth) * 12, "depth x 12")
            overhang = z.get("canopy_overhang_ft") or 0
            put(f"{key} canopy reach ft", float(depth) + float(overhang),
                "usable_depth_ft + canopy_overhang_ft, what _check_depth uses")
        for d in MULCH_DEPTHS:
            if net:
                put(f"{key} mulch cu ft at {d:g} in (net)", net * d / 12.0,
                    "net area x depth / 12")
            if gross:
                put(f"{key} mulch cu ft at {d:g} in (gross)",
                    float(gross) * d / 12.0, "gross area x depth / 12")

    # The ornamental set as a whole, because that is how mulch gets bought and
    # how `d9`'s figure was arrived at — from one of these, and it matched
    # neither.
    orn = [k for k in zones if re.fullmatch(r"bed_g0[1-9]", k)]
    for d in MULCH_DEPTHS:
        net_total = sum(areas.get(k) or 0 for k in orn)
        gross_total = sum(float((zones[k] or {}).get("area_sqft") or 0)
                          for k in orn)
        if net_total:
            put(f"ornamental beds mulch cu ft at {d:g} in (net)",
                net_total * d / 12.0,
                f"{len(orn)} beds, net area, x depth / 12")
        if gross_total:
            put(f"ornamental beds mulch cu ft at {d:g} in (gross)",
                gross_total * d / 12.0,
                f"{len(orn)} beds, gross area, x depth / 12")
    put("ornamental beds net area sq ft",
        sum(areas.get(k) or 0 for k in orn) or None, f"{len(orn)} beds, net")
    put("ornamental beds gross area sq ft",
        sum(float((zones[k] or {}).get("area_sqft") or 0) for k in orn) or None,
        f"{len(orn)} beds, gross")

    # Sun, per zone, straight out of the model rather than off a note. Both
    # windows, and each named: a document quoting 6.5 h for a bed is quoting
    # one of these two and does not usually say which, and they differ by more
    # than the tolerance a sweep would forgive.
    for key in sorted(zones):
        for label, months in (
                ("annual mean", list(solar.MONTHS)),
                ("growing season mean",
                 list(design_mod.DEFAULT_LIGHT_MONTHS)),
                ("Jun", ["Jun"]), ("Dec", ["Dec"])):
            h = design_mod.zone_hours(sun, site, key, months)
            put(f"{key} sun h {label}", h,
                f"design.zone_hours from sun-hours.json, {label}")

    for p in dsn.get("plants", []):
        if p.get("mature_spread_ft"):
            put(f"plant {p['name'][:40]} footprint sq ft",
                design_mod.footprint(p),
                f"pi r^2 x count {p.get('count', 1)}, spread "
                f"{p['mature_spread_ft']} ft"
                + (", vine so zero" if p.get("layer") == "vine" else ""))

    # The band itself, so that a document quoting the ceiling it is being
    # judged against is not reported as quoting an unrecognised ratio.
    put("spacing band floor ratio", design_mod.COVER_FLOOR,
        "design.COVER_FLOOR")
    put("spacing band ceiling ratio", design_mod.COVER_CEILING,
        "design.COVER_CEILING")

    soil = (cond or {}).get("soil") or {}
    put("soil pH", soil.get("ph"), "conditions.json soil.ph")
    return table, site, dsn, sun, cond


# --------------------------------------------------------- the number sweep

NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")

# A number is only swept when it carries a unit that ties it to something in the
# table. Sweeping every number instead gave 327 findings on this yard, nearly
# all of them years, citations, prices and bird-mortality statistics matched
# against whatever recomputed quantity happened to be numerically nearest — a
# sun figure "nearest" a mulch volume is not a diagnosis, it is a coincidence
# dressed as one, and 300 of those is how a check gets switched off in a week.
#
# `ft` and `in` are deliberately out. The table's only lengths are bed depths
# and canopy reaches, and those documents are full of plant heights, fence
# heights and distances, so the class would be noise. Bed depth is covered
# properly by the derivation check instead.
#
# `%` is out too. The table's only percentage is zone coverage, which is the
# ratio restated, and the documents are full of sales tax, impervious-cover caps
# and germination rates. The class was three findings, all noise.
#
# Thousands separators are matched and stripped, because `2,547 sq ft` read as
# `547 sq ft` is a fabricated finding rather than a missed one.
UNIT_PATTERNS = (
    ("sq ft", re.compile(r"(?<![\d,.])(\d[\d,]*(?:\.\d+)?)\s*"
                         r"(?:sq\.? ?ft|square feet)", re.I)),
    ("cu ft", re.compile(r"(?<![\d,.])(\d[\d,]*(?:\.\d+)?)\s*"
                         r"(?:cu\.? ?ft|cubic feet)", re.I)),
    # `x` only counts as a ratio when nothing numeric follows it. `102.5 x 60.5
    # in` is a porch, not an overplanting figure.
    ("ratio", re.compile(r"(\d+(?:\.\d+)?)\s*x(?!\s*[\d.])(?![\w])", re.I)),
    # `h` is also how every task duration in the calendar is written, so a
    # figure followed by minutes is a duration and is not swept.
    ("h", re.compile(r"(\d+(?:\.\d+)?)\s*(?:h|hours?|hrs?)\b(?!\w)"
                     r"(?!\s*\d+\s*min)")),
)

# No day anywhere gets more than about fourteen hours of sun, and Austin's
# solstice is 14.1. A larger figure carrying `h` is a soak time, a curing time
# or a quarantine, not a light measurement.
MAX_SUN_HOURS = 14.5

# Ratios live between about 0.4 and 2, so the tolerance that works for square
# feet would make 1.58 and 1.61 the same number, and those are the two figures
# the whole audit is about.
TOLERANCE = {"ratio": 0.005}

# An unmatched number wildly outside the span of everything recomputed in its
# unit is about something else — a lot area, an outbuilding footprint, a
# label's coverage rate — and naming its "nearest" bed is a coincidence
# presented as a lead. Reported only inside this multiple of the span.
OUT_OF_SCALE = 2.0


def _significant(text):
    """Three significant digits, or it is not worth searching for.

    `6`, `12`, `100` and `3.5` appear in any document by accident, and a
    checker that reports those is one nobody reads twice.
    """
    return len(re.sub(r"[^0-9]", "", text).strip("0")) >= 3


def unit_of(name):
    for unit in ("sq ft", "cu ft"):
        if unit in name:
            return unit
    if "ratio" in name:
        return "ratio"
    if "sun h" in name:
        return "h"
    if "pct" in name:
        return "pct"
    return None


def _close(a, b, unit):
    floor = TOLERANCE.get(unit, 0.05)
    return abs(a - b) <= max(0.005 * max(abs(a), abs(b)), floor)


def sweep(table, sources):
    """Numbers in prose checked against the recomputed quantity of the same unit.

    Two kinds of finding come out, and the first is the valuable one:

    `wrong method` — the number matches a quantity in the table that is
    explicitly labelled as arrived at the wrong way. That is not an anomaly,
    it is a diagnosis: `47.9 sq ft` is the perennial and annual spreads added,
    and `check_space` takes the larger. The right figure is reported alongside.

    `unmatched` — nothing of that unit reproduces it, and the nearest thing
    that shares its unit is named so a reader can see what it nearly is.
    """
    units = {name: unit_of(name) for name in table}
    findings = []
    for where, text in sources:
        seen = set()
        for unit, pattern in UNIT_PATTERNS:
            for m in pattern.finditer(text):
                raw = m.group(1)
                if (unit, raw) in seen or not _significant(raw):
                    continue
                seen.add((unit, raw))
                v = float(raw.replace(",", ""))
                if unit == "h" and v > MAX_SUN_HOURS:
                    continue
                pool = {n: e for n, e in table.items() if units[n] == unit}
                if not pool:
                    continue
                span = [e["value"] for e in pool.values()]
                if v > OUT_OF_SCALE * max(span):
                    continue
                hits = [n for n, e in pool.items()
                        if _close(v, e["value"], unit)]
                bad = [n for n in hits if "WRONG:" in n]
                if bad:
                    name = sorted(bad)[0]
                    right = table[name].get("instead")
                    findings.append({
                        "kind": "wrong method", "where": where, "number": raw,
                        "unit": unit, "value": v, "nearest": name,
                        "nearest_value": table[name]["value"],
                        "how": table[name]["how"],
                        "instead": ([(right, table[right]["value"])]
                                    if right in table else []),
                        "context": _context(text, m.start()),
                    })
                    continue
                if hits:
                    continue
                near = min(pool.items(),
                           key=lambda kv: abs(kv[1]["value"] - v))
                findings.append({
                    "kind": "unmatched", "where": where, "number": raw,
                    "unit": unit, "value": v, "nearest": near[0],
                    "nearest_value": near[1]["value"], "how": near[1]["how"],
                    "instead": [], "context": _context(text, m.start()),
                })
    findings.sort(key=lambda f: (f["kind"] != "wrong method", f["where"]))
    return findings


def _context(text, at, span=64):
    lo, hi = max(0, at - span), min(len(text), at + span)
    return " ".join(text[lo:hi].split())


def prose_sources(slug):
    """Doubt cards and plan documents, each as one addressable blob of text."""
    out = []
    board = yards.load(slug, "doubts.json") or {}
    for c in board.get("cards", []):
        bits = [c.get("question"), c.get("detail"), c.get("answer"),
                c.get("how_to_settle")]
        for o in c.get("options") or []:
            bits += [o.get(k) for k in ("name", "pro", "con", "cost")]
        text = " ".join(b for b in bits if isinstance(b, str))
        if text:
            out.append((f"doubts.json [{c.get('id')}] {c.get('status')}", text))
    d = yards.yard_dir(slug)
    for name in DOCS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            with open(p, errors="replace") as fh:
                out.append((name, fh.read()))
    return out


# --------------------------------------------------------- the hard checks

def _finding(check, what, detail, cost=""):
    return {"check": check, "what": what, "detail": detail, "cost": cost}


def check_derivations(site):
    """Re-multiply every derivation string against the numbers it cites."""
    out = []
    for key, z in sorted((site.get("zones") or {}).items()):
        if not isinstance(z, dict):
            continue
        text = z.get("area_derivation")
        if text:
            out += _one_area_derivation(site, key, z, text)
        text = z.get("usable_depth_derivation")
        if text:
            out += _one_depth_derivation(key, z, text)
    return out


def _one_area_derivation(site, key, z, text):
    out = []
    stated = z.get("area_sqft")

    cited = re.search(r"size_in \[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]", text)
    ref = re.search(r"(features\.beds\.[A-Za-z0-9_]+) size_in", text)
    if cited and ref:
        a, b = float(cited.group(1)), float(cited.group(2))
        actual = siteschema.get_path(site, ref.group(1) + ".size_in")
        if actual is None:
            out.append(_finding(
                "derivations", f"zones.{key}.area_derivation",
                f"cites {ref.group(1)}.size_in and that path does not exist",
                "the derivation cannot be checked against its own source"))
        elif sorted(float(x) for x in actual[:2]) != sorted([a, b]):
            out.append(_finding(
                "derivations", f"zones.{key}.area_derivation",
                f"cites size_in [{a:g}, {b:g}] and {ref.group(1)}.size_in is "
                f"{actual}",
                "one of the two is stale, and the area was computed from the "
                "one in the string"))

    net = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*in", text)
    if net and stated:
        w, h = float(net.group(1)), float(net.group(2))
        recomputed = w * h / 144.0
        if abs(recomputed - float(stated)) > 0.1:
            out.append(_finding(
                "derivations", f"zones.{key}.area_derivation",
                f"says {w:g} x {h:g} in, which is {recomputed:.2f} sq ft, and "
                f"area_sqft is {stated}",
                "every quantity that scales with bed area is off by "
                f"{abs(recomputed - float(stated)):.2f} sq ft"))
        if cited:
            a, b = float(cited.group(1)), float(cited.group(2))
            for gross, netdim in ((a, w), (b, h)):
                ded = gross - netdim
                if ded not in EDGE_DEDUCTIONS and \
                        not re.search(r"(?<![\d.])" + re.escape(f"{ded:g}")
                                      + r"(?![\d])", text):
                    out.append(_finding(
                        "derivations", f"zones.{key}.area_derivation",
                        f"takes {gross:g} in down to {netdim:g} in, a "
                        f"deduction of {ded:g} in, which is not one of the "
                        f"edging conventions ({', '.join(f'{d:g}' for d in EDGE_DEDUCTIONS)}) "
                        f"and is not itself explained in the string",
                        "the net area rests on an unexplained deduction"))

    # Deliberately no sweep of every `N sq ft` in the string. A derivation
    # legitimately quotes its intermediates — the gross figure, the per-barrel
    # area, the 1.5 sq ft the two ends of g02 differ by, the 11.4 sq ft it is
    # explaining is wrong. Flagging those was four findings out of four false,
    # and a check that is wrong every time is a check nobody reads twice. The
    # `A x B in` recompute above covers the failure that matters, and the prose
    # sweep catches a genuinely orphaned figure.
    return out


def _one_depth_derivation(key, z, text):
    depth = z.get("usable_depth_ft")
    if not depth:
        return []
    implied = float(depth) * 12
    # The convention these strings follow is "<n> in outside, edged ...", so the
    # figure to reconcile against is the first one carrying inches, not the
    # largest number in the sentence. Taking the largest read the "inner 62% of
    # this depth" in g05's string as a measurement.
    first = re.search(r"([\d.]+)\s*in\b", text)
    if not first:
        return []
    nums = [float(n) for n in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?!\s*%)",
                                         text)]
    outside = float(first.group(1))
    ded = outside - implied
    if abs(ded) < 0.01 or any(abs(ded - d) < 0.01 for d in EDGE_DEDUCTIONS) \
            or any(abs(ded - n) < 0.01 for n in nums) \
            or any(abs(ded - (n + e)) < 0.01 for n in nums
                   for e in EDGE_DEDUCTIONS):
        return []
    return [_finding(
        "derivations", f"zones.{key}.usable_depth_derivation",
        f"usable_depth_ft {depth} is {implied:g} in, and the string's largest "
        f"figure is {outside:g} in — a deduction of {ded:g} in that nothing in "
        f"the string accounts for",
        "the depth check in design._check_depth runs on this number")]


def check_provenance(site):
    """Hard provenance claims about values that are not in the file."""
    out = []
    prov = (site or {}).get("provenance") or {}
    for path in sorted(prov):
        source = (prov[path] or {}).get("source")
        if source not in HARD_SOURCES:
            continue
        if siteschema.get_path(site, path, influence.MISSING) is \
                influence.MISSING:
            out.append(_finding(
                "provenance", path,
                f"claims {source!r} and there is no value at that path",
                "an orphaned claim reads as an attested measurement to "
                "anything counting provenance, including the all-clear"))
    return out


def check_zone_notes(site, sun):
    """Sun figures written into a zone note, against the model that knows."""
    out = []
    for key, z in sorted((site.get("zones") or {}).items()):
        if not isinstance(z, dict):
            continue
        note = z.get("note")
        if not isinstance(note, str):
            continue
        for m in re.finditer(r"([\d.]+)\s*h\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|"
                             r"Aug|Sep|Oct|Nov|Dec)", note):
            claimed, month = float(m.group(1)), m.group(2)
            actual = design_mod.zone_hours(sun, site, key, [month])
            if actual is None:
                out.append(_finding(
                    "zone notes", f"zones.{key}.note",
                    f"claims {claimed:g} h in {month} and sun-hours.json has "
                    f"no figure for this zone at all",
                    "the note is the only sun figure anyone will find here"))
            elif abs(actual - claimed) > 0.3:
                out.append(_finding(
                    "zone notes", f"zones.{key}.note",
                    f"claims {claimed:g} h in {month}; the model says "
                    f"{actual:.2f} h — out by {abs(actual - claimed):.2f} h",
                    "plant choice is made against whichever figure the reader "
                    "happens to see"))
        cat = re.match(r"\s*(full sun|part sun|part shade|full shade|shade|"
                       r"deep shade)\b", note, re.I)
        if cat:
            # On the same window `design.check_light` judges a plant over, so
            # the note and the linter cannot disagree about what "full sun"
            # means for the same bed.
            hours = design_mod.zone_hours(sun, site, key)
            if hours is not None:
                want = design_mod._label_for(hours)
                if want.lower() != cat.group(1).lower():
                    out.append(_finding(
                        "zone notes", f"zones.{key}.note",
                        f"opens {cat.group(1)!r} and {hours:.2f} h over "
                        f"{design_mod.window_label(None)} is {want!r} on "
                        f"design.LIGHT_NEED",
                        "the category is what a plant list gets chosen "
                        "against"))
    return out


def check_units(site, dsn):
    """The inches / feet / square-feet boundaries."""
    out = []
    for key, z in sorted((site.get("zones") or {}).items()):
        if not isinstance(z, dict):
            continue
        depth = z.get("usable_depth_ft")
        if depth and float(depth) > 20:
            out.append(_finding(
                "units", f"zones.{key}.usable_depth_ft",
                f"{depth} ft of usable depth, which is a bed the size of a "
                f"room. Inches recorded in a feet field",
                "_check_depth would pass every plant on earth"))
        box, area = z.get("box"), z.get("area_sqft")
        if box and len(box) == 4 and area:
            x0, y0, x1, y1 = box
            from_box = abs((x1 - x0) * (y1 - y0)) / 144.0
            if from_box > 0 and not 0.4 <= float(area) / from_box <= 2.5:
                out.append(_finding(
                    "units", f"zones.{key}",
                    f"area_sqft is {area} and its own box is {from_box:.1f} "
                    f"sq ft — a factor of {float(area) / from_box:.2f}",
                    "zone_areas prefers area_sqft, so the box is decorative "
                    "and the drawings use it"))
        for axis in ("x", "y"):
            v = z.get(axis)
            if isinstance(v, list) and len(v) == 2 and \
                    all(isinstance(n, (int, float)) for n in v) and \
                    max(abs(float(n)) for n in v) < 12 and any(v):
                out.append(_finding(
                    "units", f"zones.{key}.{axis}",
                    f"{v} — the zone frame is inches, and these read as feet",
                    "the sun model would mask a few square inches of ground"))
    for p in dsn.get("plants", []):
        s = p.get("mature_spread_ft")
        if s and float(s) > 40:
            out.append(_finding(
                "units", f"plant {p.get('name')}",
                f"mature_spread_ft {s}, which is a shade tree. Inches in a "
                f"feet field",
                "footprint is pi r^2, so the space check goes wrong by the "
                "square"))
    return out


def check_cross_file(slug, site, dsn, sun):
    """Zones and counts that disagree across files."""
    out = []
    zones = set((site.get("zones") or {}))
    for p in dsn.get("plants", []):
        z = p.get("zone")
        if z and design_mod.resolve_site_zone(site, z) is None:
            out.append(_finding(
                "cross-file", f"design.json plant {p.get('name')}",
                f"is in zone {z!r} and site.json has no such zone",
                "check_space finds no area, so the plant is silently exempt "
                "from the spacing check"))
    for label in (sun.get("by_zone_and_month") or {}):
        if label in ("Whole yard",) or re.match(r"(West|Middle|East) third",
                                                label):
            continue
        if design_mod.resolve_site_zone(site, label) is None:
            out.append(_finding(
                "cross-file", f"sun-hours.json zone {label!r}",
                "is in the sun model and site.json has no such zone",
                "a retired zone keeps publishing sun hours that nothing will "
                "recompute"))
    # `where.bed` is prose by design — "both rose trellises", "g02, g03, and
    # the habitat zones" — so resolving the whole string as a zone name reports
    # eleven findings and none of them real. What is worth catching is a task
    # naming a bed by its identifier when the record no longer has that bed,
    # which is what a rename or a retirement does.
    tasks = yards.load(slug, "tasks.json") or {}
    named = {}
    for t in tasks.get("tasks", []):
        for token in re.findall(r"\b(g0\d|bed_g0\d|front_bed)\b",
                                str((t.get("where") or {}).get("bed") or "")):
            named.setdefault(token, t.get("id"))
    for token, tid in sorted(named.items()):
        if design_mod.resolve_site_zone(site, token) is None:
            out.append(_finding(
                "cross-file", f"tasks.json {tid} where.bed names {token!r}",
                "no zone of that name in site.json",
                "somebody is sent to a bed the record does not have"))
    return out


#: How many changed subtrees a finding names before it says "and n more".
NAME_AT_MOST = 4


def _say_moved(m):
    """The changed inputs, in the order a reader wants them.

    A subtree that changed and also gained a member is one piece of news, so
    the census line only carries what the fingerprints did not already name.
    """
    changed = set(m.get("changed") or [])
    groups = (("changed", sorted(changed)),
              ("added", m.get("added") or []),
              ("no longer read", m.get("removed") or []),
              ("gained or lost members",
               [n for n in m.get("counted") or []
                if not any(n == c or n.startswith(c + ".") for c in changed)]))
    parts = []
    for label, names in groups:
        if not names:
            continue
        shown = ", ".join(names[:NAME_AT_MOST])
        if len(names) > NAME_AT_MOST:
            shown += f", and {len(names) - NAME_AT_MOST} more"
        parts.append(f"{label}: {shown}")
    return "; ".join(parts)


def check_staleness(slug, site):
    """Derived artifacts built from inputs that have since moved, and dead [cNN].

    This used to compare modification times with an hour of tolerance, and was
    wrong on both axes. It cried wolf for a whole working day over a corrected
    provenance string and a rewritten note, neither of which can move a shadow —
    and the remedy such a finding recommends is another run of `lib.sunmodel`,
    which is gated, so a false positive points somebody at the doubt gate for
    nothing. In the other direction the hour of tolerance was exactly the window
    an agent session works in, so a real geometry edit left un-regenerated was
    invisible for as long as it mattered most.

    Each artifact now records a fingerprint per input subtree it was built from,
    which is `lib.doubts`'s all-clear mechanism and `lib.week`'s section hashes
    for the third time in this repo, and for the same reason both exist: the
    finding can name what moved. The scope comes from `lib.inputs.ARTIFACTS`
    off the same `JOB_INPUTS` map the gate uses, so the staleness question and
    the gate question cannot drift apart — `tools/doctor.py` checks that map
    against static analysis already.

    There is no tolerance to tune, because a content digest needs none.

    An artifact written before this existed carries no stamp, and that is
    reported as a question that cannot be answered yet rather than as staleness.
    Asserting freshness there would be the old false negative, and asserting
    staleness would be the old false positive.
    """
    out = []
    d = yards.yard_dir(slug)

    for name, why in (("sun-hours.json", "every light figure in the yard"),
                      ("coverage.json", "the ranked gap report")):
        if not os.path.exists(os.path.join(d, name)):
            continue
        artifact = yards.load(slug, name) or {}
        m = inputs.moved(artifact.get("inputs"), site,
                         inputs.ARTIFACTS[name])
        if m is None:
            out.append(_finding(
                "staleness", name,
                "records no digest of the site.json subtrees it was built "
                "from, so whether it is current cannot be answered",
                f"{why}, on trust. The next run of the job that writes it "
                f"stamps one and the question becomes answerable"))
        elif not m["current"]:
            out.append(_finding(
                "staleness", name,
                "was built from site.json values that have since moved — "
                + (_say_moved(m) or "the census of what is in them"),
                f"{why}, computed from geometry the record no longer holds"))

    # One finding for the whole map directory. Eight lines saying the same thing
    # about eight drawings written by one command is eight times the reading for
    # the same fact.
    #
    # A PNG cannot carry a stamp, so the drawings inherit `sun-hours.json`'s:
    # they are written by the same command from the same geometry, and a run
    # that rewrote one rewrote all of them. What that misses is a drawing
    # deleted or edited by hand afterwards, which nothing here ever caught.
    mapdir = os.path.join(d, "maps")
    if os.path.isdir(mapdir) and os.listdir(mapdir):
        sun = yards.load(slug, "sun-hours.json") or {}
        m = inputs.moved(sun.get("inputs"), site, "sunmodel")
        if m is not None and not m["current"]:
            names = sorted(os.listdir(mapdir))
            out.append(_finding(
                "staleness", f"maps/ — {len(names)} drawings",
                "drawn beside a sun-hours.json whose inputs have moved: "
                + (_say_moved(m) or "the census of what is in them"),
                "drawings of geometry that has since changed. One "
                "`lib.sunmodel` run rewrites all of them"))

    log = yards.load(slug, "changelog.json") or {}
    ids = {e.get("id") for e in log.get("entries", [])}
    for name in DOCS:
        p = os.path.join(d, name)
        if not os.path.exists(p):
            continue
        with open(p, errors="replace") as fh:
            text = fh.read()
        for cid in sorted(set(re.findall(r"\[(c\d+)\]", text))):
            if cid not in ids:
                out.append(_finding(
                    "staleness", f"{name} cites [{cid}]",
                    "no changelog entry with that id",
                    "the reason for a line in the plan is unfindable"))
    return out


# ----------------------------------------------------------------- citations

#: An unresolved binomial. `"Carex perdentata or C. texensis"` is not a species
#: and cannot be checked against anything: the two have different light ratings,
#: so every downstream verdict is a coin toss nobody tossed. `spp.` is the same
#: failure in genus form, and a slash is how it usually gets typed.
UNRESOLVED = re.compile(r"\s+or\s+|/|\bspp?\.|\bsp\.|\?|\bcf\.|\bagg\.", re.I)

#: A citation that names a record. Any one of these is enough: a URL, a
#: catalogue or accession id, a page or section reference, or a table name.
#: What is being asked for is something a second person can go and open.
HAS_RECORD = re.compile(
    r"https?://"                            # a url
    r"|\b[A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*\b"   # CAPL3, G2189, a symbol or accession
    r"|\b(?:table|fig(?:ure)?|sec(?:tion)?|§|p{1,2}\.|page|no\.)\s*[\dIVX]"
    r"|\.md[:#]\d"                           # research-plants.md:147
    r"|\bsection\s+\d",
    re.I)

#: A retrieval date. Without one a citation cannot be re-read as it was read:
#: LBJ edits its pages, and "Soil pH: Acidic" today is not evidence about what
#: the page said when somebody wrote 6.0 into the record.
HAS_DATE = re.compile(r"\b(19|20)\d\d-\d\d-\d\d\b"
                      r"|\b\d{1,2}\s+\w+\s+(19|20)\d\d\b"
                      r"|\b\w+\s+\d{1,2},?\s+(19|20)\d\d\b")

#: Authorities whose name alone reads as evidence and is not. Naming them
#: explicitly rather than flagging every `source` keeps the check on the failure
#: it was built for: "Lady Bird Johnson Wildflower Center" as a whole citation,
#: where the page it means is one of nine thousand.
AUTHORITIES = ("lady bird johnson", "lbj", "wildflower center", "usda",
               "nrcs", "plants database", "agrilife", "aggie horticulture",
               "extension", "missouri botanical", "rhs", "monrovia",
               "native plant society", "npsot", "calflora", "efloras",
               "gardenia", "dave's garden", "wikipedia")

#: The fields whose value is a claim about a species rather than about this
#: yard, and which therefore have to cite something.
CITED_FIELDS = ("source", "light_source", "soil_drainage_source",
                "rooting_depth_source", "months_source", "ph_source",
                "water_source")

#: A document in this repo, cited with an anchor. Exempt from all of the above:
#: it is under version control, so what it said when the number was written is
#: recoverable exactly, which is more than a retrieval date buys.
IN_REPO = re.compile(r"\b[\w-]+\.md\s*[:#§]\s*[\d\w]|\b[\w-]+\.md\s+section\s+\d",
                     re.I)


def check_citations(slug):
    """Whether a plant record's citations can be checked by a second person.

    Two checks, and one deliberately missing third.

    `botanical` gets a regex, because an unresolved binomial is a defect on its
    face. The sedge in this design was recorded as `"Carex perdentata or
    C. texensis"`, and the two do not share a light rating, so its `light` was
    a guess wearing a citation. That one is `serious`.

    A `source` gets asked whether it names a *record*. "Lady Bird Johnson
    Wildflower Center" is unfalsifiable prose; "LBJ CAPL3, <url>, read
    2026-09-05" is checkable in half a minute. This one is a `note`, not a
    defect, and deliberately so: it fires on a large fraction of any existing
    design, and a check that indicts most of the file on its first run is a
    check somebody switches off by Wednesday. It also asks only of citations
    that name an authority, because those are the ones whose name reads as
    evidence — `research-plants.md section 3.1` points at a record in this repo
    and is left alone.

    None of this says the right plant was chosen. A record can carry a perfect
    citation for a species that will die where it is being put, and every
    number here can agree with its source while the choice is wrong. That is
    judgement, it stays judgement, and a clean run of this is not a second
    opinion about it.
    """
    out = []
    design = yards.load(slug, "design.json") or {}
    for p in design.get("plants") or []:
        if not isinstance(p, dict):
            continue
        who = p.get("name") or p.get("botanical") or "?"
        bot = str(p.get("botanical") or "")
        if bot and UNRESOLVED.search(bot):
            out.append(_finding(
                "citations", f"{who} — botanical {bot!r}",
                "is not one species, so nothing about it can be checked "
                "against a source",
                "every rating on this record — light, water, pH — is being "
                "read off whichever of the candidates the writer had in mind, "
                "and the record does not say which"))
        for field in CITED_FIELDS:
            text = str(p.get(field) or "").strip()
            if not text:
                continue
            low = text.lower()
            if not any(a in low for a in AUTHORITIES) or IN_REPO.search(text):
                continue
            missing = [what for what, rx in (("a record id, url or section",
                                              HAS_RECORD),
                                             ("a retrieval date", HAS_DATE))
                       if not rx.search(text)]
            if missing:
                out.append(_finding(
                    "citation form", f"{who} — {field}",
                    f"names an authority without {' or '.join(missing)}: "
                    f"{text[:90]!r}",
                    "a second person cannot open what this cites. Not a "
                    "defect on its own — the number may well be right"))
    return out


# ----------------------------------------------------------------- reporting

def run(slug):
    table, site, dsn, sun, cond = canonical(slug)
    notes = check_zone_notes(site, sun)
    stale = check_staleness(slug, site)

    # The zone-note check compares a note against `sun-hours.json`, so if that
    # file is behind `site.json` the comparison inherits the staleness and the
    # deltas will move when the model re-runs. Saying so beside the findings is
    # the difference between a reader acting on them and a reader being misled
    # by them.
    if notes and any(f["what"] == "sun-hours.json" for f in stale):
        notes.insert(0, _finding(
            "zone notes", "READ THESE WITH THE STALENESS FINDING",
            "the staleness check cannot vouch for sun-hours.json, so every "
            "delta below is measured against a model that may predate the "
            "current geometry. The disagreements are real; the exact figures "
            "will move when lib.sunmodel re-runs",
            "correcting a note to a stale model's number just moves the error"))

    checks = (check_derivations(site)
              + check_provenance(site)
              + notes
              + check_units(site, dsn)
              + check_cross_file(slug, site, dsn, sun)
              + check_citations(slug)
              + stale)
    numbers = sweep(table, prose_sources(slug))
    return table, checks, numbers


def report_checks(checks):
    print("=" * 78)
    print(f"DETERMINISTIC CHECKS  ({len(checks)})")
    print("=" * 78)
    if not checks:
        print("  nothing disagrees.\n")
        return
    by = {}
    for f in checks:
        by.setdefault(f["check"], []).append(f)
    for name in sorted(by):
        print(f"\n  -- {name} ({len(by[name])})")
        if name.startswith("citation"):
            # Said here and not only in the docstring, because the place a
            # green check gets over-read is the place it is printed.
            for line in influence._wrap(
                    "These ask whether a number can be checked against what it "
                    "cites. None of them asks whether the right species was "
                    "chosen for the site, and a clean run is not a second "
                    "opinion about that.", 68):
                print(f"     {line}")
        for f in by[name]:
            print(f"     {f['what']}")
            for line in influence._wrap(f["detail"], 68):
                print(f"         {line}")
            if f["cost"]:
                for line in influence._wrap("costs: " + f["cost"], 68):
                    print(f"         {line}")
    print()


def report_numbers(numbers, limit=40):
    bad = [f for f in numbers if f["kind"] == "wrong method"]
    rest = [f for f in numbers if f["kind"] == "unmatched"]

    print("=" * 78)
    print(f"FIGURES ARRIVED AT BY A METHOD THE CHECK DOES NOT USE  ({len(bad)})")
    print("=" * 78)
    print("  These reproduce exactly — from the wrong arithmetic. Not an")
    print("  anomaly but a diagnosis, and the corrected figure is given.\n")
    if not bad:
        print("  none.\n")
    for f in bad:
        print(f"  {f['where']}: {f['number']} {f['unit']}")
        print(f"      is    {f['nearest']} = {f['nearest_value']:.2f}")
        for line in influence._wrap(f["how"], 66):
            print(f"            {line}")
        for name, value in f["instead"]:
            print(f"      not   {name} = {value:.2f}")
        print(f"      here  ...{f['context']}...")
        print()

    print("=" * 78)
    print(f"UNMATCHED, WITH THE NEAREST THING OF THE SAME UNIT  ({len(rest)})")
    print("=" * 78)
    print("  Heuristic. A number can legitimately come from a price, a")
    print("  catalogue or a probe the table does not cover, so this is")
    print("  'unmatched', never 'wrong'. Only numbers carrying a unit the")
    print("  table also carries are swept at all.\n")
    if not rest:
        print("  everything reconciles.\n")
        return
    for f in rest[:limit]:
        print(f"  {f['where']}: {f['number']} {f['unit']}")
        print(f"      nearest  {f['nearest_value']:.2f}  {f['nearest']}")
        print(f"      context  ...{f['context']}...")
    if len(rest) > limit:
        print(f"\n  ... and {len(rest) - limit} more (--limit to raise)")
    print()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--table", action="store_true",
                    help="print the canonical quantities and stop")
    ap.add_argument("--numbers", action="store_true")
    ap.add_argument("--checks", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.table:
        table, *_ = canonical(args.slug)
        for name, e in sorted(table.items()):
            print(f"  {e['value']:12.3f}  {name}")
            print(f"                {e['how']}")
        return

    table, checks, numbers = run(args.slug)

    if args.json:
        print(json.dumps({"yard": args.slug, "table": table,
                          "checks": checks, "unmatched_numbers": numbers},
                         indent=2, default=str))
        raise SystemExit(1 if checks or numbers else 0)

    stamp = yards.sandbox_stamp(args.slug)
    if stamp:
        print(f"** {stamp}. A rehearsal copy, not the plan. **\n")
    print(f"{args.slug} — {len(table)} quantities recomputed\n")
    if not args.numbers:
        report_checks(checks)
    if not args.checks:
        report_numbers(numbers, args.limit)
    print(f"{len(checks)} deterministic finding"
          f"{'s' if len(checks) != 1 else ''}, "
          f"{len(numbers)} unmatched number"
          f"{'s' if len(numbers) != 1 else ''}. Nothing has been filed.")
    raise SystemExit(1 if checks or numbers else 0)


if __name__ == "__main__":
    main()
