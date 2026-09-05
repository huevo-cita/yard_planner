#!/usr/bin/env python3
"""Prove the calendar refuses to render over a plan it no longer agrees with.

    python3 tools/test_week.py
    python3 tools/test_week.py -v        show every check's detail

This repo tests its guardrails rather than asserting them — `test_gate.py` for
the doubt gate, `test_changelog.py` for the prose lint — because a mechanism
hand-tested once in a chat that no longer exists is not evidence of anything.

`lib.week` is the third guardrail and it turns entirely on one claim: that a date
changed in `PLAN.md` and not in `tasks.json` is caught rather than silently
disagreeing. The properties worth proving, each easy to pass by accident:

  the digest fires     editing a source section makes the render refuse, naming
                       that section. This is the layer that catches a task
                       nobody ever transcribed, which comparing dates cannot
  source means source  a section named under `source` is hashed whatever file it
                       is in, and one named under `reference` or `technique` is
                       not. Both halves matter: the first is the hole the g05
                       gutter programme took its dates through, and the second
                       is what keeps the check from firing on a correct record
  the date check fires moving a date the record cites makes the render refuse,
                       naming the task. Separate from the digest because a
                       digest says only that something moved
  it is not noisy      a clean record produces no findings at all. A check that
                       fires on a correct document is the one that gets switched
                       off, and then there is no check. Tested explicitly,
                       because the obvious implementation — scanning prose for
                       dates and asking which are missing — fails exactly here
  no false positive    a date the plan writes as a range start, "Wed 2 - Sat 5
                       Sep", is stated and must not read as missing
  the flag is honoured a date the plan never states is fine when the task says
                       so with `date_inferred`, and not otherwise
  force stamps         `--force` renders, and the page names what it came past.
                       "Provisional" on its own is not something anyone can act
                       on, so the stamp has to carry the section and the task
  restamp is not a fix `--restamp` clears the digest but must not clear a date
                       the plan no longer states, or the escape hatch swallows
                       the finding it exists to record

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SLUG = "testyard"

results = []          # (state, label, detail) — state in pass/FAIL
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    print(f"  {'ok  ' if state == 'pass' else 'FAIL'}  {label}")
    if detail and (state != "pass" or verbose):
        for line in str(detail).strip().splitlines():
            print(f"          {line}")


def ok(cond, label, detail=""):
    record("pass" if cond else "FAIL", label, "" if cond else detail)


# --------------------------------------------------------------- the fixture

# Small, but shaped like the real thing: two numbered sections, a date written
# plainly, a date written as the start of a dashed range with the month only at
# the end, and a date the prose never states at all. Each exists to make one
# check above fail if it is wrong.
PLAN = """# Scratch — the plan

## 1. The next seven days

- **Mon 31 Aug, 10 min — phone the nursery.**
- **Wed 2 - Sat 5 Sep — watch the tray.**

## 2. Weekend by weekend

### Sep 6-13

- **Sat 12 Sep, 2 h — prune the roses.**
- Weekday evening, 30 min — set out the toad abodes.
"""

# Not a plan document, and numbered the way a long reference document is: a
# parent section with dotted subsections and no `.` after the number. The whole
# g05 gutter programme came out of a file shaped exactly like this, cited it
# under `source`, and got no digest because the filename was not on a whitelist.
RESEARCH = """# Scratch — research

## 4. Slope, and why it matters

Body of section four.

### 4.1 Read this before buying anything

Body of section four point one.

### 4.2 The other one

