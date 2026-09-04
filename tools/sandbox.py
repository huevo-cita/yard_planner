#!/usr/bin/env python3
"""A rehearsal copy of a real yard, for trying new work without touching it.

    yard sandbox new cloverleaf-austin        deep copy -> cloverleaf-sandbox
    yard sandbox list                         what exists, from what, when
    yard sandbox diff cloverleaf-sandbox      what changed against the real yard
    yard sandbox promote cloverleaf-sandbox niches.json
    yard sandbox rm cloverleaf-sandbox

Why this exists
---------------
New functionality has to be tried against real data, because the interesting
failures are all in the data — a bed measured in the wrong axis, a zone named by
its label, a figure recorded in prose. A fixture yard does not have those and so
does not test anything. But a real yard is somebody's actual plan, with a live
calendar and dated tasks, and a rehearsal that writes into it is worse than no
rehearsal at all.

So: a real copy under a distinct slug, in the same garden root, marked as a copy.

Three properties, each chosen against an alternative that does not work
-----------------------------------------------------------------------
    a real copy         never a symlink, because a symlink writes through and
                        the whole promise is that it does not.
    the same root       rather than redirecting GARDEN_ROOT, because the doubt
                        gate hook resolves the repo from its own location and
                        the gate is part of what is being rehearsed. A sandbox
                        where the gate silently allowed everything would teach
                        exactly the wrong thing.
    stamped output      every document generated inside one says so, through
                        `yards.write_text` and `doubts.gate`, so it is stamped
                        once rather than in each of a dozen modules.

Two alternatives, and why not. A `--dry-run` flag on every module needs a guard
on every write path, and one missed `yards.save` breaks the promise silently. A
git branch does not work at all, because `.gitignore` is a whitelist and yard
data is not in it — which is also why a new sandbox directory is already
un-committable with no new rule.

What this honestly protects against: accident. Not a deliberately mistyped slug.
"""

import argparse
import datetime
import difflib
import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import yards  # noqa: E402

MARKER = yards.SANDBOX_MARKER

# Copied wholesale except these. `.git` would be catastrophic and the caches are
# large and reproducible.
SKIP_DIRS = {".git", "__pycache__", ".cache"}


def default_name(origin):
    """cloverleaf-austin -> cloverleaf-sandbox. The place name is what carries
    the identity, so keeping it and replacing the locality reads correctly in a
    file listing and sorts next to its origin."""
    head = origin.split("-")[0]
    return f"{head}-sandbox"


