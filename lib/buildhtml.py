#!/usr/bin/env python3
"""Convert markdown garden documents into standalone HTML you can double-click.

    python3 -m lib.buildhtml cloverleaf-austin/PLAN.md
    python3 -m lib.buildhtml cloverleaf-austin/*.md
    python3 -m lib.buildhtml cloverleaf-austin/PLAN.md -o /tmp/plan.html

The output is a single self-contained file: styles are inlined and any referenced
image is embedded as a data URI, so it survives being emailed or moved to a phone.

These documents are mostly wide reference tables, which is what the stylesheet is
built around - tables scroll sideways rather than crushing their columns, and the
header row sticks while you scroll a long one.

An action document - a plan, a schedule, a sowing calendar - is checked against
`lib.changelog` on the way past, because publishing is the point at which someone
starts acting on it. A finding prints and the page is still written; --strict
refuses instead. The check is deliberately not silent and deliberately not fatal
by default: a document worth publishing under a warning exists, and a check that
blocks a publish gets routed around within a week.

--strict refuses over narration, not over length. Being long is advisory - it
still prints - because a document can be long for the good reason that it has a
lot to say, and refusing that one leaves dropping --strict as the only way to
ship it, which switches off the narration check too. --budget asks for length to
block as well.

Requires: markdown
"""
import argparse
import base64
import mimetypes
import os
import re

import markdown as md_lib

IMG_RE = re.compile(r'<img\s+([^>]*?)src="([^"]+)"([^>]*?)/?>', re.I)

CSS = """
:root {
  --ink: #1a1a1a;
  --muted: #5c5c5c;
  --rule: #dcdcdc;
  --accent: #2f5d34;
  --band: #f6f7f4;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: #fff;
  color: var(--ink);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
.wrap { max-width: 54rem; margin: 0 auto; padding: 3rem 1.5rem 6rem; }

h1, h2, h3, h4 { line-height: 1.25; font-weight: 650; margin: 2.2em 0 .6em; }
h1 { font-size: 2.1rem; margin-top: 0; letter-spacing: -.02em; }
h2 { font-size: 1.5rem; padding-bottom: .3rem; border-bottom: 2px solid var(--accent); }
h3 { font-size: 1.18rem; color: var(--accent); }
h4 { font-size: 1rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
p, li { margin: .7em 0; }
li > ul, li > ol { margin: .2em 0; }
strong { font-weight: 650; }
a { color: var(--accent); }
a:hover { text-decoration: none; }
/* A reference into the change log sits beside a sentence without interrupting
   it, so it is small and quiet until you go looking for it. */
a.cref {
  font-size: 0.78em; vertical-align: 0.25em; text-decoration: none;
  opacity: 0.6; padding: 0 0.1em; font-variant-numeric: tabular-nums;
}
a.cref::before { content: "\2009"; }
a.cref:hover { opacity: 1; text-decoration: underline; }
hr { border: 0; border-top: 1px solid var(--rule); margin: 2.5em 0; }

blockquote {
  margin: 1.4em 0; padding: .1em 1.2em;
  border-left: 3px solid var(--accent); background: var(--band); color: var(--muted);
}
code {
  font: .87em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--band); padding: .12em .35em; border-radius: 3px;
}
pre { background: var(--band); padding: 1em 1.2em; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }

/* Wide reference tables: scroll rather than crush. */
.tablewrap { overflow-x: auto; margin: 1.5em 0; border: 1px solid var(--rule); border-radius: 6px; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { padding: .55em .8em; text-align: left; vertical-align: top; border-bottom: 1px solid var(--rule); }
th {
  position: sticky; top: 0; z-index: 1;
  background: var(--accent); color: #fff; font-weight: 600;
  white-space: nowrap;
}
tbody tr:nth-child(even) { background: var(--band); }
tbody tr:last-child td { border-bottom: 0; }

img { max-width: 100%; height: auto; display: block; margin: 1.5em auto; border-radius: 6px; }

nav.toc {
  background: var(--band); border: 1px solid var(--rule); border-radius: 6px;
  padding: 1.2em 1.5em; margin: 0 0 3rem;
}
nav.toc p { margin: 0 0 .5em; font-weight: 650; font-size: .8rem;
            text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
nav.toc ul { list-style: none; margin: 0; padding: 0; column-gap: 2rem; }
nav.toc li { margin: .25em 0; font-size: .93rem; }
nav.toc li.lvl3 { padding-left: 1.1rem; font-size: .87rem; }
nav.toc a { text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }

footer { margin-top: 4rem; padding-top: 1.2em; border-top: 1px solid var(--rule);
         color: var(--muted); font-size: .82rem; }

@media (max-width: 640px) {
  .wrap { padding: 2rem 1rem 4rem; }
  h1 { font-size: 1.7rem; }
  table { font-size: .82rem; }
}
@media print {
  .wrap { max-width: none; padding: 0; }
  nav.toc { display: none; }
  h2 { break-after: avoid; }
  .tablewrap, tr, img { break-inside: avoid; }
  th { position: static; }
}
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
{toc}
{body}
<footer>{source} &middot; generated {stamp}</footer>
</div>
</body>
</html>
"""


