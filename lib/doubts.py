#!/usr/bin/env python3
"""doubts.json — the doubts that would change the answer, and the gate that holds.

    python3 -m lib.doubts <slug>                     the board
    python3 -m lib.doubts <slug> --open              only what is still open
    python3 -m lib.doubts <slug> --price             probe, and settle what does
                                                     not matter
    python3 -m lib.doubts <slug> --gate <job>        JSON, for the hook
    python3 -m lib.doubts <slug> --add "..." --kind fact --blocks sunmodel
    python3 -m lib.doubts <slug> --settle d3 --answer "..." --by measured
    python3 -m lib.doubts <slug> --waive d3 --reason "..."

    python3 -m lib.doubts <slug> --inputs sunmodel   what an all-clear must answer
    python3 -m lib.doubts <slug> --clear sunmodel --because 'path.*=reason'
    python3 -m lib.doubts <slug> --clearances        what is attested, and whether
                                                     it is still current

Why this file exists
--------------------
`site.json` provenance records where a number came from. `lib.gaps` prices what
is missing or labelled `assumed`. Neither holds the third thing, which is the one
that actually costs money: a doubt formed while working. "That fence might be
open rail, not solid board." "The lidar was leaf-off, so I read that as an oak
and it could be a cedar elm." "Bed against the house, or out in the open?"

A doubt like that has nowhere to live, so saying it out loud is what discharges
it — and the expensive run starts anyway, on the assumption in question. Then the
doubt gets resolved, the answer moves, and the run is wasted. This file is the
somewhere for it to live, and `gate()` is what makes an open doubt cost something
to ignore.

Three kinds, because they are settled differently
------------------------------------------------
    fact      a number may be wrong. Settled by measuring, or by probing to
              discover the number does not matter
    choice    a decision is owed, and it is not the assistant's to make. Carries
              its options with the pros, cons and cost of each
    risk      it may simply not work. Settled by a person accepting it, in
              writing, or by changing the plan

Pricing, and why most doubts should die unread
----------------------------------------------
A board that interrupts someone over every flicker of uncertainty gets ignored
within a week. So a `fact` card can carry a `probe`, and `--price` re-runs the
shade model across the plausible range of the unknown exactly as `lib.gaps` does.
A doubt that moves the answer by less than a few minutes of light a day, and does
not straddle a light-category threshold, is settled on the spot as
`probed-immaterial` with the measured spread recorded as the evidence.

What is left is the board worth putting in front of someone.

Nothing is ever settled silently. Waiving requires a reason, and a job forced
past an open doubt stamps its own output provisional, the same way a sun model
run against an unwalked record does.

The all-clear, and why an empty board is not permission
-------------------------------------------------------
The board catches a doubt that was written down. The failure it exists for is a
doubt that was *not* — voiced in prose on the way past, and discharged by being
said. Against that failure an empty board is the exact signature of the problem,
and reading it as consent gets it backwards.

So the five expensive jobs also require an all-clear: a positive statement, in
`all-clear.json`, that every value the job leans on which was **assumed or
reported** rather than measured has been looked at, with either a doubt card id
or a written reason against each one. No all-clear is a refusal, the same as an
open card.

`lib.inputs` says which parts of site.json each job reads, so the question is
the job's own and not the whole record. The clearance is bound to a digest of
the values it covers, so editing `site.json` under it makes it stale and stale
blocks exactly like missing.

Be clear about what this does and does not buy. Nothing stops someone writing
`--because '*=looks fine'` and clearing the whole record in one line. The gain
is narrower than that and still worth having: the omission becomes an artifact.
Instead of silence, there is a file with a date on it saying which values were
waved through and on what grounds, and a reviewer can disagree with a sentence
in a way they cannot disagree with something nobody said.
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import sys

from . import yards

TODAY = datetime.date.today().isoformat()

KINDS = ["fact", "choice", "risk"]

# The jobs a doubt can block. These are the expensive ones: minutes of compute, a
# directory of drawings, a shopping list someone might act on. The cheap
# inspection paths — `--quick`, the linters, the gap report — are deliberately
# absent, because running them is how a doubt gets settled.
JOBS = {
    "sunmodel": "the full shade model and every drawing it writes",
    "design": "the design linter and its objections",
    "drawbeds": "the to-scale bed maps",
    "bom": "the bill of materials and the total",
    "schedule": "the weekend-by-weekend build plan",
}

STATUS = ["open", "settled", "waived"]

SETTLED_BY = {
    "measured": "someone went and measured it",
    "probed-immaterial": "the model was re-run across the range and barely moved",
    "decided": "a person chose",
    "accepted": "a person accepted the risk in writing",
    "waived": "set aside deliberately, with a reason",
}

# Below this, a geometry doubt is not worth anyone's attention — unless the range
# it spans crosses a light-category boundary, which is checked separately. Ten
# minutes of light a day is inside the error of the model's own inputs.
IMMATERIAL_HOURS = 0.17


def blank(slug):
    return {"yard": slug, "schema_version": 1, "cards": []}


def load(slug):
    return yards.load(slug, "doubts.json") or blank(slug)


# ------------------------------------------------------------------- the cards

def _next_id(board):
    used = {c.get("id") for c in board.get("cards", [])}
    n = 1
    while f"d{n}" in used:
        n += 1
    return f"d{n}"


def card(question, kind="fact", blocks=None, priced=None, detail=None,
         options=None, probe=None, how_to_settle=None, effort=None):
    """One doubt, in the shape the gate and the board both read."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    return {
        "id": None,
        "raised": TODAY,
        "question": question,
        "kind": kind,
        "blocks": list(blocks or []),
        "priced": priced,
        "detail": detail,
        "options": options or [],
        "probe": probe,
        "how_to_settle": how_to_settle,
        "effort": effort,
        "status": "open",
        "answer": None,
        "settled_on": None,
        "settled_by": None,
    }