Body of section four point two.
"""

TASKS = {
    "yard": SLUG,
    "schema_version": 1,
    "target_date": "2026-12-13",
    "sources": {"PLAN.md#1": {"digest": None, "read": None},
                "PLAN.md#2": {"digest": None, "read": None}},
    "suppliers": {},
    "shopping": [],
    "tasks": [
        {"id": "t001", "date": "2026-08-31", "minutes": 10, "kind": "call",
         "title": "Phone the nursery", "where": {"place": "phone"},
         "source": ["PLAN.md#1"], "done": False},
        {"id": "t002", "window": ["2026-09-02", "2026-09-05"], "minutes": 1,
         "kind": "inspect", "title": "Watch the tray",
         "where": {"place": "indoors"}, "source": ["PLAN.md#1"], "done": False},
        {"id": "t003", "date": "2026-09-12", "minutes": 120, "kind": "prune",
         "title": "Prune the roses", "where": {"bed": "roses"},
         "source": ["PLAN.md#2"], "done": False},
        {"id": "t004", "date": "2026-09-11", "minutes": 30, "kind": "build",
         "title": "Set out the toad abodes", "where": {"place": "the outfalls"},
         "date_inferred": True, "date_note": "PLAN.md says 'weekday evening'",
         "source": ["PLAN.md#2"], "done": False},
    ],
}


def make_yard(root):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "PLAN.md"), "w") as f:
        f.write(PLAN)
    with open(os.path.join(d, "research-scratch.md"), "w") as f:
        f.write(RESEARCH)
    with open(os.path.join(d, "tasks.json"), "w") as f:
        json.dump(TASKS, f, indent=2)
    return d


def edit_plan(yard, old, new):
    p = os.path.join(yard, "PLAN.md")
    with open(p) as f:
        text = f.read()
    assert old in text, f"fixture does not contain {old!r}"
    with open(p, "w") as f:
        f.write(text.replace(old, new, 1))


def kinds(findings):
    return sorted({f["kind"] for f in findings})


def subjects(findings, kind):
    return sorted(f["subject"] for f in findings if f["kind"] == kind)


# ------------------------------------------------------------------ the checks

def check_clean(week, yard):
    """A correct record produces nothing. The check that keeps the rest usable."""
    week.restamp(SLUG)
    found = week.check(SLUG)
    ok(not found, "a record that agrees with the plan reports nothing",
       "\n".join(f["message"] for f in found))

    # t002 is written "Wed 2 - Sat 5 Sep" and the month appears once, at the end.
    # A naive matcher looks for "2 Sep", does not find it, and reports a date the
    # plan states plainly as missing.
    ok(not any(f["subject"] == "t002" for f in found),
       "a date written as the start of a dashed range is not reported missing")

    # t004's date is nowhere in the prose, and the record says so.
    ok(not any(f["subject"] == "t004" for f in found),
       "a date flagged date_inferred is not reported missing")


def check_unstamped(week, yard):
    """Never stamped is not the same as agreeing, and must not read as clean."""
    data = week.load(SLUG)
    data["sources"]["PLAN.md#1"]["digest"] = None
    week.save(SLUG, data)
    found = week.check(SLUG)
    ok("unstamped" in kinds(found) and subjects(found, "unstamped") == ["PLAN.md#1"],
       "a section that was never stamped is reported, not assumed fine",
       [f["message"] for f in found])
    week.restamp(SLUG)


def check_uncited(week, yard):
    """A section a task leans on but nothing hashes is a hole in the digest."""
    data = week.load(SLUG)
    data["tasks"][0]["source"].append("PLAN.md#9")
    week.save(SLUG, data)
    found = week.check(SLUG)
    ok(subjects(found, "uncited") == ["PLAN.md#9"],
       "a section cited by a task but carrying no digest is reported",
       [f["message"] for f in found])
    data = week.load(SLUG)
    data["tasks"][0]["source"] = ["PLAN.md#1"]
    week.save(SLUG, data)


def check_source_is_hashed_whatever_the_file(week, yard):
    """`source` means extracted from, so it is hashed even in a research file.

    This is the hole the g05 gutter walked through. Seven tasks took their
    content from `research-guttering.md`, named it under `source`, and got no
    digest, because the check only asked about a fixed list of plan documents.
    Section 5 of that file then turned out to rest on a driveway at the wrong
    corner of the house and nothing anywhere noticed.
    """
    data = week.load(SLUG)
    data["tasks"][0]["source"].append("research-scratch.md#4.1")
    week.save(SLUG, data)
    found = week.check(SLUG)
    ok(subjects(found, "uncited") == ["research-scratch.md#4.1"],
       "a research section cited under `source` is reported as unhashed",
       [f["message"] for f in found])

    # And the escape hatch works in one command rather than a hand edit.
    week.restamp(SLUG)
    ok("research-scratch.md#4.1" in week.load(SLUG).get("sources", {}),
       "--restamp adopts a cited section that carried no digest")
    ok(not week.check(SLUG), "and the record is clean once it has",
       [f["message"] for f in week.check(SLUG)])

    # The point of hashing it: a change to it now surfaces.
    p = os.path.join(yard, "research-scratch.md")
    with open(p) as f:
        before = f.read()
    with open(p, "w") as f:
        f.write(before.replace("Body of section four point one.",
                               "Actually the opposite, and it was never true."))
    found = week.check(SLUG)
    ok("research-scratch.md#4.1" in subjects(found, "stale"),
       "editing that research section makes the digest stale, naming it",
       [f["message"] for f in found])
    with open(p, "w") as f:
        f.write(before)

    data = week.load(SLUG)
    data["tasks"][0]["source"] = ["PLAN.md#1"]
    week.save(SLUG, data)


def check_reference_is_not_hashed(week, yard):
    """`reference` and `technique` are links, not provenance, and stay unhashed.

    The other half of the rule, and the one that keeps it usable. If every
    document a task points at had to be stamped, a task linking three technique
    notes would make the check fire on a correct record, which is how a check
    gets switched off.
    """
    data = week.load(SLUG)
    data["sources"].pop("research-scratch.md#4.1", None)
    data["tasks"][0]["reference"] = "research-scratch.md#4.2"
    data["tasks"][0]["technique"] = "research-scratch.md#4"
    week.save(SLUG, data)
    found = week.check(SLUG)
    ok(not found, "a research file under `reference` or `technique` is not hashed",
       [f["message"] for f in found])
    data = week.load(SLUG)
    data["tasks"][0].pop("reference"), data["tasks"][0].pop("technique")
    week.save(SLUG, data)


def check_dotted_anchor(week, yard):
    """`#4.1` finds `### 4.1 ...`, and `#4` does not swallow its own children.

    A reference document numbers subsections `4.1` and writes no `.` after the
    number. Before this the anchor fell through to a slug match, `4.1` was not a
    substring of `41-read-this-before-buying-anything`, and the reference
    resolved to nothing — so a task could cite a section that could never be
    hashed and the failure looked like a typo.
    """
    sec, err = week.resolve(yard, "research-scratch.md#4.1")
    ok(sec is not None and sec["text"].startswith("4.1 Read"),
       "a dotted section anchor resolves", err or (sec or {}).get("text"))

    sec, err = week.resolve(yard, "research-scratch.md#4")
    ok(sec is not None and sec["text"].startswith("4. Slope"),
       "the parent anchor still resolves to the parent, not to a child",
       err or (sec or {}).get("text"))

    sec, err = week.resolve(yard, "research-scratch.md#4.9")
    ok(sec is None, "a dotted anchor that names no heading is an error, not a guess",
       (sec or {}).get("text"))


def check_digest(week, yard):
    """Editing a section makes the render refuse, naming that section.

    The edit deliberately adds a task rather than moving one, because that is
    the case no date comparison can catch: nothing in tasks.json is wrong, and
    something in the plan was never transcribed.
    """
    edit_plan(yard, "### Sep 6-13",
              "### Sep 6-13\n\n- **Sun 13 Sep, 1 h — mulch the roses.**")
    found = week.check(SLUG)
    ok(subjects(found, "stale") == ["PLAN.md#2"],
       "a task added to the plan and never transcribed makes the digest stale",
       [f["message"] for f in found])

    try:
        week.calendar(SLUG)
        rendered = True
    except SystemExit as exc:
        rendered = False
        message = str(exc)
    ok(not rendered, "--calendar refuses while a section is stale")
    if not rendered:
        ok("PLAN.md §2" in message,
           "the refusal names the section that moved", message)
        ok("--force" in message and "--check" in message,
           "the refusal says what to do next", message)


def check_date(week, yard):
    """Moving a date the record cites is caught, and names the task."""
    week.restamp(SLUG)                      # the digest is no longer the finding
    edit_plan(yard, "Sat 12 Sep", "Sat 19 Sep")
    week.restamp(SLUG)                      # and neither is the second edit
    found = week.check(SLUG)
    ok(subjects(found, "date") == ["t003"],
       "a date moved in the plan is reported against the task that holds it",
       [f["message"] for f in found])
    ok(any("12 September" in f["message"] for f in found if f["kind"] == "date"),
       "the finding says which date the record still believes",
       [f["message"] for f in found])

    # This is the property that makes --restamp safe to offer: it settles the
    # digest, which is a claim about having re-read the section, and settles
    # nothing about a date that is genuinely wrong.
    week.restamp(SLUG)
    still = week.check(SLUG)
    ok(subjects(still, "date") == ["t003"],
       "--restamp does not clear a date the plan no longer states",
       [f["message"] for f in still])


def check_force(week, yard):
    """It renders, and the page names what it came past."""
    found = week.check(SLUG)
    try:
        path, _, text = week.calendar(SLUG, force=True)
    except SystemExit as exc:
        record("FAIL", "--force renders anyway", str(exc))
        return
    record("pass", "--force renders anyway")

    head = text.split("\n## ", 1)[0]
    ok("PROVISIONAL" in head, "the page is stamped provisional", head[:400])
    ok("t003" in head,
       "the stamp names the task whose date the plan no longer states", head[:400])
    ok(len(found) == 1 or "PLAN.md §" in head,
       "the stamp names the section, where a section moved", head[:400])
    ok(head.count("PROVISIONAL") == 1,
       "the stamp appears once, at the top, not per week")

    # A stamp that only said "provisional" would pass every check above except
    # this one: the point is that a reader can tell which dates to distrust.
    ok(week.stamp(found) and week.stamp(found) != "provisional",
       "the stamp is specific rather than a bare word", week.stamp(found))


def check_cheap_paths(week, yard):
    """The ways out have to stay open, or the refusal is a dead end."""
    for label, fn in (("--check", lambda: week.check(SLUG)),
                      ("the terminal week view", lambda: week.report(SLUG)),
                      ("--shop", lambda: week.shop(SLUG, 3))):
        try:
            fn()
            record("pass", f"{label} still runs while the record is refusing")
        except SystemExit as exc:
            record("FAIL", f"{label} still runs while the record is refusing",
                   str(exc))


def check_sync(week, yard):
    """Ticks come back, through the escaping the Docs export applies."""
    export = os.path.join(yard, "exported.md")
    with open(export, "w") as f:
        f.write("> - [x] **Phone the nursery** · 10 min · phone\n"
                "> - [ ] **Watch the tray** · 1 min · indoors\n"
                "> - [x] **Prune the roses** · 2 h · roses\n")
    changed, unmatched, seen = week.sync(SLUG, export)
    ok(seen == 3, f"every checkbox in the export is read (saw {seen})")
    ok(sorted(c[0] for c in changed) == ["t001", "t003"],
       "the ticked ones, and only those, are marked done", changed)
    ok(not unmatched, "every item in the export matches a task", unmatched)

    # The export backslash-escapes punctuation, so a title with a dash in it is
    # the case that silently matches nothing.
    data = week.load(SLUG)
    data["tasks"][3]["title"] = "Set out the toad abodes - four of them"
    week.save(SLUG, data)
    with open(export, "w") as f:
        f.write("> - [x] **Set out the toad abodes \\- four of them** · 30 min\n")
    changed, unmatched, _ = week.sync(SLUG, export)
    ok(sorted(c[0] for c in changed) == ["t004"] and not unmatched,
       "a title the export escaped still matches its task", (changed, unmatched))


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yard-week-test-")
    os.environ["GARDEN_ROOT"] = root
    for mod in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[mod]
    from lib import week

    print("lib.week — does the calendar refuse over a plan it disagrees with\n")
    try:
        yard = make_yard(root)
        print(" a clean record")
        check_clean(week, yard)
        print("\n the digest")
        check_unstamped(week, yard)
        check_uncited(week, yard)
        check_source_is_hashed_whatever_the_file(week, yard)
        check_reference_is_not_hashed(week, yard)
        check_dotted_anchor(week, yard)
        check_digest(week, yard)
        print("\n the dates")
        check_date(week, yard)
        print("\n --force")
        check_force(week, yard)
        print("\n the way out")
        check_cheap_paths(week, yard)
        print("\n the ticks")
        check_sync(week, yard)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nThe calendar is not holding:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
