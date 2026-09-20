#!/usr/bin/env python3
"""The bar across the top of every page, and the look they share.

A yard publishes a dozen HTML files. Before this they were a dozen unrelated
documents: you opened one, read it, and had no way to reach the others except
by going back to the folder. That is workable on a laptop and useless on a
phone, which is where these are actually read.

So every generated page carries the same nav, built here, from one list. One
consequence is worth stating because it is the reason this is a module rather
than a string copied into four renderers: when a screen is added, it appears
everywhere, and when it is renamed it is renamed everywhere. Four copies of a
nav is three chances to link to a page that no longer exists.

The order is the order somebody needs them in — what do I do now, then when,
then how, then where to buy it, then why it says that — and not alphabetical.
"""
import os

#: (file, short label, long label). The short one is what the bar shows on a
#: phone; the long one is the title attribute and the index heading.
SCREENS = [
    ("INDEX.html", "Yard", "Everything about this yard"),
    ("WEEK.html", "This week", "The seven days in front of you"),
    ("CALENDAR.html", "Calendar", "Every week, start to finish"),
    ("TASKS.html", "Tasks", "Every job, in full"),
    ("CALL-CARD.html", "Calls", "What to ask a nursery, with pictures"),
    ("PLAN.md", "Plan", "The beds, the water, the budget"),
    ("SOWING-CALENDAR.md", "Bed", "The raised bed, square by square"),
    ("SOURCING.md", "Buying", "Prices, shops and confidence"),
    ("SITE-WALK.md", "Site walk", "What to measure on foot"),
    ("CHANGELOG.md", "Log", "Why any of it reads this way"),
]

#: The shell every generated page sits in: the palette, the column, the
#: footer. Kept apart from each page's own rules so that "all our pages look
#: like each other" is enforced by one file rather than by care.
BASE_CSS = """
:root { --ink:#1a1a1a; --muted:#5c5c5c; --rule:#dcdcdc; --accent:#2f5d34;
        --band:#f6f7f4; --warnline:#b45309; --crit:#a52121; --yes:#1b6b2f; }
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:#fff; color:var(--ink);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
.wrap { max-width:58rem; margin:0 auto; padding:.4rem 1.1rem 5rem; }
h1 { font-size:1.75rem; margin:.4em 0 .1em; letter-spacing:-.02em; }
h2 { font-size:1.12rem; margin:2em 0 .5em; padding-bottom:.2rem;
  border-bottom:2px solid var(--accent); }
h3 { font-size:.95rem; margin:1.4em 0 .4em; color:var(--accent); }
p.sub { margin:0 0 1.2em; color:var(--muted); }
a { color:var(--accent); }
code { font:.87em ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--band); padding:.1em .3em; border-radius:3px; }
.warn { border-left:4px solid var(--warnline); background:#fef3c7;
  color:#78350f; padding:.7em 1em; border-radius:0 8px 8px 0; margin:1em 0; }
footer { margin-top:2.5rem; padding-top:1em; border-top:1px solid var(--rule);
  color:var(--muted); font-size:.8rem; }
footer p { margin:.5em 0; }
@media (max-width:640px) { .wrap { padding:.3rem .7rem 3rem; }
  h1 { font-size:1.35rem; } }
"""

NAV_CSS = """
nav.screens { position:sticky; top:0; z-index:20; display:flex; gap:.1em;
  overflow-x:auto; background:#24482a; margin:0 0 1.4rem;
  padding:0 .3em; scrollbar-width:none; -webkit-overflow-scrolling:touch; }
nav.screens::-webkit-scrollbar { display:none; }
nav.screens a { flex:0 0 auto; color:#cfdccf; text-decoration:none;
  font-size:.82rem; letter-spacing:.02em; padding:.7em .85em;
  white-space:nowrap; border-bottom:3px solid transparent; }
nav.screens a:hover { color:#fff; background:rgba(255,255,255,.08); }
nav.screens a.here { color:#fff; font-weight:650;
  border-bottom-color:#cfdccf; }
nav.screens span.brand { flex:0 0 auto; color:#8fae93; font-size:.72rem;
  text-transform:uppercase; letter-spacing:.09em; padding:.95em .7em .7em .4em;
  white-space:nowrap; }
@media (max-width:640px) { nav.screens span.brand { display:none; } }
@media print { nav.screens { display:none; } }
"""


#: How old a page may be before it says so, in days.
#:
#: A generated page is a photograph of `bundle.json` on the day it was built.
#: The week it shows rolls over on its own, but the jobs, the dates and the
#: prices in it do not. Fourteen days is one fortnight: long enough that a page
#: in normal use never shows the banner, and short enough that a plan a month
#: behind says so before somebody acts on it.
STALE_DAYS = 14

STALE_CSS = """
.stale { border-left:4px solid var(--warnline); background:#fef3c7;
  color:#78350f; padding:.7em 1em; border-radius:0 8px 8px 0; margin:1em 0; }
.stale b { display:block; }
.stale code { background:#fff8e1; }
"""

