#!/usr/bin/env python3
"""Scan for personal data that must not reach a public remote.

    python3 tools/scrub.py                 check everything git is tracking
    python3 tools/scrub.py --staged        check only what is staged, for a hook
    python3 tools/scrub.py --install-hook  wire it into .git/hooks/pre-commit
    python3 tools/scrub.py <path> ...      check specific files

`.gitignore` is the real defence, and it is a whitelist, so a new yard directory
is excluded the moment it exists. This is the second line: it catches the case
the ignore rules cannot, which is a real address or a real coordinate copied
into a file that *is* tracked — a docstring example, a README, a skill written
against a live yard.

The distinction that matters and is easy to get wrong: an example needs to look
real to be useful, and something that looks real is indistinguishable from
something that is real. So the rule here is not "no coordinates". It is "no
coordinates outside the small allowlist of deliberately public landmarks", which
forces a choice to be made once, in the open, rather than assumed each time.

Exit code is 1 on any finding, so a pre-commit hook stops the commit.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Deliberately public places, used in documentation examples. Anything outside
# this list is treated as somebody's home until a human says otherwise.
ALLOWED_COORDS = {
    ("39.7392", "-104.9903"),      # Denver, CO — civic centre
    ("1600", "Pennsylvania"),      # the obvious one
}
ALLOWED_SUBSTRINGS = (
    "1600 Pennsylvania",
    "39.7392", "-104.9903",
    "America/Denver", "America/New_York", "America/Chicago",
)

# Text files worth reading. A PNG can carry an address in its pixels, which no
# regex will find; that is what the ignore whitelist is for.
TEXT_SUFFIX = (".py", ".md", ".json", ".txt", ".sh", ".yml", ".yaml", ".toml",
               ".cfg", ".html", ".gitignore", ".gitattributes")

CHECKS = [
    ("street address",
     re.compile(r"\b\d{1,6}\s+[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3}\s+"
                r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|"
                r"Boulevard|Ct|Court|Way|Pl|Place|Ter|Terrace|Cir|Circle|Hwy|"
                r"Pkwy|Parkway)\b\.?", re.M),
     "a house number with a street name"),
    ("latitude/longitude pair",
     re.compile(r"[-+]?\b\d{1,3}\.\d{4,}\b\s*[,\s]\s*[-+]\d{1,3}\.\d{4,}\b"),
     "a coordinate precise enough to place a rooftop"),
    ("US ZIP code in context",
     re.compile(r"\b(?:zip|postal|zipcode|zip_code)\D{0,12}(\d{5})\b", re.I),
     "a postal code tied to a record"),
    ("parcel identifier",
     re.compile(r"\b(?:BBL|APN|parcel_?id|mukey|pin)\W{0,4}\d{6,}\b", re.I),
     "a parcel number, which resolves to an owner name in a public registry"),
    ("personal path",
     re.compile(r"/Users/[a-z][a-z0-9._-]+/", re.I),
     "a home directory path naming the account"),
]


def tracked_files():
    out = subprocess.run(["git", "-C", ROOT, "ls-files"],
                         stdout=subprocess.PIPE, check=False)
    return [os.path.join(ROOT, p) for p in out.stdout.decode().splitlines()]


def staged_files():
    out = subprocess.run(
        ["git", "-C", ROOT, "diff", "--cached", "--name-only",
         "--diff-filter=ACMR"], stdout=subprocess.PIPE, check=False)
    return [os.path.join(ROOT, p) for p in out.stdout.decode().splitlines()]


def allowed(line):
    return any(a in line for a in ALLOWED_SUBSTRINGS)


def scan(paths):
    findings = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        if not path.endswith(TEXT_SUFFIX) and \
                os.path.basename(path) not in (".gitignore", ".gitattributes"):
            continue
        # This file is a catalogue of the patterns; it would report itself.
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if allowed(line):
                continue
            for name, rx, why in CHECKS:
                m = rx.search(line)
                if m:
                    findings.append({
                        "path": os.path.relpath(path, ROOT), "line": n,
                        "kind": name, "why": why,
                        "text": line.strip()[:120], "match": m.group(0)[:60]})
                    break
    return findings


def report(findings, checked):
    if not findings:
        print(f"scrub: clean. {checked} tracked text files checked, nothing "
              f"that identifies a property or a person.")
        return 0
    print(f"scrub: {len(findings)} thing"
          f"{'s' if len(findings) > 1 else ''} that should not be published\n")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  [{f['kind']}]")
        print(f"      found   {f['match']}")
        print(f"      why     {f['why']}")
        print(f"      line    {f['text']}\n")
    print("Fix by replacing the value with a neutral example, or move the file "
          "out of the tracked set. If a value is genuinely public and belongs "
          "in documentation, add it to ALLOWED_SUBSTRINGS in tools/scrub.py so "
          "the exception is recorded rather than repeated.")
    return 1


HOOK = """#!/bin/sh
# Installed by tools/scrub.py. Blocks a commit that would publish an address,
# a rooftop coordinate or a parcel number. Bypass with --no-verify only if you
# have actually looked at what it found.
exec python3 "$(git rev-parse --show-toplevel)/tools/scrub.py" --staged
"""


def install_hook():
    d = os.path.join(ROOT, ".git", "hooks")
    if not os.path.isdir(d):
        raise SystemExit("no .git/hooks — is this a git checkout?")
    p = os.path.join(d, "pre-commit")
    with open(p, "w") as fh:
        fh.write(HOOK)
    os.chmod(p, 0o755)
    print(f"installed {os.path.relpath(p, ROOT)}. Every commit is now checked.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--install-hook", action="store_true")
    args = ap.parse_args()

    if args.install_hook:
        return install_hook()

    paths = ([os.path.abspath(p) for p in args.paths] or
             (staged_files() if args.staged else tracked_files()))
    sys.exit(report(scan(paths), len(paths)))


if __name__ == "__main__":
    main()
