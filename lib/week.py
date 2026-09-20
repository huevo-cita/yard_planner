#!/usr/bin/env python3
"""One place that says what to do this week, built from the yard's dated actions.

    python3 -m lib.week <slug>                  this week, to the terminal
    python3 -m lib.week <slug> --week 2026-09-14
    python3 -m lib.week <slug> --html           -> WEEK.html, Mon-Sun on a page
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
import html
import json
import os
import re

from . import chrome, conditions, links, yards

# Reading a document and resolving a reference into it now live in `lib.links`,
# because the publisher needs the same two answers and a second implementation
# of them is how a deep link comes to point at nothing. Re-exported here: every
# caller of `week.resolve` is asking the same question it always was.
HEADING = links.HEADING
SECTION_NO = links.SECTION_NO
_slug = links.slug
sections = links.sections
resolve = links.resolve

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
        "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

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


def link_check(slug):
    """Every reference that points nowhere, and every plant name nobody knows.

    Reported and not blocking, on purpose, and the distinction is the same one
    `blackout_conflicts` draws. `check()` asks whether a person would be sent
    into the garden on the wrong day, and refuses a render when the answer is
    yes. A dead reference does not move a date. It costs the reader the
    explanation behind a job, which is worth fixing and is not worth refusing
    to print the calendar over.

    Two kinds, because they fail differently. A reference that resolves to
    nothing is a task whose method cannot be reached from the page somebody
    reads. A placement naming a plant the design does not contain is worse in
    a quieter way: the prose and the design disagree about what goes in the
    ground, and nothing else in the record compares them.
    """
    from . import bundle, plants

    out = []
    data = bundle.build(slug)
    for t in data["tasks"]:
        for l in t["links"]:
            if l["error"]:
                out.append({"kind": "reference", "subject": t["id"],
                            "message": f'{t["id"]} "{t["title"]}" cites '
                                       f'{l["kind"]} {l["ref"]!r}: '
                                       f'{l["error"]}'})
        for p in t["placements"]:
            if p["unmatched"] and p["positional"]:
                out.append({"kind": "placement", "subject": t["id"],
                            "message": f'{t["id"]} plants "{p["text"]}" at '
                                       f'{p.get("bed") or "?"} '
                                       f'{p.get("at") or ""}'.rstrip()
                                       + ", and design.json holds no plant "
                                         "of that name"})
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


def week_id(monday):
    """The stable id of a week: `w` and the ISO date of its Monday.

    A week is now a thing pages address, so it needs an id of the same kind as
    `t016`, `b15` and `c306`: one form, derivable, and the same in every file
    that names it. `WEEK.html` gives each week that id, `CALENDAR.html` links
    to `WEEK.html#w2026-10-19`, `bundle.json` carries it, and the script that
    picks the current week builds it from the device clock. Nothing stores a
    week number, because a number is only meaningful beside the plan that
    counted it, and the plan moves.
    """
    return "w" + monday.isoformat()


def week_monday(wid):
    """The Monday back out of a week id."""
    return _date(str(wid).lstrip("w"))


#: How far past the end of the record to look for the next piece of work. The
#: search runs over occurrences rather than dates, so it needs a stop.
_HORIZON_DAYS = 365 * 12


def next_work(data, after):
    """The first day after `after` that the record asks for work, and the task.

    Occurrences, not dates, so a standing job that runs on past the last one-off
    is named rather than passed over. Returns `(day, task)`, or None where the
    record asks for nothing more.
    """
    a = after + datetime.timedelta(days=1)
    z = after + datetime.timedelta(days=_HORIZON_DAYS)
    best = None
    for t in data.get("tasks", []):
        days = _occurrences(t, a, z)
        if not days:
            continue
        day = min(days)
        if best is None or (day, t["id"]) < (best[0], best[1]["id"]):
            best = (day, t)
    return best


def target_of(data):
    """The date the plan is built towards, or None where none is recorded."""
    return _date(data["target_date"]) if data.get("target_date") else None


def beyond_plan(monday, target):
    """Is this whole week later than the date the plan runs to.

    The week that holds the target is not beyond it. Every week whose Monday
    falls after the target is, and the distinction is the one an empty week
    turns on: before the target an empty week is planned and clear, after it
    nobody has planned that far.
    """
    return bool(target and monday > target)


def week_spine(data, cond=None, target=None):
    """Every week from the first job to the last, as one row of facts each.

    The spine is what the density strip, the calendar and the index all count
    from, and it goes into `bundle.json` so none of them counts it twice.
    """
    if not data or not data.get("tasks"):
        return []
    target = target or target_of(data)
    first, last = span_of(data)
    out, mon = [], first
    total = ((last - first).days // 7) + 1
    n = 0
    while mon <= last:
        n += 1
        sun = mon + datetime.timedelta(days=6)
        grid, loose = week_grid(data, mon)
        buys = buys_for(data, mon)
        s = week_shape(grid, loose, buys)
        blocks = week_blackout(data, cond or {}, mon)
        jobs = s["jobs"] + len(loose)
        out.append({
            "id": week_id(mon),
            "monday": mon.isoformat(),
            "sunday": sun.isoformat(),
            "minutes": s["fixed"],
            "standing_minutes": s["standing"],
            "jobs": jobs,
            "buys": len(buys),
            "critical": len(s["critical"]),
            "blackout": bool(blocks),
            "beyond": beyond_plan(mon, target),
            "empty": not jobs and not buys,
            "label": f"{mon:%-d %b}",
            "title": f"{mon:%A %-d %B} to {sun:%A %-d %B}",
            "position": f"week {n} of {total}",
        })
        mon += datetime.timedelta(weeks=1)
    return out


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


def detail_rows(t):
    """A task's detail as (label, value) pairs, in the order they are read.

    Split out from the markdown renderer because the HTML week page shows the
    same rows, and a second copy of this ordering would drift from this one the
    first time a field was added.

    Values are raw. Escaping and whitespace flattening belong to whichever
    renderer is being used, because they are not the same in the two formats.
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
            rows.append((spot, p["plant"]))
    elif where_of(t):
        rows.append(("Where", where_of(t)))
    if w.get("note"):
        rows.append(("Note", w["note"]))

    if t.get("how"):
        rows.append(("How", " · ".join(str(h) for h in t["how"])))
    g = t.get("gate") or {}
    if g.get("below_f"):
        rows.append(("Gate", f"Soil under {g['below_f']} °F"))
    elif g.get("depends"):
        rows.append(("Gate", f"depends on {g['depends']}"
                     + (f" — {g['unless']}" if g.get("unless") else "")))
    if g.get("early"):
        rows.append(("Earlier", g["early"]))
    for key, label in ((g.get("miss"), "If the window closes"),
                       (t.get("miss"), "If it slips")):
        if key:
            rows.append((label, key))
    for key, label in (("why", "Why"), ("warn", "Watch out"), ("then", "Then")):
        if t.get(key):
            rows.append((label, t[key]))
    return rows


def detail_links(t, root=None):
    """The task's references as (label, target) pairs.

    The target is the real `FILE.html#heading-anchor` wherever the reference
    resolves, worked out by `lib.links` — the same code the publisher uses to
    put the id on the heading, so the two cannot disagree about where a link
    lands. A reference that resolves to nothing keeps the file as its target
    rather than vanishing, because a task that silently loses its method is
    the failure `--links` exists to report.
    """
    w = t.get("where") or {}
    out = []
    for ref, label in ((t.get("technique"), "technique"),
                       (t.get("reference"), "detail")):
        if not ref:
            continue
        ref = str(ref)
        url, sec, err = (links.target(root, ref) if root
                         else (None, None, "no yard given"))
        name = ref.split("#")[0].split()[0]
        # The label stays short even though the target is now a full anchor.
        # This one goes into a markdown table cell and then into the Doc, and
        # a forty-word heading in a cell is worse than the dead link was.
        where = f" §{ref.partition('#')[2]}" if "#" in ref else (
            " " + " ".join(ref.split()[1:]) if len(ref.split()) > 1 else "")
        if ref.startswith(("http://", "https://")):
            out.append((f"{label} at {links.label(ref)}", ref))
        else:
            out.append((f"{label} in {name}{where}", url or name))
    if w.get("map"):
        out.append(("bed map", w["map"]))
    return out


