#!/usr/bin/env python3
"""Measuring things from a photograph.

    # one known dimension in frame, measure others parallel to it
    python3 -m lib.photomeasure scale house.jpg \\
        --ref 412,880 412,1240 --ref-length 36 --ref-name "basement window" \\
        --measure 980,300 980,1240 --label "eave height" \\
        --measure 1180,420 1180,560 --label "awning drop"

    # a known rectangle in frame rectifies its whole plane at once
    python3 -m lib.photomeasure rectify back.jpg \\
        --quad 300,700 1500,690 1520,1580 280,1600 \\
        --size 192,96 --name "garage door" \\
        --measure 900,240 900,1560 --label "eave above door head"

Two modes, and the difference matters
-------------------------------------
**Scale reference.** One object of known size, and everything measured must lie
in the same plane and at the same distance from the camera. Quick, and good to
a few percent when that holds. It says nothing reliable about anything nearer or
further than the reference, and it cannot correct perspective: a wall
photographed from below has a foreshortened top, and this mode will not know.

**Four-point homography.** Four corners of a known rectangle define the whole
plane they sit in. That plane is then rectified, and any two points on it can be
measured, in any direction, with perspective removed. One photograph of a house
wall with a known door or window in it yields eave height, awning projection and
window sizes together. This is the mode to reach for.

Both report an error bar and neither returns a bare number. The bar comes from
propagating how precisely a point can be clicked, by Monte Carlo, plus the
residual of the rectangle fit itself. It does not cover lens distortion, which
on a phone's wide lens bends straight lines near the frame edge; keep what is
being measured away from the corners of the shot.

What this cannot do
-------------------
Tree crowns. A crown has no sharp edge, no known reference at its distance, and
its far side is invisible from the ground. Use lidar, and where the survey is
too old to help, say so rather than guessing from a photo.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

DEFAULT_CLICK_PX = 4.0          # how precisely a corner can be picked, in pixels
TRIALS = 400


# --------------------------------------------------------------- homography

def homography(src, dst):
    """H mapping src pixels to dst plane coordinates, by the direct linear
    transform. Four correspondences is the minimum; more are least-squared."""
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    n = len(src)
    A = np.zeros((2 * n, 9))
    for i in range(n):
        x, y = src[i]
        u, v = dst[i]
        A[2 * i] = [-x, -y, -1, 0, 0, 0, u * x, u * y, u]
        A[2 * i + 1] = [0, 0, 0, -x, -y, -1, v * x, v * y, v]
    _, _, vt = np.linalg.svd(A)
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def apply_h(H, pts):
    pts = np.atleast_2d(np.asarray(pts, float))
    ones = np.ones((len(pts), 1))
    p = np.hstack([pts, ones]) @ H.T
    return p[:, :2] / p[:, 2:3]


def fit_residual(H, src, dst):
    """How well the rectangle's own corners land where they should, in plane units."""
    got = apply_h(H, src)
    return float(np.sqrt(((got - np.asarray(dst, float)) ** 2).sum(axis=1)).mean())


# ------------------------------------------------------------------- errors

def monte_carlo(fn, points, click_px, trials=TRIALS, rng=None):
    """Spread of a measurement under realistic clicking error.

    Every point that went into the answer is jittered by a Gaussian the size of
    a click, the answer recomputed, and the spread reported. It is the honest
    way to turn "I clicked roughly there" into a number with a bar on it.
    """
    rng = rng or np.random.default_rng(20260827)
    out = []
    for _ in range(trials):
        jittered = [np.asarray(p, float) + rng.normal(0, click_px, size=2)
                    for p in points]
        try:
            v = fn(jittered)
        except Exception:
            continue
        if v is not None and np.isfinite(v):
            out.append(v)
    if not out:
        return None, None
    a = np.array(out)
    return float(a.mean()), float(a.std())


def band(value, sigma, unit="in"):
    if sigma is None:
        return f"{value:.1f} {unit}"
    return f"{value:.1f} ± {2 * sigma:.1f} {unit}"


# ------------------------------------------------------------------- modes

def measure_by_scale(ref_px, ref_length, targets, click_px=DEFAULT_CLICK_PX):
    """One known dimension sets the scale for everything in its plane."""
    def length(pts):
        return math.dist(pts[0], pts[1])

    ref_len_px = length(ref_px)
    if ref_len_px < 20:
        raise ValueError("the reference is under 20 px long; the scale it sets "
                         "would be worse than a tape measure")
    out = []
    for label, (p1, p2) in targets:
        def f(pts, _p1=p1, _p2=p2):
            r = math.dist(pts[0], pts[1])
            t = math.dist(pts[2], pts[3])
            return t * ref_length / r if r > 1 else None
        value = length((p1, p2)) * ref_length / ref_len_px
        mean, sigma = monte_carlo(f, [ref_px[0], ref_px[1], p1, p2], click_px)
        out.append({
            "label": label,
            "inches": round(value, 1),
            "sigma_in": round(sigma, 2) if sigma else None,
            "reported": band(value, sigma),
            "pixels": round(length((p1, p2)), 1),
        })
    return {
        "mode": "scale reference",
        "reference_length_in": ref_length,
        "reference_pixels": round(ref_len_px, 1),
        "inches_per_pixel": round(ref_length / ref_len_px, 4),
        "click_px": click_px,
        "measurements": out,
        "caveat": ("valid only for things lying in the reference's plane at the "
                   "reference's distance from the camera. Perspective is not "
                   "corrected, so a dimension high on a wall shot from below "
                   "reads short"),
    }


