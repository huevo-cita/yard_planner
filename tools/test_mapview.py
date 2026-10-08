#!/usr/bin/env python3
"""The bed map in a real browser, at phone width and at desktop width.

    python3 tools/test_mapview.py <slug> [--shots DIR]

The test serves the map from memory. A swap in the test does not write the
yard's scheme.json. It fails on:

- a console error, a page error, or a failed request
- two labels whose boxes overlap, or a label outside the drawing
- two leader lines that cross
- a plant with no label, or a label with a count in it
- one plant in one niche at two sizes, or a canopy plant that is shrunk
- a tap target smaller than the practice minimum
- a schedule count that does not match the circles
- a tap that does not open the choice list, or a swap that does not redraw
- a swap option taller than the plant behind it that is not last or not labelled
- a choice list with no card for the plant that is there now
- a Ctrl+Z that does not put back the plant from before the swap
- a new plant offered over a keep-out strip, a swap that leaves one plant at
  two sizes, or an undo that does not put back the sizes
- an override that is accepted without a reason, or that the audit reports
  as an error, or that the review does not note
- a month that does not change the circles, or a bloom strip cell that
  disagrees with the plants in that bed
- a fruit mark outside the fruit months, or on a dormant plant

It saves a picture of every bed at both widths, and of every bed in April,
July, October and December. Playwright must be installed:

    python3 -m pip install --user playwright
    python3 -m playwright install chromium
"""

import argparse
import copy
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import practice, scheme, yards  # noqa: E402

WIDTHS = {"phone": 390, "desktop": 1280}
SHOT_MONTHS = ["Apr", "Jul", "Oct", "Dec"]
FAILS = []


def check(ok, name):
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        FAILS.append(name)


def _serve_from_memory(slug):
    """The real server, with scheme.json held in memory for the test."""
    state = {"scheme": copy.deepcopy(scheme.load(slug))}
    real_save = yards.save

    def save(s, name, data):
        if s == slug and name == scheme.FILE:
            state["scheme"] = data
            return None
        return real_save(s, name, data)

    scheme.load = lambda s: state["scheme"] if s == slug else None
    yards.save = save
    srv, url = scheme.serve(slug, port=0, host="127.0.0.1")
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/" + url.rsplit("/", 1)[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, url, state


GEOMETRY = """() => {
  const sheet = document.querySelector('.sheet:not([hidden])');
  const svg = sheet.querySelector('svg.bed');
  const box = svg.getBoundingClientRect();
  const labels = [...svg.querySelectorAll('text')].map(t => {
    const r = t.getBoundingClientRect();
    return {text: t.textContent, x: r.x - box.x, y: r.y - box.y, w: r.width, h: r.height};
  }).filter(l => l.text.trim());
  const leaders = [...svg.querySelectorAll('line.leader')].map(l => ({
    x1: +l.getAttribute('x1'), y1: +l.getAttribute('y1'),
    x2: +l.getAttribute('x2'), y2: +l.getAttribute('y2')}));
  const plants = [...svg.querySelectorAll('.plant')].map(g => ({
    id: g.dataset.id, name: g.dataset.name, group: g.dataset.group,
    locked: g.dataset.locked, hit: g.querySelector('circle.hit').getBoundingClientRect().width}));
  const tagged = [...svg.querySelectorAll('.tag')].map(t => t.dataset.for)
    .concat([...svg.querySelectorAll('.labels .code')].map(t => t.dataset.host));
  const last = svg.lastElementChild;
  const onTop = last && last.classList.contains('labels')
    && [...svg.querySelectorAll('text')].every(t => last.contains(t) || t.closest('.tag'));
  const rows = [...sheet.querySelectorAll('.schedule tr')].slice(1).map(tr =>
    parseInt(tr.children[1].textContent, 10));
  const circles = [...svg.querySelectorAll('.plant')].map(g => {
    const r = g.querySelector('circle.solid').getBoundingClientRect();
    return {id: g.dataset.id, cx: r.x - box.x + r.width / 2, cy: r.y - box.y + r.height / 2, r: r.width / 2};
  });
  const coded = [...svg.querySelectorAll('.labels .code')].map(t => {
    const r = t.getBBox();
    return {text: t.textContent, host: t.dataset.host, x: r.x, y: r.y, w: r.width, h: r.height};
  });
  const tagText = [...svg.querySelectorAll('.tag text')].map(t => t.textContent);
  return {w: box.width, h: box.height, labels, leaders, plants, tagged, rows, onTop, circles, coded, tagText};
}"""

