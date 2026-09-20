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

Since the all-clear landed there is a fourth, and it is the one most worth
having a test for, because the whole change turns on it:

  silence refuses     an empty board does not clear a job. The gate wants a
                      positive all-clear naming every assumed or reported value
                      the job reads, and that clearance is bound to a digest of
                      those values, so editing site.json underneath it blocks
                      again. A test that only proved "a filed doubt blocks"
                      would pass just as happily with the inversion reverted.

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

from lib import doubts, inputs  # noqa: E402  (after sys.path)

SLUG = "testyard"
HOOK = os.path.join(ROOT, ".cursor", "hooks", "doubt-gate.sh")
HOOKS_JSON = os.path.join(ROOT, ".cursor", "hooks.json")

# A blocked job should refuse in about the time the interpreter takes to start.
# Generous enough for a cold numpy import on a slow disk, still far short of a
# real sun model, which is the thing being prevented.
DEADLINE = 45.0

# The gate's refusal says one of these. Matching on them is what separates
# "refused by the gate" from "fell over for some unrelated reason". Two now,
# because there are two ways to be blocked and the second one — no current
# all-clear — is the common case on a yard nobody has raised a card against.
FINGERPRINTS = ("open doubt", "all-clear")


def named_the_gate(out):
    low = (out or "").lower()
    return any(f in low for f in FINGERPRINTS)

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
#
# The provenance map is chosen so the jobs do not all see the same thing.
# `zones.West bed.x` is read by every job that costs or schedules a bed;
# `boundary.points` and the tree crown are read only by the sun model; the
# measured entry must never appear in an all-clear at all. Without that spread
# the per-job input map could be the same set five times over and no test here
# would notice.
SOFT_EVERYWHERE = "zones.West bed.x"
SOFT_SUNMODEL_ONLY = "boundary.points"

FIXTURES = {
    "site.json": {
        "label": "scratch",
        "boundary": {"points": [[0, 0], [40, 0], [40, 30], [0, 30]]},
        "zones": {"West bed": {"x": [2, 8], "y": [2, 20]}},
        "provenance": {
            SOFT_EVERYWHERE: {"source": "assumed", "note": "paced, not taped"},
            SOFT_SUNMODEL_ONLY: {"source": "reported"},
            "features.trees.0.crown_radius": {"source": "assumed"},
            "zones.West bed.y": {"source": "measured"},
        },
    },
    "conditions.json": {"soil": {"texture": "loam"}, "tools": {}},
    "vision.json": {"purpose": "scratch"},
    "design.json": {
        "plants": [{"name": "Salvia greggii", "zone": "West bed",
                    "count": 3, "light": "full sun"}],
        "hardscape": [],
    },
}

# Wide enough to cover every soft path in the fixture in one line. Real use
# should be narrower, and the point of allowing this at all is admitted in
# lib/doubts.py: nothing stops a blanket clearance, and the gain is that it
# becomes a sentence somebody signed rather than an omission.
BLANKET = "*=scratch fixture; none of these values describe a real place"

# The example the docs use for the blanket-clearance hole. Kept here so the
# claim and the code cannot come apart: `check_clearance` files it and greps for
# it, and an example the code refuses is a hole nobody has actually demonstrated.
LAZY_EXAMPLE = "*=fine, I looked"


def make_yard(root):
    d = os.path.join(root, SLUG)
    os.makedirs(d, exist_ok=True)
    for name, body in FIXTURES.items():
        with open(os.path.join(d, name), "w") as f:
            json.dump(body, f)
    return d


def site_path(root):
    return os.path.join(root, SLUG, "site.json")


def read_site(root):
    with open(site_path(root)) as f:
        return json.load(f)


def write_site(root, site):
    with open(site_path(root), "w") as f:
        json.dump(site, f)


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


def reset_board(root, clearances=True):
    """Back to a yard nobody has said anything about, in either file.

    `clearances=False` keeps the all-clear, for the checks that are about the
    board alone and would otherwise be testing two things at once.
    """
    for name in ("doubts.json",) + (("all-clear.json",) if clearances else ()):
        p = os.path.join(root, SLUG, name)
        if os.path.exists(p):
            os.remove(p)
    write_site(root, json.loads(json.dumps(FIXTURES["site.json"])))


def file_card(root, blocks, question="scratch doubt"):
    rc, out, _ = doubtcmd(root, "--add", question, "--kind", "fact",
                          "--blocks", blocks, "--hours", "1.0")
    return rc == 0


