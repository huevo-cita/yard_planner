#!/usr/bin/env python3
"""Every watering job of a yard, as one morning and one evening calendar event a day.

    python3 -m lib.watercal <slug>                the next 7 days, as the events read
    python3 -m lib.watercal <slug> --days 14
    python3 -m lib.watercal <slug> --coverage     is every plant in the ground watered
    python3 -m lib.watercal <slug> --lint         water tasks with no `when` or `dose`
    python3 -m lib.watercal <slug> --init         write water-calendar.json with defaults
    python3 -m lib.watercal <slug> --plan         -> water-calendar.plan.json
    python3 -m lib.watercal <slug> --record <results.json>
    python3 -m lib.watercal <slug> --ics          -> WATER.ics

Why this module exists
----------------------
A planted yard has many watering jobs at the same time. Each one has its own
cadence, its own amount and its own last day. `tasks.json` holds them, and the
week page shows them, but a person in the garden at 07:30 wants one note that
says what to water now, how much, and what stops or starts today.

So this module reads every watering job and writes one event for each slot of
each day: the morning and the evening. The description names the plants, the
total amount, the skip rules and the change to the next stage. It also says
what the drip does that day, so that the person knows what is automatic.

The coverage check
------------------
An event list shows the jobs that exist. It cannot show a plant that no job
waters. So `--coverage` takes every plant in the ground and asks which regime
waters it on each day of the window:

    drip            a drip zone that runs in that period reaches its bed
    hand            a water task reaches the plant, inside that task's cadence
    exempt          `design.json` `water_exempt` says why nothing waters it

Two stricter rules apply on top. A new planting needs hand water at the
establishment intervals, because a short drip run does not wet a new root ball.
A sown square needs water every day until the seed is up. A repeat whose note
describes a change of cadence that its own fields do not hold is a finding too,
because the calendar can only show the fields.

The sync
--------
The Google Calendar tools are reachable only by the agent, through an MCP
server. So `--plan` writes the create, update and delete operations to a file,
the agent runs each one, and `--record` writes the returned event ids into the
ledger in `water-calendar.json`. A second `--plan` with nothing changed gives no
operations. An event in the past is never changed or deleted.

`--plan` refuses while `lib.week --check` fails, while the coverage check has a
finding, or while a water task has no `dose`. `--force` continues and puts the
reason at the top of every description.

Not a gated job: nothing here runs the sun model or costs money.
"""
import argparse
import datetime
import hashlib
import json
import os
import re

from . import week, yards

FILE = "water-calendar.json"
PLAN_FILE = "water-calendar.plan.json"
ICS_FILE = "WATER.ics"

SLOTS = ("morning", "evening")
SLOT_SHORT = {"morning": "AM", "evening": "PM"}

#: The defaults for a yard with no `water-calendar.json`. The establishment
#: stages are (last day of the stage, the longest gap in days between hand
#: waterings). They follow the common nursery rule: every second day for two
#: weeks, every three or four days to day 35, weekly to day 60.
DEFAULTS = {
    "account": None,
    "namespace": None,
    "calendar_name": "Garden - watering",
    "calendar_id": None,
    "timezone": None,
    "slots": {"morning": "07:30", "evening": "18:00"},
    "horizon_days": 42,
    "min_minutes": 15,
    "establishment": [[14, 2], [35, 4], [60, 7]],
    "germinate_days": 7,
    "events": {},
}

#: Which job kinds go on the calendar without a `dose`. Any other kind goes on
#: it when it carries a `dose`, because "weed and water the empty squares" is a
#: watering job filed under prep.
KINDS = ("water", "timer")

#: The units that a dose can use, in gallons.
UNITS = {"cup": 1 / 16, "cups": 1 / 16, "quart": 0.25, "quarts": 0.25,
         "qt": 0.25, "gal": 1.0, "gallon": 1.0, "gallons": 1.0}

#: A note that says the cadence changes part of the way through. The repeat
#: fields hold one cadence, so the calendar shows that one and drops the rest.
TAPER = re.compile(
    r"\b(then|from day|to day|after day)\b[^.;]*\b(every|weekly|daily|once a)\b"
    r"|\bevery\b[^.;]*\b(to|until) day \d+", re.I)

_MARK_TOL = week.MAP_TOLERANCE_FT


# ------------------------------------------------------------------ settings

def settings(slug):
    """The yard's `water-calendar.json` over the defaults."""
    rec = yards.load(slug, FILE) or {}
    out = json.loads(json.dumps(DEFAULTS))
    for k, v in rec.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "events":
            out[k].update(v)
        else:
            out[k] = v
    if not out.get("timezone") or out["timezone"] == "UTC":
        site = yards.load_site(slug) or {}
        addr = site.get("address") or {}
        tz = addr.get("timezone") or site.get("timezone")
        if not tz and addr.get("lon") is not None:
            from . import solar
            tz = solar.guess_timezone(addr["lon"])
        out["timezone"] = tz or "UTC"
    return out


def save_settings(slug, s):
    keep = {k: v for k, v in s.items() if k != "yard"}
    yards.save(slug, FILE, keep)


def init(slug, account=None, namespace=None):
    """Write `water-calendar.json` with the defaults, keeping any value set."""
    s = settings(slug)
    if account:
        s["account"] = account
    if namespace:
        s["namespace"] = namespace
    save_settings(slug, s)
    return yards.path(slug, FILE)


# ------------------------------------------------------------------ the jobs

def is_watering(t):
    return t.get("kind") in KINDS or bool(t.get("dose"))


def jobs(data):
    """Every watering job that has a day, and is not done."""
    out = []
    for t in (data or {}).get("tasks", []):
        if not is_watering(t) or t.get("done"):
            continue
        if not t.get("repeat") and not t.get("date"):
            continue
        out.append(t)
    return out


def _text(t):
    r = t.get("repeat") or {}
    return " ".join([t.get("title", ""), " ".join(t.get("how") or []),
                     r.get("note", "")]).lower()


