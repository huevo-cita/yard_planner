#!/usr/bin/env python3
"""One machine-readable view of a yard, for everything that draws a screen.

    python3 -m lib.bundle cloverleaf-austin              write bundle.json
    python3 -m lib.bundle cloverleaf-austin --summary    what is in it
    python3 -m lib.bundle cloverleaf-austin --stdout     print it

Why this exists rather than each page reading the JSON files itself.

A yard's record is eight or nine files that disagree about shape: `tasks.json`
holds dated work, `design.json` holds plants, `sourcing.json` holds shops,
`doubts.json` holds open questions, and the markdown documents hold the prose
those four point at. Every page that renders any of it has to do the same
joining — resolve a task's `technique` to a real anchor, work out which plant a
placement line names, find the supplier behind a shopping line. Done once per
page, that join is four copies that drift.

So it is done once, here, and the pages render what comes out. The immediate
gain is that `WEEK.html`, `TASKS.html` and `CALENDAR.html` cannot disagree
about a date or a link. The one after that is that a phone app reads this same
file and renders the same screens natively, with no second extraction to keep
in step with this one.

A week is in here as well, under `weeks`: one row of facts each, carrying its
id, its hours, how many jobs it holds, and whether it falls past the date the
plan runs to. Three screens count weeks, and three counts are three answers.
A week's id is `w` and its Monday's date, which is the only address a week has.

What this is not: a new source of truth. Nothing is authored here and nothing
is stored here that is not derived. Delete `bundle.json` and rebuild it; the
record is the JSON files and the markdown, exactly as before.
"""
import argparse
import datetime
import json
import os

from . import links, plants, yards

BUNDLE = "bundle.json"

#: A yard's own documents, with what each is for, in reading order. The order
#: is the one a person needs them in rather than alphabetical, and the blurb is
#: here because the index page is unreadable as a bare list of filenames.
DOCS = [
    ("PLAN.md", "The plan", "The beds, the standing water and pruning "
     "calendars, the pest tables and the budget."),
    ("SOWING-CALENDAR.md", "The raised bed", "Soil-temperature gates, the "
     "days-to-maturity arithmetic and the technique notes."),
    ("SOURCING.md", "Where to buy it", "Every price with the confidence "
     "label it earned, and who to call."),
    ("SITE-WALK.md", "The site walk", "What to measure on foot, and what the "
     "record expects so it can be proved wrong."),
    ("CHANGELOG.md", "Why it reads this way", "Every change, correction and "
     "argument, behind the [cNN] marks."),
]

#: Reference material. Long on purpose, read once, cited often.
RESEARCH_BLURB = "Reference material, cited by the plan."


def _doc_entry(root, name, title=None, blurb=None):
    path = os.path.join(root, name)
    if not os.path.exists(path):
        return None
    secs = links.anchored(path)
    page = name[:-3] + ".html"
    head = next((s for s in secs if s["level"] == 1), None)
    return {
        "file": name,
        "html": page,
        "title": title or (head["text"] if head else name[:-3]),
        "heading": head["text"] if head else None,
        "blurb": blurb,
        "published": os.path.exists(os.path.join(root, page)),
        "sections": [{"level": s["level"], "text": s["text"],
                      "anchor": s["anchor"],
                      "url": f"{page}#{s['anchor']}" if s["anchor"] else None}
                     for s in secs if s["level"] in (1, 2, 3)],
    }


def documents(slug):
    """Every document this yard publishes, with the anchors it offers.

    Anchors are carried rather than recomputed by each reader, because the
    anchor is the whole mechanism: a page links into another page's heading,
    and if the two disagree about what that heading's id is the link lands at
    the top and looks like it worked.
    """
    root = yards.yard_dir(slug)
    out = []
    for name, title, blurb in DOCS:
        e = _doc_entry(root, name, title, blurb)
        if e:
            out.append(e)
    known = {d["file"] for d in out}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".md") or name in known:
            continue
        if name == "CALENDAR.md":
            continue                      # generated, and the pages replace it
        e = _doc_entry(root, name, blurb=RESEARCH_BLURB)
        if e:
            e["research"] = True
            out.append(e)
    return out


def task_links(root, task, open_doubts=()):
    """Everywhere a task points, as URLs into the published set.

    The order is the order somebody in the garden wants them: how to do it,
    then the wider detail, then where it came from, then why it reads this way,
    then what is still unsettled about it.

    A reference that resolves to nothing is kept, carrying its error, rather
    than dropped. A silently missing link is the failure that `--links` exists
    to report, and it can only report what the join admits it could not do.
    """
    out = []

    def add(kind, ref):
        url, sec, err = links.target(root, str(ref))
        out.append({"kind": kind, "ref": str(ref), "url": url,
                    "label": links.label(str(ref), sec),
                    "section": sec["text"] if sec else None,
                    "error": err})

    for kind in ("technique", "reference"):
        if task.get(kind):
            add(kind, task[kind])
    for ref in task.get("source", []) or []:
        add("source", ref)
    for c in task.get("changelog", []) or []:
        out.append({"kind": "changelog", "ref": c,
                    "url": f"CHANGELOG.html#{c}", "label": c,
                    "section": None, "error": None})
    # Only an open card is on the index, so only an open card gets a link.
    # A settled one still names itself, because a job that was held up by a
    # question is worth knowing about after the question is answered.
    for d in task.get("doubts", []) or []:
        live = d in open_doubts
        out.append({"kind": "doubt", "ref": d,
                    "url": f"INDEX.html#{d}" if live else None,
                    "label": (f"open question {d}" if live
                              else f"settled question {d}"),
                    "section": None, "error": None})
    return out


