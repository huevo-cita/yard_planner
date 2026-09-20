#!/usr/bin/env python3
"""The nursery calls on one page, with a picture of every name trap.

    python3 -m lib.callcard cloverleaf-austin              every call still ahead
    python3 -m lib.callcard cloverleaf-austin --task t076  one of them
    python3 -m lib.callcard cloverleaf-austin --traps      what it found, and where

Writes `CALL-CARD.html`, a page to hold while the phone rings.

A common name maps to more than one species, and the wrong one comes home:
"milkweed" in an Austin autumn is *Asclepias curassavica*, which does active
harm; a bench reading "Texas sedge" is *Carex texensis*, a sun-loving
medium-water plant, and the design wants *Carex planostachys* for dry shade.
The card's whole job is to put the right binomial in your mouth and a
photograph of the wrong plant in front of your eyes.

NOTHING HERE IS A LIST SOMEBODY TYPED. The traps are found in the yard's own
record. A call task's `how` steps and its shopping lines' `ask`, `note` and
`pin` fields already say things like "Yucca pallida NOT Y. recurvifolia" and
"anything sold simply as milkweed ... is A. curassavica". So each of those
fields is read as one unit, the binomials in it are pulled out, and they split
two ways: a species the design actually contains is a BUY, and a species of
the same genus that the design does not contain is a REFUSE. A plant the
design dropped, named in `cut_and_why`, is a refuse too.

The consequence worth stating: correct the record and the card follows, and a
trap nobody wrote into the record does not appear. `--traps` prints what was
found and the field it came from, so a missing one is traceable to the
sentence that should have said it.
"""
import argparse
import datetime
import html
import os
import re

from . import bundle, buildhtml, chrome, plants, yards

OUT = "CALL-CARD.html"

#: An abbreviated species: "A. asperula", "Y. pendula", "C. texensis". Always
#: expanded against a genus the design actually names, never guessed.
ABBREV = re.compile(r"\b([A-Z])\.\s*([a-z]{3,})\b")

#: A quoted or plain common name in the text is not enough to identify a
#: plant, but the design's own dropped-plant list gives the names to look for.
CUT_STOP = re.compile(r"\s*[-\u2013(].*$")

#: English words that follow a genus in these sentences and are not epithets.
#: "Same trap as the Yucca above" is not a species. Grouping by genus already
#: discards most of these, because a bare English word never has a wanted
#: species beside it; this is the cheap second guard.
NOT_AN_EPITHET = {
    "above", "below", "and", "are", "also", "but", "can", "for", "from",
    "has", "here", "instead", "into", "not", "only", "plants", "rather",
    "seed", "sold", "stock", "that", "the", "them", "then", "they", "this",
    "was", "were", "which", "will", "with", "would", "you", "your",
}