STRIP = """(m) => {
  const sheet = document.querySelector('.sheet:not([hidden])');
  const names = new Set();
  sheet.querySelectorAll('.plant').forEach(g => {
    if (g.dataset.feeds === '1' && g.dataset.bloom.split(' ').includes(m)) names.add(g.dataset.name);
  });
  const cell = sheet.querySelector('.cell[data-month="' + m + '"] b');
  const states = [...sheet.querySelectorAll('.plant')].map(g =>
    ['m-bloom', 'm-leaf', 'm-ever', 'm-dormant'].find(c => g.classList.contains(c)) || '');
  const fruitWrong = [...sheet.querySelectorAll('.plant')].filter(g => {
    const due = (g.dataset.fruit || '').split(' ').includes(m);
    const mark = g.querySelector('.fruit');
    const shown = !!mark && getComputedStyle(mark).display !== 'none';
    return due !== shown || (due && g.classList.contains('m-dormant'));
  }).map(g => g.dataset.id);
  return {want: names.size, shown: parseInt(cell.textContent, 10), states, fruitWrong};
}"""


def _overlap(a, b):
    return (a["x"] < b["x"] + b["w"] - 1 and b["x"] < a["x"] + a["w"] - 1
            and a["y"] < b["y"] + b["h"] - 1 and b["y"] < a["y"] + a["h"] - 1)


def _covers(label, circle):
    """True when a label box reaches more than a pixel into a circle."""
    nx = min(max(circle["cx"], label["x"]), label["x"] + label["w"])
    ny = min(max(circle["cy"], label["y"]), label["y"] + label["h"])
    return (nx - circle["cx"]) ** 2 + (ny - circle["cy"]) ** 2 < (circle["r"] - 1) ** 2


