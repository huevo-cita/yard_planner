#!/usr/bin/env python3
"""Break the all-clear on purpose and check the suite notices.

A regression test that has never failed is a hypothesis, not evidence. This
applies a set of small, plausible-looking edits to the gate — each one the kind
of change someone could make while tidying — runs `tools/test_gate.py` against
each, and reports which tests died. A mutation nothing catches is a hole in the
suite, not a bug in the mutation.

Every file is restored in a `finally`, and the whole run re-verifies a clean
tree at the end, because a harness that leaves the repo broken is worse than no
harness.

**It edits the working tree.** `lib/doubts.py`, `lib/inputs.py` and
`.cursor/hooks/doubt-gate.sh` are rewritten in place for the length of one test
run each — around ten seconds — and put back afterwards. A `SIGKILL`, a power
cut, or a `git commit -a` from another terminal inside that window will catch a
deliberately broken gate, and the commit will look ordinary. `git diff` after a
crash says what happened, and `git checkout` on those three files fixes it. Do
not run this on a tree with uncommitted work you would not want to re-derive.

    python3 tools/mutate_gate.py            # all of them
    python3 tools/mutate_gate.py --list
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, file, what it stands for, old, new)
MUTATIONS = [
    (
        "silence-clears",
        "lib/doubts.py",
        "the gate treats a missing all-clear as fine — the exact default this "
        "change was made to invert",
        '    if not filed:\n        return dict(base, state="missing", summary=(',
        '    if not filed:\n        return dict(base, state="ok", summary=(',
    ),
    (
        "never-stale",
        "lib/doubts.py",
        "the freshness check is dropped, so one all-clear rubber-stamps the "
        "yard forever",
        "    if moved or appeared or shape:\n        detail = []",
        "    if False:\n        detail = []",
    ),
    (
        "coverage-not-checked",
        "lib/doubts.py",
        "filing stops checking that every assumed input is answered for, so a "
        "clearance can be filed with a hole in it",
        "        missed = [s[\"path\"] for s in soft\n"
        "                  if not any(_covers(e, s[\"path\"]) for e in entries)]",
        "        missed = []",
    ),
    (
        "open-doubt-cited",
        "lib/doubts.py",
        "citing a doubt card that is still open counts as an answer, which is "
        "the original failure with a citation on it",
        '        elif c.get("status") == "open" and not why:',
        '        elif False:',
    ),
    (
        "soft-set-empty",
        "lib/inputs.py",
        "nothing is ever classified as assumed or reported, so every clearance "
        "is vacuous and every job walks through",
        'SOFT_SOURCES = ("assumed", "reported")',
        'SOFT_SOURCES = ()',
    ),
    (
        "input-map-narrowed",
        "lib/inputs.py",
        "a job's declared inputs drop a section it really reads, so the gate "
        "stops asking about part of the record",
        '        "sections": ["address", "analysis_bands", "boundary", "features",\n'
        '                     "frame", "narrative", "obstructions", "pending_site_walk",\n'
        '                     "zones"],',
        '        "sections": ["address", "analysis_bands", "features",\n'
        '                     "frame", "narrative", "obstructions", "pending_site_walk",\n'
        '                     "zones"],',
    ),
    (
        "renew-carries-the-moved",
        "lib/doubts.py",
        "renewing carries a reason forward for a value that has since changed, "
        "which turns the one convenience here into a rubber stamp",
        '        if touched and not any(p in out["moved"] for p in touched):',
        '        if touched:',
    ),
    (
        "shape-blind",
        "lib/doubts.py",
        "the census check goes away, so a new obstruction carrying no "
        "provenance entry is invisible to every clearance",
        '    was = filed.get("census")\n    if was is None:\n        return []',
        '    was = filed.get("census")\n    if True:\n        return []',
    ),
    (
        "alias-blind",
        "lib/inputs.py",
        "the scan stops following a record assigned to a local name, so "
        "drift() reports clean on a section it never saw",
        "        if tree is not None:\n            self._learn_aliases(tree)",
        "        if tree is None:\n            self._learn_aliases(tree)",
    ),
    (
        "hook-allows-silence",
        ".cursor/hooks/doubt-gate.sh",
        "the hook stops denying and only the in-process gate is left, so the "
        "block arrives after the command has already been chosen",
        '[ "$BLOCKED" = "true" ] || allow',
        '[ "$BLOCKED" = "never" ] || allow',
    ),
]


def run_suite(timeout=900):
    p = subprocess.run([sys.executable, os.path.join(HERE, "test_gate.py")],
                       cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    failed, incon = [], []
    for line in p.stdout.splitlines():
        for mark, bucket in (("FAIL", failed), ("??", incon)):
            if line.startswith(f"  {mark}  "):
                bucket.append(line[2 + len(mark):].strip())
    return p.returncode, failed, incon, p.stdout


def drop_pycache():
    """So a rewritten module is never read through a cache of the old one.

    Rewriting a file in place and re-running immediately is exactly the case
    where mtime-based invalidation is at its least reliable, and a stale or
    half-written .pyc shows up here as a test that fails for no visible reason.
    """
    for d in ("lib", "tools"):
        shutil.rmtree(os.path.join(ROOT, d, "__pycache__"), ignore_errors=True)


def apply(path, old, new):
    full = os.path.join(ROOT, path)
    with open(full) as f:
        text = f.read()
    if text.count(old) != 1:
        raise SystemExit(f"mutation site in {path} matched {text.count(old)} "
                         f"times, expected exactly 1 — the code has moved and "
                         f"this harness needs updating before it can be trusted")
    with open(full, "w") as f:
        f.write(text.replace(old, new))
    drop_pycache()
    return text


def restore(path, text):
    with open(os.path.join(ROOT, path), "w") as f:
        f.write(text)
    drop_pycache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", help="run one mutation by name")
    a = ap.parse_args()

    if a.list:
        for name, path, what, _, _ in MUTATIONS:
            print(f"  {name:22s} {path:28s} {what}")
        return

    todo = [m for m in MUTATIONS if not a.only or m[0] == a.only]
    if not todo:
        raise SystemExit(f"no mutation named {a.only!r}")

    print(f"mutation — {len(todo)} deliberate breakages\n")
    code, failed, incon, out = run_suite()
    if code != 0:
        print(out)
        raise SystemExit("the suite does not pass before mutating. Fix that "
                         "first; nothing measured from here would mean anything.")
    print(f" baseline: green\n")

    survivors = []
    for name, path, what, old, new in todo:
        original = None
        try:
            original = apply(path, old, new)
            code, failed, incon, out = run_suite()
        finally:
            if original is not None:
                restore(path, original)
        caught = code != 0 and failed
        mark = "ok  " if caught else "MISS"
        print(f" {mark}  {name}")
        print(f"        {what}")
        if caught:
            print(f"        caught by {len(failed)} test"
                  f"{'s' if len(failed) > 1 else ''}:")
            for f in failed[:4]:
                print(f"          - {f}")
            if len(failed) > 4:
                print(f"          - and {len(failed) - 4} more")
        elif incon:
            # Only inconclusives means something died without naming the gate,
            # which does not demonstrate the gate held. Not a catch.
            print(f"        SURVIVED as far as the gate goes — {len(incon)} "
                  f"inconclusive, no test named it")
            survivors.append(name)
        else:
            print(f"        SURVIVED. Nothing in the suite noticed.")
            survivors.append(name)
        print()

    code, failed, incon, out = run_suite()
    if code != 0:
        print(out)
        raise SystemExit("the suite is red after restoring. The tree is not "
                         "back the way it was — check `git diff` before doing "
                         "anything else.")
    print("tree restored, suite green again.")

    if survivors:
        print(f"\n{len(survivors)} mutation"
              f"{'s' if len(survivors) > 1 else ''} survived: "
              + ", ".join(survivors))
        raise SystemExit(1)
    print(f"\nall {len(todo)} caught.")


if __name__ == "__main__":
    main()