def embed_images(html, base):
    """Swap <img src> for data URIs so the page travels as one file."""
    def swap(m):
        before, src, after = m.groups()
        if src.startswith(('http://', 'https://', 'data:')):
            return m.group(0)
        path = src if os.path.isabs(src) else os.path.join(base, src)
        if not os.path.exists(path):
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or 'image/png'
        with open(path, 'rb') as fh:
            data = base64.b64encode(fh.read()).decode('ascii')
        return '<img %ssrc="data:%s;base64,%s"%s>' % (before, mime, data, after)
    return IMG_RE.sub(swap, html)


def slug(text, seen):
    s = re.sub(r'[^\w\s-]', '', re.sub(r'<[^>]+>', '', text)).strip().lower()
    s = re.sub(r'[\s_-]+', '-', s) or 'section'
    n, out = seen.get(s, 0), s
    if n:
        out = '%s-%d' % (s, n)
    seen[s] = n + 1
    return out


def add_anchors(html):
    """Give h2/h3 ids and collect them for the contents list."""
    entries, seen = [], {}
    def tag(m):
        level, attrs, text = m.group(1), m.group(2), m.group(3)
        label = re.sub(r'<[^>]+>', '', text).strip()
        # A heading that brought its own id still belongs in the contents. The
        # change log writes {: #cNN } on all of its entries, so skipping those
        # left it as the one document with no way to navigate it.
        own = re.search(r'id="([^"]+)"', attrs)
        if own:
            entries.append((level, own.group(1), label))
            return m.group(0)
        anchor = slug(text, seen)
        entries.append((level, anchor, label))
        return '<h%s id="%s"%s>%s</h%s>' % (level, anchor, attrs, text, level)
    html = re.sub(r'<h([23])([^>]*)>(.*?)</h\1>', tag, html, flags=re.S)
    return html, entries


def build_toc(entries):
    if len(entries) < 3:
        return ''
    items = ''.join(
        '<li class="lvl%s"><a href="#%s">%s</a></li>' % (lvl, anchor, text)
        for lvl, anchor, text in entries if lvl == '2'
    )
    return '<nav class="toc"><p>Contents</p><ul>%s</ul></nav>' % items


def link_changelog(html, base):
    """Turn the plan's bare [c14] marks into links into the published log.

    The marks are written bare in the markdown on purpose — a plan sentence
    reads worse with a URL in the middle of it, and the whole point of the
    reference is that it stays out of the way. So the link is made here, at
    publish time, which is also the only point where we know CHANGELOG.html
    will exist. Without this the reference is dead text in the artifact people
    actually read, which is the mechanism failing at its last step.
    """
    if not os.path.exists(os.path.join(base, 'CHANGELOG.md')):
        return html
    return re.sub(
        r'\[(c\d+)\]',
        lambda m: '<a class="cref" href="CHANGELOG.html#%s">%s</a>'
                  % (m.group(1), m.group(1)),
        html)


def relink_siblings(html, base, name):
    """Point cross-document links at the .html we publish, not at the source."""
    def swap(m):
        target = m.group(1)
        if target == name or not os.path.exists(os.path.join(base, target)):
            return m.group(0)
        return 'href="%s.html%s"' % (target[:-3], m.group(2) or '')
    return re.sub(r'href="([^":/]+\.md)(#[^"]*)?"', swap, html)