def file_allclear(root, jobs="all", *specs):
    """File an all-clear. Returns (rc, output)."""
    args = ["--clear", jobs]
    for spec in (specs or (BLANKET,)):
        args += ["--because", spec]
    rc, out, _ = doubtcmd(root, *args)
    return rc, out


def clean_slate(root, jobs="all"):
    """No open doubts, and a current all-clear: the state where jobs may run."""
    reset_board(root)
    return file_allclear(root, jobs)


def clearance_state(root, job):
    rc, out, _ = doubtcmd(root, "--gate", job)
    try:
        return json.loads(out)["clearance"]["state"]
    except Exception:
        return None


# ------------------------------------------------------------------- the checks

def check_verdicts(root):
    """gate_json: the right jobs blocked, and only those."""
    print("\n verdicts")

    reset_board(root)
    blocked = [j for j in doubts.JOBS if board_clear(root, j) is False]
    ok = sorted(blocked) == sorted(doubts.JOBS)
    record("pass" if ok else "FAIL",
           "an empty board on its own clears nothing",
           "" if ok else f"only {blocked} blocked. Silence is being read as "
                         f"permission again, which is the whole thing this "
                         f"gate was inverted to stop")

    clean_slate(root)
    clear = [j for j in doubts.JOBS if board_clear(root, j) is True]
    record("pass" if len(clear) == len(doubts.JOBS) else "FAIL",
           f"a clean slate clears all {len(doubts.JOBS)} jobs",
           "" if len(clear) == len(doubts.JOBS)
           else f"cleared only {clear}")

    clean_slate(root)
    file_card(root, "sunmodel")
    blocked = [j for j in doubts.JOBS if board_clear(root, j) is False]
    ok = blocked == ["sunmodel"]
    record("pass" if ok else "FAIL", "a card naming one job blocks only that job",
           "" if ok else f"blocked {blocked}, expected ['sunmodel']")

    clean_slate(root)
    file_card(root, "*")
    blocked = [j for j in doubts.JOBS if board_clear(root, j) is False]
    ok = sorted(blocked) == sorted(doubts.JOBS)
    record("pass" if ok else "FAIL", "a wildcard card blocks every job",
           "" if ok else f"blocked {blocked}, expected all of {list(doubts.JOBS)}")


def check_lifecycle(root):
    """Settling and waiving clear the block; a waive without a reason does not."""
    print("\n lifecycle")

    clean_slate(root)
    file_card(root, "sunmodel")
    rc, out, _ = doubtcmd(root, "--settle", "d1", "--answer", "measured 72in",
                          "--by", "measured")
    ok = rc == 0 and board_clear(root, "sunmodel") is True
    record("pass" if ok else "FAIL", "settling a card clears the job",
           "" if ok else f"rc={rc}\n{out}")

    clean_slate(root)
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


# ------------------------------------------------------------- the all-clear

def check_inputs_map(root):
    """The per-job input map: differentiated, and still matching the source."""
    print("\n what each job reads")

    problems = inputs.drift()
    record("pass" if not problems else "FAIL",
           "JOB_INPUTS still matches what the modules read",
           "" if not problems else "\n".join(problems))

    site = read_site(root)
    soft = {j: {s["path"] for s in inputs.soft_inputs(site, j)}
            for j in doubts.JOBS}

    ok = SOFT_SUNMODEL_ONLY in soft["sunmodel"] and \
        not any(SOFT_SUNMODEL_ONLY in soft[j] for j in soft if j != "sunmodel")
    record("pass" if ok else "FAIL",
           f"{SOFT_SUNMODEL_ONLY} is charged to sunmodel and to nothing else",
           "" if ok else f"soft sets: { {j: sorted(s) for j, s in soft.items()} }")

    ok = all(SOFT_EVERYWHERE in soft[j]
             for j in ("sunmodel", "design", "bom", "schedule"))
    record("pass" if ok else "FAIL",
           f"{SOFT_EVERYWHERE} is charged to every job that reads a bed",
           "" if ok else f"only { [j for j in soft if SOFT_EVERYWHERE in soft[j]] }")

    measured = any("zones.West bed.y" in s for s in soft.values())
    record("FAIL" if measured else "pass",
           "a measured value is never asked about",
           "zones.West bed.y is measured and still turned up in a soft set"
           if measured else "")

    # The derivation reads through a local name bound to the record. This is the
    # difference between drift() catching a section and reporting clean on one it
    # never saw, so it is worth pinning rather than assuming.
    seen = _sections_read('rec = site or {}\nx = rec.get("obstructions")\n')
    record("pass" if seen == {"obstructions"} else "FAIL",
           "a read through a local alias of the record is still seen",
           "" if seen == {"obstructions"} else f"found {sorted(seen)}")

    # And the limit of that, tested so the docs stay true. A record arriving as
    # a parameter under a new name is invisible, which is a false negative in
    # drift() and is stated as one in lib/inputs.py and VALIDATOR.md.
    blind = _sections_read('def shade(record):\n    return record["boundary"]\n')
    record("pass" if blind == set() else "FAIL",
           "a record reached only as a parameter is not seen (the stated limit)",
           "" if blind == set() else
           f"found {sorted(blind)} — if the scan has been widened, the "
           f"limitation described in lib/inputs.py and VALIDATOR.md needs "
           f"rewriting to match")