def _detail(t, root=None):
    """A task's detail, as a table.

    A table rather than paragraphs for two reasons that point the same way. This
    is looked up for the one task in hand rather than read straight through, so
    the labelled rows are easier to scan than prose. And the action-document word
    budget counts prose only, precisely because a table does not cost the reader
    what an argument does — seventy tasks of depth, spacing and fallbacks in
    paragraph form would put this document three times over it and get the whole
    check switched off.
    """
    rows = [(_cell(a), _cell(b)) for a, b in detail_rows(t)]

    refs = [f"[{label}]({target})"
            for label, target in detail_links(t, root)]
    if t.get("changelog"):
        refs.append(" ".join(f"[{c}]" for c in t["changelog"]))
    if refs:
        rows.append(("More", " · ".join(refs)))

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
    root = yards.yard_dir(slug) if slug else None
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
            out += _detail(t, root)

    if starting:
        out.append("### Starts this week, and runs on")
        out.append("")
        for t in starting:
            out.append(_checkbox(t))
        out.append("")
        for t in starting:
            out += _detail(t, root)

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


def week_grid(data, monday):
    """Every day of the week, with the work that actually lands on it.

    `placed()` splits a week three ways, and that split is right for a document
    somebody ticks: a daily watering rendered as a checkbox in each of the nine
    weeks it spans reads as nagging, and the Docs checkbox pass cannot address
    nine identical strings. It is the wrong split for a week read at a glance,
    because it lifts every standing job off the days it happens on and leaves
    the reader to work out for themselves which of them lands on Tuesday. That
    is the specific confusion this grid exists to remove.

    So a repeat is expanded onto each day it asks for work, and carries a flag
    saying it is standing rather than one-off. A window is not expanded. It is
    returned separately, because the record does not say which day inside the
    window the work happens, and putting it on Monday would state a date nobody
    chose.
    """
    sunday = monday + datetime.timedelta(days=6)
    grid = {monday + datetime.timedelta(days=i): [] for i in range(7)}
    loose = []
    for t in data.get("tasks", []):
        if t.get("window"):
            lo, hi = _date(t["window"][0]), _date(t["window"][1])
            if lo <= sunday and hi >= monday:
                loose.append(t)
            continue
        standing = bool(t.get("repeat"))
        for d in _occurrences(t, monday, sunday):
            grid[d].append((t, standing))
    for items in grid.values():
        items.sort(key=lambda p: (p[1], not p[0].get("critical"),
                                  -p[0].get("minutes", 0)))
    loose.sort(key=lambda t: (not t.get("critical"), t["id"]))
    return grid, loose


def week_shape(grid, loose, buys):
    """The numbers the summary strip quotes, counted off the grid itself.

    Counted from the grid rather than alongside it, so the headline and the
    days cannot disagree. A total that has drifted from the thing it totals is
    worse than no total, because it is believed.
    """
    fixed = standing = 0
    per_day = {}
    critical, seen = [], set()
    for d, items in grid.items():
        f = sum(t.get("minutes", 0) for t, s in items if not s)
        s = sum(t.get("minutes", 0) for t, st in items if st)
        per_day[d] = (f, s)
        fixed += f
        standing += s
        for t, st in items:
            if t.get("critical") and t["id"] not in seen:
                seen.add(t["id"])
                critical.append((d, t))
    busiest = max(per_day, key=lambda d: per_day[d][0] + per_day[d][1])
    if sum(per_day[busiest]) == 0:
        busiest = None
    jobs = len({t["id"] for items in grid.values() for t, _ in items})
    return {"fixed": fixed, "standing": standing, "per_day": per_day,
            "busiest": busiest,
            "critical": sorted(critical, key=lambda p: (p[0], p[1]["id"])),
            "jobs": jobs, "loose": len(loose),
            "buys": [b for b in buys if not b.get("optional")]}


WEEK_CSS = """
:root { --ink:#1a1a1a; --muted:#5c5c5c; --rule:#dcdcdc; --accent:#2f5d34;
        --band:#f6f7f4; --today:#fff8e1; --todayline:#b45309; --crit:#a52121; }
* { box-sizing:border-box; }
body { margin:0; background:#fff; color:var(--ink);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
.wrap { max-width:58rem; margin:0 auto; padding:2rem 1.1rem 5rem; }
h1 { font-size:1.75rem; margin:0 0 .1em; letter-spacing:-.02em; }
p.sub { margin:0 0 1.2em; color:var(--muted); }
a { color:var(--accent); }

.shape { display:flex; flex-wrap:wrap; gap:.5em; margin:0 0 1em; }
.stat { flex:1 1 7rem; background:var(--band); border:1px solid var(--rule);
  border-radius:8px; padding:.55em .75em; }
.stat b { display:block; font-size:1.35rem; line-height:1.15;
  font-variant-numeric:tabular-nums; }
.stat span { color:var(--muted); font-size:.76rem; text-transform:uppercase;
  letter-spacing:.05em; }
.gist { border-left:4px solid var(--accent); background:var(--band);
  padding:.7em 1em; border-radius:0 8px 8px 0; margin:0 0 1.6em; }
.gist p { margin:.35em 0; }

.day { border:1px solid var(--rule); border-radius:10px; margin:.55em 0;
  overflow:hidden; }
.day.weekend { background:#fbfbf9; }
.day.today { border-color:var(--todayline); box-shadow:0 0 0 1px var(--todayline); }
.dayhead { display:flex; align-items:baseline; gap:.6em; padding:.5em .85em;
  background:var(--accent); color:#fff; }
.day.weekend .dayhead { background:#24482a; }
.day.today .dayhead { background:var(--todayline); }
.dayhead .dow { font-weight:700; font-size:1rem; }
.dayhead .dat { opacity:.85; font-size:.85rem; }
.dayhead .mins { margin-left:auto; font-size:.85rem;
  font-variant-numeric:tabular-nums; }
.empty { padding:.6em .9em; color:var(--muted); font-size:.88rem; }

details.job { border-top:1px solid var(--rule); }
details.job:first-of-type { border-top:0; }
summary { cursor:pointer; padding:.5em .85em; list-style:none;
  display:flex; align-items:baseline; gap:.5em; }
summary::-webkit-details-marker { display:none; }
summary::before { content:"\\25B8"; color:var(--muted); font-size:.8em; }
details[open] > summary::before { content:"\\25BE"; }
summary:hover { background:var(--band); }
.ttl { font-weight:600; }
details.standing .ttl { font-weight:400; color:#444; }
.tag { font-size:.7rem; text-transform:uppercase; letter-spacing:.05em;
  border:1px solid var(--rule); border-radius:999px; padding:.05em .5em;
  color:var(--muted); white-space:nowrap; }
.tag.crit { color:var(--crit); border-color:var(--crit); font-weight:600; }
.tag.done { color:var(--accent); border-color:var(--accent); }
.mins2 { margin-left:auto; color:var(--muted); font-size:.82rem;
  white-space:nowrap; font-variant-numeric:tabular-nums; }
.where { color:var(--muted); font-size:.85rem; }

dl.detail { margin:0; padding:.2em .85em 1em; border-top:1px dashed var(--rule);
  display:grid; grid-template-columns:8.5rem 1fr; gap:.3em .9em;
  font-size:.92rem; }
dl.detail dt { color:var(--muted); font-size:.82rem; padding-top:.15em; }
dl.detail dd { margin:0; }
dl.detail dd ul { margin:.1em 0; padding-left:1.1em; }
dl.detail dd li { margin:.15em 0; }

p.tools { margin:0 0 .6em; }
p.tools button { font:inherit; font-size:.85rem; cursor:pointer;
  background:var(--band); border:1px solid var(--rule); border-radius:999px;
  padding:.3em 1em; color:var(--accent); }
p.tools button:hover { background:#eceee8; }
.loose { border:1px dashed var(--rule); border-radius:10px; margin:1.2em 0 0; }
.loose > .dayhead { background:#6b6b6b; }
table.buy { border-collapse:collapse; width:100%; font-size:.9rem;
  margin:.6em 0 1.4em; }
table.buy th, table.buy td { padding:.45em .6em; text-align:left;
  border-bottom:1px solid var(--rule); vertical-align:top; }
table.buy thead th { background:var(--band); font-size:.76rem;
  text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
h2 { font-size:1.05rem; margin:2em 0 .4em; padding-bottom:.2rem;
  border-bottom:2px solid var(--accent); }
.warn { border-left:4px solid var(--todayline); background:#fef3c7;
  color:#78350f; padding:.7em 1em; border-radius:0 8px 8px 0; margin:1em 0; }

/* Every week of the plan is in the page and one of them is shown. The
   fallback, with no script running, is the week the build chose. */
section.wk { display:none; }
section.wk.on { display:block; }

.weeknav { display:flex; flex-wrap:wrap; gap:.4em; align-items:baseline;
  margin:0 0 .5em; }
.weeknav button { font:inherit; font-size:.85rem; cursor:pointer;
  background:var(--band); border:1px solid var(--rule); border-radius:999px;
  padding:.3em 1em; color:var(--accent); }
.weeknav button:hover { background:#eceee8; border-color:var(--accent); }
.weeknav button[disabled] { opacity:.38; cursor:default; }
.weeknav .notnow { color:var(--todayline); font-size:.82rem; font-weight:600; }
.weeknav .pos { margin-left:auto; color:var(--muted); font-size:.8rem; }

/* Hours a week, across the whole plan. A strip and not a slider: 129 weeks
   give a slider about two pixels of thumb travel on a phone. It scrolls, the
   current week is scrolled into the middle of it, and the buttons above are
   the controls that a thumb is meant to use. */
.density { display:flex; align-items:flex-end; gap:1px; height:2.3rem;
  overflow-x:auto; background:var(--band); border:1px solid var(--rule);
  border-radius:8px; padding:3px; margin:0 0 .25em; scrollbar-width:none;
  -webkit-overflow-scrolling:touch; }
.density::-webkit-scrollbar { display:none; }
.density a.bar { flex:0 0 6px; height:100%; display:flex; align-items:flex-end;
  text-decoration:none; border-radius:2px; }
.density a.bar i { display:block; width:100%; min-height:2px;
  background:#b9c9ba; border-radius:1px; }
.density a.bar.beyond i { background:#e0e0d8; }
.density a.bar.crit i { background:var(--accent); }
.density a.bar.now i { background:var(--todayline); }
.density a.bar.at { background:rgba(47,93,52,.2); }
.density a.bar:hover i { background:#24482a; }
p.dnote { margin:0 0 1.1em; color:var(--muted); font-size:.76rem; }

.note { border-left:4px solid var(--rule); background:var(--band);
  padding:.8em 1em; border-radius:0 8px 8px 0; margin:1em 0; }
.note.beyond { border-left-color:var(--todayline); background:#fff8e1; }
.note b { display:block; margin-bottom:.25em; }
.note p { margin:.35em 0; font-size:.93rem; }
.tagline { color:var(--todayline); font-size:.82rem; font-weight:600;
  margin:0 0 .6em; }
footer { margin-top:2.5rem; padding-top:1em; border-top:1px solid var(--rule);
  color:var(--muted); font-size:.8rem; }
code { font:.87em ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--band); padding:.1em .3em; border-radius:3px; }
@media (max-width:640px) {
  .wrap { padding:1.2rem .6rem 3rem; }
  h1 { font-size:1.35rem; }
  dl.detail { grid-template-columns:1fr; gap:.05em; }
  dl.detail dt { margin-top:.5em; }
  .stat { flex:1 1 40%; } }
@media print { details { break-inside:avoid; } details > .detail { display:grid; } }
"""