CARD_CSS = """
.call { border:1px solid var(--rule); border-radius:10px; padding:0;
  margin:1.4em 0 2.4em; overflow:hidden; scroll-margin-top:5rem; }
.call > header { background:var(--accent); color:#fff; padding:.8em 1em; }
.call > header h2 { margin:0; border:0; color:#fff; font-size:1.1rem; }
.call > header p { margin:.2em 0 0; font-size:.86rem; opacity:.9; }
.call .inner { padding:.2em 1em 1em; }
.shopcard { background:var(--band); border:1px solid var(--rule);
  border-radius:8px; padding:.8em 1em; margin:1em 0; }
.shopcard .tel { font-size:1.5rem; font-weight:700; display:inline-block;
  text-decoration:none; letter-spacing:-.01em; }
.shopcard .meta { color:var(--muted); font-size:.86rem; }
ol.script { padding-left:1.3em; } ol.script li { margin:.55em 0; }

details.trap { border:1px solid var(--rule); border-radius:8px; margin:.6em 0; }
details.trap > summary { cursor:pointer; padding:.7em .9em; list-style:none;
  display:flex; flex-wrap:wrap; gap:.5em; align-items:baseline; }
details.trap > summary::-webkit-details-marker { display:none; }
details.trap > summary::before { content:"\\25B8"; color:var(--muted); }
details.trap[open] > summary::before { content:"\\25BE"; }
details.trap > summary:hover { background:var(--band); }
.trap .say { font-weight:700; }
.trap .binom { color:var(--yes); font-weight:600; font-style:italic; }
.trap .qty { margin-left:auto; color:var(--muted); font-size:.82rem; }
.trap .body { padding:0 .9em 1em; border-top:1px solid var(--rule); }
.quote { border-left:3px solid var(--accent); background:var(--band);
  padding:.5em .8em; margin:.8em 0; font-size:.92rem; }
.quote cite { display:block; color:var(--muted); font-size:.76rem;
  font-style:normal; margin-top:.3em; }
.pics { display:flex; gap:.8em; flex-wrap:wrap; margin:.9em 0; }
.col { flex:1 1 14rem; display:flex; flex-direction:column; gap:.5em; }
figure.shot { margin:0; border:2px solid var(--rule); border-radius:8px;
  overflow:hidden; }
.yescol figure.shot { border-color:var(--yes); }
.nocol figure.shot { border-color:var(--crit); }
/* contain, not cover: habit and size are what tell one species from the
   other, and a crop throws both away. */
figure.shot img { display:block; width:100%; height:13rem;
  object-fit:contain; background:var(--band); }
figure.shot figcaption { padding:.4em .6em .55em; font-size:.82rem; }
.verdict { letter-spacing:.06em; font-size:.74rem; font-weight:700; }
.verdict.y { color:var(--yes); } .verdict.n { color:var(--crit); }
.cred { display:block; color:var(--muted); font-size:.7rem; margin-top:.2em;
  line-height:1.4; }
.nopic { padding:1.4em .9em; background:var(--band); color:var(--muted);
  font-size:.84rem; }
table.lines { border-collapse:collapse; width:100%; font-size:.88rem; }
table.lines td { padding:.45em .5em; border-bottom:1px solid var(--rule);
  vertical-align:top; }
table.lines td.c { white-space:nowrap; color:var(--muted); }
.cuts { display:flex; flex-wrap:wrap; gap:.6em; margin:.8em 0; }
.cutshot { margin:0; width:9rem; border:2px solid var(--crit);
  border-radius:8px; overflow:hidden; opacity:.85; }
.cutshot img { display:block; width:100%; height:6rem; object-fit:contain;
  background:var(--band); filter:grayscale(.45); }
.cutshot figcaption { padding:.35em .5em .5em; font-size:.74rem;
  line-height:1.35; }
"""


def _e(s):
    return html.escape(str(s), quote=False)


def lbj(binomial):
    """The Wildflower Center page for a species, as the fallback for no photo."""
    return ("https://www.wildflower.org/plants/search.php?search_field="
            + binomial.replace(" ", "+").replace("'", "") + "&newsearch=true")


def genera(design):
    """Every genus the design names, as the only ones an abbreviation may mean."""
    out = {}
    for p in design.get("plants", []):
        for b in plants.binomials(p):
            out.setdefault(b.split()[0][0], set()).add(b.split()[0])
    return out