def slots_of(t):
    """The slots a job asks for: `when` if the task says, else read from prose."""
    w = (t.get("when") or "").lower()
    if w:
        return [s for s in SLOTS if s in w] or ["morning"]
    text = _text(t)
    am = bool(re.search(r"\bmorning\b|\bpre-dawn\b", text))
    pm = bool(re.search(r"\bevening\b", text))
    if pm and am:
        return list(SLOTS)
    return ["evening"] if pm else ["morning"]


def step_of(t):
    r = t.get("repeat")
    if not r:
        return 1
    return week._step_days(r.get("every")) or 1


def span_of(t):
    r = t.get("repeat")
    if r:
        return week._date(r["from"]), week._date(r["to"])
    d = week._date(t["date"])
    return d, d


def occurs(t, d):
    return d in week._occurrences(t, d, d)


def cadence(t):
    return week._cadence(t) or "once"


# --------------------------------------------------------------- the plants

def bed_key(name):
    """`bed_g01`, `g01`, `raised-bed` and `Raised bed` as one key each."""
    toks = [x for x in re.split(r"[-_\s]+", (name or "").strip().lower())
            if x and x != "bed"]
    return "-".join(toks)


def _bed_rx(key):
    word = re.escape(key.replace("-", " ")).replace(r"\ ", r"[-_\s]+")
    return re.compile(r"\b" + word.rstrip("s") + r"s?\b", re.I)


def beds_in(text, keys):
    """Every known bed that a free-form `where.bed` names."""
    return {k for k in keys if _bed_rx(k).search(text or "")}


def short_name(name):
    return re.split(r"\s+[-\u2013\u2014]\s+|\s*\(|\n", name or "")[0].strip()


def _name_rx(name):
    base = re.escape(short_name(name).lower())
    return re.compile(r"\b" + base + r"(?:e?s)?\b", re.I)


def names_hit(name, text):
    return bool(short_name(name)) and bool(_name_rx(name).search(text or ""))


def grid_squares(grid):
    """`{square: label}` for a grid bed in `design.json` `layout.beds`.

    A square is named by its row, counted from the `top_label` end, and its
    column. The first column is `W1`, the last is `E<width>`, and the others
    are their number. A grid that names its columns another way carries
    `columns`, a list of names from left to right.
    """
    width, length = int(grid.get("width") or 0), int(grid.get("length") or 0)
    cols = grid.get("columns") or [
        "W1" if i == 0 else f"E{width}" if i == width - 1 else str(i + 1)
        for i in range(width)]
    out = {}
    for c in grid.get("cells") or []:
        label = (c.get("label") or "").split("\n")[0].strip()
        for dx in range(int(c.get("w") or 1)):
            for dy in range(int(c.get("h") or 1)):
                x, y = int(c["x"]) + dx, int(c["y"]) + dy
                if 0 <= x < width and 0 <= y < length:
                    out[f"{length - y}-{cols[x]}"] = label
    return out


def _task_squares(t):
    w = t.get("where") or {}
    out = list(w.get("squares") or [])
    for p in w.get("placements") or []:
        out += p.get("squares") or []
    return out


def _exempt_rules(design):
    return [r for r in (design or {}).get("water_exempt") or []]


def _exempt_for(item, rules):
    for r in rules:
        if r.get("bed") and bed_key(r["bed"]) != item["bed"]:
            continue
        if r.get("name") and not names_hit(r["name"], item["name"]) \
                and not names_hit(item["name"], r["name"]):
            continue
        return r
    return None