def _cross(p, q):
    def orient(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    d1 = orient(p["x1"], p["y1"], p["x2"], p["y2"], q["x1"], q["y1"])
    d2 = orient(p["x1"], p["y1"], p["x2"], p["y2"], q["x2"], q["y2"])
    d3 = orient(q["x1"], q["y1"], q["x2"], q["y2"], p["x1"], p["y1"])
    d4 = orient(q["x1"], q["y1"], q["x2"], q["y2"], p["x2"], p["y2"])
    return d1 * d2 < 0 and d3 * d4 < 0


def swap_rules(slug, state):
    """A swap keeps a new plant out of a keep-out strip and keeps one size per group."""
    print("\nswap rules")
    work = copy.deepcopy(state["scheme"])
    for record in work["beds"]:
        scheme._even_sizes(record.get("plants") or [])
    state["scheme"] = work

    strip = None
    for record in work["beds"]:
        band = next(iter(record.get("keep_out") or []), None)
        spot = next((p for p in record.get("plants") or [] if not p.get("locked")), None)
        if band and spot:
            strip = (record, spot, band)
            break
    check(strip is not None, "some bed has a keep-out strip and a plant that can change")
    if strip:
        record, spot, band = strip
        saved = dict(spot)
        x_from = float(band.get("x_from") or 0)
        x_to = float(band["x_to"]) if band.get("x_to") is not None else float(record["length_ft"])
        spot.update(kept=True, y=float(band["y_below"]), x=(x_from + x_to) / 2)
        opts, _ = scheme.options_for(slug, work, spot["id"])
        check(not opts, f"{spot['id']}: a circle over the {band.get('kind') or 'keep-out'} "
                        f"strip offers no new plant ({len(opts or [])} offered)")
        _, err = scheme.swap(slug, spot["id"], "Turk's cap",
                             override="a test that the ground still rules")
        check(err is not None, f"{spot['id']}: an override cannot put a plant over the strip")
        spot.clear()
        spot.update(saved)

    target = None
    for record in work["beds"]:
        plants = record.get("plants") or []
        for plant in plants:
            if plant.get("locked"):
                continue
            opts, _ = scheme.options_for(slug, work, plant["id"])
            for o in opts or []:
                group = [p for p in plants if p is not plant and p["name"] == o["name"]
                         and p.get("niche") == plant.get("niche") and not p.get("locked")]
                if group and abs(group[0]["spread_ft"] - o["spread_ft"]) > 0.001:
                    target = (record, plant["id"], o["name"])
                    break
            if target:
                break
        if target:
            break
    check(target is not None, "some swap would draw a plant at a size that differs from its group")
    if target:
        record, pid, name = target
        snapshot = copy.deepcopy(work)
        _, err = scheme.swap(slug, pid, name)
        record = next(b for b in state["scheme"]["beds"] if b["id"] == record["id"])
        check(err is None and not scheme.uneven(record.get("plants") or []),
              f"{pid}: a swap to {name} leaves one size for each group in {record['id']}")
        scheme.undo(slug, pid)
        restored = state["scheme"]
        restored.pop("history", None)
        snapshot.pop("history", None)
        check(restored == snapshot, f"{pid}: undo puts back every plant that the swap resized")

    forced = None
    for record in state["scheme"]["beds"]:
        for plant in record.get("plants") or []:
            if plant.get("locked"):
                continue
            offered = {o["name"] for o in scheme.options_for(slug, state["scheme"], plant["id"])[0] or []}
            if "Turk's cap" not in offered and plant["name"] != "Turk's cap":
                forced = (record["id"], plant["id"])
                break
        if forced:
            break
    check(forced is not None, "some circle does not offer Turk's cap")
    if forced:
        bed_id, pid = forced
        before = copy.deepcopy(scheme.find_plant(state["scheme"], pid)[1])
        _, err = scheme.swap(slug, pid, "Turk's cap")
        check(err is not None, f"{pid}: a swap to a plant that is not offered is refused")
        _, err = scheme.swap(slug, pid, "Turk's cap", override="too short")
        check(err is not None, f"{pid}: an override with a short reason is refused")
        plant, err = scheme.swap(slug, pid, "Turk's cap",
                                 override="a test of a choice past the limit")
        chosen = (plant or {}).get("override") or {}
        check(err is None and chosen.get("reason") and chosen.get("limit"),
              f"{pid}: an override keeps the reason and the limit on the plant")
        bad = [line for line in scheme.audit(slug, state["scheme"]) if line.startswith(pid + " ")]
        check(not any("slate" in line for line in bad),
              f"{pid}: the audit reports no slate error for the override {bad[:2]}")
        notes = [f for f in scheme.review(slug, state["scheme"])
                 if f["rule"] == "override" and pid in f["text"]]
        check(len(notes) == 1 and notes[0].get("info"), f"{pid}: the review notes the override")
        scheme.undo(slug, pid)
        check(scheme.find_plant(state["scheme"], pid)[1] == before,
              f"{pid}: undo puts back {before['name']} exactly")


def run(slug, shots):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  skip  Playwright is not installed. See the module docstring.")
        return 0
    if not scheme.load(slug):
        raise SystemExit(f"{slug} has no {scheme.FILE}. Run lib.scheme --init first.")
    os.makedirs(shots, exist_ok=True)
    tap = float(practice.rule("drawing.tap_target_px"))
    srv, url, state = _serve_from_memory(slug)
    beds = [b["id"] for b in state["scheme"]["beds"]]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for label, width in WIDTHS.items():
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("requestfailed", lambda req: errors.append("failed " + req.url))
            page.goto(url + "#" + beds[0] + "/Oct")
            page.wait_for_load_state("networkidle")
            print(f"\n{label} ({width} px)")
            for bed in beds:
                page.click(f".tab[data-bed='{bed}']")
                g = page.evaluate(GEOMETRY)
                bad = [(a["text"], b["text"]) for i, a in enumerate(g["labels"])
                       for b in g["labels"][i + 1:] if _overlap(a, b)]
                check(not bad, f"{bed}: no two labels overlap {bad[:3] if bad else ''}")
                out = [l["text"] for l in g["labels"]
                       if l["x"] < -1 or l["y"] < -1 or l["x"] + l["w"] > g["w"] + 1
                       or l["y"] + l["h"] > g["h"] + 1]
                check(not out, f"{bed}: every label sits inside the drawing {out[:3] if out else ''}")
                crossing = sum(1 for i, a in enumerate(g["leaders"])
                               for b in g["leaders"][i + 1:] if _cross(a, b))
                check(crossing == 0, f"{bed}: no two leaders cross ({crossing})")
                check(g["onTop"], f"{bed}: every label is drawn above the circles")
                by_id = {p["id"]: p for b in state["scheme"]["beds"] for p in b["plants"]}
                over = sorted({(c["text"], o["id"]) for c in g["coded"] for o in g["circles"]
                               if o["id"] != c["host"] and _covers(c, o)
                               and not scheme._under_canopy(by_id[c["host"]], by_id[o["id"]])})
                check(not over, f"{bed}: no label sits on another plant's circle {over[:3] if over else ''}")
                coded = set(g["tagged"])
                blank = sorted(p["id"] for p in g["plants"] if p["id"] not in coded)
                check(not blank, f"{bed}: every plant has a label {blank[:4] if blank else ''}")
                shown = [c["text"] for c in g["coded"]] + g["tagText"]
                counted = sorted({text for text in shown if " " in text.strip()})
                check(not counted, f"{bed}: a plant label is the code only {counted[:3]}")
                record = next(b for b in state["scheme"]["beds"] if b["id"] == bed)
                mixed = [grp[0]["name"] for grp in scheme.uneven(record.get("plants") or [])]
                check(not mixed, f"{bed}: one plant in one niche has one size {mixed[:4] if mixed else ''}")
                shrunk = [p["id"] for p in record.get("plants") or [] if scheme.shrunk_canopy(p)]
                check(not shrunk, f"{bed}: no canopy plant is shrunk {shrunk}")
                small = [p["name"] for p in g["plants"] if p["hit"] + 0.5 < tap]
                check(not small, f"{bed}: every tap target is {tap:g} px or more")
                check(sum(g["rows"]) == len(g["plants"]),
                      f"{bed}: the schedule counts {sum(g['rows'])} and the map draws {len(g['plants'])}")
                seen = {}
                for m in SHOT_MONTHS:
                    page.click(f".month[data-month='{m}']")
                    s = page.evaluate(STRIP, m)
                    check(s["want"] == s["shown"],
                          f"{bed} {m}: the strip shows {s['shown']} nectar species and the plants give {s['want']}")
                    check(not s["fruitWrong"],
                          f"{bed} {m}: fruit shows in its months only, on a plant that is not dormant {s['fruitWrong'][:3]}")
                    seen[m] = s["states"]
                    if label == "desktop":
                        page.add_style_tag(content=".scroller{overflow:visible}")
                        page.locator(".sheet:not([hidden]) svg.bed").screenshot(
                            path=os.path.join(shots, f"{bed}-{m}.png"))
                check(len({tuple(v) for v in seen.values()}) > 1 or len(g["plants"]) <= 1,
                      f"{bed}: the circles change with the month")
                page.locator(".sheet:not([hidden])").screenshot(
                    path=os.path.join(shots, f"{bed}-{label}.png"))
            check(not errors, f"no console errors or failed requests {errors[:3] if errors else ''}")
            page.close()

        page = browser.new_page(viewport={"width": 390, "height": 900})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        target = None
        for bed in beds:
            page.click(f".tab[data-bed='{bed}']")
            ids = page.evaluate(
                "() => [...document.querySelectorAll('.sheet:not([hidden]) .plant')]"
                ".filter(g => g.dataset.locked === '0').map(g => g.dataset.id)")
            for pid in ids:
                opts, _ = scheme.options_for(slug, state["scheme"], pid)
                if opts:
                    target = (bed, pid, opts[0]["name"])
                    break
            if target:
                break
        check(target is not None, "some plant on the map has a choice list")
        if target:
            bed, pid, name = target
            page.click(f".tab[data-bed='{bed}']")
            page.locator(f".plant[data-id='{pid}'] circle.hit").dispatch_event("click")
            page.wait_for_selector("#list .opt")
            check(page.locator("#panel").is_visible(), "a tap opens the choice list")
            before = copy.deepcopy(scheme.find_plant(state["scheme"], pid)[1])
            kept_history = len(state["scheme"].get("history") or [])
            now = page.locator("#list .opt.now")
            check(now.count() == 1 and before["name"] in now.inner_text(),
                  f"the list shows the plant that is there now ({before['name']})")
            page.locator("#list button.opt", has_text=name).first.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("#status.saved", timeout=5000)
            drawn = page.get_attribute(f".plant[data-id='{pid}']", "data-name")
            check(drawn == name, f"a swap saves and redraws ({drawn} is now {name})")
            page.wait_for_selector("#undo:not([hidden])", timeout=5000)
            page.keyboard.press("Control+z")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("#status.saved:has-text('Put back')", timeout=5000)
            drawn = page.get_attribute(f".plant[data-id='{pid}']", "data-name")
            after = scheme.find_plant(state["scheme"], pid)[1]
            check(drawn == before["name"] and after == before,
                  f"Ctrl+Z puts back {before['name']} exactly ({drawn})")
            check(len(state["scheme"].get("history") or []) == kept_history,
                  "the undo removes only its own history entry")

        # A g01 viola offered Gayfeather is the case that started this check.
        # Any other flagged option stands in if the yard changes.
        flagged = []
        misordered = []
        for record in state["scheme"]["beds"]:
            for plant in record.get("plants") or []:
                if plant.get("locked"):
                    continue
                opts, _ = scheme.options_for(slug, state["scheme"], plant["id"])
                marks = [bool(o["taller_than"]) for o in opts or []]
                if marks != sorted(marks):
                    misordered.append(plant["id"])
                for o in opts or []:
                    if o["taller_than"]:
                        best = (record["id"], plant["name"], o["name"]) == ("g01", "Viola", "Gayfeather")
                        flagged.append((not best, record["id"], plant["id"], o["name"]))
        check(not misordered,
              f"a taller option sorts below every option that fits the row {misordered[:3]}")
        check(bool(flagged), "some option stands taller than the plant behind it")
        if flagged:
            _, bed, pid, name = min(flagged)
            if page.locator("#panel").is_visible():
                page.click("#close")
            page.click(f".tab[data-bed='{bed}']")
            page.locator(f".plant[data-id='{pid}'] circle.hit").dispatch_event("click")
            page.wait_for_selector("#list button.opt")
            rows = page.evaluate(
                "() => [...document.querySelectorAll('#list button.opt')].map(b => "
                "({name: b.querySelector('b').textContent, tall: b.classList.contains('tall'), "
                "warn: (b.querySelector('.taller') || {}).textContent || ''}))")
            marks = [r["tall"] for r in rows]
            row = next((r for r in rows if r["name"] == name), None)
            check(marks == sorted(marks), f"{pid}: the list shows taller options last")
            check(row is not None and row["tall"] and row["warn"].startswith("Taller than "),
                  f"{pid}: {name} carries the taller-than line ({row and row['warn']})")
        browser.close()
    srv.shutdown()
    swap_rules(slug, state)
    print(f"\n  pictures in {shots}")
    print(f"\n{len(FAILS)} failure{'' if len(FAILS) == 1 else 's'}")
    return 1 if FAILS else 0


def main():
    ap = argparse.ArgumentParser(description="The bed map in a real browser.")
    ap.add_argument("slug", nargs="?", default="cloverleaf-austin")
    ap.add_argument("--shots", default=os.path.join(yards.GARDEN_ROOT, ".cache", "mapview"))
    args = ap.parse_args()
    sys.exit(run(args.slug, args.shots))


if __name__ == "__main__":
    main()
