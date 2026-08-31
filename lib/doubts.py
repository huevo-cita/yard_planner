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
"""
import argparse
import datetime
import json
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


# -------------------------------------------------------------------- the gate

PROVISIONAL = "PROVISIONAL - run with open doubts"


def gate(slug, job, force=False):
    """Refuse to run an expensive job while a doubt that would change it is open.

    Returns True when the refusal was overridden and the caller should stamp its
    output provisional. Raises SystemExit otherwise, so the gate holds for
    programmatic callers and not only for the command line. Deliberately the same
    contract as `sunmodel.check_walked`.
    """
    cards = open_cards(slug, job=job)
    if not cards:
        return False

    n = len(cards)
    count = f"{n} open doubt{'s' if n > 1 else ''}"
    what = JOBS.get(job, job)

    if force:
        # stderr, not stdout: several of these jobs have a --json mode, and a
        # warning printed into the payload turns a machine-readable artifact into
        # a parse error. A warning nobody can pipe past is not a kindness.
        say = [f"\n!! WARNING: running {job} on {slug} with {count} outstanding.",
               f"!! This produces {what} on assumptions that are still in",
               f"!! question, and settling any one of them may change it:", ""]
        say += [f"!!   [{c['id']}] {c['question']}  ({native(c)})" for c in cards]
        say.append(f"!! Output stamped {PROVISIONAL!r}.\n")
        print("\n".join(say), file=sys.stderr)
        return True

    lines = [f"refusing to run {job} on {slug}: {count} would change the answer.",
             f"  This would produce {what}, and these are still open:",
             ""]
    for c in cards:
        lines.append(f"  [{c['id']}] {c['question']}")
        lines.append(f"        costs     {native(c)}")
        if c.get("kind") == "choice" and c.get("options"):
            for o in c["options"]:
                bits = [b for b in (o.get("pro"), o.get("con"), o.get("cost"))
                        if b]
                lines.append(f"        option    {o['name']}"
                             + (f" — {'; '.join(str(b) for b in bits)}"
                                if bits else ""))
        if c.get("how_to_settle"):
            effort = f"  ({c['effort']})" if c.get("effort") else ""
            lines.append(f"        to settle {c['how_to_settle']}{effort}")
        lines.append("")
    lines += [
        "  Settling one of these is cheap. Running this, discovering the answer",
        "  moved, and running it again is not. That is the whole reason this",
        "  gate exists.",
        "",
        f"  Probe what can be probed:  python3 -m lib.doubts {slug} --price",
        f"  Settle one:                python3 -m lib.doubts {slug} --settle "
        f"{cards[0]['id']} --answer \"...\" --by measured",
        f"  Set one aside, on record:  python3 -m lib.doubts {slug} --waive "
        f"{cards[0]['id']} --reason \"...\"",
        f"  Override anyway:           python3 -m lib.{job} {slug} --force",
    ]
    raise SystemExit("\n".join(lines))


def unfiled_warning(slug, job):
    """A yard leaning on assumptions with nothing at all on its board.

    The gate can only stop what has been written down, which leaves the original
    failure half-covered: the doubt that was voiced in prose and never filed. No
    check here can read prose, but it can read the shape that failure leaves
    behind — a record largely built on `assumed` and `reported` values, about to
    have an expensive job run on it, and not one card ever raised against it.

    That is a nudge rather than a refusal. Plenty of legitimate early runs look
    exactly like this, and blocking them would make the gate something to be
    disabled rather than used.
    """
    from . import siteschema
    board = load(slug)
    if board.get("cards"):
        return None
    site = yards.load(slug, "site.json")
    if not site:
        return None

    soft = [p for p, e in (site.get("provenance") or {}).items()
            if e.get("source") in ("assumed", "reported")]
    if not soft:
        return None
    measured = siteschema.measured_fraction(site)
    # Two assumptions on an otherwise measured record is not the pattern; a
    # record that is mostly assumption with an empty board is.
    if len(soft) < 3 or measured > 0.6:
        return None
    return {"job": job, "assumed_count": len(soft),
            "measured_fraction": round(measured, 2),
            "examples": sorted(soft)[:5]}


def gate_json(slug, job):
    """The gate's verdict as data, for the hook that denies the shell command.

    Always exits 0 and reports in the payload, because the caller is a shell
    script under `set -e` and an exit code would be read as a broken hook rather
    than as a refusal.
    """
    cards = open_cards(slug, job=job)
    return {
        "yard": slug,
        "job": job,
        "blocked": bool(cards),
        "count": len(cards),
        "unfiled": unfiled_warning(slug, job) if not cards else None,
        # Options travel with the verdict so that a blocked agent can put the
        # trade in front of a person in the same breath as the refusal, rather
        # than having to go and look the card up first.
        "cards": [{"id": c["id"], "question": c["question"], "kind": c["kind"],
                   "priced": native(c), "how_to_settle": c.get("how_to_settle"),
                   "options": c.get("options") or []}
                  for c in cards],
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

    ap.add_argument("--settle", metavar="ID")
    ap.add_argument("--answer")
    ap.add_argument("--by", default="decided", choices=sorted(SETTLED_BY))
    ap.add_argument("--waive", metavar="ID")
    ap.add_argument("--reason")
    args = ap.parse_args()

    if args.gate:
        print(json.dumps(gate_json(args.slug, args.gate), indent=2))
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
