#!/usr/bin/env python3
"""Render to-scale garden maps from a JSON layout spec.

    python3 -m lib.drawbeds layout.json --outdir maps/
    python3 -m lib.drawbeds <slug>            # from design.json's "layout" block

Writes one PNG per bed, named <name>.png. All measurements are in feet.

Spec is {"beds": [...]} with three bed types.

"grid" — square-foot raised bed, cells on a 1 ft grid.
  {"type": "grid", "name": "raised-bed",
   "title": "Raised Bed 4 ft x 8 ft", "subtitle": "8-ft side along the west fence",
   "width": 4, "length": 8,                  # width = x across, length = y up
   "top_label": "NORTH (tall end)", "bottom_label": "SOUTH (short end)",
   "left_wall": "WEST FENCE (evening shade)",
   "cells": [{"x": 0, "y": 7, "w": 2, "h": 1,
              "label": "Broccoli x2", "color": "#7fb069", "fontsize": 8.5}]}

"border" — long bed drawn horizontally, plants as circles sized to mature spread.
  {"type": "border", "name": "west-bed",
   "title": "West-Side Bed 13 ft x 40 in",
   "subtitle": ["House wall along the top.", "ft 0 = the corner."],
   "length": 13, "depth": 3.34,
   "wall": "HOUSE WALL",                     # drawn along the top edge
   "bands": [{"from": 0, "to": 1.17,         # measured from the FRONT (bottom) edge
              "color": "#c9c9c9", "hatch": "ooo"}],
   "plants": [{"x": 0.75, "y": 2.55, "r": 0.52, "label": "Rosemary",
               "color": "#9db8a1", "fontsize": 6, "hatch": null}],
   "side_notes": [{"y": 2.35, "text": "PLANTING ZONE", "color": "#555"}],
   "notes": ["footnote line"],
   "ruler": true}

"overview" — freeform yard plan, x east, y north.
  {"type": "overview", "name": "yard-overview",
   "title": "Yard Overview", "subtitle": "North is up.",
   "xlim": [-20.5, 28], "ylim": [-24, 31],
   "shapes": [{"x": 0, "y": 0, "w": 26, "h": 26, "color": "#ded6c8",
               "edge": "#8a7f6d", "hatch": null, "label": "HOUSE",
               "label_size": 15, "rotate_label": false, "zorder": 2}],
   "circles": [{"x": -5.4, "y": 9.5, "r": 0.85, "color": "#8fc9e8", "zorder": 5}],
   "labels": [{"x": 9, "y": -12, "text": "LAWN", "size": 11, "color": "#9db08c",
               "rotation": 0, "halo": "#eaf1e2", "align": "center"}],
   "arrows": [{"text": "the corner", "to": [-2, -0.4], "at": [-11.5, -5.5],
               "color": "#6b5b45", "size": 8.5}],
   "north": [24, -18], "scalebar": {"x": 8, "y": -18.6, "length": 10}}

Any bed may override "figsize": [w, h]. Always look at the rendered PNG and nudge
positions until labels stop colliding; first passes usually collide somewhere.

Requires: matplotlib
"""
import argparse
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle, Circle

SOIL = '#f5efe2'
SOIL_EDGE = '#6b5b45'
INK = '#3d3d3d'
MUTED = '#666'


def _halo(color, lw=2.4):
    return [pe.withStroke(linewidth=lw, foreground=color)]


def _fig(spec, xlim, ylim, default_scale=0.85):
    span_x, span_y = xlim[1] - xlim[0], ylim[1] - ylim[0]
    figsize = spec.get('figsize') or (
        max(6.0, min(18.0, span_x * default_scale)),
        max(4.0, min(16.0, span_y * default_scale)),
    )
    fig, ax = plt.subplots(figsize=tuple(figsize))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect('equal')
    ax.axis('off')
    return fig, ax


def _titles(ax, spec, x, y, gap=0.42):
    if spec.get('title'):
        ax.text(x, y, spec['title'], fontsize=15, fontweight='bold', color=INK)
        y -= gap
    sub = spec.get('subtitle')
    for line in ([sub] if isinstance(sub, str) else (sub or [])):
        ax.text(x, y, line, fontsize=9.5, color=MUTED)
        y -= gap
    return y


def _ruler(ax, length, y0=0.0):
    for f in range(1, int(length)):
        ax.plot([f, f], [y0, y0 - 0.06], color='#999', lw=0.8)
        ax.text(f, y0 - 0.3, str(f), ha='center', fontsize=7, color='#999')
    ax.text(length / 2.0, y0 - 0.62, 'feet', ha='center', fontsize=7.5, color='#999')