def _sections_read(src):
    import ast
    tree = ast.parse(src)
    v = inputs._Reads(tree)
    v.visit(tree)
    return set(v.sections)


def check_clearance(root):
    """The all-clear: required, specific, and bound to what it was written over."""
    print("\n the all-clear")

    reset_board(root)
    rc, out, _ = run(JOB_ARGS["sunmodel"], root)
    ok = rc != 0 and "all-clear" in out.lower()
    record("pass" if ok else "FAIL",
           "no all-clear blocks a job with an empty board",
           "" if ok else f"rc={rc}\n{out.strip()[-400:]}")

    reset_board(root)
    rc, out = file_allclear(root, "sunmodel")
    ran = run(JOB_ARGS["sunmodel"], root)[1]
    ok = rc == 0 and clearance_state(root, "sunmodel") == "ok" and \
        "refusing to run" not in ran.lower()
    record("pass" if ok else "FAIL", "a valid all-clear lets the job through",
           "" if ok else f"file rc={rc}\n{out}\n---\n{ran.strip()[-300:]}")

    ok = clearance_state(root, "design") == "missing"
    record("pass" if ok else "FAIL",
           "an all-clear for sunmodel does not clear design",
           "" if ok else f"design clearance is {clearance_state(root, 'design')}")

    # The freshness binding. Without it the clearance is a stamp collected once
    # and the record can be rewritten underneath it at no cost.
    reset_board(root)
    file_allclear(root, "sunmodel")
    site = read_site(root)
    site["boundary"]["points"] = [[0, 0], [80, 0], [80, 30], [0, 30]]
    write_site(root, site)
    rc, out, _ = run(JOB_ARGS["sunmodel"], root)
    stale = clearance_state(root, "sunmodel") == "stale"
    says_why = SOFT_SUNMODEL_ONLY in out and "stale" in out.lower()
    record("pass" if rc != 0 and stale and says_why else "FAIL",
           "editing a value it covers makes the all-clear stale, and names it",
           "" if (rc != 0 and stale and says_why)
           else f"rc={rc} state={clearance_state(root, 'sunmodel')}\n"
                f"{out.strip()[-400:]}")

    # Improving a value is not the same as moving it. A path that leaves the
    # soft set because someone went and measured it must not block the run they
    # just made more trustworthy.
    reset_board(root)
    file_allclear(root, "sunmodel")
    site = read_site(root)
    site["provenance"][SOFT_SUNMODEL_ONLY] = {"source": "measured"}
    write_site(root, site)
    ok = clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "measuring a covered value does not invalidate the all-clear",
           "" if ok else f"went {clearance_state(root, 'sunmodel')} after an "
                         f"assumption was upgraded to a measurement")

    reset_board(root)
    rc, out = file_allclear(root, "sunmodel", f"{SOFT_EVERYWHERE}=paced it twice")
    named = SOFT_SUNMODEL_ONLY in out
    still = clearance_state(root, "sunmodel") == "missing"
    record("pass" if rc != 0 and named and still else "FAIL",
           "an all-clear that misses an assumed input is refused, and names it",
           "" if (rc != 0 and named and still)
           else f"rc={rc} state={clearance_state(root, 'sunmodel')}\n{out}")

    # The same check across a filing that covers several jobs at once, where
    # the temptation is to let a job through on another job's coverage.
    reset_board(root)
    rc, out = file_allclear(root, "all", f"{SOFT_EVERYWHERE}=paced it twice")
    ok = rc != 0 and "sunmodel" in out and clearance_state(root, "bom") == "missing"
    record("pass" if ok else "FAIL",
           "--clear all is refused whole when one job is left with a gap",
           "" if ok else f"rc={rc} bom={clearance_state(root, 'bom')}\n{out}")

    reset_board(root)
    rc, out = file_allclear(root, "sunmodel", "*=TODO why this is fine")
    ok = rc != 0 and "todo" in out.lower()
    record("pass" if ok else "FAIL",
           "a half-edited draft is refused rather than recorded",
           "" if ok else f"rc={rc}\n{out}")

    reset_board(root)
    file_card(root, "design", "is the west fence solid board?")
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--cite", "*=d1")
    ok = rc != 0 and "still open" in out.lower()
    record("pass" if ok else "FAIL",
           "citing a doubt that is still open is refused",
           "" if ok else f"rc={rc}\n{out}")

    doubtcmd(root, "--settle", "d1", "--answer", "solid board", "--by", "measured")
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--cite", "*=d1")
    ok = rc == 0 and clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "citing a settled doubt satisfies the inputs it covers",
           "" if ok else f"rc={rc}\n{out}")

    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--cite", "*=d99")
    ok = rc != 0 and "not on the board" in out.lower()
    record("pass" if ok else "FAIL",
           "citing a card that does not exist is refused",
           "" if ok else f"rc={rc}\n{out}")

    # The file is editable by hand, so the coverage check cannot only run at
    # write time or a text editor is enough to walk around it.
    reset_board(root)
    file_allclear(root, "sunmodel")
    p = os.path.join(root, SLUG, "all-clear.json")
    with open(p) as f:
        doc = json.load(f)
    doc["jobs"]["sunmodel"]["entries"] = [
        {"paths": ["nothing.matches.this"], "why": "hand-edited to leave a hole"}]
    with open(p, "w") as f:
        json.dump(doc, f)
    rc, out, _ = run(JOB_ARGS["sunmodel"], root)
    unsound = clearance_state(root, "sunmodel") == "unsound"
    record("pass" if rc != 0 and unsound else "FAIL",
           "an all-clear hand-edited to leave a hole is caught at the gate",
           "" if (rc != 0 and unsound)
           else f"rc={rc} state={clearance_state(root, 'sunmodel')}\n"
                f"{out.strip()[-300:]}")

    reset_board(root)
    rc, out, el = doubtcmd(root, "--inputs", "sunmodel")
    useful = rc == 0 and "--clear sunmodel" in out and SOFT_SUNMODEL_ONLY in out
    record("pass" if useful else "FAIL",
           "--inputs names the guessed values and prints a command that files them",
           "" if useful else f"rc={rc}\n{out.strip()[:500]}")

    # The docs illustrate the blanket-clearance hole with a specific string. An
    # earlier version used one the code rejects for being under twelve
    # characters, so the single example offered for the hole was one of the few
    # strings that did not demonstrate it. Pin both ends.
    reset_board(root)
    rc, out = file_allclear(root, "sunmodel", LAZY_EXAMPLE)
    filed = rc == 0 and clearance_state(root, "sunmodel") == "ok"
    docs = [f for f in ("AGENTS.md", "README.md", ".cursor/hooks/VALIDATOR.md",
                        "lib/doubts.py")
            if LAZY_EXAMPLE not in open(os.path.join(ROOT, f)).read()]
    record("pass" if filed and not docs else "FAIL",
           "the blanket clearance the docs describe as accepted is accepted",
           "" if (filed and not docs)
           else (f"rc={rc}: {out.strip()[:200]}" if not filed
                 else f"{LAZY_EXAMPLE!r} is not the example in {docs}, so the "
                      f"docs and this check have come apart"))

    reset_board(root)
    rc, out = file_allclear(root, "sunmodel", "*=too short")
    ok = rc != 0 and "too short" in out
    record("pass" if ok else "FAIL",
           "a reason under twelve characters is refused, and says so",
           "" if ok else f"rc={rc}\n{out}")

    # The hole, tested so that it stays the hole it is documented to be rather
    # than becoming a surprise. Only assumed and reported values are
    # fingerprinted, so a measured one can be corrected underneath a clearance
    # without invalidating it. That is defensible — nobody has to re-attest a
    # measurement — but it is not what "editing site.json makes it stale" would
    # mean, and the docs must not say that.
    reset_board(root)
    file_allclear(root, "sunmodel")
    site = read_site(root)
    site["zones"]["West bed"]["y"] = [2, 200]      # measured, per the fixture
    write_site(root, site)
    ok = clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "a measured value can change under a clearance without staling it "
           "(the documented hole)",
           "" if ok else f"went {clearance_state(root, 'sunmodel')}; if this is "
                         f"a deliberate tightening, the three docs saying it is "
                         f"a hole need changing too")

    # The half of that hole which is not defensible: a whole new obstruction
    # with no provenance entry anywhere near it is invisible to the
    # fingerprints, because there is nothing to fingerprint.
    reset_board(root)
    site = read_site(root)
    site["obstructions"] = {"fences": [{"height": 6.0, "points": [[0, 0], [40, 0]]}]}
    site["provenance"]["obstructions.fences.0.height"] = {"source": "measured"}
    write_site(root, site)
    file_allclear(root, "sunmodel")
    site["obstructions"]["walls"] = [
        {"height": 10.0, "points": [[0, 30], [40, 30]]}]
    write_site(root, site)
    rc, out, _ = run(JOB_ARGS["sunmodel"], root)
    stale = clearance_state(root, "sunmodel") == "stale"
    named = "obstructions.walls" in out
    record("pass" if rc != 0 and stale and named else "FAIL",
           "an unprovenanced obstruction appearing stales the clearance, and is named",
           "" if (rc != 0 and stale and named)
           else f"rc={rc} state={clearance_state(root, 'sunmodel')}\n"
                f"{out.strip()[-400:]}")

    # And the other direction. A fence coming down changes the light as surely
    # as one going up, and leaves nothing behind to fingerprint.
    reset_board(root)
    site = read_site(root)
    site["obstructions"] = {"fences": [{"height": 6.0}, {"height": 7.0}]}
    write_site(root, site)
    file_allclear(root, "sunmodel")
    site["obstructions"]["fences"].pop()
    write_site(root, site)
    ok = clearance_state(root, "sunmodel") == "stale"
    record("pass" if ok else "FAIL",
           "an obstruction being removed stales the clearance too",
           "" if ok else f"state={clearance_state(root, 'sunmodel')} after a "
                         f"fence was deleted from the record")


