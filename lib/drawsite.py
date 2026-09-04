#!/usr/bin/env python3
"""Architectural drawings of a yard, rendered from its site.json.

    python3 -m lib.drawsite <slug> [--outdir maps]

Writes, into the yard's maps/ directory:

    site-plan.png       dimensioned plan, architectural conventions
    site-context.png    the yard's position on the lot, with neighbours
    elevation.png       looking at the primary wall
    section.png         a cut across the yard: what is tall, and how far away
Everything comes from site.json. Nothing is hard-coded here but drawing style.

Where a yard needs a callout that only makes sense for that yard, it goes in
site.json under `drawings`, not in this file:

    "drawings": {
      "plan": {
        "extent": [-152, 664, -472, 118],
        "title": "ASTORIA SIDE YARD — DIMENSIONED PLAN",
        "subtitle": "...",
        "context": [ {"kind": "street", "rect": [...], "label": "12th STREET"} ],
        "notes": [ {"text": "...", "at": [x, y], "arrow_to": [x, y]} ],
        "titleblock": [["Address", "..."], ["Lot area", "..."], ...]
      }
    }
"""
import argparse
import functools
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Polygon, Circle, Rectangle, Wedge
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

from . import design, doubts, siteschema, solar, sunmodel, yards

INK = "#2f3437"
MUTED = "#6b7280"
DIM = "#b03a2e"          # dimension lines, red as per drafting convention
SOIL = "#f4efe4"
LAWN = "#dfe8cf"
WOOD = "#d9b98c"
WOOD_LINE = "#a9814f"
STRIP = "#cbd8bd"
FENCE = "#4f6b3e"
HOUSE = "#ddd6cb"
HOUSE_EDGE = "#8a7f6d"
PAVER = "#cfcac1"
CANOPY = "#7d9b6a"
STEEL = "#8d949c"
STREET = "#eceff1"

DIM_Z = 16

ZONE_STYLE = {
    "lawn": (LAWN, "#7e8f66"),
    "patio": (WOOD, "#8a6636"),
    "deck": (WOOD, "#8a6636"),
    "bed": (SOIL, "#8a7a55"),
    "strip": (STRIP, "#5c7a4b"),
    "gravel": (PAVER, "#8b867d"),
    "default": ("#eceae4", "#8a8478"),
}


def halo(color="white", lw=2.6):
    return [pe.withStroke(linewidth=lw, foreground=color)]


def ftin(inches):
    """Inches as feet and inches. Rounding to the nearest foot turns 19 ft 6 in
    into 20 ft, which is exactly the kind of quiet error this system exists to
    avoid."""
    ft = int(abs(inches)) // 12
    rem = abs(inches) - ft * 12
    sign = "-" if inches < 0 else ""
    if rem < 0.5:
        return f"{sign}{ft} ft"
    return f"{sign}{ft} ft {rem:.0f} in"


def wrap(text, width=54):
    import textwrap
    return textwrap.wrap(text, width) or [""]


# ---------------------------------------------------------------- dimensions

def dim_h(ax, x1, x2, y, text, side=1, gap=0, fs=8.5, color=DIM):
    """Horizontal dimension between x1 and x2, drawn at plot height y."""
    ax.annotate("", xy=(x1, y), xytext=(x2, y), zorder=DIM_Z,
                arrowprops=dict(arrowstyle="<|-|>", color=color, lw=1.0,
                                shrinkA=0, shrinkB=0, mutation_scale=9))
    for x in (x1, x2):
        ax.plot([x, x], [y - 4 * side, y + 4 * side], color=color, lw=0.8,
                zorder=DIM_Z)
    ax.text((x1 + x2) / 2.0, y + (7 + gap) * side, text, ha="center",
            va="bottom" if side > 0 else "top", fontsize=fs, color=color,
            fontweight="bold", zorder=DIM_Z + 1, path_effects=halo("white", 3.2))


def dim_v(ax, y1, y2, x, text, side=1, fs=8.5, color=DIM, rot=90, label_xy=None):
    """Vertical dimension between plot heights y1 and y2, drawn at x."""
    ax.annotate("", xy=(x, y1), xytext=(x, y2), zorder=DIM_Z,
                arrowprops=dict(arrowstyle="<|-|>", color=color, lw=1.0,
                                shrinkA=0, shrinkB=0, mutation_scale=9))
    for y in (y1, y2):
        ax.plot([x - 4 * side, x + 4 * side], [y, y], color=color, lw=0.8,
                zorder=DIM_Z)
    tx, ty = label_xy or (x + 7 * side, (y1 + y2) / 2.0)
    ax.text(tx, ty, text, ha="center", va="center", rotation=rot, fontsize=fs,
            color=color, fontweight="bold", zorder=DIM_Z + 1,
            path_effects=halo("white", 3.2))


def witness(ax, x, y1, y2, color=DIM):
    ax.plot([x, x], [y1, y2], color=color, lw=0.6, ls=(0, (5, 3)), alpha=0.8,
            zorder=DIM_Z)


def scalebar(ax, x, y, feet=5, label=True):
    L = feet * 12.0
    step = max(feet // 5, 1)
    n = feet // step
    for i in range(n):
        ax.add_patch(Rectangle((x + i * step * 12, y), step * 12, L * 0.075,
                               fc=INK if i % 2 == 0 else "white",
                               ec=INK, lw=0.8, zorder=12))
    ax.text(x, y - L * 0.15, "0", ha="center", fontsize=7.5, color=INK)
    ax.text(x + L, y - L * 0.15, f"{feet} ft", ha="center", fontsize=7.5, color=INK)
    if label:
        ax.text(x + L / 2.0, y + L * 0.15, "S C A L E", ha="center", fontsize=7,
                color=MUTED, fontweight="bold")


def north_plot_angle(site):
    """Plot angle of true north, derived rather than taken on trust.

    `frame.yard_north_true_bearing` is a convenience copy of a number the frame
    already fixes. +x is drawn to the right and plan y is negated, so bearing
    runs clockwise in the drawing exactly as it does in the world, north sits at
    `true_bearing_of_plus_x` anticlockwise from the drawn +x axis, and the angle
    this helper wants is that bearing less 90 degrees.

    Which makes the stored field redundant, and a redundant field nobody
    recomputes is one that can quietly disagree with the axis it was copied
    from. On a drawing whose entire purpose is to be carried outside and held up
    against the ground, a north arrow ninety degrees out is worse than no north
    arrow: it does not look wrong, it just makes every comparison wrong. So
    derive it, and fall back to the stored value only when the frame carries no
    bearing at all.

    Returns the angle and, when the two disagree by more than a degree, the
    stored value that lost, so a caller can say so on the drawing.
    """
    f = site.get("frame", {}) or {}
    stored = f.get("yard_north_true_bearing")
    xb = f.get("true_bearing_of_plus_x")
    if xb is None:
        return (stored or 0.0), None
    derived = (float(xb) - 90.0) % 360.0
    if stored is None:
        return derived, None
    off = abs((float(stored) - derived + 180.0) % 360.0 - 180.0)
    return derived, (None if off <= 1.0 else float(stored))


def north_arrows(ax, x, y, site, R=42):
    """True north, plus any second bearing the yard cares about."""
    yard_north, _ = north_plot_angle(site)
    arrows = [(yard_north, "TRUE\nNORTH", INK, 2.2, 1.0)]
    second = site.get("frame", {}).get("secondary_bearing")
    if second:
        arrows.append((second.get("plot_angle", 0.0), second.get("label", ""),
                       "#1f6f8b", 1.6, 0.58))
    for ang, lab, col, lw, f in arrows:
        a = math.radians(ang)
        dx, dy = -math.sin(a) * R * f, math.cos(a) * R * f
        ax.annotate("", xy=(x + dx, y + dy), xytext=(x, y),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=lw,
                                    mutation_scale=13), zorder=13)
        ax.text(x + dx * 1.34, y + dy * 1.34, lab, ha="center", va="center",
                fontsize=7.6, fontweight="bold", color=col, linespacing=1.15,
                zorder=13, path_effects=halo())
    ax.add_patch(Circle((x, y), R * 0.07, fc=INK, ec="none", zorder=13))


def line_step(step, size, per_in, k=1.5):
    """A line pitch in data units that is still legible at this drawing's scale.

    Every vertical pitch in this module was a bare data-unit constant tuned on a
    40 ft yard. Data units are inches of ground, so the same constant is worth a
    different number of POINTS on every drawing: 24 pt on a 40 ft extent, 12 pt
    on an 80 ft one, and 3.4 pt on a 73 ft lot drawn with its tree crowns, where
    every row of the titleblock and every line of the verify list landed on top
    of the one before it. The drawing did not fail, it just became a smear, which
    is the kind of fault you scroll past.

    Floor the pitch at `k` times the type size and leave it alone otherwise, so
    drawings that already read correctly are untouched.
    """
    return max(step, k * size / 72.0 * per_in) if per_in else step


def titleblock(ax, x, y, w, lines, title="SITE DATA", per_in=None):
    """Label left, value right, in a boxed panel.

    `per_in` is data units per inch. Given it, a row whose label and value are
    together too wide has its value stepped down in size until the pair fits.
    Without it the two texts simply overlap: the value is right-aligned and the
    label left-aligned, so a long value slides silently underneath the label and
    both become unreadable, which looks like a font bug rather than an overflow.
    """
    pitch = line_step(11.5, 7.2, per_in)
    # The heading's own drop from the box edge has to scale too. At 9 data units
    # below the top it sat neatly inside a 40 ft drawing and straddled the border
    # on a large one, because 9 in of ground is a third of a character there.
    lead = max(9.0, 0.95 * 9.5 / 72.0 * per_in) if per_in else 9.0
    ax.add_patch(Rectangle((x, y), w, -(lead + pitch * (len(lines) + 0.5)),
                           fc="white", ec=INK, lw=1.2, zorder=14))
    ax.text(x + 6, y - lead, title, fontsize=9.5, fontweight="bold", color=INK,
            zorder=15)
    for i, (k, v) in enumerate(lines):
        yy = y - lead - pitch * (i + 1)
        size = 7.2
        if per_in:
            budget = (w - 16) / per_in
            while size > 5.4 and (text_width_in(str(k), 7.2)
                                  + text_width_in(str(v), size)) > budget:
                size -= 0.2
        ax.text(x + 6, yy, k, fontsize=7.2, color=MUTED, zorder=15)
        ax.text(x + w - 6, yy, str(v), fontsize=size, color=INK, ha="right",
                fontweight="bold", zorder=15)


@functools.lru_cache(maxsize=8192)
def _width_per_point(s):
    """Glyph-outline width of a string, per point of type size.

    A string's rendered width is exactly proportional to its size — the glyph
    outlines are one shape scaled — so one measurement answers every size, and
    the measurement is the expensive part. Building the outline and taking its
    extents costs about 60 ms a string here, and `fit_columns` asks the same
    question thousands of times while it walks down the wrap widths: measuring
    naively put two minutes into laying out three text panels, which is long
    enough that a drawing stops being re-run and starts being remembered.
    """
    return TextPath((0, 0), s, size=1.0,
                    prop=FontProperties()).get_extents().width / 72.0


def text_width_in(s, size):
    """Rendered width of a string in inches, at a font size in points.

    Measured off the actual glyph outlines rather than estimated from a
    characters-per-inch guess, because the guess is wrong by enough to run a
    column of text off the edge of the page and the failure is silent.
    """
    if not s:
        return 0.0
    return _width_per_point(s) * size