def option(name, pro=None, con=None, cost=None):
    return {"name": name, "pro": pro, "con": con, "cost": cost}


def record(slug, question, **kw):
    """File a doubt. This is the call that should happen instead of saying it."""
    board = load(slug)
    c = card(question, **kw)
    c["id"] = _next_id(board)
    board.setdefault("cards", []).append(c)
    yards.save(slug, "doubts.json", board)
    return c


def find(board, card_id):
    for c in board.get("cards", []):
        if c.get("id") == card_id:
            return c
    return None


def open_cards(slug_or_board, job=None):
    """Open cards, optionally only those that block a given job.

    `blocks: ["*"]` blocks everything, which is the right default for a doubt
    about something as load-bearing as the frame or the lot lines.
    """
    board = (slug_or_board if isinstance(slug_or_board, dict)
             else load(slug_or_board))
    out = [c for c in board.get("cards", []) if c.get("status") == "open"]
    if job:
        out = [c for c in out
               if job in (c.get("blocks") or []) or "*" in (c.get("blocks") or [])]
    return sorted(out, key=score, reverse=True)


def settle(slug, card_id, answer, by="decided"):
    if by not in SETTLED_BY:
        raise ValueError(f"--by must be one of {', '.join(SETTLED_BY)}")
    board = load(slug)
    c = find(board, card_id)
    if c is None:
        raise SystemExit(f"{slug} has no doubt {card_id!r}")
    c.update({"status": "settled", "answer": answer, "settled_on": TODAY,
              "settled_by": by})
    yards.save(slug, "doubts.json", board)
    return c


def waive(slug, card_id, reason):
    """Set a doubt aside. Requires a reason, and the reason is kept."""
    if not (reason or "").strip():
        raise SystemExit("waiving a doubt requires a reason. That is the point")
    board = load(slug)
    c = find(board, card_id)
    if c is None:
        raise SystemExit(f"{slug} has no doubt {card_id!r}")
    c.update({"status": "waived", "answer": reason, "settled_on": TODAY,
              "settled_by": "waived"})
    yards.save(slug, "doubts.json", board)
    return c


# ------------------------------------------------------------------- the price

def _weights():
    """The exchange rate lives in `lib.gaps` and is imported late.

    `lib.sunmodel` imports this module for the gate, and `lib.gaps` imports
    `lib.sunmodel` for the probe, so importing gaps at the top of this file
    closes a loop. Deferring it keeps one canonical, arguable exchange rate
    rather than a second copy that drifts.
    """
    try:
        from . import gaps
        return gaps.WEIGHTS
    except Exception:
        return {"hours_per_day": 10.0, "usd": 0.04, "decisions": 2.5}


def score(c):
    """One number for ordering, on the same scale the gap report uses."""
    priced = c.get("priced") or {}
    if not priced:
        # An unpriced doubt is not therefore unimportant; it sits mid-board
        # rather than at the bottom, matching how gaps.score treats the same case.
        return 12.0
    w = _weights()
    return sum(float(v) * w.get(unit, 1.0) for unit, v in priced.items())


def native(c):
    """The price in its own units, never converted into a single fake one."""
    priced = c.get("priced") or {}
    if not priced:
        return "not priced"
    bits = []
    for unit, v in priced.items():
        if unit == "hours_per_day":
            bits.append(f"{float(v):.1f} h/day of light")
        elif unit == "usd":
            bits.append(f"about ${float(v):,.0f} at risk")
        elif unit == "decisions":
            n = int(v)
            bits.append(f"{n} decision{'s' if n != 1 else ''} blocked")
        else:
            bits.append(f"{v} {unit}")
    return ", ".join(bits)


def _straddles_light_threshold(low, high):
    """Whether a small spread still crosses a line that changes plant choice.

    A tenth of an hour is noise in the middle of a range and decisive at 5.95
    hours, where it decides whether a bed is full sun or part sun and therefore
    whether half a plant list belongs in it. A flat threshold on the spread alone
    would settle exactly the doubts that matter most.
    """
    from .design import LIGHT_NEED
    return any(low < need <= high for need, _ in LIGHT_NEED.values())


def _mutator(probe):
    """Turn a card's probe spec into the mutate function `light_spread` wants."""
    from . import gaps
    if probe.get("trees_field"):
        return gaps._set_all_trees(probe["trees_field"])
    if probe.get("path"):
        return gaps._set_path(probe["path"])
    return None