def binomials_in(text, known_genera):
    """Every species named in one field, abbreviations expanded.

    Only a genus the design already names is recognised. That restraint is the
    point: a loose "Capitalised lowercase" pattern reads "Austin this" as a
    species, and a card that invents a plant is worse than one that misses a
    trap somebody never wrote down.
    """
    found, full = [], {}
    for g in {x for s in known_genera.values() for x in s}:
        for m in re.finditer(rf"\b{re.escape(g)}\s+([a-z]{{3,}})"
                             rf"(?:\s+var\.\s+[a-z]+)?", text):
            if m.group(1) in NOT_AN_EPITHET:
                continue
            name = " ".join(m.group(0).split())
            full[m.start()] = name
            found.append((m.start(), name))
    for m in ABBREV.finditer(text):
        initial, epithet = m.group(1), m.group(2)
        options = known_genera.get(initial) or set()
        # Prefer a genus already spelled out earlier in this same field, which
        # is how these sentences are actually written.
        before = [n for pos, n in sorted(full.items()) if pos < m.start()]
        pick = next((n.split()[0] for n in reversed(before)
                     if n.split()[0][0] == initial), None)
        if not pick and len(options) == 1:
            pick = next(iter(options))
        if pick:
            found.append((m.start(), f"{pick} {epithet}"))
    seen, out = set(), []
    for _, name in sorted(found):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def cut_names(design):
    """The plants that left the design, by the name a bench label would use."""
    out = []
    for c in design.get("cut_and_why", []) or []:
        name = CUT_STOP.sub("", c.get("item", "")).strip()
        name = re.sub(r"\s+x\d+$", "", name).strip()
        if name:
            out.append((name, c.get("reason", "")))
    return out


def find_traps(slug, data, task):
    """Every name trap the record states, and the field that states it.

    A field is read whole and then split BY GENUS, which is what a name trap
    actually is: one common name covering two species of the same genus. Two
    things fall out of grouping that way rather than by sentence.

    One long `ask` field states three separate traps — the milkweed, the yucca
    and the sage — and by genus they come apart correctly, where one panel
    naming all six species would be unusable at a nursery counter.

    And a sentence like "Same trap as the Yucca above" contributes a Yucca
    with nothing to buy beside it, so it produces no panel. A trap needs both
    halves by definition, which is a stronger filter than any word list.
    """
    design = yards.load(slug, "design.json") or {}
    known = genera(design)
    idx = plants.index(design)
    wanted = {b: p for p in data["plants"] for b in p["binomials"]}
    cuts = cut_names(design)
    lines = {b["id"]: b for b in data["shopping"]}

    units = [(f"the call script, step {i + 1}", str(h))
             for i, h in enumerate(task.get("how", []) or [])]
    for bid in task.get("buy", []) or []:
        b = lines.get(bid)
        if not b:
            continue
        for field in ("ask", "note", "pin"):
            if b.get(field):
                units.append((f"{bid} &middot; {field}", b[field]))

    # Keyed on what to buy, not on the field it was said in. The yucca trap is
    # stated twice — the script says "NOT Y. pendula" and the order line says
    # "NOT Y. recurvifolia" — and those are two wrong names for one decision.
    # Two panels would make a reader at a counter check the same plant twice.
    merged = {}
    for where, text in units:
        by_genus = {}
        for n in binomials_in(text, known):
            by_genus.setdefault(n.split()[0], []).append(n)
        for genus, names in by_genus.items():
            buy = sorted({n for n in names if n in wanted})
            refuse = sorted({n for n in names if n not in wanted})
            if not buy or not refuse:
                continue
            trap = merged.setdefault((genus, tuple(buy)), {
                "genus": genus, "buy": buy, "refuse": [], "said": [],
                "plants": [wanted[n] for n in buy],
                "common": sorted({n for b in buy for p in [wanted[b]]
                                  for n in p["names"]}, key=len)[:1],
            })
            for r in refuse:
                if r not in trap["refuse"]:
                    trap["refuse"].append(r)
            trap["said"].append((where, text))
    traps = list(merged.values())
    # Named in the call and dropped from the design. Not a genus trap, because
    # the two plants need not be related; reported once for the whole call so
    # the same warning does not appear beside three different panels.
    text = " ".join(t for _, t in units)
    dropped = [(n, why) for n, why in cuts
               if re.search(rf"\b{re.escape(n)}\b", text, re.I)]
    return traps, dropped