def convert(md_path, out_path=None, link_images=False):
    base = os.path.dirname(os.path.abspath(md_path))
    src = open(md_path, encoding='utf-8').read()

    html = md_lib.markdown(src, extensions=['tables', 'fenced_code', 'sane_lists', 'attr_list'])
    html = re.sub(r'<table>', '<div class="tablewrap"><table>', html)
    html = re.sub(r'</table>', '</table></div>', html)
    if not link_images:
        html = embed_images(html, base)

    name = os.path.basename(md_path)
    html = relink_siblings(html, base, name)
    if name != 'CHANGELOG.md':
        html = link_changelog(html, base)

    html, entries = add_anchors(html)

    title = entries[0][2] if entries else os.path.splitext(name)[0]
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()

    out = out_path or os.path.splitext(os.path.abspath(md_path))[0] + '.html'
    page = PAGE.format(
        title=title, css=CSS, toc=build_toc(entries), body=html, source=name,
        stamp=__import__('datetime').date.today().isoformat())
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(page)
    return out, len(entries), html.count('<table>')


def check_prose(md_path):
    """Findings for an action document, or None if this is not one.

    Reference material is not held to the contract, so the filename decides.
    Imported late: converting a document should not depend on the changelog
    module being importable.
    """
    from . import changelog, yards
    name = os.path.basename(md_path)
    if name not in changelog.ACTION_DOCS:
        return None
    slug = os.path.basename(os.path.dirname(os.path.abspath(md_path)))
    with open(md_path, encoding='utf-8') as fh:
        text = fh.read()
    # No log for this slug means the document is not sitting in a yard this
    # checkout knows about, and every reference in it would read as dangling.
    log = yards.load(slug, 'changelog.json')
    known = {e.get('id') for e in log.get('entries', [])} if log else None
    words = changelog.prose_words(text)
    over = words - changelog.WORD_BUDGET
    findings = changelog.lint_text(text, md_path, known)
    return {'slug': slug, 'findings': findings, 'words': words,
            'over': over if over > 0 else 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('markdown', nargs='+', help='source .md file(s)')
    ap.add_argument('-o', '--output', help='output .html (only with a single input)')
    ap.add_argument('--link', action='store_true',
                    help='reference images by path instead of embedding them')
    ap.add_argument('--strict', action='store_true',
                    help='refuse to publish an action document that narrates '
                         'its own history')
    ap.add_argument('--budget', action='store_true',
                    help='with --strict, also refuse one that is over the '
                         'prose budget')
    args = ap.parse_args()

    if args.output and len(args.markdown) > 1:
        raise SystemExit('-o takes a single input file')

    # Checked before anything is written, so --strict refuses rather than
    # publishing and then complaining about what it published.
    prose = {p: check_prose(p) for p in args.markdown}
    flagged = [p for p, r in prose.items()
               if r and (r['findings'] or r['over'])]

    for path in flagged:
        r = prose[path]
        name = os.path.basename(path)
        for line, what, instead in r['findings']:
            print('    %s:%d  %s' % (name, line, what))
            print('        %s' % instead)
        if r['over']:
            print('    %s: %d words of prose, %d over the action-document '
                  'budget%s' % (name, r['words'], r['over'],
                                '' if args.budget else ' (advisory)'))
        print('    python3 -m lib.changelog %s --lint' % r['slug'])

    # Narration and length are different failures and only one of them is a
    # defect. A document that is long because it has a lot to say is what the
    # budget is advisory about; one that is narrating its own history is the
    # thing this refuses over. Collapsing the two means the only way to publish
    # a long clean document is to drop --strict, which switches off the check
    # that matters - so length blocks only when it is asked to.
    narrating = [p for p in flagged if prose[p]['findings']]
    refuse = flagged if args.budget else narrating
    if refuse and args.strict:
        raise SystemExit(
            'nothing published. %d action document%s %s,\nand --strict was '
            'asked for. The prose above is change-log entries.'
            % (len(refuse), 's' if len(refuse) > 1 else '',
               'narrating its own history or over budget' if args.budget
               else 'narrating its own history'))

    for path in args.markdown:
        out, sections, tables = convert(path, args.output, args.link)
        print('%-34s -> %s  (%d sections, %d tables, %.0f KB)'
              % (os.path.basename(path), os.path.basename(out),
                 sections, tables, os.path.getsize(out) / 1024))


if __name__ == '__main__':
    main()
