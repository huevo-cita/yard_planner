#!/usr/bin/env python3
"""changelog.json — what changed, and why the plan is the way it is.

    python3 -m lib.changelog <slug>                   the log, newest first
    python3 -m lib.changelog <slug> --subject g03     one thread
    python3 -m lib.changelog <slug> --add "..." --kind change
                                     --was "..." --now "..." --why "..."
    python3 -m lib.changelog <slug> --render          write CHANGELOG.md
    python3 -m lib.changelog <slug> --from-doubts     import the settled cards
    python3 -m lib.changelog <slug> --lint            prose that belongs in here
    python3 -m lib.changelog <slug> --check           entries missing their why

Why this file exists
--------------------
A plan document is read to find out what to do this weekend. Every sentence in it
about what the plan used to say is a sentence between the reader and that answer,
and there is no shortage of them: the plan gets revised, the revision is narrated
in place, and the narration stays. `PLAN.md` on one yard reached nine and a half
thousand words that way, with the actual instruction for a Wednesday evening
buried behind a parenthesis explaining why it was no longer Tuesday.

The argument does the same thing at greater length. A decision that took real
reasoning gets the reasoning written out beside it, and then the conclusion is
somewhere in the middle of eight hundred words defending it.

Neither is worthless — that is exactly why they survive. They are just in the
wrong file. So they go here, keyed and dated, and the plan carries the current
fact, one sentence of reason, and a reference.

Three kinds, because they are read for different reasons
-------------------------------------------------------
    change      the plan said X, and now says Y. Needs `was`, `now` and `why`
    correction  the record was wrong and is now right. Needs `why`, and the
                evidence that settled it in `source`
    rationale   no prior state: why the plan is the way it is. Needs `why`.
                This is where the argument goes

The distinction that matters is between the first two. "The walk moved from
Tuesday to Wednesday" is a change — both were defensible. "The plan said g02 was
bare in December and it is not" is a correction, and a reader who is deciding
whether to trust the document needs to be able to find those on their own.

The reference, and why the anchors are explicit
-----------------------------------------------
Entries render as `## c14 — headline {: #c14 }` — an explicit anchor, so the id
is stable rather than derived from a headline somebody may later reword.

**Write the mark in the plan bare, as `[c14]`.** A URL in the middle of a plan
sentence is precisely the noise this whole mechanism exists to remove, so
`lib.buildhtml` makes the link at publish time: bare `[cNN]` becomes a link into
`CHANGELOG.html`, and sibling `.md` links are repointed at the `.html` alongside.
Without that the reference is dead text in the artifact people actually read,
which is the mechanism failing at its last step.

Nothing is ever quietly restated. `--add` refuses an entry without its `why`,
because an undated line saying only that something changed is worse than the
sentence it replaced: it costs the same to read and answers nothing.
"""
import argparse
import datetime
import json
import os
import re
import sys
import textwrap

from . import yards

TODAY = datetime.date.today().isoformat()

KINDS = {
    "change": "the plan said X, and now says Y",
    "correction": "the record was wrong, and is now right",
    "rationale": "why the plan is the way it is",
}

# What each kind cannot be filed without. `why` is on all three because an entry
# without it records that something moved and not one useful thing about it.
REQUIRED = {
    "change": ("was", "now", "why"),
    "correction": ("why",),
    "rationale": ("why",),
}

# The documents this holds to the contract: what to do, when, and what it costs.
# Reference material is deliberately absent — `research-plants.md` is long
# because the plant list is long, and that is the right length for it.
ACTION_DOCS = ("PLAN.md", "SCHEDULE.md", "SOWING-CALENDAR.md",
               "SOURCING.md", "SITE-WALK.md", "CALENDAR.md", "ANT-PLAN.md")