# The reasons already written down are the expensive part of an all-clear, and a
# mechanism that throws them away every time one value moves is a mechanism that
# gets --force'd instead. These are the checks on getting them back.
THREE_LINES = (f"zones.*=paced with a stride I have checked against a tape",
               f"boundary.*=county parcel polygon, good to about a foot",
               f"features.*=crown read off the shadow at noon, near enough")
KEPT = "county parcel polygon, good to about a foot"


def entries_on_record(root, job):
    p = os.path.join(root, SLUG, "all-clear.json")
    with open(p) as f:
        return ((json.load(f).get("jobs") or {}).get(job) or {}).get("entries") or []


def check_renewal(root):
    """Re-filing keeps what still stands, and only what still stands."""
    print("\n renewing an all-clear")

    reset_board(root)
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew")
    ok = rc != 0 and "no all-clear on record" in out
    record("pass" if ok else "FAIL",
           "--renew with nothing on record is refused, not filed from thin air",
           "" if ok else f"rc={rc}\n{out}")

    # One value moves. The other two reasons are still about the values they
    # were written for, and the tool has them.
    reset_board(root)
    file_allclear(root, "sunmodel", *THREE_LINES)
    site = read_site(root)
    site["zones"]["West bed"]["x"] = [2, 30]
    write_site(root, site)
    before = clearance_state(root, "sunmodel")
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew",
                          "--because", "zones.*=re-paced after the bed was cut back")
    on_record = entries_on_record(root, "sunmodel")
    kept = any(KEPT == (e.get("why") or "") for e in on_record)
    fresh = any("re-paced" in (e.get("why") or "") for e in on_record)
    ok = before == "stale" and rc == 0 and kept and fresh and \
        clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "--renew carries forward the reasons whose values did not move",
           "" if ok else f"was {before}, rc={rc}, kept={kept}, fresh={fresh}, "
                         f"now {clearance_state(root, 'sunmodel')}\n{out}")

    # The property that makes the above safe rather than a rubber stamp.
    reset_board(root)
    file_allclear(root, "sunmodel", *THREE_LINES)
    site = read_site(root)
    site["zones"]["West bed"]["x"] = [2, 30]
    write_site(root, site)
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew")
    refused = rc != 0 and SOFT_EVERYWHERE in out
    still = clearance_state(root, "sunmodel") == "stale"
    record("pass" if refused and still else "FAIL",
           "--renew will not carry a reason for a value that moved, and says which",
           "" if (refused and still)
           else f"rc={rc} state={clearance_state(root, 'sunmodel')}\n{out}")

    # Renewing re-derives the soft set rather than trusting the old one, so a
    # path that has newly become assumed cannot ride in on a filing that never
    # looked at it.
    reset_board(root)
    file_allclear(root, "sunmodel", *THREE_LINES)
    site = read_site(root)
    site["obstructions"] = {"fences": [{"height": 6.0}]}
    site["provenance"]["obstructions.fences.0.height"] = {"source": "assumed"}
    write_site(root, site)
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew")
    ok = rc != 0 and "obstructions.fences.0.height" in out
    record("pass" if ok else "FAIL",
           "--renew cannot carry a path that has newly become assumed",
           "" if ok else f"rc={rc} state={clearance_state(root, 'sunmodel')}\n"
                         f"{out}")

    # A shape change moves nothing that was fingerprinted, so every reason still
    # stands and re-affirming is the one command the refusal advertises.
    reset_board(root)
    file_allclear(root, "sunmodel", *THREE_LINES)
    site = read_site(root)
    site.setdefault("obstructions", {})["walls"] = [{"height": 10.0}]
    write_site(root, site)
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew")
    kept = sum(1 for e in entries_on_record(root, "sunmodel") if e.get("why"))
    ok = rc == 0 and kept == 3 and clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "after an addition nothing has to be retyped: bare --renew re-affirms",
           "" if ok else f"rc={rc} kept={kept} "
                         f"state={clearance_state(root, 'sunmodel')}\n{out}")

    # A reason can go false while its value sits still, which the fingerprints
    # cannot see. Answering for it again has to REPLACE the old sentence: two
    # contradictory reasons for the same values, with nothing saying which is
    # current, is worse than the stale one on its own.
    reset_board(root)
    file_allclear(root, "sunmodel", *THREE_LINES)
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew",
                          "--because", "boundary.*=the parcel polygon was "
                                       "superseded by the owner's tape")
    on_record = entries_on_record(root, "sunmodel")
    gone = not any(KEPT == (e.get("why") or "") for e in on_record)
    fresh = sum(1 for e in on_record if "superseded by the owner" in
                (e.get("why") or ""))
    ok = rc == 0 and gone and fresh == 1 and \
        clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "answering again for a value that did not move replaces the old "
           "reason rather than filing beside it",
           "" if ok else f"rc={rc} old_gone={gone} new_copies={fresh} "
                         f"state={clearance_state(root, 'sunmodel')}\n{out}")

    # The other half of that: a carried line still speaking for ground the new
    # one does not reach must survive, or replacing narrows the clearance.
    reset_board(root)
    file_allclear(root, "sunmodel", "*=one line covering the whole record")
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew",
                          "--because", "boundary.*=only the boundary, re-read")
    on_record = entries_on_record(root, "sunmodel")
    broad = any("whole record" in (e.get("why") or "") for e in on_record)
    ok = rc == 0 and broad and clearance_state(root, "sunmodel") == "ok"
    record("pass" if ok else "FAIL",
           "a carried line covering more than the new one is not dropped by it",
           "" if ok else f"rc={rc} broad_kept={broad} "
                         f"state={clearance_state(root, 'sunmodel')}\n{out}")

    # A line can rot without its value moving.
    reset_board(root)
    file_card(root, "sunmodel", "is the west fence solid board?")
    doubtcmd(root, "--settle", "d1", "--answer", "solid board", "--by", "measured")
    doubtcmd(root, "--clear", "sunmodel", "--cite", "*=d1")
    board = os.path.join(root, SLUG, "doubts.json")
    with open(board) as f:
        doc = json.load(f)
    doc["cards"][0]["status"] = "open"
    with open(board, "w") as f:
        json.dump(doc, f)
    rc, out, _ = doubtcmd(root, "--clear", "sunmodel", "--renew")
    ok = rc != 0 and "still open" in out.lower()
    record("pass" if ok else "FAIL",
           "--renew will not carry a line citing a card that has been reopened",
           "" if ok else f"rc={rc}\n{out}")

    # And the other route to the same place: the printed draft should hand back
    # what is on record, so the only TODO in a re-file is the thing that changed.
    reset_board(root)
    file_allclear(root, "sunmodel", *THREE_LINES)
    site = read_site(root)
    site["zones"]["West bed"]["x"] = [2, 30]
    write_site(root, site)
    rc, out, _ = doubtcmd(root, "--inputs", "sunmodel")
    hands_back = KEPT in out
    todo = "TODO" in out
    only_moved = out.count("TODO why") == 1
    record("pass" if rc == 0 and hands_back and todo and only_moved else "FAIL",
           "--inputs reprints the reasons on record, and only TODOs what moved",
           "" if (rc == 0 and hands_back and todo and only_moved)
           else f"rc={rc} hands_back={hands_back} todo={todo} "
                f"only_moved={only_moved}\n{out.strip()[-700:]}")