def inventory(slug, data=None):
    """Every plant the yard records, with the day it went into the ground.

    Four sources, each the record of one kind of planting:

        map         a circle in `scheme.json`, the record of a border bed
        square      a square of a grid bed in `design.json` `layout.beds`
        record      a `design.json` plant in a zone that has no map
        container   a pot in `design.json` `containers`
        sown        a seed placement on a border bed that the map does not hold

    `planted` is the date of the plant, transplant or sow task that put it in
    the ground. `existing` means it was there before the plan.
    """
    from . import scheme

    data = data if data is not None else week.load(slug) or {}
    design = yards.load(slug, "design.json") or {}
    tasks = data.get("tasks", [])
    planting = [t for t in tasks if t.get("kind") in ("plant", "transplant", "sow")
                and (t.get("date") or t.get("window"))]
    rules = _exempt_rules(design)
    existing = [p for p in design.get("plants", []) if p.get("existing")]

    def is_existing(name, botanical, bed):
        for p in existing:
            if bed_key(p.get("zone")) != bed:
                continue
            if botanical and p.get("botanical") and \
                    p["botanical"].split()[0:2] == botanical.split()[0:2]:
                return True
            if names_hit(short_name(name), p["name"]) or \
                    names_hit(short_name(p["name"]), name):
                return True
        return False

    def first_day(t):
        return week._date(t["date"]) if t.get("date") else week._date(t["window"][0])

    items, mapped = [], set()
    plan_map = scheme.load(slug) or {}
    for b in plan_map.get("beds") or []:
        bed = bed_key(b["id"])
        mapped.add(bed)
        for c in b.get("plants") or []:
            if c.get("feature") or not c.get("botanical"):
                continue
            it = {"id": c.get("id") or f"{bed}@{c.get('x')}", "kind": "map",
                  "bed": bed, "name": c["name"], "x": c.get("x"),
                  "botanical": c.get("botanical"),
                  "existing": is_existing(c["name"], c.get("botanical"), bed),
                  "planted": None, "planted_by": None, "sown": False}
            for t in sorted(planting, key=first_day):
                w = t.get("where") or {}
                hit = False
                for p in w.get("placements") or []:
                    if bed_key(p.get("bed")) != bed:
                        continue
                    if not names_hit(c["name"], p.get("plant", "")):
                        continue
                    if re.search(r"\bexisting\b", p.get("plant", ""), re.I):
                        continue
                    marks = week._marks(p.get("at"))
                    if marks and not any(abs(m - (c.get("x") or -99)) <=
                                         _MARK_TOL + 1e-9 for m in marks):
                        continue
                    hit = True
                    break
                if not w.get("placements") and bed in beds_in(
                        w.get("bed", ""), {bed}) and names_hit(c["name"],
                                                              t.get("title", "")):
                    hit = True
                if hit:
                    it["planted"], it["planted_by"] = first_day(t), t["id"]
                    it["sown"] = t.get("kind") == "sow"
                    it["establish"] = t.get("establishment", True)
                    break
            items.append(it)

    for g in (design.get("layout") or {}).get("beds") or []:
        if g.get("type") != "grid":
            continue
        bed = bed_key(g.get("name"))
        mapped.add(bed)
        for sq, label in grid_squares(g).items():
            it = {"id": f"{bed}:{sq}", "kind": "square", "bed": bed,
                  "square": sq, "name": label, "existing": False,
                  "planted": None, "planted_by": None, "sown": False,
                  "plantings": []}
            for t in sorted(planting, key=first_day):
                if sq in _task_squares(t):
                    germ = t.get("germinate_days")
                    for p in (t.get("where") or {}).get("placements") or []:
                        if sq in (p.get("squares") or []) and \
                                p.get("germinate_days") is not None:
                            germ = p["germinate_days"]
                    it["plantings"].append({"task": t["id"], "date": first_day(t),
                                            "sow": t.get("kind") == "sow",
                                            "germinate_days": germ,
                                            "establish": t.get("establishment",
                                                               True)})
            if it["plantings"]:
                first = it["plantings"][0]
                it["planted"], it["planted_by"] = first["date"], first["task"]
                it["sown"] = first["sow"]
            items.append(it)

    zones = {}
    for p in design.get("plants", []):
        bed = bed_key(p.get("zone"))
        if bed and bed not in mapped:
            zones.setdefault(bed, []).append(p)
    for bed, recs in sorted(zones.items()):
        for p in recs:
            items.append({"id": f"{bed}:{short_name(p['name'])}", "kind": "record",
                          "bed": bed, "name": p["name"],
                          "existing": bool(p.get("existing")),
                          "planted": None, "planted_by": None, "sown": False})

    by_id = {t["id"]: t for t in tasks}
    for c in design.get("containers") or []:
        t = by_id.get(c.get("planted_by"))
        items.append({"id": f"pot:{c['id']}", "kind": "container",
                      "bed": "containers", "pot": c["id"], "name": c["name"],
                      "existing": bool(c.get("existing")),
                      "planted": first_day(t) if t else None,
                      "planted_by": c.get("planted_by"), "sown": False})

    for t in planting:
        if t.get("kind") != "sow":
            continue
        for p in (t.get("where") or {}).get("placements") or []:
            bed = bed_key(p.get("bed"))
            if not bed or bed not in {i["bed"] for i in items if i["kind"] == "map"}:
                continue
            if any(i["bed"] == bed and i["planted_by"] == t["id"] for i in items):
                continue
            items.append({"id": f"{bed}:sown:{t['id']}", "kind": "sown",
                          "bed": bed, "name": p.get("plant", ""), "existing": False,
                          "planted": first_day(t), "planted_by": t["id"],
                          "sown": True,
                          "germinate_days": p.get("germinate_days",
                                                  t.get("germinate_days"))})

    for it in items:
        it["exempt"] = _exempt_for(it, rules)
    return items


def in_ground(item, d):
    if item.get("existing"):
        return True
    return bool(item.get("planted")) and item["planted"] <= d


# ---------------------------------------------------------- what reaches what

def covers(t, item, keys):
    """Does this job water this plant. The most specific field decides."""
    w = t.get("where") or {}
    if w.get("planted_by"):
        return item.get("planted_by") in w["planted_by"] or any(
            p.get("task") in w["planted_by"] for p in item.get("plantings") or [])
    if w.get("containers"):
        return item.get("pot") in w["containers"]
    squares = _task_squares(t)
    if squares:
        if item.get("kind") != "square" or item["square"] not in squares:
            return False
        named = beds_in(w.get("bed", ""), keys)
        return not named or item["bed"] in named
    if item.get("kind") == "square" and not w.get("bed"):
        return False
    for p in w.get("placements") or []:
        if bed_key(p.get("bed")) == item["bed"] and \
                names_hit(item["name"], p.get("plant", "")):
            marks = week._marks(p.get("at"))
            if not marks or any(abs(m - (item.get("x") or -99)) <= _MARK_TOL
                                for m in marks):
                return True
    if w.get("placements"):
        return False
    named = beds_in(w.get("bed", ""), keys)
    hint = " ".join([t.get("title", ""), w.get("bed", ""), w.get("at", "") or "",
                     w.get("note", "") or ""])
    if named:
        if item["bed"] not in named:
            return False
        peers = [k for k in named]
        return _name_filter(item, hint, peers)
    if item.get("kind") == "container":
        return False
    return bool(w.get("bed")) and names_hit(item["name"], hint)


#: The plants of each bed, filled by `coverage` and `events` before `covers`
#: runs, so that a name filter can tell "names a plant of this bed" from
#: "names nothing in particular".
_BED_NAMES = {}


def _name_filter(item, hint, beds):
    names = [n for b in beds for n in _BED_NAMES.get(b, [])]
    hits = [n for n in names if names_hit(n, hint)]
    if not hits:
        return True
    return any(names_hit(h, item["name"]) or names_hit(item["name"], h)
               for h in hits)


def _prime(items):
    _BED_NAMES.clear()
    for it in items:
        _BED_NAMES.setdefault(it["bed"], []).append(it["name"])


# ------------------------------------------------------------------ the drip

def drip(slug):
    return (yards.load(slug, "irrigation.json") or {}).get("drip") or {}


def drip_period(block, d):
    """The drip period in effect on day d, or None."""
    until = block.get("until")
    if until and d > week._date(until):
        return None
    best = None
    for p in block.get("periods") or []:
        if week._date(p["from"]) <= d:
            if best is None or week._date(p["from"]) >= week._date(best["from"]):
                best = p
    return best


def _zone_sched(block, period, zone):
    z = (block.get("zones") or {}).get(zone) or {}
    src = z.get("valve") or zone
    return (period.get("zones") or {}).get(src) or {}


