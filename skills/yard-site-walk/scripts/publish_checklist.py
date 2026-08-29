#!/usr/bin/env python3
"""Turn a site-walk checklist markdown into a Google Doc that keeps its formatting.

    python3 publish_checklist.py <slug>/SITE-WALK.md

Writes two files next to the markdown:

    SITE-WALK.html        paste as the `html` argument of gdrive createDocFromHTML
    SITE-WALK.runs.json   ordered textToFind strings for the checkbox pass

Then, to publish:

  1. gdrive createDocFromHTML(name=..., html=<contents of the .html>)
  2. for each string in the .runs.json, in order:
       gdrive createParagraphBullets(documentId=..., bulletPreset='BULLET_CHECKBOX',
                                     textToFind=<the string>)
     Each call reports the character range it touched. A "not found" means the
     markdown and the HTML have drifted apart — regenerate, do not hand-patch.
  3. Verify: gdrive downloadFile(exportMimeType='text/markdown'), then
       python3 publish_checklist.py <slug>/SITE-WALK.md --verify <exported.md>
     which counts the checkboxes the way the export actually writes them.

Seven things about the Docs HTML importer and this MCP surface, all learned the
hard way:

  * <hr> steals the heading style of whatever follows it, so a rule before an
    <h2> silently demotes that heading to bold body text and puts "---" in the
    document outline. Rules are dropped; heading spacing separates sections.
  * The importer zeroes space-below on <p>, running paragraphs into one block.
    Explicit margins are emitted on every paragraph.
  * HTML collapses runs of whitespace, so the checkbox run strings are
    whitespace-normalised to match what the document will actually contain.
  * There is no HTML for a checklist. Checkbox items import as ordinary bullets
    and need the second pass above to become tickable checkboxes.
  * The whole document has to travel as one inline `html` argument. Drive itself
    converts text/html to a Doc, but the MCP `uploadFile` tool refuses it —
    convertToGoogleFormat allows only .docx/.xls/.pptx — so `localPath` is not
    an escape route and a long checklist is simply a large argument. A 107-item
    walk is about 33 KB. Do not go looking for a file-based path; there isn't
    one.
  * The text/markdown export prefixes EVERY list item with "> ", rendering
    lists inside a blockquote: "> - [ ] Tape the...". So the obvious
    verification regex, anchored as ^\s*-\s*\[ \], matches nothing and reports
    total failure on a document that is perfectly correct. Anchor as
    ^[>\s]*[-*]\s*\[[ xX]\] or use --verify below.
  * A checklist may legitimately contain ordinary `-` bullets that are prose,
    not items to tick — a summary of what changed since the last revision, for
    instance. The parser already keeps those apart (`bul` vs `cb`), but a
    verifier that counts every remaining bullet as a missed conversion will
    report failure on a correct document, which is the same trap as the entry
    above wearing a different hat. --verify takes the prose-bullet count as its
    baseline and reports only the surplus. A NEGATIVE surplus is worth having:
    it means a textToFind reached past its run and converted a prose bullet, so
    some run matched the wrong paragraphs.
"""
import argparse
import html
import json
import os
import re

CODE = "font-family:'Courier New',monospace;background-color:#f1f3f4;"
BODY = 'margin-top:0;margin-bottom:10pt;'
HEAD = 'margin-top:22pt;margin-bottom:8pt;'
QUOTE = 'margin-left:28pt;margin-top:6pt;margin-bottom:12pt;color:#5f6368;'
LEADIN = 'margin-top:0;margin-bottom:3pt;'


def inline(t):
    """Markdown inline spans to HTML. Order matters: bold before italic."""
    t = html.escape(t, quote=False)
    t = re.sub(r'`([^`]+)`', rf'<span style="{CODE}">\1</span>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', t)
    return t


def plain(t):
    """The text a checkbox item will actually contain once Docs has imported it.

    Markup is gone, entities are resolved, and runs of whitespace are collapsed
    the way HTML collapses them. The checkbox pass matches on this, so it has to
    be character-exact or createParagraphBullets reports "not found".
    """
    t = re.sub(r'<[^>]+>', '', inline(t))
    return re.sub(r'\s+', ' ', html.unescape(t)).strip()