def species(slug):
    """Every binomial a card would want a photograph of, design or not.

    `lib.plantphotos` asks for this so the refused species get fetched too. A
    trap panel with a picture of the right plant and an empty box where the
    wrong one goes is half a warning.
    """
    data = bundle.build(slug)
    out = []
    for t in data["tasks"]:
        if t.get("kind") != "call":
            continue
        traps, _ = find_traps(slug, data, t)
        for trap in traps:
            for b in trap["buy"] + trap["refuse"]:
                if b not in out:
                    out.append(b)
    return out


def _shot(names, verdict, creds):
    """One picture for one plant, however many names the trade gives it.

    `names` is a list because two of them can be the same plant: "Yucca
    pendula" is what the trade calls *Yucca recurvifolia*, and both resolve to
    the same Commons file. Rendering that twice looks like a mistake in the
    card and hides the useful fact, which is that they are one plant.

    When the article the photograph came from is not the binomial that was
    asked for, the caption says so. A silent substitution is the exact error
    this page exists to prevent, and it would be perverse to commit it here.
    """
    cls, word = ("y", "BUY THIS") if verdict else ("n", "REFUSE THIS")
    shown = " = ".join(f"<i>{_e(n)}</i>" for n in names)
    cap = f'<span class="verdict {cls}">{word}</span> {shown}'
    if len(names) > 1:
        cap += "<br>The same plant under two names."

    rec = next((creds[n] for n in names
                if (creds.get(n) or {}).get("image")), None)
    if not rec:
        return (f'<figure class="shot"><div class="nopic">No photograph on '
                f'Wikimedia Commons carries '
                f'{"either binomial" if len(names) > 1 else "that binomial"}, '
                f'and none is borrowed from a neighbouring species. '
                f'<a href="{lbj(names[0])}">See the Wildflower Center</a>.'
                f'</div><figcaption>{cap}</figcaption></figure>')

    art = rec.get("article")
    if art and art not in names:
        cap += f"<br>Photographed as <i>{_e(art)}</i>."
    src = rec.get("web") or rec["image"]
    return (f'<figure class="shot"><a href="{_e(rec.get("commons") or "#")}">'
            f'<img src="{_e(src)}" alt="{_e(names[0])}" loading="lazy"></a>'
            f'<figcaption>{cap}<span class="cred">{_e(rec.get("artist"))} '
            f'&middot; {_e(rec.get("licence"))} &middot; '
            f'<a href="{lbj(names[0])}">Wildflower Center</a></span>'
            f'</figcaption></figure>')


def _same_plant(names, creds):
    """Group names that Wikimedia resolved to the very same photograph."""
    groups, order = {}, []
    for n in names:
        rec = creds.get(n) or {}
        key = rec.get("file") or n
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(n)
    return [groups[k] for k in order]


def _trap_html(trap, creds):
    say = trap["common"][0].title() if trap["common"] else trap["buy"][0]
    count = sum(p.get("count", 0) for p in trap["plants"])
    beds = sorted({p.get("zone", "") for p in trap["plants"]} - {""})
    yes = "".join(_shot(g, True, creds)
                  for g in _same_plant(trap["buy"], creds))
    no = "".join(_shot(g, False, creds)
                 for g in _same_plant(trap["refuse"], creds))
    return f"""
<details class="trap" open>
<summary><span class="say">{_e(say)}</span>
<span class="binom">{" or ".join(_e(b) for b in trap["buy"])}</span>
<span class="qty">&times;{count}{" &middot; " + ", ".join(
    _e(b.replace("bed_", "")) for b in beds) if beds else ""}</span></summary>
<div class="body">
{"".join(f'<div class="quote">{_e(text)}'
         f'<cite>The record&rsquo;s own words, from {where}.</cite></div>'
         for where, text in trap["said"])}
<div class="pics"><div class="col yescol">{yes}</div>
<div class="col nocol">{no}</div></div>
</div></details>"""