# An action document past this is not read, it is skimmed, and skimming a
# schedule is how a dated task gets missed. Advisory, and counted apart from the
# prose findings, because a long document can still be a clean one.
#
# Counted over prose only: table rows, fenced blocks and link targets are
# excluded. A table is scanned rather than read straight through, so a long one
# does not cost the reader what a long argument does — and a budget that fires on
# a document full of dense, well-formed tables is the linter crying wolf, which
# is how the whole check gets ignored. Measured on the pair that motivated it:
# the same PLAN.md was 8,231 prose words of 9,522 before its rewrite and 3,829
# of 5,867 after, so the prose count separates the two cleanly and the raw count
# does not.
WORD_BUDGET = 4000

REF_RE = re.compile(r"\[c(\d+)\]")

# Prose that is describing the document's own history rather than the yard. Each
# carries what to do instead, because a linter that only says no gets switched
# off. Matched case-insensitively against the line.
RETROSPECTIVE = [
    (r"\byou were right\b", "the reader does not need to be told they won"),
    (r"\byou (asked|said|wanted|thought|chose|told me)\b",
     "the brief lives in vision.json; restating it here is argument"),
    (r"\b(previous|earlier|older|last) (version|draft|plan|pass)\b",
     "what it used to say belongs in the log"),
    (r"\bpreviously\b", "what it used to say belongs in the log"),
    (r"\boriginally\b", "what it used to say belongs in the log"),
    (r"\bused to (be|say|read)\b", "what it used to say belongs in the log"),
    (r"\bwas wrong\b", "file it as a correction and state the right thing here"),
    (r"\b(rewritten|revised|updated) (on|against|to reflect)\b",
     "a document that says it was rewritten is dating itself, not informing"),
    (r"\bmoved (off|from) (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
     "give the date it is on now; the log holds why it moved"),
    (r"\bthis (replaces|supersedes)\b", "the log holds what it replaced"),
    (r"\bsuperseded\b", "the log holds what it replaced"),
    (r"\bno longer (says|reads|applies|holds)\b",
     "say what does apply; the log holds what stopped"),
    (r"\bI (had|initially) (assumed|thought|read)\b",
     "the assistant's history is not the reader's business"),
    (r"\bI checked the reasoning\b",
     "state the conclusion; the check goes in the log"),
    (r"\bnobody had flagged\b", "just state the finding"),
    (r"\bchanged from\b", "state what it is; the log holds what it was"),
    (r"\b(two|three|four|several) things changed\b",
     "the log holds the changes, one entry each"),
    (r"\bwith one correction\b", "apply it and file the correction"),
]

SECOND_PERSON_ARGUMENT = [
    (r"\bas you (know|recall|remember)\b", "assumes a memory the reader may not have"),
    (r"\byou may recall\b", "assumes a memory the reader may not have"),
    (r"\byou are right\b", "the reader does not need to be told they won"),
]

# A heading is a signpost. One that argues is a section that argues.
ARGUMENT_HEADING = [
    (r"\?\s*$", "a heading that asks a question introduces an argument"),
    (r"\?\s+\w", "a heading that answers its own question is an argument"),
    (r"^(why|whether) (you|it|the|this|that|not)\b",
     "a 'why' section is rationale; the log is where it goes"),
    (r"\bactually cost\b", "state the cost in the table; the log holds the trade"),
    (r"\bit holds\b", "the reader cannot act on the reasoning holding"),
    (r"\bI checked\b", "state the conclusion"),
]


def blank(slug):
    return {"yard": slug, "schema_version": 1, "entries": []}


def load(slug):
    return yards.load(slug, "changelog.json") or blank(slug)


# ----------------------------------------------------------------- the entries

def _next_id(log):
    used = {e.get("id") for e in log.get("entries", [])}
    n = 1
    while f"c{n}" in used:
        n += 1
    return f"c{n}"