def _job_html(t, standing, show_cadence=True, root=None):
    e = html.escape
    tags = []
    if t.get("critical"):
        tags.append('<span class="tag crit">cannot slip</span>')
    if standing and show_cadence:
        tags.append(f'<span class="tag">{e(_cadence(t))}</span>')
    w = where_of(t)
    mins = hours(t["minutes"]) if t.get("minutes") else ""

    rows = []
    for label, value in detail_rows(t):
        if label == "How":
            steps = "".join(f"<li>{e(str(h))}</li>" for h in t["how"])
            rows.append(("How", f"<ul>{steps}</ul>"))
        else:
            rows.append((label, e(str(value))))
    if standing:
        span = _repeat_span(t)
        if span:
            rows.append(("Runs", f"{_cadence(t)}, "
                                 f"{span[0]:%-d %b} to {span[1]:%-d %b}"))
    refs = [f'<a href="{e(target)}">{e(label)}</a>'
            for label, target in detail_links(t, root)]
    if t.get("changelog"):
        refs += [f'<a href="CHANGELOG.html#{e(c)}">{e(c)}</a>'
                 for c in t["changelog"]]
    if refs:
        rows.append(("More", " · ".join(refs)))
    # Into the one page that holds the whole job. Every screen points at the
    # same anchor, so there is one address for a task and not four.
    rows.append(("Task", f'<a href="TASKS.html#{e(t["id"])}">'
                         f'<code>{e(t["id"])}</code> in full</a>'))

    body = "".join(f"<dt>{e(str(a))}</dt><dd>{b}</dd>" for a, b in rows)
    cls = "job standing" if standing else "job"
    return (f'<details class="{cls}"><summary>'
            + chrome.tick(t)
            + f'<span class="ttl">{e(t["title"])}</span>'
            + "".join(tags)
            + (f'<span class="where">{e(w)}</span>' if w else "")
            + (f'<span class="mins2">{mins}</span>' if mins else "")
            + f'</summary><dl class="detail">{body}</dl></details>')


def _runs_to(target, note):
    """The date the plan runs to, as a page says it."""
    said = f"{target:%A %-d %B %Y}"
    return said + (f" &mdash; {html.escape(str(note))}" if note else "")


def _quiet_note(target, note):
    """An empty week the plan reaches: nothing to do, and it means it."""
    if not target:
        return ('<div class="note quiet"><b>Nothing is planned for this '
                'week.</b><p>This yard records no target date, so nothing '
                'here can say whether the plan reaches this week or stops '
                'before it.</p></div>')
    return ('<div class="note quiet"><b>Nothing is planned for this week.</b>'
            f'<p>The plan runs to {_runs_to(target, note)}, and it leaves '
            f'this week clear.</p></div>')


def _beyond_note(data, monday, target, note):
    """An empty week past the target: the plan stops, and says where.

    A blank week and a finished week look the same on a page, and this is the
    difference between them. The plan runs to a date; after that date nobody
    has planned the week rather than nothing needing doing in it.

    Only a blank week gets this note. Weeks past the target do carry work, and
    they take the ordinary week body with a tagline. The blank ones can sit a
    long way in front of the next job, so each of them names that job and
    links to it.
    """
    e = html.escape
    sunday = monday + datetime.timedelta(days=6)
    nxt = next_work(data, sunday)
    out = ['<div class="note beyond"><b>Beyond the plan.</b>',
           f'<p>The plan runs to {_runs_to(target, note)}. This week is after '
           f'that. So the record does not say the week is clear; it says '
           f'nobody has planned this far.</p>']
    if nxt:
        day, t = nxt
        out.append(
            f'<p>The next dated job is <a href="TASKS.html#{e(t["id"])}">'
            f'<code>{e(t["id"])}</code> {e(t["title"])}</a>, on '
            f'{day:%A %-d %B %Y}. '
            f'<a class="goweek" href="#{week_id(monday_of(day))}">'
            f'Open that week</a>.</p>')
    else:
        out.append('<p>The record asks for no work after this week.</p>')
    out.append("</div>")
    return "".join(out)