JOB_ARGS = {
    "sunmodel": ["-m", "lib.sunmodel", SLUG],
    "design": ["-m", "lib.design", SLUG],
    "drawbeds": ["-m", "lib.drawbeds", SLUG],
    "bom": ["-m", "lib.bom", SLUG],
    "schedule": ["-m", "lib.schedule", SLUG],
}


def _refusal_case(root, job, label):
    rc, out, el = run(JOB_ARGS[job], root)
    if rc is None:
        record("FAIL", f"{job} refuses {label}",
               f"no verdict within {DEADLINE:.0f}s — the gate did not fire "
               f"before the expensive work, which is the one thing it is for")
    elif rc != 0 and named_the_gate(out):
        record("pass", f"{job} refuses {label} ({el:.1f}s)",
               out.strip()[:300] if verbose else "")
    elif rc != 0:
        record("INCONCLUSIVE", f"{job} exited {rc} but not via the gate ({label})",
               "non-zero for some other reason, so this proves nothing "
               "about the gate:\n" + out.strip()[-400:])
    else:
        record("FAIL", f"{job} ran anyway {label}", out.strip()[-400:])


def check_refusals(root):
    """The real entrypoints refuse, name the gate, and do it quickly."""
    print("\n refusals at the real entrypoints")

    for job in doubts.JOBS:
        clean_slate(root)
        file_card(root, job, f"is the west fence solid board? ({job})")
        _refusal_case(root, job, "with a doubt open")

    for job in doubts.JOBS:
        reset_board(root)
        _refusal_case(root, job, "with no all-clear")


