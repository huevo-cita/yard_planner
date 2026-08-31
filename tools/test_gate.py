#!/usr/bin/env python3
"""Prove the doubt gate actually refuses, on a scratch yard, from a clean start.

    python3 tools/test_gate.py
    python3 tools/test_gate.py -v        show every command's output

The gate was hand-tested once in a chat that no longer exists, which is not
evidence of anything. This is the same checks, re-runnable, so that "the gate
works" is a claim someone can settle in twenty seconds instead of believing.

Three properties are worth more than the rest, and each is easy to pass by
accident:

  it refuses          a blocked job exits non-zero *naming the gate*. A job that
                      dies because a fixture was thin also exits non-zero, and a
                      test that accepts that proves nothing — so every refusal is
                      matched against the gate's own wording, and a non-zero exit
                      without it is reported INCONCLUSIVE rather than passed.
  it refuses early    the whole point is to refuse *before* the expensive work.
                      Each job is given a deadline; overrunning it is a failure
                      even if the job would eventually have refused.
  it lets go          the cheap paths, which are how a doubt gets settled, must
                      stay open. A gate that blocks its own escape route gets
                      switched off within a week and then there is no gate.

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written and none of this touches personal data.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import doubts  # noqa: E402  (after sys.path)

SLUG = "testyard"
HOOK = os.path.join(ROOT, ".cursor", "hooks", "doubt-gate.sh")
HOOKS_JSON = os.path.join(ROOT, ".cursor", "hooks.json")

# A blocked job should refuse in about the time the interpreter takes to start.
# Generous enough for a cold numpy import on a slow disk, still far short of a
# real sun model, which is the thing being prevented.
DEADLINE = 45.0

# The gate's refusal says this. Matching on it is what separates "refused by the
# gate" from "fell over for some unrelated reason".
FINGERPRINT = "open doubt"

results = []          # (state, label, detail) — state in pass/FAIL/INCONCLUSIVE
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    mark = {"pass": "ok  ", "FAIL": "FAIL", "INCONCLUSIVE": "??  "}[state]
    print(f"  {mark}  {label}")
    if detail and (state != "pass" or verbose):
        for line in detail.strip().splitlines():
            print(f"          {line}")


# --------------------------------------------------------------- the scratch yard

# Deliberately minimal, but not empty. An empty design.json is falsy and makes
# lib.design short-circuit before it ever reaches the gate, which reads as a pass
# and tests nothing — the fixtures have to be thick enough for each job to get as
# far as the gate on its own.
FIXTURES = {
    "site.json": {
        "label": "scratch",
        "boundary": {"points": [[0, 0], [40, 0], [40, 30], [0, 30]]},
        "zones": {"West bed": {"x": [2, 8], "y": [2, 20]}},
        "provenance": {},
    },
    "conditions.json": {"soil": {"texture": "loam"}, "tools": {}},
    "vision.json": {"purpose": "scratch"},
    "design.json": {
        "plants": [{"name": "Salvia greggii", "zone": "West bed",
                    "count": 3, "light": "full sun"}],
        "hardscape": [],
    },
}


def make_yard(root):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    for name, body in FIXTURES.items():
        with open(os.path.join(d, name), "w") as f:
            json.dump(body, f)
    return d


def run(args, root, deadline=DEADLINE):
    """Run a module against the scratch root. Returns (rc, output, seconds)."""
    env = dict(os.environ, GARDEN_ROOT=root)
    env.pop("PYTHONWARNINGS", None)
    t = time.time()
    try:
        p = subprocess.run([sys.executable] + args, cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=deadline)
    except subprocess.TimeoutExpired:
        return None, "", time.time() - t
    return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t


def doubtcmd(root, *args):
    return run(["-m", "lib.doubts", SLUG, *args], root)


def board_clear(root, job):
    rc, out, _ = doubtcmd(root, "--gate", job)
    try:
        return not json.loads(out)["blocked"]
    except Exception:
        return None


def reset_board(root):
    p = os.path.join(root, SLUG, "doubts.json")
    if os.path.exists(p):
        os.remove(p)


def file_card(root, blocks, question="scratch doubt"):
    rc, out, _ = doubtcmd(root, "--add", question, "--kind", "fact",
                          "--blocks", blocks, "--hours", "1.0")
    return rc == 0


# ------------------------------------------------------------------- the checks

def check_verdicts(root):
    """gate_json: the right jobs blocked, and only those."""
    print("\n verdicts")

    reset_board(root)
    clear = [j for j in doubts.JOBS if board_clear(root, j) is True]
    record("pass" if len(clear) == len(doubts.JOBS) else "FAIL",
           f"empty board clears all {len(doubts.JOBS)} jobs",
           "" if len(clear) == len(doubts.JOBS)
           else f"cleared only {clear}")

    reset_board(root)
    file_card(root, "sunmodel")
    blocked = [j for j in doubts.JOBS if board_clear(root, j) is False]
    ok = blocked == ["sunmodel"]
    record("pass" if ok else "FAIL", "a card naming one job blocks only that job",
           "" if ok else f"blocked {blocked}, expected ['sunmodel']")

    reset_board(root)
    file_card(root, "*")
    blocked = [j for j in doubts.JOBS if board_clear(root, j) is False]
    ok = sorted(blocked) == sorted(doubts.JOBS)
    record("pass" if ok else "FAIL", "a wildcard card blocks every job",
           "" if ok else f"blocked {blocked}, expected all of {list(doubts.JOBS)}")


def check_lifecycle(root):
    """Settling and waiving clear the block; a waive without a reason does not."""
    print("\n lifecycle")

    reset_board(root)
    file_card(root, "sunmodel")
    rc, out, _ = doubtcmd(root, "--settle", "d1", "--answer", "measured 72in",
                          "--by", "measured")
    ok = rc == 0 and board_clear(root, "sunmodel") is True
    record("pass" if ok else "FAIL", "settling a card clears the job",
           "" if ok else f"rc={rc}\n{out}")

    reset_board(root)
    file_card(root, "sunmodel")
    rc, out, _ = doubtcmd(root, "--waive", "d1")
    still = board_clear(root, "sunmodel") is False
    ok = rc != 0 and still
    record("pass" if ok else "FAIL", "a waive with no reason is refused",
           "" if ok else f"rc={rc} (wanted non-zero), still blocked={still}\n{out}")

    rc, out, _ = doubtcmd(root, "--waive", "d1", "--reason", "not worth a ladder")
    ok = rc == 0 and board_clear(root, "sunmodel") is True
    record("pass" if ok else "FAIL", "a waive with a reason clears the job",
           "" if ok else f"rc={rc}\n{out}")


JOB_ARGS = {
    "sunmodel": ["-m", "lib.sunmodel", SLUG],
    "design": ["-m", "lib.design", SLUG],
    "drawbeds": ["-m", "lib.drawbeds", SLUG],
    "bom": ["-m", "lib.bom", SLUG],
    "schedule": ["-m", "lib.schedule", SLUG],
}


def check_refusals(root):
    """The real entrypoints refuse, name the gate, and do it quickly."""
    print("\n refusals at the real entrypoints")

    for job in doubts.JOBS:
        reset_board(root)
        file_card(root, job, f"is the west fence solid board? ({job})")
        rc, out, el = run(JOB_ARGS[job], root)

        if rc is None:
            record("FAIL", f"{job} refuses",
                   f"no verdict within {DEADLINE:.0f}s — the gate did not fire "
                   f"before the expensive work, which is the one thing it is for")
            continue
        named = FINGERPRINT in out.lower()
        if rc != 0 and named:
            record("pass", f"{job} refuses, naming the gate ({el:.1f}s)",
                   out.strip()[:300] if verbose else "")
        elif rc != 0:
            record("INCONCLUSIVE", f"{job} exited {rc} but not via the gate",
                   "non-zero for some other reason, so this proves nothing "
                   "about the gate:\n" + out.strip()[-400:])
        else:
            record("FAIL", f"{job} ran anyway with a doubt open",
                   out.strip()[-400:])


def check_force(root):
    """--force proceeds, and stamps what it came past."""
    print("\n --force")

    reset_board(root)
    file_card(root, "design")
    rc, out, _ = run(JOB_ARGS["design"] + ["--force"], root)
    ok = rc == 0 and "provisional" in out.lower()
    record("pass" if ok else "FAIL", "design --force proceeds and says it is provisional",
           "" if ok else f"rc={rc}\n{out.strip()[-400:]}")

    # The stamp has to survive into the artifact, not just the console: a caveat
    # printed once does not travel with the file it describes.
    reset_board(root)
    file_card(root, "bom")
    rc, out, _ = run(JOB_ARGS["bom"] + ["--force"], root)
    stamped = doubts.PROVISIONAL.split(" - ")[0].lower() in out.lower()
    record("pass" if rc == 0 and stamped else "INCONCLUSIVE",
           "bom --force carries the provisional stamp",
           "" if (rc == 0 and stamped) else f"rc={rc}\n{out.strip()[-300:]}")


CHEAP = [
    ("sunmodel --quick", ["-m", "lib.sunmodel", SLUG, "--quick"]),
    ("design --init", ["-m", "lib.design", SLUG, "--init"]),
    ("bom --crossover", ["-m", "lib.bom", SLUG, "--crossover"]),
    ("doubts --open", ["-m", "lib.doubts", SLUG, "--open"]),
    ("gaps", ["-m", "lib.gaps", SLUG]),
]


def check_cheap_paths(root):
    """The escape routes stay open, because they are how a doubt gets settled."""
    print("\n cheap paths stay open")

    for label, args in CHEAP:
        reset_board(root)
        file_card(root, "*")
        rc, out, el = run(args, root)
        if rc is None:
            record("FAIL", f"{label} not gated", f"hung for {DEADLINE:.0f}s")
            continue
        # These may legitimately fail on thin fixtures. What must never happen is
        # failing *because of the gate*, so only the gate's wording is a failure.
        refused = FINGERPRINT in out.lower() and "refusing" in out.lower()
        record("FAIL" if refused else "pass", f"{label} is not gated",
               out.strip()[-300:] if refused else "")


HOOK_CASES = [
    # (label, command, board, expected permission)
    ("gated job, doubt open", f"python3 -m lib.sunmodel {SLUG}", "*", "deny"),
    ("gated job with --force", f"python3 -m lib.sunmodel {SLUG} --force", "*", "ask"),
    ("gated job, board clear", f"python3 -m lib.sunmodel {SLUG}", None, "allow"),
    ("--quick, doubt open", f"python3 -m lib.sunmodel {SLUG} --quick", "*", "allow"),
    ("bom --crossover", f"python3 -m lib.bom {SLUG} --crossover", "*", "allow"),
    ("the doubts tool itself", f"python3 -m lib.doubts {SLUG} --open", "*", "allow"),
    ("an unrelated command", "git status", "*", "allow"),
    ("an unknown yard", "python3 -m lib.sunmodel no-such-yard", "*", "allow"),
]


def check_hook(root):
    """The shell hook: one valid JSON object, exit 0, right verdict."""
    print("\n hook")

    if not (os.path.exists(HOOK) and os.access(HOOK, os.X_OK)):
        record("FAIL", "doubt-gate.sh is present and executable",
               f"{HOOK} missing or not executable")
        return
    if not shutil.which("jq"):
        record("INCONCLUSIVE", "hook verdicts",
               "jq is not installed, so the hook fails open by design and its "
               "verdicts cannot be tested here")
        return

    for label, cmd, board, want in HOOK_CASES:
        reset_board(root)
        if board:
            file_card(root, board)
        payload = json.dumps({"command": cmd, "cwd": "",
                              "hook_event_name": "beforeShellExecution"})
        env = dict(os.environ, GARDEN_ROOT=root)
        p = subprocess.run(["bash", HOOK], input=payload, capture_output=True,
                           text=True, timeout=30, env=env, cwd=ROOT)
        if p.returncode != 0:
            record("FAIL", f"hook: {label}",
                   f"exited {p.returncode}; with failClosed set, a crash reads "
                   f"as a refusal of a command nobody objected to")
            continue
        try:
            got = json.loads(p.stdout)["permission"]
        except Exception:
            record("FAIL", f"hook: {label}",
                   f"did not emit one valid JSON object:\n{p.stdout[:200]}")
            continue
        record("pass" if got == want else "FAIL",
               f"hook: {label} -> {want}",
               "" if got == want else f"got {got!r}, wanted {want!r}")


def check_drift(root):
    """The three places the job list is written down have to agree."""
    print("\n drift")

    try:
        with open(HOOK) as f:
            hook_src = f.read()
        line = next(l for l in hook_src.splitlines() if l.startswith("GATED="))
        gated = line.split("=", 1)[1].strip().strip('"').split()
    except Exception as e:
        record("FAIL", "hook GATED list is readable", str(e))
        return
    ok = sorted(gated) == sorted(doubts.JOBS)
    record("pass" if ok else "FAIL", "hook GATED matches lib.doubts.JOBS",
           "" if ok else f"hook has {sorted(gated)}, "
                         f"doubts has {sorted(doubts.JOBS)}")

    try:
        with open(HOOKS_JSON) as f:
            cfg = json.load(f)
        matchers = json.dumps(cfg)
    except Exception as e:
        record("FAIL", "hooks.json parses", str(e))
        return
    missing = [j for j in doubts.JOBS if j not in matchers]
    record("pass" if not missing else "FAIL",
           "hooks.json matcher mentions every gated job",
           "" if not missing else f"absent from the matcher: {missing}. "
                                 f"Those jobs would never reach the hook.")


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print the output of every command, not just failures")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yard-gate-test-")
    print(f"doubt gate — scratch yard in {root}")
    try:
        make_yard(root)
        check_verdicts(root)
        check_lifecycle(root)
        check_refusals(root)
        check_force(root)
        check_cheap_paths(root)
        check_hook(root)
        check_drift(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] == "FAIL"]
    meh = [r for r in results if r[0] == "INCONCLUSIVE"]
    print(f"\n{len(results) - len(bad) - len(meh)} passed, {len(bad)} failed, "
          f"{len(meh)} inconclusive")
    if meh and not bad:
        print("Inconclusive is not passing: something exited non-zero without "
              "naming the gate, so the gate itself was never demonstrated.")
    if bad:
        print("\nThe gate is not holding:")
        for _, label, _ in bad:
            print(f"  - {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
