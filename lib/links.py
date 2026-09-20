#!/usr/bin/env python3
"""Where a reference in the record lands in the published HTML.

    python3 -m lib.links cloverleaf-austin              every document
    python3 -m lib.links cloverleaf-austin PLAN.md      one document

A task cites its method as `SOWING-CALENDAR.md#8`. A reader on a phone wants
that click to land on the heading, in the page they already have. Three things
had to agree for that to work and only two of them did:

    `week.sections`      what a heading is called
    `buildhtml.slug`     what id that heading gets in the page
    the reference itself

The first two were separate implementations of the same idea. They happened to
agree, and nothing made them. This module is the one implementation, imported
by both, so a deep link is a guarantee rather than a coincidence.

The rule this module exists to keep: a generated page LINKS to prose, it does
not reproduce it. Copying the carrot method out of SOWING-CALENDAR.md and into
a task page makes two copies that drift, and the one somebody reads is then a
coin toss. So the deep link has to work, or the rule cannot be followed.
"""
import argparse
import os
import re

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

#: A `#4.1` anchor: a section number, dotted, optionally suffixed with a letter.
SECTION_NO = re.compile(r"^\d+(?:\.\d+)*[a-z]?$")

#: `## c306 — ... {: #c306 }`. The markdown attr_list extension turns this into
#: the heading's id, so the publisher leaves it alone and so must we.
OWN_ID = re.compile(r"\{:\s*#([^}\s]+)\s*\}\s*$")

#: The levels `buildhtml.add_anchors` gives an id to. A reference to any other
#: level names a real heading that the page has no way to scroll to, which is
#: worth saying out loud rather than emitting a link that silently does nothing.
ANCHORED = (2, 3)


def slug(text, seen=None):
    """The id a heading gets in the published page.

    Pass `seen` to number a repeated heading the way the publisher does, and
    leave it out for the stable base slug that a reference matches against.
    """
    s = re.sub(r"[^\w\s-]", "", re.sub(r"<[^>]+>", "", text)).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s) or "section"
    if seen is None:
        return s
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if not n else f"{s}-{n}"


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
        out.append({"level": level, "text": text, "slug": slug(text),
                    "body": "\n".join(lines[start:end]).rstrip()})
    return out


def anchored(path):
    """Every section, each carrying the anchor its heading gets in the page.

    This mirrors `buildhtml.add_anchors` rather than guessing at it: only h2 and
    h3 are given ids, they are numbered in document order, and a heading that
    brought its own `{: #c306 }` keeps it and does not consume a number. Get any
    of those three wrong and the link points at nothing, which is worse than no
    link because it looks like it worked.
    """
    seen, out = {}, []
    for s in sections(path):
        s = dict(s)
        own = OWN_ID.search(s["text"])
        if own:
            s["text"] = OWN_ID.sub("", s["text"]).strip()
            s["slug"] = slug(s["text"])
            s["anchor"] = own.group(1)
        elif s["level"] in ANCHORED:
            s["anchor"] = slug(s["text"], seen)
        else:
            s["anchor"] = None
        out.append(s)
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
    secs = anchored(path)
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


def target(root, ref):
    """A reference as the URL it has in the published set, or why it has none.

    Returns (url, section, error) with exactly one of url and error set. An
    external URL is passed through untouched: a task citing the Houston
    Arboretum's build page is not a broken reference, it is a reference to
    somewhere else.
    """
    ref = str(ref)
    if ref.startswith(("http://", "https://")):
        return ref, None, None
    sec, err = resolve(root, ref)
    if err:
        return None, None, err
    if not sec["anchor"]:
        return None, sec, (f"{ref} names a level-{sec['level']} heading, and "
                           f"the publisher only anchors h2 and h3")
    page = ref.split("#", 1)[0]
    return f"{page[:-3]}.html#{sec['anchor']}", sec, None


def label(ref, sec=None):
    """What to call the link, in words a person reading the page recognises."""
    ref = str(ref)
    if ref.startswith(("http://", "https://")):
        host = ref.split("//", 1)[1].split("/", 1)[0]
        return host[4:] if host.startswith("www.") else host
    name, _, anchor = ref.partition("#")
    doc = name[:-3] if name.endswith(".md") else name
    if sec:
        return f"{doc} — {sec['text']}"
    return f"{doc} §{anchor}" if anchor else doc


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("document", nargs="?", help="just this one")
    args = ap.parse_args()

    from . import yards
    root = yards.yard_dir(args.slug)
    names = ([args.document] if args.document
             else sorted(f for f in os.listdir(root) if f.endswith(".md")))
    for name in names:
        secs = anchored(os.path.join(root, name))
        shown = [s for s in secs if s["anchor"]]
        print(f"\n  {name}  — {len(shown)} of {len(secs)} headings anchored")
        for s in shown[:200]:
            print(f"      {name[:-3]}.html#{s['anchor']}")
            print(f"          h{s['level']}  {s['text'][:66]}")


if __name__ == "__main__":
    main()