def _plant(ax, p):
    r = p.get('r', 0.5)
    ax.add_patch(Circle((p['x'], p['y']), r, fc=p.get('color', '#c9d6c0'),
                        ec='white', lw=1.6, alpha=0.92, hatch=p.get('hatch'),
                        zorder=p.get('zorder', 2)))
    if p.get('label'):
        ax.text(p['x'], p.get('label_y', p['y']), p['label'], ha='center', va='center',
                fontsize=p.get('fontsize', 7), fontweight='bold', color='#2d2d2d',
                zorder=p.get('zorder', 2) + 2, path_effects=_halo('white', 2.2))


def draw_grid(spec, path):
    w, ln = spec['width'], spec['length']
    xlim = (-2.2, w + 1.6)
    ylim = (-1.4, ln + 1.8)
    fig, ax = _fig(spec, xlim, ylim, default_scale=1.05)
    ax.add_patch(Rectangle((0, 0), w, ln, fc=SOIL, ec=SOIL_EDGE, lw=2.5, zorder=0))
    _titles(ax, spec, xlim[0] + 0.1, ln + 1.3, gap=0.38)
    if spec.get('left_wall'):
        ax.add_patch(Rectangle((-1.35, -0.4), 0.18, ln + 1.0, fc='#9a8a76', zorder=1))
        ax.text(-1.62, ln / 2.0, spec['left_wall'], rotation=90, va='center',
                fontsize=8, color=MUTED, fontweight='bold')
    if spec.get('top_label'):
        ax.text(w / 2.0, ln + 0.35, spec['top_label'], ha='center', fontsize=8,
                color=MUTED, fontweight='bold')
    if spec.get('bottom_label'):
        ax.text(w / 2.0, -1.05, spec['bottom_label'], ha='center', fontsize=8,
                color=MUTED, fontweight='bold')
    _ruler(ax, w)
    for f in range(1, int(ln)):
        ax.plot([w, w + 0.06], [f, f], color='#999', lw=0.8)
        ax.text(w + 0.28, f, str(f), va='center', fontsize=7, color='#999')
    for c in spec.get('cells', []):
        ax.add_patch(Rectangle((c['x'], c['y']), c['w'], c['h'], fc=c.get('color', '#b5d99c'),
                               ec='white', lw=1.8, zorder=2))
        ax.text(c['x'] + c['w'] / 2.0, c['y'] + c['h'] / 2.0, c.get('label', ''),
                ha='center', va='center', fontsize=c.get('fontsize', 8.5),
                color='#2d2d2d', fontweight='bold', zorder=3)
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def draw_border(spec, path):
    ln, depth = spec['length'], spec['depth']
    notes = spec.get('notes', [])
    right = ln + (5.0 if spec.get('side_notes') else 0.8)
    bottom = -1.1 - 0.34 * len(notes)
    xlim = spec.get('xlim') or (-1.0, right)
    ylim = spec.get('ylim') or (bottom, depth + 2.4)
    fig, ax = _fig(spec, xlim, ylim, default_scale=0.95)
    ax.add_patch(Rectangle((0, 0), ln, depth, fc=SOIL, ec=SOIL_EDGE, lw=2.5, zorder=0))
    _titles(ax, spec, xlim[0], depth + 1.9)
    if spec.get('wall'):
        ax.add_patch(Rectangle((0, depth), ln, 0.16, fc='#8a8a8a', zorder=1))
        ax.text(ln / 2.0, depth + 0.42, spec['wall'], ha='center', fontsize=8,
                color=MUTED, fontweight='bold')
    for b in spec.get('bands', []):
        # A band runs the length of the bed unless it says otherwise. A wall
        # that only backs part of a border is exactly the case that needs it.
        bx0 = b.get('x_from', 0.0)
        bx1 = b.get('x_to', ln)
        ax.add_patch(Rectangle((bx0, b['from']), bx1 - bx0, b['to'] - b['from'],
                               fc=b.get('color', '#c9c9c9'), ec=b.get('edge', 'none'),
                               lw=0.6, hatch=b.get('hatch'), alpha=b.get('alpha', 1.0),
                               zorder=b.get('zorder', 1)))
    if spec.get('ruler', True):
        _ruler(ax, ln)
    for p in spec.get('plants', []):
        _plant(ax, p)
    for s in spec.get('side_notes', []):
        ax.text(ln + 0.35, s['y'], s['text'], va='center', fontsize=8,
                color=s.get('color', '#555'), fontweight='bold')
    for i, note in enumerate(notes):
        ax.text(0.0, -1.0 - 0.34 * i, note, fontsize=7.2, color='#557', style='italic')
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def draw_overview(spec, path):
    xlim, ylim = spec['xlim'], spec['ylim']
    fig, ax = _fig(spec, xlim, ylim, default_scale=0.28)
    _titles(ax, spec, xlim[0], ylim[1] - (ylim[1] - ylim[0]) * 0.03,
            gap=(ylim[1] - ylim[0]) * 0.032)
    for s in spec.get('shapes', []):
        ax.add_patch(Rectangle((s['x'], s['y']), s['w'], s['h'], fc=s.get('color', SOIL),
                               ec=s.get('edge', 'none'), lw=s.get('lw', 2.0),
                               hatch=s.get('hatch'), alpha=s.get('alpha', 1.0),
                               zorder=s.get('zorder', 2)))
        if s.get('label'):
            ax.text(s['x'] + s['w'] / 2.0, s['y'] + s['h'] / 2.0, s['label'],
                    ha='center', va='center', fontsize=s.get('label_size', 10),
                    fontweight='bold', color='#4a4a4a',
                    rotation=90 if s.get('rotate_label') else 0,
                    zorder=s.get('zorder', 2) + 3)
    for c in spec.get('circles', []):
        ax.add_patch(Circle((c['x'], c['y']), c['r'], fc=c.get('color', '#8fc9e8'),
                            ec='white', lw=1.6, zorder=c.get('zorder', 5)))
    for lb in spec.get('labels', []):
        kw = {'path_effects': _halo(lb['halo'], 3)} if lb.get('halo') else {}
        ax.text(lb['x'], lb['y'], lb['text'], ha=lb.get('align', 'center'), va='center',
                fontsize=lb.get('size', 9), color=lb.get('color', MUTED),
                fontweight=lb.get('weight', 'bold'), rotation=lb.get('rotation', 0),
                zorder=8, **kw)
    for a in spec.get('arrows', []):
        ax.annotate(a['text'], xy=tuple(a['to']), xytext=tuple(a['at']), ha='center',
                    fontsize=a.get('size', 8), fontweight='bold',
                    color=a.get('color', '#555'), zorder=9,
                    arrowprops=dict(arrowstyle='->', color=a.get('color', '#777'), lw=1.1))
    if spec.get('north'):
        nx, ny = spec['north']
        span = (ylim[1] - ylim[0]) * 0.09
        ax.annotate('', xy=(nx, ny + span), xytext=(nx, ny),
                    arrowprops=dict(arrowstyle='-|>', color='#555', lw=2.2))
        ax.text(nx, ny + span * 1.25, 'N', ha='center', fontsize=14,
                fontweight='bold', color='#555')
    sb = spec.get('scalebar')
    if sb:
        x, y, L = sb['x'], sb['y'], sb['length']
        ax.plot([x, x + L], [y, y], color='#555', lw=2.2)
        for e in (x, x + L):
            ax.plot([e, e], [y - 0.3, y + 0.3], color='#555', lw=2.2)
        ax.text(x + L / 2.0, y + 0.7, '%g ft' % L, ha='center', fontsize=8.5, color='#555')
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)