def _week_body(slug, data, cond, monday, root, target=None, note=None):
    """One week: the shape, the seven days, what to buy, the detail on a click.

    Every week of the plan is rendered this way and all of them travel in the
    page, because the page is read on a phone that is often offline and the
    build cannot know which day it will be opened on. The script picks; it
    never composes a sentence.
    """
    e = html.escape
    grid, loose = week_grid(data, monday)
    buys = buys_for(data, monday)
    s = week_shape(grid, loose, buys)
    beyond = beyond_plan(monday, target)

    if not s["jobs"] and not loose and not buys:
        return (_beyond_note(data, monday, target, note) if beyond
                else _quiet_note(target, note))

    tag = (f'<p class="tagline">Beyond the plan, which runs to '
           f'{_runs_to(target, note)}.</p>') if beyond else ""

    # Jobs in all counts the loose ones too. A week whose only work sits in a
    # window used to read "0 jobs in all" above two jobs, and the strip is the
    # first thing anybody reads. This is the count the spine carries.
    stats = [(hours(s["fixed"]), "dated work"),
             (hours(s["standing"]) if s["standing"] else "none",
              "standing jobs"),
             (str(s["jobs"] + len(loose)), "jobs in all"),
             (f"{s['busiest']:%a}" if s["busiest"] else "\u2014",
              "busiest day")]
    if s["buys"]:
        first = min(s["buys"], key=lambda b: b["by"])
        stats.append((str(len(s["buys"])),
                      f"to buy, first {_date(first['by']):%a}"))
    strip = "".join(f'<div class="stat"><b>{e(a)}</b><span>{e(b)}</span></div>'
                    for a, b in stats)

    gist = []
    if s["critical"]:
        gist.append("<p><b>Cannot slip:</b> " + "; ".join(
            f'{d:%A} &mdash; {e(t["title"])}' for d, t in s["critical"])
            + ".</p>")
    if s["busiest"] and sum(s["per_day"][s["busiest"]]) >= 60:
        f, st = s["per_day"][s["busiest"]]
        gist.append(f"<p><b>{s['busiest']:%A}</b> carries {hours(f + st)} of "
                    f"it. The other six days hold {hours(s['fixed'] - f)} of "
                    f"dated work between them.</p>")
    if s["standing"]:
        gist.append(f"<p>{hours(s['standing'])} of that is standing jobs "
                    f"&mdash; watering and the like, a few minutes at a time, "
                    f"shown on each day they fall on.</p>")
    if loose:
        many = len(loose) > 1
        gist.append(f"<p>{len(loose)} job{'s' if many else ''} "
                    f"{'have' if many else 'has'} a window rather than a day, "
                    f"and {'they are' if many else 'it is'} under "
                    f"&ldquo;any day this week&rdquo; below.</p>")
    if not gist:
        gist.append("<p>A quiet week. Nothing on it cannot move.</p>")

    banner = ""
    blocks = week_blackout(data, cond or {}, monday)
    for b in blocks:
        banner += (f'<div class="warn"><b>No-build week.</b> The '
                   f'{b["from"]:%-d %b}&ndash;{b["to"]:%-d %b} blackout bars '
                   f'{e(b["bars"] or "work it has not named")}.'
                   + (f' Permitted: {e("; ".join(b["permits"]))}.'
                      if b["permits"] else "")
                   + "</div>")

    daysout = []
    for i in range(7):
        d = monday + datetime.timedelta(days=i)
        items = grid[d]
        f, st = s["per_day"][d]
        # Which day is today is a fact about the reader's device, so the
        # script marks it. The build stamps the day it belongs to and nothing
        # more, because a baked "today" is wrong from the next morning on.
        cls = "day" + (" weekend" if d.weekday() >= 5 else "")
        mins = " + ".join(x for x in
                          [hours(f) if f else "", f"{st} min standing" if st
                           else ""] if x)
        inner = "".join(_job_html(t, standing, root=root)
                        for t, standing in items) \
            or '<div class="empty">Nothing dated.</div>'
        daysout.append(
            f'<section class="{cls}" data-day="{d.isoformat()}">'
            f'<div class="dayhead">'
            f'<span class="dow">{d:%A}</span>'
            f'<span class="dat">{d:%-d %B}</span>'
            f'<span class="mins">{mins or "&mdash;"}</span></div>'
            f'{inner}</section>')

    if loose:
        inner = "".join(_job_html(t, True, show_cadence=False, root=root)
                        for t in loose)
        # These minutes are deliberately outside the headline figure, because
        # the work is not promised to this week. They are still quoted, because
        # a reader planning a Saturday needs to know they exist.
        spare = sum(t.get("minutes", 0) for t in loose)
        daysout.append(
            '<section class="day loose"><div class="dayhead">'
            '<span class="dow">Any day this week</span>'
            '<span class="dat">the record names no day for these</span>'
            f'<span class="mins">{hours(spare)}, not in the total</span>'
            '</div>' + inner + '</section>')

    buytable = ""
    if buys:
        sup = data.get("suppliers", {})
        rows = ""
        for b in buys:
            shop = sup.get(b.get("supplier")) or {}
            where = e(shop["name"]) if shop else "anywhere"
            if shop.get("phone"):
                where += f'<br><a href="tel:{e(shop["phone"])}">' \
                         f'{e(shop["phone"])}</a>'
            rows += (f'<tr><td>{e(b["item"])}</td>'
                     f'<td>{_date(b["by"]):%a %-d %b}</td>'
                     f'<td>{e(money(b))}</td><td>{where}</td></tr>')
        buytable = ('<h2>To buy this week</h2><table class="buy"><thead><tr>'
                    '<th>Item</th><th>By</th><th>Cost</th><th>Where</th>'
                    f'</tr></thead><tbody>{rows}</tbody></table>')

    return (tag
            + f'<div class="shape">{strip}</div>'
            + f'<div class="gist">{"".join(gist)}</div>'
            + banner + "".join(daysout) + buytable)


#: Picking the week, moving between weeks, and marking the day.
#:
#: Everything this does is a choice between things Python already wrote. It
#: shows one of the rendered weeks, copies that week's own title into the
#: heading, and adds a class to the day the device says it is. It composes no
#: sentence and computes no hours, so it cannot disagree with the page it is
#: in. The date arithmetic it leans on is in `chrome.DATES_JS`.
WEEK_JS = """
(function () {
  var weeks = [].slice.call(document.querySelectorAll('section.wk'));
  if (!weeks.length) return;
  var out = document.getElementById('wkout');
  var ttl = document.getElementById('wkttl');
  var pos = document.getElementById('wkpos');
  var notnow = document.getElementById('notnow');
  var prev = document.getElementById('prevwk');
  var next = document.getElementById('nextwk');
  var strip = document.getElementById('density');
  var index = {}, at = -1, moved = false;
  weeks.forEach(function (s, i) { index[s.id] = i; });

  function bars() {
    return strip ? [].slice.call(strip.querySelectorAll('a.bar')) : [];
  }

  function mark_today() {
    var day = yard.today(), id = yard.weekId(day);
    [].forEach.call(document.querySelectorAll('.day.today'), function (el) {
      el.classList.remove('today');
    });
    [].forEach.call(document.querySelectorAll('.day[data-day="' + day + '"]'),
      function (el) { el.classList.add('today'); });
    bars().forEach(function (b) {
      b.classList.toggle('now', b.getAttribute('data-week') === id);
    });
  }

  function show(i) {
    if (i < 0 || i >= weeks.length) return;
    if (out) out.hidden = true;
    weeks.forEach(function (s, k) { s.classList.toggle('on', k === i); });
    at = i;
    var s = weeks[i], id = s.id;
    if (ttl) ttl.textContent = s.getAttribute('data-title');
    if (pos) pos.textContent = s.getAttribute('data-pos');
    if (prev) prev.disabled = i === 0;
    if (next) next.disabled = i === weeks.length - 1;
    if (notnow) notnow.hidden = id === yard.weekId(yard.today());
    bars().forEach(function (b) {
      b.classList.toggle('at', b.getAttribute('data-week') === id);
    });
    var here = strip && strip.querySelector('a.bar[data-week="' + id + '"]');
    // Scrolled by hand rather than with scrollIntoView, which also scrolls
    // the page and throws the reader to the top of the strip on load.
    if (here) strip.scrollLeft = here.offsetLeft - strip.clientWidth / 2;
    window.scrollTo(0, 0);
    if (window.yardTally) window.yardTally();
    // Only once the reader has moved. Writing the week into the address on
    // the way in gives the browser a section to scroll to when loading ends,
    // which pushes the week's own heading off the top of the screen.
    if (moved && window.history && history.replaceState)
      history.replaceState(null, '', '#' + id);
  }

  function outside() {
    weeks.forEach(function (s) { s.classList.remove('on'); });
    at = -1;
    if (out) out.hidden = false;
    if (ttl && out) ttl.textContent = out.getAttribute('data-title');
    if (pos) pos.textContent = '';
    if (notnow) notnow.hidden = true;
    if (prev) prev.disabled = false;
    if (next) next.disabled = false;
  }

  function step(n) {
    if (at < 0) { show(n > 0 ? 0 : weeks.length - 1); return; }
    show(Math.min(weeks.length - 1, Math.max(0, at + n)));
  }

  function now() {
    var id = yard.weekId(yard.today());
    mark_today();
    if (id in index) show(index[id]); else outside();
  }

  function from_hash() {
    var h = (location.hash || '').slice(1);
    return (h && h in index) ? index[h] : -1;
  }

  if (prev) prev.addEventListener('click', function () { step(-1); });
  if (next) next.addEventListener('click', function () { step(1); });
  var back = document.getElementById('thiswk');
  if (back) back.addEventListener('click', now);

  window.addEventListener('hashchange', function () {
    var i = from_hash();
    if (i >= 0) show(i);
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var el = ev.target;
    if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName || '')) return;
    if (ev.key === 'ArrowLeft') { step(-1); ev.preventDefault(); }
    else if (ev.key === 'ArrowRight') { step(1); ev.preventDefault(); }
    else if (ev.key === 't' || ev.key === 'T') { now(); }
  });

  // The same two handlers under a thumb. A drag to the left moves forward,
  // the way a page turns. The density strip scrolls sideways itself, so a
  // touch that starts in it is left alone.
  var x0 = null, y0 = null;
  document.addEventListener('touchstart', function (ev) {
    if (ev.touches.length !== 1 ||
        (ev.target.closest && ev.target.closest('#density'))) {
      x0 = null;
      return;
    }
    x0 = ev.touches[0].clientX;
    y0 = ev.touches[0].clientY;
  }, {passive: true});

  document.addEventListener('touchend', function (ev) {
    if (x0 === null) return;
    var t = ev.changedTouches[0], dx = t.clientX - x0, dy = t.clientY - y0;
    x0 = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    step(dx < 0 ? 1 : -1);
  }, {passive: true});

  var all = document.getElementById('all');
  if (all) all.addEventListener('click', function () {
    var jobs = document.querySelectorAll('section.wk.on details.job');
    var opening = all.dataset.open !== 'yes';
    [].forEach.call(jobs, function (d) { d.open = opening; });
    all.dataset.open = opening ? 'yes' : 'no';
    all.textContent = opening ? 'Close every task' : 'Open every task';
  });

  var i = from_hash();
  mark_today();
  if (i >= 0) show(i); else now();
  moved = true;

  // A week arrived at by its id is still scrolled to by the browser when
  // loading ends. The week is chosen rather than scrolled to, so the page
  // belongs at the top. This runs after that scroll, not before it.
  window.addEventListener('load', function () { window.scrollTo(0, 0); });
})();
"""