def drip_reaches(block, d):
    """The beds that a running drip zone reaches in the period of day d."""
    period = drip_period(block, d)
    if not period:
        return set()
    out = set()
    for zone, z in (block.get("zones") or {}).items():
        s = _zone_sched(block, period, zone)
        if s.get("weekdays") or (s.get("days_per_week") or 0) > 0:
            out.update(bed_key(b) for b in z.get("beds") or [])
    return out


def drip_line(block, d):
    """What the drip does on day d, in one paragraph."""
    period = drip_period(block, d)
    if not period:
        return ""
    day = week.DAYS[d.weekday()]
    runs, weekly = [], []
    groups = {}
    for zone, z in (block.get("zones") or {}).items():
        groups.setdefault(z.get("valve") or zone, []).append(
            z.get("label") or f"zone {zone}")
    for src, labels in groups.items():
        s = _zone_sched(block, period, src)
        z = (block.get("zones") or {}).get(src) or {}
        label = " + ".join(labels)
        if s.get("weekdays"):
            if day not in s["weekdays"]:
                continue
            cyc = s.get("cycles") or 1
            mins = s.get("min_per_cycle") or s.get("minutes")
            starts = s.get("start_times") or z.get("start_times") or []
            runs.append(f"{label} {cyc} x {mins} min"
                        + (f" from {', '.join(starts[:cyc])}" if starts else ""))
        elif (s.get("days_per_week") or 0) >= 7:
            runs.append(f"{label} {s.get('minutes')} min")
        elif s.get("days_per_week"):
            weekly.append(f"{label} runs {s['days_per_week']} days a week, "
                          f"{s.get('minutes')} min")
    bits = []
    if runs:
        bits.append("Drip today, automatic: " + "; ".join(runs) + ".")
    else:
        bits.append("No drip run on the fixed-day zones today.")
    if weekly:
        bits.append("; ".join(weekly) + ", on the days the timer picks.")
    return " ".join(bits)


def drip_check(slug, data=None):
    """Each drip period has to name its timer task, on the same day.

    Findings in the shape of `week.check`, so that a timer task moved in
    `tasks.json` and not in `irrigation.json` stops the calendar.
    """
    block = drip(slug)
    if not block:
        return []
    data = data if data is not None else week.load(slug) or {}
    by_id = {t["id"]: t for t in data.get("tasks", [])}
    out = []
    for p in block.get("periods") or []:
        tid = p.get("task")
        if not tid:
            continue
        t = by_id.get(tid)
        if not t:
            out.append({"kind": "drip", "subject": tid,
                        "message": f"irrigation.json drip period from {p['from']} "
                                   f"names {tid}, and tasks.json has no such task"})
            continue
        if t.get("date") and t["date"] != p["from"]:
            out.append({"kind": "drip", "subject": tid,
                        "message": f"{tid} \"{t['title']}\" is dated {t['date']}, "
                                   f"and the irrigation.json drip period it sets "
                                   f"starts {p['from']}. Move one to agree"})
        text = " ".join(t.get("how") or [])
        for zone, s in (p.get("zones") or {}).items():
            mins = s.get("min_per_cycle") or s.get("minutes")
            if mins and not re.search(rf"\b{mins}\s*min", text):
                out.append({"kind": "drip", "subject": tid,
                            "message": f"{tid} \"{t['title']}\" does not give the "
                                       f"{mins} min that irrigation.json sets for "
                                       f"zone {zone} from {p['from']}"})
    return out


# -------------------------------------------------------------- the coverage

def _ranges(days):
    """Consecutive dates as (first, last) pairs."""
    out = []
    for d in sorted(days):
        if out and (d - out[-1][1]).days == 1:
            out[-1][1] = d
        else:
            out.append([d, d])
    return [tuple(r) for r in out]


def _fmt_range(a, z):
    if a == z:
        return f"{a:%a %-d %b}"
    return f"{a:%-d %b}-{z:%-d %b}"


def _hand_days(item, hand, keys, lo, hi):
    """Every day in lo..hi on which a hand job reaches this plant."""
    days = set()
    for t in hand:
        if covers(t, item, keys):
            days.update(week._occurrences(t, lo, hi))
    return days


def _gaps(watered, lo, hi, allowed, anchor=None):
    """The unwatered days on which the interval `allowed(d)` has run out.

    An interval of 1 means every day, so a day with no water is a gap. An
    interval of 3 allows two dry days, and the third one is a gap.
    """
    prev = anchor
    for d in sorted(x for x in watered if x < lo):
        prev = d if prev is None or d > prev else prev
    bad = []
    d = lo
    while d <= hi:
        if d in watered:
            prev = d
        else:
            lim = allowed(d)
            if lim is not None and (prev is None or (d - prev).days >= lim):
                bad.append(d)
        d += datetime.timedelta(days=1)
    return bad