def fit_columns(items, col_in, size=7.6, indent=0, lo=18, hi=72):
    """The widest wrap, in characters, whose longest line still fits `col_in`.

    Wrapping is not monotonic in the obvious way — a narrower wrap can produce a
    longer worst line than a wider one, because of where the breaks land — so
    this walks down from `hi` and takes the first width that genuinely fits.
    """
    budget = col_in - indent * size * 0.5 / 72.0
    for cols in range(hi, lo - 1, -1):
        widest = max((text_width_in(c, size)
                      for it in items for c in wrap(it, cols)), default=0.0)
        if widest <= budget:
            return cols
    return lo


def _wrap_ceiling(items, col_in, size, slack=1.15):
    """A wrap width no answer can be wider than, to start `fit_columns` from.

    `fit_columns` walks widths down one character at a time and measures the
    wrap at each, so where it starts decides most of what it costs. Starting
    from a fixed constant means walking sixty widths that were never going to
    fit before reaching the plausible ones — two minutes of glyph measurement
    on a page of prose panels.

    The bound comes from the text itself: the mean glyph width of these very
    strings, which is a far tighter estimate than any characters-per-inch rule
    and cannot be badly wrong about its own content. Scaled up by `slack`
    because the mean is not the maximum and a ceiling that lands below the true
    answer would quietly cost a column of readable width.
    """
    joined = "".join(items)
    if not joined:
        return 24
    mean = _width_per_point(joined) / len(joined) * size
    return max(24, min(240, int(col_in / mean * slack) + 4))


def notes_block(ax, x, y, lines, step=15, heading_size=8.4, size=7.6, zorder=15,
                per_in=None):
    """A left-aligned block of annotation lines.

    Drawn above the zone fills. Without an explicit zorder these land at the
    text default of 3, under the zone patches at 4, so any note overlapping a
    lawn or a bed had its first characters painted over — which reads as a
    clipped column rather than as a layering fault and sends you looking at the
    text width instead.
    """
    step = line_step(step, size, per_in)
    for i, ln in enumerate(lines):
        ax.text(x, y - step * i, ln,
                fontsize=heading_size if i == 0 else size,
                color=DIM if i == 0 else MUTED,
                fontweight="bold" if i == 0 else "normal",
                zorder=zorder, path_effects=halo("white", 3))


def annotate_all(ax, notes, default_color=INK):
    """Free-form callouts declared in site.json."""
    for n in notes or []:
        kw = dict(fontsize=n.get("size", 8.0), color=n.get("color", default_color),
                  ha=n.get("ha", "center"), va=n.get("va", "center"),
                  linespacing=1.4, zorder=n.get("zorder", 12))
        if n.get("bold"):
            kw["fontweight"] = "bold"
        if n.get("rotation"):
            kw["rotation"] = n["rotation"]
        if n.get("italic"):
            kw["style"] = "italic"
        if n.get("arrow_to"):
            ax.annotate(n["text"], xy=tuple(n["arrow_to"]), xytext=tuple(n["at"]),
                        path_effects=halo("white", 3),
                        arrowprops=dict(arrowstyle="-|>", color=kw["color"],
                                        lw=1.1), **kw)
        else:
            if n.get("box"):
                kw["bbox"] = dict(boxstyle="round,pad=0.5", fc="#f8f8f5",
                                  ec="#d6d2c8")
            ax.text(n["at"][0], n["at"][1], n["text"], **kw)


def data_per_inch(fig, ax, ext, ylim=None):
    """Data units per drawn inch, with the equal-aspect fit honoured.

    Everything that sizes text against the drawing — the wrap widths, the line
    pitches, the titleblock step-down — needs to know how many inches of ground
    land on an inch of paper. Dividing the extent by the axes' nominal width
    gets that wrong whenever the drawing is taller than its axes box, because
    an equal-aspect axis then shrinks its WIDTH to fit the height and the
    fraction of the figure it was allotted stops being the fraction it uses.

    The error is one-directional and therefore nasty: the scale comes out too
    small, so every column is believed wider than it is, and prose wrapped to
    that belief prints out through the right-hand border of the panel it was
    measured for. On a plan drawn portrait with tall tree crowns it ran a whole
    legend past the edge of its own box.

    matplotlib picks the single scale that fits both axes, so the honest figure
    is whichever of the two ratios is larger. Pass `ylim` when the caller is
    about to grow the y range for a header, since that is the range the axes
    will actually be fitted to.
    """
    pos = ax.get_position()
    fw, fh = fig.get_size_inches()
    dw = ext[1] - ext[0]
    dh = (ylim[1] - ylim[0]) if ylim else (ext[3] - ext[2])
    avail_w, avail_h = pos.width * fw, pos.height * fh
    if avail_w <= 0 or avail_h <= 0:
        return dw / max(fw, 1e-6)
    return max(dw / avail_w, dh / avail_h)


def frame(extent, figsize):
    # An equal-aspect axis inside a figure of a different shape pads one side
    # with dead white space, so the figure follows the extent unless the yard
    # asked for a specific size.
    w, h = extent[1] - extent[0], extent[3] - extent[2]
    if w > 0 and h > 0:
        want = h / w
        have = figsize[1] / figsize[0]
        if abs(want - have) > 0.12:
            figsize = [figsize[0], round(figsize[0] * want, 2)] \
                if want < 2.2 else [round(figsize[1] / want, 2), figsize[1]]
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


# ------------------------------------------------------------------- helpers

class Geom:
    """The handful of numbers every drawing needs, pulled out once."""

    def __init__(self, site):
        b = site["boundary"]
        self.S = site
        self.s = float(b.get("north_fence_slope") or 0.0)
        self.W = float(b["width_east_west"])
        self.C = float(b["south_boundary_offset"])
        self.trees = siteschema.trees(site)
        self.draw = site.get("drawings", {}) or {}

    def nf(self, x):
        """Plot y of the sloped north boundary at x."""
        return -self.s * x

    @property
    def yS(self):
        return -self.C

    def outline(self):
        return [(0, 0), (self.W, self.nf(self.W)), (self.W, self.yS), (0, self.yS)]

    def spec(self, name, key, default=None):
        return (self.draw.get(name, {}) or {}).get(key, default)

    def extent(self, name, default):
        return self.spec(name, "extent", default)

    def zone_polygon(self, z):
        """A zone as a plan polygon, honouring the sloped boundary."""
        x0, x1 = z.get("x", [0, self.W])
        if z.get("y"):
            y0, y1 = z["y"]
            return [(x0, -y0), (x1, -y0), (x1, -y1), (x0, -y1)]
        north = z.get("y_north")
        south = z.get("y_south", self.C)
        south = self.C if not isinstance(south, (int, float)) else south
        if isinstance(north, (int, float)):
            return [(x0, -north), (x1, -north), (x1, -south), (x0, -south)]
        return [(x0, self.nf(x0)), (x1, self.nf(x1)), (x1, -south), (x0, -south)]


def draw_context_shapes(ax, items):
    """Streets, parking, neighbouring ground: whatever the yard sits among."""
    for it in items or []:
        kind = it.get("kind", "area")
        fc = {"street": STREET, "parking": "#f0f0ec", "open": "#f0f0ec",
              "lot": "#f5f5f2"}.get(kind, "#f2f2ee")
        if it.get("rect"):
            x, y, w, h = it["rect"]
            ax.add_patch(Rectangle((x, y), w, h, fc=it.get("fill", fc),
                                   ec=it.get("edge", "none"),
                                   lw=it.get("lw", 0), zorder=it.get("zorder", 0),
                                   ls=(0, (4, 3)) if it.get("dashed") else "-"))
        elif it.get("polygon"):
            ax.add_patch(Polygon([tuple(p) for p in it["polygon"]], closed=True,
                                 fc=it.get("fill", fc),
                                 ec=it.get("edge", "#d6d2c8"),
                                 lw=it.get("lw", 1.0), zorder=it.get("zorder", 0)))
        if it.get("label"):
            ax.text(it["label_at"][0], it["label_at"][1], it["label"],
                    fontsize=it.get("size", 10), color=it.get("color", "#9aa0a6"),
                    fontweight="bold", ha="center",
                    rotation=it.get("rotation", 0), zorder=2)


# ---------------------------------------------------------------- site plan

def _verify_line(v):
    """One `verify_on_site` entry as the single line the plan draws it on.

    The schema says these are plain strings, and a dict here used to reach
    `textwrap` and die on `expandtabs` eight frames down, which says nothing
    about the record that caused it. Accept the richer form the doubt board
    uses, since it is the obvious thing to write, and keep the drawing to the
    one field that belongs on a plan — the rest of it is the card's job.
    """
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for key in ("what", "question", "title", "note"):
            if isinstance(v.get(key), str):
                return v[key]
    return str(v)


