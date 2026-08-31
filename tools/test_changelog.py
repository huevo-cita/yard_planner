#!/usr/bin/env python3
"""Prove the change log holds, and the lint actually catches the prose it is for.

    python3 tools/test_changelog.py
    python3 tools/test_changelog.py -v        show every command's output

`lib.changelog` exists to move two kinds of sentence out of the plan documents:
what the plan used to say, and the argument for what it says now. Three things
have to be true for that to be worth anything, and each fails silently.

  the log refuses a shrug   an entry with no `why` is worse than the sentence it
                            replaced — same cost to read, less answered. So
                            `--add` refuses one, and `--check` finds any that got
                            in another way.
  the reference resolves     a plan that says `[c14]` and nothing else is only
                            useful if `[c14]` lands somewhere. The anchor has to
                            survive markdown into HTML, which is the step that
                            quietly renames headings.
  the lint bites, and lets   a linter that flags nothing is decoration; one that
  a clean document past      flags a clean document gets switched off within a
                            week. Both directions are checked here.

The last one is checked twice over: against a document written to fail, and
against the same document rewritten clean. A test that only asserted the first
would pass just as happily with the patterns widened until they matched every
sentence in English.

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import changelog  # noqa: E402  (after sys.path)

SLUG = "testyard"
HOOK = os.path.join(ROOT, ".cursor", "hooks", "plan-prose.sh")

# Written to fail, one line per pattern family, so a finding can be traced to the
# rule that caught it rather than to the paragraph as a whole.
DIRTY = """# testyard — the plan to 13 December 2026

Rewritten on 31 August 2026 against your own drawings.

## 1. The audit

You said the palette had green things in December. **You were right, and the
previous version of this plan was wrong about it.**

### What dropping the yaupon actually cost

Height. The bed used to be taller.

### Are the violas enough? No.

## 2. Why you must not sow this afternoon

Soil is above 80 F.

## 3. Weekend by weekend

- **Wed evening, 30 min — walk both roses.** *(Moved off Tuesday: the tray
  arrives Tuesday.)*
- **Sat 5 Sep, 2 h — deep-soak both roses**, five gallons each in three passes [c1].
- Cut the asters to 6-8 in in late November [c99].
"""

# The same facts, none of the history. Every date, quantity and instruction in
# DIRTY survives here — which is the standard a real rewrite is held to.
CLEAN = """# testyard — the plan to 13 December 2026

`site.json` holds the facts. Why anything here reads as it does is in
[CHANGELOG.md](CHANGELOG.md).

## The next seven days

- **Wed 2 Sep, 30 min — walk both roses with a torch** [c1]. Photograph anything
  odd.
- **Sat 5 Sep, 2 h — deep-soak both roses**, five gallons each in three passes.

## Standing calendar

| When | What |
|---|---|
| Late November | Cut the asters to 6-8 in |
"""

results = []
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    mark = {"pass": "ok  ", "FAIL": "FAIL"}[state]
    print(f"  {mark}  {label}")
    if detail and (state != "pass" or verbose):
        for line in detail.strip().splitlines():
            print(f"          {line}")


def run(root, *args, module="lib.changelog"):
    env = dict(os.environ, GARDEN_ROOT=root)
    p = subprocess.run([sys.executable, "-m", module] + list(args),
                       cwd=ROOT, env=env, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def doc(root, name, text):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ------------------------------------------------------- the log refuses a shrug

def check_refuses_a_shrug(root):
    code, out = run(root, SLUG, "--add", "something moved", "--kind", "change",
                    "--was", "a", "--now", "b")
    record("pass" if code != 0 and "--why" in out else "FAIL",
           "a change with no why is refused",
           out if code == 0 else "")

    code, out = run(root, SLUG, "--add", "the asters", "--kind", "change",
                    "--why", "because")
    record("pass" if code != 0 and "--was" in out and "--now" in out else "FAIL",
           "a change with no before and after is refused", out)

    code, out = run(root, SLUG, "--add", "g02 is not bare in December",
                    "--kind", "correction", "--why", "checked plant by plant")
    ok = code == 0
    problems = changelog.check(_load(root))
    record("pass" if ok and any("no source" in p for p in problems) else "FAIL",
           "a correction with no source is flagged by --check",
           "\n".join(problems) if ok else out)


def _load(root):
    """Read the log directly, without depending on the module's own root."""
    import json
    p = os.path.join(root, SLUG, "changelog.json")
    if not os.path.exists(p):
        return {"entries": []}
    with open(p) as fh:
        return json.load(fh)


# -------------------------------------------------------- the reference resolves