def coverage(slug, start=None, end=None, data=None):
    """Every plant in the ground that no regime waters, day by day."""
    data = data if data is not None else week.load(slug) or {}
    s = settings(slug)
    start = start or datetime.date.today()
    end = end or start + datetime.timedelta(days=s["horizon_days"] - 1)
    items = inventory(slug, data)
    _prime(items)
    keys = {i["bed"] for i in items}
    hand = [t for t in data.get("tasks", []) if is_watering(t)
            and t.get("kind") != "timer" and (t.get("repeat") or t.get("date"))]
    block = drip(slug)
    stages = s["establishment"]
    out = []
    back = start - datetime.timedelta(days=90)

    def finding(kind, item, days, why):
        for a, z in _ranges(days):
            out.append({"kind": kind, "item": item, "from": a, "to": z,
                        "why": why})

    for it in items:
        exempt = it.get("exempt")
        lo = start
        if not it.get("existing"):
            if not it.get("planted"):
                if it["kind"] in ("map", "record", "container"):
                    out.append({"kind": "untracked", "item": it, "from": None,
                                "to": None,
                                "why": "no task plants it, and design.json does "
                                       "not mark it existing"})
                continue
            if it["planted"] > end:
                continue
            lo = max(start, it["planted"])
        if exempt and not exempt.get("to") and not exempt.get("from"):
            continue
        watered = _hand_days(it, hand, keys, back, end)

        def exempt_on(d, ex=exempt):
            if not ex:
                return False
            a = week._date(ex["from"]) if ex.get("from") else datetime.date.min
            z = week._date(ex["to"]) if ex.get("to") else datetime.date.max
            return a <= d <= z

        def cadence_on(d, item=it):
            """The longest gap that a responsible hand job allows on day d."""
            best = None
            for t in hand:
                if not covers(t, item, keys):
                    continue
                a, z = span_of(t)
                step = step_of(t)
                lead = datetime.timedelta(days=step)
                if a - lead <= d <= z + lead:
                    best = max(best or 0, step)
            return best

        reach_cache = {}

        def on_drip(d, item=it):
            if d not in reach_cache:
                reach_cache[d] = drip_reaches(block, d)
            return item["bed"] in reach_cache[d]

        def allowed(d):
            if exempt_on(d) or on_drip(d):
                return None
            c = cadence_on(d)
            return c if c is not None else -1

        bad = _gaps(watered, lo, end, allowed, anchor=it.get("planted"))
        if bad:
            finding("uncovered", it, bad,
                    "no drip zone reaches it and no hand job is responsible")

        plantings = it.get("plantings") or (
            [{"task": it["planted_by"], "date": it["planted"], "sow": it["sown"],
              "germinate_days": it.get("germinate_days"),
              "establish": it.get("establish", True)}]
            if it.get("planted") else [])
        for i, p in enumerate(plantings):
            nxt = plantings[i + 1]["date"] if i + 1 < len(plantings) else None
            if p["sow"]:
                g = p.get("germinate_days")
                g = s["germinate_days"] if g is None else g
                a = max(start, p["date"] + datetime.timedelta(days=1))
                z = min(end, p["date"] + datetime.timedelta(days=g))
                if nxt:
                    z = min(z, nxt - datetime.timedelta(days=1))
                if g and a <= z:
                    bad = _gaps(watered, a, z,
                                lambda d: None if exempt_on(d) else 1,
                                anchor=p["date"])
                    finding("seed", it, bad,
                            f"sown {p['date']:%-d %b} by {p['task']}, and seed "
                            f"needs water every day for {g} days")
            elif not it.get("existing") and p.get("establish") is not False:
                stages = p["establish"] if isinstance(p.get("establish"),
                                                      list) else s["establishment"]
                last = stages[-1][0]
                a = max(start, p["date"])
                z = min(end, p["date"] + datetime.timedelta(days=last))
                if nxt:
                    z = min(z, nxt - datetime.timedelta(days=1))
                if a > z:
                    continue

                def stage(d, planted=p["date"]):
                    if exempt_on(d):
                        return None
                    age = (d - planted).days
                    for upto, gap in stages:
                        if age <= upto:
                            return gap
                    return None

                bad = _gaps(watered, a, z, stage, anchor=p["date"])
                finding("establishment", it, bad,
                        f"planted {p['date']:%-d %b} by {p['task']}; a new "
                        f"planting needs hand water every "
                        + ", then ".join(f"{g} days to day {u}"
                                         for u, g in stages))

    for t in data.get("tasks", []):
        if not is_watering(t) or t.get("done") or not t.get("repeat"):
            continue
        a, z = span_of(t)
        if z < start or a > end:
            continue
        note = (t["repeat"].get("note") or "")
        if TAPER.search(note) and not t["repeat"].get("taper_ok"):
            out.append({"kind": "taper", "task": t, "from": a, "to": z,
                        "why": f"the note says \"{note}\", and the repeat holds "
                               f"only \"{cadence(t)}\". Split it into one task "
                               f"for each stage"})
    return out


def coverage_lines(findings):
    """The findings, grouped so that one gap on twelve plants is one line."""
    groups = {}
    for f in findings:
        if f["kind"] == "taper":
            t = f["task"]
            groups[("taper", t["id"])] = [f"{t['id']} \"{t['title']}\": {f['why']}"]
            continue
        it = f["item"]
        where = it.get("square") or (f"ft {it['x']:g}" if it.get("x") is not None
                                     else it.get("pot") or "")
        when = _fmt_range(f["from"], f["to"]) if f["from"] else "every day"
        key = (f["kind"], it["bed"], when, f["why"])
        groups.setdefault(key, []).append(
            f"{short_name(it['name'])}" + (f" ({where})" if where else ""))
    lines = []
    for key, names in groups.items():
        if key[0] == "taper":
            lines.append(("taper", names[0]))
            continue
        kind, bed, when, why = key
        shown = ", ".join(names[:8]) + (f" and {len(names) - 8} more"
                                        if len(names) > 8 else "")
        lines.append((kind, f"{bed}, {when}: {shown}. {why[0].upper()}{why[1:]}"))
    return lines


# -------------------------------------------------------------------- lint

def lint(data):
    """Water jobs that the calendar has to guess about."""
    out = []
    for t in jobs(data):
        if t.get("kind") == "timer":
            continue
        if not t.get("dose"):
            out.append({"kind": "dose", "subject": t["id"],
                        "message": f"{t['id']} \"{t['title']}\" has no `dose`, so "
                                   f"the event cannot say how much"})
        if not t.get("when"):
            out.append({"kind": "when", "subject": t["id"],
                        "message": f"{t['id']} \"{t['title']}\" has no `when`; "
                                   f"the calendar reads "
                                   f"{' and '.join(slots_of(t))} from the prose"})
    return out


# -------------------------------------------------------------- the events

def _qty(gal):
    """An amount in gallons, as a person measures it."""
    if gal >= 1:
        whole, frac = divmod(round(gal * 4) / 4, 1)
        part = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}.get(round(frac, 2), "")
        return (f"{int(whole)} {part}".strip() if whole else part) + " gal"
    if gal >= 0.25:
        q = round(gal * 4 * 2) / 2
        return f"{q:g} quart{'s' if q != 1 else ''}"
    c = round(gal * 16 * 2) / 2
    return f"{c:g} cup{'s' if c != 1 else ''}"


