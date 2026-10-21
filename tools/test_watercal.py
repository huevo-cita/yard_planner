#!/usr/bin/env python3
"""Prove that the watering calendar says the right thing, and stops when it must.

    python3 tools/test_watercal.py
    python3 tools/test_watercal.py -v        show every check's detail

`lib.watercal` writes events to a real calendar that a person follows in the
garden. The properties worth proving:

  the squares        a grid cell is named by its row from the top and its
                     column, W1 to E<width>, so a task square reaches its crop
  the slots          `when` decides the slot. With no `when`, the prose decides
  the amount         a dose is multiplied by the squares or the plants that the
                     job reaches on that day
  the flags          the first day says STARTS TODAY, the last day says LAST
                     DAY and names the job that takes over
  the drip           the drip paragraph names the zones that run on that weekday
  coverage is quiet  a yard where every plant has a regime gives no finding
  coverage fires     a plant on no drip and no hand job, a seed that dries out,
                     a new planting with a long gap, and a taper hidden in a
                     note are each one finding
  exempt             a `water_exempt` record removes the finding that it names
  the timer check    a timer task on another day than its drip period is a
                     `week.check` finding
  the sync           the first plan creates, a second plan with no change gives
                     no operations, a changed task updates, and a removed task
                     deletes only the future events. A past event is never
                     touched
  the gate           a finding stops `--plan`, and `--force` stamps the events
  the .ics           every line is 75 octets or fewer

Everything runs against a temporary GARDEN_ROOT, so no real yard is read or
written.
"""
import argparse
import copy
import datetime
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="watercal-")
os.environ["GARDEN_ROOT"] = TMP
sys.path.insert(0, ROOT)

from lib import watercal, week, yards  # noqa: E402

SLUG = "wateryard"
D = datetime.date

results = []
verbose = False
MARK = {"pass": "ok  ", "FAIL": "FAIL"}


def record(state, label, detail=""):
    results.append((state, label, detail))
    print(f"  {MARK.get(state, state)}  {label}")
    if detail and (state != "pass" or verbose):
        for line in str(detail).strip().splitlines():
            print(f"          {line}")


def ok(cond, label, detail=""):
    record("pass" if cond else "FAIL", label, "" if cond else detail)


# --------------------------------------------------------------- the fixture

SITE = {"address": {"timezone": "America/Chicago", "lon": -97.7}}

SCHEME = {"beds": [
    {"id": "g01", "plants": [
        {"id": "g01-01", "name": "Sage", "botanical": "Salvia testii", "x": 1.0},
        {"id": "g01-02", "name": "Rose", "botanical": "Rosa testii", "x": 3.0}]},
    {"id": "g02", "plants": [
        {"id": "g02-01", "name": "Fern", "botanical": "Fernus testii", "x": 1.0}]},
]}

DESIGN = {
    "plants": [
        {"name": "Rose (existing)", "botanical": "Rosa testii", "zone": "bed_g01",
         "existing": True},
        {"name": "Fern (existing)", "botanical": "Fernus testii", "zone": "bed_g02",
         "existing": True},
    ],
    "layout": {"beds": [{"type": "grid", "name": "raised-bed", "width": 2,
                         "length": 2, "cells": [
                             {"x": 0, "y": 1, "w": 1, "h": 1, "label": "Kale\nx1"},
                             {"x": 1, "y": 1, "w": 1, "h": 1, "label": "Kale\nx1"},
                             {"x": 0, "y": 0, "w": 1, "h": 1, "label": "Carrots\nx8"},
                             {"x": 1, "y": 0, "w": 1, "h": 1, "label": "Radish"}]}]},
    "containers": [{"id": "P1", "name": "Cactus", "existing": True}],
}

IRRIGATION = {"drip": {
    "zones": {"B": {"label": "Zone B", "beds": ["g01"],
                    "start_times": ["00:00", "01:30"]},
              "A1": {"label": "Zone A1", "beds": ["raised"]}},
    "periods": [{"from": "2026-09-01", "task": "t009",
                 "zones": {"B": {"weekdays": ["Wed", "Sat"], "cycles": 2,
                                 "min_per_cycle": 10},
                           "A1": {"days_per_week": 7, "minutes": 5}}}],
}}


def task(tid, kind, title, **kw):
    t = {"id": tid, "kind": kind, "title": title, "minutes": 5, "done": False,
         "date_inferred": True, "date_note": "test"}
    t.update(kw)
    if "repeat" in t and "date" not in t:
        t["date"] = t["repeat"]["from"]
    return t


def rep(every, a, z, note=None):
    r = {"every": every, "from": a, "to": z}
    if note:
        r["note"] = note
    return r


