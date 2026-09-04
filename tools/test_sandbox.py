#!/usr/bin/env python3
"""Prove a sandbox is a copy, is marked as one, and cannot quietly overwrite.

    python3 tools/test_sandbox.py
    python3 tools/test_sandbox.py -v        show every command's output

The whole value of a rehearsal copy is a promise — that nothing done inside it
reaches the real yard. A promise like that is worth exactly as much as the test
of it, so four properties, each of which would be easy to get wrong and silent
if it were:

  it is a real copy    writing in the sandbox does not change the origin. A
                       symlinked "copy" passes every other check here and fails
                       this one, which is why it is first.
  it says what it is   a document rendered inside a sandbox carries a banner
                       naming its origin, and the doubt gate returns the stamp
                       for a job that is otherwise clear. An unstamped rehearsal
                       artifact found in six months is indistinguishable from
                       the plan.
  the gate still bites a sandbox is a real directory under the garden root, so
                       `yard_known` is true and both the hook and the in-process
                       gate refuse in it exactly as they would on the origin. A
                       rehearsal in which the gate silently allowed everything
                       would teach the wrong thing.
  promote refuses      when the origin has moved since the copy was taken,
                       promoting would discard whatever moved it. That is the
                       one case where the tool has to say no, and it is the
                       hardest to notice by hand.

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ORIGIN = "testyard-austin"
SAND = "testyard-sandbox"
HOOK = os.path.join(ROOT, ".cursor", "hooks", "doubt-gate.sh")

# Thick enough that lib.design reaches the gate rather than short-circuiting on
# an empty design, and that there is a real file to promote.
FIXTURES = {
    "site.json": {
        "label": "scratch",
        "boundary": {"points": [[0, 0], [40, 0], [40, 30], [0, 30]]},
        "zones": {"West bed": {"x": [2, 8], "y": [2, 20], "area_sqft": 40.0}},
        "provenance": {"zones.West bed.x": {"source": "assumed"}},
    },
    "conditions.json": {"soil": {"texture": "loam"}, "tools": {}},
    "vision.json": {"purpose": "scratch"},
    "design.json": {"plants": [{"name": "Salvia greggii", "zone": "West bed",
                                "count": 3, "light": "full sun",
                                "mature_spread_ft": 1.75}],
                    "hardscape": []},
}

results = []
verbose = False


def record(state, label, detail=""):
    results.append((state, label, detail))
    print(f"  {'ok  ' if state == 'pass' else 'FAIL'}  {label}")
    if detail and (state != "pass" or verbose):
        for line in str(detail).strip().splitlines()[:12]:
            print(f"          {line}")


def check(label, cond, detail=""):
    record("pass" if cond else "FAIL", label, detail)


def run(root, *args):
    env = dict(os.environ, GARDEN_ROOT=root)
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                     "sandbox.py")] + list(args),
                       cwd=ROOT, env=env, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def make_origin(root):
    d = os.path.join(root, ORIGIN)
    os.makedirs(d, exist_ok=True)
    for name, body in FIXTURES.items():
        with open(os.path.join(d, name), "w") as f:
            json.dump(body, f)
    with open(os.path.join(d, "PLAN.md"), "w") as f:
        f.write("# Plan\n\nDo the thing on Saturday.\n")
    return d


def read(root, slug, name):
    with open(os.path.join(root, slug, name), encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------- the tests

def test_copy_is_a_copy(root):
    print("\na copy, not a symlink")
    code, out = run(root, "new", ORIGIN, "--as", SAND)
    check("new succeeds", code == 0, out)
    check("it is a directory, not a link",
          os.path.isdir(os.path.join(root, SAND))
          and not os.path.islink(os.path.join(root, SAND)))
    check("no file inside is a link",
          not any(os.path.islink(os.path.join(root, SAND, f))
                  for f in os.listdir(os.path.join(root, SAND))))

    # The property that matters: write in the sandbox, origin unmoved.
    with open(os.path.join(root, SAND, "PLAN.md"), "w") as f:
        f.write("# Plan\n\nRehearsal nonsense.\n")
    check("writing in the sandbox leaves the origin alone",
          "Saturday" in read(root, ORIGIN, "PLAN.md"),
          read(root, ORIGIN, "PLAN.md"))

    code, out = run(root, "new", ORIGIN, "--as", SAND)
    check("a second copy over the same name is refused", code != 0, out)
    code, out = run(root, "new", SAND)
    check("a copy of a copy is refused", code != 0, out)


def test_it_says_what_it_is(root):
    print("\nit says what it is")
    env = dict(os.environ, GARDEN_ROOT=root)
    p = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.');"
         "from lib import yards, doubts;"
         f"print(repr(yards.sandbox_stamp('{SAND}')));"
         f"print(repr(yards.sandbox_stamp('{ORIGIN}')));"
         f"yards.write_text('{SAND}', 'REPORT.md', '# Report\\n\\nbody\\n');"
         f"yards.write_text('{ORIGIN}', 'REPORT.md', '# Report\\n\\nbody\\n')"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    lines = (p.stdout or "").strip().splitlines()
    check("the sandbox has a stamp",
          lines and lines[0] == repr(f"SANDBOX of {ORIGIN}"), p.stdout + p.stderr)
    check("the real yard has none",
          len(lines) > 1 and lines[1] == "None", p.stdout + p.stderr)
    check("a rendered document carries the banner",
          "SANDBOX of" in read(root, SAND, "REPORT.md"),
          read(root, SAND, "REPORT.md"))
    check("and the real yard's does not",
          "SANDBOX of" not in read(root, ORIGIN, "REPORT.md"))
    check("the banner does not double on a second write",
          read(root, SAND, "REPORT.md").count("SANDBOX of") == 1)
    os.remove(os.path.join(root, ORIGIN, "REPORT.md"))


def test_the_gate_still_bites(root):
    print("\nthe gate refuses inside a sandbox")
    env = dict(os.environ, GARDEN_ROOT=root)
    p = subprocess.run(
        [sys.executable, "-c",
         "import sys, json; sys.path.insert(0,'.');"
         "from lib import doubts;"
         f"print(json.dumps(doubts.gate_json('{SAND}', 'design')))"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    try:
        v = json.loads(p.stdout)
    except ValueError:
        record("FAIL", "gate_json parses in a sandbox", p.stdout + p.stderr)
        return
    # This is the specific trap: the hook routes `yard_known == false` straight
    # to allow, so a sandbox the gate cannot see would silently permit
    # everything, and the rehearsal would prove the opposite of the truth.
    check("the sandbox is a known yard", v["yard_known"] is True, p.stdout)
    check("and design is blocked in it (no all-clear)", v["blocked"] is True,
          v["clearance"]["summary"])

    p = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.');"
         "from lib import doubts;"
         f"doubts.gate('{SAND}', 'design')"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    check("the in-process gate raises too", p.returncode != 0,
          (p.stderr or p.stdout)[:400])
    check("and its refusal names the gate",
          "all-clear" in (p.stderr + p.stdout).lower()
          or "open doubt" in (p.stderr + p.stdout).lower())

    if os.access(HOOK, os.X_OK):
        p = subprocess.run(
            [HOOK], input=json.dumps({
                "command": f"python3 -m lib.design {SAND}", "cwd": ROOT}),
            env=env, capture_output=True, text=True)
        try:
            got = json.loads(p.stdout).get("permission")
        except ValueError:
            got = p.stdout[:200]
        check("the hook denies it as well", got == "deny", p.stdout[:400])


def test_promote(root):
    print("\npromote keeps what is named, and refuses what it must")
    with open(os.path.join(root, SAND, "niches.json"), "w") as f:
        json.dump({"niches": []}, f)

    code, out = run(root, "promote", SAND)
    check("promote with nothing named refuses and lists candidates",
          code != 0 and "niches.json" in out, out)

    code, out = run(root, "promote", SAND, "niches.json")
    check("a named new file is promoted", code == 0, out)
    check("and lands in the origin",
          os.path.exists(os.path.join(root, ORIGIN, "niches.json")))

    code, out = run(root, "promote", SAND, "nothing-here.json")
    check("a file that is not in the sandbox is refused", code != 0, out)

    # The dangerous case. Both sides changed since the copy, so promoting
    # would discard whatever moved the origin, and nothing about the file
    # itself reveals that.
    with open(os.path.join(root, ORIGIN, "PLAN.md"), "w") as f:
        f.write("# Plan\n\nSomebody else edited this on Tuesday.\n")
    code, out = run(root, "diff", SAND)
    check("diff names it origin-moved", "origin-moved" in out, out)
    code, out = run(root, "promote", SAND, "PLAN.md")
    check("promote refuses it", code != 0, out)
    check("and says why, rather than just failing",
          "discard" in out.lower(), out)
    check("the origin is untouched",
          "Tuesday" in read(root, ORIGIN, "PLAN.md"))


def test_list_and_rm(root):
    print("\nlist and rm")
    code, out = run(root, "list")
    check("list names the sandbox and its origin",
          SAND in out and ORIGIN in out, out)

    code, out = run(root, "rm", SAND)
    check("rm refuses while the sandbox holds work", code != 0, out)
    check("and points at promote", "promote" in out, out)

    code, out = run(root, "rm", SAND, "--yes")
    check("rm --yes removes it", code == 0, out)
    check("the directory is gone", not os.path.exists(os.path.join(root, SAND)))
    check("the origin survives", os.path.isdir(os.path.join(root, ORIGIN)))

    code, out = run(root, "rm", ORIGIN, "--yes")
    check("rm refuses a real yard outright", code != 0, out)
    check("the real yard is still there",
          os.path.isdir(os.path.join(root, ORIGIN)))


def main():
    global verbose
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    verbose = ap.parse_args().verbose

    root = tempfile.mkdtemp(prefix="yard-sandbox-test-")
    print(f"a sandbox is a copy, is marked, and cannot overwrite\n  root {root}")
    try:
        make_origin(root)
        test_copy_is_a_copy(root)
        test_it_says_what_it_is(root)
        test_the_gate_still_bites(root)
        test_promote(root)
        test_list_and_rm(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [r for r in results if r[0] != "pass"]
    print(f"\n{len(results) - len(bad)} of {len(results)} passed")
    if bad:
        print("\nfailed:")
        for _, label, _ in bad:
            print(f"  {label}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