def _density_strip(spine):
    """Hours a week across the whole plan, as one bar each.

    Orientation, and the reason paging through empty weeks is bearable. The
    clusters of real work are visible as shape, and a bar is a link to its own
    week. It is not a slider: 129 weeks give a slider about two pixels of
    thumb travel, so this scrolls and the buttons do the moving.
    """
    if not spine:
        return ""
    top = max(w["minutes"] + w["standing_minutes"] for w in spine) or 1
    bars = []
    for w in spine:
        mins = w["minutes"] + w["standing_minutes"]
        pct = max(6, round(100.0 * mins / top)) if mins else 0
        cls = "bar" + (" beyond" if w["beyond"] else "") \
                    + (" crit" if w["critical"] else "")
        note = (f'{w["label"]} &middot; {hours(w["minutes"])} &middot; '
                f'{w["jobs"]} job{"s" if w["jobs"] != 1 else ""}'
                + (" &middot; beyond the plan" if w["beyond"] else ""))
        bars.append(f'<a class="{cls}" href="#{w["id"]}" '
                    f'data-week="{w["id"]}" title="{note}" '
                    f'aria-label="{note}"><i style="height:{pct}%"></i></a>')
    return ('<div class="density" id="density">' + "".join(bars) + "</div>")


def render_week_html(slug, monday=None, today=None, data=None):
    """Every week of the plan on one page, with the device clock picking one.

    The page used to hold one week, chosen on the day it was built. It then
    said the same seven days for as long as nobody rebuilt it, which on a
    phone read overnight is wrong by the next morning and says nothing about
    being wrong. So the build ships the whole span and the script picks. The
    page is correct on any day it is opened, offline, with no rebuild.

    `monday` is the week the page shows when no script runs. `--week` sets it,
    and it is a fallback rather than the answer.
    """
    e = html.escape
    tasks = load(slug)
    root = yards.yard_dir(slug)
    cond = yards.load_conditions(slug) or {}
    today = today or datetime.date.today()
    target = target_of(tasks or {})
    note = (tasks or {}).get("target_note")
    spine = week_spine(tasks or {}, cond, target)
    name = yard_name(slug)
    built = (data or {}).get("built") or datetime.date.today().isoformat()

    if not spine:
        first = last = monday_of(monday or today)
        spine = [{"id": week_id(first), "monday": first.isoformat(),
                  "sunday": (first + datetime.timedelta(days=6)).isoformat(),
                  "minutes": 0, "standing_minutes": 0, "jobs": 0, "buys": 0,
                  "critical": 0, "blackout": False, "beyond": False,
                  "empty": True, "label": f"{first:%-d %b}",
                  "title": f"{first:%A %-d %B} to "
                           f"{first + datetime.timedelta(days=6):%A %-d %B}",
                  "position": "week 1 of 1"}]

    want = week_id(monday_of(monday or today))
    ids = [w["id"] for w in spine]
    default = want if want in ids else ids[0]

    sections = []
    for w in spine:
        mon = _date(w["monday"])
        body = _week_body(slug, tasks or {}, cond, mon, root, target, note)
        on = " on" if w["id"] == default else ""
        sections.append(
            f'<section class="wk{on}" id="{w["id"]}" '
            f'data-monday="{w["monday"]}" data-title="{e(w["title"])}" '
            f'data-pos="{e(w["position"])}">{body}</section>')

    first, last = _date(spine[0]["monday"]), _date(spine[-1]["sunday"])
    outside = (
        f'<section class="note beyond" id="wkout" '
        f'data-title="Outside the plan" hidden>'
        f'<b>Today is outside this plan.</b>'
        f'<p>The plan covers {first:%-d %B %Y} to {last:%-d %B %Y}, and today '
        f'is not in it. Nothing below is wrong; none of it is about this '
        f'week.</p>'
        f'<p><a class="goweek" href="#{spine[0]["id"]}">Open the first week'
        f'</a> &middot; <a class="goweek" href="#{spine[-1]["id"]}">open the '
        f'last week</a>.</p></section>')

    shown = next(w for w in spine if w["id"] == default)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(name)} &mdash; this week</title>
<style>{WEEK_CSS}{chrome.NAV_CSS}{chrome.TICKS_CSS}{chrome.STALE_CSS}</style>
</head>
<body>
{chrome.nav(root, 'WEEK.html', name)}
<div class="wrap">
{chrome.stale_banner(slug, built)}
<h1 id="wkttl">{e(shown['title'])}</h1>
<p class="sub">{e(name)} &middot; every day of the week, with the detail behind
a click. The week follows this device's clock, so opening the page tomorrow
moves it on. Any job opens to its full instructions in
<a href="TASKS.html">every job, in full</a>.</p>

<p class="weeknav">
<button type="button" id="prevwk">&larr; Previous</button>
<button type="button" id="thiswk">This week</button>
<button type="button" id="nextwk">Next &rarr;</button>
<span class="notnow" id="notnow" hidden>Not the current week</span>
<span class="pos" id="wkpos">{e(shown['position'])}</span>
</p>

{_density_strip(spine)}
<p class="dnote">Hours of dated work, week by week, over the whole plan. Each
bar opens its week. Arrow keys move a week at a time, and so does a swipe.</p>

{chrome.tools('<button type="button" id="all">Open every task</button>')}
{"".join(sections)}
{outside}

<footer>
<p>Built from <code>tasks.json</code> on {built} by
<code>python3 -m lib.week {e(slug)} --html</code>. Every week of the plan is
in this file and the clock picks one, so the page is right on any day it is
opened, offline. A week is addressed as
<code>WEEK.html#{e(shown['id'])}</code>, which is the Monday's date.</p>
<p>A standing job appears on every day it asks for work, so the week reads as
days rather than as a list with the repeats filed at the bottom.</p>
</footer>

</div>
{chrome.dates_js()}
<script>
{WEEK_JS}
{chrome.ticks_js(slug, scope='section.wk.on')}
{chrome.STALE_JS}
</script>
</body>
</html>
"""


# ------------------------------------------------------- every job, in full

TASKS_CSS = """
.jump { position:sticky; top:2.6rem; z-index:10; background:#fff;
  border-bottom:1px solid var(--rule); display:flex; gap:.15em;
  overflow-x:auto; padding:.4em 0; margin:0 0 1em; scrollbar-width:none; }
.jump::-webkit-scrollbar { display:none; }
.jump a { flex:0 0 auto; font-size:.8rem; text-decoration:none;
  padding:.25em .6em; border-radius:999px; background:var(--band);
  border:1px solid var(--rule); white-space:nowrap; }
.jump a:hover { border-color:var(--accent); }

h2.month { position:relative; margin:2.2em 0 .6em; }
article.task { border:1px solid var(--rule); border-left:4px solid var(--rule);
  border-radius:8px; padding:.8em 1em 1em; margin:.7em 0;
  scroll-margin-top:5.5rem; }
