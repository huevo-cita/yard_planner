#!/usr/bin/env python3
"""Build a yard's whole set of pages, and the page that ties them together.

    python3 -m lib.site cloverleaf-austin            build everything
    python3 -m lib.site cloverleaf-austin --index    just INDEX.html
    python3 -m lib.site cloverleaf-austin --link     images by path, not embedded

`INDEX.html` is the front door: what this yard is, what is happening now, and
every other page grouped by the question it answers.

The rule the whole set is built on, and the reason this module refuses to hold
any prose of its own: **a page links to what is written elsewhere, it never
repeats it.** The alternative was tried. A task page that inlines the sowing
technique is easier to read exactly once, and then the technique is in two
files, and the day one is corrected the other becomes a trap — with no way for
a reader to tell which one they are holding. So the index describes a document
in one line and links to it, and a task page links to the section that explains
it. Nothing here is a second copy of anything.
"""
import argparse
import datetime
import glob
import html
import os

from . import bundle, chrome, yards

INDEX = "INDEX.html"

INDEX_CSS = """
.hero { background:var(--band); border:1px solid var(--rule);
  border-radius:10px; padding:1em 1.2em; margin:0 0 1.4em; }
.hero h1 { margin:0 0 .1em; }
.hero p { margin:.3em 0; }
.hero .big { font-size:1.05rem; }
.hero a.go { display:inline-block; margin-top:.7em; background:var(--accent);
  color:#fff; text-decoration:none; padding:.5em 1.1em; border-radius:999px;
  font-size:.92rem; font-weight:600; }
.hero a.go:hover { background:#24482a; }

.cards { display:flex; flex-wrap:wrap; gap:.6em; margin:.6em 0 0; }
.card { flex:1 1 15rem; border:1px solid var(--rule); border-radius:10px;
  padding:.75em .95em; text-decoration:none; color:inherit; display:block; }
.card:hover { border-color:var(--accent); background:var(--band); }
.card b { display:block; font-size:1rem; color:var(--accent); }
.card span { display:block; color:var(--muted); font-size:.85rem;
  margin-top:.15em; }
.card em { display:block; color:var(--muted); font-size:.75rem;
  font-style:normal; margin-top:.4em; }

.stats { display:flex; flex-wrap:wrap; gap:.5em; margin:0 0 1.2em; }
.stat { flex:1 1 7rem; background:var(--band); border:1px solid var(--rule);
  border-radius:8px; padding:.5em .75em; }
.stat b { display:block; font-size:1.3rem; line-height:1.15;
  font-variant-numeric:tabular-nums; }
.stat span { color:var(--muted); font-size:.74rem; text-transform:uppercase;
  letter-spacing:.05em; }

ul.doubts { list-style:none; padding:0; margin:.4em 0; }
ul.doubts li { border-left:3px solid var(--warnline); background:#fffbeb;
  padding:.5em .8em; margin:.4em 0; border-radius:0 6px 6px 0;
  font-size:.92rem; }
ul.doubts li code { background:#fff; }
ul.doubts li span { display:block; color:var(--muted); font-size:.82rem;
  margin-top:.15em; }

/* One of these is shown, and the script picks which. The hero used to hold
   the build week's hours, which stopped being true the following Monday. */
.hero .wknow { display:none; }
.hero .wknow.on { display:block; }
"""

#: The hero, corrected by the device clock.
#:
#: Python writes a paragraph for every week and this shows one of them. It
#: writes nothing itself, so the front door cannot say an hours figure the
#: week page disagrees with.
INDEX_JS = """
(function () {
  var blocks = [].slice.call(document.querySelectorAll('.hero .wknow'));
  if (!blocks.length) return;
  var id = yard.weekId(yard.today()), found = false;
  blocks.forEach(function (b) {
    var on = b.getAttribute('data-week') === id;
    b.classList.toggle('on', on);
    found = found || on;
  });
  if (found) return;
  var out = document.getElementById('hwout');
  if (out) out.classList.add('on');
})();
"""


def _e(s):
    return html.escape(str(s), quote=False)


def _stat(value, label):
    return f'<div class="stat"><b>{_e(value)}</b><span>{_e(label)}</span></div>'


def _card(href, title, blurb, note=None):
    return (f'<a class="card" href="{_e(href)}"><b>{_e(title)}</b>'
            f'<span>{_e(blurb)}</span>'
            + (f"<em>{_e(note)}</em>" if note else "") + "</a>")


