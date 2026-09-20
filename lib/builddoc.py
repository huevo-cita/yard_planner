#!/usr/bin/env python3
"""Convert a markdown garden plan into a .docx with real headings, lists, tables and
embedded images — the format that survives an upload to Google Docs.

    python3 build_doc.py plan.md -o plan.docx

Handles two things a plain markdown-to-docx conversion gets wrong:

1. Images. Any <img src="..." width="N" /> tag in the markdown is embedded as an inline
   picture. src resolves relative to the markdown file. width is in pixels; it is
   converted to inches at 96 dpi, capped to the text column.
2. Lists that markdown collapses. Hand-written schedules often put "- item" lines inside
   what markdown parses as a single paragraph; those are rebuilt into real <ul>/<ol>.

Then upload:
  new doc     -> gdrive.uploadFile(localPath=..., convertToGoogleFormat=True)
  update copy -> gdrive.uploadFile(localPath=..., fileId=...)   # keeps the same link
convertToGoogleFormat and fileId cannot be combined.

Requires: markdown, python-docx
"""
import argparse
import os
import re
from html.parser import HTMLParser

import markdown as md_lib
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

MAX_WIDTH_IN = 6.5
IMG_RE = re.compile(r'<img\s+[^>]*src="([^"]+)"[^>]*?/?>', re.I)
WIDTH_RE = re.compile(r'width="(\d+)"', re.I)

# The text column between the margins set in main().
TABLE_WIDTH_IN = 7.3
MIN_COL_IN = 0.55


def column_widths(rows, ncols):
    """Inches per column, weighted by how much text each column actually holds.

    Left to itself the importer gives every column a similar share, which is
    wrong whenever one column is prose and the others are dates and prices: the
    prose wraps to fifteen lines and every other cell in the row is nine tenths
    white space, so the page becomes mostly scroll.

    Weighting by the square root of the mean cell length rather than by the
    length itself is what keeps this honest at both ends. Raw proportion hands a
    1,500-character cell 80% of the page and squeezes a street address into half
    an inch; the square root damps the extreme while still moving most of the
    width where the text is. MIN_COL_IN is the floor a date or a price needs to
    stay on one line, and it is taken out before the rest is shared.
    """
    lengths = [0.0] * ncols
    counts = [0] * ncols
    for row in rows:
        for j, cell in enumerate(row[:ncols]):
            lengths[j] += sum(len(text) for text, _, _ in cell)
            counts[j] += 1
    means = [lengths[j] / counts[j] if counts[j] else 1.0 for j in range(ncols)]
    weights = [max(m, 1.0) ** 0.5 for m in means]

    floor = MIN_COL_IN * ncols
    if floor >= TABLE_WIDTH_IN:            # more columns than the page can hold
        return [TABLE_WIDTH_IN / ncols] * ncols
    spare, total = TABLE_WIDTH_IN - floor, sum(weights)
    return [MIN_COL_IN + spare * w / total for w in weights]


def fix_layout(table, widths):
    """Pin the widths so the importer honours them instead of re-fitting.

    w:tblGrid is the part that matters and the one python-docx never touches: it
    writes w:tcW per cell and leaves the grid at the equal split add_table made,
    and Google Docs reads the grid. Setting only the cells looks correct in a
    local inspection — cell.width reads back exactly what was set — and imports
    as evenly spaced columns, so this has to be verified on the grid rather than
    on the cells. Both are written, because Word prefers w:tcW under a fixed
    layout, and the two disagreeing is what produced the wrong answer here.
    """
    table.autofit = False
    tblPr = table._tbl.tblPr
    layout = tblPr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout')
        tblPr.append(layout)
    layout.set(qn('w:type'), 'fixed')

    twips = [str(int(round(w * 1440))) for w in widths]
    gridEl = table._tbl.find(qn('w:tblGrid'))
    if gridEl is not None:
        cols = gridEl.findall(qn('w:gridCol'))
        for col, tw in zip(cols, twips):
            col.set(qn('w:w'), tw)
    for j, w in enumerate(widths):
        for cell in table.column_cells(j):
            cell.width = Inches(w)