def parse(md):
    """Markdown lines to (kind, indent, text) blocks, folding wrapped prose.

    A checklist is written hard-wrapped for the terminal, so a single item or
    paragraph spans several lines. Anything indented that is not itself a list
    marker continues the block above it.
    """
    blocks = []
    for line in md.split('\n'):
        s = line.rstrip()
        if not s.strip():
            blocks.append(('blank', 0, ''))
            continue
        ind = len(s) - len(s.lstrip())
        body = s.strip()
        m = re.match(r'^(#{1,6})\s+(.*)$', body)
        if m:
            blocks.append((f'h{len(m.group(1))}', 0, m.group(2)))
        elif set(body) <= {'-'} and len(body) >= 3:
            blocks.append(('hr', 0, ''))
        elif body.startswith('|'):
            blocks.append(('table', 0, body))
        elif body.startswith('> '):
            blocks.append(('quote', 0, body[2:]))
        elif re.match(r'^[-*] \[[ xX]\]\s+', body):
            blocks.append(('cb', ind, re.sub(r'^[-*] \[[ xX]\]\s+', '', body)))
        elif re.match(r'^\d+\.\s+', body):
            blocks.append(('num', ind, re.sub(r'^\d+\.\s+', '', body)))
        elif re.match(r'^[-*]\s+', body):
            blocks.append(('bul', ind, re.sub(r'^[-*]\s+', '', body)))
        elif ind >= 2 and blocks and blocks[-1][0] in (
                'cb', 'num', 'bul', 'quote', 'para'):
            k, i, t = blocks[-1]
            blocks[-1] = (k, i, t + ' ' + body)
        else:
            blocks.append(('para', 0, body))
    return blocks


def render(blocks):
    """Blocks to Docs-safe HTML, plus the checkbox runs to convert afterwards.

    A run is a maximal stretch of consecutive checkbox items with nothing else
    between them. Each becomes one createParagraphBullets call, because the
    tool applies the preset to every paragraph its matched text overlaps.
    """
    out = ['<html><body style="font-family:Arial,sans-serif;font-size:11pt;">']
    runs, i, n = [], 0, len(blocks)

    while i < n:
        kind, ind, text = blocks[i]

        if kind == 'blank':
            i += 1

        elif re.match(r'^h[1-6]$', kind):
            style = '' if kind == 'h1' else f' style="{HEAD}"'
            out.append(f'<{kind}{style}>{inline(text)}</{kind}>')
            i += 1

        elif kind == 'hr':
            i += 1                      # dropped: it would eat the next heading

        elif kind == 'quote':
            buf = []
            while i < n and blocks[i][0] == 'quote':
                buf.append(blocks[i][2])
                i += 1
            out.append(f'<p style="{QUOTE}"><i>{inline(" ".join(buf))}</i></p>')

        elif kind == 'table':
            rows = []
            while i < n and blocks[i][0] == 'table':
                rows.append(blocks[i][2])
                i += 1
            parsed = []
            for r in rows:
                cells = [c.strip() for c in r.strip().strip('|').split('|')]
                if all(c and set(c) <= set('-: ') for c in cells):
                    continue            # the |---|---| separator row
                parsed.append(cells)
            out.append('<table border="1" cellpadding="6" '
                       'style="border-collapse:collapse;border-color:#d0d0d0;">')
            for ri, cells in enumerate(parsed):
                out.append('<tr>')
                for c in cells:
                    if ri == 0:
                        out.append('<td style="background-color:#eaf1e5;">'
                                   f'<b>{inline(c)}</b></td>')
                    else:
                        out.append(f'<td>{inline(c)}</td>')
                out.append('</tr>')
            out.append('</table>')

        elif kind == 'bul':
            # Plain bullets are labels and definitions, not tasks. They keep
            # ordinary bullets, and they break a checkbox run.
            out.append('<ul>')
            while i < n and blocks[i][0] == 'bul':
                out.append(f'<li>{inline(blocks[i][2])}</li>')
                i += 1
            out.append('</ul>')

        elif kind in ('cb', 'num'):
            tag = 'ul' if kind == 'cb' else 'ol'
            base, depth, items = ind, 0, []
            out.append(f'<{tag}>')
            while i < n and blocks[i][0] == kind:
                _, i2, t2 = blocks[i]
                want = 1 if i2 > base else 0
                while depth < want:
                    out.append(f'<{tag}>')
                    depth += 1
                while depth > want:
                    out.append(f'</{tag}>')
                    depth -= 1
                out.append(f'<li>{inline(t2)}</li>')
                items.append(plain(t2))
                i += 1
                if (i + 1 < n and blocks[i][0] == 'blank'
                        and blocks[i + 1][0] == kind):
                    i += 1              # a blank line inside a list is cosmetic
            while depth > 0:
                out.append(f'</{tag}>')
                depth -= 1
            out.append(f'</{tag}>')
            if kind == 'cb':
                runs.append('\n'.join(items))

        else:
            buf = []
            while i < n and blocks[i][0] == 'para':
                buf.append(blocks[i][2])
                i += 1
            joined = ' '.join(buf)
            # A short bold-only line introduces the list under it, so tighten
            # the gap rather than letting a full body margin orphan it.
            lead = re.fullmatch(r'\*\*[^*]{,70}\*\*:?', joined) is not None
            out.append(f'<p style="{LEADIN if lead else BODY}">{inline(joined)}</p>')

    out.append('</body></html>')
    return '\n'.join(out), runs


