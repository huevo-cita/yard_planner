#!/usr/bin/env python3
"""Draw a square-foot rotation map for a raised bed, colored by plant family.

    python3 draw_bed.py layout.json -o maps/bed-spring-2027.png

Coloring by family (rather than by crop) is the point: it makes the rotation legible at a
glance and makes a repeated family in the same quadrant obvious before it gets planted.

Layout spec:

{
  "title": "Raised Bed — Spring 2027",
  "subtitle": "Transplant window Feb 20 - Mar 15. Nightshades moved to the south half.",
  "width": 4,                          # x, feet across
  "length": 8,                         # y, feet along
  "top_label": "NORTH (tall end)",
  "bottom_label": "SOUTH",
  "left_wall": "WEST FENCE (evening shade)",
  "quadrants": true,                   # dashed quadrant lines + Q1..Q4 labels
  "cells": [
    {"x": 0, "y": 6, "w": 2, "h": 2, "crop": "Tomato x2", "family": "nightshade",
     "note": "caged"},
    {"x": 0, "y": 0, "w": 1, "h": 1, "crop": "Parsley", "family": "umbellifer",
     "fixed": true}
  ],
  "footnotes": ["Melons trellised on the north face.", "Sweet potatoes in a grow bag."]
}

x, y are the lower-left corner of the cell in feet from the bed's southwest corner.
"fixed": true hatches the cell to mark a zone that doesn't rotate.
Unknown family names fall back to grey and still render.

Requires: matplotlib
"""
import argparse
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle, Patch

FAMILY_COLORS = {
    'nightshade': '#e8998d',
    'cucurbit': '#9fd6b0',
    'brassica': '#7fb069',
    'legume': '#c5e09b',
    'allium': '#e8d5b7',
    'umbellifer': '#6ec6b3',
    'chenopod': '#b5d99c',
    'aster': '#cfe3a8',
    'mallow': '#f2b880',
    'mint': '#a8d8c8',
    'morning glory': '#d9b8e0',
    'grass': '#e0d9a8',
    'flower': '#b39ddb',
    'fallow': '#ded6c8',
}
FALLBACK = '#c9c9c9'


def draw(spec, path):
    w, ln = spec['width'], spec['length']
    fig, ax = plt.subplots(figsize=(max(6.0, w * 1.7), max(8.0, ln * 1.35)))
    ax.set_xlim(-2.2, w + 1.5)
    ax.set_ylim(-1.5 - 0.35 * len(spec.get('footnotes', [])), ln + 2.0)
    ax.set_aspect('equal')
    ax.axis('off')

    ax.text(-2.1, ln + 1.45, spec.get('title', 'Raised Bed'),
            fontsize=14, fontweight='bold', color='#3d3d3d')
    if spec.get('subtitle'):
        ax.text(-2.1, ln + 1.05, spec['subtitle'], fontsize=9.5, color='#666')

    ax.add_patch(Rectangle((0, 0), w, ln, fc='#f5efe2', ec='#6b5b45', lw=2.5, zorder=0))

    if spec.get('left_wall'):
        ax.add_patch(Rectangle((-1.35, -0.4), 0.18, ln + 0.8, fc='#9a8a76', zorder=1))
        ax.text(-1.62, ln / 2.0, spec['left_wall'], rotation=90, va='center',
                fontsize=8, color='#666', fontweight='bold')
    if spec.get('top_label'):
        ax.text(w / 2.0, ln + 0.3, spec['top_label'], ha='center', fontsize=8,
                color='#666', fontweight='bold')
    if spec.get('bottom_label'):
        ax.text(w / 2.0, -1.0, spec['bottom_label'], ha='center', fontsize=8,
                color='#666', fontweight='bold')

    # 1 ft grid
    for f in range(1, int(w)):
        ax.plot([f, f], [0, ln], color='#ddd2bd', lw=0.7, zorder=1)
    for f in range(1, int(ln)):
        ax.plot([0, w], [f, f], color='#ddd2bd', lw=0.7, zorder=1)

    for c in spec.get('cells', []):
        fam = (c.get('family') or '').lower()
        color = FAMILY_COLORS.get(fam, FALLBACK)
        ax.add_patch(Rectangle((c['x'], c['y']), c['w'], c['h'], fc=color, ec='white',
                               lw=1.8, hatch='///' if c.get('fixed') else None, zorder=2))
        label = c.get('crop', '')
        if c.get('note'):
            label += '\n(%s)' % c['note']
        ax.text(c['x'] + c['w'] / 2.0, c['y'] + c['h'] / 2.0, label, ha='center',
                va='center', fontsize=c.get('fontsize', 8.5), fontweight='bold',
                color='#2d2d2d', zorder=3)

    if spec.get('quadrants'):
        ax.plot([w / 2.0, w / 2.0], [0, ln], color='#8a7f6d', lw=1.4, ls='--', zorder=4)
        ax.plot([0, w], [ln / 2.0, ln / 2.0], color='#8a7f6d', lw=1.4, ls='--', zorder=4)
        # labelled in the outer margins, so they never sit on top of a crop name
        for name, (qx, qy) in {'Q1': (-0.42, 0.75), 'Q2': (w + 0.42, 0.75),
                               'Q3': (-0.42, 0.25), 'Q4': (w + 0.42, 0.25)}.items():
            ax.text(qx, qy * ln, name, ha='center', va='center', fontsize=10,
                    fontweight='bold', color='#8a7f6d', zorder=6)

    used = []
    for c in spec.get('cells', []):
        fam = (c.get('family') or '').lower()
        if fam and fam not in used:
            used.append(fam)
    if used:
        ax.legend(handles=[Patch(facecolor=FAMILY_COLORS.get(f, FALLBACK),
                                 edgecolor='white', label=f.title()) for f in used],
                  loc='upper left', bbox_to_anchor=(1.02, 0.88), frameon=False,
                  fontsize=8.5, title='Family', title_fontsize=9)

    for i, note in enumerate(spec.get('footnotes', [])):
        ax.text(-2.1, -1.35 - 0.35 * i, note, fontsize=7.5, color='#557', style='italic')

    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec', help='JSON layout file')
    ap.add_argument('-o', '--output', default='bed.png', help='output PNG path')
    args = ap.parse_args()

    with open(args.spec) as fh:
        spec = json.load(fh)
    outdir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(outdir, exist_ok=True)
    draw(spec, args.output)
    print('wrote', args.output)


if __name__ == '__main__':
    main()
