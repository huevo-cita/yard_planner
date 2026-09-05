#!/usr/bin/env python3
"""One place that says what to do this week, built from the yard's dated actions.

    python3 -m lib.week <slug>                  this week, to the terminal
    python3 -m lib.week <slug> --week 2026-09-14
    python3 -m lib.week <slug> --calendar       -> CALENDAR.md
    python3 -m lib.week <slug> --shop 3         the next three weeks of buying
    python3 -m lib.week <slug> --check          has the plan drifted from tasks.json
    python3 -m lib.week <slug> --restamp        record that the sources have been re-read
    python3 -m lib.week <slug> --sync <exported.md>   ticks from the Google Doc

Why this module exists
----------------------
A person standing in the garden on a Saturday wants one document. The dates for
this yard were written into four: the plan owns the garden-wide work, the sowing
calendar owns the bed and says so, the sourcing report owns every price and
address and is keyed to no date at all, and the shopping lists sit in a fifth
place again. Each is coherent. Together they are three documents open at once and
a shopping list that never sits beside the shop that sells the thing.

So `tasks.json` holds the dated actions once, and this renders them.

The drift problem, and what is actually done about it
-----------------------------------------------------
The plan documents keep their own week-by-week sections, so a date can be changed
in one place and not the other. Two checks, and they catch different things.

    digest      every section tasks.json was extracted from is recorded with a
                hash of its text. Edit the section and it goes stale, naming
                which one moved. This is the check that catches a task nobody
                ever transcribed, which no amount of date-matching can
    date        every task's date has to still appear somewhere in a section it
                cites. This catches the specific case of a date that moved

The direction of the date check matters. Scanning the prose for dates and asking
which ones are missing from `tasks.json` sounds equivalent and is not: "13
December" appears in those documents dozens of times as the target date, and a
check that fires on every mention is the linter crying wolf, which is how a check
gets switched off. Asking instead whether each task's own date is still written
down somewhere gives one finding per task and no false positives.

`--calendar` refuses while either check fails, the way `doubts.gate()` does, and
`--force` stamps the output with what it came past rather than a bare
"provisional" nobody can act on.

Not a gated job: nothing here runs the sun model or costs anything, and this is
one of the cheap paths that has to stay open so a plan can be read at all.
"""
import argparse
import datetime
import hashlib
import json
import os
import re

from . import conditions, yards

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
        "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

#: An anchor that names a numbered section rather than a slug: `4`, `4.1`, `3.9a`.
SECTION_NO = re.compile(r"^\d+(?:\.\d+)*[a-z]?$")

#: A task's `source` is where it was extracted from, and everything named there
#: has to carry a digest. `reference` and `technique` are the link fields, and
#: they are not hashed.
#:
#: This used to be a whitelist of plan documents, on the reading that anything
#: else was reference material. Two files walked through the gap it left.
#: `ANT-PLAN.md` carried a dated table of seven jobs, one of them on a Saturday
#: no calendar in the yard had heard of, and was added by name. Then the whole
#: g05 gutter programme took its content from `research-guttering.md`, cited it
#: under `source`, and got no digest because the name was not on the list — and
#: when the document's section 5 turned out to rest on a driveway that is at the
#: other corner of the house, nothing anywhere noticed that seven tasks were
#: still running off it.
#:
#: So the rule is the schema's own distinction rather than a list of filenames:
#: a document a task says it came from is a source, and a source is hashed. The
#: cost is that a research file cited under `source` now has to be stamped, which
#: is the work the two failures above were the price of skipping.


# ------------------------------------------------------------------ the record

def load(slug):
    return yards.load(slug, "tasks.json")


def save(slug, data):
    data["updated"] = datetime.date.today().isoformat()
    yards.save(slug, "tasks.json", data)


def _date(v):
    return datetime.date.fromisoformat(v)


def monday_of(d):
    return d - datetime.timedelta(days=d.weekday())


# -------------------------------------------------------------- source digests

def _slug(text):
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)