def check_force(root):
    """--force proceeds, and stamps what it came past."""
    print("\n --force")

    clean_slate(root)
    file_card(root, "design")
    rc, out, _ = run(JOB_ARGS["design"] + ["--force"], root)
    ok = rc == 0 and "provisional" in out.lower()
    record("pass" if ok else "FAIL", "design --force proceeds and says it is provisional",
           "" if ok else f"rc={rc}\n{out.strip()[-400:]}")

    # The stamp has to survive into the artifact, not just the console: a caveat
    # printed once does not travel with the file it describes.
    clean_slate(root)
    file_card(root, "bom")
    rc, out, _ = run(JOB_ARGS["bom"] + ["--force"], root)
    stamped = doubts.PROVISIONAL.lower() in out.lower()
    record("pass" if rc == 0 and stamped else "INCONCLUSIVE",
           "bom --force carries the provisional stamp",
           "" if (rc == 0 and stamped) else f"rc={rc}\n{out.strip()[-300:]}")

    # "Provisional" on its own is not something anyone can act on. Forced past a
    # missing all-clear and forced past an open card are different defects and
    # the artifact has to say which.
    reset_board(root)
    rc, out, _ = run(JOB_ARGS["bom"] + ["--force"], root)
    names_it = "all-clear" in out.lower() and "provisional" in out.lower()
    record("pass" if rc == 0 and names_it else "FAIL",
           "--force past a missing all-clear says that is what it came past",
           "" if (rc == 0 and names_it) else f"rc={rc}\n{out.strip()[-400:]}")