def dose_line(t, targets):
    """"1 1/2 gal in all: 1/2 gal on each of 3 squares"."""
    dose = t.get("dose") or {}
    if not dose:
        return ""
    if dose.get("amount") is None:
        return dose.get("text", "")
    unit = UNITS.get(str(dose.get("unit", "gal")).lower(), 1.0)
    each = float(dose["amount"]) * unit
    per = dose.get("per") or "bed"
    n = targets.get(per)
    if per in ("bed", "strip", "tray", "vessel"):
        n = n or 1
    if not n:
        line = f"{_qty(each)} per {per}"
    elif n == 1:
        line = f"{_qty(each)}" + (f" on the {per}" if per != "bed" else "")
    else:
        line = f"{_qty(each * n)} in all: {_qty(each)} on each of {n} {per}s"
    if dose.get("text"):
        line += f". {dose['text']}"
    return line


def _targets(t, d, items, keys):
    """What the job reaches today: plants, squares and pots, with counts."""
    w = t.get("where") or {}
    reached = [i for i in items if in_ground(i, d) and covers(t, i, keys)]
    squares = _task_squares(t)
    plants = [i for i in reached if i["kind"] != "square"]
    pots = list(w.get("containers") or [])
    return reached, {"square": len(squares) or None,
                     "plant": len(plants) or None,
                     "pot": len(pots) or None}


def _subject(t, reached):
    """A short name for the job, for the title.

    `label` on the task wins. Else the plants, when there are one or two kinds.
    Else the beds, because "g02, g03 new plantings" reads better in a title
    than twenty plant names.
    """
    if t.get("label"):
        return [t["label"]]
    if t.get("kind") == "timer":
        return ["timer"]
    names = []
    for i in reached:
        n = short_name(i["name"]).lower()
        if n and n not in names:
            names.append(n)
    if 0 < len(names) <= 2:
        return names
    beds = []
    for i in reached:
        if i["bed"] not in beds:
            beds.append(i["bed"])
    if beds:
        return [" + ".join(beds)]
    w = t.get("where") or {}
    return [short_name(w.get("place") or w.get("bed") or t["title"]).lower()]


def _plant_list(reached):
    """"g02: Damianita x3, Gulf muhly x5; raised: Carrots (5-W1, 6-W1)"."""
    beds = {}
    for i in reached:
        beds.setdefault(i["bed"], {}).setdefault(short_name(i["name"]), []).append(i)
    out = []
    for bed, by_name in beds.items():
        bits = []
        for n, its in by_name.items():
            sq = [i["square"] for i in its if i.get("square")]
            if sq:
                bits.append(f"{n} ({', '.join(sq)})")
            else:
                bits.append(n if len(its) == 1 else f"{n} x{len(its)}")
        out.append(f"{bed}: {', '.join(bits)}")
    return "; ".join(out)


def _next_job(t, d, all_jobs, items, keys):
    """The job that takes over the same plants after this one ends."""
    mine = {i["id"] for i in items if covers(t, i, keys)}
    sq = set(_task_squares(t))
    best = None
    for o in all_jobs:
        if o is t or o.get("kind") == "timer":
            continue
        a, _ = span_of(o)
        if not (d < a <= d + datetime.timedelta(days=step_of(t) + 7)):
            continue
        theirs = {i["id"] for i in items if covers(o, i, keys)}
        if (mine and mine & theirs) or (sq and sq & set(_task_squares(o))):
            if best is None or a < span_of(best)[0]:
                best = o
    return best


def job_block(t, d, all_jobs, items, keys):
    reached, targets = _targets(t, d, items, keys)
    lines = [f"- {t['title']} [{t['id']}]"]
    plants = _plant_list(reached)
    w = t.get("where") or {}
    if plants:
        lines.append(f"  Plants: {plants}")
    elif w.get("place") or w.get("bed"):
        lines.append(f"  Where: {w.get('place') or w.get('bed')}")
    if w.get("at"):
        lines.append(f"  At: {w['at']}")
    dl = dose_line(t, targets)
    if dl:
        lines.append(f"  Amount: {dl}")
    if t.get("repeat"):
        a, z = span_of(t)
        nxt_occ = week._occurrences(t, d + datetime.timedelta(days=1), z)
        if d == a:
            lines.append(f"  STARTS TODAY: {cadence(t)} to {z:%a %-d %b}.")
        if not nxt_occ:
            follow = _next_job(t, d, all_jobs, items, keys)
            if follow:
                fa, _ = span_of(follow)
                fd = dose_line(follow, _targets(follow, fa, items, keys)[1])
                lines.append(f"  LAST DAY of this job. From {fa:%a %-d %b}: "
                             f"{follow['title']} ({cadence(follow)}"
                             + (f", {fd}" if fd else "") + f") [{follow['id']}].")
            else:
                lines.append("  LAST DAY of this job. Then stop.")
        elif d != a:
            lines.append(f"  {cadence(t).capitalize()}, to {z:%a %-d %b}.")
        if t["repeat"].get("note"):
            lines.append(f"  Note: {t['repeat']['note']}")
    for step in t.get("how") or []:
        lines.append(f"  * {step}")
    gate = t.get("gate") or {}
    if gate.get("miss"):
        lines.append(f"  Skip rule: {gate['miss']}")
    if t.get("warn"):
        lines.append(f"  WARNING: {t['warn']}")
    return "\n".join(lines), _subject(t, reached)


def _clock(s, slot):
    hh, mm = (int(x) for x in s["slots"][slot].split(":"))
    return datetime.time(hh, mm)


def _iso(d, tm, tz):
    """An RFC 3339 time with the offset of that zone on that day."""
    dt = datetime.datetime.combine(d, tm)
    try:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo(tz))
        return dt.isoformat(timespec="seconds")
    except Exception:
        return dt.isoformat(timespec="seconds")