def check_reference_resolves(root):
    code, out = run(root, SLUG, "--add", "Rose walk moved to Wednesday",
                    "--kind", "change", "--subject", "rose walk",
                    "--was", "Tuesday 1 September", "--now", "Wednesday 2 September",
                    "--why", "the seed tray arrives Tuesday and that sowing is "
                             "date-bound; the walk is not",
                    "--affects", "PLAN.md")
    if code != 0:
        record("FAIL", "an entry with its why is accepted", out)
        return
    record("pass", "an entry with its why is accepted")

    ids = [e["id"] for e in _load(root)["entries"]]
    code, out = run(root, SLUG, "--render")
    md = os.path.join(root, SLUG, "CHANGELOG.md")
    if code != 0 or not os.path.exists(md):
        record("FAIL", "--render writes CHANGELOG.md", out)
        return
    body = open(md, encoding="utf-8").read()
    missing = [i for i in ids if f"{{: #{i} }}" not in body]
    record("pass" if not missing else "FAIL",
           "every entry renders with an explicit anchor",
           f"no anchor for {missing}" if missing else "")

    code, out = run(root, md, module="lib.buildhtml")
    html_path = os.path.splitext(md)[0] + ".html"
    if code != 0 or not os.path.exists(html_path):
        record("FAIL", "the log converts to HTML", out)
        return
    html = open(html_path, encoding="utf-8").read()
    lost = [i for i in ids if f'id="{i}"' not in html]
    record("pass" if not lost else "FAIL",
           "the anchor survives markdown into HTML, so [cNN] resolves",
           f"{lost} lost their id in conversion — a plan linking to them would "
           f"land at the top of the page" if lost else "")

    # add_anchors used to skip any heading that arrived with an id, which is
    # every entry in here, so the one document that most needs navigating was
    # the only one published without a contents list.
    missing_toc = [i for i in ids if f'href="#{i}"' not in html]
    record("pass" if not missing_toc else "FAIL",
           "an entry that brought its own id still reaches the contents list",
           f"{missing_toc} absent from the table of contents"
           if missing_toc else "")

    # The plan writes the mark bare, because a URL mid-sentence is exactly the
    # noise this whole mechanism exists to remove. So the link has to be made at
    # publish time or the reference is dead text in the artifact people read.
    plan = doc(root, "PLAN.md",
               "# Plan\n\n## 1. This week\n\n- Prune the roses [%s], then mulch.\n"
               "\nSowing dates are in [SOWING-CALENDAR.md](SOWING-CALENDAR.md).\n"
               % ids[0])
    doc(root, "SOWING-CALENDAR.md", "# Sowing\n\n## 1. This week\n\n- Sow lettuce.\n")
    code, out = run(root, plan, module="lib.buildhtml")
    ph = os.path.splitext(plan)[0] + ".html"
    body = open(ph, encoding="utf-8").read() if os.path.exists(ph) else ""
    record("pass" if f'href="CHANGELOG.html#{ids[0]}"' in body else "FAIL",
           "a bare [cNN] in the plan is published as a link into the log",
           out + "\n" + body[:400])
    record("pass" if f"[{ids[0]}]" not in body else "FAIL",
           "no [cNN] is left as dead text in the published plan")
    record("pass" if 'href="SOWING-CALENDAR.html"' in body else "FAIL",
           "a sibling .md link is published pointing at the .html")


# -------------------------------------------------- back-dating

def check_back_dating(root):
    """Adopting the log on an existing project means back-filling its history.

    Entries sort by date, so a malformed one files itself in the wrong place in
    its own thread — the failure is silent and it corrupts exactly the reading
    order the log exists to provide.
    """
    code, out = run(root, SLUG, "--add", "Bed sizes taken off the owner's drawing",
                    "--kind", "correction", "--date", "2026-08-25",
                    "--why", "the drawing is dimensioned and the earlier figures "
                             "were scaled off an aerial",
                    "--source", "owner's drawing, 25 August")
    dated = [e for e in _load(root)["entries"] if e.get("date") == "2026-08-25"]
    record("pass" if code == 0 and dated else "FAIL",
           "--date back-files an entry under the day it was decided", out)

    code, out = run(root, SLUG, "--add", "x", "--kind", "rationale",
                    "--why", "y", "--date", "25 Aug 2026")
    record("pass" if code != 0 and "not an iso date" in out.lower() else "FAIL",
           "a date that is not ISO is refused rather than mis-sorted", out)


# -------------------------------------------------- the lint bites, and lets past

# Each family the lint is meant to catch, matched against its own finding, so a
# pattern deleted from RETROSPECTIVE fails a named check instead of nudging a
# total.
EXPECTED = {
    "a document announcing it was rewritten": "rewritten on",
    "the brief restated as argument": "you said",
    "being told the reader was right": "you were right",
    "a reference to the previous version": "previous version",
    "the record being called wrong in place": "was wrong",
    "what the yard used to be": "used to be",
    "a task carrying the day it moved off": "moved off tuesday",
    "a heading that argues the cost": "heading: What dropping the yaupon",
    "a heading that answers its own question": "heading: Are the violas enough",
    "a why section": "heading: Why you must not sow",
}