CHEAP = [
    ("sunmodel --quick", ["-m", "lib.sunmodel", SLUG, "--quick"]),
    ("design --init", ["-m", "lib.design", SLUG, "--init"]),
    ("bom --crossover", ["-m", "lib.bom", SLUG, "--crossover"]),
    ("doubts --open", ["-m", "lib.doubts", SLUG, "--open"]),
    ("doubts --inputs sunmodel", ["-m", "lib.doubts", SLUG, "--inputs",
                                  "sunmodel"]),
    ("doubts --clearances", ["-m", "lib.doubts", SLUG, "--clearances"]),
    ("doubts --clear --renew", ["-m", "lib.doubts", SLUG, "--clear", "sunmodel",
                                "--renew"]),
    ("inputs", ["-m", "lib.inputs", SLUG]),
    ("gaps", ["-m", "lib.gaps", SLUG]),
]


def check_cheap_paths(root):
    """The escape routes stay open, because they are how a doubt gets settled."""
    print("\n cheap paths stay open")

    for label, args in CHEAP:
        # Both ways of being blocked at once: a wildcard card and no all-clear.
        # An escape route that only survives one of them is not an escape route.
        reset_board(root)
        file_card(root, "*")
        rc, out, el = run(args, root)
        if rc is None:
            record("FAIL", f"{label} not gated", f"hung for {DEADLINE:.0f}s")
            continue
        # These may legitimately fail on thin fixtures. What must never happen is
        # failing *because of the gate*, so only the gate's wording is a failure.
        refused = named_the_gate(out) and "refusing to run" in out.lower()
        record("FAIL" if refused else "pass", f"{label} is not gated",
               out.strip()[-300:] if refused else "")