def events(slug, start, end, data=None, stamp=None):
    """The events for start..end inclusive, keyed `<slug>:<date>:<slot>`."""
    data = data if data is not None else week.load(slug) or {}
    s = settings(slug)
    items = inventory(slug, data)
    _prime(items)
    keys = {i["bed"] for i in items}
    all_jobs = jobs(data)
    block = drip(slug)
    sandbox = yards.sandbox_stamp(slug)
    out = []
    d = start
    while d <= end:
        for slot in SLOTS:
            today = [t for t in all_jobs if slot in slots_of(t) and occurs(t, d)]
            if not today:
                continue
            blocks, subjects, mins = [], [], 0
            for t in sorted(today, key=lambda x: (x.get("kind") == "timer",
                                                  not x.get("critical"), x["id"])):
                text, subj = job_block(t, d, all_jobs, items, keys)
                blocks.append(text)
                subjects += [x for x in subj if x not in subjects]
                mins += t.get("minutes") or 0
            mins = max(mins, s["min_minutes"])
            shown = ", ".join(subjects[:4]) + (f" +{len(subjects) - 4} more"
                                               if len(subjects) > 4 else "")
            summary = f"Water {SLOT_SHORT[slot]}: {shown} ({mins} min)"
            if sandbox:
                summary = f"[{sandbox}] {summary}"
            head = []
            if stamp:
                head.append(stamp)
            if sandbox:
                head.append(f"{sandbox}. A rehearsal copy, not the plan.")
            body = "\n\n".join(blocks)
            tail = drip_line(block, d)
            description = "\n\n".join(x for x in ["\n".join(head), body, tail,
                                                  "Generated from tasks.json. "
                                                  "The next sync overwrites any "
                                                  "edit to this event."] if x)
            tm = _clock(s, slot)
            st = datetime.datetime.combine(d, tm)
            en = st + datetime.timedelta(minutes=mins)
            ev = {"key": f"{slug}:{d.isoformat()}:{slot}", "date": d.isoformat(),
                  "slot": slot, "summary": summary, "description": description,
                  "start": {"dateTime": _iso(d, tm, s["timezone"]),
                            "timeZone": s["timezone"]},
                  "end": {"dateTime": _iso(en.date(), en.time(), s["timezone"]),
                          "timeZone": s["timezone"]},
                  "tasks": [t["id"] for t in today]}
            ev["hash"] = _hash(ev)
            out.append(ev)
        d += datetime.timedelta(days=1)
    return out