def draw_plan(site, path):
    g = Geom(site)
    W, C, yS = g.W, g.C, g.yS
    ext = g.extent("plan", [-0.65 * W, 2.85 * W, -1.47 * C, 0.37 * C])
    fig, ax = frame(ext, g.spec("plan", "figsize", [16.5, 12.4]))

    draw_context_shapes(ax, g.spec("plan", "context"))

    # the house, drawn beyond the yard's edge
    ho = site.get("obstructions", {}).get("house")
    if ho:
        y0, y1 = ho["wall_y"]
        width = float(ho.get("width") or 0)
        ax.add_patch(Rectangle((ho["wall_x"], -y1), width, y1 - y0, fc=HOUSE,
                               ec=HOUSE_EDGE, lw=1.6, zorder=1))
        if width:
            ax.text(ho["wall_x"] + width / 2, -(y0 + y1) / 2, "HOUSE",
                    fontsize=15, fontweight="bold", color="#7c7264",
                    ha="center", rotation=90, zorder=2)

    # the yard
    ax.add_patch(Polygon(g.outline(), closed=True, fc=SOIL, ec=INK, lw=2.6,
                         zorder=3))

    for key, z in (site.get("zones") or {}).items():
        style = ZONE_STYLE.get(z.get("style", key.split("_")[-1]),
                               ZONE_STYLE["default"])
        poly = g.zone_polygon(z)
        ax.add_patch(Polygon(poly, closed=True, fc=style[0], ec="none",
                             hatch=z.get("hatch"), alpha=0.95, zorder=4))
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        width = max(p[0] for p in poly) - min(p[0] for p in poly)
        label = (z.get("label_short") or z.get("label") or key).upper()
        # a narrow strip gets its label turned to run along it
        rot = 90 if width < 0.22 * W else 0
        ax.text(cx, cy, label, fontsize=z.get("label_size", 11),
                fontweight="bold", color=style[1], ha="center", va="center",
                rotation=rot, zorder=6, path_effects=halo(style[0], 4))
        if z.get("area_sqft"):
            off = (0, -21) if rot == 0 else (16, 0)
            ax.text(cx + off[0], cy + off[1], f"{z['area_sqft']:.0f} sq ft",
                    fontsize=8.4, color=style[1], ha="center", va="center",
                    rotation=rot, zorder=6, path_effects=halo(style[0], 3))

    # decking, laid across whichever zone is built of boards
    for key, z in (site.get("zones") or {}).items():
        if z.get("style") not in ("patio", "deck") or not z.get("y"):
            continue
        x0, x1 = z.get("x", [0, W])
        y0, y1 = z["y"]
        for i in range(1, int((y1 - y0) / 8)):
            ax.plot([x0, x1], [-y1 + i * 8] * 2, color=WOOD_LINE, lw=0.55,
                    alpha=0.65, zorder=6)

    # anything paved, edged or laid down that is not a zone in its own right
    for ov in (site.get("features") or {}).get("overlays", []):
        pts = [(p[0], -p[1]) for p in ov["polygon"]]
        ax.add_patch(Polygon(pts, closed=True, fc=ov.get("fill", PAVER),
                             ec=ov.get("edge", "#aaa49a"), lw=0.9,
                             hatch=ov.get("hatch"), alpha=0.95, zorder=6))

    # fences
    for f in site.get("obstructions", {}).get("fences", []):
        # Clamped to the yard by default, because a boundary fence drawn past
        # the plot reads as someone else's. A wall that genuinely runs beyond
        # the modelled ground — a house flank, usually — says so and is left
        # alone, with the drawing's own extent deciding what is visible.
        pts = [(p[0], -p[1]) for p in f["points"]]
        if not f.get("extends_beyond_yard"):
            pts = [(max(min(x, W), 0), max(min(y, 0), yS)) for x, y in pts]
        colour = HOUSE_EDGE if "house" in str(f.get("id", "")).lower() else FENCE
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=colour, lw=5.5,
                solid_capstyle="butt", zorder=8, clip_on=True)
    for legacy, pts in (("west_fence", None), ("north_fence", None)):
        blk = site.get("obstructions", {}).get(legacy)
        if not blk:
            continue
        if legacy == "west_fence":
            ax.plot([blk["x"], blk["x"]], [0, yS], color=FENCE, lw=5.5,
                    solid_capstyle="butt", zorder=8)
        else:
            ax.plot([0, W], [0, g.nf(W)], color=FENCE, lw=5.5,
                    solid_capstyle="butt", zorder=8)

    # the house wall along the yard
    if ho:
        ax.plot([ho["wall_x"], ho["wall_x"]], [g.nf(W), yS], color=HOUSE_EDGE,
                lw=5.5, solid_capstyle="butt", zorder=9)

    # half-round wells in a wall
    ww = (site.get("features") or {}).get("window_wells")
    if ww:
        for i, cy in enumerate(ww["centers_y"]):
            ax.add_patch(Wedge((ww.get("wall_x", W), -cy), ww["radius"], 90, 270,
                               fc="#e8eaec", ec=STEEL, lw=1.6, zorder=10))
            ax.text(ww.get("wall_x", W) - ww["radius"] - 6, -cy, f"WW{i + 1}",
                    fontsize=7.4, color="#5f666d", fontweight="bold",
                    ha="right", va="center", zorder=11)

    # overhead planes: awnings, pergolas, the roof edge itself
    for ov in site.get("obstructions", {}).get("overheads", []) or []:
        ox0, ox1 = min(ov["x"]), max(ov["x"])
        oy0, oy1 = min(ov["y"]), max(ov["y"])
        for ring in (ov.get("polygon"), ov.get("hole")):
            if ring:
                ax.add_patch(Polygon([(p[0], -p[1]) for p in ring], closed=True,
                                     fc="none", ec="#8a6d3b", lw=1.6,
                                     ls=(0, (7, 4)), zorder=10, clip_on=True))
        if not ov.get("polygon"):
            ax.add_patch(Rectangle((ox0, -oy1), ox1 - ox0, oy1 - oy0, fc="none",
                                   ec="#8a6d3b", lw=1.6, ls=(0, (7, 4)),
                                   zorder=10, clip_on=True))
        ax.text((ox0 + ox1) / 2, -(oy0 + oy1) / 2,
                (ov.get("label") or ov.get("id", "")).upper(),
                fontsize=7.2, fontweight="bold", color="#8a6d3b",
                ha="center", va="center", zorder=11, clip_on=True,
                path_effects=halo("white", 3))

    # trees, crown then trunk. Clipped, because the trees that matter to a
    # shade model are routinely on someone else's lot.
    for n, t in enumerate(g.trees, 1):
        if t.get("crown_radius"):
            ax.add_patch(Circle((t["crown_center_x"], -t["crown_center_y"]),
                                t["crown_radius"], fc=CANOPY, ec="#5c7a4b",
                                lw=1.1, ls=(0, (6, 4)), alpha=0.24, zorder=7,
                                clip_on=True))
    for n, t in enumerate(g.trees, 1):
        ax.add_patch(Circle((t["trunk_x"], -t["trunk_y"]), 7.5, fc="#6b4f34",
                            ec="white", lw=1.2, zorder=11, clip_on=True))
        ax.text(t["trunk_x"] + 15, -t["trunk_y"], str(n), fontsize=8,
                fontweight="bold", color="#6b4f34", va="center", zorder=11,
                clip_on=True)

    # proposed barriers
    for bar in site.get("obstructions", {}).get("proposed_barriers", []):
        pts = bar.get("points", [[0, C], [W, C]])
        ax.plot([p[0] for p in pts], [-p[1] for p in pts], color="#7d3c98",
                lw=3.0, ls=(0, (9, 5)), zorder=10)
        ax.text(sum(p[0] for p in pts) / len(pts), -pts[0][1] - 15,
                bar.get("label", "proposed barrier").upper(),
                fontsize=8.4, color="#7d3c98", fontweight="bold", ha="center")

    # dimensions: the measurements the yard was actually fitted from
    for st in site["boundary"].get("measured_depths", []):
        x = st.get("x")
        if x is None:
            continue
        dim_v(ax, g.nf(x), yS, x, f'{st["depth"]:.0f}"', side=-1, fs=8.4, rot=0,
              label_xy=(x, ext[3] * 0.14))
    dim_v(ax, 0, yS, -34, f'{C:.0f}"  along the west edge', side=-1, fs=8.4)
    dim_h(ax, 0, W, yS - 68, f'{W:.0f}"  ({ftin(W)})', side=-1, fs=9)
    witness(ax, 0, yS, yS - 64)
    witness(ax, W, yS, yS - 64)

    annotate_all(ax, g.spec("plan", "notes"))
    na = g.spec("plan", "north_arrow_at",
                [ext[1] - 0.12 * (ext[1] - ext[0]),
                 ext[2] + 0.86 * (ext[3] - ext[2])])
    north_arrows(ax, na[0], na[1], site, R=52)
    scalebar(ax, ext[0] + 6, ext[2] + 0.07 * (ext[3] - ext[2]), 5)

    # Everything below is laid out before anything is drawn, because both the
    # header and the verify column size themselves from their own content and
    # both used to be drawn straight into the data area — the header downward
    # from the top edge, the verify list downward from 44% of the height. Each
    # was fine at the length it was written at and silently destroyed the
    # drawing when the record grew: the subtitle began painting over the house,
    # and the verify list ran off the bottom of the page. Reserve the room, then
    # draw. A dimensioned plan that clips is worse than no plan, because the
    # missing part is invisible rather than obviously absent.
    sub = g.spec("plan", "subtitle",
                 "All dimensions in inches, as measured on site.")
    axes_in = ax.get_position().width * fig.get_size_inches()[0]
    per_in = (ext[1] - ext[0]) / axes_in
    sub_lines = wrap(sub, fit_columns([sub], axes_in, size=9.0))
    sub_pitch = line_step(13, 9.0, per_in)
    head_h = 2.2 * sub_pitch + sub_pitch * len(sub_lines)

    tb = g.spec("plan", "titleblock") or default_titleblock(site, g)
    tb = refresh_derived(site, tb)
    tb_x = ext[1] - 0.24 * (ext[1] - ext[0])

    # The verify list is wrapped to the column it is actually drawn in, measured
    # rather than estimated. A thorough record grows this list, and both a fixed
    # character count and a guessed character width silently ran the longest and
    # most important items off the right edge of the page.
    items = [_verify_line(v) for v in (site.get("verify_on_site", []) or [])]
    lines, v_top, foot_h = [], ext[2] + 0.44 * (ext[3] - ext[2]), 0.0
    if items:
        # Measured off the axes, not the figure: `frame` may rewrite figsize to
        # match the extent's aspect, and the axes then takes only part of that
        # after margins. Using the figure width overestimated the column by a
        # third and put the wrap back over the edge.
        col_in = (ext[1] - tb_x) / (ext[1] - ext[0]) * axes_in
        cols = fit_columns(items, col_in, size=7.6, indent=2)
        lines = ["VERIFY ON SITE"]
        for v in items:
            chunks = wrap(v, cols)
            lines.append("· " + chunks[0])
            lines.extend("  " + c for c in chunks[1:])
        # Grow the canvas downward rather than let the tail fall off it. Moving
        # the block up instead would run it into the titleblock, and shrinking
        # the type is what makes a verify list stop being read.
        foot_h = max(0.0, line_step(13, 7.6, per_in) * len(lines)
                     - (v_top - ext[2]))

    ax.set_ylim(ext[2] - foot_h, ext[3] + head_h)

    top = ext[3] + head_h
    ax.text(ext[0] + 4, top - 1.05 * sub_pitch,
            g.spec("plan", "title", f"{site.get('title', site.get('yard', ''))} "
                                    "— DIMENSIONED PLAN"),
            fontsize=16, fontweight="bold", color=INK, zorder=16,
            path_effects=halo("white", 4))
    for i, line in enumerate(sub_lines):
        ax.text(ext[0] + 4, top - 2.2 * sub_pitch - i * sub_pitch, line,
                fontsize=9, color=MUTED, zorder=16,
                path_effects=halo("white", 3))

    titleblock(ax, tb_x, ext[3] - 0.16 * (ext[3] - ext[2]),
               0.21 * (ext[1] - ext[0]), tb, per_in=per_in)
    if lines:
        notes_block(ax, tb_x, v_top, lines, step=13, per_in=per_in)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


def refresh_derived(site, rows):
    """Recompute the titleblock rows that are statistics rather than facts.

    A hand-authored titleblock in site.json is mostly durable — a parcel id or a
    lot bearing does not drift. The measured fraction does, every time a reading
    lands or a claim is withdrawn, and a stale one is the exact failure this
    drawing exists to expose: a number that looks surveyed and is not. So it is
    always taken live and the literal in the file is ignored.
    """
    try:
        live = "%.0f%%" % (100 * siteschema.measured_fraction(site))
    except Exception:
        return rows
    out = []
    for row in rows:
        label, value = row[0], row[1]
        if label.strip().lower() == "measured" and value != live:
            row = (label, live)
        out.append(row)
    return out


def default_titleblock(site, g):
    a = site.get("address", {})
    b = site["boundary"]
    rows = []
    if a.get("mailing"):
        rows.append(("Address", a["mailing"]))
    if a.get("lat"):
        rows.append(("Lat / Lon", f"{a['lat']:.5f}, {a['lon']:.5f}"))
    rows.append(("Yard area", f"{b.get('area_sqft', 0):.0f} sq ft"))
    rows.append(("Width", f'{g.W:.0f}"  ({ftin(g.W)})'))
    rows.append(("Depth, west", f'{b.get("depth_along_west_fence", g.C):.0f}"'))
    if b.get("north_fence_angle_off_square_deg"):
        rows.append(("Boundary angle",
                     f"{b['north_fence_angle_off_square_deg']:.2f}° off square"))
    f = site.get("frame", {})
    if f.get("true_bearing_of_plus_x") is not None:
        rows.append(("X axis bearing", f"true {f['true_bearing_of_plus_x']:.2f}°"))
    return rows


# ------------------------------------------------------------------- context