def measure_by_homography(quad_px, size, targets, click_px=DEFAULT_CLICK_PX,
                          name="reference rectangle"):
    """Four corners of a known rectangle rectify the plane they lie in.

    Corners are given in order around the rectangle. Their real-world size is
    width by height, in inches.
    """
    w, h = size
    dst = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    H = homography(quad_px, dst)
    resid = fit_residual(H, quad_px, dst)

    out = []
    for label, (p1, p2) in targets:
        def f(pts):
            Hj = homography(pts[:4], dst)
            a, b = apply_h(Hj, [pts[4], pts[5]])
            return math.dist(a, b)
        a, b = apply_h(H, [p1, p2])
        value = math.dist(a, b)
        mean, sigma = monte_carlo(f, list(quad_px) + [p1, p2], click_px)
        # the rectangle's own fit error adds on top of clicking error
        sigma = math.hypot(sigma or 0.0, resid)
        out.append({
            "label": label,
            "inches": round(value, 1),
            "sigma_in": round(sigma, 2),
            "reported": band(value, sigma),
            "plane_from": [round(v, 1) for v in a],
            "plane_to": [round(v, 1) for v in b],
        })
    return {
        "mode": "four-point homography",
        "reference": name,
        "reference_size_in": [w, h],
        "fit_residual_in": round(resid, 2),
        "click_px": click_px,
        "measurements": out,
        "caveat": ("valid for anything lying in the rectangle's plane. A point "
                   "standing off that plane, such as the front edge of an eave "
                   "overhanging the wall, is projected onto it and reads further "
                   "away than it is. Measure the overhang from a second photo "
                   "taken along the wall"),
    }


# ------------------------------------------------------------------- output