def _call_html(slug, data, task, creds, shops):
    shop = shops.get((task.get("where") or {}).get("supplier")) or {}
    lines = {b["id"]: b for b in data["shopping"]}
    traps, dropped = find_traps(slug, data, task)

    tel = ""
    if shop.get("phone"):
        digits = "+1" + re.sub(r"\D", "", shop["phone"])[-10:]
        tel = (f'<div class="shopcard"><a class="tel" href="tel:{digits}">'
               f'{_e(shop["phone"])}</a><div class="meta">'
               f'{_e(shop.get("name"))} &middot; {_e(shop.get("address"))}'
               + (f' &middot; {_e(shop["hours"])}' if shop.get("hours") else "")
               + (f' &middot; {shop["distance_mi"]} mi'
                  if shop.get("distance_mi") else "") + "</div></div>")

    script = "".join(f"<li>{_e(h)}</li>" for h in task.get("how", []) or [])

    rows = ""
    for bid in task.get("buy", []) or []:
        b = lines.get(bid)
        if not b:
            continue
        lo, hi = (b.get("cost_usd") or [None, None])[:2]
        cost = "not priced" if lo is None else (
            f"${lo:,.0f}" if lo == hi else f"${lo:,.0f}\u2013{hi:,.0f}")
        rows += (f'<tr><td><b>{_e(b["item"])}</b><br>{_e(b.get("ask") or "")}'
                 f'</td><td class="c">{cost}<br>by '
                 f'{datetime.date.fromisoformat(b["by"]):%-d %b}</td></tr>')

    cards = [c for c in data["doubts"]
             if c["id"] in (task.get("doubts") or [])]
    doubts = ""
    if cards:
        doubts = "<h3>The open question this call settles</h3>" + "".join(
            f'<div class="quote"><b>{_e(c["id"])}</b> {_e(c["question"])}'
            f'<cite>How to settle it: {_e(c.get("how_to_settle") or "")}</cite>'
            f"</div>" for c in cards)

    when = (f'{datetime.date.fromisoformat(task["date"]):%A %-d %B}'
            if task.get("date") else task.get("when", ""))
    return f"""
<section class="call" id="{_e(task['id'])}">
<header><h2>{_e(task['title'])}</h2>
<p>{when} &middot; {task.get('minutes', 0)} minutes &middot;
<a href="TASKS.html#{_e(task['id'])}"
   style="color:#cfdccf">{_e(task['id'])} in full</a></p></header>
<div class="inner">
{tel}
<h3>Ask these {len(task.get('how', []) or [])} things, in this order</h3>
<ol class="script">{script}</ol>
{f'<h3>The name traps, with pictures</h3><p class="sub">Say the binomial. '
  f'Write down the binomial on their bench tag, not the common name.</p>'
  + "".join(_trap_html(t, creds) for t in traps) if traps else ''}
{f'<div class="quote"><b>Named in this call and no longer in the design:</b> '
  + ", ".join(_e(n) for n, _ in dropped)
  + f'. Refuse {"them" if len(dropped) > 1 else "it"} however good '
    f'{"they look" if len(dropped) > 1 else "it looks"} on the bench.'
  + '</div>' if dropped else ''}
<h3>What is on this order</h3>
<table class="lines">{rows}</table>
{doubts}
</div></section>"""