TASKS = {"yard": SLUG, "schema_version": 1, "target_date": "2026-12-13",
         "sources": {}, "suppliers": {}, "shopping": [], "tasks": [
    task("t001", "plant", "Plant the sage", date="2026-10-01",
         where={"bed": "g01", "placements": [
             {"bed": "g01", "at": "ft 1.0 - front", "plant": "Sage x1"}]}),
    task("t002", "sow", "Sow the carrots", date="2026-10-01",
         germinate_days=3, where={"bed": "raised bed", "squares": ["2-W1"]}),
    task("t003", "water", "Keep the carrots damp", when="morning",
         where={"bed": "raised bed", "squares": ["2-W1", "2-E2"]},
         repeat=rep("day", "2026-10-01", "2026-10-04"),
         dose={"amount": 1, "unit": "cup", "per": "square"}),
    task("t004", "water", "Water the carrots every 2 days", when="morning",
         where={"bed": "raised bed", "squares": ["2-W1"]},
         repeat=rep("2 days", "2026-10-05", "2026-11-30"),
         dose={"amount": 0.5, "unit": "gal", "per": "square"}),
    task("t005", "water", "Establishment, every 2 days", when="morning",
         where={"bed": "g01", "planted_by": ["t001"]},
         repeat=rep("2 days", "2026-10-01", "2026-10-14"),
         dose={"amount": 1, "unit": "gal", "per": "plant"}),
    task("t006", "water", "Establishment, every 3 days", when="morning",
         where={"bed": "g01", "planted_by": ["t001"]},
         repeat=rep("3 days", "2026-10-15", "2026-11-04"),
         dose={"amount": 1, "unit": "gal", "per": "plant"}),
    task("t007", "water", "Establishment, weekly", when="evening",
         where={"bed": "g01", "planted_by": ["t001"]},
         repeat=rep("week", "2026-11-05", "2026-11-30"),
         dose={"amount": 1.5, "unit": "gal", "per": "plant"}),
    task("t008", "water", "Check the cactus", how=["In the evening, check it"],
         where={"place": "porch", "containers": ["P1"]},
         repeat=rep("14 days", "2026-10-01", "2026-12-31"),
         dose={"text": "only if dry"}),
    task("t009", "timer", "Set the timer", date="2026-09-01",
         where={"place": "the timer"},
         how=["Zone B: 2 cycles of 10 minutes", "Zone A1: daily, 5 min"]),
    task("t010", "water", "Water the fern", when="morning",
         where={"bed": "g02"}, repeat=rep("week", "2026-10-01", "2026-11-30"),
         dose={"amount": 1, "unit": "gal", "per": "plant"}),
]}


def write(tasks=None, design=None, irrigation=None, cal=None):
    shutil.rmtree(os.path.join(TMP, SLUG), ignore_errors=True)
    yards.save(SLUG, "site.json", copy.deepcopy(SITE))
    yards.save(SLUG, "scheme.json", copy.deepcopy(SCHEME))
    yards.save(SLUG, "design.json", copy.deepcopy(design or DESIGN))
    yards.save(SLUG, "irrigation.json", copy.deepcopy(irrigation or IRRIGATION))
    yards.save(SLUG, "tasks.json", copy.deepcopy(tasks or TASKS))
    if cal is not None:
        yards.save(SLUG, watercal.FILE, cal)


def tasks_with(fn):
    t = copy.deepcopy(TASKS)
    fn({x["id"]: x for x in t["tasks"]}, t)
    return t


START, END = D(2026, 10, 1), D(2026, 10, 30)


def kinds(found):
    return sorted(f["kind"] for f in found)


# ------------------------------------------------------------------- checks

def check_squares():
    write()
    items = watercal.inventory(SLUG)
    sq = {i["square"]: i["name"] for i in items if i["kind"] == "square"}
    ok(sq == {"1-W1": "Kale", "1-E2": "Kale", "2-W1": "Carrots",
              "2-E2": "Radish"}, "a grid cell is named by its row and column",
       json.dumps(sq))
    sage = next(i for i in items if i["name"] == "Sage")
    ok(sage["planted"] == D(2026, 10, 1) and sage["planted_by"] == "t001",
       "a foot-mark placement dates the circle that it names", json.dumps(
           sage, default=str))
    rose = next(i for i in items if i["name"] == "Rose")
    ok(rose["existing"], "a design record marked existing marks its circle")
    pot = next(i for i in items if i["kind"] == "container")
    ok(pot["pot"] == "P1" and pot["existing"], "a container is in the inventory")