def draw_context(site, path):
    """The yard's position on the lot, with the neighbours that cast shade."""
    g = Geom(site)
    W, C = g.W, g.C
    ext = g.extent("context", [-1.25 * W, 3.4 * W, -3.3 * C, 1.25 * C])
    fig, ax = frame(ext, g.spec("context", "figsize", [11.6, 15.0]))

    draw_context_shapes(ax, g.spec("context", "context"))

    for bd in site.get("obstructions", {}).get("context_buildings", []):
        xs = [p[0] for p in bd["polygon"]]
        ys = [-p[1] for p in bd["polygon"]]
        if max(xs) < ext[0] or min(xs) > ext[1] or max(ys) < ext[2] \
                or min(ys) > ext[3]:
            continue
        ax.add_patch(Polygon(list(zip(xs, ys)), closed=True, fc="#e4e4e0",
                             ec="#c2beb5", lw=0.9, zorder=1))
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        if ext[0] < mx < ext[1] and ext[2] < my < ext[3]:
            ax.text(mx, my, f"{bd['height'] / 12:.0f} ft", fontsize=6.6,
                    color="#a5a09a", ha="center", va="center", zorder=2)

    ho = site.get("obstructions", {}).get("house")
    if ho:
        y0, y1 = ho["wall_y"]
        ax.add_patch(Rectangle((ho["wall_x"], -y1), float(ho.get("width") or 0),
                               y1 - y0, fc=HOUSE, ec=HOUSE_EDGE, lw=1.8, zorder=3))

    if site.get("address", {}).get("lot_polygon"):
        ax.add_patch(Polygon([(p[0], -p[1]) for p in
                              site["address"]["lot_polygon"]], closed=True,
                             fc="none", ec="#b03a2e", lw=1.6, ls=(0, (8, 5)),
                             zorder=2))

    ax.add_patch(Polygon(g.outline(), closed=True, fc="#cfe0b8", ec=INK, lw=2.4,
                         zorder=5))
    ax.text(W / 2, -C / 2, f"THE YARD\n{site['boundary'].get('area_sqft', 0):.0f}"
                           " sq ft", fontsize=12, fontweight="bold",
            color="#5d7345", ha="center", va="center", linespacing=1.4, zorder=6)

    annotate_all(ax, g.spec("context", "notes"))
    north_arrows(ax, ext[1] - 0.10 * (ext[1] - ext[0]),
                 ext[3] - 0.10 * (ext[3] - ext[2]), site, R=96)
    scalebar(ax, ext[0] + 8, ext[2] + 0.06 * (ext[3] - ext[2]), 20)
    ax.text(ext[0] + 4, ext[3] - 20,
            g.spec("context", "title", "THE YARD IN CONTEXT"), fontsize=15,
            fontweight="bold", color=INK)
    ax.text(ext[0] + 4, ext[3] - 44, g.spec(
        "context", "subtitle",
        "Neighbouring footprints and heights from OSM and city data."),
        fontsize=8.6, color=MUTED)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# ----------------------------------------------------------------- elevation

def draw_elevation(site, path):
    """Looking at the primary wall. Horizontal axis runs along the wall."""
    g = Geom(site)
    ho = site.get("obstructions", {}).get("house")
    if not ho:
        return
    W, C = g.W, g.C
    y0 = g.s * W
    eave = ho["eave_height"]
    ridge = float(ho.get("ridge_height") or eave)
    ext = g.extent("elevation", [y0 - 96, C + 116, -52, ridge + 86])
    fig, ax = frame(ext, g.spec("elevation", "figsize", [10.4, 8.6]))

    ax.add_patch(Rectangle((y0, 0), C - y0, eave, fc=HOUSE, ec=HOUSE_EDGE,
                           lw=2.0, zorder=3))
    if ridge > eave:
        ax.add_patch(Rectangle((y0, eave), C - y0, ridge - eave, fc="#eae4da",
                               ec=HOUSE_EDGE, lw=1.0, ls=(0, (6, 4)), zorder=2))
        ax.text((y0 + C) / 2, eave + 30,
                f"roof behind — ridge {ridge / 12:.0f} ft", fontsize=8,
                color="#948a7c", ha="center", zorder=4)
    ax.text((y0 + C) / 2, eave * 0.62, "HOUSE WALL", fontsize=13,
            fontweight="bold", color="#7c7264", ha="center", zorder=4)

    ax.plot([ext[0] + 22, ext[1] - 22], [0, 0], color=INK, lw=2.2, zorder=5)
    for x in range(int(ext[0] + 26), int(ext[1] - 22), 11):
        ax.plot([x, x - 7], [0, -7], color=MUTED, lw=0.6, zorder=4)

    ww = (site.get("features") or {}).get("window_wells")
    if ww:
        for i, cy in enumerate(ww["centers_y"]):
            ax.add_patch(Wedge((cy, 0), ww["radius"], 0, 180, fc="#e8eaec",
                               ec=STEEL, lw=1.6, zorder=7))
            ax.plot([cy - ww["radius"], cy + ww["radius"]],
                    [ww["guard_height"], ww["guard_height"]], color=STEEL,
                    lw=2.4, zorder=8)
            ax.text(cy, -19, f"WW{i + 1}", fontsize=7.8, color="#5f666d",
                    fontweight="bold", ha="center", zorder=8)

    for f in site.get("obstructions", {}).get("fences", []) or []:
        pass
    nf = site.get("obstructions", {}).get("north_fence")
    if nf:
        ax.plot([y0, y0], [0, nf["height"]], color=FENCE, lw=4.0, zorder=6)
        ax.annotate(f"north fence  {nf['height'] / 12:.0f} ft",
                    xy=(y0 + 3, nf["height"] * 0.72), xytext=(y0 + 46, 104),
                    fontsize=7.8, color=FENCE, fontweight="bold", ha="left",
                    arrowprops=dict(arrowstyle="-|>", color=FENCE, lw=1.0))

    levels = [(eave, f"{eave / 12:.0f} ft eave")]
    if ridge > eave:
        levels.append((ridge, f"{ridge / 12:.0f} ft ridge"))
    if nf:
        levels.insert(0, (nf["height"], f"{nf['height'] / 12:.0f} ft fence"))
    for h, lab in levels:
        ax.plot([ext[0] + 6, C + 62], [h, h], color="#c9ccce", lw=0.7,
                ls=(0, (6, 5)), zorder=1)
        ax.text(C + 66, h, lab, fontsize=7.2, color=MUTED, va="center")

    dim_v(ax, 0, eave, y0 - 50, f'{eave:.0f}"  ({eave / 12:.0f} ft)', side=-1, fs=8)
    dim_h(ax, y0, C, -32, f'{C - y0:.0f}"  yard length along the wall',
          side=-1, fs=8.4)

    annotate_all(ax, g.spec("elevation", "notes"))
    ax.text(ext[0] + 4, ext[3] - 8, g.spec(
        "elevation", "title", "ELEVATION — LOOKING AT THE HOUSE WALL"),
        fontsize=14, fontweight="bold", color=INK)
    ax.text(ext[0] + 4, ext[3] - 28, g.spec("elevation", "subtitle", ""),
            fontsize=8.6, color=MUTED)
    scalebar(ax, C + 10, ext[3] - 56, 5)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# ------------------------------------------------------------------- section

def crown_polygon(cx, cr, base, top, n=26):
    """Crown silhouette: broadest a little above mid-height."""
    pts = []
    for i in range(n + 1):
        f = i / n
        w = cr * math.sin(math.pi * (0.18 + 0.82 * f)) ** 0.75
        pts.append((cx + w, base + f * (top - base)))
    for i in range(n, -1, -1):
        f = i / n
        w = cr * math.sin(math.pi * (0.18 + 0.82 * f)) ** 0.75
        pts.append((cx - w, base + f * (top - base)))
    return pts


def draw_section(site, path):
    """A cut across the yard: what is tall, and how far away it stands."""
    g = Geom(site)
    W = g.W
    ho = site.get("obstructions", {}).get("house") or {}
    eave = float(ho.get("eave_height") or 0)
    ridge = float(ho.get("ridge_height") or eave)
    tallest = max([t.get("height") or 0 for t in g.trees] + [ridge, 1.0])
    ext = g.extent("section", [-1.45 * W, 3.0 * W, -0.65 * W, tallest * 1.42])
    fig, ax = frame(ext, g.spec("section", "figsize", [15.0, 14.2]))

    ax.plot([ext[0], ext[1]], [0, 0], color=INK, lw=2.2, zorder=6)
    for x in range(int(ext[0]) + 4, int(ext[1]), 14):
        ax.plot([x, x - 9], [0, -10], color="#c4c8ca", lw=0.6, zorder=3)
    ax.add_patch(Rectangle((0, -44), W, 44, fc=SOIL, ec="none", zorder=2))

    # trees, collapsed onto the section by their distance across the yard
    by_x = {}
    for t in g.trees:
        by_x.setdefault(round(t["crown_center_x"], 1), []).append(t)
    graze = None
    for cx, group in by_x.items():
        t = max(group, key=lambda q: q["height"])
        cr = t.get("crown_radius") or 0
        base = t["crown_base_height"]
        crown = crown_polygon(cx, cr, base, t["height"])
        ax.add_patch(Polygon(crown, closed=True, fc=CANOPY, ec="#4e6b3d", lw=1.3,
                             alpha=0.32, zorder=4))
        for k, _ in enumerate(group):
            dx = (k - (len(group) - 1) / 2.0) * 6
            ax.add_patch(Rectangle((cx + dx - 3.5, 0), 7, base, fc="#6b4f34",
                                   ec="none", alpha=0.9, zorder=5))
        outer = max(crown, key=lambda p: p[0])
        if graze is None or outer[1] > graze[1]:
            graze = outer
        dim_v(ax, 0, t["height"], cx - 128,
              f'{t["height"] / 12:.0f} ft', side=-1, fs=9)
        dim_v(ax, 0, base, cx - 58, f'crown base\n{base / 12:.0f} ft', side=-1,
              fs=7.4, rot=0)

    if ho:
        far = ho["wall_x"] + float(ho.get("width") or 0)
        ax.add_patch(Polygon([(ho["wall_x"], 0), (ho["wall_x"], eave),
                              (ho.get("ridge_x", ho["wall_x"]), ridge),
                              (far, eave), (far, 0)], closed=True, fc=HOUSE,
                             ec=HOUSE_EDGE, lw=2.0, zorder=5))
        ax.text((ho["wall_x"] + far) / 2, 96, "HOUSE", fontsize=13,
                fontweight="bold", color="#7c7264", ha="center", zorder=6)
        dim_v(ax, 0, eave, far + 24, f"{eave / 12:.0f} ft eave", side=1, fs=8)
        if ridge > eave:
            dim_v(ax, 0, ridge, far + 118, f"{ridge / 12:.0f} ft ridge", side=1,
                  fs=8)

    wf = site.get("obstructions", {}).get("west_fence")
    if wf:
        ax.plot([wf["x"], wf["x"]], [0, wf["height"]], color=FENCE, lw=5.0,
                zorder=7)
        ax.text(wf["x"] - 18, wf["height"] * 0.53,
                f"{wf['height'] / 12:.0f} ft fence", fontsize=8, color=FENCE,
                fontweight="bold", rotation=90, va="center", ha="center")

    # the altitude needed to see over each obstruction, from a few spots
    if graze and ho:
        for x0, tgt, col, tf in ((ho["wall_x"] - 4, graze, "#b03a2e", 0.80),
                                 (W / 7.0, graze, "#b03a2e", 0.34),
                                 (0, (ho["wall_x"], eave), "#1f6f8b", 0.58),
                                 (W / 2.0, (ho["wall_x"], eave), "#1f6f8b", 0.34)):
            if abs(tgt[0] - x0) < 1:
                continue
            ang = math.degrees(math.atan2(tgt[1], abs(tgt[0] - x0)))
            ax.plot([x0, tgt[0]], [0, tgt[1]], color=col, lw=1.2, ls=(0, (7, 4)),
                    zorder=8)
            ax.text(x0 + (tgt[0] - x0) * tf, tgt[1] * tf, f"{ang:.0f}°",
                    fontsize=8.6, color=col, fontweight="bold", ha="center",
                    va="center", zorder=9, path_effects=halo("white", 3.4))

    # real afternoon sun in this plane, and where its shade line lands
    if graze:
        sun = solar.SolarSite.from_site(site)
        wall_az = site.get("bearings_true", {}).get(
            "house_west_wall_faces",
            (site["frame"]["true_bearing_of_plus_x"] + 180.0) % 360.0)
        doy = solar.DOY["Jun 21"]
        y_lab = ext[3] * 0.88
        for hh in g.spec("section", "sun_hours", [13.0, 14.0, 15.0]):
            pa = solar.profile_angle(*sun.position(doy, hh), wall_azimuth=wall_az)
            if pa is None or pa <= 1:
                continue
            t = math.tan(math.radians(pa))
            land = graze[0] + graze[1] / t
            h_wall = graze[1] - (W - graze[0]) * t
            inside = land <= W
            col = "#e0a11b" if inside else "#c0392b"
            end = (land, 0.0) if inside else (W, max(h_wall, 0.0))
            x_top = graze[0] - (y_lab - graze[1]) / t
            ax.annotate("", xy=end, xytext=(x_top, y_lab),
                        arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6,
                                        alpha=0.92), zorder=10)
            ax.text(x_top, y_lab + 12,
                    f"{solar.fmt_clock(sun.solar_to_clock(doy, hh))}\n"
                    f"{pa:.0f}° in plane", fontsize=7.6, color=col,
                    fontweight="bold", ha="center", va="bottom",
                    linespacing=1.3, zorder=11)
            if inside:
                ax.plot([land], [0], marker="v", ms=9, color=col, zorder=11)
        ax.add_patch(Circle((graze[0], graze[1]), 6.5, fc="#c0392b", ec="white",
                            lw=1.2, zorder=12))

    dim_h(ax, 0, W, -74, f'{W:.0f}"  yard width', side=-1, fs=8.6)
    annotate_all(ax, g.spec("section", "notes"))
    ax.text(ext[0] + 4, ext[3] - 10, g.spec(
        "section", "title", "SECTION — LOOKING ACROSS THE YARD"), fontsize=14,
        fontweight="bold", color=INK)
    ax.text(ext[0] + 4, ext[3] - 28, g.spec("section", "subtitle", ""),
            fontsize=8.6, color=MUTED)
    scalebar(ax, ext[0] + 4, ext[3] * 0.84, 5)

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# ------------------------------------------------------- the crown field check

