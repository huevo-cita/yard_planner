#!/usr/bin/env python3
"""Break a check on purpose and confirm the suite notices.

A test that has never failed is a hypothesis. This applies a set of small,
plausible-looking edits to the modules under it — each the kind of change
somebody could make while tidying, or while making a noisy check quieter — runs
the suite that is supposed to own that behaviour, and reports which named checks
died. A mutation nothing catches is a hole in the suite, not a bug in the
mutation.

Each mutation names its own suite, because the behaviours covered here are owned
by different files: the reconciliation between `lib.schedule` and `tasks.json`
by `tools/test_reconcile.py`, the no-build week's visibility on the calendar by
`tools/test_blackout.py`, layered soil — which layer rules a plant's pH and
which layer rules the water — by `tools/test_layers.py`, and a bed's depth
against the rows it is offered by `tools/test_rows.py`. Running the whole repo
against every
mutation would be slower and would also let a mutation be "caught" by a suite
that has no business knowing about it.

Three outcomes, not two, and the third is the reason this file exists
--------------------------------------------------------------------
    caught      the suite ran and at least one named check reported FAIL. The
                suite points at the damage
    CRASH       the suite exited non-zero with no named check failing — an
                import error, a traceback, a mutation that made the module
                unloadable. **This is not a catch and it is not silence.** An
                earlier harness in this repo scored exactly this case as
                "missed" and reported holes that were not there; a run that
                dies before any check can rule has measured nothing, and the
                mutation site or the suite needs fixing before the result means
                anything
    SURVIVED    the suite ran green over a deliberately broken check. A real
                hole, and the only outcome that says something about coverage

**It edits the working tree.** `lib/reconcile.py`, `lib/schedule.py`,
`lib/week.py`, `lib/design.py`, `lib/conditions.py` and `lib/doubts.py` are
rewritten in place for the length of one test run each — under
a second — and put back in a `finally`. A `SIGKILL` or a `git commit -a` from
another terminal inside that window will catch a deliberately broken module.
`git diff` after a crash says what happened.

    python3 tools/mutate.py
    python3 tools/mutate.py --list
    python3 tools/mutate.py --only bulk-is-opens
    python3 tools/mutate.py --suite blackout
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, suite, file, what it stands for, old, new)
MUTATIONS = [
    (
        "timing-never-fires",
        "reconcile",
        "lib/reconcile.py",
        "the timing verdict is hard-wired to agreement, which is the shape of "
        "somebody quietening a check that kept complaining. This is the exact "
        "axis the original month-long divergence lived on",
        "    if abs(bulk) <= WEEKEND_DAYS:",
        "    if True:",
    ),
    (
        "resolution-widened",
        "reconcile",
        "lib/reconcile.py",
        "one weekend becomes over a year, so every date on earth is inside the "
        "resolution and every timing comparison passes",
        "WEEKEND_DAYS = 7",
        "WEEKEND_DAYS = 400",
    ),
    (
        "hours-never-fire",
        "reconcile",
        "lib/reconcile.py",
        "the hours axis always reports agreement, so 4 h of planting against "
        "19 h reads as two derivations that concur",
        "    if abs(gap) < per:",
        "    if True:",
    ),
    (
        "presence-folded-in",
        "reconcile",
        "lib/reconcile.py",
        "work on one side and none on the other stops being its own finding "
        "and becomes a difference of degree, which is the weaker statement",
        '        if not s["hours"] or not t["hours"]:',
        "        if False:",
    ),
    (
        "bulk-is-opens",
        "reconcile",
        "lib/reconcile.py",
        "the bulk of a stage becomes its first day, so the verdict goes back "
        "to being set by the smallest job at the front — one tray sown indoors "
        "in September",
        "            if run >= total / 2.0:",
        "            if run >= 0:",
    ),
    (
        "undeclared-kind-dropped",
        "reconcile",
        "lib/reconcile.py",
        "a task kind nobody has declared is silently left out of every total "
        "instead of reported. Silence about a kind of work becoming permission "
        "to ignore it is the failure AGENTS.md is about",
        "        if stage_of_kind(kind) or kind in UNASSIGNED or kind in OUTSIDE:",
        "        if True:",
    ),
    (
        "prep-assigned-anyway",
        "reconcile",
        "lib/reconcile.py",
        "the kind that genuinely spans the bridge gets put on one side of it, "
        "so ten hours of kitchen-sink work counts as structure",
        '        "kinds": ["build"],',
        '        "kinds": ["build", "prep"],',
    ),
    (
        "repeats-summed",
        "reconcile",
        "lib/reconcile.py",
        "a repeating job's per-occurrence minutes get summed as hours, which "
        "quotes a total against a cadence running past the target date",
        '            repeating.append(t["id"])\n            continue',
        '            repeating.append(t["id"])',
    ),
    (
        "past-the-target-counted",
        "reconcile",
        "lib/reconcile.py",
        "work dated after the target is counted against a plan that stops at "
        "the target, so next spring's planting inflates this autumn's total",
        "        if end and first > end:",
        "        if False:",
    ),
    (
        "gate-forced",
        "reconcile",
        "lib/reconcile.py",
        "the reconciliation forces `build()` past the doubt gate rather than "
        "reporting the refusal, so a yard with open doubts gets compared "
        "against a plan stamped provisional",
        "        plan = schedule.build(slug, target=target, "
        "hours_per_weekend=hours)",
        "        plan = schedule.build(slug, target=target, "
        "hours_per_weekend=hours,\n                              force=True)",
    ),
    (
        "pipeline-inverted",
        "reconcile",
        "lib/schedule.py",
        "lib.schedule learns to read tasks.json. The two then always agree and "
        "their agreement stops being evidence of anything — a copy would have "
        "agreed perfectly on the month it was a month wrong",
        "def build(slug, target=None, hours_per_weekend=None, start_from=None,\n"
        "          force=False):",
        "def build(slug, target=None, hours_per_weekend=None, start_from=None,\n"
        "          force=False):\n"
        "    dated = yards.load(slug, 'tasks.json') or {}",
    ),

    # ---- the no-build week, on the page somebody reads on the way out ----
    (
        "banner-never-shown",
        "blackout",
        "lib/week.py",
        "the banner is dropped from the rendered week, which is precisely the "
        "state the calendar was already in: the scope legible to every tool "
        "and invisible to a person",
        '        lines += [f"{head} {said}", ""]',
        "        lines += []",
    ),
    (
        "banner-under-the-days",
        "blackout",
        "lib/week.py",
        "the banner moves below the day-by-day. Still technically present, and "
        "useless — a person who has read the hours and gone outside does not "
        "scroll back",
        "    out += _blackout_banner(week_blackout(data, cond, monday), slug)",
        "    _later = _blackout_banner(week_blackout(data, cond, monday), slug)",
    ),
    (
        "every-week-blacked-out",
        "blackout",
        "lib/week.py",
        "the overlap test stops excluding weeks the blackout does not touch, "
        "so every week in a 129-week calendar carries a no-build banner. A "
        "banner on every page is a banner nobody reads",
        "        if a > z:\n            continue",
        "        if False:\n            continue",
    ),
    (
        "permits-not-named",
        "blackout",
        "lib/week.py",
        "the page says the week is off and never says what is nonetheless "
        "allowed, so a recorded decision reads as a blanket refusal and the "
        "critical establishment watering looks barred",
        '            tail.append("Permitted: " + " · ".join(b["permits"]))',
        "            pass",
    ),
    (
        "whole-justification-printed",
        "blackout",
        "lib/week.py",
        "the forty-word defence of each permit goes onto the calendar "
        "verbatim instead of its headline clause. The calendar is a plan "
        "document again, and there is already one of those",
        '    s = re.split(r"\\s+[-\\u2013\\u2014]\\s+|,\\s+including\\b|;\\s+", '
        'str(text), 1)[0]',
        "    s = str(text)",
    ),
    (
        "unruled-work-called-permitted",
        "blackout",
        "lib/week.py",
        "a task in a kind the scope names in neither list stops being flagged, "
        "so the record's silence becomes its permission. This is the failure "
        "AGENTS.md is about, arriving through a calendar",
        "            if worst in (conditions.BARRED, conditions.UNSCOPED):",
        "            if worst == conditions.BARRED:",
    ),
    (
        "clear-and-not-clear",
        "blackout",
        "lib/week.py",
        "the all-clear sentence prints even when something on the week is not "
        "permitted, so the page asserts both that a job is barred and that "
        "everything below is allowed",
        '        if not b["flagged"]:\n            tail.append("everything '
        'below is work it allows")',
        '        if True:\n            tail.append("everything below is work '
        'it allows")',
    ),

    # ---- soil in layers, and which layer is allowed to rule what ----
    (
        "native-never-consulted",
        "layers",
        "lib/design.py",
        "the depth-aware pH check reads only the layer the roots start in, so "
        "the twelve plantings that root straight through six inches into clay "
        "go quiet with the shallow annuals. This is the shape of the fix "
        "working too well, and it is the failure the whole suite is aimed at",
        "    certain, possible = conditions.reached(layers, rooting_depth(plant))",
        "    certain, possible = layers[:1], []",
    ),
    (
        "missing-depth-defaulted",
        "layers",
        "lib/design.py",
        "a plant with no researched rooting depth is given six inches so the "
        "check has something to run on. That is the original bug one field "
        "along: an assumed number applied to ground it does not describe",
        "    v = plant.get(\"rooting_depth_in\")\n"
        "    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:\n"
        "        return None",
        "    v = plant.get(\"rooting_depth_in\")\n"
        "    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:\n"
        "        return 6.0",
    ),
    (
        "band-quoted-as-a-reading",
        "layers",
        "lib/design.py",
        "the plausible band is consulted even where the layer carries a value, "
        "so the native 8.2 becomes the 7.8-8.3 interval its own note quotes "
        "and every remaining pH objection drops to a shrug",
        "    ph = layer.get(\"ph\")\n    if ph is not None:",
        "    ph = layer.get(\"ph\")\n    if ph is not None and not "
        "layer.get(\"ph_plausible\"):",
    ),
    (
        "unmeasured-reads-as-fine",
        "layers",
        "lib/design.py",
        "a layer nobody has tested passes everything, which is the friendly "
        "direction of the same error: nineteen plantings that cannot be ruled "
        "on read as nineteen that are fine",
        "        return PH_DEPENDS\n    return PH_UNKNOWN",
        "        return PH_OK\n    return PH_OK",
    ),
    (
        "boundary-inclusive",
        "layers",
        "lib/conditions.py",
        "`bottom_in` becomes inclusive, so a six-inch root zone is judged to "
        "enter the layer starting at six. Off by one here refuses the entire "
        "shallow palette against caliche again, and reads identically in prose",
        "        elif top < float(depth_in):",
        "        elif top <= float(depth_in):",
    ),
    (
        "drainage-follows-ph",
        "layers",
        "lib/design.py",
        "drainage is made depth-aware like pH, so a shallow-rooted plant is "
        "judged to escape the clay by staying above it. Water perches at the "
        "interface and stands upward from it; this would silence four real "
        "objections and the four grit mounds already funded to answer them",
        "def _sharp_by_depth(plant, layers):",
        "def _sharp_by_depth(plant, layers):\n"
        "    layers, _ = conditions.reached(layers, rooting_depth(plant) or 4.0)",
    ),
    (
        "limiting-layer-is-deepest",
        "layers",
        "lib/conditions.py",
        "the limiting layer becomes the deepest slow one rather than the "
        "shallowest, which is where the water table would perch if water ran "
        "uphill",
        "    for layer in layers or []:\n"
        "        drain = str(layer.get(\"drainage\") or \"\").lower()\n"
        "        if any(w in drain for w in SLOW_WORDS):\n"
        "            return layer\n"
        "    return None",
        "    found = None\n"
        "    for layer in layers or []:\n"
        "        drain = str(layer.get(\"drainage\") or \"\").lower()\n"
        "        if any(w in drain for w in SLOW_WORDS):\n"
        "            found = layer\n"
        "    return found",
    ),
    (
        "gaps-not-reported",
        "layers",
        "lib/design.py",
        "the coverage notes are dropped. Everything the narrower pH check "
        "stops saying then lands nowhere, and a check that answers fewer "
        "questions looks exactly like a yard with fewer problems",
        "    out += check_layer_coverage(plants, site, cond)",
        "    out += []",
    ),
    (
        "boundary-halves-not-compared",
        "layers",
        "lib/conditions.py",
        "the contiguity check stops comparing the two halves of each boundary, "
        "so a profile can say the imported layer stops at 3 in while the "
        "native layer starts at 6 and the three inches between belong to "
        "neither. Nothing objects, because every verdict is decided from "
        "`top_in` alone",
        "        elif abs(float(bottom) - top) > 1e-9:",
        "        elif False:",
    ),
    (
        "unprobeable-priced-anyway",
        "layers",
        "lib/doubts.py",
        "`--price` goes back to probing a path that is not in site.json, so a "
        "doubt light cannot measure settles itself `probed-immaterial` on a "
        "spread of zero — a number closing a question it never looked at",
        "        unmeasurable = _unprobeable(site, probe)\n"
        "        if unmeasurable:\n"
        "            results.append((c, None, unmeasurable))\n"
        "            continue",
        "        pass",
    ),

    # ---- a bed has a depth, and rows add up ----
    (
        "stack-is-the-widest-rank",
        "rows",
        "lib/design.py",
        "the depth a layered bed consumes becomes its deepest rank instead of "
        "the sum of them, which is the shape of somebody quietening a check "
        "that objected to four beds at once. It is also exactly the blindness "
        "that let g05 be offered 6.5 ft of rows in 3.708 ft of bed",
        "    return sum(float(s) for s in spreads)",
        "    return max([float(s) for s in spreads] or [0])",
    ),
    (
        "stack-arm-dropped",
        "rows",
        "lib/design.py",
        "`check_space` stops taking the depth arm at all and goes back to "
        "judging a border on area alone. This is the state the linter was in, "
        "and it read as a yard with four fewer problems",
        "        out += _check_row_depth(z, plants, site, key)",
        "        out += []",
    ),
    (
        "overhang-assumed",
        "rows",
        "lib/design.py",
        "an undeclared canopy overhang becomes a foot of assumed apron, so "
        "every front rank may lean out over ground nobody has said is there. "
        "The friendly direction of the same error, and it silences g01 and g04",
        "    return float(depth) + z_overhang(site, key)",
        "    return float(depth) + (z_overhang(site, key) or 1.0)",
    ),
    (
        "unranked-layer-skipped",
        "rows",
        "lib/design.py",
        "a plant whose `layer` is not one of the three ranks is dropped from "
        "the stack rather than counted and named. g01's yucca is filed "
        "`accent`, so the bed goes quiet — and this is the `hardscape[\"kind\"]` "
        "bug arriving one file along: a guard skipping what it does not "
        "recognise",
        '        key = layer if layer in ROWS else "other"',
        "        if layer not in ROWS:\n            continue\n        key = layer",
    ),
    (
        "niches-budgets-no-depth",
        "rows",
        "lib/niches.py",
        "the row budget stops spending depth and goes back to picking the "
        "largest class that fits the bed on its own. This reproduces g05's "
        "original slate exactly — three rows of 2.5, 2.5 and 1.5 — and it "
        "still passes the coverage band, because the band was never the "
        "constraint",
        "            if headroom is not None and rep > headroom + 1e-9:",
        "            if False:",
    ),
    (
        "rows-thresholded-again",
        "rows",
        "lib/niches.py",
        "how many ranks a bed holds goes back to two hard-coded depths instead "
        "of the sum of the size classes. The numbers even look reasonable, and "
        "they hand a 3.0 ft bed three ranks that need 3.5",
        "    for rows in _ROW_SETS:",
        "    if float(room) >= 3.0:\n        return [lay for lay, _ in LAYERS]\n"
        "    for rows in _ROW_SETS:",
    ),
    (
        "audit-trusts-the-file",
        "rows",
        "lib/niches.py",
        "the read-back audit takes the bed's depth from niches.json's own "
        "cached copy rather than from site.json. It then agrees with the file "
        "by construction and can never contradict it — which is the whole bug "
        "this suite is about, rebuilt inside the check written to catch it",
        "        depth = measured or cached",
        "        depth = cached or measured",
    ),
    (
        "run-cap-dropped",
        "rows",
        "lib/niches.py",
        "the count stops being capped by the bed's own length, so g05's front "
        "rank is paid 9.3 sq ft of area share at 0.196 sq ft a plant and "
        "offered 47 edging plants for an 8.7 ft line with room for 17",
        "        tight = \"\"\n        if along is not None:",
        "        tight = \"\"\n        if False:",
    ),
]


#: Which suite owns which behaviour. A mutation is measured only against the
#: suite that is supposed to know about it, so "caught" means the right file
#: noticed rather than something downstream tripping over the wreckage.
SUITES = {"reconcile": "test_reconcile.py", "blackout": "test_blackout.py",
          "layers": "test_layers.py", "rows": "test_rows.py"}


def run_suite(suite, timeout=300):
    p = subprocess.run([sys.executable, os.path.join(HERE, SUITES[suite])],
                       cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    failed = [line[8:].strip() for line in p.stdout.splitlines()
              if line.startswith("  FAIL  ")]
    return p.returncode, failed, p.stdout, p.stderr


def drop_pycache():
    for d in ("lib", "tools"):
        shutil.rmtree(os.path.join(ROOT, d, "__pycache__"), ignore_errors=True)


def apply(path, old, new):
    full = os.path.join(ROOT, path)
    with open(full, encoding="utf-8") as f:
        text = f.read()
    if text.count(old) != 1:
        raise SystemExit(f"mutation site in {path} matched {text.count(old)} "
                         f"times, expected exactly 1 — the code has moved and "
                         f"this harness needs updating before it can be "
                         f"trusted")
    with open(full, "w", encoding="utf-8") as f:
        f.write(text.replace(old, new))
    drop_pycache()
    return text


def restore(path, text):
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as f:
        f.write(text)
    drop_pycache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", help="run one mutation by name")
    ap.add_argument("--suite", choices=sorted(SUITES),
                    help="only the mutations one suite owns")
    a = ap.parse_args()

    if a.list:
        for name, suite, path, what, _, _ in MUTATIONS:
            print(f"  {name:28s} {suite:10s} {path:16s} {what}")
        return 0

    todo = [m for m in MUTATIONS
            if (not a.only or m[0] == a.only)
            and (not a.suite or m[1] == a.suite)]
    if not todo:
        raise SystemExit(f"nothing matched --only {a.only!r} --suite "
                         f"{a.suite!r}")

    suites = sorted({m[1] for m in todo})
    print(f"mutation — {len(todo)} deliberate breakages, measured against "
          f"{', '.join(SUITES[s] for s in suites)}\n")
    for s in suites:
        code, failed, out, err = run_suite(s)
        if code != 0:
            print(out, err)
            raise SystemExit(f"{SUITES[s]} does not pass before mutating. Fix "
                             f"that first; nothing measured from here would "
                             f"mean anything.")
        print(f" baseline {SUITES[s]}: green")
    print()

    survivors, crashed = [], []
    for name, suite, path, what, old, new in todo:
        original = None
        try:
            original = apply(path, old, new)
            code, failed, out, err = run_suite(suite)
        finally:
            if original is not None:
                restore(path, original)

        if code != 0 and failed:
            mark, note = "ok  ", None
        elif code != 0:
            # Non-zero with nothing named. The suite died rather than ruled, so
            # this measures nothing either way. Not a catch, and emphatically
            # not silence.
            mark, note = "CRASH", ((err or out).strip().splitlines() or [""])[-1]
            crashed.append(name)
        else:
            mark, note = "MISS", None
            survivors.append(name)

        print(f" {mark:5s} {name}   ({SUITES[suite]})")
        for line in _wrap(what, 68):
            print(f"        {line}")
        if mark == "ok  ":
            print(f"        caught by {len(failed)} check"
                  f"{'s' if len(failed) > 1 else ''}:")
            for f in failed[:4]:
                print(f"          - {f}")
            if len(failed) > 4:
                print(f"          - and {len(failed) - 4} more")
        elif mark == "CRASH":
            print(f"        the suite exited non-zero with no check failing, "
                  f"so it measured")
            print(f"        nothing. Not a catch and not a hole — the mutation "
                  f"site needs")
            print(f"        moving. Last line: {note[:80]!r}")
        else:
            print(f"        SURVIVED. The suite ran green over it.")
        print()

    for s in suites:
        code, failed, out, err = run_suite(s)
        if code != 0:
            print(out, err)
            raise SystemExit(f"{SUITES[s]} is red after restoring. The tree is "
                             f"not back the way it was — check `git diff` "
                             f"before doing anything else.")
    print("tree restored, every suite green again.")

    bad = 0
    if survivors:
        print(f"\n{len(survivors)} mutation"
              f"{'s' if len(survivors) > 1 else ''} survived, which is "
              f"{len(survivors)} hole{'s' if len(survivors) > 1 else ''} in "
              f"the suite: " + ", ".join(survivors))
        bad = 1
    if crashed:
        print(f"\n{len(crashed)} mutation"
              f"{'s' if len(crashed) > 1 else ''} crashed the suite instead of "
              f"being caught by it: " + ", ".join(crashed)
              + ".\nThose results are inconclusive, not passes.")
        bad = 1
    if not bad:
        print(f"\nall {len(todo)} caught by a named check.")
    return bad


def _wrap(text, width=68):
    out, line = [], ""
    for word in str(text).split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


if __name__ == "__main__":
    sys.exit(main())
