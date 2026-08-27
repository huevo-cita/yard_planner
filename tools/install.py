#!/usr/bin/env python3
"""Link this repo's skills and subagents into ~/.cursor so the agent sees them.

    python3 tools/install.py            link everything, report what changed
    python3 tools/install.py --check    say what would happen, change nothing
    python3 tools/install.py --remove   unlink, leaving the repo untouched

Symlinks rather than copies, on purpose. A copy means two versions of every
skill and a slow drift between the one being edited and the one being run,
which is exactly the failure this repo exists to prevent. With a link there is
one file, and `git status` tells the truth about it.

A skill directory that already exists and is a real directory is never
overwritten — it is reported and skipped, because it might be work that was
never committed.
"""

import argparse
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURSOR = os.path.expanduser(os.environ.get("CURSOR_HOME", "~/.cursor"))
TARGETS = [("skills", os.path.join(CURSOR, "skills")),
           ("agents", os.path.join(CURSOR, "agents"))]


def entries(kind):
    src = os.path.join(ROOT, kind)
    if not os.path.isdir(src):
        return []
    return sorted(n for n in os.listdir(src) if not n.startswith("."))


def plan():
    out = []
    for kind, dest_dir in TARGETS:
        for name in entries(kind):
            src = os.path.join(ROOT, kind, name)
            dest = os.path.join(dest_dir, name)
            if os.path.islink(dest):
                state = "ok" if os.path.realpath(dest) == os.path.realpath(src) \
                    else "relink"
            elif os.path.exists(dest):
                state = "conflict"
            else:
                state = "link"
            out.append((kind, name, src, dest, dest_dir, state))
    return out


def apply(items, remove=False):
    changed = 0
    for kind, name, src, dest, dest_dir, state in items:
        if remove:
            if os.path.islink(dest):
                os.unlink(dest)
                print(f"  unlinked {kind}/{name}")
                changed += 1
            continue
        if state == "ok":
            continue
        if state == "conflict":
            print(f"  SKIPPED  {kind}/{name}: a real file or directory is "
                  f"already at {dest}.")
            print(f"           Move it aside first if the repo's copy should "
                  f"win — it may hold uncommitted work.")
            continue
        os.makedirs(dest_dir, exist_ok=True)
        if os.path.islink(dest):
            os.unlink(dest)
        os.symlink(src, dest)
        print(f"  linked   {kind}/{name}")
        changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()

    items = plan()
    if not items:
        raise SystemExit("nothing to install: no skills/ or agents/ directory.")

    if args.check:
        for kind, name, _, dest, _, state in items:
            print(f"  {state:<9} {kind}/{name}")
        conflicts = sum(1 for i in items if i[5] == "conflict")
        print(f"\n{len(items)} entries, {conflicts} conflict"
              f"{'s' if conflicts != 1 else ''}. Nothing was changed.")
        return

    print(f"{'unlinking' if args.remove else 'linking'} into {CURSOR}")
    n = apply(items, remove=args.remove)
    print(f"\n{n} change{'s' if n != 1 else ''}.")
    if not args.remove:
        print("Restart the agent, or start a new chat, for it to pick these up.")


if __name__ == "__main__":
    main()
