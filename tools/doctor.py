#!/usr/bin/env python3
"""Check a machine can actually run this, and say what is missing.

    python3 tools/doctor.py

Every check states what breaks without the thing, rather than only whether it is
present, because "rasterio: missing" tells you nothing about whether you can get
on with your afternoon.
"""

import importlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MODULES = [
    ("numpy", True, "everything. The sun model is one big array operation."),
    ("matplotlib", True, "every drawing and every chart."),
    ("PIL", False, "photo measurement annotation, in lib.photomeasure."),
    ("laspy", False, "lidar. Without it, tree and roof heights have to be "
                     "measured by hand or guessed."),
    ("lazrs", False, "reading compressed LAZ tiles, which is how USGS ships "
                     "3DEP. laspy without it will refuse the files."),
    ("rasterio", False, "coordinate transforms for lidar projections."),
]

BINARIES = [
    ("openssl", True, "the vault. Without it, yard data cannot be encrypted "
                      "and so cannot travel in the repo."),
    ("git", True, "version control, and the pre-commit PII guard."),
    ("jq", False, "the doubt gate hook. Without it the hook fails open and "
                  "only the in-process Python gate holds."),
]


def check_python():
    v = sys.version_info
    ok = v >= (3, 9)
    print(f"  {'ok  ' if ok else 'FAIL'}  python {v.major}.{v.minor}.{v.micro}")
    if not ok:
        print("        3.9 or newer. zoneinfo, which handles daylight saving "
              "in the solar clock, arrived in 3.9.")
    return ok


def check_modules():
    bad = 0
    for name, required, why in MODULES:
        try:
            importlib.import_module(name)
            print(f"  ok    {name}")
        except ImportError:
            tag = "FAIL" if required else "warn"
            bad += required
            print(f"  {tag}  {name} is missing — no {why}")
    return bad == 0


def check_binaries():
    bad = 0
    for name, required, why in BINARIES:
        if shutil.which(name):
            print(f"  ok    {name}")
        else:
            tag = "FAIL" if required else "warn"
            bad += required
            print(f"  {tag}  {name} is missing — no {why}")
    return bad == 0


def check_layout():
    ok = True
    for d in ("lib", "skills", "agents", "tools"):
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            print(f"  ok    {d}/")
        else:
            print(f"  FAIL  {d}/ is missing from the checkout")
            ok = False
    hook = os.path.join(ROOT, ".git", "hooks", "pre-commit")
    if os.path.exists(hook):
        print("  ok    pre-commit PII guard installed")
    else:
        print("  warn  no pre-commit guard. `python3 tools/scrub.py "
              "--install-hook` stops an address reaching the remote.")
    return ok


def check_data():
    from lib import yards
    print(f"  data root: {yards.GARDEN_ROOT}")
    if yards.GARDEN_ROOT == yards.REPO_ROOT:
        print("        (same as the checkout — fine, and the default. Set "
              "GARDEN_ROOT to keep personal data outside a repo.)")
    found = yards.list_yards()
    if found:
        print(f"  ok    {len(found)} yard{'s' if len(found) != 1 else ''}: "
              f"{', '.join(found)}")
    else:
        print("  warn  no yards yet. `yard vault unlock --all` restores them "
              "from the vault, or the new-yard skill starts one.")
    return True


def check_gate():
    """The doubt gate, at both layers, and where the outer one is blind."""
    from lib import doubts

    ok = True
    conf = os.path.join(ROOT, ".cursor", "hooks.json")
    script = os.path.join(ROOT, ".cursor", "hooks", "doubt-gate.sh")

    print("  ok    lib.doubts gate is in-process and always holds")

    if not os.path.exists(conf):
        print("  warn  no .cursor/hooks.json, so nothing denies the shell "
              "command itself. The Python gate still refuses.")
        return True
    if not os.path.exists(script):
        print("  FAIL  .cursor/hooks.json points at a doubt-gate.sh that is "
              "not there. With failClosed set, every gated job is blocked.")
        return False
    if not os.access(script, os.X_OK):
        print("  FAIL  .cursor/hooks/doubt-gate.sh is not executable, so it "
              "exits 126 and failClosed blocks every gated job. "
              "`chmod +x .cursor/hooks/doubt-gate.sh`")
        return False
    print("  ok    doubt-gate.sh is present and executable")

    # Drift between the matcher and the job list is silent and total: a job
    # added to JOBS but not to the matcher is never gated by the hook, and
    # nothing anywhere says so.
    try:
        with open(conf) as fh:
            entries = json.load(fh)["hooks"]["beforeShellExecution"]
        matcher = next((e.get("matcher") for e in entries
                        if "doubt-gate.sh" in e.get("command", "")), None)
    except Exception as exc:
        print(f"  FAIL  .cursor/hooks.json will not parse: {exc}")
        return False

    if matcher:
        missed = [j for j in doubts.JOBS if f"lib\\.{j}" not in matcher
                  and j not in re.findall(r"[a-z]+", matcher)]
        if missed:
            print(f"  warn  the hook matcher does not mention "
                  f"{', '.join(missed)}, so the shell command for "
                  f"{'those jobs is' if len(missed) > 1 else 'that job is'} "
                  f"never denied. Only the Python gate covers "
                  f"{'them' if len(missed) > 1 else 'it'}.")
        else:
            print(f"  ok    matcher covers all {len(doubts.JOBS)} gated jobs")

    # The all-clear asks about the values a job reads, so the map of which
    # values those are has to still describe the code. Drift here is worse than
    # silent: the gate keeps refusing and keeps accepting clearances, and the
    # clearances quietly stop covering something.
    from lib import inputs
    problems = inputs.drift()
    if problems:
        print(f"  FAIL  the per-job input map has drifted from lib/. An "
              f"all-clear would attest to the wrong set:")
        for p in problems:
            print(f"          {p}")
        ok = False
    else:
        print(f"  ok    the all-clear knows what each of the "
              f"{len(doubts.JOBS)} jobs reads")

    from lib import yards
    if yards.GARDEN_ROOT != yards.REPO_ROOT:
        print("  warn  GARDEN_ROOT is set away from the checkout. The hook is a "
              "child of the editor, not of your shell, so it only finds those "
              "yards if the editor itself was launched with GARDEN_ROOT set. "
              "Where it cannot find a yard it fails open, by design — the "
              "Python gate is what holds in that case.")
    return ok


def check_git():
    r = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", "example-yard"],
                       check=False)
    if r.returncode == 0:
        print("  ok    .gitignore excludes an unknown yard directory by default")
        return True
    print("  FAIL  .gitignore does NOT exclude a new yard directory. Yard data "
          "would be committed. Do not push until this is fixed.")
    return False


def main():
    print("yard planner — environment\n")
    print(" python")
    a = check_python()
    print("\n packages")
    b = check_modules()
    print("\n binaries")
    c = check_binaries()
    print("\n checkout")
    d = check_layout()
    print("\n privacy")
    e = check_git()
    print("\n doubt gate")
    f = check_gate()
    print("\n data")
    check_data()

    ok = all([a, b, c, d, e, f])
    print("\n" + ("ready." if ok else
                  "not ready. The FAIL lines above have to be fixed first."))
    print("Optional packages only limit what can be measured automatically; "
          "everything else still runs.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