def entry(headline, kind="rationale", subject=None, was=None, now=None,
          why=None, source=None, affects=None, from_doubt=None, date=None):
    """One log entry, in the shape both the render and the reference read."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    given = {"was": was, "now": now, "why": why, "source": source}
    missing = [f for f in REQUIRED[kind] if not (given.get(f) or "").strip()]
    if missing:
        reason = ("A change with no before and after is a rumour"
                  if {"was", "now"} & set(missing) else
                  "An entry with no why costs the same to read as the sentence "
                  "it replaced and answers less")
        raise ValueError(
            f"a {kind} entry needs {', '.join('--' + m for m in missing)}. "
            + reason)
    if date:
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            raise ValueError(
                f"--date {date!r} is not an ISO date. Entries sort by date, so "
                "a malformed one\nputs the entry in the wrong place in its own "
                "thread. Use YYYY-MM-DD.")
    return {
        "id": None,
        "date": date or TODAY,
        "kind": kind,
        "subject": subject,
        "headline": headline,
        "was": was,
        "now": now,
        "why": why,
        "source": source,
        "affects": list(affects or []),
        "from_doubt": from_doubt,
    }


def record(slug, headline, **kw):
    """File an entry. This is the call that happens instead of narrating it."""
    log = load(slug)
    e = entry(headline, **kw)
    e["id"] = _next_id(log)
    log.setdefault("entries", []).append(e)
    yards.save(slug, "changelog.json", log)
    return e


def find(log, entry_id):
    for e in log.get("entries", []):
        if e.get("id") == entry_id:
            return e
    return None


def _seq(entry_id):
    """c14 -> 14, so ids sort as numbers. Lexically, c53 comes before c6."""
    m = re.match(r"c(\d+)$", entry_id or "")
    return int(m.group(1)) if m else 0


def entries(slug_or_log, subject=None, kind=None):
    """Newest first, which is the order a log is read in."""
    log = (slug_or_log if isinstance(slug_or_log, dict) else load(slug_or_log))
    out = list(log.get("entries", []))
    if subject:
        out = [e for e in out if (e.get("subject") or "").lower() == subject.lower()]
    if kind:
        out = [e for e in out if e.get("kind") == kind]
    return sorted(out, key=lambda e: (e.get("date") or "", _seq(e.get("id"))),
                  reverse=True)


def subjects(log):
    """Every subject with a thread, and how long the thread is."""
    counts = {}
    for e in log.get("entries", []):
        s = e.get("subject") or "the yard"
        counts[s] = counts.get(s, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def from_doubts(slug):
    """Import the settled and waived doubt cards, once each.

    A settled card is already a rationale entry carrying its own evidence — the
    measured spread, the decision, the accepted risk. Retyping it by hand is how
    the two records drift apart, and the doubt board is the one with the better
    provenance, so it wins.
    """
    board = yards.load(slug, "doubts.json")
    if board is None:
        return []
    log = load(slug)
    already = {e.get("from_doubt") for e in log.get("entries", [])}
    added = []
    for c in board.get("cards", []):
        if c.get("status") not in ("settled", "waived"):
            continue
        if c.get("id") in already:
            continue
        by = c.get("settled_by") or "settled"
        e = entry(c.get("question") or f"doubt {c.get('id')}",
                  kind="rationale",
                  subject=c.get("subject"),
                  why=c.get("answer") or "settled with nothing written down",
                  source=f"doubts.json [{c['id']}], {by}",
                  from_doubt=c.get("id"),
                  date=c.get("settled_on") or TODAY)
        e["id"] = _next_id(log)
        log.setdefault("entries", []).append(e)
        added.append(e)
    if added:
        yards.save(slug, "changelog.json", log)
    return added


# ------------------------------------------------------------------ the render

def _longdate(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "undated"
    return f"{d.day} {d.strftime('%B %Y')}"


def render(slug, log=None):
    """changelog.json -> CHANGELOG.md, with the anchors the plan links to."""
    log = log or load(slug)
    rows = entries(log)
    out = [f"# {slug} — change log", ""]
    out += textwrap.wrap(
        "Why the plan says what it says, and what it said before. The plan "
        "documents carry the current fact and one line of reason; the argument "
        "and the history are here. Newest first.", 96)
    out += ["",
            "Generated from `changelog.json`. Edits here are lost on the next "
            "`python3 -m lib.changelog " + slug + " --render`.", ""]

    if not rows:
        out += ["Nothing has been logged yet.", ""]
        return yards.write_text(slug, "CHANGELOG.md", "\n".join(out) + "\n")

    threads = subjects(log)
    if len(threads) > 1:
        out += ["## Threads", ""]
        for name, n in threads:
            ids = [e["id"] for e in rows if (e.get("subject") or "the yard") == name]
            links = ", ".join(f"[{i}](#{i})" for i in ids)
            out += [f"- **{name}** — {n} entr{'ies' if n > 1 else 'y'}: {links}"]
        out += [""]

    for e in rows:
        out += [f"## {e['id']} — {e['headline']} {{: #{e['id']} }}", ""]
        meta = [e["kind"], e.get("subject") or "the yard", _longdate(e.get("date"))]
        if e.get("affects"):
            meta.append("affects " + ", ".join(e["affects"]))
        out += ["*" + " · ".join(meta) + "*", ""]
        for label, key in (("Was", "was"), ("Now", "now"), ("Why", "why"),
                           ("Source", "source")):
            if e.get(key):
                out += [f"- **{label}** {e[key]}"]
        if e.get("from_doubt"):
            out += [f"- **Doubt** {e['from_doubt']}"]
        out += [""]

    return yards.write_text(slug, "CHANGELOG.md", "\n".join(out) + "\n")


# -------------------------------------------------------------------- the lint

def action_docs(slug):
    d = yards.yard_dir(slug)
    return [os.path.join(d, n) for n in ACTION_DOCS
            if os.path.exists(os.path.join(d, n))]


def prose_words(text):
    """Words a reader has to read in order, so tables and code do not count."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    text = re.sub(r"^\s*\|.*$", "", text, flags=re.M)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return len(text.split())