def price(slug, settle_immaterial=True):
    """Probe every `fact` card that says how, and settle the ones that do not matter.

    This is the step that keeps the board short enough to be read. It is also the
    honest answer to a doubt: rather than asserting that a fence height matters,
    set it to each plausible value in turn and measure how far the yard's light
    actually moves.
    """
    from . import gaps
    site = yards.load(slug, "site.json")
    board = load(slug)
    results = []

    for c in board.get("cards", []):
        if c.get("status") != "open" or c.get("kind") != "fact":
            continue
        probe = c.get("probe")
        if not probe or not probe.get("values"):
            continue
        if site is None:
            results.append((c, None, "no site.json to probe against"))
            continue
        mutate = _mutator(probe)
        if mutate is None:
            results.append((c, None, "probe names neither a path nor a tree field"))
            continue
        spread = gaps.light_spread(site, mutate, probe["values"],
                                   zone=probe.get("zone"))
        if spread is None:
            results.append((c, None, "the model would not run across that range"))
            continue

        c["priced"] = dict(c.get("priced") or {},
                           hours_per_day=spread["spread_hours"])
        c["probe"] = dict(probe, measured=spread)

        crosses = _straddles_light_threshold(spread["low"], spread["high"])
        immaterial = spread["spread_hours"] < IMMATERIAL_HOURS and not crosses
        if immaterial and settle_immaterial:
            c.update({
                "status": "settled",
                "settled_on": TODAY,
                "settled_by": "probed-immaterial",
                "answer": (
                    f"does not matter: across {probe['values'][0]} to "
                    f"{probe['values'][-1]} the model moves "
                    f"{spread['spread_hours']:.2f} h/day over "
                    f"{spread['measured_over']}, which is inside the error of "
                    f"its own inputs and crosses no light-category threshold"),
            })
            results.append((c, spread, "settled — immaterial"))
        elif crosses and spread["spread_hours"] < IMMATERIAL_HOURS:
            results.append((c, spread, "small, but it crosses a light threshold"))
        else:
            results.append((c, spread, "stays open"))

    yards.save(slug, "doubts.json", board)
    return results


# --------------------------------------------------------------- the all-clear

CLEARANCE_FILE = "all-clear.json"
CLEARANCE_VERSION = 1

# An all-clear filed from a half-edited draft is worse than none, because it
# looks like an answer. `draft()` writes its blanks in this vocabulary so that
# leaving one in is refused rather than recorded.
PLACEHOLDER_PREFIXES = ("todo", "tbd", "fixme", "xxx", "...", "why ")
PLACEHOLDER_EXACT = ("?", "n/a", "na", "none", "reason", "-")


def blank_clearances(slug):
    return {"yard": slug, "schema_version": CLEARANCE_VERSION, "jobs": {}}


def load_clearances(slug):
    return yards.load(slug, CLEARANCE_FILE) or blank_clearances(slug)


def soft_inputs(slug, job, site=None):
    """The assumed-or-reported values this job reads. Empty is a real answer."""
    from . import inputs
    if site is None:
        site = yards.load(slug, "site.json") or {}
    return inputs.soft_inputs(site, job)


def _covers(entry, path):
    return any(fnmatch.fnmatch(path, pat) for pat in entry.get("paths", []))


def entry(paths, doubt=None, why=None):
    """One line of an all-clear: some paths, and why running on them is all right."""
    if isinstance(paths, str):
        paths = [paths]
    return {"paths": list(paths), "doubt": doubt or None,
            "why": (why or "").strip() or None}


def _entry_problems(e, board):
    """Whether this line actually says anything. Cheap to satisfy, not free."""
    out = []
    if not e.get("paths"):
        out.append("an entry with no paths covers nothing")
    cited = e.get("doubt")
    why = (e.get("why") or "").strip()

    if not cited and not why:
        out.append(f"{'/'.join(e.get('paths') or ['?'])} has neither a doubt id "
                   f"nor a reason. One or the other is the whole mechanism")
    flat = why.lower().strip(" .!")
    if why and (flat.startswith(PLACEHOLDER_PREFIXES) or
                flat in PLACEHOLDER_EXACT):
        out.append(f"{'/'.join(e.get('paths') or ['?'])} still carries {why!r} "
                   f"from the draft. Filing a half-edited draft is worse than "
                   f"filing nothing, because it looks like an answer")
    elif why and len(why) < 12:
        out.append(f"{'/'.join(e.get('paths') or ['?'])} carries {why!r}, which "
                   f"is too short to be a reason anyone could disagree with")
    if cited:
        c = find(board, cited)
        if c is None:
            out.append(f"{'/'.join(e.get('paths') or ['?'])} cites {cited}, "
                       f"which is not on the board")
        elif c.get("status") == "open" and not why:
            # Citing a card that is still open is the original failure wearing a
            # badge: the doubt was noticed, written down, and then run past.
            out.append(f"{'/'.join(e.get('paths') or ['?'])} cites {cited}, "
                       f"which is still open. Settle or waive it, or give a "
                       f"reason for proceeding while it stands")
    return out