def build_html(md_path, images):
    """Markdown -> HTML, with <img> tags swapped for placeholder tokens."""
    src = open(md_path).read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)
    base = os.path.dirname(os.path.abspath(md_path))

    def swap(m):
        tag, rel = m.group(0), m.group(1)
        path = rel if os.path.isabs(rel) else os.path.join(base, rel)
        if not os.path.exists(path):
            raise SystemExit('image not found: %s (referenced as %s)' % (path, rel))
        px = WIDTH_RE.search(tag)
        width = min(int(px.group(1)) / 96.0, MAX_WIDTH_IN) if px else MAX_WIDTH_IN
        token = 'XIMAGE%dX' % len(images)
        images[token] = (path, width)
        return token

    src = IMG_RE.sub(swap, src)
    html = md_lib.markdown(src, extensions=['tables'])
    html = html.replace('<blockquote>', '').replace('</blockquote>', '')
    html = re.sub(r'<hr ?/?>', '', html)

    def fix_para(m):
        inner = m.group(1)
        if '\n' not in inner:
            return m.group(0)
        out, lead, items, kind = [], [], [], None

        def flush():
            nonlocal items, kind
            if items:
                tag = 'ul' if kind == 'ul' else 'ol'
                out.append('<%s>%s</%s>' % (tag, ''.join('<li>%s</li>' % i for i in items), tag))
                items, kind = [], None

        for ln in inner.split('\n'):
            s = ln.strip()
            mnum = re.match(r'^(\d+)\.\s+(.*)', s)
            if s.startswith('- '):
                if kind == 'ol':
                    flush()
                kind = 'ul'
                items.append(s[2:])
            elif mnum:
                if kind == 'ul':
                    flush()
                kind = 'ol'
                items.append(mnum.group(2))
            else:
                flush()
                lead.append(s)
        flush()
        prefix = '<p>%s</p>' % ' '.join(lead) if lead else ''
        return prefix + ''.join(out)

    return re.sub(r'<p>(.*?)</p>', fix_para, html, flags=re.S)


class Conv(HTMLParser):
    def __init__(self, doc, images):
        super().__init__(convert_charrefs=True)
        self.doc = doc
        self.images = images
        self.bold = 0
        self.italic = 0
        self.para = None
        self.mode = None
        self.list_style = None
        self.table_rows = None
        self.cur_row = None
        self.cur_cell = None
        self._th = False

    def emit(self, text):
        if self.table_rows is not None and self.cur_cell is not None:
            self.cur_cell.append((text, bool(self.bold), bool(self.italic)))
        elif self.para is not None:
            r = self.para.add_run(text)
            r.bold = bool(self.bold)
            r.italic = bool(self.italic)

    def handle_starttag(self, tag, attrs):
        if tag in ('h1', 'h2', 'h3', 'h4'):
            self.para = self.doc.add_heading('', level=int(tag[1]))
            self.mode = 'h'
        elif tag == 'p':
            self.para = self.doc.add_paragraph()
            self.mode = 'p'
        elif tag == 'ul':
            self.list_style = 'List Bullet'
        elif tag == 'ol':
            self.list_style = 'List Number'
        elif tag == 'li':
            self.para = self.doc.add_paragraph(style=self.list_style)
            self.mode = 'li'
        elif tag in ('strong', 'b'):
            self.bold += 1
        elif tag in ('em', 'i'):
            self.italic += 1
        elif tag == 'table':
            self.table_rows = []
        elif tag == 'tr':
            self.cur_row = []
        elif tag in ('td', 'th'):
            self.cur_cell = []
            self._th = tag == 'th'
            if self._th:
                self.bold += 1

    def handle_endtag(self, tag):
        if tag in ('h1', 'h2', 'h3', 'h4', 'p', 'li'):
            if self.para is not None and self.para.text.strip() in self.images:
                path, width = self.images[self.para.text.strip()]
                for r in list(self.para.runs):
                    r.text = ''
                self.para.add_run().add_picture(path, width=Inches(width))
            self.para = None
            self.mode = None
        elif tag in ('strong', 'b'):
            self.bold -= 1
        elif tag in ('em', 'i'):
            self.italic -= 1
        elif tag in ('td', 'th'):
            if self._th:
                self.bold -= 1
            self.cur_row.append(self.cur_cell)
            self.cur_cell = None
        elif tag == 'tr':
            self.table_rows.append(self.cur_row)
            self.cur_row = None
        elif tag == 'table':
            rows, self.table_rows = self.table_rows, None
            if not rows:
                return
            ncols = max(len(r) for r in rows)
            t = self.doc.add_table(rows=len(rows), cols=ncols)
            t.style = 'Table Grid'
            fix_layout(t, column_widths(rows, ncols))
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    p = t.cell(i, j).paragraphs[0]
                    for text, bold, ital in cell:
                        r = p.add_run(text)
                        r.bold, r.italic = bold, ital
                        r.font.size = Pt(9)
            self.doc.add_paragraph()

    def handle_data(self, data):
        if self.mode or (self.table_rows is not None and self.cur_cell is not None):
            self.emit(data.replace('\n', ' '))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('markdown', help='source .md file')
    ap.add_argument('-o', '--output', help='output .docx (default: alongside the markdown)')
    args = ap.parse_args()

    out = args.output or os.path.splitext(os.path.abspath(args.markdown))[0] + '.docx'
    images = {}
    html = build_html(args.markdown, images)

    doc = Document()
    for s in doc.sections:          # narrower margins so wide tables fit
        s.left_margin = Inches(0.6)
        s.right_margin = Inches(0.6)
    Conv(doc, images).feed(html)
    doc.save(out)

    check = Document(out)
    print(out)
    print('tables: %d | inline images: %d | paragraphs: %d'
          % (len(check.tables), len(check.inline_shapes), len(check.paragraphs)))
    if len(check.inline_shapes) != len(images):
        print('WARNING: expected %d images, embedded %d' % (len(images), len(check.inline_shapes)))


if __name__ == '__main__':
    main()