def when_of(task):
    """When this happens, in one phrase, however the record states it."""
    from . import week
    if task.get("repeat"):
        r = task["repeat"]
        return (f"{week._cadence(task)}, "
                f"{week._date(r['from']):%-d %b} to {week._date(r['to']):%-d %b}")
    if task.get("window"):
        a, z = task["window"]
        return (f"any day from {week._date(a):%a %-d %b} "
                f"to {week._date(z):%a %-d %b}")
    return f"{week._date(task['date']):%A %-d %B}"


def build(slug):
    """The whole yard, joined, as one structure."""
    from . import week

    root = yards.yard_dir(slug)
    tasks_doc = yards.load(slug, "tasks.json") or {}
    design = yards.load(slug, "design.json") or {}
    sourcing = yards.load(slug, "sourcing.json") or {}
    doubts_doc = yards.load(slug, "doubts.json") or {}

    idx = plants.index(design)
    creds = plants.credits(slug)
    shops = {s["id"]: s for s in sourcing.get("suppliers", [])}
    open_doubts = {c["id"] for c in doubts_doc.get("cards", [])
                   if c.get("status") == "open"}

    out_tasks = []
    for t in tasks_doc.get("tasks", []):
        rows = plants.placements(t, idx)
        shots, seen = [], set()
        for r in rows:
            for n in r["named"]:
                pic = plants.photo_for(n["binomials"], creds)
                if pic and pic["binomial"] not in seen:
                    seen.add(pic["binomial"])
                    shots.append(dict(pic, name=n["name"]))
        out_tasks.append(dict(
            t,
            anchor=t["id"],
            when=when_of(t),
            links=task_links(root, t, open_doubts),
            placements=rows,
            photos=shots,
        ))

    out_plants = []
    for p in design.get("plants", []):
        bs = plants.binomials(p)
        out_plants.append(dict(
            p, names=sorted(plants.names_for(p)), binomials=bs,
            photo=plants.photo_for(bs, creds)))

    return {
        "schema": 1,
        "yard": {
            "slug": slug,
            "name": week.yard_name(slug),
            "sandbox": yards.sandbox_stamp(slug) or None,
            "target_date": tasks_doc.get("target_date"),
            "target_note": tasks_doc.get("target_note"),
        },
        "built": datetime.date.today().isoformat(),
        "documents": documents(slug),
        "weeks": week.week_spine(tasks_doc,
                                 yards.load_conditions(slug) or {}),
        "tasks": out_tasks,
        "shopping": [dict(b, shop=shops.get(b.get("supplier")))
                     for b in tasks_doc.get("shopping", [])],
        "suppliers": sourcing.get("suppliers", []),
        "plants": out_plants,
        "doubts": [c for c in doubts_doc.get("cards", [])
                   if c.get("status") == "open"],
        "google_doc": tasks_doc.get("google_doc"),
    }


def write(slug):
    data = build(slug)
    path = os.path.join(yards.yard_dir(slug), BUNDLE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
    return path, data


def load(slug, rebuild=True):
    """The bundle, built fresh unless a caller explicitly wants what is on disk."""
    if rebuild:
        return build(slug)
    path = os.path.join(yards.yard_dir(slug), BUNDLE)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    data = build(args.slug)

    if args.stdout:
        print(json.dumps(data, indent=1))
        return

    if not args.summary:
        path, _ = write(args.slug)
        print(f"wrote {path}  ({os.path.getsize(path) // 1024} KB)")

    anchors = sum(len([s for s in d["sections"] if s["anchor"]])
                  for d in data["documents"])
    broken = [l for t in data["tasks"] for l in t["links"] if l["error"]]
    nophoto = [p for p in data["plants"] if p["binomials"] and not p["photo"]]
    unmatched = sum(1 for t in data["tasks"] for r in t["placements"]
                    if r["unmatched"] and r["positional"])

    print(f"\n  {data['yard']['name']}")
    print(f"      {len(data['documents']):3d} documents, {anchors} anchored "
          f"sections to link into")
    beyond = [w for w in data["weeks"] if w["beyond"]]
    print(f"      {len(data['weeks']):3d} weeks, "
          f"{sum(1 for w in data['weeks'] if not w['empty'])} of them carrying "
          f"work, {len(beyond)} past the target date")
    print(f"      {len(data['tasks']):3d} tasks, "
          f"{sum(len(t['links']) for t in data['tasks'])} references, "
          f"{len(broken)} of them resolving to nothing")
    print(f"      {len(data['plants']):3d} plants, "
          f"{sum(1 for p in data['plants'] if p['photo'])} with a photograph")
    print(f"      {len(data['shopping']):3d} things to buy from "
          f"{len(data['suppliers'])} suppliers")
    print(f"      {len(data['doubts']):3d} open doubts")
    if unmatched:
        print(f"      {unmatched} placement line(s) name no plant in "
              f"design.json — `python3 -m lib.plants {args.slug} --match`")
    for l in broken:
        print(f"      broken: {l['error']}")


if __name__ == "__main__":
    main()