# A pace is not a unit. It is printed on the drawing next to every figure it
# produced, because somebody standing in a yard has no tape and every stride is
# different, and a paced distance quoted without the stride behind it cannot be
# checked or corrected later.
PACE_FT = 2.5

# The proportional range the crowns are checked over. A crown estimated by eye
# is wrong by a fraction of itself rather than by a fixed number of feet, so the
# error is a scaling; 0.7 to 1.6 is the span the yard's own doubt board prices
# its crowns across, and holding to it keeps this drawing and that card
# commensurable instead of two answers to the same question in different units.
CHECK_SCALES = (0.7, 1.0, 1.6)

# Days to cast on: one at each end of the leaf-on season and one at the
# solstice. December is deliberately absent — every crown that shades this kind
# of yard is bare by then, so a winter cast measures nothing about crown radius.
CHECK_DAYS = (79, 172, 265)

CHECK_HOUR_STEP = 0.25
CHECK_GRID = 13          # samples per zone edge

# Sun altitudes below this are not cast at all. A shadow's length goes as
# 1/tan(altitude), so near the horizon every crown reaches every bed: at 3
# degrees a fifty-foot tree throws four hundred feet of shade and the ranking
# collapses into a list of tree sizes. Ten degrees is where the beam stops
# being worth counting anyway — the air mass is above five, and in a yard with
# a six-foot fence and neighbours the low sun is blocked by something the
# ranking does not model. Held at ten rather than tuned: on the yard this was
# built for the tiers are identical anywhere from 3 to 15 degrees, so the
# figure earns its place by refusing the pathology, not by moving the answer.
CHECK_ALT_FLOOR = 10.0


def _light_band():
    """The narrowest gap between two of the light categories, in hours a day.

    This is the threshold that decides whether a tree is worth walking out to.
    It is read off `design.LIGHT_NEED` rather than chosen, because the only
    honest definition of "this crown matters" is that its own radius can move a
    bed from one nursery label to the next on its own, and the width of the
    tightest label is exactly that distance. Picking a round number instead
    would make the cut arbitrary in the one place somebody is most likely to
    argue with it.
    """
    floors = sorted({v[0] for v in design.LIGHT_NEED.values()})
    return min(b - a for a, b in zip(floors, floors[1:]))


def _zone_samples(z, n=CHECK_GRID):
    """A zone's footprint as cell centres, in yard coordinates."""
    x0, x1 = z["x"]
    y0, y1 = z["y"]
    return [(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n)
            for i in range(n) for j in range(n)]


def _shadow_ellipse(tree, scale, alt, az, x_bearing):
    """Where one crown's shadow lands on level ground, as an ellipse.

    The crown is taken at its widest horizontal section, halfway up, and cast
    down the beam. A disc's shadow on the flat is an ellipse: the radius across
    the beam, the radius over sin(altitude) along it, centred down-sun by the
    section's height over the tangent of the altitude.

    This is emphatically NOT the sun model. There is no house, no fence, no leaf
    transmissivity and no horizon here, so shade that falls on ground the wall
    already had is counted a second time. That is the right trade for the one
    question the field check asks — could this particular tree ever darken that
    particular bed, and by how much does its recorded radius move the answer —
    and it is the reason the output is called a share of the swing rather than a
    light level. Anything that needs a light level reads `sun-hours.json`.
    """
    a = math.radians(az - x_bearing)
    ux, uy = math.cos(a), math.sin(a)          # toward the sun, in plan
    r = tree["crown_radius"] * scale
    mid = (tree["crown_base_height"] + tree["height"]) / 2.0
    run = (mid - 2.0) / math.tan(math.radians(alt))
    return (tree["crown_center_x"] - ux * run, tree["crown_center_y"] - uy * run,
            r / math.sin(math.radians(alt)), r, ux, uy)


def _crown_shade_hours(tree, pts, scale, casts):
    """Hours a day this crown, at `scale`, lies over `pts`.

    Averaged over `casts`, which carries the sun's position at every sampled
    hour of every reference day, so the figure is comparable between trees and
    between beds and is in the same unit as everything else on the board.
    """
    if not tree.get("crown_radius") or not pts:
        return 0.0
    total = 0.0
    for alt, az, xb in casts:
        sx, sy, along_r, across_r, ux, uy = _shadow_ellipse(
            tree, scale, alt, az, xb)
        n = 0
        for px, py in pts:
            ex, ey = px - sx, py - sy
            along = -(ex * ux + ey * uy)
            across = ex * uy - ey * ux
            if (along / along_r) ** 2 + (across / across_r) ** 2 <= 1.0:
                n += 1
        total += n / len(pts) * CHECK_HOUR_STEP
    return total / len(CHECK_DAYS)


def _casts(site):
    """Sun altitude and azimuth at every sampled hour, with the frame bearing."""
    sun = solar.SolarSite.from_site(site)
    xb = float(site["frame"]["true_bearing_of_plus_x"])
    out = []
    for doy in CHECK_DAYS:
        rise, set_ = sun.day_length(doy)
        t = rise
        while t <= set_:
            alt, az = sun.position(doy, t)
            if alt > CHECK_ALT_FLOOR:
                out.append((alt, az, xb))
            t += CHECK_HOUR_STEP
    return out


def decisive_zones(site, slug=None):
    """The zones whose light category actually turns on the crown radii.

    Which beds move is a measured fact about one yard, not a rule, so it is
    read from that yard's `drawings.tree_map.decisive_zones` — the same place
    every other per-yard callout in this module comes from. It belongs in a
    file because the measurement that produced it was expensive: the doubt
    board priced it with the real sun model, house and fences and all, and this
    drawing's own casting geometry cannot reproduce that. Ground the wall
    already shades is counted twice here, which is harmless when ranking one
    tree against another and useless for deciding whether a bed flips.

    Failing that, take the single zone the open crown card prices itself over,
    and failing that every planted zone, which ranks the trees against the beds
    rather than against the decision and is the honest default when nobody has
    said which decision is live.

    Returns the zone keys and a short note naming where they came from.
    """
    spec = ((site.get("drawings", {}) or {}).get("tree_map", {})
            or {}).get("decisive_zones") or {}
    zones = site.get("zones") or {}
    keys = [k for k in (spec.get("zones") or []) if k in zones]
    if keys:
        cites = spec.get("cites")
        return keys, f"named by {cites}" if cites else "named in site.json"

    card = crown_card(site, slug)
    want = (card or {}).get("probe", {}).get("zone")
    if want:
        keys = [k for k, z in zones.items() if z.get("label_short") == want
                or z.get("label") == want]
        if keys:
            return keys, f"the zone {card['id']} prices itself over"

    keys = [k for k, z in zones.items()
            if z.get("style") == "bed" and z.get("x") and z.get("y")]
    return keys, "every planted zone; no yard has said which decision is live"


def crown_card(site, slug=None):
    """The open doubt card, if any, that is about the tree crowns.

    Found by what the card probes rather than by its id or its wording, so this
    drawing keeps pointing at the live question after the card is settled and
    the next one is filed.
    """
    slug = slug or site.get("yard")
    if not slug:
        return None
    try:
        cards = doubts.open_cards(slug)
    except Exception:
        return None
    for c in cards:
        if (c.get("probe") or {}).get("trees_field") == "crown_radius":
            return c
    return None