def check_slots_and_amounts():
    write()
    data = week.load(SLUG)
    by = {t["id"]: t for t in data["tasks"]}
    ok(watercal.slots_of(by["t007"]) == ["evening"], "`when` decides the slot")
    ok(watercal.slots_of(by["t008"]) == ["evening"],
       "with no `when`, the prose decides the slot")
    evs = watercal.events(SLUG, D(2026, 10, 1), D(2026, 10, 1))
    am = next(e for e in evs if e["slot"] == "morning")
    ok("2 cups in all: 1 cup on each of 2 squares" in am["description"],
       "a dose is multiplied by the squares", am["description"])
    ok("1 gal on the plant" in am["description"],
       "a dose is multiplied by the plants that the job reaches",
       am["description"])
    ok(am["start"]["dateTime"] == "2026-10-01T07:30:00-05:00",
       "the event starts at the slot time with the zone offset",
       am["start"]["dateTime"])
    nov = watercal.events(SLUG, D(2026, 11, 5), D(2026, 11, 5))
    ok(any(e["start"]["dateTime"].endswith("-06:00") for e in nov),
       "the offset follows the change from daylight time")


def check_flags():
    write()
    first = watercal.events(SLUG, D(2026, 10, 1), D(2026, 10, 1))
    text = "\n".join(e["description"] for e in first)
    ok("STARTS TODAY: every day to Sun 4 Oct." in text,
       "the first day of a repeat says STARTS TODAY", text)
    last = watercal.events(SLUG, D(2026, 10, 4), D(2026, 10, 4))
    text = "\n".join(e["description"] for e in last)
    ok("LAST DAY of this job. From Mon 5 Oct: Water the carrots every 2 days"
       in text, "the last day names the job that takes over", text)
    ok("Then stop" not in text.split("[t003]")[1].split("\n\n")[0],
       "a job with a successor does not say stop")


def check_drip():
    write()
    block = watercal.drip(SLUG)
    wed = watercal.drip_line(block, D(2026, 10, 7))
    thu = watercal.drip_line(block, D(2026, 10, 8))
    ok("Zone B 2 x 10 min from 00:00, 01:30" in wed and "Zone A1 5 min" in wed,
       "the drip paragraph names the zones that run that day", wed)
    ok("Zone B" not in thu and "Zone A1 5 min" in thu,
       "a fixed-day zone is not named on another weekday", thu)


def check_coverage():
    write()
    found = watercal.coverage(SLUG, START, END)
    ok(found == [], "a yard where every plant has a regime gives no finding",
       "\n".join(m for _, m in watercal.coverage_lines(found)))

    write(tasks_with(lambda by, t: t["tasks"].remove(by["t010"])))
    found = watercal.coverage(SLUG, START, END)
    ok(kinds(found) == ["uncovered"] and found[0]["item"]["name"] == "Fern",
       "a plant on no drip and no hand job is one finding",
       "\n".join(m for _, m in watercal.coverage_lines(found)))

    d = copy.deepcopy(DESIGN)
    d["water_exempt"] = [{"bed": "g02", "name": "Fern", "reason": "test"}]
    write(tasks_with(lambda by, t: t["tasks"].remove(by["t010"])), design=d)
    ok(watercal.coverage(SLUG, START, END) == [],
       "a water_exempt record removes the finding that it names")

    def short_seed(by, t):
        by["t003"]["repeat"]["to"] = "2026-10-02"
    write(tasks_with(short_seed))
    found = watercal.coverage(SLUG, START, END)
    ok("seed" in kinds(found), "a seed that dries out before it is up is a "
       "finding", "\n".join(m for _, m in watercal.coverage_lines(found)))

    def long_gap(by, t):
        by["t006"]["repeat"]["every"] = "6 days"
    write(tasks_with(long_gap))
    found = watercal.coverage(SLUG, START, END)
    ok("establishment" in kinds(found),
       "a new planting with a gap longer than its stage is a finding",
       "\n".join(m for _, m in watercal.coverage_lines(found)))

    def taper(by, t):
        by["t005"]["repeat"]["note"] = "every second day for 14 days, then weekly"
    write(tasks_with(taper))
    found = watercal.coverage(SLUG, START, END)
    ok(kinds(found) == ["taper"], "a taper in a note is a finding",
       "\n".join(m for _, m in watercal.coverage_lines(found)))

    def stop(by, t):
        by["t005"]["repeat"]["note"] = "from day 0 to day 14, then stop"
    write(tasks_with(stop))
    ok(watercal.coverage(SLUG, START, END) == [],
       "a note that only says where the job ends is not a taper")


