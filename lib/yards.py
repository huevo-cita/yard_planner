#!/usr/bin/env python3
"""Locating yards and loading their files.

    python3 -m lib.yards                 list every yard
    python3 -m lib.yards <slug>          show what that yard has and is missing
    python3 -m lib.yards --new <slug> --address "..." [--lat --lon]

One garden root holds one directory per yard. Every other module in this package
takes a slug or a directory and goes through here, so there is exactly one place
that knows where things live.
"""
import datetime
import json
import os
import re

LIB = os.path.dirname(os.path.abspath(__file__))

# Two roots, deliberately separate.
#
# REPO_ROOT is where the code lives — found from this file, so a clone works
# from wherever it is put. GARDEN_ROOT is where the yards live, and defaults to
# the same place because that is the simple case. Point GARDEN_ROOT somewhere
# else to keep personal data outside a checkout entirely, which is the safer
# arrangement on a shared or backed-up machine.
REPO_ROOT = os.path.dirname(LIB)
GARDEN_ROOT = os.path.expanduser(os.environ.get("GARDEN_ROOT", REPO_ROOT))
REGISTRY = os.path.join(GARDEN_ROOT, "yards.md")

# The repo's own directories sit alongside the yards when the two roots are the
# same, and are never a yard.
REPO_DIRS = {"lib", "maps", "skills", "agents", "bin", "tools", "vault",
             "docs", ".git", ".github"}

# the per-yard files, in the order a yard acquires them
FILES = ["site.json", "conditions.json", "vision.json", "design.json",
         "coverage.json", "sun-hours.json", "doubts.json", "all-clear.json",
         "changelog.json"]

PROVENANCE = ["measured", "lidar", "photo", "parcel", "osm", "survey",
              "reported", "derived", "assumed"]

# A rehearsal copy of a real yard, for trying new work against real data without
# touching it. The marker file is what makes a sandbox recognisable from the
# outside, so that everything generated inside one can say so. An unstamped
# rehearsal artifact found in six months is indistinguishable from the plan.
SANDBOX_MARKER = "sandbox.json"


def sandbox_of(slug):
    """The yard this one is a copy of, or None if it is a real yard."""
    return (load(slug, SANDBOX_MARKER) or {}).get("origin")