def crown_field_check(site, slug=None):
    """Every tree, ranked by how far its own crown radius could move a bed.

    One row per tree, carrying what somebody outside needs — the recorded
    height and radius in feet, the radius in paces so it can be walked, the
    beds the crown can reach, and how the record says each figure was arrived
    at — plus the number that sorts the list: `worst`, the hours a day of crown
    shade that this one tree's radius adds or removes across `CHECK_SCALES` on
    the worst-affected decisive bed.

    The point of ranking rather than listing is that the list is fourteen trees
    long and the afternoon is not. Half of them cannot reach a bed under any
    plausible error and measuring them teaches nothing; sending somebody out
    with all fourteen is how none of them get measured.

    `tier` is `measure`, `maybe` or `skip`, cut at `_light_band()` and a tenth
    of it. `governs` names the beds the tree's shadow can fall on, which is not
    the same as the beds its crown overhangs, and both are reported because
    only the second can be checked by standing underneath it.
    """
    trees_ = siteschema.trees(site)
    keys, source = decisive_zones(site, slug)
    zones = site.get("zones") or {}
    pts = {k: _zone_samples(zones[k]) for k in keys}
    names = {k: (zones[k].get("label_short") or k) for k in keys}
    casts = _casts(site)
    band = _light_band()

    rows = []
    for i, t in enumerate(trees_):
        r = t.get("crown_radius") or 0.0
        row = {
            "i": i, "id": t.get("id", f"tree-{i + 1}"),
            "species": t.get("species", "tree"), "tree": t,
            "height_ft": (t.get("height") or 0) / 12.0,
            "radius_ft": r / 12.0,
            "paces": r / 12.0 / PACE_FT,
            "height_src": (siteschema.provenance_of(
                site, f"features.trees.{i}.height") or {}).get("source", "—"),
            "radius_src": (siteschema.provenance_of(
                site, f"features.trees.{i}.crown_radius") or {}).get("source", "—"),
            "spreads": {}, "governs": [], "overhangs": [],
        }
        for k in keys:
            hours = [_crown_shade_hours(t, pts[k], s, casts) for s in CHECK_SCALES]
            row["spreads"][names[k]] = (min(hours), max(hours) - min(hours))
            if max(hours) > 0.0:
                row["governs"].append(names[k])
            # Standing over a bed and shading it are different questions and
            # both are wanted. The second is what costs light; the first is the
            # only one of the two that can be checked by looking up.
            if _reaches(t, zones[k], 1.0):
                row["overhangs"].append(names[k])
        row["worst"] = max([s for _, s in row["spreads"].values()] or [0.0])
        row["worst_zone"] = max(row["spreads"].items(),
                                key=lambda kv: kv[1][1])[0] if row["spreads"] else ""
        row["tier"] = ("measure" if row["worst"] >= band
                       else "maybe" if row["worst"] >= band / 10.0 else "skip")
        rows.append(row)

    rows.sort(key=lambda q: (-q["worst"], q["id"]))
    return rows, {"zones": [names[k] for k in keys], "source": source,
                  "band": band}


def engulfed_crowns(rows, stacking="single", groups=None):
    """Pairs where one crown is drawn wholly inside another, and it matters.

    Two crowns that overlap are two separate attenuations under
    `features.canopy_stacking: multiply`, so a small crown swallowed by a big
    one darkens its own footprint twice over — once as itself and once as the
    tree it is standing under. The record cannot tell that from two trees at
    opposite ends of a yard, and the arithmetic is invisible in the output.

    Worth surfacing on a drawing about crowns for a second reason: a tree whose
    crown is entirely inside another's is not measurable from the ground as a
    separate canopy, so a field check that asks for its radius is asking for
    something nobody can give.

    Containment has to be tested in three dimensions, not in plan. Crowns are
    ellipsoids floating clear of the ground, so two that sit one inside the
    other on a plan view can occupy completely separate bands of height and
    share no volume at all — cloverleaf-austin's t10 tops out at 14 ft and t11's
    crown does not begin until 18 ft. No ray passes through both, nothing is
    attenuated twice, and reporting the pair sends somebody out to check an
    overlap that is not there. The plan-only version of this test claimed
    exactly that.

    A pair declared fused in `features.canopy_groups` is left out too, because
    the model now attenuates such a group once and there is no double count left
    to report. `groups` is the tree-id-to-group map `sunmodel.Model` builds.
    """
    if stacking != "multiply":
        return []
    groups = groups or {}
    out = []
    for a in rows:
        ta = a["tree"]
        ra = ta.get("crown_radius") or 0.0
        for b in rows:
            tb = b["tree"]
            rb = tb.get("crown_radius") or 0.0
            if a is b or ra >= rb:
                continue
            gid = groups.get(a["id"])
            if gid is not None and gid == groups.get(b["id"]):
                continue
            d = math.hypot(ta["crown_center_x"] - tb["crown_center_x"],
                           ta["crown_center_y"] - tb["crown_center_y"])
            if d + ra > rb:
                continue
            if _height_overlap(ta, tb) <= 0:
                continue
            out.append((a["id"], b["id"]))
    return out


def _height_overlap(ta, tb):
    """Inches of height two crowns share. Zero or less means no shared volume."""
    def span(t):
        base, top = t.get("crown_base_height"), t.get("height")
        if base is None or top is None:
            return None
        return float(base), float(top)

    sa, sb = span(ta), span(tb)
    if sa is None or sb is None:
        return 0.0
    return min(sa[1], sb[1]) - max(sa[0], sb[0])


def _reaches(tree, z, scale=1.0):
    """Does the crown, at `scale`, stand over any part of this zone?"""
    r = (tree.get("crown_radius") or 0.0) * scale
    x0, x1 = z["x"]
    y0, y1 = z["y"]
    dx = max(x0 - tree["crown_center_x"], 0.0, tree["crown_center_x"] - x1)
    dy = max(y0 - tree["crown_center_y"], 0.0, tree["crown_center_y"] - y1)
    return math.hypot(dx, dy) <= r


def leaf_date(md):
    """'11-20' as '20 Nov'. A bare month-number is not a date in a field."""
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    try:
        m, d = str(md).split("-")
        return f"{int(d)} {months[int(m) - 1]}"
    except Exception:
        return str(md)


# ----------------------------------------------------------------- tree map

TIER_STYLE = {
    # fill, edge, ink, label weight
    "measure": ("#7d9b6a", "#3f5c2f", "#2f3437", "bold"),
    "maybe": ("#a9bd9a", "#6f8560", "#4a5157", "normal"),
    "skip": ("#d8d8d2", "#a8a8a0", "#9aa0a6", "normal"),
}
DECISIVE = "#b03a2e"


def _label_box(lines, size, per_in, pad=0.35):
    """A text block's footprint in data units: half-width, half-height."""
    w = max((text_width_in(ln, size) for ln in lines), default=0.0) * per_in
    pitch = line_step(0, size, per_in, k=1.25)
    h = pitch * len(lines)
    return w / 2.0 + pad * pitch, h / 2.0 + pad * pitch, pitch