def _headings(text):
    for n, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^#{1,4}\s+(.*)$", line)
        if m:
            yield n, m.group(1).strip()


def _strip_numbering(heading):
    """'## 4. The twelve squares' -> 'The twelve squares'."""
    return re.sub(r"^\d+[.)]\s*", "", heading).strip()


def lint_text(text, path="", known_ids=None):
    """Every finding in one document, as (line, what, instead) triples."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for pattern, instead in RETROSPECTIVE + SECOND_PERSON_ARGUMENT:
            m = re.search(pattern, low)
            if m:
                found.append((n, f"\"{m.group(0)}\"", instead))
    for n, heading in _headings(text):
        bare = _strip_numbering(heading).lower()
        for pattern, instead in ARGUMENT_HEADING:
            m = re.search(pattern, bare)
            if m:
                found.append((n, f"heading: {_strip_numbering(heading)[:56]}",
                              instead))
                break
    if known_ids is not None:
        for n, line in enumerate(text.splitlines(), 1):
            for num in REF_RE.findall(line):
                if f"c{num}" not in known_ids:
                    found.append((n, f"[c{num}] is not in the log",
                                  "file it, or drop the reference"))
    return sorted(found)


def lint(slug, paths=None):
    """Findings per document, plus the word count against the budget.

    A yard with no log yet gets no reference check. Treating an absent log as an
    empty one would report every `[c14]` in the document as dangling, which is
    the wrong answer whenever the log is simply somewhere this process cannot
    see — a hook that never inherited GARDEN_ROOT, most often.
    """
    log = yards.load(slug, "changelog.json")
    known = {e.get("id") for e in log.get("entries", [])} if log else None
    targets = paths or action_docs(slug)
    out = []
    for p in targets:
        if not os.path.exists(p):
            out.append((p, [(0, "no such file", "check the path")], 0))
            continue
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        out.append((p, lint_text(text, p, known), prose_words(text)))
    return out


def report_lint(slug, paths=None):
    results = lint(slug, paths)
    if not results:
        print(f"{slug} — no action documents to check. Looked for: "
              + ", ".join(ACTION_DOCS))
        return 0

    total = sum(len(f) for _, f, _ in results)
    fat = [(p, w) for p, _, w in results if w > WORD_BUDGET]

    print(f"{slug} — action documents\n")
    for path, findings, words in results:
        name = os.path.basename(path)
        mark = "ok  " if not findings else f"{len(findings):<4d}"
        over = f"  ({words} words of prose, {words - WORD_BUDGET} over budget)" \
            if words > WORD_BUDGET else f"  ({words} words of prose)"
        print(f"  {mark}  {name}{over}")
        for line, what, instead in findings:
            print(f"          {name}:{line}  {what}")
            print(f"              {instead}")
        if findings:
            print()

    if not total and not fat:
        print("\n  Every action document states the current fact and nothing "
              "about its own past.")
        return 0

    if total:
        print(f"\n  {total} line{'s' if total != 1 else ''} describing the "
              f"document's history or arguing its case.")
        print(f"  Each one is an entry. File it, then state only what is true "
              f"now:\n")
        print(f"    python3 -m lib.changelog {slug} --add \"...\" --kind change "
              f"\\\n      --was \"...\" --now \"...\" --why \"...\" --affects PLAN.md")
    for path, words in fat:
        print(f"\n  {os.path.basename(path)} carries {words} words of prose "
              f"against a {WORD_BUDGET}-word budget.")
        print("  Tables are not counted, so this is text somebody has to read "
              "straight through,")
        print("  and a schedule that long gets skimmed rather than read.")
    return 1


# ------------------------------------------------------------------- the check

def check(log):
    """Structural problems with the log itself."""
    out = []
    for e in log.get("entries", []):
        eid = e.get("id") or "?"
        if e.get("kind") not in KINDS:
            out.append(f"[{eid}] kind {e.get('kind')!r} is not one of "
                       f"{', '.join(KINDS)}")
            continue
        for field in REQUIRED[e["kind"]]:
            if not (e.get(field) or "").strip():
                out.append(f"[{eid}] is a {e['kind']} with no {field}. "
                           + ("A change with no before and after is a rumour"
                              if field in ("was", "now") else
                              "Without the why it answers nothing the plan "
                              "did not already say"))
        if not (e.get("headline") or "").strip():
            out.append(f"[{eid}] has no headline, so it cannot be found")
        if e["kind"] == "correction" and not (e.get("source") or "").strip():
            out.append(f"[{eid}] is a correction with no source. A correction "
                       f"is only worth more than the error if it says what "
                       f"settled it")
    ids = [e.get("id") for e in log.get("entries", [])]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    for d in dupes:
        out.append(f"[{d}] appears more than once, so a reference to it is "
                   f"ambiguous")
    return out


# ------------------------------------------------------------------ the report

def report(slug, subject=None, kind=None):
    log = yards.load(slug, "changelog.json")
    if log is None:
        print(f"{slug} has no changelog.json yet — nothing has been logged.")
        print(f"  file one:  python3 -m lib.changelog {slug} --add \"...\" "
              f"--kind rationale --why \"...\"")
        return None

    rows = entries(log, subject=subject, kind=kind)
    if not rows:
        which = " ".join(filter(None, [subject and f"subject {subject}",
                                       kind and f"kind {kind}"]))
        print(f"{slug} — nothing logged{' for ' + which if which else ''}")
        return log

    print(f"{slug} — change log ({len(rows)} entr"
          f"{'ies' if len(rows) > 1 else 'y'}, newest first)\n")
    for e in rows:
        head = f"  [{e['id']}] {e['headline']}"
        print(head)
        meta = [e["kind"], e.get("subject") or "the yard", e.get("date") or "?"]
        print(f"        {' · '.join(meta)}")
        for label, key in (("was  ", "was"), ("now  ", "now"),
                           ("why  ", "why"), ("src  ", "source")):
            if not e.get(key):
                continue
            for i, ln in enumerate(textwrap.wrap(str(e[key]), 66)):
                print(f"        {label if i == 0 else '     '} {ln}")
        if e.get("affects"):
            print(f"        docs   {', '.join(e['affects'])}")
        print()

    if not subject and not kind:
        threads = subjects(log)
        if len(threads) > 1:
            print("  threads:  " + ", ".join(f"{n} ({c})" for n, c in threads))
    problems = check(log)
    if problems:
        print("\n  problems with the log itself:")
        for p in problems:
            print(f"    {p}")
    return log


# ---------------------------------------------------------------------- the CLI

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--json", action="store_true")

    ap.add_argument("--add", metavar="HEADLINE",
                    help="log an entry, in plain language")
    ap.add_argument("--kind", default="rationale", choices=sorted(KINDS),
                    help="; ".join(f"{k}: {v}" for k, v in KINDS.items()))
    ap.add_argument("--subject", help="the bed, task or plant it explains")
    ap.add_argument("--was", help="for a change: what the plan said before")
    ap.add_argument("--now", help="for a change: what it says now")
    ap.add_argument("--why", help="why. Required on every kind")
    ap.add_argument("--source", help="the evidence: a document and section")
    ap.add_argument("--affects", default="",
                    help="comma-separated documents the entry explains")
    ap.add_argument("--doubt", help="the doubt card this settles")
    # Adopting the log on a project that already has history means back-filling
    # it, and stamping every one of those entries with today's date loses the
    # ordering that makes a thread readable.
    ap.add_argument("--date", help="ISO date the change was made, if not today")

    ap.add_argument("--kind-only", dest="filter_kind", choices=sorted(KINDS),
                    help="show one kind")
    ap.add_argument("--render", action="store_true", help="write CHANGELOG.md")
    ap.add_argument("--from-doubts", action="store_true", dest="from_doubts",
                    help="import the settled and waived doubt cards")
    ap.add_argument("--lint", nargs="*", metavar="DOC", default=None,
                    help="prose in the action documents that belongs in here")
    ap.add_argument("--check", action="store_true",
                    help="structural problems with the log")
    args = ap.parse_args()

    if args.lint is not None:
        sys.exit(report_lint(args.slug, args.lint or None))

    if args.init:
        if yards.load(args.slug, "changelog.json") is not None:
            print(f"{args.slug} already has a changelog.json; not overwriting")
            return
        print(f"wrote {yards.save(args.slug, 'changelog.json', blank(args.slug))}")
        return

    if args.add:
        affects = [a.strip() for a in args.affects.split(",") if a.strip()]
        try:
            e = record(args.slug, args.add, kind=args.kind, subject=args.subject,
                       was=args.was, now=args.now, why=args.why,
                       source=args.source, affects=affects,
                       from_doubt=args.doubt, date=args.date)
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(f"logged [{e['id']}] on {args.slug}: {e['headline']}")
        print(f"  reference it from the plan as [{e['id']}]"
              f"(CHANGELOG.md#{e['id']}), and state only the current fact there")
        print(f"  then:  python3 -m lib.changelog {args.slug} --render")
        return

    if args.from_doubts:
        added = from_doubts(args.slug)
        if not added:
            print(f"{args.slug}: no settled or waived doubt cards left to "
                  f"import")
            return
        for e in added:
            print(f"logged [{e['id']}] from {e['from_doubt']}: {e['headline']}")
        print(f"  {len(added)} imported. Render with: "
              f"python3 -m lib.changelog {args.slug} --render")
        return

    if args.render:
        log = load(args.slug)
        path = render(args.slug, log)
        n = len(log.get("entries", []))
        print(f"{path}  ({n} entr{'ies' if n != 1 else 'y'})")
        return

    if args.check:
        problems = check(load(args.slug))
        if not problems:
            print(f"{args.slug}: the log is well formed")
            return
        for p in problems:
            print(f"  {p}")
        sys.exit(1)

    if args.json:
        print(json.dumps(load(args.slug), indent=2))
        return

    report(args.slug, subject=args.subject, kind=args.filter_kind)


if __name__ == "__main__":
    main()