def sandbox_stamp(slug):
    """`SANDBOX of <origin>`, or None. Same contract as the provisional stamp
    in `doubts.gate` — a caller that gets a string marks its output with it."""
    origin = sandbox_of(slug)
    return f"SANDBOX of {origin}" if origin else None


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def yard_dir(slug, create=False):
    d = os.path.join(GARDEN_ROOT, slug)
    if create:
        for sub in ("", "maps", "photos", "design"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


def list_yards():
    """Every directory under the garden root that looks like a yard."""
    out = []
    if not os.path.isdir(GARDEN_ROOT):
        return out
    for name in sorted(os.listdir(GARDEN_ROOT)):
        d = os.path.join(GARDEN_ROOT, name)
        if not os.path.isdir(d) or name.startswith(".") or name in REPO_DIRS:
            continue
        if any(os.path.exists(os.path.join(d, f)) for f in FILES) or \
                os.path.exists(os.path.join(d, "profile.md")):
            out.append(name)
    return out


def path(slug, filename):
    return os.path.join(yard_dir(slug), filename)


def load(slug, filename, default=None):
    p = path(slug, filename)
    if not os.path.exists(p):
        return default
    with open(p) as fh:
        return json.load(fh)


def save(slug, filename, data):
    """Write JSON with a stamped `updated` field, creating the yard if needed."""
    yard_dir(slug, create=True)
    if isinstance(data, dict):
        data.setdefault("yard", slug)
        data["updated"] = datetime.date.today().isoformat()
    p = path(slug, filename)
    with open(p, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return p


def write_text(slug, filename, text):
    """Write a rendered document into the yard, creating the yard if needed.

    A document written into a sandbox is banner-stamped here rather than in each
    of the dozen modules that render one, because the failure being prevented is
    someone finding a rehearsal artifact months later and reading it as the plan,
    and that only takes one module forgetting.
    """
    yard_dir(slug, create=True)
    stamp = sandbox_stamp(slug)
    if stamp and filename.lower().endswith(".md") and stamp not in text[:400]:
        text = (f"> **{stamp}.** A rehearsal copy, not the plan. Nothing here "
                f"describes work anyone should do, and the real yard is "
                f"`{sandbox_of(slug)}`.\n\n") + text
    p = path(slug, filename)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def load_site(slug):
    site = load(slug, "site.json")
    if site is None:
        raise FileNotFoundError(
            f"{slug} has no site.json yet. Run the yard-survey skill first.")
    return site


def load_conditions(slug):
    return load(slug, "conditions.json", default={})


def load_vision(slug):
    return load(slug, "vision.json", default={})


def latlon(site):
    a = site.get("address", {})
    if a.get("lat") is None or a.get("lon") is None:
        raise ValueError("site.json has no lat/lon; run the yard-survey skill")
    return float(a["lat"]), float(a["lon"])


def status(slug):
    """What this yard has, for the gap report and the registry."""
    d = yard_dir(slug)
    have = {f: os.path.exists(os.path.join(d, f)) for f in FILES}
    have["profile.md"] = os.path.exists(os.path.join(d, "profile.md"))
    maps = os.path.join(d, "maps")
    have["maps"] = len(os.listdir(maps)) if os.path.isdir(maps) else 0
    return have


def stale(section, months=12):
    """True when a conditions.json section has not been verified recently.

    Compost gets used, tools get bought, and a bed that was edged last year may
    not be edged now. Anything older than the window is re-confirmed, not trusted.
    """
    when = (section or {}).get("last_verified")
    if not when:
        return True
    try:
        d = datetime.date.fromisoformat(str(when)[:10])
    except ValueError:
        return True
    return (datetime.date.today() - d).days > months * 30


def register(slug, address=None, lat=None, lon=None, label=None):
    """Create a yard directory and the seed site.json.

    Deliberately minimal. It records only what is actually known at this point,
    which is an address and possibly a coordinate, so that nothing downstream can
    mistake a placeholder for a measurement."""
    slug = slugify(slug)
    d = yard_dir(slug, create=True)
    site = load(slug, "site.json")
    if site is None:
        site = {"yard": slug, "schema_version": 2,
                "label": label or slug.replace("-", " ").title(),
                "address": {}, "frame": {}, "boundary": {}, "zones": {},
                "features": {}, "obstructions": {}, "provenance": {}}
    a = site.setdefault("address", {})
    if address:
        a["street"] = address
    if lat is not None:
        a["lat"] = float(lat)
    if lon is not None:
        a["lon"] = float(lon)
    save(slug, "site.json", site)
    update_registry()
    return d


def update_registry():
    """Rewrite yards.md from what is actually on disk."""
    lines = ["# Yards", "",
             "Regenerated by `python3 -m lib.yards --registry`. One line per yard,",
             "with what it has. The files themselves are the source of truth.", "",
             "| yard | address | site | conditions | vision | design | maps |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for slug in list_yards():
        st = status(slug)
        site = load(slug, "site.json") or {}
        a = site.get("address") or {}
        addr = a.get("street") or a.get("mailing") or a.get("of_record") or ""
        mark = lambda k: "yes" if st.get(k) else "-"        # noqa: E731
        lines.append(f"| `{slug}` | {addr} | {mark('site.json')} | "
                     f"{mark('conditions.json')} | {mark('vision.json')} | "
                     f"{mark('design.json')} | {st['maps']} |")
    lines.append("")
    with open(REGISTRY, "w") as fh:
        fh.write("\n".join(lines))
    return REGISTRY


def main():
    import argparse
    import sys

    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        ap = argparse.ArgumentParser()
        ap.add_argument("--new")
        ap.add_argument("--address")
        ap.add_argument("--lat", type=float)
        ap.add_argument("--lon", type=float)
        ap.add_argument("--label")
        ap.add_argument("--registry", action="store_true")
        args = ap.parse_args()
        if args.new:
            d = register(args.new, args.address, args.lat, args.lon, args.label)
            print(f"registered {slugify(args.new)} at {d}")
            print("next: python3 -m lib.parcel --geocode \"<address>\" to set "
                  "address.lat/lon, then set frame.anchor before importing "
                  "anything in lon/lat")
            return
        if args.registry:
            print(f"wrote {update_registry()}")
            return

    if len(sys.argv) > 1:
        slug = sys.argv[1]
        st = status(slug)
        print(f"{slug}  ({yard_dir(slug)})")
        for k, v in st.items():
            mark = "yes" if v else "no"
            print(f"  {k:18s} {mark if not isinstance(v, int) or k != 'maps' else str(v) + ' files'}")
        return
    ys = list_yards()
    if not ys:
        print(f"no yards yet under {GARDEN_ROOT}")
        return
    print(f"{'slug':22s} {'site':5s} {'cond':5s} {'vis':5s} {'design':7s} {'maps':>5s}")
    for slug in ys:
        st = status(slug)
        # A sandbox is named as one here, not left to be inferred from the slug.
        # A rehearsal copy sitting unlabelled in a list of real yards is the
        # thing the marker file exists to prevent.
        origin = sandbox_of(slug)
        print(f"{slug:22s} "
              f"{'yes' if st['site.json'] else '-':5s} "
              f"{'yes' if st['conditions.json'] else '-':5s} "
              f"{'yes' if st['vision.json'] else '-':5s} "
              f"{'yes' if st['design.json'] else '-':7s} "
              f"{st['maps']:>5d}"
              + (f"   SANDBOX of {origin}" if origin else ""))


if __name__ == "__main__":
    main()