def _place_label(anchor, half, taken, ext, prefer):
    """A spot for one label that lands on nothing already placed.

    Candidates ring the trunk at a few radii and sixteen bearings; the first
    that clears every box already taken, every trunk, and the drawing's own
    edge, wins. Leading a label out on a line is only worth doing if the label
    at the end of it is readable, and two labels on top of each other are
    neither readable nor obviously broken — they just look like one label with
    a font fault, which is the failure this walks a ring to avoid.

    `prefer` is the direction to try first, so a crown out on the east side of
    the lot gets its label pushed further east into the margin rather than back
    over the beds.
    """
    ax_, ay = anchor
    hw, hh = half
    for grow in (1.0, 1.35, 1.75, 2.3, 3.0):
        for step in range(16):
            # alternate either side of the preferred bearing, widening out
            ang = math.radians(prefer + (step // 2 + 0.5) * 22.5 *
                               (1 if step % 2 == 0 else -1))
            cx = ax_ + math.cos(ang) * hw * 2.0 * grow
            cy = ay + math.sin(ang) * hh * 2.6 * grow
            if not (ext[0] + hw < cx < ext[1] - hw
                    and ext[2] + hh < cy < ext[3] - hh):
                continue
            if any(abs(cx - bx) < hw + bw and abs(cy - by) < hh + bh
                   for bx, by, bw, bh in taken):
                continue
            return cx, cy
    return ax_ + hw * 2.4, ay + hh * 2.4


def draw_tree_map(site, path, slug=None):
    """Every crown to scale, labelled, for somebody to carry out and falsify.

    The other three drawings in this module report the record. This one exists
    to be argued with. Crown radius is the least measured and most
    consequential number in a yard record — it is guessed from the ground, it
    is guessed for every tree on the same afternoon by the same pair of eyes,
    and it decides how much light every bed gets — and no amount of re-running
    the model settles it, because the model has only ever been run on the
    guess. The only thing that settles it is a person standing at a trunk,
    pacing to the drip line, and disagreeing with a number.

    So every figure the record holds is printed where it can be checked: the
    crown as a circle at the radius on file, the radius in feet and in paces
    with the stride stated, the height, and how the record says each of those
    was arrived at. The trees are ranked, because fourteen is more than anybody
    will measure and the ones that cannot change a decision should be skipped
    out loud rather than quietly. And the beds whose light category turns on
    the answer are flagged, so the crowns that reach them read as the reason to
    go outside rather than as more green circles.
    """
    g = Geom(site)
    W, C = g.W, g.C
    rows, meta = crown_field_check(site, slug)
    card = crown_card(site, slug)
    zones = site.get("zones") or {}
    decisive_keys, _ = decisive_zones(site, slug)

    # Extent from the drawn objects, so no crown is silently clipped: every
    # crown at its recorded radius, every check ring on a tree worth measuring,
    # and the lot itself even when no tree stands near a corner of it.
    xs, ys = [0.0, W], [0.0, C]
    for r in rows:
        t = r["tree"]
        reach = (t.get("crown_radius") or 0.0) * (
            max(CHECK_SCALES) if r["tier"] == "measure" else 1.0)
        xs += [t["crown_center_x"] - reach, t["crown_center_x"] + reach]
        ys += [t["crown_center_y"] - reach, t["crown_center_y"] + reach]
    pad = 0.05 * max(max(xs) - min(xs), max(ys) - min(ys))
    plan = [min(xs) - pad, max(xs) + pad, -(max(ys) + pad), -(min(ys) - pad)]
    # The field-check table is a column of the drawing rather than a caption,
    # so the extent has to carry it. Reserved before anything is drawn, for the
    # reason the plan's header is: a panel sized from its own content and drawn
    # into the data area lands on the map the first time the record grows.
    table_w = 0.52 * (plan[1] - plan[0])
    ext = g.extent("tree_map", [plan[0], plan[1] + table_w, plan[2], plan[3]])
    fig, ax = frame(ext, g.spec("tree_map", "figsize", [17.5, 13.0]))

    # The header is laid out and the y range grown to hold it before anything
    # is measured against the drawing, because growing the range afterwards
    # rescales an equal-aspect axis and every wrap width computed before the
    # change is then wrong in the direction that overflows.
    sub = g.spec("tree_map", "subtitle", _tree_subtitle(site, rows, meta, card))
    per_in = data_per_inch(fig, ax, ext)
    sub_lines = wrap(sub, fit_columns(
        [sub], (ext[1] - ext[0]) / per_in, size=9.0,
        hi=_wrap_ceiling([sub], (ext[1] - ext[0]) / per_in, 9.0)))
    sub_pitch = line_step(13, 9.0, per_in)
    head_h = 2.3 * sub_pitch + sub_pitch * len(sub_lines)
    ax.set_ylim(ext[2], ext[3] + head_h)
    per_in = data_per_inch(fig, ax, ext, ylim=(ext[2], ext[3] + head_h))

    draw_context_shapes(ax, g.spec("tree_map", "context"))

    # ---- the ground: lot, house, zones, fences
    ax.add_patch(Polygon(g.outline(), closed=True, fc="#fbf8f1", ec=INK, lw=2.4,
                         zorder=3))
    # The measured wall footprint where the yard has one, which is the line a
    # person orients off outside: a rectangle stretched over an L-shaped house
    # puts every bed on the wrong side of a wall that is not there.
    ho = site.get("obstructions", {}).get("house")
    walls = (site.get("obstructions", {}).get("house_walls") or {}).get("polygon")
    if walls:
        ax.add_patch(Polygon([(p[0], -p[1]) for p in walls], closed=True,
                             fc=HOUSE, ec=HOUSE_EDGE, lw=1.8, zorder=5))
        wx = sum(p[0] for p in walls) / len(walls)
        wy = -sum(p[1] for p in walls) / len(walls)
        ax.text(wx, wy, "HOUSE", fontsize=15, fontweight="bold",
                color="#7c7264", ha="center", va="center", zorder=13)
    elif ho:
        y0, y1 = ho["wall_y"]
        ax.add_patch(Rectangle((ho["wall_x"], -y1), float(ho.get("width") or 0),
                               y1 - y0, fc=HOUSE, ec=HOUSE_EDGE, lw=1.8,
                               zorder=5))

    zone_labels = []
    for key, z in zones.items():
        if not (z.get("x") and z.get("y")):
            continue
        poly = g.zone_polygon(z)
        bed = z.get("style") == "bed"
        style = ZONE_STYLE.get(z.get("style", ""), ZONE_STYLE["default"])
        hot = key in decisive_keys
        ax.add_patch(Polygon(poly, closed=True, fc=style[0] if bed else "none",
                             ec=DECISIVE if hot else (style[1] if bed else "#cfcabd"),
                             lw=2.6 if hot else (1.2 if bed else 0.9),
                             ls="-" if bed or hot else (0, (5, 4)),
                             alpha=0.95, zorder=6))
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        lab = (z.get("label_short") or key).upper()
        if hot:
            lab += "  ▲"
        size = 9.6 if bed or hot else 8.4
        ax.text(cx, cy, lab, fontsize=size,
                fontweight="bold" if bed or hot else "normal",
                color=DECISIVE if hot else (style[1] if bed else "#a9a49a"),
                ha="center", va="center", zorder=13,
                path_effects=halo("white", 3.4))
        # A tree label that lands on a bed's name costs the reader the one
        # thing this map is for: knowing which crown sits over which bed.
        zone_labels.append((cx, cy, text_width_in(lab, size) * per_in / 2.0,
                            line_step(0, size, per_in, k=1.4) / 2.0))

    for f in site.get("obstructions", {}).get("fences", []) or []:
        pts = [(p[0], -p[1]) for p in f["points"]]
        col = HOUSE_EDGE if "house" in str(f.get("id", "")).lower() else FENCE
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=3.4,
                solid_capstyle="butt", alpha=0.9, zorder=7)

    # ---- crowns, biggest influence last so it is drawn on top
    for r in sorted(rows, key=lambda q: q["worst"]):
        t = r["tree"]
        rr = t.get("crown_radius") or 0.0
        if not rr:
            continue
        fill, edge, _, _ = TIER_STYLE[r["tier"]]
        cx, cy = t["crown_center_x"], -t["crown_center_y"]
        # Deciduous dashed, evergreen solid and hatched. What a crown does in
        # December is the whole of its winter cost and none of it is visible
        # from the crown's size, so the distinction cannot be left to a legend
        # entry nobody reads next to a circle that looks like every other.
        decid = t.get("deciduous", True)
        ax.add_patch(Circle((cx, cy), rr, fc=fill, ec=edge, lw=1.4,
                            ls=(0, (7, 5)) if decid else "-",
                            hatch=None if decid else "xxx",
                            alpha=0.34 if r["tier"] != "skip" else 0.5,
                            zorder=8))
        if r["tier"] == "measure":
            # The falsifiable claim. If the canopy reaches this ring, the
            # record is wrong by the margin that flips a bed's light category.
            ax.add_patch(Circle((cx, cy), rr * max(CHECK_SCALES), fc="none",
                                ec=DECISIVE, lw=1.1, ls=(0, (2, 4)), alpha=0.8,
                                zorder=9))

    # The trunk is where a person stands, so it is a hard mark and not the
    # centre of a soft circle. Sized in points rather than inches of ground,
    # because a mark measured in ground units is a legible dot on a 40 ft yard
    # and invisible on a 250 ft one. Filled where the height on file is a real
    # measurement, hollow where it is somebody's eye.
    dot = 4.2 / 72.0 * per_in
    for r in rows:
        t = r["tree"]
        hard = r["height_src"] in siteschema.HARD_SOURCES
        ax.add_patch(Circle((t["trunk_x"], -t["trunk_y"]),
                            dot * (1.35 if r["tier"] == "measure" else 1.0),
                            fc="#6b4f34" if hard else "white",
                            ec="#6b4f34", lw=2.0 if hard else 1.6, zorder=15))

    # ---- north, scale, and the panels. Placed before the labels so their
    # footprints join the collision set: a scale bar with a label box printed
    # over it is a drawing with no scale, and it does not look like one.
    na = (plan[0] + 0.08 * (plan[1] - plan[0]),
          plan[2] + 0.86 * (plan[3] - plan[2]))
    nr = 0.055 * C
    north_arrows(ax, na[0], na[1], site, R=nr)
    sb = (plan[0] + 0.03 * (plan[1] - plan[0]),
          plan[2] + 0.05 * (plan[3] - plan[2]))
    scalebar(ax, sb[0], sb[1], 20)

    tb_x = ext[1] - table_w * 0.97
    tb_w = table_w * 0.95
    gap = 0.018 * (plan[3] - plan[2])
    y = _tree_table(ax, tb_x, plan[3] - gap, tb_w, rows, per_in)
    y = _tree_legend(ax, tb_x, y - gap, tb_w, rows, per_in)
    feats = site.get("features") or {}
    _tree_honesty(ax, tb_x, y - gap, tb_w, rows, card, meta, per_in,
                  engulfed_crowns(rows, feats.get("canopy_stacking", "single"),
                                  sunmodel.canopy_groups(site)))

    # ---- labels, led out where they would collide
    taken = list(zone_labels) + [
        (na[0], na[1], nr * 1.5, nr * 1.9),
        (sb[0] + 120, sb[1], 132, 60),
    ] + [(r["tree"]["trunk_x"], -r["tree"]["trunk_y"], 18, 18) for r in rows]
    for r in rows:
        t = r["tree"]
        rr = t.get("crown_radius") or 0.0
        fill, edge, ink, weight = TIER_STYLE[r["tier"]]
        lines = [f"{r['id']}  {r['species']}"]
        if r["tier"] == "skip":
            lines.append(f"{r['height_ft']:.0f} ft · R {r['radius_ft']:.1f} ft"
                         f" · reaches nothing")
        else:
            lines.append(f"{r['height_ft']:.0f} ft tall · crown R "
                         f"{r['radius_ft']:.1f} ft")
            lines.append(f"{r['paces']:.1f} paces to the drip line")
            lines.append(f"bare from {leaf_date(t.get('leaf_off'))}"
                         if t.get("deciduous", True) else "evergreen all winter")
            if r["overhangs"]:
                lines.append("stands over " + ", ".join(r["overhangs"]))
        size = 8.2 if r["tier"] == "measure" else 7.4
        hw, hh, pitch = _label_box(lines, size, per_in)
        tx, ty = t["trunk_x"], -t["trunk_y"]
        # Push outward from the middle of the lot, so labels gather in the
        # margins instead of over the ground the map is about.
        prefer = math.degrees(math.atan2(ty + C / 2.0, tx - W / 2.0))
        anchor = (tx + math.cos(math.radians(prefer)) * rr * 0.9,
                  ty + math.sin(math.radians(prefer)) * rr * 0.9)
        cx, cy = _place_label(anchor, (hw, hh), taken, plan, prefer)
        taken.append((cx, cy, hw, hh))
        ax.plot([tx, cx], [ty, cy], color=edge, lw=0.8, ls=(0, (4, 3)),
                alpha=0.85, zorder=14)
        ax.add_patch(Rectangle((cx - hw, cy - hh), hw * 2, hh * 2, fc="white",
                               ec=edge if r["tier"] != "skip" else "#cfcac1",
                               lw=1.0, alpha=0.94, zorder=16))
        for i, ln in enumerate(lines):
            ax.text(cx - hw + 0.3 * pitch, cy + hh - pitch * (i + 0.72), ln,
                    fontsize=size if i else size + 0.6,
                    fontweight=weight if i else "bold",
                    color=ink, zorder=17)

    top = ext[3] + head_h
    ax.text(ext[0] + 4, top - 1.1 * sub_pitch,
            g.spec("tree_map", "title",
                   f"{site.get('label', site.get('yard', ''))} — TREE MAP, "
                   "CROWNS TO SCALE"),
            fontsize=17, fontweight="bold", color=INK, zorder=18,
            path_effects=halo("white", 4))
    for i, line in enumerate(sub_lines):
        ax.text(ext[0] + 4, top - 2.3 * sub_pitch - i * sub_pitch, line,
                fontsize=9, color=MUTED, zorder=18,
                path_effects=halo("white", 3))

    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


def _tree_subtitle(site, rows, meta, card):
    n = sum(1 for r in rows if r["tier"] == "measure")
    skip = sum(1 for r in rows if r["tier"] == "skip")
    beds = ", ".join(meta["zones"]) or "no bed"
    who = f"Settles {card['id']}. " if card else ""
    return (f"{who}Carry this out and disagree with it. Every circle is the "
            f"crown radius the record holds, drawn to scale about the trunk; "
            f"pace from the trunk to the drip line and see whether it lands on "
            f"the line. {n} of {len(rows)} trees can move the light in "
            f"{beds} by more than {meta['band']:.1f} h a day on their own and "
            f"are worth the walk; {skip} cannot reach a decisive bed under any "
            f"plausible error and are marked to skip. Paces assume a "
            f"{PACE_FT:.1f} ft stride — check yours over a known 25 ft first, "
            f"because every figure in the PACES column is wrong by whatever "
            f"your stride is wrong by.")


def _panel(ax, x, y, w, entries, per_in, title, size=7.4, heading=9.0,
           key_size=None):
    """A boxed panel of key-and-wrapped-prose rows. Returns its bottom edge.

    The prose is wrapped to the column it is actually drawn in, measured off
    the glyphs rather than guessed at a characters-per-inch rate, for the
    reason the plan's verify list is: a guess is wrong by enough to run the
    longest and most important line off the edge of the page, and the failure
    is silent.

    Each entry is `(key, text, colour, bold)`; a key of None runs the text the
    full width, and a `draw` callable in place of the key gets handed the row's
    baseline so a legend can put a real glyph where the word for it would go.
    """
    key_size = key_size or size
    pitch = line_step(11.5, size, per_in)
    lead = max(9.0, 0.95 * heading / 72.0 * per_in)
    keys = [e[0] for e in entries if isinstance(e[0], str)]
    key_w = (max((text_width_in(k, key_size) for k in keys), default=0.0)
             * per_in)
    # A drawn key needs a column reserved for it the same way a written one
    # does. Measuring only the strings left glyph keys a zero-width column and
    # painted every swatch underneath the sentence explaining it.
    if any(callable(e[0]) for e in entries):
        key_w = max(key_w, 2.4 * pitch)
    body_x = x + 8 + (key_w + 0.45 * pitch if key_w else 0.0)
    body_in = (x + w - 8 - body_x) / per_in
    texts = [e[1] for e in entries]
    cols = fit_columns(texts, body_in, size=size, lo=24,
                       hi=_wrap_ceiling(texts, body_in, size))

    laid = []
    for key, text, col, bold in entries:
        for j, chunk in enumerate(wrap(text, cols)):
            laid.append((key if j == 0 else None, chunk, col, bold))
    h = lead + pitch * (len(laid) + 0.6)
    ax.add_patch(Rectangle((x, y), w, -h, fc="white", ec=INK, lw=1.2,
                           zorder=19))
    ax.text(x + 8, y - lead, title, fontsize=heading, fontweight="bold",
            color=INK, zorder=20)
    for i, (key, chunk, col, bold) in enumerate(laid):
        yy = y - lead - pitch * (i + 1)
        if callable(key):
            key(ax, x + 8, yy, key_w, pitch)
        elif key:
            ax.text(x + 8, yy, key, fontsize=key_size, color=MUTED,
                    fontweight="bold", zorder=20)
        ax.text(body_x if (key_w or key) else x + 8, yy, chunk, fontsize=size,
                color=col, fontweight="bold" if bold else "normal", zorder=20)
    return y - h