def annotate(image_path, out_path, quad=None, ref=None, targets=None, results=None):
    """Draw what was measured back onto the photo, so it can be checked by eye."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    im = Image.open(image_path).convert("RGB")
    d = ImageDraw.Draw(im)
    scale = max(im.size) / 1600.0
    lw = max(int(3 * scale), 2)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                  int(26 * scale))
    except Exception:
        font = ImageFont.load_default()

    if quad:
        d.polygon([tuple(p) for p in quad], outline=(60, 190, 255), width=lw)
        for p in quad:
            d.ellipse([p[0] - 6 * scale, p[1] - 6 * scale,
                       p[0] + 6 * scale, p[1] + 6 * scale], fill=(60, 190, 255))
    if ref:
        d.line([tuple(ref[0]), tuple(ref[1])], fill=(60, 190, 255), width=lw + 1)

    lookup = {r["label"]: r for r in (results or {}).get("measurements", [])}
    for label, (p1, p2) in (targets or []):
        d.line([tuple(p1), tuple(p2)], fill=(255, 90, 60), width=lw + 1)
        for p in (p1, p2):
            d.line([p[0] - 12 * scale, p[1], p[0] + 12 * scale, p[1]],
                   fill=(255, 90, 60), width=lw)
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        txt = f"{label}: {lookup.get(label, {}).get('reported', '')}"
        d.rectangle([mid[0] + 8 * scale, mid[1] - 18 * scale,
                     mid[0] + 8 * scale + len(txt) * 13 * scale,
                     mid[1] + 16 * scale], fill=(20, 22, 26))
        d.text((mid[0] + 14 * scale, mid[1] - 14 * scale), txt,
               fill=(255, 220, 120), font=font)
    im.save(out_path)
    return out_path


def print_report(res):
    print(f"\n{res['mode']}")
    if res["mode"].startswith("four"):
        print(f"  reference: {res['reference']}, "
              f"{res['reference_size_in'][0]:g} x {res['reference_size_in'][1]:g} in")
        print(f"  rectangle fit residual: {res['fit_residual_in']:.2f} in")
    else:
        print(f"  reference: {res['reference_length_in']:g} in over "
              f"{res['reference_pixels']:.0f} px "
              f"= {res['inches_per_pixel']:.4f} in/px")
    print(f"  assumed click precision: {res['click_px']:.0f} px\n")
    print(f"  {'measurement':32s} {'inches':>10s} {'feet':>12s}")
    for m in res["measurements"]:
        ft = m["inches"] / 12.0
        print(f"  {m['label'][:32]:32s} {m['reported']:>10s} "
              f"{ft:9.2f} ft")
    print(f"\n  {res['caveat']}")


# ------------------------------------------------------------------- parsing

def selftest():
    """Project a known wall through a real perspective camera and measure it back.

    Also demonstrates, rather than merely asserting, why the scale-reference mode
    is the weaker of the two: given the same photograph it overstates an eave by
    tens of percent, because the eave is nowhere near the reference's height and
    nothing corrects for that.
    """
    f, cx, cy = 1200.0, 960.0, 720.0
    tilt = math.radians(12)
    C = np.array([0.0, -140.0, 60.0])
    R = np.array([[1, 0, 0],
                  [0, math.cos(tilt), -math.sin(tilt)],
                  [0, math.sin(tilt), math.cos(tilt)]])

    def project(X, Z):
        p = R @ (np.array([X, 0.0, Z]) - C)
        return (f * p[0] / p[1] + cx, -f * p[2] / p[1] + cy)

    dw, dh = 192.0, 96.0
    quad = [project(40, dh), project(40 + dw, dh), project(40 + dw, 0),
            project(40, 0)]
    truth = {"eave height": ((150, 0.0), (150, 240.0)),
             "window head to sill": ((300, 96.0), (300, 148.0)),
             "door to wall corner": ((40, 20.0), (0, 20.0))}
    targets = [(k, (project(*a), project(*b))) for k, (a, b) in truth.items()]
    expect = {k: math.dist(a, b) for k, (a, b) in truth.items()}

    res = measure_by_homography(quad, [dw, dh], targets, name="garage door")
    print("four-point homography against known truth:")
    ok = True
    for m in res["measurements"]:
        t = expect[m["label"]]
        good = abs(m["inches"] - t) <= 2 * m["sigma_in"] + 0.5
        ok &= good
        print(f"  {m['label']:24s} true {t:7.1f}  got {m['reported']:>16s}  "
              f"{'ok' if good else 'OUTSIDE THE STATED BAR'}")

    res2 = measure_by_scale((quad[3], quad[2]), dw, targets)
    print("\nsame photo, scale reference on the door's bottom edge:")
    for m in res2["measurements"]:
        t = expect[m["label"]]
        print(f"  {m['label']:24s} true {t:7.1f}  got {m['inches']:7.1f}  "
              f"off by {m['inches'] - t:+.0f} in")
    print("\nSELFTEST " + ("PASS" if ok else "FAIL"))
    return ok


def _pt(text):
    x, y = text.split(",")
    return (float(x), float(y))


def _pairs(values):
    if len(values) % 2:
        raise ValueError("points must come in pairs")
    return [(values[i], values[i + 1]) for i in range(0, len(values), 2)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["scale", "rectify", "selftest"])
    ap.add_argument("image", nargs="?")
    ap.add_argument("--ref", nargs=2, type=_pt,
                    help="two pixels spanning the known dimension")
    ap.add_argument("--ref-length", type=float, help="its real length, inches")
    ap.add_argument("--ref-name", default="reference")
    ap.add_argument("--quad", nargs=4, type=_pt,
                    help="four pixels, in order around the known rectangle")
    ap.add_argument("--size", type=lambda s: [float(v) for v in s.split(",")],
                    help="the rectangle's real width,height in inches")
    ap.add_argument("--measure", nargs=2, type=_pt, action="append", default=[],
                    help="two pixels to measure between; repeatable")
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("--click-px", type=float, default=DEFAULT_CLICK_PX)
    ap.add_argument("--annotate", default=None, help="write a marked-up copy here")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if args.mode == "selftest":
        raise SystemExit(0 if selftest() else 1)
    if not args.image or not os.path.exists(args.image):
        raise SystemExit(f"no such image: {args.image}")
    if not args.measure:
        raise SystemExit("nothing to measure; pass at least one --measure")

    labels = list(args.label) + [f"measurement {i + 1}"
                                 for i in range(len(args.label),
                                                len(args.measure))]
    targets = list(zip(labels, args.measure))

    if args.mode == "scale":
        if not args.ref or not args.ref_length:
            raise SystemExit("scale mode needs --ref and --ref-length")
        res = measure_by_scale(args.ref, args.ref_length, targets, args.click_px)
        res["reference_name"] = args.ref_name
    else:
        if not args.quad or not args.size:
            raise SystemExit("rectify mode needs --quad and --size")
        res = measure_by_homography(args.quad, args.size, targets,
                                    args.click_px, args.ref_name)

    res["image"] = os.path.abspath(args.image)
    print_report(res)

    if args.annotate:
        p = annotate(args.image, args.annotate, quad=args.quad, ref=args.ref,
                     targets=targets, results=res)
        print(f"\n  annotated copy: {p}" if p
              else "\n  (PIL not available, no annotated copy)")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=2)
            fh.write("\n")
        print(f"  json: {args.json}")


if __name__ == "__main__":
    main()