def _digest(covered):
    body = json.dumps(sorted(covered.items()), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def file_clearance(slug, jobs, entries, note=None):
    """Record an all-clear for one or more jobs. Refuses if it leaves a gap.

    Filing is checked here *and* re-checked in `clearance_state`, because the
    file is editable by hand and a check that only runs at write time is a check
    that can be walked around with a text editor.
    """
    board = load(slug)
    site = yards.load(slug, "site.json") or {}
    entries = [dict(e) for e in entries]

    problems = []
    for e in entries:
        problems += _entry_problems(e, board)

    written = {}
    for job in jobs:
        if job not in JOBS:
            problems.append(f"{job!r} is not a gated job; nothing would ever "
                            f"read an all-clear for it")
            continue
        soft = soft_inputs(slug, job, site=site)
        missed = [s["path"] for s in soft
                  if not any(_covers(e, s["path"]) for e in entries)]
        if missed:
            problems.append(
                f"{job}: {len(missed)} assumed or reported input"
                f"{'s' if len(missed) > 1 else ''} nothing in this all-clear "
                f"addresses — " + ", ".join(missed[:6])
                + (f", and {len(missed) - 6} more" if len(missed) > 6 else ""))
            continue
        written[job] = {
            "job": job,
            "filed": TODAY,
            "note": note,
            "entries": entries,
            "covered": {s["path"]: f"{s['source']}/{s['fingerprint']}"
                        for s in soft},
        }
        written[job]["digest"] = _digest(written[job]["covered"])

    if problems:
        raise SystemExit(
            "refusing to file this all-clear:\n  "
            + "\n  ".join(problems)
            + f"\n\n  See what has to be answered:  python3 -m lib.doubts "
              f"{slug} --inputs {list(jobs)[0]}")

    # A line that matches nothing anywhere in this filing is not an error — the
    # path may be about to exist — but it is almost always a typo in a glob, and
    # a typo here silently narrows what the clearance actually covers.
    every = {p for job in written for p in written[job]["covered"]}
    dead = [e for e in entries
            if not any(_covers(e, p) for p in every)] if every else []

    doc = load_clearances(slug)
    doc.setdefault("jobs", {}).update(written)
    yards.save(slug, CLEARANCE_FILE, doc)
    return written, dead


def clearance_state(slug, job, site=None):
    """Whether this job has a current all-clear, and if not, precisely why not.

    Returns a dict whose `state` is one of ok, missing, stale or unsound. The
    detail lines are written to be pasted in front of whoever is blocked, so
    they name the paths rather than counting them.
    """
    if site is None:
        site = yards.load(slug, "site.json") or {}
    soft = soft_inputs(slug, job, site=site)
    doc = load_clearances(slug)
    filed = (doc.get("jobs") or {}).get(job)

    base = {"job": job, "soft": len(soft),
            "filed": (filed or {}).get("filed"),
            "digest": (filed or {}).get("digest"), "detail": []}

    if not filed:
        return dict(base, state="missing", summary=(
            f"no all-clear on record for {job} — "
            + (f"{len(soft)} of the values it reads "
               f"{'were' if len(soft) > 1 else 'was'} assumed or reported "
               f"rather than measured, and nothing says why running on "
               f"{'them' if len(soft) > 1 else 'it'} is all right" if soft
               else "nothing it reads is assumed or reported, so this is a "
                    "one-line formality, but it is still required, because a "
                    "record that has never written down where a number came "
                    "from looks exactly like one that measured everything")))

    covered = filed.get("covered") or {}
    entries = filed.get("entries") or []
    board = load(slug)

    moved, appeared, unaddressed = [], [], []
    for s in soft:
        want = f"{s['source']}/{s['fingerprint']}"
        have = covered.get(s["path"])
        if have is None:
            appeared.append(s["path"])
        elif have != want:
            moved.append((s["path"], have.split("/")[0], s["source"]))
        if not any(_covers(e, s["path"]) for e in entries):
            unaddressed.append(s["path"])

    if moved or appeared:
        detail = []
        for path, was, now in moved:
            detail.append(f"{path} has changed since the all-clear was filed"
                          + (f" (provenance {was} -> {now})" if was != now
                             else " (the value itself moved)"))
        for path in appeared:
            detail.append(f"{path} is assumed or reported and was not in the "
                          f"record when the all-clear was filed")
        n = len(moved) + len(appeared)
        return dict(base, state="stale", detail=detail, summary=(
            f"the all-clear for {job}, filed {filed.get('filed')}, has gone "
            f"stale — {n} of the values it was written over "
            f"{'have' if n > 1 else 'has'} moved underneath it"))

    problems = unaddressed and [
        f"{p} is assumed or reported and no entry in the all-clear matches it"
        for p in unaddressed] or []
    for e in entries:
        problems += _entry_problems(e, board)
    if problems:
        return dict(base, state="unsound", detail=problems, summary=(
            f"the all-clear for {job} does not hold up: "
            f"{len(problems)} problem{'s' if len(problems) > 1 else ''} in what "
            f"it claims"))

    return dict(base, state="ok", summary=(
        f"all-clear filed {filed.get('filed')} covering {len(soft)} assumed or "
        f"reported input{'s' if len(soft) != 1 else ''}"))


def draft(slug, job):
    """A pre-filled command that files the all-clear, with the reasons left blank.

    The whole mechanism turns on this being close to one command. Anyone who has
    to type sixty dotted paths out of a provenance map will disable the gate
    instead, and they will be right to.
    """
    from . import inputs
    soft = soft_inputs(slug, job)
    if not soft:
        return (f"python3 -m lib.doubts {slug} --clear {job} \\\n"
                f"    --note 'nothing {job} reads is assumed or reported'")
    by_path = {s["path"]: s for s in soft}
    lines = [f"python3 -m lib.doubts {slug} --clear {job} \\"]
    grouped = inputs.group(list(by_path))
    for i, (pattern, members) in enumerate(grouped):
        sources = sorted({by_path[m]["source"] for m in members})
        tail = " \\" if i < len(grouped) - 1 else ""
        lines.append(f"    --because '{pattern}=TODO why {', '.join(sources)}"
                     f" is good enough here, or cite a settled card'{tail}")
    return "\n".join(lines)


# -------------------------------------------------------------------- the gate

PROVISIONAL = "PROVISIONAL"

# What is wrong, in the two or three words that go into a provisional stamp and
# into the hook's one-line summary. One copy, because the stamp and the block
# describing the same yard differently is how a reader stops trusting either.
CLEARANCE_FAULT = {
    "missing": "no all-clear",
    "stale": "a stale all-clear",
    "unsound": "an all-clear that does not hold up",
}


def _fault(cards, clearance):
    reasons = []
    if cards:
        reasons.append(f"{len(cards)} open doubt"
                       f"{'s' if len(cards) > 1 else ''}")
    if clearance["state"] != "ok":
        reasons.append(CLEARANCE_FAULT[clearance["state"]])
    return reasons


def gate(slug, job, force=False):
    """Refuse to run an expensive job unless the yard is clear for it.

    Two conditions, and both must hold. Nothing on the board may be open against
    this job, and there must be a current all-clear for it. The second is the
    one that inverts the default: silence used to mean permission, and silence
    is what the failure produces.

    Returns a provisional stamp naming what was overridden when `force` is set
    and the caller should mark its output. Raises SystemExit otherwise, so the
    gate holds for programmatic callers and not only for the command line.
    Deliberately the same contract as `sunmodel.check_walked`.
    """
    cards = open_cards(slug, job=job)
    clearance = clearance_state(slug, job)
    if not cards and clearance["state"] == "ok":
        return False

    what = JOBS.get(job, job)
    summary = " and ".join(_fault(cards, clearance))

    if force:
        # stderr, not stdout: several of these jobs have a --json mode, and a
        # warning printed into the payload turns a machine-readable artifact into
        # a parse error. A warning nobody can pipe past is not a kindness.
        say = [f"\n!! WARNING: running {job} on {slug} past {summary}.", ""]
        if cards:
            say += [f"!! This produces {what} on assumptions that are still in",
                    f"!! question, and settling any one of them may change it:",
                    ""]
            say += [f"!!   [{c['id']}] {c['question']}  ({native(c)})"
                    for c in cards]
            say.append("")
        if clearance["state"] != "ok":
            say.append(f"!! {clearance['summary']}.")
            say += [f"!!   - {d}" for d in clearance["detail"]]
            if clearance["soft"]:
                say += [f"!! Nobody has said why running on those "
                        f"{clearance['soft']} guessed or remembered values is",
                        f"!! all right, so this output rests on them unexamined.",
                        ""]
            else:
                say += ["!! Nothing it reads is recorded as assumed or "
                        "reported, so the all-clear would",
                        "!! have been a formality — but it was not filed, "
                        "which is not the same as", "!! looking.", ""]
        stamp = f"{PROVISIONAL} - forced past {summary}"
        say += [f"!! Output stamped {stamp!r}.\n"]
        print("\n".join(say), file=sys.stderr)
        return stamp

    raise SystemExit("\n".join(refusal(slug, job, cards, clearance)))


def refusal(slug, job, cards, clearance):
    """The refusal, as lines. Shared with the hook so there is one wording.

    A block without a redirect is useless, so most of this is the redirect.
    """
    what = JOBS.get(job, job)
    lines = []

    if cards:
        n = len(cards)
        lines += [f"refusing to run {job} on {slug}: {n} open "
                  f"doubt{'s' if n > 1 else ''} would change the answer.",
                  f"  This would produce {what}, and these are still open:",
                  ""]
        for c in cards:
            lines.append(f"  [{c['id']}] {c['question']}")
            lines.append(f"        costs     {native(c)}")
            if c.get("kind") == "choice" and c.get("options"):
                for o in c["options"]:
                    bits = [b for b in (o.get("pro"), o.get("con"),
                                        o.get("cost")) if b]
                    lines.append(f"        option    {o['name']}"
                                 + (f" — {'; '.join(str(b) for b in bits)}"
                                    if bits else ""))
            if c.get("how_to_settle"):
                effort = f"  ({c['effort']})" if c.get("effort") else ""
                lines.append(f"        to settle {c['how_to_settle']}{effort}")
            lines.append("")
        lines += [
            "  Settling one of these is cheap. Running this, discovering the",
            "  answer moved, and running it again is not. That is the whole",
            "  reason this gate exists.",
            "",
            f"  Probe what can be probed:  python3 -m lib.doubts {slug} --price",
            f"  Settle one:                python3 -m lib.doubts {slug} "
            f"--settle {cards[0]['id']} --answer \"...\" --by measured",
            f"  Set one aside, on record:  python3 -m lib.doubts {slug} "
            f"--waive {cards[0]['id']} --reason \"...\"",
            "",
        ]

    if clearance["state"] != "ok":
        if not cards:
            lines.append(f"refusing to run {job} on {slug}: "
                         f"{clearance['summary']}.")
        else:
            lines.append(f"Also: {clearance['summary']}.")
        for d in clearance["detail"]:
            lines.append(f"  - {d}")
        lines.append("")
        lines += [f"  {ln}" for ln in WHY_CLEARANCE[clearance["state"]]]
        lines += [
            "",
            "  What has to be answered, with the command pre-filled:",
            f"    python3 -m lib.doubts {slug} --inputs {job}",
            "",
            "  File it, replacing each TODO with the real reason:",
            f"    python3 -m lib.doubts {slug} --clear {job} "
            f"--because 'some.path.*=why running on this is all right'",
            "",
            "  Where a card on the board already answers a path, cite it "
            "instead — once",
            "  the card is settled or waived, because citing an open one is "
            "the failure",
            "  this gate is about, with a reference number on it:",
            f"    python3 -m lib.doubts {slug} --clear {job} "
            f"--cite 'obstructions.fences.*.height=d3'",
            "",
            "  One filing can cover several jobs: --clear sunmodel,design or "
            "--clear all.",
            "",
        ]

    lines.append(f"  Override anyway:           python3 -m lib.{job} {slug} "
                 f"--force")
    return lines


# Why each refusal is a refusal, in the words that make it worth complying with
# rather than disabling. Kept apart from `refusal` so the three cases can be
# read against each other.
WHY_CLEARANCE = {
    "missing": [
        "An empty doubt board is not permission. It is also exactly what a",
        "doubt that was thought and never written down looks like from",
        "outside, and that doubt is the whole reason this gate exists. So",
        "silence does not clear a job: for every value the job reads that was",
        "assumed or reported rather than measured, there has to be either a",
        "doubt card id or a sentence saying why proceeding on it is all right.",
    ],
    "stale": [
        "An all-clear is bound to the values it was written over, so that it",
        "is a statement about this record rather than a stamp collected once.",
        "Something it covered has changed, which means nobody has looked at",
        "the record as it stands now. Re-read the lines above, and re-file:",
        "most of the reasons will still be the right ones.",
    ],
    "unsound": [
        "There is an all-clear, but it does not answer for everything the job",
        "reads, or one of its lines does not say anything. A clearance with a",
        "hole in it is worse than none, because it reads as though someone",
        "checked.",
    ],
}


def gate_json(slug, job):
    """The gate's verdict as data, for the hook that denies the shell command.

    Always exits 0 and reports in the payload, because the caller is a shell
    script under `set -e` and an exit code would be read as a broken hook rather
    than as a refusal.

    The agent-facing wording is built here rather than in jq. The redirect is the
    part of a denial that does any good, and keeping one copy of it in Python
    means it is the same text the in-process gate raises and it can be tested
    without a shell.
    """
    cards = open_cards(slug, job=job)
    clearance = clearance_state(slug, job)
    blocked = bool(cards) or clearance["state"] != "ok"

    reasons = _fault(cards, clearance)

    agent = ""
    if blocked:
        agent = (f"Blocked: {job} on {slug} is held up by "
                 f"{' and '.join(reasons)}.\n\n"
                 + "\n".join(refusal(slug, job, cards, clearance))
                 + "\n\nDo not reach for --force to get unblocked. If you "
                   "hedged about any of these in the last few messages, that "
                   "is exactly the case this gate exists for: write the hedge "
                   "down, settle it or say in the all-clear why it does not "
                   "matter, and then run.")

    return {
        "yard": slug,
        # Whether this slug is a yard at all. The hook fails open on a yard it
        # cannot find, because it is a child of the editor and does not inherit
        # a shell's GARDEN_ROOT; blocking every command on a yard it simply
        # cannot see is how the whole layer gets uninstalled. The in-process
        # gate is deliberately stricter and refuses anyway.
        "yard_known": os.path.isdir(yards.yard_dir(slug)),
        "job": job,
        "blocked": blocked,
        "count": len(cards),
        "reasons": reasons,
        "clearance": {k: clearance[k]
                      for k in ("state", "summary", "detail", "soft", "filed")},
        # Options travel with the verdict so that a blocked agent can put the
        # trade in front of a person in the same breath as the refusal, rather
        # than having to go and look the card up first.
        "cards": [{"id": c["id"], "question": c["question"], "kind": c["kind"],
                   "priced": native(c), "how_to_settle": c.get("how_to_settle"),
                   "options": c.get("options") or []}
                  for c in cards],
        "agent_message": agent,
        "user_message": (f"{slug}: {job} blocked by {' and '.join(reasons)}."
                         if blocked else ""),
    }


# ------------------------------------------------------------------- the board

def check(board):
    """Structural problems with the board itself."""
    out = []
    for c in board.get("cards", []):
        cid = c.get("id") or "?"
        if c.get("kind") not in KINDS:
            out.append(f"[{cid}] kind {c.get('kind')!r} is not one of "
                       f"{', '.join(KINDS)}")
        unknown = [b for b in (c.get("blocks") or [])
                   if b != "*" and b not in JOBS]
        if unknown:
            out.append(f"[{cid}] blocks {', '.join(unknown)}, which no job is "
                       f"called. Nothing will ever check it")
        if c.get("status") == "open" and not c.get("blocks"):
            out.append(f"[{cid}] is open and blocks nothing, so it will never "
                       f"stop anything. Either name a job or settle it")
        if c.get("kind") == "choice" and c.get("status") == "open" and \
                len(c.get("options") or []) < 2:
            out.append(f"[{cid}] is a choice with fewer than two options "
                       f"recorded. A choice without its alternatives is a "
                       f"question, not a decision anyone can make")
        if c.get("status") in ("settled", "waived") and not c.get("answer"):
            out.append(f"[{cid}] is {c['status']} with nothing recorded as the "
                       f"reason")
    return out


def report(slug, only_open=False):
    board = yards.load(slug, "doubts.json")
    if board is None:
        print(f"{slug} has no doubts.json yet — nothing has been questioned.")
        print(f"  file one:  python3 -m lib.doubts {slug} --add \"...\" "
              f"--kind fact --blocks sunmodel")
        return None

    cards = board.get("cards", [])
    if not cards:
        print(f"{slug} — no doubts on the board")
        return board

    opens = sorted([c for c in cards if c.get("status") == "open"],
                   key=score, reverse=True)
    closed = [c for c in cards if c.get("status") != "open"]

    print(f"{slug} — doubts\n")
    blocked = sorted({b for c in opens for b in (c.get("blocks") or [])})
    if opens:
        print(f"  {len(opens)} open, worst first. "
              + (f"Blocking: {', '.join(blocked)}" if blocked else ""))
    else:
        print("  nothing open")
    print()

    for c in opens:
        print(f"  [{c['id']}] {c['question']}   ({c['kind']})")
        print(f"        costs     {native(c)}")
        if c.get("detail"):
            for i, ln in enumerate(_wrap(c["detail"], 64)):
                label = "why      " if i == 0 else "         "
                print(f"        {label} {ln}")
        for o in c.get("options") or []:
            print(f"        option    {o['name']}")
            for k in ("pro", "con", "cost"):
                if o.get(k):
                    print(f"                    {k:5s} {o[k]}")
        p = (c.get("probe") or {}).get("measured")
        if p:
            print(f"        measured  {p['low']:.1f} to {p['high']:.1f} h/day "
                  f"over {p['measured_over']}")
        if c.get("how_to_settle"):
            effort = f"  ({c['effort']})" if c.get("effort") else ""
            print(f"        to settle {c['how_to_settle']}{effort}")
        print(f"        blocks    {', '.join(c.get('blocks') or ['nothing'])}")
        print()

    if closed and not only_open:
        print(f"  {len(closed)} settled or waived:")
        for c in closed:
            by = c.get("settled_by") or "?"
            print(f"    [{c['id']}] {c['question'][:56]}"
                  f"{'...' if len(c['question']) > 56 else ''}")
            print(f"          {by} on {c.get('settled_on') or '?'}")
        print()

    problems = check(board)
    if problems:
        print("  problems with the board itself:")
        for p in problems:
            print(f"    {p}")
    return board


def show_inputs(slug, job):
    """What an all-clear for this job has to answer, and the command that files it."""
    from . import inputs
    if job not in JOBS:
        raise SystemExit(f"{job!r} is not a gated job. One of: "
                         + ", ".join(sorted(JOBS)))
    soft = soft_inputs(slug, job)
    sections = ", ".join(sorted(inputs.declared(job)))
    print(f"{slug} — what {job} reads, and what is still a guess\n")
    print(f"  reads   site.json: {sections}")
    for line in _wrap(inputs.JOB_INPUTS[job]["why"], 68):
        print(f"          {line}")
    print()

    if not soft:
        print("  Nothing it reads is assumed or reported. The all-clear is a "
              "formality here,")
        print("  but it is still required, because a record that has recorded "
              "no provenance at")
        print("  all looks exactly like one that was measured throughout.")
    else:
        print(f"  {len(soft)} value{'s' if len(soft) > 1 else ''} it reads "
              f"came from a guess or from somebody's memory:\n")
        by_path = {s["path"]: s for s in soft}
        for pattern, members in inputs.group(list(by_path)):
            srcs = sorted({by_path[m]["source"] for m in members})
            note = by_path[members[0]]["note"]
            print(f"    {pattern}")
            print(f"        {len(members)} value"
                  f"{'s' if len(members) > 1 else ''}, {', '.join(srcs)}"
                  + (f" — {note[:56]}" if note else ""))
    print()
    state = clearance_state(slug, job)
    print(f"  on record: {state['summary']}")
    for d in state["detail"]:
        print(f"    - {d}")
    if state["state"] == "ok":
        return
    print("\n  File it with this, replacing each TODO with the actual reason, "
          "or swap a\n  --because for --cite 'paths=d3' where a settled card "
          "already answers it:\n")
    print(draft(slug, job))


def show_clearances(slug):
    doc = load_clearances(slug)
    filed = doc.get("jobs") or {}
    print(f"{slug} — all-clears\n")
    for job in sorted(JOBS):
        state = clearance_state(slug, job)
        mark = {"ok": "ok  ", "missing": "none", "stale": "STALE",
                "unsound": "BAD "}[state["state"]]
        print(f"  {mark}  {job:10s} {state['summary']}")
        for d in state["detail"]:
            print(f"          - {d}")
        for e in (filed.get(job) or {}).get("entries") or []:
            answer = e.get("doubt") and f"cites {e['doubt']}" or e.get("why")
            print(f"          {', '.join(e['paths'])}")
            print(f"              {answer}")
        print()


def _wrap(text, width):
    from .vision import _wrap as w
    return w(str(text), width)


# ---------------------------------------------------------------------- the CLI

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--open", action="store_true", dest="only_open",
                    help="only what is still open")
    ap.add_argument("--check", action="store_true",
                    help="structural problems with the board")
    ap.add_argument("--json", action="store_true")

    ap.add_argument("--add", metavar="QUESTION",
                    help="file a doubt, in plain language")
    ap.add_argument("--kind", default="fact", choices=KINDS)
    ap.add_argument("--blocks", default="",
                    help="comma-separated jobs, or '*' for all: "
                         + ", ".join(JOBS))
    ap.add_argument("--detail", help="why it is in doubt")
    ap.add_argument("--how", dest="how_to_settle")
    ap.add_argument("--effort")
    ap.add_argument("--hours", type=float, metavar="H",
                    help="price it in hours a day of light")
    ap.add_argument("--usd", type=float, help="price it in dollars at risk")
    ap.add_argument("--decisions", type=int, help="price it in blocked decisions")
    ap.add_argument("--option", action="append", default=[], metavar="SPEC",
                    help="for a choice: 'name|pro|con|cost', repeatable")

    ap.add_argument("--price", action="store_true",
                    help="probe fact cards and settle the immaterial ones")
    ap.add_argument("--gate", metavar="JOB",
                    help="the gate's verdict as JSON, for the hook")

    ap.add_argument("--inputs", metavar="JOB",
                    help="the assumed and reported values JOB reads, and a "
                         "pre-filled command that clears them")
    ap.add_argument("--clear", metavar="JOBS",
                    help="file an all-clear for one or more gated jobs, "
                         "comma-separated, or 'all'")
    ap.add_argument("--because", action="append", default=[], metavar="PATHS=WHY",
                    help="why it is safe to run on these paths. Repeatable; "
                         "PATHS is a glob against the provenance path")
    ap.add_argument("--cite", action="append", default=[], metavar="PATHS=ID",
                    help="the settled doubt card that answers these paths")
    ap.add_argument("--note", help="a line about the all-clear as a whole")
    ap.add_argument("--clearances", action="store_true",
                    help="what has been attested, and whether it still holds")

    ap.add_argument("--settle", metavar="ID")
    ap.add_argument("--answer")
    ap.add_argument("--by", default="decided", choices=sorted(SETTLED_BY))
    ap.add_argument("--waive", metavar="ID")
    ap.add_argument("--reason")
    args = ap.parse_args()

    if args.gate:
        print(json.dumps(gate_json(args.slug, args.gate), indent=2))
        return

    if args.inputs:
        show_inputs(args.slug, args.inputs)
        return

    if args.clear:
        jobs = (sorted(JOBS) if args.clear.strip() == "all"
                else [j.strip() for j in args.clear.split(",") if j.strip()])
        entries = []
        for spec in args.because:
            paths, _, why = spec.partition("=")
            entries.append(entry(paths.strip(), why=why))
        for spec in args.cite:
            paths, _, cid = spec.partition("=")
            entries.append(entry(paths.strip(), doubt=cid.strip() or None))
        written, dead = file_clearance(args.slug, jobs, entries, note=args.note)
        for job in sorted(written):
            w = written[job]
            print(f"all-clear filed for {job} on {args.slug} "
                  f"({len(w['covered'])} assumed or reported input"
                  f"{'s' if len(w['covered']) != 1 else ''}, "
                  f"digest {w['digest']})")
        for e in dead:
            print(f"  note: {', '.join(e['paths'])} matches nothing on this "
                  f"record. Check the glob — a typo here quietly narrows what "
                  f"the all-clear covers")
        print(f"  it goes stale the moment site.json moves under it: "
              f"python3 -m lib.doubts {args.slug} --clearances")
        return

    if args.clearances:
        show_clearances(args.slug)
        return

    if args.init:
        if yards.load(args.slug, "doubts.json") is not None:
            print(f"{args.slug} already has a doubts.json; not overwriting")
            return
        print(f"wrote {yards.save(args.slug, 'doubts.json', blank(args.slug))}")
        return

    if args.add:
        priced = {}
        if args.hours is not None:
            priced["hours_per_day"] = args.hours
        if args.usd is not None:
            priced["usd"] = args.usd
        if args.decisions is not None:
            priced["decisions"] = args.decisions
        options = []
        for spec in args.option:
            parts = [p.strip() or None for p in spec.split("|")]
            parts += [None] * (4 - len(parts))
            options.append(option(parts[0], parts[1], parts[2], parts[3]))
        blocks = [b.strip() for b in args.blocks.split(",") if b.strip()]
        c = record(args.slug, args.add, kind=args.kind, blocks=blocks,
                   priced=priced or None, detail=args.detail, options=options,
                   how_to_settle=args.how_to_settle, effort=args.effort)
        print(f"filed [{c['id']}] on {args.slug}: {c['question']}")
        if not blocks:
            print("  it blocks nothing, so nothing will ever stop for it. "
                  "Add --blocks to make it bite")
        else:
            print(f"  blocks {', '.join(blocks)}")
        return

    if args.settle:
        c = settle(args.slug, args.settle,
                   args.answer or "settled, with nothing written down",
                   by=args.by)
        print(f"settled [{c['id']}] {c['question']}")
        print(f"  {c['settled_by']}: {c['answer']}")
        return

    if args.waive:
        c = waive(args.slug, args.waive, args.reason or "")
        print(f"waived [{c['id']}] {c['question']}")
        print(f"  on record: {c['answer']}")
        return

    if args.price:
        results = price(args.slug)
        if not results:
            print(f"{args.slug}: no open fact cards carry a probe, so there is "
                  f"nothing to measure. A doubt without a probe has to be "
                  f"settled by a person")
            return
        print(f"{args.slug} — probed {len(results)} doubt"
              f"{'s' if len(results) > 1 else ''}\n")
        for c, spread, verdict in results:
            print(f"  [{c['id']}] {c['question']}")
            if spread:
                print(f"        {spread['low']:.2f} to {spread['high']:.2f} "
                      f"h/day across the range, a {spread['spread_hours']:.2f} "
                      f"h spread over {spread['measured_over']}")
            print(f"        {verdict}")
            print()
        still = open_cards(args.slug)
        print(f"  {len(still)} still open")
        return

    if args.check:
        board = yards.load(args.slug, "doubts.json") or blank(args.slug)
        problems = check(board)
        for job in sorted(JOBS):
            state = clearance_state(args.slug, job)
            if state["state"] == "unsound":
                problems += [f"all-clear for {job}: {d}" for d in state["detail"]]
        if not problems:
            print(f"{args.slug}: the board is well formed")
            return
        for p in problems:
            print(f"  {p}")
        sys.exit(1)

    if args.json:
        print(json.dumps(yards.load(args.slug, "doubts.json")
                         or blank(args.slug), indent=2))
        return

    report(args.slug, only_open=args.only_open)


if __name__ == "__main__":
    main()