# (label, command, how to leave the yard, expected permission). `board` is what
# the yard looks like before the hook runs: "blocked" is the state after a
# wildcard card, "clear" is no cards and a filed all-clear, "silent" is the
# state that used to be read as consent — nothing on the board, nothing attested.
HOOK_CASES = [
    ("gated job, doubt open", f"python3 -m lib.sunmodel {SLUG}", "blocked", "deny"),
    ("gated job, nothing said at all", f"python3 -m lib.sunmodel {SLUG}",
     "silent", "deny"),
    ("gated job with --force", f"python3 -m lib.sunmodel {SLUG} --force",
     "blocked", "ask"),
    ("gated job, cleared", f"python3 -m lib.sunmodel {SLUG}", "clear", "allow"),
    ("--quick, doubt open", f"python3 -m lib.sunmodel {SLUG} --quick",
     "blocked", "allow"),
    ("bom --crossover", f"python3 -m lib.bom {SLUG} --crossover", "blocked",
     "allow"),
    ("the doubts tool itself", f"python3 -m lib.doubts {SLUG} --open", "blocked",
     "allow"),
    ("filing the all-clear", f"python3 -m lib.doubts {SLUG} --clear sunmodel "
                             f"--because '*=x'", "blocked", "allow"),
    ("an unrelated command", "git status", "blocked", "allow"),
    ("an unknown yard", "python3 -m lib.sunmodel no-such-yard", "blocked",
     "allow"),
]


def _stage(root, board):
    if board == "clear":
        clean_slate(root)
    elif board == "silent":
        reset_board(root)
    else:
        clean_slate(root)
        file_card(root, "*")


def hook_verdict(root, cmd):
    payload = json.dumps({"command": cmd, "cwd": "",
                          "hook_event_name": "beforeShellExecution"})
    env = dict(os.environ, GARDEN_ROOT=root)
    return subprocess.run(["bash", HOOK], input=payload, capture_output=True,
                          text=True, timeout=30, env=env, cwd=ROOT)


def check_hook(root):
    """The shell hook: one valid JSON object, exit 0, right verdict, usable redirect."""
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
        _stage(root, board)
        p = hook_verdict(root, cmd)
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

    # A denial without a redirect is the failure mode this whole layer warns
    # about, so the message is checked rather than only the verdict.
    reset_board(root)
    p = hook_verdict(root, f"python3 -m lib.sunmodel {SLUG}")
    try:
        msg = json.loads(p.stdout).get("agent_message") or ""
    except Exception:
        msg = ""
    wanted = [f"--inputs sunmodel", f"--clear sunmodel", "all-clear"]
    absent = [w for w in wanted if w not in msg]
    record("pass" if not absent else "FAIL",
           "the deny message tells the agent how to file the all-clear",
           "" if not absent else f"missing from the redirect: {absent}\n{msg[:400]}")


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

    missing = [j for j in doubts.JOBS if j not in inputs.JOB_INPUTS]
    record("pass" if not missing else "FAIL",
           "every gated job declares what it reads",
           "" if not missing else f"{missing} would be cleared by an all-clear "
                                  f"that attests to nothing at all")


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
        check_inputs_map(root)
        check_clearance(root)
        check_renewal(root)
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