def sections(path):
    """Every heading in a document, with the text it owns.

    A section runs to the next heading at the same level or higher, so `## 2`
    stops at `## 3` and carries its own `###` subsections with it. That matters:
    the weekend blocks in the plan are `###` under one `##`, and hashing the
    parent without them would miss every change that actually moves a date.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    heads = []
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m:
            heads.append((len(m.group(1)), m.group(2), i))
    out = []
    for k, (level, text, start) in enumerate(heads):
        end = len(lines)
        for level2, _, start2 in heads[k + 1:]:
            if level2 <= level:
                end = start2
                break
        out.append({"level": level, "text": text, "slug": _slug(text),
                    "body": "\n".join(lines[start:end]).rstrip()})
    return out


def resolve(root, ref):
    """A `FILE.md#anchor` reference to the one section it names.

    A section-number anchor matches a heading numbered that way — `#2` is `## 2.
    Weekend by weekend`, and `#4.1` is `### 4.1 Read this table`. The number may
    be dotted, because a long reference document numbers its subsections that
    way, and the `.` or `)` after it is optional, because most of them do not
    write one. `#4` still does not match `4.1`: the separator after the anchor
    has to be whitespace, so a parent number cannot swallow its own children.
    Anything else matches on the heading's slug containing it, which keeps the
    reference readable rather than a forty-character slug.
    Returns (section, error); exactly one of them is None.
    """
    if "#" not in ref:
        return None, f"{ref} has no #anchor"
    name, anchor = ref.split("#", 1)
    path = os.path.join(root, name)
    if not os.path.exists(path):
        return None, f"{name} does not exist"
    secs = sections(path)
    if SECTION_NO.match(anchor):
        pattern = rf"^{re.escape(anchor)}[.)]?\s"
        hits = [s for s in secs if re.match(pattern, s["text"])]
    else:
        hits = [s for s in secs if anchor in s["slug"]]
    if not hits:
        return None, f"{ref} matches no heading in {name}"
    if len(hits) > 1:
        found = ", ".join(h["text"][:34] for h in hits)
        return None, f"{ref} is ambiguous in {name} — matches {found}"
    return hits[0], None


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------- the drift

def _spellings(d):
    """The ways these documents write a date, as patterns to search for.

    The third is the dashed range, where the month is written once at the end:
    "Wed 2 - Sat 5 Sep" states the second of September and never puts the two
    tokens next to each other. Without it every range start reads as a date the
    plan no longer contains, which is a false positive on a correct document.
    """
    a = ABBR[d.month]
    return [rf"\b{d.day}\s+{a}",
            rf"\b{a}\s+{d.day}\b",
            rf"\b{d.day}\s*[-\u2013\u2014]\s*(?:\w+\s+)?\d{{1,2}}\s+{a}"]


def _task_dates(t):
    if t.get("date"):
        return [_date(t["date"])]
    return [_date(t["window"][0]), _date(t["window"][1])]


def pretty(ref):
    """`PLAN.md#2` as a person would say it."""
    name, _, anchor = ref.partition("#")
    return f"{name} §{anchor}" if anchor else name


#: What each kind of finding is called when the stamp has to name it in a phrase.
KINDS = {
    "stale": "section{s} that changed after tasks.json read {them}",
    "unstamped": "section{s} that {have} never been stamped",
    "missing": "reference{s} that point{p} at no such section",
    "uncited": "section{s} cited by a task but not under a digest",
    "date": "task date{s} the plan documents no longer state",
}


def check(slug):
    """Everything that says tasks.json and the plan documents disagree.

    Findings are dicts rather than sentences so that the same result can be a
    paragraph for a person, a one-line stamp on a forced render, and a count in
    `tools/doctor.py`, without any of the three re-deriving it.
    """
    data = load(slug)
    if not data:
        return [{"kind": "missing", "subject": slug,
                 "message": f"{slug} has no tasks.json"}]
    root = yards.yard_dir(slug)
    out, bodies = [], {}

    def add(kind, subject, message):
        out.append({"kind": kind, "subject": subject, "message": message})

    declared = data.get("sources", {})
    for ref, rec in sorted(declared.items()):
        sec, err = resolve(root, ref)
        if err:
            add("missing", ref, f"{err} — a task leans on that section")
            continue
        bodies[ref] = sec["body"]
        now, was = digest(sec["body"]), rec.get("digest")
        if not was:
            add("unstamped", ref,
                f"{pretty(ref)} has never been stamped, so nothing knows "
                f"whether tasks.json reflects it. `--restamp` once it is read")
        elif was != now:
            add("stale", ref,
                f"{pretty(ref)} has changed since tasks.json read it on "
                f"{rec.get('read') or 'an unrecorded date'}. Re-read it, fix "
                f"any task the change moves, then `--restamp`")

    # Every section a task or a purchase leans on has to be one of the sections
    # under a digest, or a change to it goes unnoticed by the layer above.
    for ref in sorted(cited_sources(data) - set(declared)):
        add("uncited", ref,
            f"{pretty(ref)} is cited as a source but carries no digest, so a "
            f"change to it would go unnoticed. Add it to `sources` and "
            f"`--restamp`, or move it to `reference` if the task did not "
            f"actually come from it")

    for t in data.get("tasks", []):
        if t.get("date_inferred"):
            continue
        refs = [r for r in t.get("source", []) if r in bodies]
        if not refs:
            continue
        text = "\n".join(bodies[r] for r in refs)
        for d in _task_dates(t):
            if not any(re.search(p, text, re.I) for p in _spellings(d)):
                add("date", t["id"],
                    f"{t['id']} \"{t['title']}\" is dated {d:%-d %B} and none "
                    f"of {', '.join(pretty(r) for r in refs)} says so any more. "
                    f"Either the date moved in the plan, or the task needs "
                    f"`date_inferred` and a note saying where its date came from")
                break
    return out


#: Worst first. A task hitting two blackouts, or one span on several days,
#: answers for the strongest thing any of those days says about it.
_VERDICT_ORDER = (conditions.BARRED, conditions.UNSCOPED, conditions.PERMITTED)


def blackout_conflicts(slug):
    """Dated work that falls inside a blackout, and what the blackout says of it.

    Kept out of `check()` deliberately. `check()` asks one question — do
    `tasks.json` and the plan documents still say the same thing — and it is
    wired to refuse a render when the answer is no. This asks a different
    question, about the world rather than about two files, and the honest
    response to it is usually a conversation rather than an edit: a freeze watch
    inside a blackout cannot simply be moved to a week when there is no freeze.
    So it reports and does not block.

    Every task that falls inside is returned, carrying a `verdict` from
    `conditions.blackout_bars`, and the reason it is all of them rather than only
    the barred ones is that the audit question is "what is in this week". Eleven
    permitted jobs inside a blackout and eleven unexamined ones look identical
    from outside, and the second is the thing worth catching. The caller decides
    what to shout about; a `permitted` verdict is a recorded decision, not a find.

    A repeating job is reported by the occurrences that land inside, not by its
    span, because a weekly bowl scrub that runs through a blackout is one
    missed refill and a planting session inside one is a lost weekend.
    """
    data = load(slug)
    cond = yards.load_conditions(slug) or {}
    spans = conditions.blackouts(cond)
    if not data or not spans:
        return []
    out = []
    for t in data.get("tasks", []):
        hits, verdicts, said = [], set(), []
        for a, z in spans:
            for d in _occurrences(t, a, z):
                hits.append(d)
                verdicts.add(conditions.blackout_bars(cond, d, t.get("kind")))
                inside = conditions.in_blackout(cond, d)
                if not inside:
                    # A day `_occurrences` called a hit and no blackout claims.
                    # Reported rather than raised or dropped: it is a bug in the
                    # occurrence arithmetic, and a bug that empties this report is
                    # worse than one that shows a line nobody can rule on
                    said.append(f"{d} is not in any blackout, so nothing here "
                                f"can rule on it")
                    continue
                scope = inside.get("scope") or {}
                phrase = (f"the {_date(inside['from']):%-d %b}-"
                          f"{_date(inside['to']):%-d %b} blackout "
                          + (f"bars {scope.get('bars', 'work it has not named')}"
                             if scope else "bars all work"))
                if phrase not in said:
                    said.append(phrase)
        if hits:
            # None is reachable only if a hit day lands outside every span, which
            # is a bug in `_occurrences` rather than a state to reason about. It
            # is carried through as the verdict rather than raised, so the check
            # reports a task it cannot rule on instead of taking the whole run down
            worst = next((v for v in _VERDICT_ORDER if v in verdicts), None)
            out.append({"id": t["id"], "title": t["title"],
                        "minutes": t.get("minutes", 0),
                        "critical": bool(t.get("critical")),
                        "repeat": bool(t.get("repeat")),
                        "kind": t.get("kind"),
                        "verdict": worst,
                        "blackout": "; ".join(said),
                        "dates": sorted(d.isoformat() for d in set(hits))})
    return out


def _report_blackout(clashes, records):
    """Read the blackout board out, loudest thing first.

    Barred and unscoped work is named task by task. Work the blackout's own
    record permits is counted and listed by id on one line, and not itemised,
    because a check that prints eleven paragraphs about eleven jobs somebody has
    already ruled on is the check that gets switched off inside a week. It is
    still printed: "eleven tasks inside a blackout" is the shape of an oversight,
    and the answer to it has to be visible from the same place the shape is.
    """
    def days(c):
        out = ", ".join(f"{_date(d):%-d %b}" for d in c["dates"][:6])
        return out + (f" and {len(c['dates']) - 6} more"
                      if len(c["dates"]) > 6 else "")

    flagged = [c for c in clashes if c["verdict"] != conditions.PERMITTED]
    allowed = [c for c in clashes if c["verdict"] == conditions.PERMITTED]

    if flagged:
        print(f"\n  and {len(flagged)} task{'s' if len(flagged) > 1 else ''} "
              f"ask{'' if len(flagged) > 1 else 's'} for work inside a blackout "
              f"that the blackout does not allow:\n")
        for c in flagged:
            why = (f"{c['blackout']}" if c["verdict"] == conditions.BARRED else
                   f"{c['blackout']}, and its scope neither bars nor permits "
                   f"{c['kind'] or 'a task with no kind'} — so nobody has ruled "
                   f"on this one")
            print(f"      {c['id']} \"{c['title']}\" — {days(c)}"
                  + ("  CANNOT SLIP" if c["critical"] else ""))
            print(f"          {c['kind'] or 'no kind'}: {why}")

    if allowed:
        print(f"\n  {len(allowed)} task{'s' if len(allowed) > 1 else ''} fall "
              f"inside a blackout and {'are' if len(allowed) > 1 else 'is'} work "
              f"its own record permits: "
              f"{', '.join(c['id'] for c in allowed)}")
        for rec in records:
            scope = rec.get("scope") or {}
            if not scope:
                continue
            settled = f" [{scope['settled']}]" if scope.get("settled") else ""
            print(f"      {rec['from']:%-d %b}-{rec['to']:%-d %b} bars "
                  f"{scope.get('bars', 'work it has not named')}{settled}. "
                  f"Permitted inside it: "
                  f"{'; '.join(scope.get('permits') or ['nothing recorded'])}")

    print("\n  These do not block a render. Moving one is a decision, "
          "not an edit.")


def _permit_headline(text):
    """A permitted activity's name, without the paragraph defending it.

    A `scope.permits` entry is written to be argued with and runs to forty
    words: "keep-alive watering, including the 60-day establishment regime the
    October plantings are on days 50-57 of, and the bird bath, mammal bowl and
    Bti that keep the water features usable". Three of those on the calendar is
    a plan document again, and there is already one of those.

    The clause before the first dash or `, including` is the name of the thing.
    The rest is the reason, and the reason stays in conditions.json, behind the
    changelog reference printed on the same line.
    """
    s = re.split(r"\s+[-\u2013\u2014]\s+|,\s+including\b|;\s+", str(text), 1)[0]
    s = s.strip().rstrip(".,")
    if len(s) <= 64:
        return s
    return s[:61].rsplit(" ", 1)[0] + "..."


def _settled_ref(slug, doubt_id):
    """The changelog entry that settled a doubt, as a bare `cNN`, or None.

    Looked up from the doubt id the scope already carries rather than written
    into the calendar, because a reference typed into a generated document is
    the one that goes stale without anything noticing. `--from-doubts` files one
    entry per settled card, so this is one-to-one in the normal case; where a
    card has several the most recent wins, and where it has none the calendar
    simply carries no reference.
    """
    if not doubt_id:
        return None
    from . import changelog
    hits = [e["id"] for e in changelog.load(slug).get("entries", [])
            if e.get("from_doubt") == doubt_id]
    return hits[-1] if hits else None


def week_blackout(data, cond, monday):
    """What a blackout says about this week, for the person reading the page.

    The December scope was legible to every tool in the repo and invisible to a
    person: this module printed the week's 2 h 35 min with no sign it was a
    no-build week, and `CALENDAR.md` said nothing either. A decision recorded
    where only code can see it is the failure AGENTS.md is about, one file
    along.

    Deliberately not `blackout_conflicts`, which answers the audit question —
    what is in this blackout, across the whole record — and is read by
    `--check`. This answers the door-handle question: is this week a no-build
    week, what does it still allow, and is anything on it that the record does
    not allow. A task the scope permits is not named, because eleven permitted
    jobs listed one by one is the paragraph nobody reads twice; the count of
    what is *not* permitted is the thing worth interrupting somebody with.
    """
    sunday = monday + datetime.timedelta(days=6)
    out = []
    for rec in conditions.blackout_records(cond or {}):
        a, z = max(rec["from"], monday), min(rec["to"], sunday)
        if a > z:
            continue
        flagged = []
        for t in (data or {}).get("tasks", []):
            verdicts = {conditions.blackout_bars(cond, d, t.get("kind"))
                        for d in _occurrences(t, a, z)}
            worst = next((v for v in _VERDICT_ORDER if v in verdicts), None)
            if worst in (conditions.BARRED, conditions.UNSCOPED):
                flagged.append({"id": t["id"], "title": t["title"],
                                "kind": t.get("kind"), "verdict": worst})
        scope = rec.get("scope") or {}
        out.append({
            "from": rec["from"], "to": rec["to"], "covers": (a, z),
            "all_week": a == monday and z == sunday,
            "scoped": bool(scope),
            "bars": scope.get("bars") if scope else "all work",
            "permits": [_permit_headline(p) for p in scope.get("permits") or []],
            "settled": scope.get("settled"),
            "flagged": flagged,
        })
    return out


def _blackout_banner(blocks, slug=None):
    """The no-build week, as the two or three lines a calendar can afford."""
    lines = []
    for b in blocks:
        a, z = b["covers"]
        when = f"{b['from']:%-d %b}-{b['to']:%-d %b}"
        part = "" if b["all_week"] else f", and it covers {a:%a %-d} to {z:%a %-d}"
        head = (f"**NO-BUILD WEEK · the {when} blackout bars "
                f"{b['bars'] or 'work it has not named'}{part}.**")
        ref = _settled_ref(slug, b["settled"]) if slug else None
        tail = []
        if b["permits"]:
            tail.append("Permitted: " + " · ".join(b["permits"]))
        elif b["scoped"]:
            tail.append("It names nothing it permits")
        else:
            tail.append("It names no exception, so it bars everything")
        if not b["flagged"]:
            tail.append("everything below is work it allows")
        said = ". ".join(s[0].upper() + s[1:] for s in tail) + "."
        if ref:
            said += f" [{ref}]"
        lines += [f"{head} {said}", ""]
        if b["flagged"]:
            named = "; ".join(
                f"{f['id']} \"{f['title']}\" ({f['kind'] or 'no kind'}, "
                f"{'barred' if f['verdict'] == conditions.BARRED else 'nobody has ruled on it'})"
                for f in b["flagged"])
            lines += [f"**Still on this week and not permitted:** {named}.", ""]
    return lines


def _occurrences(t, a, z):
    """Every day this task actually asks for work between a and z inclusive."""
    r = t.get("repeat")
    if r:
        start, end = _date(r["from"]), _date(r["to"])
        step = _step_days(r.get("every"))
        if not step:
            return [d for d in (start,) if a <= d <= z]
        out, d = [], start
        while d <= end:
            if a <= d <= z:
                out.append(d)
            d += datetime.timedelta(days=step)
        return out
    if t.get("window"):
        lo, hi = _date(t["window"][0]), _date(t["window"][1])
        # A window overlapping the span asks for work on some day inside it, and
        # which day is not knowable from the record. The first day of the overlap
        # is the honest stand-in: the window's own start can be weeks outside the
        # span, and reporting that day as one inside it is a wrong date.
        return [max(lo, a)] if lo <= z and hi >= a else []
    d = _date(t["date"])
    return [d] if a <= d <= z else []


#: `repeat.every` is written the way a person says a cadence, so the unit has to
#: be read as well as the number. "6 months" is not six days, and reading it that
#: way puts a twice-yearly gutter clean inside every week it is asked about.
_UNITS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30,
          "months": 30, "year": 365, "years": 365}


def _step_days(every):
    every = str(every or "").strip().lower()
    if every in _UNITS:
        return _UNITS[every]
    m = re.match(r"^(\d+)\s*(\w*)$", every)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return n * _UNITS.get(unit, 1)


def stamp(findings):
    """One line naming what a forced render came past, by kind and by name."""
    parts = []
    for kind, phrase in KINDS.items():
        subjects = [f["subject"] for f in findings if f["kind"] == kind]
        if not subjects:
            continue
        n = len(subjects)
        words = phrase.format(s="s" if n > 1 else "", p="" if n > 1 else "s",
                              them="them" if n > 1 else "it",
                              have="have" if n > 1 else "has")
        named = ", ".join(pretty(s) for s in subjects[:4])
        if n > 4:
            named += f" and {n - 4} more"
        parts.append(f"{n} {words} ({named})")
    return "; ".join(parts)


def cited_sources(data):
    """Every section a task or a purchase says it was extracted from."""
    cited = set()
    for t in data.get("tasks", []):
        cited.update(t.get("source", []))
    for b in data.get("shopping", []):
        cited.update(b.get("source", []))
    return cited


def restamp(slug):
    """Stamp every declared source, adopting any a task cites and none declares.

    Adopting rather than only stamping is what makes the `uncited` finding
    actionable in one command. It is safe in the direction that matters: a ref
    that appears here is one a task already claims to have come from, and the
    alternative to hashing it is the status quo, which is not hashing it.
    """
    data = load(slug)
    root = yards.yard_dir(slug)
    today = datetime.date.today().isoformat()
    declared = data.setdefault("sources", {})
    adopted = sorted(cited_sources(data) - set(declared))
    for ref in adopted:
        declared[ref] = {}
    if adopted:
        print(f"  adopted {len(adopted)} cited section"
              f"{'s' if len(adopted) > 1 else ''} that carried no digest: "
              + ", ".join(pretty(r) for r in adopted))
    changed = []
    for ref, rec in data.get("sources", {}).items():
        sec, err = resolve(root, ref)
        if err:
            print(f"  {err}")
            continue
        now = digest(sec["body"])
        if rec.get("digest") != now:
            changed.append(ref)
        rec["digest"], rec["read"] = now, today
    save(slug, data)
    if changed:
        print(f"  re-stamped {len(changed)}: {', '.join(sorted(changed))}")
    else:
        print("  nothing had moved; all stamps refreshed to today")


# --------------------------------------------------------------- the weeks

def _repeat_span(t):
    r = t.get("repeat")
    if not r:
        return None
    return _date(r["from"]), _date(r["to"])


def _cadence(t):
    r = t.get("repeat") or {}
    every = str(r.get("every", ""))
    if every == "day":
        return "every day"
    if every == "week":
        return "weekly"
    if every == "month":
        return "monthly"
    if every.endswith("days") or re.match(r"^\d+$", every):
        return f"every {every.replace('days', '').strip()} days"
    return f"every {every}" if every else ""


def placed(data, monday):
    """This week's work: the days, what starts this week, and what is mid-run.

    The three-way split is not cosmetic. A daily watering is not something a
    person ticks once a week, and rendering it as a checkbox in each of the nine
    weeks it spans produces nine identical items — which reads as nagging, and
    which the Docs checkbox pass cannot convert, because it finds text by content
    and nine identical strings are not addressable. So a standing job gets a
    checkbox in the week it begins and a line saying it is still running in the
    weeks after.
    """
    sunday = monday + datetime.timedelta(days=6)
    days, starting, running = {}, [], []
    for t in data.get("tasks", []):
        span = _repeat_span(t) or (
            (_date(t["window"][0]), _date(t["window"][1])) if t.get("window")
            else None)
        if span:
            if span[0] <= sunday and span[1] >= monday:
                (starting if monday <= span[0] <= sunday else running).append(t)
            continue
        d = _date(t["date"])
        if monday <= d <= sunday:
            days.setdefault(d, []).append(t)
    for items in days.values():
        items.sort(key=lambda x: (not x.get("critical"), -x.get("minutes", 0)))
    for items in (starting, running):
        items.sort(key=lambda x: (not x.get("critical"), x["id"]))
    return days, starting, running


def buys_for(data, monday):
    sunday = monday + datetime.timedelta(days=6)
    out = [b for b in data.get("shopping", [])
           if b.get("by") and monday <= _date(b["by"]) <= sunday]
    out.sort(key=lambda b: (b.get("optional", 0), b["by"]))
    return out


def span_of(data):
    """The first and last Monday the record has anything on."""
    ds = []
    for t in data.get("tasks", []):
        span = _repeat_span(t)
        if span:
            ds += list(span)
        elif t.get("window"):
            ds += [_date(t["window"][0]), _date(t["window"][1])]
        else:
            ds.append(_date(t["date"]))
    return monday_of(min(ds)), monday_of(max(ds))


def minutes_in(days, starting):
    """Hours a person has to find this week.

    A repeating job's minutes are per occurrence and are left out: quoting a
    weekly total for something that runs to Christmas is a number nobody can
    plan against.
    """
    total = sum(t.get("minutes", 0) for items in days.values() for t in items)
    total += sum(t.get("minutes", 0) for t in starting if not t.get("repeat"))
    return total


def hours(mins):
    if not mins:
        return "no fixed hours"
    h, m = divmod(int(mins), 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def money(b):
    lo, hi = b.get("cost_usd") or [None, None]
    if lo is None:
        return "not priced"
    if lo == 0 and hi == 0:
        return "free"
    if lo == hi:
        return f"${lo:,.2f}".rstrip("0").rstrip(".") if lo % 1 else f"${lo:,.0f}"
    return f"${lo:,.0f}-{hi:,.0f}"


def where_of(t):
    w = t.get("where") or {}
    bits = []
    if w.get("bed"):
        bits.append(w["bed"])
    if w.get("squares"):
        sq = w["squares"]
        bits.append("Rows " + ", ".join(sq) if len(sq) <= 4
                    else f"{len(sq)} squares, Rows {sq[0]} to {sq[-1]}")
    if w.get("at"):
        bits.append(w["at"])
    if w.get("place"):
        bits.append(w["place"])
    return " · ".join(bits)


# --------------------------------------------------------------- the rendering

def _checkbox(t, done=None):
    tick = "x" if (t.get("done") if done is None else done) else " "
    bits = [f"**{t['title']}**"]
    if t.get("minutes"):
        bits.append(hours(t["minutes"]))
    if t.get("repeat"):
        bits.append(_cadence(t))
    w = where_of(t)
    if w:
        bits.append(w)
    return f"- [{tick}] " + " · ".join(bits)


def _cell(text):
    """Markdown table cells cannot hold a pipe or a line break."""
    return re.sub(r"\s+", " ", str(text)).replace("|", "/").strip()


def _detail(t):
    """A task's detail, as a table.

    A table rather than paragraphs for two reasons that point the same way. This
    is looked up for the one task in hand rather than read straight through, so
    the labelled rows are easier to scan than prose. And the action-document word
    budget counts prose only, precisely because a table does not cost the reader
    what an argument does — seventy tasks of depth, spacing and fallbacks in
    paragraph form would put this document three times over it and get the whole
    check switched off.
    """
    w = t.get("where") or {}
    rows = []

    if w.get("placements"):
        for p in w["placements"]:
            spot = p.get("at") or ("Rows " + ", ".join(p.get("squares", [])))
            if p.get("bed") and p.get("at"):
                spot = f"{p['bed']} {p['at']}"
            elif p.get("bed"):
                spot = f"{p['bed']} {spot}"
            rows.append((_cell(spot), _cell(p["plant"])))
    elif where_of(t):
        rows.append(("Where", _cell(where_of(t))))
    if w.get("note"):
        rows.append(("Note", _cell(w["note"])))

    if t.get("how"):
        rows.append(("How", " · ".join(_cell(h) for h in t["how"])))
    g = t.get("gate") or {}
    if g.get("below_f"):
        rows.append(("Gate", f"Soil under {g['below_f']} °F"))
    elif g.get("depends"):
        rows.append(("Gate", _cell(f"depends on {g['depends']}"
                                   + (f" — {g['unless']}" if g.get("unless") else ""))))
    if g.get("early"):
        rows.append(("Earlier", _cell(g["early"])))
    for key, label in ((g.get("miss"), "If the window closes"),
                       (t.get("miss"), "If it slips")):
        if key:
            rows.append((label, _cell(key)))
    for key, label in (("why", "Why"), ("warn", "Watch out"), ("then", "Then")):
        if t.get(key):
            rows.append((label, _cell(t[key])))

    # The section number goes in the link text rather than the target. Publishing
    # rewrites a .md target to .html, but the anchor a heading actually gets is
    # its slug, so "#8" would land nowhere. Naming the section in the text is a
    # reference that survives both formats.
    links = []
    for ref, label in ((t.get("technique"), "technique"),
                       (t.get("reference"), "detail")):
        if ref:
            name, _, anchor = str(ref).partition("#")
            name = name.split()[0]
            where = f" §{anchor}" if anchor else (
                " " + " ".join(str(ref).split()[1:]) if len(str(ref).split()) > 1 else "")
            links.append(f"[{label} in {name}{where}]({name})")
    if w.get("map"):
        links.append(f"[bed map]({w['map']})")
    if t.get("changelog"):
        links.append(" ".join(f"[{c}]" for c in t["changelog"]))
    if links:
        rows.append(("More", " · ".join(links)))

    if not rows:
        return []
    out = [f"| **{_cell(t['title'])}** | |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    out.append("")
    return out


def _buy_table(data, buys):
    sup = data.get("suppliers", {})
    out = ["| Buy | By | Cost | Where | Ask for |", "|---|---|---|---|---|"]
    for b in buys:
        s = sup.get(b.get("supplier")) or {}
        place = "anywhere"
        if s:
            place = f"**{s['name']}**, {s['address']}"
            if s.get("phone"):
                place += f", {s['phone']}"
            if s.get("hours"):
                place += f" ({s['hours']})"
        by = f"{_date(b['by']):%a %-d %b}"
        ask = b.get("ask", "")
        if b.get("note"):
            ask += f" {b['note']}"
        out.append(f"| {b['item']} | {by} | {money(b)} | {place} | {ask.strip()} |")
    out.append("")
    return out


def render_week(data, monday, heading=None, cond=None, slug=None):
    days, starting, running = placed(data, monday)
    buys = buys_for(data, monday)
    if not days and not starting and not running and not buys:
        return []
    sunday = monday + datetime.timedelta(days=6)
    total = minutes_in(days, starting)

    out = [heading or f"## Week of {monday:%a %-d %B}", ""]
    banner = [f"{hours(total)} of dated work" if total
              else "Nothing on the clock this week"]
    urgent = [b for b in buys if not b.get("optional")]
    if urgent:
        first = min(urgent, key=lambda b: b["by"])
        banner.append(f"{len(urgent)} thing{'s' if len(urgent) > 1 else ''} to "
                      f"buy, the first by {_date(first['by']):%A}")
    crit = [t["title"] for items in days.values() for t in items
            if t.get("critical")]
    if crit:
        shown = "; ".join(crit[:3])
        if len(crit) > 3:
            shown += f"; and {len(crit) - 3} more"
        banner.append(f"Cannot slip: {shown}")
    out.append("**" + ". ".join(b[0].upper() + b[1:] for b in banner) + ".**")
    out.append("")

    # Before the buying and before the days, because it changes what the rest of
    # the week means. An hours figure over a no-build week reads as an ordinary
    # light week, and the person acting on it is on the way out of the door.
    out += _blackout_banner(week_blackout(data, cond, monday), slug)

    if buys:
        out += _buy_table(data, buys)

    for d in sorted(days):
        items = days[d]
        mins = sum(t.get("minutes", 0) for t in items)
        tag = "WEEKEND" if d.weekday() >= 5 else "WEEKDAY"
        out.append(f"### {d:%a %-d %B} · {tag}"
                   + (f" · {hours(mins)}" if mins else ""))
        out.append("")
        for t in items:
            out.append(_checkbox(t))
        out.append("")
        for t in items:
            out += _detail(t)

    if starting:
        out.append("### Starts this week, and runs on")
        out.append("")
        for t in starting:
            out.append(_checkbox(t))
        out.append("")
        for t in starting:
            out += _detail(t)

    if running:
        out.append("### Already running")
        out.append("")
        out.append("| Standing job | Until | Detail |")
        out.append("|---|---|---|")
        for t in running:
            span = _repeat_span(t) or (_date(t["window"][0]),
                                       _date(t["window"][1]))
            cadence = _cadence(t) or "when the moment comes"
            out.append(f"| {_cell(t['title'])} | {span[1]:%-d %b} | "
                       f"{cadence}, {hours(t.get('minutes', 0))} a time |")
        out.append("")
    return out


def yard_name(slug):
    """What to call the yard at the top of the page.

    The street address if the record has one, the slug if it does not, because a
    calendar headed with a slug is still usable and one that dies here is not.
    """
    try:
        site = yards.load_site(slug) or {}
    except (FileNotFoundError, ValueError):
        return slug
    street = (site.get("address", {}) or {}).get("street") or ""
    return street.split(",")[0].strip() or slug


HEADER = """# {name} — what to do, week by week