article.task.crit { border-left-color:var(--crit); }
article.task.done { opacity:.62; }
article.task h3 { margin:0; font-size:1.06rem; color:var(--ink);
  display:flex; gap:.5em; align-items:baseline; flex-wrap:wrap; }
article.task h3 a.self { margin-left:auto; font-size:.72rem; color:var(--muted);
  text-decoration:none; font-variant-numeric:tabular-nums; }
article.task h3 a.self:hover { color:var(--accent); }
.meta { color:var(--muted); font-size:.86rem; margin:.2em 0 .6em;
  display:flex; gap:.5em; flex-wrap:wrap; align-items:baseline; }
.badge { font-size:.68rem; text-transform:uppercase; letter-spacing:.05em;
  border:1px solid var(--rule); border-radius:999px; padding:.05em .55em;
  color:var(--muted); white-space:nowrap; }
.badge.crit { color:var(--crit); border-color:var(--crit); font-weight:700; }
.badge.kind { color:var(--accent); border-color:var(--accent); }

dl.f { margin:0; display:grid; grid-template-columns:8rem 1fr; gap:.25em .9em;
  font-size:.93rem; }
dl.f dt { color:var(--muted); font-size:.79rem; padding-top:.2em;
  text-transform:uppercase; letter-spacing:.04em; }
dl.f dd { margin:0; }
dl.f dd ol, dl.f dd ul { margin:.1em 0; padding-left:1.2em; }
dl.f dd li { margin:.25em 0; }
dl.f dd.gate { background:#fef3c7; color:#78350f; border-radius:5px;
  padding:.35em .6em; }

table.place { border-collapse:collapse; width:100%; font-size:.9rem; }
table.place td { padding:.3em .5em .3em 0; vertical-align:top;
  border-bottom:1px solid var(--rule); }
table.place td.spot { color:var(--muted); white-space:nowrap; width:9rem; }
table.place td.sp i { color:var(--muted); font-size:.85rem; }
table.place .miss { color:var(--warnline); font-size:.8rem; }

.shots { display:flex; flex-wrap:wrap; gap:.5em; margin:.5em 0 0; }
figure.shot { margin:0; width:8.2rem; border:1px solid var(--rule);
  border-radius:7px; overflow:hidden; }
figure.shot img { display:block; width:100%; height:5.6rem;
  object-fit:contain; background:var(--band); }
figure.shot figcaption { padding:.3em .45em .45em; font-size:.7rem;
  line-height:1.35; color:var(--muted); }
figure.shot figcaption b { display:block; color:var(--ink); font-size:.74rem; }

.more a { display:inline-block; margin:.15em .5em .15em 0; font-size:.88rem; }
.more .dead { color:var(--warnline); font-size:.82rem; }
.more .settled { color:var(--muted); font-size:.82rem; margin-right:.5em; }

section.maps figure { margin:1em 0; border:1px solid var(--rule);
  border-radius:8px; overflow:hidden; scroll-margin-top:5.5rem; }
section.maps img { display:block; width:100%; }
section.maps figcaption { padding:.5em .8em; font-size:.85rem;
  color:var(--muted); background:var(--band); }
"""


def _sort_key(t):
    """When a task happens, for ordering, whatever shape its date is in."""
    if t.get("date"):
        return _date(t["date"])
    if t.get("window"):
        return _date(t["window"][0])
    return _date(t["repeat"]["from"])


def _photo_figure(pic, root, link_images):
    """One plant photograph with the credit it has to travel with."""
    e = html.escape
    src = pic.get("web") or pic["image"]
    return (f'<figure class="shot">'
            f'<a href="{e(pic.get("commons") or "#")}">'
            f'<img src="{e(src)}" alt="{e(pic["binomial"])}" loading="lazy">'
            f'</a><figcaption><b>{e(pic.get("name") or pic["binomial"])}</b>'
            f'<i>{e(pic["binomial"])}</i><br>{e(pic.get("artist") or "")} '
            f'&middot; {e(pic.get("licence") or "")}</figcaption></figure>')


def _task_article(t, root, maps, link_images):
    """One job, in full, with every deeper explanation as a link.

    Nothing in here reproduces prose that lives in a document. The technique
    for sowing a carrot is in SOWING-CALENDAR.md and stays there; this carries
    the link to the exact heading. Two copies of a method is one copy nobody
    can trust, and the reader cannot tell which they are holding.
    """
    e = html.escape
    rows = []
    w = t.get("where") or {}

    if t.get("placements"):
        cells = ""
        for p in t["placements"]:
            spot = p.get("at") or (", ".join(p.get("squares") or []) or "&mdash;")
            if p.get("bed") and p.get("at"):
                spot = f"{p['bed']} {p['at']}"
            elif p.get("bed"):
                spot = f"{p['bed']} {spot}"
            named = "".join(
                f' <i>{e(n["binomials"][0])}</i>' if n["binomials"] else ""
                for n in p["named"][:1])
            flag = ('<span class="miss"> &mdash; names no plant in the '
                    'design</span>') if p["unmatched"] and p["positional"] \
                else ""
            cells += (f'<tr><td class="spot">{spot}</td>'
                      f'<td class="sp">{e(p["text"])}{named}{flag}</td></tr>')
        rows.append(("Goes where", f'<table class="place">{cells}</table>'))
    elif where_of(t):
        rows.append(("Where", e(where_of(t))))
    if w.get("note"):
        rows.append(("Note", e(w["note"])))

    if t.get("photos"):
        rows.append(("What they look like",
                     '<div class="shots">'
                     + "".join(_photo_figure(p, root, link_images)
                               for p in t["photos"]) + "</div>"))

    if t.get("how"):
        steps = "".join(f"<li>{e(str(h))}</li>" for h in t["how"])
        rows.append(("How", f"<ol>{steps}</ol>"))

    g = t.get("gate") or {}
    if g.get("below_f"):
        rows.append(("Gate", f'<span class="gate">Only if the soil is under '
                             f'{g["below_f"]} &deg;F</span>'))
    elif g.get("depends"):
        rows.append(("Gate", f'<span class="gate">Depends on '
                             f'{e(g["depends"])}'
                             + (f' &mdash; {e(g["unless"])}'
                                if g.get("unless") else "") + "</span>"))
    if g.get("early"):
        rows.append(("Earlier", e(g["early"])))
    for value, lbl in ((g.get("miss"), "If the window closes"),
                       (t.get("miss"), "If it slips")):
        if value:
            rows.append((lbl, e(value)))
    for key, lbl in (("why", "Why"), ("warn", "Watch out"), ("then", "Then"),
                     ("decides", "Decides"), ("answer", "Answer")):
        if t.get(key):
            rows.append((lbl, e(str(t[key]))))
    if t.get("date_inferred") and t.get("date_note"):
        rows.append(("Where the date came from", e(t["date_note"])))

    more = []
    if w.get("map") and w["map"] in maps:
        more.append(f'<a href="#{maps[w["map"]]}">the bed map</a>')
    for l in t.get("links", []):
        if l["url"]:
            more.append(f'<a href="{e(l["url"])}">{e(l["label"])}</a>')
        elif l["kind"] == "doubt":
            more.append(f'<span class="settled">{e(l["label"])}</span>')
        else:
            more.append(f'<span class="dead">{e(l["error"] or l["ref"])}</span>')
    if more:
        rows.append(("Read more", '<span class="more">'
                     + " ".join(more) + "</span>"))

    badges = f'<span class="badge kind">{e(t["kind"])}</span>'
    if t.get("critical"):
        badges += '<span class="badge crit">cannot slip</span>'

    body = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    cls = "task" + (" crit" if t.get("critical") else "")
    return (f'<article class="{cls}" id="{e(t["id"])}">'
            f'<h3>{chrome.tick(t)}{e(t["title"])}'
            f'<a class="self" href="#{e(t["id"])}">{e(t["id"])}</a></h3>'
            f'<div class="meta">{e(t["when"])}'
            + (f' &middot; {hours(t["minutes"])}' if t.get("minutes") else "")
            + f" {badges}</div>"
            + (f'<dl class="f">{body}</dl>' if body else "")
            + "</article>")


def render_tasks_html(slug, data=None, link_images=False):
    """Every job on one page, each at its own anchor, each linking out.

    One page rather than one per task, because every other screen wants to
    point at a job and a single file with `#t016` in it is the cheapest thing
    that can be pointed at — from the week, from the calendar, from the call
    card, and later from an app that keeps the same ids as its routes.
    """
    from . import bundle, buildhtml, plantphotos

    e = html.escape
    data = data or bundle.build(slug)
    root = yards.yard_dir(slug)
    tasks = sorted(data["tasks"], key=_sort_key)

    # Each distinct bed map once, at its own anchor, with every task that uses
    # it linking here. Twenty-seven tasks share four maps.
    maps, figs = {}, []
    for t in tasks:
        rel = (t.get("where") or {}).get("map")
        if not rel or rel in maps:
            continue
        small = plantphotos.web_copy(root, rel) or rel
        anchor = "map-" + links.slug(os.path.splitext(os.path.basename(rel))[0])
        maps[rel] = anchor
        users = [x["id"] for x in tasks
                 if (x.get("where") or {}).get("map") == rel]
        figs.append(f'<figure id="{anchor}"><img src="{e(small)}" '
                    f'alt="{e(rel)}" loading="lazy">'
                    f'<figcaption><code>{e(rel)}</code> &middot; used by '
                    f'{len(users)} job{"s" if len(users) != 1 else ""}'
                    f'</figcaption></figure>')

    months, order = {}, []
    for t in tasks:
        d = _sort_key(t)
        key = (d.year, d.month)
        if key not in months:
            months[key] = []
            order.append(key)
        months[key].append(t)

    jump = "".join(
        f'<a href="#m{y}-{m:02d}">{ABBR[m]} {str(y)[2:]} '
        f'<b>{len(months[(y, m)])}</b></a>' for y, m in order)

    body = ""
    for y, m in order:
        body += (f'<h2 class="month" id="m{y}-{m:02d}">{MONTHS[m]} {y}'
                 f' <span class="badge">{len(months[(y, m)])} jobs</span></h2>')
        body += "".join(_task_article(t, root, maps, link_images)
                        for t in months[(y, m)])

    mapsec = ""
    if figs:
        mapsec = ('<h2 id="maps">The bed maps</h2><p class="sub">Each one '
                  'once. Every job above that needs a map links down to it '
                  'rather than carrying its own copy.</p>'
                  '<section class="maps">' + "".join(figs) + "</section>")

    dead = sum(1 for t in tasks for l in t["links"] if l["error"])
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(data['yard']['name'])} &mdash; every job</title>
<style>{chrome.BASE_CSS}{chrome.NAV_CSS}{chrome.TICKS_CSS}{TASKS_CSS}</style>
</head>
<body>
{chrome.nav(root, 'TASKS.html', data['yard']['name'])}
<div class="wrap">
<h1>Every job, in full</h1>
<p class="sub">{len(tasks)} jobs, in the order they happen. Each one is at its
own address, so the week and the calendar link straight to it.</p>
{chrome.tools()}
<div class="jump">{jump}</div>
{body}
{mapsec}
<footer>
<p>Built from <code>tasks.json</code> and <code>design.json</code> on
{data['built']} by <code>python3 -m lib.site {e(slug)}</code>.</p>
<p>Nothing here repeats prose that lives in a document. &ldquo;Read more&rdquo;
goes to the section that explains the job, so correcting it there corrects it
everywhere.{f' {dead} reference(s) currently resolve to nothing and say so '
             f'in place.' if dead else ''}</p>
<p>Plant photographs are from Wikimedia Commons under the licence printed with
each. A species with no verified photograph shows none, because a picture of
the wrong plant is worse than no picture.</p>
<p>Ticks are kept in this browser only. <code>Copy the done list</code> hands
them back as text, and <code>python3 -m lib.week {e(slug)} --sync &lt;file&gt;
</code> folds them into <code>tasks.json</code>, which is the record.</p>
</footer>
</div>
<script>{chrome.ticks_js(slug)}</script>
</body>
</html>
"""
    if not link_images:
        page = buildhtml.embed_images(page, root)
    return page