def _hash(ev):
    body = json.dumps([ev["summary"], ev["description"], ev["start"], ev["end"]],
                      sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ the sync

def blockers(slug, start, end, data=None):
    """Everything that stops `--plan`, as (kind, message) pairs."""
    data = data if data is not None else week.load(slug) or {}
    out = [("week", p["message"]) for p in week.check(slug)]
    out += [(k, m) for k, m in coverage_lines(coverage(slug, start, end, data))]
    out += [("dose", f["message"]) for f in lint(data) if f["kind"] == "dose"]
    return out


def _stamp_for(found):
    kinds = {}
    for k, _ in found:
        kinds[k] = kinds.get(k, 0) + 1
    named = ", ".join(f"{n} {k}" for k, n in kinds.items())
    return f"PROVISIONAL - forced past {named} finding(s). Run `lib.watercal --coverage`."


def plan(slug, today=None, force=False):
    """Write the create, update and delete operations, and return them."""
    s = settings(slug)
    if not s.get("calendar_id"):
        raise SystemExit(
            f"  {slug}: water-calendar.json has no calendar_id. Create the "
            f"calendar \"{s['calendar_name']}\" in Google Calendar, find its id "
            f"with listCalendars, and put it in {yards.path(slug, FILE)}")
    today = today or datetime.date.today()
    end = today + datetime.timedelta(days=s["horizon_days"] - 1)
    data = week.load(slug) or {}
    found = blockers(slug, today, end, data)
    stamp = None
    if found:
        if not force:
            lines = "\n".join(f"      [{k}] {m}" for k, m in found)
            raise SystemExit(
                f"  {slug}: {len(found)} finding(s) stop the calendar sync:\n\n"
                f"{lines}\n\n  Fix them in tasks.json, irrigation.json or "
                f"design.json, or run `--plan --force` to sync with a stamp.")
        stamp = _stamp_for(found)
    desired = {e["key"]: e for e in events(slug, today, end, data, stamp)}
    ledger = s.get("events") or {}
    cal = s["calendar_id"]
    ops = []
    for key, e in desired.items():
        args = {"calendarId": cal, "summary": e["summary"],
                "description": e["description"], "start": e["start"],
                "end": e["end"], "sendUpdates": "none"}
        have = ledger.get(key)
        if not have:
            ops.append({"op": "create", "key": key, "hash": e["hash"],
                        "date": e["date"], "slot": e["slot"],
                        "tool": "createCalendarEvent", "args": args})
        elif have.get("hash") != e["hash"]:
            ops.append({"op": "update", "key": key, "hash": e["hash"],
                        "date": e["date"], "slot": e["slot"],
                        "tool": "updateCalendarEvent",
                        "args": dict(args, eventId=have["id"])})
    for key, have in sorted(ledger.items()):
        if key in desired or week._date(have["date"]) < today:
            continue
        ops.append({"op": "delete", "key": key, "date": have["date"],
                    "tool": "deleteCalendarEvent",
                    "args": {"calendarId": cal, "eventId": have["id"],
                             "sendUpdates": "none"}})
    out = {"yard": slug, "built": today.isoformat(),
           "namespace": s.get("namespace"), "account": s.get("account"),
           "calendar_id": cal, "window": [today.isoformat(), end.isoformat()],
           "stamp": stamp,
           "counts": {k: sum(1 for o in ops if o["op"] == k)
                      for k in ("create", "update", "delete")},
           "unchanged": len(desired) - sum(1 for o in ops
                                           if o["op"] in ("create", "update")),
           "ops": ops}
    yards.save(slug, PLAN_FILE, out)
    return out


def record(slug, results, today=None):
    """Write the event ids that the agent got back into the ledger.

    `results` is a list of `{"key", "op", "id"}`, or a `{key: id}` mapping for
    creates and updates. A key that is not in the current plan is refused,
    because its hash is not known.
    """
    s = settings(slug)
    p = yards.load(slug, PLAN_FILE) or {}
    ops = {o["key"]: o for o in p.get("ops", [])}
    if isinstance(results, dict):
        results = [{"key": k, "id": v} for k, v in results.items()]
    ledger = s.setdefault("events", {})
    done, refused = [], []
    for r in results:
        o = ops.get(r.get("key"))
        if not o:
            refused.append(r.get("key"))
            continue
        kind = r.get("op") or o["op"]
        if kind == "delete":
            ledger.pop(o["key"], None)
        else:
            ev_id = r.get("id") or (ledger.get(o["key"]) or {}).get("id")
            if not ev_id:
                refused.append(o["key"])
                continue
            ledger[o["key"]] = {"id": ev_id, "hash": o["hash"],
                                "date": o["date"], "slot": o["slot"]}
        done.append(o["key"])
    cutoff = (today or datetime.date.today()) - datetime.timedelta(days=90)
    for k in [k for k, v in ledger.items() if week._date(v["date"]) < cutoff]:
        ledger.pop(k)
    save_settings(slug, s)
    return done, refused


# ------------------------------------------------------------------- .ics

def _ics_escape(text):
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _fold(line):
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def ics(slug, evs):
    s = settings(slug)
    tz = s["timezone"]
    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//yard planner//lib.watercal//EN",
             f"X-WR-CALNAME:{_ics_escape(s['calendar_name'])}",
             f"X-WR-TIMEZONE:{tz}"]
    for e in evs:
        st = e["start"]["dateTime"][:19].replace("-", "").replace(":", "")
        en = e["end"]["dateTime"][:19].replace("-", "").replace(":", "")
        lines += ["BEGIN:VEVENT", f"UID:{e['key']}@yard-planner",
                  f"DTSTAMP:{stamp}", f"DTSTART;TZID={tz}:{st}",
                  f"DTEND;TZID={tz}:{en}",
                  f"SUMMARY:{_ics_escape(e['summary'])}",
                  f"DESCRIPTION:{_ics_escape(e['description'])}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


# ------------------------------------------------------------------ report

def preview(slug, start, end):
    for e in events(slug, start, end):
        st = e["start"]["dateTime"][11:16]
        print(f"\n== {e['date']} {st}  {e['summary']}")
        for line in e["description"].splitlines():
            print(f"   {line}")


def report_coverage(slug, start, end):
    found = coverage(slug, start, end)
    items = [i for i in inventory(slug) if in_ground(i, end)]
    print(f"  {slug}: {len(items)} plants, squares and pots in the ground by "
          f"{end:%-d %b}, checked {start:%-d %b} to {end:%-d %b}\n")
    if not found:
        print("  every one of them is watered by the drip or by a hand job on "
              "every day, at the establishment and seed intervals")
        return 0
    lines = coverage_lines(found)
    order = ["untracked", "uncovered", "establishment", "seed", "taper"]
    heads = {"untracked": "no planting date, so nothing can know if it is watered",
             "uncovered": "nothing waters it",
             "establishment": "a new planting with a gap in its hand watering",
             "seed": "a sowing that dries out before it is up",
             "taper": "a repeat that hides a change of cadence in its note"}
    for kind in order:
        rows = [m for k, m in lines if k == kind]
        if not rows:
            continue
        print(f"  {heads[kind]} ({len(rows)}):")
        for m in rows:
            print(f"      {m}")
        print()
    return len(lines)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--from", dest="start", help="first day, YYYY-MM-DD")
    ap.add_argument("--days", type=int, help="how many days to show or check")
    ap.add_argument("--coverage", action="store_true",
                    help="every plant in the ground that nothing waters")
    ap.add_argument("--lint", action="store_true",
                    help="water tasks with no `when` or `dose`")
    ap.add_argument("--init", action="store_true",
                    help="write water-calendar.json with the defaults")
    ap.add_argument("--account", help="with --init: the Google account alias")
    ap.add_argument("--namespace", help="with --init: the MCP namespace")
    ap.add_argument("--plan", action="store_true",
                    help="-> water-calendar.plan.json, the operations to run")
    ap.add_argument("--record", metavar="RESULTS_JSON",
                    help="the event ids that the agent got back")
    ap.add_argument("--ics", action="store_true", help="-> WATER.ics")
    ap.add_argument("--force", action="store_true",
                    help="--plan past a finding; every event is stamped")
    args = ap.parse_args()

    if not args.slug:
        print(__doc__)
        return
    slug = args.slug
    s = settings(slug)
    start = week._date(args.start) if args.start else datetime.date.today()

    if args.init:
        print(f"wrote {init(slug, args.account, args.namespace)}")
        return

    if args.lint:
        found = lint(week.load(slug) or {})
        for f in found:
            print(f"  [{f['kind']}] {f['message']}")
        if not found:
            print("  every water task has a `when` and a `dose`")
        raise SystemExit(1 if any(f["kind"] == "dose" for f in found) else 0)

    if args.coverage:
        days = args.days or s["horizon_days"]
        n = report_coverage(slug, start, start + datetime.timedelta(days=days - 1))
        raise SystemExit(1 if n else 0)

    if args.plan:
        out = plan(slug, start if args.start else None, force=args.force)
        c = out["counts"]
        print(f"  {out['window'][0]} to {out['window'][1]}: {c['create']} to "
              f"create, {c['update']} to update, {c['delete']} to delete, "
              f"{out['unchanged']} unchanged")
        if out["stamp"]:
            print(f"  {out['stamp']}")
        print(f"  {yards.path(slug, PLAN_FILE)}")
        print(f"  Run each op with its `tool` in {out['namespace'] or 'the MCP'} "
              f"namespace, then `--record` the ids.")
        return

    if args.record:
        with open(args.record, encoding="utf-8") as fh:
            done, refused = record(slug, json.load(fh))
        print(f"  recorded {len(done)} operation(s)")
        if refused:
            print(f"  refused {len(refused)}, not in the current plan or with "
                  f"no id: {', '.join(str(r) for r in refused[:8])}")
        return

    if args.ics:
        days = args.days or s["horizon_days"]
        evs = events(slug, start, start + datetime.timedelta(days=days - 1))
        path = yards.write_text(slug, ICS_FILE, ics(slug, evs))
        print(f"  {len(evs)} events -> {path}")
        return

    days = args.days or 7
    preview(slug, start, start + datetime.timedelta(days=days - 1))


if __name__ == "__main__":
    main()