#: A list item in a text/markdown export of a Doc, which arrives wrapped in a
#: blockquote. Anchoring on whitespace alone silently matches nothing.
EXPORTED_ITEM = re.compile(r'^[>\s]*[-*]\s*(\[[ xX]\])?\s*', re.M)


def verify(runs, exported, prose_items=0):
    """Compare a Doc exported as markdown against the runs that should be in it.

    `prose_items` is the number of ordinary `-` bullets the source deliberately
    contains. Those are NOT checklist items and must not be counted as misses;
    a checklist that also carries a prose list would otherwise report failure on
    a perfectly good document.

    Returns (expected, checkboxes, surplus_plain), where surplus_plain is the
    plain-bullet count in excess of the prose baseline. Positive means a
    createParagraphBullets call was missed and those items will not tick.
    Negative means a prose bullet was converted, so some textToFind matched the
    wrong paragraphs.
    """
    expected = sum(len(r.split('\n')) for r in runs)
    checkboxes = plain = 0
    for line in exported.split('\n'):
        m = EXPORTED_ITEM.match(line)
        if not m or not line.strip():
            continue
        if not re.match(r'^[>\s]*[-*]\s', line):
            continue
        if m.group(1):
            checkboxes += 1
        else:
            plain += 1
    return expected, checkboxes, plain - prose_items


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('markdown', help='the checklist .md')
    ap.add_argument('--verify', metavar='EXPORTED_MD',
                    help='a text/markdown export of the published Doc, to check '
                         'the checkbox count against this checklist')
    args = ap.parse_args()

    src = os.path.abspath(args.markdown)
    stem = os.path.splitext(src)[0]
    blocks = parse(open(src).read())
    doc, runs = render(blocks)

    if args.verify:
        prose = sum(1 for kind, _, _ in blocks if kind == 'bul')
        expected, boxes, surplus = verify(
            runs, open(args.verify).read(), prose)
        print('expected checkbox items %d | checkboxes in the Doc %d | '
              'prose bullets %d' % (expected, boxes, prose))
        if boxes == expected and not surplus:
            print('  match')
        elif surplus > 0:
            print('  MISSED %d item(s): a createParagraphBullets pass did not '
                  'run, and those items will not tick' % surplus)
        elif surplus < 0:
            print('  OVERREACHED by %d: a textToFind converted %d prose bullet(s) '
                  'into checkboxes, so a run matched the wrong paragraphs'
                  % (-surplus, -surplus))
        else:
            print('  MISMATCH by %d' % (expected - boxes))
        return

    open(stem + '.html', 'w').write(doc)
    json.dump(runs, open(stem + '.runs.json', 'w'), indent=1)

    strays = [m for m in re.findall(r'<p[^>]*>(.*?)</p>', doc)
              if m and (m[0].islower() or m[0] in ',.')]
    # createParagraphBullets matches the first instance of textToFind, so a run
    # that also occurs earlier would convert the wrong paragraphs.
    haystack = '\n'.join(runs)
    ambiguous = [i for i, r in enumerate(runs) if haystack.count(r) > 1]
    print(os.path.basename(stem) + '.html')
    print('  checkbox items %d in %d runs | numbered lists %d | tables %d'
          % (sum(len(r.split('\n')) for r in runs), len(runs),
             doc.count('<ol>'), doc.count('<table')))
    print('  headings h1 %d h2 %d h3 %d'
          % (doc.count('<h1>'), doc.count('<h2 '), doc.count('<h3 ')))
    if strays:
        print('  WARNING: %d paragraph(s) start mid-sentence, so a wrapped line '
              'was not folded:' % len(strays))
        for s in strays[:5]:
            print('    ' + s[:70])
    if ambiguous:
        print('  WARNING: run(s) %s are not unique in the document. Reword one '
              'of the duplicated items, or pass matchInstance to disambiguate.'
              % ', '.join(str(i) for i in ambiguous))


if __name__ == '__main__':
    main()