# ----------------------------------------------------------- the whole run

CALENDAR_CSS = """
table.year { border-collapse:collapse; width:100%; font-size:.9rem;
  margin:.5em 0 2em; }
table.year th { position:sticky; top:2.6rem; z-index:5; background:var(--accent);
  color:#fff; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:.5em .6em; font-weight:600; }
table.year td { padding:.5em .6em; border-bottom:1px solid var(--rule);
  vertical-align:top; }
table.year tr.past { color:var(--muted); background:#fcfcfc; }
table.year tr.past a { color:var(--muted); }
table.year tr.now td { background:#fff8e1; }
table.year tr.now td.wk { border-left:4px solid var(--warnline); }
table.year tr.quiet td { color:var(--muted); }
table.year tr.blackout td.wk { border-left:4px solid var(--crit); }
td.wk { white-space:nowrap; width:9.5rem; border-left:4px solid transparent; }
td.wk b { display:block; font-size:.95rem; }
td.wk b a { text-decoration:none; }
td.wk b a:hover { text-decoration:underline; }
td.wk span { color:var(--muted); font-size:.76rem; }
td.wk em { display:none; font-style:normal; color:var(--warnline);
  font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }
table.year tr.now td.wk em { display:block; }
table.year tr.click { cursor:pointer; }
td.hrs { white-space:nowrap; width:5.5rem; font-variant-numeric:tabular-nums; }
td.hrs b { font-size:1rem; }
td.hrs span { display:block; color:var(--muted); font-size:.72rem; }
td.work a { text-decoration:none; }
td.work a:hover { text-decoration:underline; }
td.work .crit { color:var(--crit); font-weight:600; }
td.work .sep { color:var(--rule); }
td.buy { width:12rem; font-size:.84rem; color:var(--muted); }
td.buy b { color:var(--ink); font-weight:600; }
.mrow td { background:var(--band); font-weight:650; font-size:.82rem;
  text-transform:uppercase; letter-spacing:.06em; color:var(--accent);
  border-bottom:2px solid var(--accent); }
.legend { color:var(--muted); font-size:.82rem; margin:.4em 0 1.2em; }
@media (max-width:640px) {
  table.year, table.year tbody, table.year tr, table.year td { display:block;
    width:auto; }
  table.year thead { display:none; }
  table.year tr { border-bottom:1px solid var(--rule); padding:.5em 0; }
  table.year td { border:0; padding:.15em .4em; }
  td.wk { border-left:4px solid transparent; }
  table.year tr.now td.wk, table.year tr.blackout td.wk { border-left-width:4px; }
  td.hrs { width:auto; } td.buy { width:auto; } }
"""


#: The year view, corrected by the device clock, and made a way in.
#:
#: Two jobs and no third. It moves the `now` mark onto the week the device
#: says it is, because a build from three weeks ago marks the wrong row; and
#: it makes the whole row open its week, because the row is the map and the
#: week page is the detail. It writes no text.
CALENDAR_JS = """
(function () {
  var rows = [].slice.call(document.querySelectorAll('tr[data-monday]'));
  if (!rows.length) return;
  var here = yard.mondayOf(yard.today());
  var was = document.getElementById('now');
  if (was) was.removeAttribute('id');
  rows.forEach(function (r) {
    var mon = r.getAttribute('data-monday');
    r.classList.toggle('now', mon === here);
    r.classList.toggle('past', mon < here);
    if (mon === here) r.id = 'now';
    r.addEventListener('click', function (ev) {
      if (ev.target.closest && ev.target.closest('a')) return;
      location.href = 'WEEK.html#' + r.getAttribute('data-week');
    });
  });
})();
"""