def check_lint_bites(root):
    path = doc(root, "PLAN.md", DIRTY)
    code, out = run(root, SLUG, "--lint")
    low = out.lower()
    if code == 0:
        record("FAIL", "the lint refuses a document that narrates its history",
               out)
        return
    record("pass", "the lint exits non-zero on a document full of it")

    for label, needle in EXPECTED.items():
        record("pass" if needle.lower() in low else "FAIL",
               f"caught: {label}",
               f"nothing matched {needle!r}" if needle.lower() not in low else "")

    record("pass" if "[c99] is not in the log" in out else "FAIL",
           "a reference to an entry that does not exist is caught",
           "a plan can promise a reason that was never written" )
    record("pass" if "[c1] is not in the log" not in out else "FAIL",
           "a reference to an entry that does exist is left alone", out)

    os.remove(path)


def check_lint_lets_past(root):
    path = doc(root, "PLAN.md", CLEAN)
    code, out = run(root, SLUG, "--lint")
    record("pass" if code == 0 else "FAIL",
           "a clean document passes, so the lint is not decoration",
           out if code else "")
    os.remove(path)


def check_reference_material_exempt(root):
    """A 90,000-word plant reference is the right length for a plant reference."""
    doc(root, "research-plants.md", DIRTY * 40)
    code, out = run(root, SLUG, "--lint")
    record("pass" if code == 0 else "FAIL",
           "reference material is not held to the plan contract", out)


def check_word_budget(root):
    doc(root, "PLAN.md", CLEAN + ("\n- filler word " * 4000))
    code, out = run(root, SLUG, "--lint")
    ok = code != 0 and "over budget" in out
    record("pass" if ok else "FAIL",
           "an action document over the word budget is reported", out)
    os.remove(os.path.join(root, SLUG, "PLAN.md"))


# ------------------------------------------------------------------- the publish

def check_publish_gate(root):
    path = doc(root, "PLAN.md", DIRTY)
    html = os.path.splitext(path)[0] + ".html"
    for f in (html,):
        if os.path.exists(f):
            os.remove(f)

    code, out = run(root, path, "--strict", module="lib.buildhtml")
    record("pass" if code != 0 and not os.path.exists(html) else "FAIL",
           "--strict publishes nothing rather than publishing and complaining",
           out)

    code, out = run(root, path, module="lib.buildhtml")
    record("pass" if code == 0 and os.path.exists(html) else "FAIL",
           "without --strict it publishes and says what it found",
           out)
    record("pass" if "belongs in the log" in out or "log holds" in out
           else "FAIL",
           "the warning carries the redirect, not just the complaint", out)
    os.remove(path)


# ---------------------------------------------------------------------- the hook

def check_hook(root):
    """The hook has to stay quiet on everything that is not a plan document."""
    if not os.path.exists(HOOK):
        record("FAIL", "the plan-prose hook exists", f"{HOOK} is missing")
        return
    if shutil.which("jq") is None:
        record("pass", "the hook is skipped: jq is not installed")
        return

    path = doc(root, "PLAN.md", DIRTY)
    quiet = [
        ('a shell command', '{"tool_input":{"command":"ls"}}'),
        ('a path that does not exist', '{"tool_input":{"path":"/nope/PLAN.md"}}'),
        ('a file that is not an action document',
         '{"tool_input":{"path":"%s"}}' % os.path.join(root, SLUG, "CHANGELOG.md")),
    ]
    for label, payload in quiet:
        p = subprocess.run([HOOK], input=payload, capture_output=True, text=True,
                           env=dict(os.environ, GARDEN_ROOT=root))
        said = (p.stdout or "").strip()
        record("pass" if said == "{}" else "FAIL",
               f"the hook stays quiet on {label}", said)

    p = subprocess.run([HOOK], input='{"tool_input":{"path":"%s"}}' % path,
                       capture_output=True, text=True,
                       env=dict(os.environ, GARDEN_ROOT=root))
    said = p.stdout or ""
    record("pass" if "additional_context" in said and "moved off" in said
           else "FAIL",
           "the hook speaks up on a plan document, with the findings", said)
    os.remove(path)


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print the output of every command, not just failures")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yard-changelog-test-")
    print(f"change log — scratch yard in {root}")
    try:
        os.makedirs(os.path.join(root, SLUG), exist_ok=True)
        check_refuses_a_shrug(root)
        check_reference_resolves(root)
        check_back_dating(root)
        check_lint_bites(root)
        check_lint_lets_past(root)
        check_reference_material_exempt(root)
        check_word_budget(root)
        check_publish_gate(root)
        check_hook(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
    if bad:
        print("\nThe log is not holding:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