def _hero_week(tasks, w, target, target_note):
    """What one week is, in the two or three lines the front door can afford.

    Written for every week of the plan, because the page is opened on a day
    the build cannot know. The distance to the target is counted in weeks
    rather than in days for the same reason: a week's worth of prose is true
    for that whole week.
    """
    from . import week

    monday = week._date(w["monday"])
    grid, loose = week.week_grid(tasks, monday)
    buys = week.buys_for(tasks, monday)
    shape = week.week_shape(grid, loose, buys)

    out = []
    if w["beyond"]:
        nxt = week.next_work(tasks, week._date(w["sunday"]))
        out.append('<p class="big">This week is past the end of the plan.</p>')
        out.append(f'<p>The plan runs to {target:%-d %B %Y}'
                   + (f' &mdash; {_e(target_note)}' if target_note else "")
                   + ". Nobody has planned this week yet.</p>")
        if nxt:
            day, t = nxt
            out.append(f'<p>The next dated job is '
                       f'<a href="TASKS.html#{_e(t["id"])}">{_e(t["title"])}'
                       f'</a>, on {day:%-d %B %Y}.</p>')
        return "".join(out)

    out.append(f'<p class="big">{week.hours(shape["fixed"])} of dated work '
               f'this week, across {shape["jobs"]} job'
               f'{"s" if shape["jobs"] != 1 else ""}.</p>')
    if shape["critical"]:
        d, t = shape["critical"][0]
        out.append(f'<p><b>{d:%A}</b> carries work that cannot slip: '
                   f'{_e(t["title"])}.</p>')
    if shape["buys"]:
        first = min(shape["buys"], key=lambda b: b["by"])
        out.append(f'<p>{len(shape["buys"])} thing'
                   f'{"s" if len(shape["buys"]) > 1 else ""} to buy, the first '
                   f'by {week._date(first["by"]):%A}.</p>')
    if not shape["critical"] and not shape["buys"] and not shape["fixed"]:
        out.append("<p>Nothing is dated to this week.</p>")
    if target:
        weeks = (week.monday_of(target) - monday).days // 7
        when = ("this week" if weeks == 0 else
                "last week" if weeks == -1 else
                f"{-weeks} weeks ago" if weeks < 0 else
                "next week" if weeks == 1 else f"{weeks} weeks away")
        out.append(f'<p>{target:%-d %B} is {when}'
                   + (f' &mdash; {_e(target_note)}' if target_note else "")
                   + ".</p>")
    return "".join(out)