def build(slug, data=None, tasks=None, link_images=False):
    """The page, covering every call still ahead."""
    data = data or bundle.build(slug)
    root = yards.yard_dir(slug)
    creds = plants.credits(slug)
    shops = {s["id"]: s for s in data["suppliers"]}
    design = yards.load(slug, "design.json") or {}

    calls = [t for t in data["tasks"]
             if t.get("kind") == "call" and not t.get("done")]
    if tasks:
        calls = [t for t in data["tasks"] if t["id"] in tasks]
    calls.sort(key=lambda t: t.get("date") or "9999")
    if not calls:
        return None

    body = "".join(_call_html(slug, data, t, creds, shops) for t in calls)

    cuts = ""
    dropped = cut_names(design)
    if dropped:
        shots = ""
        for name, why in dropped:
            found = plants.match(name, plants.index(design))
            pic = None
            for _, ps in found:
                pic = plants.photo_for(plants.binomials(ps[0]), creds)
                if pic:
                    break
            img = (f'<img src="{_e(pic.get("web") or pic["image"])}" '
                   f'alt="{_e(name)}" loading="lazy">' if pic else
                   '<div class="nopic" style="padding:2em .5em;'
                   'text-align:center;font-size:.72rem">no photograph</div>')
            shots += (f'<figure class="cutshot">{img}<figcaption>'
                      f'<b>{_e(name)}</b></figcaption></figure>')
        cuts = (f'<h2>What to refuse outright</h2><p class="sub">'
                f'{len(dropped)} plants left this design. They are on nobody'
                f'&rsquo;s list now, however good they look on the bench. '
                f'Why each went is in <a href="CHANGELOG.html">the log</a>.'
                f'</p><div class="cuts">{shots}</div>')

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(data['yard']['name'])} &mdash; the nursery calls</title>
<style>{chrome.BASE_CSS}{chrome.NAV_CSS}{CARD_CSS}</style>
</head>
<body>
{chrome.nav(root, OUT, data['yard']['name'])}
<div class="wrap">
<h1>The nursery calls</h1>
<p class="sub">{len(calls)} call{"s" if len(calls) != 1 else ""} still ahead.
Every trap below was found in this yard&rsquo;s own record, in the field
quoted with it.</p>
{body}
{cuts}
<footer>
<p>Built on {data['built']} by <code>python3 -m lib.callcard {_e(slug)}</code>.
The script, the order and the prices come from <code>tasks.json</code>; the
shop from <code>sourcing.json</code>; the counts and beds from
<code>design.json</code>. Correct one of those and this page follows.</p>
<p>Photographs are from Wikimedia Commons under the licence printed with each.
A species with no verified photograph of that exact binomial shows none and
links to the Wildflower Center instead, because a mislabelled picture here
would cause the exact mistake this page exists to prevent.</p>
</footer>
</div>
</body>
</html>
"""
    if not link_images:
        page = buildhtml.embed_images(page, root)
    return page


def build_all(slug, data=None, link_images=False):
    """Write the card, and report the paths written."""
    page = build(slug, data=data, link_images=link_images)
    if not page:
        return []
    return [yards.write_text(slug, OUT, page)]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--task", nargs="+", help="only these call tasks")
    ap.add_argument("--traps", action="store_true",
                    help="what the record states, and where it states it")
    ap.add_argument("--link", action="store_true")
    args = ap.parse_args()

    data = bundle.build(args.slug)

    if args.traps:
        calls = [t for t in data["tasks"] if t.get("kind") == "call"]
        for t in calls:
            traps, dropped = find_traps(args.slug, data, t)
            print(f"\n  {t['id']}  {t['title']}  — {len(traps)} trap(s)")
            for tr in traps:
                print(f"      {tr['genus']}: buy {', '.join(tr['buy'])}")
                print(f"      {'':{len(tr['genus'])}}  refuse "
                      f"{', '.join(tr['refuse'])}")
                for where, _ in tr["said"]:
                    print(f"      said in {where.replace('&middot;', ':')}")
            if dropped:
                print(f"      also named, dropped from the design: "
                      f"{', '.join(n for n, _ in dropped)}")
        missing = [b for b in species(args.slug)
                   if not (plants.credits(args.slug).get(b) or {}).get("image")]
        if missing:
            print(f"\n  {len(missing)} species on a trap have no photograph: "
                  f"{', '.join(missing)}")
            print(f"  python3 -m lib.plantphotos {args.slug}")
        return

    page = build(args.slug, data=data, tasks=args.task,
                 link_images=args.link)
    if not page:
        print(f"  {args.slug} has no call still ahead")
        return
    path = yards.write_text(args.slug, OUT, page)
    print(f"wrote {path}  ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