def check_timer():
    write()
    ok(watercal.drip_check(SLUG) == [], "a timer task on its period day agrees")
    irr = copy.deepcopy(IRRIGATION)
    irr["drip"]["periods"][0]["from"] = "2026-09-02"
    write(irrigation=irr)
    found = [p for p in week.check(SLUG) if p["kind"] == "drip"]
    ok(len(found) == 1 and "t009" in found[0]["message"],
       "a timer task on another day is a week.check finding",
       json.dumps(found))


def check_sync():
    write(cal={})
    try:
        watercal.plan(SLUG, today=START)
        ok(False, "a plan with no calendar_id refuses")
    except SystemExit:
        ok(True, "a plan with no calendar_id refuses")

    cal = {"calendar_id": "cal-1", "horizon_days": 20, "namespace": "ns"}
    write(cal=cal)
    p1 = watercal.plan(SLUG, today=START)
    ok(p1["counts"]["create"] > 0 and p1["counts"]["update"] == 0
       and p1["counts"]["delete"] == 0, "the first plan only creates",
       json.dumps(p1["counts"]))
    ok(all(o["args"]["sendUpdates"] == "none" and "attendees" not in o["args"]
           for o in p1["ops"]), "no event invites anybody")
    ids = {o["key"]: f"ev{i}" for i, o in enumerate(p1["ops"])}
    done, refused = watercal.record(SLUG, ids, today=START)
    ok(len(done) == len(ids) and not refused, "record keeps every created id")

    p2 = watercal.plan(SLUG, today=START)
    ok(p2["ops"] == [], "a second plan with nothing changed gives no "
       "operations", json.dumps(p2["counts"]))

    data = week.load(SLUG)
    for t in data["tasks"]:
        if t["id"] == "t003":
            t["title"] = "Keep the carrots wet"
    week.save(SLUG, data)
    p3 = watercal.plan(SLUG, today=START)
    ok(p3["counts"]["update"] > 0 and p3["counts"]["create"] == 0,
       "a changed task updates its events", json.dumps(p3["counts"]))
    watercal.record(SLUG, [{"key": o["key"]} for o in p3["ops"]], today=START)

    data = week.load(SLUG)
    data["tasks"] = [t for t in data["tasks"] if t["id"] != "t008"]
    week.save(SLUG, data)
    design = yards.load(SLUG, "design.json")
    design["water_exempt"] = [{"name": "Cactus", "reason": "test"}]
    yards.save(SLUG, "design.json", design)
    later = START + datetime.timedelta(days=2)
    p4 = watercal.plan(SLUG, today=later)
    gone = [o for o in p4["ops"] if o["op"] == "delete"]
    ok(gone and all(watercal.week._date(o["date"]) >= later for o in gone),
       "a removed task deletes only its future events", json.dumps(
           [o["key"] for o in gone]))
    ok(not any(o["key"].startswith(f"{SLUG}:2026-10-01") for o in p4["ops"]),
       "a past event is never touched")


def check_gate():
    t = tasks_with(lambda by, x: x["tasks"].remove(by["t010"]))
    write(t, cal={"calendar_id": "cal-1", "horizon_days": 7})
    try:
        watercal.plan(SLUG, today=START)
        ok(False, "a coverage finding stops the plan")
    except SystemExit as e:
        ok("uncovered" in str(e), "a coverage finding stops the plan", str(e))
    p = watercal.plan(SLUG, today=START, force=True)
    ok(p["stamp"] and all(o["args"]["description"].startswith("PROVISIONAL")
                          for o in p["ops"] if o["op"] != "delete"),
       "--force stamps every event with what it came past")

    def nodose(by, x):
        by["t004"].pop("dose")
    write(tasks_with(nodose), cal={"calendar_id": "cal-1", "horizon_days": 7})
    try:
        watercal.plan(SLUG, today=START)
        ok(False, "a water task with no dose stops the plan")
    except SystemExit as e:
        ok("no `dose`" in str(e), "a water task with no dose stops the plan")


def check_ics():
    write()
    evs = watercal.events(SLUG, START, START + datetime.timedelta(days=6))
    text = watercal.ics(SLUG, evs)
    lines = text.split("\r\n")
    ok(text.count("BEGIN:VEVENT") == len(evs), "one VEVENT for each event")
    ok(all(len(x.encode("utf-8")) <= 75 for x in lines),
       "every .ics line is 75 octets or fewer")
    ok("DTSTART;TZID=America/Chicago:20261001T073000" in text,
       "the .ics start carries the zone")


def main():
    global verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", action="store_true")
    verbose = ap.parse_args().v
    try:
        for fn in (check_squares, check_slots_and_amounts, check_flags,
                   check_drip, check_coverage, check_timer, check_sync,
                   check_gate, check_ics):
            print(f"\n {fn.__name__[6:].replace('_', ' ')}")
            fn()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    failed = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