def render_index(slug, data=None, today=None):
    """The front door, built from the bundle so it cannot contradict a page."""
    from . import week

    data = data or bundle.build(slug)
    root = yards.yard_dir(slug)
    today = today or datetime.date.today()
    monday = week.monday_of(today)
    tasks = week.load(slug) or {}
    ahead = [t for t in data["tasks"] if not t.get("done")]

    # What is happening now, for every week the plan holds, with the script
    # showing the one the device clock asks for. Baking the build week's
    # hours in here is the defect this page shares with WEEK.html.
    target = (datetime.date.fromisoformat(data["yard"]["target_date"])
              if data["yard"].get("target_date") else None)
    target_note = data["yard"].get("target_note")
    here = week.week_id(monday)
    now = []
    for w in data["weeks"]:
        on = " on" if w["id"] == here else ""
        now.append(f'<div class="wknow{on}" data-week="{w["id"]}">'
                   + _hero_week(tasks, w, target, target_note) + "</div>")
    span = ""
    if data["weeks"]:
        a = week._date(data["weeks"][0]["monday"])
        z = week._date(data["weeks"][-1]["sunday"])
        span = (f'<p>The plan covers {a:%-d %B %Y} to {z:%-d %B %Y}.</p>')
    outside = any(w["id"] == here for w in data["weeks"])
    now.append(f'<div class="wknow{"" if outside else " on"}" id="hwout">'
               f'<p class="big">Today is outside this plan.</p>{span}</div>')

    stats = (_stat(len(ahead), "jobs still to do")
             + _stat(len([b for b in data["shopping"]]), "things to buy")
             + _stat(len(data["plants"]), "plants in the design")
             + _stat(len(data["doubts"]), "open questions"))

    # --- the screens, grouped by the question each answers ---
    def exists(name):
        return os.path.exists(os.path.join(root, name))

    act = []
    if exists("WEEK.html"):
        act.append(_card("WEEK.html", "This week",
                         "The seven days in front of you, with the detail "
                         "behind a click.",
                         "follows the clock, so it rolls over on its own"))
    if exists("CALENDAR.html"):
        act.append(_card("CALENDAR.html", "The calendar",
                         "Every week from here to the end, one line each.",
                         f"{len(data['tasks'])} jobs in all"))
    if exists("TASKS.html"):
        act.append(_card("TASKS.html", "Every job, in full",
                         "How to do each one, what gates it, what to do if "
                         "the window closes."))
    if exists("CALL-CARD.html"):
        act.append(_card("CALL-CARD.html", "The nursery calls",
                         "What to ask for by binomial, with a photograph of "
                         "every name trap."))

    read, record = [], []
    for d in data["documents"]:
        if not d["published"]:
            continue
        note = f"{len([s for s in d['sections'] if s['level'] == 2])} sections"
        card = _card(d["html"], d["title"], d["blurb"] or "", note)
        (record if d["file"] == "CHANGELOG.md" else read).append(card)

    doubts = ""
    if data["doubts"]:
        # The id is the anchor a task page links to, so a doubt cited from a
        # job lands on the card rather than at the top of the page.
        items = "".join(
            f'<li id="{_e(c["id"])}"><code>{_e(c["id"])}</code> '
            f'{_e(c["question"])}'
            f'<span>Blocks {_e(", ".join(c.get("blocks") or ["nothing"]))}'
            f' &middot; {_e(c.get("effort") or "effort not recorded")}</span>'
            f"</li>" for c in data["doubts"])
        doubts = (f"<h2>Open questions</h2><p class=\"sub\">Nobody has settled "
                  f"these, and the jobs they block will refuse to run until "
                  f"somebody does.</p><ul class=\"doubts\">{items}</ul>")

    sandbox = ""
    if data["yard"].get("sandbox"):
        sandbox = (f'<div class="warn"><b>{_e(data["yard"]["sandbox"])}</b> '
                   f'&mdash; a rehearsal copy. Nothing here describes the '
                   f'real yard.</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(data['yard']['name'])} &mdash; the yard</title>
<style>{chrome.BASE_CSS}{chrome.NAV_CSS}{chrome.STALE_CSS}{INDEX_CSS}</style>
</head>
<body>
{chrome.nav(root, INDEX, data['yard']['name'])}
<div class="wrap">
{sandbox}
{chrome.stale_banner(slug, data['built'])}
<div class="hero">
<h1>{_e(data['yard']['name'])}</h1>
{''.join(now)}
<a class="go" href="WEEK.html">What to do this week &rarr;</a>
</div>

<div class="stats">{stats}</div>

<h2>Act on it</h2>
<div class="cards">{''.join(act)}</div>

<h2>Look it up</h2>
<p class="sub">Every number and every method lives in one of these, and every
page above links into them rather than repeating them.</p>
<div class="cards">{''.join(read)}</div>

<h2>The record</h2>
<div class="cards">{''.join(record)}</div>
{doubts}

<footer>
<p>Built from <code>bundle.json</code> on {data['built']} by
<code>python3 -m lib.site {_e(slug)}</code>. Every page in this set is
generated from the same bundle, so two of them cannot disagree about a date.</p>
<p>The lines above follow this device's clock, and a banner appears when the
build is more than {chrome.STALE_DAYS} days old. What the plan holds still
comes from the day it was built.</p>
<p>Nothing on any page is a copy of prose that lives somewhere else. A link
into a document is the document; correct it once and every page follows.</p>
</footer>

</div>
{chrome.dates_js()}
<script>
{INDEX_JS}
{chrome.STALE_JS}
</script>
</body>
</html>
"""


def build_all(slug, link_images=False, today=None):
    """Every page this yard publishes, in the order their links need.

    Markdown first, because the nav only offers a screen whose file is already
    on disk, and the index counts sections out of the published pages.
    """
    from . import buildhtml, callcard, week

    root = yards.yard_dir(slug)
    made = []

    # Say up front what this build will produce, so the first page written
    # carries a bar that reaches the last one.
    chrome.planned({INDEX, "WEEK.html", "TASKS.html", "CALENDAR.html"}
                   | ({"CALL-CARD.html"}
                      if any(t.get("kind") == "call" and not t.get("done")
                             for t in (yards.load(slug, "tasks.json")
                                       or {}).get("tasks", []))
                      else set()))

    for md in sorted(glob.glob(os.path.join(root, "*.md"))):
        if os.path.basename(md) == "CALENDAR.md":
            continue                 # an intermediate for the Doc, not a page
        out, _, _ = buildhtml.convert(md, link_images=link_images)
        made.append(os.path.basename(out))

    data = bundle.build(slug)
    bundle.write(slug)

    monday = week.monday_of(today or datetime.date.today())
    for name, text in (
            ("WEEK.html", week.render_week_html(slug, monday, today=today)),
            ("TASKS.html", week.render_tasks_html(slug, data=data)),
            ("CALENDAR.html", week.render_calendar_html(slug, data=data,
                                                        today=today))):
        yards.write_text(slug, name, text)
        made.append(name)

    card = callcard.build_all(slug, data=data)
    made += [os.path.basename(p) for p in card]

    # Last, because it reports on what exists and links only to what does.
    # Rebuilt from a fresh bundle so the section counts it quotes come from
    # the pages this run actually wrote.
    data = bundle.build(slug)
    yards.write_text(slug, INDEX, render_index(slug, data=data, today=today))
    made.append(INDEX)
    chrome.planned(())
    return made, data


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--index", action="store_true",
                    help="only rebuild INDEX.html")
    ap.add_argument("--link", action="store_true",
                    help="reference images by path instead of embedding them")
    args = ap.parse_args()

    root = yards.yard_dir(args.slug)
    if args.index:
        yards.write_text(args.slug, INDEX, render_index(args.slug))
        print(f"wrote {os.path.join(root, INDEX)}")
        return

    made, data = build_all(args.slug, link_images=args.link)
    print(f"  {root}/")
    for name in made:
        kb = os.path.getsize(os.path.join(root, name)) // 1024
        print(f"      {name:34s} {kb:5d} KB")
    broken = [l for t in data["tasks"] for l in t["links"] if l["error"]]
    if broken:
        print(f"\n  {len(broken)} reference(s) resolve to nothing. "
              f"`python3 -m lib.week {args.slug} --links`")


if __name__ == "__main__":
    main()