def digest(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def files_under(d):
    """Every file in a yard, as paths relative to the yard directory."""
    out = []
    for base, dirs, names in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            if n == ".DS_Store":
                continue
            out.append(os.path.relpath(os.path.join(base, n), d))
    return sorted(out)


def is_sandbox(slug):
    return yards.sandbox_of(slug) is not None


def sandboxes():
    return [s for s in yards.list_yards() if is_sandbox(s)]


# ------------------------------------------------------------------------- new

def cmd_new(args):
    origin = args.origin
    if not os.path.isdir(yards.yard_dir(origin)):
        print(f"no yard {origin!r} to copy. `yard list` shows what there is")
        return 1
    if is_sandbox(origin):
        print(f"{origin} is itself a sandbox. Copy its origin "
              f"({yards.sandbox_of(origin)}) instead — a copy of a copy has no "
              f"origin anyone can diff against")
        return 1

    name = args.name or default_name(origin)
    dest = yards.yard_dir(name)
    if os.path.exists(dest):
        print(f"{name} already exists at {dest}.\n"
              f"  `yard sandbox diff {name}` to see what is in it, or "
              f"`yard sandbox rm {name}` first")
        return 1

    src = yards.yard_dir(origin)
    rel = files_under(src)
    # symlinks=False is the whole point: a copy that writes through is not a
    # copy. shutil.copytree resolves them by default, which is what is wanted.
    shutil.copytree(src, dest,
                    ignore=shutil.ignore_patterns(*SKIP_DIRS, ".DS_Store"),
                    symlinks=False)

    marker = {
        "origin": origin,
        "created": datetime.date.today().isoformat(),
        "files": len(rel),
        # The digest of every file as it was at copy time. This is what lets
        # `promote` refuse when the origin has moved underneath the copy — the
        # case where promoting would silently discard somebody else's work.
        "origin_digests": {r: digest(os.path.join(src, r)) for r in rel},
        "what_this_is": (
            f"A rehearsal copy of {origin}, not a yard. Nothing in here "
            f"describes work anyone should do. Delete it with `yard sandbox rm "
            f"{name}` when the rehearsal is over."),
    }
    yards.save(name, MARKER, marker)
    yards.update_registry()

    print(f"copied {origin} -> {name}  ({len(rel)} files)")
    print(f"  {dest}")
    print(f"\n  every document generated in here is stamped "
          f"{yards.sandbox_stamp(name)!r}")
    known = os.path.isdir(dest)
    print(f"  the doubt gate {'sees' if known else 'CANNOT SEE'} it as a yard, "
          f"so it {'refuses exactly as it would on the real one' if known else 'WILL FAIL OPEN'}")
    return 0


# ------------------------------------------------------------------------ list

def cmd_list(args):
    have = sandboxes()
    if not have:
        print("no sandboxes. `yard sandbox new <slug>` makes one")
        return 0
    print(f"{'sandbox':24s} {'of':24s} {'created':12s} files  drifted")
    for s in have:
        m = yards.load(s, MARKER) or {}
        n_changed = len([c for c in compare(s) if c[0] != "same"])
        print(f"{s:24s} {m.get('origin', '?'):24s} "
              f"{m.get('created', '?'):12s} {m.get('files', 0):5d}  "
              f"{n_changed}")
    return 0


# ------------------------------------------------------------------------ diff

def compare(slug):
    """(state, relpath, note) for every file, sandbox against its origin.

    Three states worth distinguishing, because the remedies differ: `added` is
    the rehearsal's own output, `changed` is a real yard file the rehearsal
    edited, and `origin-moved` is the dangerous one — somebody changed the real
    yard after the copy was taken, so promoting over it would discard that.
    """
    m = yards.load(slug, MARKER) or {}
    origin = m.get("origin")
    if not origin:
        return []
    was = m.get("origin_digests") or {}
    here, there = yards.yard_dir(slug), yards.yard_dir(origin)
    mine = set(files_under(here)) - {MARKER}
    theirs = set(files_under(there))

    out = []
    for r in sorted(mine | theirs):
        a = os.path.join(there, r)
        b = os.path.join(here, r)
        now_o = digest(a) if os.path.exists(a) else None
        now_s = digest(b) if os.path.exists(b) else None
        drifted = now_o is not None and r in was and was[r] != now_o
        if now_s is None:
            out.append(("removed-here", r, "in the real yard, not in the copy"))
        elif now_o is None:
            out.append(("added", r, "the rehearsal's own output"))
        elif now_s == now_o:
            out.append(("same", r, ""))
        elif drifted:
            out.append(("origin-moved", r,
                        "BOTH changed since the copy — promoting would discard "
                        "the real yard's version"))
        else:
            out.append(("changed", r, "changed in the copy only"))
    return out


def cmd_diff(args):
    slug = args.name
    if not is_sandbox(slug):
        print(f"{slug} is not a sandbox")
        return 1
    origin = yards.sandbox_of(slug)
    rows = [r for r in compare(slug) if r[0] != "same"]
    print(f"{slug} against {origin}")
    if not rows:
        print("  identical — nothing has been tried in here yet")
        return 0
    for state, r, note in rows:
        print(f"  {state:14s} {r}" + (f"\n                 {note}" if note else ""))

    if args.text:
        for state, r, _ in rows:
            if state != "changed" or not r.endswith((".md", ".json")):
                continue
            a = os.path.join(yards.yard_dir(origin), r)
            b = os.path.join(yards.yard_dir(slug), r)
            with open(a, encoding="utf-8", errors="replace") as f:
                x = f.readlines()
            with open(b, encoding="utf-8", errors="replace") as f:
                y = f.readlines()
            print(f"\n--- {r}")
            for line in list(difflib.unified_diff(x, y, origin, slug, n=1))[2:]:
                print("  " + line.rstrip())
    else:
        print(f"\n  `yard sandbox diff {slug} --text` for the line-by-line")
    return 0


# --------------------------------------------------------------------- promote

def cmd_promote(args):
    slug = args.name
    if not is_sandbox(slug):
        print(f"{slug} is not a sandbox")
        return 1
    origin = yards.sandbox_of(slug)
    state = {r: s for s, r, _ in compare(slug)}

    wanted = args.files
    if not wanted:
        print(f"promote takes the files to keep, deliberately — copying a whole "
              f"rehearsal back is how a rehearsal becomes the plan by accident."
              f"\n\ncandidates:")
        for s, r, _ in compare(slug):
            if s in ("added", "changed"):
                print(f"  {s:9s} {r}")
        return 1

    refused, moved = [], []
    for r in wanted:
        b = os.path.join(yards.yard_dir(slug), r)
        if not os.path.exists(b):
            refused.append((r, "not in the sandbox"))
        elif state.get(r) == "origin-moved":
            moved.append(r)
        elif state.get(r) == "same":
            refused.append((r, "identical to the real yard already"))
    for r, why in refused:
        print(f"  !! {r}: {why}")
    for r in moved:
        print(f"  !! {r}: the real yard changed this since the copy was taken. "
              f"Promoting it would discard that. Re-run the rehearsal against a "
              f"fresh copy, or merge by hand")
    if refused or moved:
        print("\nnothing promoted")
        return 1

    for r in wanted:
        b = os.path.join(yards.yard_dir(slug), r)
        a = os.path.join(yards.yard_dir(origin), r)
        os.makedirs(os.path.dirname(a), exist_ok=True)
        shutil.copy2(b, a)
        print(f"  ok {r} -> {origin}")
    print(f"\n{len(wanted)} promoted into {origin}. The sandbox still exists; "
          f"`yard sandbox rm {slug}` when done")
    return 0


# -------------------------------------------------------------------------- rm

def cmd_rm(args):
    slug = args.name
    if not is_sandbox(slug):
        print(f"{slug} is not a sandbox, and this only ever removes sandboxes")
        return 1
    rows = [r for r in compare(slug) if r[0] in ("added", "changed")]
    if rows and not args.yes:
        print(f"{slug} holds {len(rows)} files not in "
              f"{yards.sandbox_of(slug)}:")
        for _, r, _ in rows[:12]:
            print(f"  {r}")
        if len(rows) > 12:
            print(f"  ... and {len(rows) - 12} more")
        print(f"\n`yard sandbox promote {slug} <file>` to keep any of it, then "
              f"`yard sandbox rm {slug} --yes`")
        return 1
    shutil.rmtree(yards.yard_dir(slug))
    yards.update_registry()
    print(f"removed {slug}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        prog="yard sandbox", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("new", help="deep-copy a yard to a sandbox slug")
    p.add_argument("origin")
    p.add_argument("--as", dest="name", help="name it something else")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("list", help="what sandboxes exist")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("diff", help="what changed against the real yard")
    p.add_argument("name")
    p.add_argument("--text", action="store_true", help="line-by-line")
    p.set_defaults(fn=cmd_diff)

    p = sub.add_parser("promote", help="keep named files, back in the real yard")
    p.add_argument("name")
    p.add_argument("files", nargs="*")
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("rm", help="delete a sandbox")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_rm)

    args = ap.parse_args()
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