Everything with a date on it, in one place. The current week is first; the rest
follow in order. Generated from `tasks.json` by `yard week`, so a date is
corrected there and re-rendered rather than edited here.

Where the rest of it lives: [PLAN.md](PLAN.md) holds the beds, the standing
water and pruning calendars, the pest tables and the budget.
[SOWING-CALENDAR.md](SOWING-CALENDAR.md) holds the soil-temperature gates, the
days-to-maturity arithmetic, the technique notes and what the bed looks like on
the day. [SOURCING.md](SOURCING.md) holds every price with its confidence label.
[CHANGELOG.md](CHANGELOG.md) holds why any of it reads as it does, behind the
`[cNN]` marks.
"""


def calendar(slug, today=None, force=False):
    data = load(slug)
    if not data:
        raise SystemExit(f"  {slug} has no tasks.json")
    problems = check(slug)
    if problems and not force:
        raise SystemExit(
            "  CALENDAR.md not written. tasks.json and the plan documents "
            "disagree, and a\n  calendar built over that sends someone into "
            "the garden on the wrong day:\n\n"
            + "\n".join(f"      {p['message']}" for p in problems)
            + f"\n\n  Settle it, or `--force`, which renders and stamps the "
              f"page with what it\n  came past.\n"
              f"      python3 -m lib.week {slug} --check")

    today = today or datetime.date.today()
    this = monday_of(today)
    first, last = span_of(data)
    cond = yards.load_conditions(slug) or {}

    out = [HEADER.format(name=yard_name(slug))]
    if problems:
        out.append(f"**PROVISIONAL — rendered past {stamp(problems)}.** Every "
                   f"date below may be wrong in exactly that way. "
                   f"`yard week {slug} --check` says what to do about it.\n")

    weeks, mon = [], first
    while mon <= last:
        weeks.append(mon)
        mon += datetime.timedelta(weeks=1)

    upcoming = [m for m in weeks if m >= this]
    past = [m for m in weeks if m < this]

    body = []
    for i, mon in enumerate(upcoming):
        sun = mon + datetime.timedelta(days=6)
        head = (f"## This week — {mon:%a %-d %b} to {sun:%a %-d %b}" if i == 0
                else f"## Week of {mon:%a %-d %B}")
        body += render_week(data, mon, head, cond=cond, slug=slug)

    if past:
        done = []
        for mon in past:
            done += render_week(data, mon, cond=cond, slug=slug)
        if done:
            body.append("## Weeks already gone")
            body.append("")
            body.append("Kept so the record of what was actually done travels "
                        "with the plan.")
            body.append("")
            body += done

    out.append("\n".join(body).rstrip() + "\n")
    text = "\n".join(out)
    path = yards.write_text(slug, "CALENDAR.md", text)
    return path, len([w for w in weeks]), text


# ------------------------------------------------------------------- shopping

def shop(slug, weeks_ahead=3, today=None):
    data = load(slug)
    today = today or datetime.date.today()
    end = today + datetime.timedelta(weeks=weeks_ahead)
    items = [b for b in data.get("shopping", [])
             if b.get("by") and _date(b["by"]) <= end]
    items.sort(key=lambda b: (b.get("optional", 0), b["by"]))
    trips = {}
    for b in items:
        trips.setdefault(b.get("supplier") or "_", []).append(b)
    return data, trips, end


# ------------------------------------------------------------- the publishing

PUBLISH_DIR = ".publish"


def publish(slug):
    """The artifacts for the Google Doc, and the calls that put them there.

    Two files, because the Doc needs the checkbox text and the checkbox pass
    needs to find that same text:

        CALENDAR.md        checkbox syntax kept, for publish_checklist.py to
                           parse into the ordered run strings
        CALENDAR-docs.md   the same text with the `[ ]` markers taken out, for
                           lib.builddoc, because a Docs checkbox and a literal
                           "[ ]" beside it is two checkboxes to the reader

    Both are derived from one transformed copy so the run strings and the
    document body cannot disagree — a mismatch there means `createParagraphBullets`
    reports "not found" on a document that is otherwise perfect.

    Why .docx rather than the inline HTML publish_checklist.py describes: this
    document is 90 KB of HTML, which has to travel as one argument, and
    `uploadFile(localPath=..., fileId=...)` updates the existing Doc in place and
    keeps the link bookmarkable. The HTML is written anyway as the fallback.

    A ticked task cannot be published back as a ticked box — `BULLET_CHECKBOX`
    creates unchecked ones and there is no argument for the state — so a done
    task is marked in the text instead. tasks.json stays the record of what was
    actually done.
    """
    root = yards.yard_dir(slug)
    out = os.path.join(root, PUBLISH_DIR)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(root, "CALENDAR.md"), encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"^- \[x\] ", "- [ ] DONE · ", text, flags=re.M)
    boxed = os.path.join(out, "CALENDAR.md")
    with open(boxed, "w", encoding="utf-8") as fh:
        fh.write(text)
    flat = os.path.join(out, "CALENDAR-docs.md")
    with open(flat, "w", encoding="utf-8") as fh:
        fh.write(re.sub(r"^- \[[ x]\] ", "- ", text, flags=re.M))
    return boxed, flat, out


# ----------------------------------------------------------------- the ticks

TICKED = re.compile(r"^[>\s]*[-*]\s*\[[xX]\]\s*(.+?)\s*$")
UNTICKED = re.compile(r"^[>\s]*[-*]\s*\[\s\]\s*(.+?)\s*$")


def _title_of(line):
    """The bold title out of a rendered checkbox line, however Docs mangled it.

    The markdown export backslash-escapes punctuation, so a title with " - " in
    it comes back as " \\- " and matches nothing. Unescaping first is what makes
    the round trip work on the eight tasks that have a dash in the name.
    """
    line = re.sub(r"\\([-_*\[\]()#.!`~])", r"\1", line.strip())
    m = re.match(r"\*{0,2}(.+?)\*{0,2}\s*(?:·|$)", line)
    return re.sub(r"\s+", " ", (m.group(1) if m else line)).strip().strip("*")


def sync(slug, exported):
    """Fold the ticks in a Docs export back into tasks.json.

    The export writes every list item inside a blockquote, so the obvious
    `^- \\[x\\]` anchor matches nothing on a document that is perfectly correct.
    Both patterns above allow the `> ` prefix for that reason.
    """
    data = load(slug)
    with open(exported, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    state = {}
    for line in lines:
        for rx, value in ((TICKED, True), (UNTICKED, False)):
            m = rx.match(line)
            if m:
                state[_title_of(m.group(1))] = value
                break
    changed, unmatched = [], []
    seen = set()
    for t in data.get("tasks", []):
        key = _title_of(f"**{t['title']}**")
        if key not in state:
            continue
        seen.add(key)
        if bool(t.get("done")) != state[key]:
            t["done"] = state[key]
            changed.append((t["id"], t["title"], state[key]))
    unmatched = sorted(set(state) - seen)
    save(slug, data)
    return changed, unmatched, len(state)


# ------------------------------------------------------------------ reporting

def report(slug, when=None):
    data = load(slug)
    if not data:
        print(f"  {slug} has no tasks.json")
        return
    today = when or datetime.date.today()
    mon = monday_of(today)
    sun = mon + datetime.timedelta(days=6)
    days, starting, running = placed(data, mon)
    buys = buys_for(data, mon)
    total = minutes_in(days, starting)

    print(f"{slug} — {mon:%a %-d %b} to {sun:%a %-d %b}   {hours(total)}\n")
    # Above the work, for the same reason the calendar carries it above the
    # days: an hours figure over a no-build week reads as an ordinary quiet one.
    for b in week_blackout(data, yards.load_conditions(slug) or {}, mon):
        a, z = b["covers"]
        print(f"  NO-BUILD WEEK   the {b['from']:%-d %b}-{b['to']:%-d %b} "
              f"blackout bars {b['bars'] or 'work it has not named'}"
              + ("" if b["all_week"] else f", {a:%a %-d} to {z:%a %-d} of this "
                                          f"week")
              + (f"  [{b['settled']}]" if b.get("settled") else ""))
        if b["permits"]:
            print(f"      permitted: {'; '.join(b['permits'])}")
        elif b["scoped"]:
            print("      it names nothing it permits")
        else:
            print("      it names no exception, so it bars everything")
        for f in b["flagged"]:
            print(f"      NOT PERMITTED  {f['id']} {f['title']} "
                  f"({f['kind'] or 'no kind'}) — "
                  + ("barred" if f["verdict"] == conditions.BARRED
                     else "nobody has ruled on this kind"))
        if not b["flagged"]:
            print("      everything below is work it allows")
        print()
    if not days and not starting and not running and not buys:
        print("  nothing dated this week")
    for b in buys:
        sup = (data.get("suppliers") or {}).get(b.get("supplier")) or {}
        print(f"  BUY by {_date(b['by']):%a %-d %b}  {b['item']}  {money(b)}"
              + (f"  — {sup['name']}, {sup.get('phone') or sup['address']}"
                 if sup else ""))
    if buys:
        print()
    for d in sorted(days):
        mins = sum(t.get("minutes", 0) for t in days[d])
        print(f"  {d:%a %-d %b}   {hours(mins)}")
        for t in days[d]:
            mark = "x" if t.get("done") else " "
            flag = "  !" if t.get("critical") else "   "
            w = where_of(t)
            print(f"    [{mark}]{flag} {t['title']}"
                  + (f" ({hours(t['minutes'])})" if t.get("minutes") else "")
                  + (f"  — {w}" if w else ""))
        print()
    if starting:
        print("  starts this week")
        for t in starting:
            mark = "x" if t.get("done") else " "
            print(f"    [{mark}]    {t['title']}"
                  + (f" — {_cadence(t)}" if t.get("repeat") else ""))
        print()
    if running:
        print("  already running")
        for t in running:
            span = _repeat_span(t) or (_date(t["window"][0]),
                                       _date(t["window"][1]))
            print(f"         {t['title']} — {_cadence(t) or 'when it comes'}, "
                  f"to {span[1]:%-d %b}")
        print()
    problems = check(slug)
    if problems:
        print(f"  {len(problems)} disagreement"
              f"{'s' if len(problems) > 1 else ''} with the plan documents: "
              f"{stamp(problems)}.\n  `--check` says what to do about each.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--week", help="any date in the week you want")
    ap.add_argument("--calendar", action="store_true", help="write CALENDAR.md")
    ap.add_argument("--shop", nargs="?", type=int, const=3, default=None,
                    metavar="WEEKS", help="buying due in the next N weeks")
    ap.add_argument("--check", action="store_true",
                    help="where tasks.json and the plan documents disagree")
    ap.add_argument("--restamp", action="store_true",
                    help="record the sources as read, after reading them")
    ap.add_argument("--publish", action="store_true",
                    help="build the .docx and the checkbox runs for the Doc")
    ap.add_argument("--sync", metavar="EXPORTED_MD",
                    help="a text/markdown export of the published Doc")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="render past a disagreement; the page is stamped")
    args = ap.parse_args()

    if not args.slug:
        print(__doc__)
        return

    if args.check:
        problems = check(args.slug)
        clashes = blackout_conflicts(args.slug)
        if problems:
            print(f"  {len(problems)} disagreement"
                  f"{'s' if len(problems) > 1 else ''} between tasks.json and "
                  f"the documents it was built from:\n")
            for p in problems:
                print(f"      {p['message']}")
        else:
            print("  tasks.json agrees with every section it was built from")
        if clashes:
            _report_blackout(clashes, conditions.blackout_records(
                yards.load_conditions(args.slug) or {}))
        raise SystemExit(1 if problems else 0)

    if args.restamp:
        restamp(args.slug)
        return

    if args.publish:
        import subprocess
        import sys
        boxed, flat, out = publish(args.slug)
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(here, "skills", "yard-site-walk", "scripts",
                              "publish_checklist.py")
        subprocess.run([sys.executable, script, boxed], check=True, cwd=here)
        docx = os.path.join(out, "CALENDAR.docx")
        subprocess.run([sys.executable, "-m", "lib.builddoc", flat, "-o", docx],
                       check=True, cwd=here)
        data = load(args.slug)
        doc = data.get("google_doc") or {}
        print(f"\n  {out}/")
        print(f"      CALENDAR.docx        upload this")
        print(f"      CALENDAR.runs.json   then one createParagraphBullets per "
              f"entry, in order")
        print(f"      CALENDAR.html        fallback, if the .docx import "
              f"disagrees with you")
        if doc.get("id"):
            print(f"\n  uploadFile(localPath=<CALENDAR.docx>, "
                  f"fileId='{doc['id']}')   keeps the link")
        else:
            print(f"\n  uploadFile(localPath=<CALENDAR.docx>, "
                  f"convertToGoogleFormat=True), then record the id in "
                  f"tasks.json google_doc.id")
        return

    if args.sync:
        changed, unmatched, seen = sync(args.slug, args.sync)
        print(f"  {seen} checkbox items read from the export")
        for tid, title, done in changed:
            print(f"      {tid} {'ticked' if done else 'un-ticked'} — {title}")
        if not changed:
            print("      nothing had changed")
        if unmatched:
            print(f"  {len(unmatched)} item(s) in the Doc match no task, so the "
                  f"Doc and tasks.json have drifted apart. Re-render and "
                  f"re-publish rather than hand-patching:")
            for u in unmatched[:8]:
                print(f"      {u[:72]}")
        return

    if args.shop is not None:
        data, trips, end = shop(args.slug, args.shop)
        sup = data.get("suppliers", {})
        print(f"{args.slug} — everything due by {end:%a %-d %b}\n")
        for key in sorted(trips, key=lambda k: sup.get(k, {}).get("name", "zz")):
            s = sup.get(key)
            if s:
                print(f"  {s['name']} — {s['address']}, {s.get('phone') or ''}"
                      f"  {s.get('hours') or ''}")
                if s.get("note"):
                    print(f"      {s['note']}")
            else:
                print("  anywhere")
            for b in trips[key]:
                tag = "  (optional)" if b.get("optional") else ""
                print(f"      by {_date(b['by']):%-d %b}  {money(b):>12}  "
                      f"{b['item']}{tag}")
                if b.get("ask"):
                    print(f"                          {b['ask']}")
            print()
        return

    if args.calendar:
        path, weeks, text = calendar(args.slug, force=args.force)
        boxes = text.count("- [ ]") + text.count("- [x]")
        from . import changelog
        print(f"  {os.path.basename(path)} — {weeks} weeks, {boxes} checkbox "
              f"items, {changelog.prose_words(text)} words of prose")
        print(f"  {path}")
        return

    when = _date(args.week) if args.week else None
    if args.json:
        data = load(args.slug)
        mon = monday_of(when or datetime.date.today())
        days, starting, running = placed(data, mon)
        print(json.dumps({"week_of": mon.isoformat(),
                          "days": {d.isoformat(): v for d, v in days.items()},
                          "starts_this_week": starting,
                          "already_running": running,
                          "buy": buys_for(data, mon)}, indent=2))
        return
    report(args.slug, when)


if __name__ == "__main__":
    main()