#: Date arithmetic for every page, and the only computation any of them do.
#:
#: The pages hold the answers and none of the rules. Python renders every week
#: and every sentence about it; this decides which of them the device clock
#: asks for. Keeping that to four functions with no DOM in them is what lets
#: `tools/test_week.py` run them in node and compare the result against the
#: ids Python wrote.
#:
#: A date is a `YYYY-MM-DD` string throughout, and the arithmetic runs in UTC
#: so that a daylight-saving change cannot move a Monday. Only `today()` reads
#: the local clock, because the day a person is having is a local fact.
DATES_JS = """
var yard = window.yard || (window.yard = {});

yard.today = function (d) {
  d = d || new Date();
  var p = function (n) { return (n < 10 ? '0' : '') + n; };
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
};

yard.utc = function (iso) {
  return Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
};

yard.iso = function (ms) { return new Date(ms).toISOString().slice(0, 10); };

yard.mondayOf = function (iso) {
  var ms = yard.utc(iso);
  var dow = (new Date(ms).getUTCDay() + 6) % 7;
  return yard.iso(ms - dow * 86400000);
};

yard.weekId = function (iso) { return 'w' + yard.mondayOf(iso); };

yard.ageDays = function (from, to) {
  return Math.floor((yard.utc(to) - yard.utc(from)) / 86400000);
};

yard.isStale = function (built, now, limit) {
  return yard.ageDays(built, now) >= limit;
};
"""


def dates_js():
    """The date functions, at the id the tests read them back from."""
    return f'<script id="yard-dates">{DATES_JS}</script>'


def stale_banner(slug, built):
    """The banner a page shows when its data is old enough to have moved.

    Written out in full and hidden, rather than composed in the browser. The
    script fills in one number and drops the `hidden` attribute.
    """
    import datetime
    import html as _h
    day = datetime.date.fromisoformat(built)
    return (f'<div class="stale" id="stale" data-built="{built}" '
            f'data-days="{STALE_DAYS}" hidden>'
            f'<b>This page was built <span class="age">?</span> days ago, on '
            f'{day:%-d %B %Y}.</b>'
            f'The week below still follows the clock, and the jobs, dates and '
            f'prices on it are whatever <code>bundle.json</code> said that '
            f'day. Build it again with '
            f'<code>python3 -m lib.site {_h.escape(slug)}</code>, then open '
            f'this page again.</div>')


STALE_JS = """
(function () {
  var el = document.getElementById('stale');
  if (!el) return;
  var age = yard.ageDays(el.getAttribute('data-built'), yard.today());
  if (!yard.isStale(el.getAttribute('data-built'), yard.today(),
                    +el.getAttribute('data-days'))) return;
  var n = el.querySelector('.age');
  if (n) n.textContent = age;
  el.hidden = false;
})();
"""


TICKS_CSS = """
input.tick { flex:0 0 auto; width:1.15em; height:1.15em; margin:0 .1em 0 0;
  accent-color:var(--accent); cursor:pointer; }
.ticked { opacity:.55; }
.ticked .ttl, .ticked h3 { text-decoration:line-through; }
p.tools { margin:.2em 0 1em; display:flex; flex-wrap:wrap; gap:.4em;
  align-items:baseline; }
p.tools button { font:inherit; font-size:.84rem; cursor:pointer;
  background:var(--band); border:1px solid var(--rule); border-radius:999px;
  padding:.3em 1em; color:var(--accent); }
p.tools button:hover { background:#eceee8; border-color:var(--accent); }
p.tools .tally { color:var(--muted); font-size:.82rem; margin-left:auto; }
p.tools .tally b { color:var(--ink); }
textarea.dump { width:100%; height:9rem; font:12px/1.4 ui-monospace,Menlo,
  monospace; border:1px solid var(--rule); border-radius:8px; padding:.6em;
  margin:.3em 0 1em; display:none; }
@media print { p.tools { display:none; } }
"""