DRAW = {'grid': draw_grid, 'border': draw_border, 'overview': draw_overview}


def render(layout, outdir):
    """Draw every bed in a layout spec. Returns the paths written."""
    os.makedirs(outdir, exist_ok=True)
    written = []
    for bed in layout['beds']:
        kind = bed.get('type')
        if kind not in DRAW:
            raise SystemExit('bed "%s": unknown type %r (expected one of %s)'
                             % (bed.get('name', '?'), kind, ', '.join(sorted(DRAW))))
        path = os.path.join(outdir, bed['name'] + '.png')
        DRAW[kind](bed, path)
        written.append(path)
        print('wrote', path)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec', help='JSON layout file, or a yard slug whose '
                                 'design.json carries a "layout" block')
    ap.add_argument('--outdir', default=None,
                    help='default: maps/ beside the spec, or the yard\'s design/')
    ap.add_argument('--force', action='store_true',
                    help='draw a yard whose board still has open doubts')
    args = ap.parse_args()

    # A slug is also a directory name here, so `os.path.exists` alone sends
    # every yard down the file branch and then fails on opening a directory.
    if os.path.isfile(args.spec):
        with open(args.spec) as fh:
            layout = json.load(fh)
        outdir = args.outdir or 'maps'
    else:
        from . import doubts, yards              # a slug, not a file
        # Only the yard branch is gated. A standalone spec file belongs to
        # nothing and has no board to check.
        doubts.gate(args.spec, 'drawbeds', force=args.force)
        design = yards.load(args.spec, 'design.json')
        if not design or 'layout' not in design:
            raise SystemExit('%r is neither a spec file nor a yard with a '
                             'design.json carrying a "layout" block' % args.spec)
        layout = design['layout']
        outdir = args.outdir or os.path.join(yards.yard_dir(args.spec), 'design')

    render(layout, outdir)


if __name__ == '__main__':
    main()