def render_calendar_html(slug, data=None, today=None):
    """Every week from the first job to the last, one line each.

    The document this replaces put every task's full detail inline, week after
    week, and ran to nine thousand words. Somebody trying to find out what
    November looks like had to read October to get there. So a row here says
    only what a week is: how long it takes, what in it cannot slip, what has
    to be bought. The detail is one click away in TASKS.html, which is the
    only place it exists.
    """
    from . import bundle

    e = html.escape
    data = data or bundle.build(slug)
    tasks = load(slug)
    root = yards.yard_dir(slug)
    today = today or datetime.date.today()
    this = monday_of(today)
    cond = yards.load_conditions(slug) or {}
    first, last = span_of(tasks)

    rows, month = [], None
    weeks = totalmin = 0
    mon = first
    while mon <= last:
        sun = mon + datetime.timedelta(days=6)
        grid, loose = week_grid(tasks, mon)
        buys = buys_for(tasks, mon)
        s = week_shape(grid, loose, buys)
        blocks = week_blackout(tasks, cond, mon)
        weeks += 1
        totalmin += s["fixed"]

        if (mon.year, mon.month) != month:
            month = (mon.year, mon.month)
            rows.append(f'<tr class="mrow"><td colspan="4">'
                        f'{MONTHS[mon.month]} {mon.year}</td></tr>')

        jobs = []
        seen = set()
        for d in sorted(grid):
            for t, standing in grid[d]:
                if t["id"] in seen or standing:
                    continue
                seen.add(t["id"])
                cls = ' class="crit"' if t.get("critical") else ""
                jobs.append(f'<a href="TASKS.html#{e(t["id"])}"{cls}>'
                            f'{e(t["title"])}</a>')
        for t in loose:
            if t["id"] not in seen:
                seen.add(t["id"])
                jobs.append(f'<a href="TASKS.html#{e(t["id"])}">'
                            f'{e(t["title"])}</a>')
        standing = {t["id"] for items in grid.values() for t, st in items if st}

        work = '<span class="sep"> &middot; </span>'.join(jobs) \
            or '<span class="sep">&mdash;</span>'
        if standing:
            work += (f'<span class="sep"> &middot; </span>'
                     f'<span class="sep">{len(standing)} standing job'
                     f'{"s" if len(standing) > 1 else ""}</span>')

        buycell = "".join(
            f'<div><b>{e(b["item"][:38])}</b> by '
            f'{_date(b["by"]):%-d %b}</div>' for b in buys[:3])
        if len(buys) > 3:
            buycell += f"<div>and {len(buys) - 3} more</div>"

        cls = []
        if mon == this:
            cls.append("now")
        elif mon < this:
            cls.append("past")
        if not jobs and not standing and not buys:
            cls.append("quiet")
        if blocks:
            cls.append("blackout")

        hrs = hours(s["fixed"]) if s["fixed"] else "&mdash;"
        note = ("no-build week" if blocks else
                f'{len(seen)} job{"s" if len(seen) != 1 else ""}'
                if seen else "")
        # The row is the map and the week page is the detail, so the row is
        # the way into it. `now` is stamped for the build day and re-applied
        # by the script from the device clock, which is what keeps it true.
        wid = week_id(mon)
        cls.append("click")
        rows.append(
            f'<tr class="{" ".join(cls)}"'
            + (' id="now"' if mon == this else "")
            + f' data-week="{wid}" data-monday="{mon.isoformat()}">'
            f'<td class="wk"><b><a href="WEEK.html#{wid}">{mon:%-d %b}</a></b>'
            f'<em>This week</em>'
            f'<span>{mon:%-d %b} &ndash; {sun:%-d %b}</span></td>'
            f'<td class="hrs"><b>{hrs}</b><span>{note}</span></td>'
            f'<td class="work">{work}</td>'
            f'<td class="buy">{buycell}</td></tr>')
        mon += datetime.timedelta(weeks=1)

    done = sum(1 for t in data["tasks"] if t.get("done"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(data['yard']['name'])} &mdash; the calendar</title>
<style>{chrome.BASE_CSS}{chrome.NAV_CSS}{chrome.STALE_CSS}{CALENDAR_CSS}</style>
</head>
<body>
{chrome.nav(root, 'CALENDAR.html', data['yard']['name'])}
<div class="wrap">
{chrome.stale_banner(slug, data['built'])}
<h1>{first:%B %Y} to {last:%B %Y}</h1>
<p class="sub">{weeks} weeks, {len(data['tasks'])} jobs, {hours(totalmin)} of
dated work. {done} done so far.</p>
<p class="legend">A red edge is a no-build week. A job in red cannot slip.
Every job name goes straight to the full instructions, and every week row
opens that week in <a href="WEEK.html">this week</a>.
<a href="#now">Go to the current week</a>.</p>
<table class="year">
<thead><tr><th>Week</th><th>Work</th><th>What happens</th>
<th>To buy</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
<footer>
<p>Built from <code>tasks.json</code> on {data['built']} by
<code>python3 -m lib.site {e(slug)}</code>. A row says what a week is; the
instructions live once, in <a href="TASKS.html">every job, in full</a>.</p>
<p>The year view is the map and the week view is the detail. A week is
addressed by its Monday, as <code>WEEK.html#w2026-09-14</code>.</p>
</footer>
</div>
{chrome.dates_js()}
<script>
{CALENDAR_JS}
{chrome.STALE_JS}
</script>
</body>
</html>
"""


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

# What the publish step above turns "- [x] " into, because a .docx checkbox
# cannot carry a ticked state through the Docs import: doneness is encoded as
# text and the box goes out empty. Reading it back therefore has to undo that,
# and both halves matter. The prefix has to come off before the title is taken
# or every done task keys on the word DONE and they collide with each other,
# and the prefix has to count as ticked or a task that is finished comes back
# through UNTICKED and gets marked undone — which silently erases the record of
# what was actually done, the one thing this file exists to keep.
DONE_MARK = re.compile(r"^DONE\s*·\s*")


def _title_of(line):
    """The bold title out of a rendered checkbox line, however Docs mangled it.

    The markdown export backslash-escapes punctuation, so a title with " - " in
    it comes back as " \\- " and matches nothing. Unescaping first is what makes
    the round trip work on the eight tasks that have a dash in the name.

    And striking a line out in the Doc — which is how a person marks a job done
    by hand, on top of ticking it — exports as `~~...~~` around the whole item.
    No task title contains a tilde, so dropping every `~~` is safe, and it has
    to happen before the title is read or the marker rides along on the front of
    it and the item is reported as drift instead of as done.
    """
    line = re.sub(r"\\([-_*\[\]()#.!`~])", r"\1", line.strip())
    line = line.replace("~~", "").strip()
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
                body = re.sub(r"\\([-_*\[\]()#.!`~])", r"\1", m.group(1).strip())
                # Before DONE_MARK, not after: a struck-out done task exports as
                # "~~DONE · **title**~~" and the marker never matches behind the
                # tildes, so the task keys on the word DONE and collides.
                body = body.replace("~~", "").strip()
                marked = DONE_MARK.match(body)
                if marked:
                    body, value = body[marked.end():], True
                state[_title_of(body)] = value
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


def _report_links(findings, slug):
    """What `--links` found, in the two groups a person fixes differently."""
    if not findings:
        print("  every task reference resolves, and every plant a task "
              "places is in design.json")
        return
    refs = [f for f in findings if f["kind"] == "reference"]
    beds = [f for f in findings if f["kind"] == "placement"]
    if refs:
        print(f"\n  {len(refs)} reference(s) that point nowhere. A task with "
              f"one of these\n  loses its explanation on every page that "
              f"shows it:\n")
        for f in refs:
            print(f"      {f['message']}")
        print(f"\n      Write it as FILE.md#anchor. "
              f"`python3 -m lib.links {slug}` lists every anchor.")
    if beds:
        print(f"\n  {len(beds)} placement(s) naming a plant design.json does "
              f"not hold. The\n  prose and the design disagree about what "
              f"goes in the ground:\n")
        for f in beds:
            print(f"      {f['message']}")
        print(f"\n      `python3 -m lib.plants {slug}` lists every name the "
              f"design knows.")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--week", help="any date in the week you want")
    ap.add_argument("--calendar", action="store_true", help="write CALENDAR.md")
    ap.add_argument("--html", action="store_true",
                    help="write WEEK.html — one week, seven days, detail on a click")
    ap.add_argument("--shop", nargs="?", type=int, const=3, default=None,
                    metavar="WEEKS", help="buying due in the next N weeks")
    ap.add_argument("--check", action="store_true",
                    help="where tasks.json and the plan documents disagree")
    ap.add_argument("--links", action="store_true",
                    help="references that point nowhere, and placements "
                         "naming a plant the design does not hold")
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

    if args.links:
        _report_links(link_check(args.slug), args.slug)
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
        _report_links(link_check(args.slug), args.slug)
        raise SystemExit(1 if problems else 0)

    if args.restamp:
        restamp(args.slug)
        return

    if args.html:
        mon = monday_of(_date(args.week) if args.week else datetime.date.today())
        path = yards.write_text(args.slug, "WEEK.html",
                                render_week_html(args.slug, mon))
        print(f"wrote {path}")
        # The page is a view of tasks.json, so a disagreement with the plan
        # documents does not make it wrong. It does make it incomplete, and
        # saying so here is cheaper than finding out on a Saturday.
        problems = check(args.slug)
        if problems:
            print(f"  {len(problems)} disagreement"
                  f"{'s' if len(problems) > 1 else ''} with the plan "
                  f"documents: {stamp(problems)}. `--check` says what to do.")
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