def ticks_js(slug, scope=None):
    """Checkboxes that survive closing the page, and can be read back in.

    The state of a job lives in `tasks.json`, which is the record. A browser
    cannot write to that, so the page does the next honest thing: it seeds
    every box from the file, keeps whatever you tick in `localStorage` for
    this yard alone, and hands the result back as text that
    `python3 -m lib.week <slug> --sync` already knows how to read.

    That round trip is the whole design. A tick that lives only in a browser
    is lost with the browser's cache and cannot reach next season's rotation
    log; a tick that has a way home is a record of what was actually done.

    `scope` is a selector that a box has to sit inside to be counted and
    copied. The week page needs it: it now holds every week of the plan, and a
    tally over all of them answers a question nobody asked. A tick is still
    stored and painted wherever it is, because the store is one record for the
    yard. Call `window.yardTally()` after showing a different week.
    """
    return """
(function () {
  var KEY = 'yard:%s:done', SCOPE = %s, store = {};
  try { store = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}

  var boxes = [].slice.call(document.querySelectorAll('input.tick'));
  if (!boxes.length) return;

  function holder(b) { return b.closest('article.task, details.job') || b; }
  function paint(b) { holder(b).classList.toggle('ticked', b.checked); }
  function counted(b) { return !SCOPE || b.closest(SCOPE); }

  // A standing job draws a box on every day it asks for work, so the same
  // task id appears several times on one page. Count each job once.
  function each_job(fn) {
    var seen = {};
    boxes.forEach(function (b) {
      if (seen[b.dataset.task] || !counted(b)) return;
      seen[b.dataset.task] = 1;
      fn(b);
    });
  }

  function twins(id) {
    return boxes.filter(function (b) { return b.dataset.task === id; });
  }

  function tally() {
    var total = 0, on = 0, moved = 0;
    each_job(function (b) {
      total++;
      if (b.checked) on++;
      if (b.checked !== (b.dataset.filed === '1')) moved++;
    });
    var el = document.getElementById('tally');
    if (el) el.innerHTML = '<b>' + on + '</b> of ' + total + ' done' +
      (moved ? ' \\u00b7 ' + moved + ' changed since the file' : '');
  }

  boxes.forEach(function (b) {
    var id = b.dataset.task;
    if (id in store) b.checked = !!store[id];
    // A box inside a <summary> would otherwise open the panel as well.
    b.addEventListener('click', function (e) { e.stopPropagation(); });
    b.addEventListener('change', function () {
      store[id] = b.checked;
      localStorage.setItem(KEY, JSON.stringify(store));
      twins(id).forEach(function (o) { o.checked = b.checked; paint(o); });
      tally();
    });
    paint(b);
  });
  tally();

  var out = document.getElementById('dump');
  var copy = document.getElementById('copy');
  if (copy) copy.addEventListener('click', function () {
    var lines = [];
    each_job(function (b) {
      lines.push('- [' + (b.checked ? 'x' : ' ') + '] **' +
                 b.dataset.title + '**');
    });
    var text = lines.join('\\n') + '\\n';
    if (out) { out.style.display = 'block'; out.value = text; out.select(); }
    if (navigator.clipboard) navigator.clipboard.writeText(text);
    copy.textContent = 'Copied \\u2014 save it and run --sync';
  });

  var reset = document.getElementById('reset');
  if (reset) reset.addEventListener('click', function () {
    localStorage.removeItem(KEY);
    boxes.forEach(function (b) {
      b.checked = b.dataset.filed === '1'; paint(b); });
    tally();
    if (out) out.style.display = 'none';
    if (copy) copy.textContent = 'Copy the done list';
  });

  window.yardTally = tally;
})();
""" % (slug, f"'{scope}'" if scope else "null")


def tick(task):
    """One checkbox, carrying what the file says so the page can compare."""
    import html as _h
    return (f'<input class="tick" type="checkbox" '
            f'data-task="{_h.escape(task["id"], quote=True)}" '
            f'data-title="{_h.escape(task["title"], quote=True)}" '
            f'data-filed="{1 if task.get("done") else 0}"'
            + (" checked" if task.get("done") else "") + ">")


def tools(extra=""):
    """The strip above a list of checkboxes."""
    return ('<p class="tools">'
            + extra
            + '<button type="button" id="copy">Copy the done list</button>'
            '<button type="button" id="reset">Reset to the file</button>'
            '<span class="tally" id="tally"></span></p>'
            '<textarea class="dump" id="dump" readonly '
            'aria-label="the done list, for --sync"></textarea>')


#: Screens a build has committed to writing but has not written yet.
#:
#: Without this the bar is wrong on exactly one run: the first one. Pages are
#: written in some order, and each is stamped with a bar built from what is on
#: disk at that moment, so the first page written offers none of the others.
#: Re-converting everything a second time would fix it and costs a second pass
#: over half a megabyte of change log. `lib.site` declares its intent here
#: instead, and a standalone `lib.buildhtml` run leaves this empty and falls
#: back to asking the filesystem, which is right when nothing is being built.
_PLANNED = set()


def planned(names):
    """Tell the bar which screens this build is about to write."""
    _PLANNED.clear()
    _PLANNED.update(names)


def nav(root, current, yard_name=None):
    """The bar, with `current` marked and anything unpublished left out.

    A screen is offered when its page exists, when the markdown that becomes
    it exists, or when the build in progress has said it is coming. Linking to
    a file that was never generated is the same defect this module exists to
    prevent, one level up.
    """
    out = []
    if yard_name:
        out.append(f'<span class="brand">{yard_name}</span>')
    for name, short, long in SCREENS:
        page = name[:-3] + ".html" if name.endswith(".md") else name
        if page not in _PLANNED \
                and not (os.path.exists(os.path.join(root, page))
                         or os.path.exists(os.path.join(root, name))):
            continue
        here = ' class="here"' if page == current else ""
        out.append(f'<a href="{page}"{here} title="{long}">{short}</a>')
    if len(out) <= 1:
        return ""
    return '<nav class="screens">' + "".join(out) + "</nav>"