def _tree_table(ax, x, y, w, rows, per_in):
    """The field-check table: what the record claims, in units for a yard.

    Printed in full even for the trees marked skip, because "you do not need to
    measure this one" is only believable next to the number it is about. A
    ranked list with the bottom of it left off reads as an oversight.
    """
    size = 7.4
    pitch = line_step(11.5, size, per_in)
    lead = max(9.0, 0.95 * 9.0 / 72.0 * per_in)
    h = lead + pitch * (len(rows) + 2.6)
    ax.add_patch(Rectangle((x, y), w, -h, fc="white", ec=INK, lw=1.2, zorder=19))
    ax.text(x + 6, y - lead, "FIELD CHECK — WORST FIRST", fontsize=9.0,
            fontweight="bold", color=INK, zorder=20)

    cells = [(r["id"], r["species"], f"{r['height_ft']:.0f}",
              f"{r['radius_ft']:.1f}", f"{r['paces']:.1f}",
              ", ".join(r["governs"]) or "—",
              f"{r['worst']:.2f}") for r in rows]
    heads = ("TREE", "SPECIES", "HT ft", "R ft", "PACES", "GOVERNS", "h/day")
    right = {2, 3, 4, 6}          # the numeric columns

    # Columns measured off the widest cell that will actually land in each, and
    # the type stepped down until the whole row fits the panel. A table sized
    # from a character count instead runs its last column off the right edge
    # the first time a species name or a bed list grows, and a figure that has
    # slid under the panel border is worse than a figure in smaller type: it
    # reads as though the record does not hold it.
    gap = 0.55 * pitch
    while size > 5.2:
        widths = [max([text_width_in(heads[i], size - 0.6)]
                      + [text_width_in(c[i], size) for c in cells]) * per_in
                  for i in range(len(heads))]
        if sum(widths) + gap * (len(widths) - 1) <= w - 16:
            break
        size -= 0.2
    slack = max(0.0, (w - 16) - sum(widths) - gap * (len(widths) - 1)) \
        / max(len(widths) - 1, 1)
    xs, cur = [], x + 8
    for wd in widths:
        xs.append((cur, cur + wd))
        cur += wd + gap + slack

    def cell_x(i, txt, sz):
        lo, hi = xs[i]
        return hi - text_width_in(txt, sz) * per_in if i in right else lo

    for i, head in enumerate(heads):
        ax.text(cell_x(i, head, size - 0.6), y - lead - pitch * 1.15, head,
                fontsize=size - 0.6, color=MUTED, fontweight="bold", zorder=20)
    ax.plot([x + 8, x + w - 8], [y - lead - pitch * 1.42] * 2, color="#d6d2c8",
            lw=0.8, zorder=20)
    for j, (r, cell) in enumerate(zip(rows, cells)):
        _, _, ink, weight = TIER_STYLE[r["tier"]]
        yy = y - lead - pitch * (j + 2.3)
        if r["tier"] == "measure":
            ax.add_patch(Rectangle((x + 4, yy - pitch * 0.3), w - 8,
                                   pitch * 0.94, fc="#f2f6ee", ec="none",
                                   zorder=19))
        for i, txt in enumerate(cell):
            ax.text(cell_x(i, txt, size), yy, txt, fontsize=size, color=ink,
                    fontweight=weight if i == 0 else "normal", zorder=20)
    return y - h


def _swatch(kind):
    """A legend key drawn as the mark it explains, not as a name for it.

    "Filled circle" and "pale circle" are only distinguishable in a legend if
    the reader already knows which is which, which is the one thing a legend
    exists to tell them.
    """
    def draw(ax, x, y, w, pitch):
        r = pitch * 0.30
        cx, cy = x + w * 0.5, y + pitch * 0.22
        if kind in TIER_STYLE:
            fill, edge, _, _ = TIER_STYLE[kind]
            ax.add_patch(Circle((cx, cy), r, fc=fill, ec=edge, lw=1.2,
                                alpha=0.5, ls=(0, (5, 4)), zorder=20))
            if kind == "measure":
                ax.add_patch(Circle((cx, cy), r * 1.55, fc="none", ec=DECISIVE,
                                    lw=1.0, ls=(0, (2, 3)), zorder=20))
        elif kind == "evergreen":
            ax.add_patch(Circle((cx, cy), r, fc=TIER_STYLE["maybe"][0],
                                ec=TIER_STYLE["maybe"][1], lw=1.2, hatch="xxx",
                                alpha=0.5, zorder=20))
        elif kind in ("measured_trunk", "eye_trunk"):
            ax.add_patch(Circle((cx, cy), r * 0.42,
                                fc="#6b4f34" if kind == "measured_trunk" else "white",
                                ec="#6b4f34", lw=1.6, zorder=20))
        elif kind == "decisive":
            ax.add_patch(Rectangle((cx - r * 1.5, cy - r * 0.8), r * 3, r * 1.6,
                                   fc=ZONE_STYLE["bed"][0], ec=DECISIVE, lw=2.0,
                                   zorder=20))
            ax.text(cx + r * 2.2, cy, "▲", fontsize=7.0, color=DECISIVE,
                    ha="center", va="center", zorder=20)
    return draw


def _tree_legend(ax, x, y, w, rows, per_in):
    counts = {k: sum(1 for r in rows if r["tier"] == k) for k in TIER_STYLE}
    decid = [r for r in rows if r["tree"].get("deciduous", True)]
    off = sorted({leaf_date(r["tree"].get("leaf_off")) for r in decid})
    lines = [
        (_swatch("measure"), f"{counts['measure']} trees worth the walk. The "
         f"solid circle is the radius on file; the red ring is "
         f"{max(CHECK_SCALES):.1f}x of it. Pace from the trunk: if the canopy "
         f"edge falls inside the solid circle the record is right, if it "
         f"reaches the red ring the record is wrong by enough to change what "
         f"can be planted.", INK, False),
        (_swatch("maybe"), f"{counts['maybe']} trees that shift a decisive bed "
         f"a little. Measure them if there is time left over.", MUTED, False),
        (_swatch("skip"), f"{counts['skip']} trees that cannot reach a decisive "
         f"bed at any radius in range. Do not spend the afternoon on these.",
         MUTED, False),
        (_swatch("maybe"), f"Dashed outline: deciduous, so a summer problem "
         f"only. All {len(decid)} of {len(rows)} trees here are deciduous, "
         f"bare from {', '.join(off)}.", MUTED, False),
        (_swatch("evergreen"), "Solid hatched outline: evergreen, and shades in "
         "December too. None on this lot.", MUTED, False),
        (_swatch("measured_trunk"), "Solid trunk dot: the height on file is a "
         "measurement.", MUTED, False),
        (_swatch("eye_trunk"), "Hollow trunk dot: the height on file is "
         "somebody's eye.", MUTED, False),
        (_swatch("decisive"), "The beds whose light category turns on the "
         "answer. Every other bed holds whatever the crowns turn out to be.",
         DECISIVE, False),
    ]
    return _panel(ax, x, y, w, lines, per_in, "HOW TO READ IT")


def _tree_honesty(ax, x, y, w, rows, card, meta, per_in, engulfed=()):
    """What the record says about itself, counted rather than characterised.

    The counts are taken live from `provenance`, so this panel cannot drift
    into flattering the file the way a hand-written note about how well
    measured a yard is always eventually does.
    """
    def tally(field):
        out = {}
        for r in rows:
            out[r[field]] = out.get(r[field], 0) + 1
        return out

    def stamps(field):
        return "; ".join(f"{k} on {v}" for k, v in sorted(tally(field).items()))

    hard = sorted(r["id"] for r in rows
                  if r["height_src"] in siteschema.HARD_SOURCES)
    lines = [
        ("HEIGHTS", f"{len(rows) - len(hard)} of {len(rows)} are estimates by "
         f"eye from the ground, which are commonly out by 20 percent. "
         f"Provenance says {stamps('height_src')}. "
         + (f"{', '.join(hard)} "
            + ("is the one exception." if len(hard) == 1 else "are the exceptions.")
            if hard else "Nothing here is instrument-measured."), INK, False),
        ("CROWNS", f"Provenance says {stamps('radius_src')}.", INK, False),
    ]
    if card:
        lines.append(
            ("", f"{card['id']} is open and disputes that stamp: it holds that "
             f"the crowns were estimated by eye, by one person on one "
             f"afternoon, so if they are wrong they are wrong together and in "
             f"one direction. Nothing has re-measured them since. This drawing "
             f"prints the record, which is the thing to be disagreed with — it "
             f"is not evidence that the record is right.", DECISIVE, False))
    if engulfed:
        by_id = {r["id"]: r["tree"] for r in rows}
        lines.append(
            ("OVERLAP", "; ".join(
                f"{a} sits wholly inside {b}, sharing "
                f"{_height_overlap(by_id[a], by_id[b]) / 12.0:.0f} ft of height"
                for a, b in engulfed)
             + ". features.canopy_stacking is 'multiply' and neither is "
               "declared in features.canopy_groups, so the model attenuates the "
               "shared volume twice. Neither crown can be told from the other "
               "standing under them either. Do not try to pace the inner one.",
             DECISIVE, False))
    lines.append(
        ("h/day", f"The last table column: hours a day of crown shade this one "
         f"tree adds or removes as its own radius swings "
         f"{min(CHECK_SCALES):.1f}x to {max(CHECK_SCALES):.1f}x, on the worst "
         f"of {', '.join(meta['zones']) or 'no bed'} ({meta['source']}). "
         f"    Crown shade only — no house, no fence, no leaf "
         f"transmissivity, and nothing cast below {CHECK_ALT_FLOOR:.0f} "
         f"degrees of altitude — so shade the wall already had is counted "
         f"twice and the columns do not sum to the swing on the card. It ranks "
         f"the trees against each other. It is not a light level; "
         f"sun-hours.json is.", MUTED, False))
    return _panel(ax, x, y, w, lines, per_in, "WHAT THE RECORD ACTUALLY KNOWS")


def run(slug, outdir=None, only=None):
    site = yards.load_site(slug)
    outdir = outdir or os.path.join(yards.yard_dir(slug), "maps")
    os.makedirs(outdir, exist_ok=True)
    drawings = {
        "plan": ("site-plan.png", lambda p: draw_plan(site, p)),
        "context": ("site-context.png", lambda p: draw_context(site, p)),
        "elevation": ("elevation.png", lambda p: draw_elevation(site, p)),
        "section": ("section.png", lambda p: draw_section(site, p)),
        "tree-map": ("tree-map.png", lambda p: draw_tree_map(site, p, slug)),
    }
    for name, (fname, fn) in drawings.items():
        if only and name not in only:
            continue
        fn(os.path.join(outdir, fname))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--only", default=None,
                    help="comma-separated: plan, context, elevation, section, "
                         "tree-map. Default is all of them.")
    args = ap.parse_args()
    run(args.slug, args.outdir,
        only=[s.strip() for s in args.only.split(",")] if args.only else None)


if __name__ == "__main__":
    main()
