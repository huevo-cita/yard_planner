#!/usr/bin/env python3
"""A verified photograph of every species the design names.

    python3 -m lib.plantphotos cloverleaf-austin            fetch what is missing
    python3 -m lib.plantphotos cloverleaf-austin --web      rebuild the small copies
    python3 -m lib.plantphotos cloverleaf-austin --report   what there is, and what there is not

Writes `photos/plants/<Binomial>.jpg`, a smaller `photos/plants/web/` copy of
each for embedding, and `photos/plants/credits.json` holding the Commons file,
the photographer and the licence. Every page that shows a plant reads that
manifest, so a picture always travels with its credit.

The pictures exist to stop the wrong plant coming home from the nursery. A
mislabelled one is therefore worse than none at all, and two rules follow.

First, an image is accepted only when Wikipedia puts it at the top of the
article for that exact binomial, or when a Commons file's own title carries
both the genus and the epithet. A search result that merely mentions the
species is not enough.

Second, a species with no match is recorded as `"image": null` with the reason,
and the page prints a link to the Lady Bird Johnson Wildflower Center instead.
Nothing is ever substituted from a neighbouring species, however similar. That
is the exact error these pictures exist to prevent.

Small copies, and why they are a separate file rather than a resize in the
page: a page that embeds its images travels as one file to a phone, which is
where it gets read, and the full-size set is about 10 MB of JPEG that becomes
14 MB once base64 has had it. The web copies bring that to roughly a fifth,
which is the difference between a page that opens on a phone and one that does
not. The originals stay, because the credit and the provenance are attached to
them and a downscale is not a source.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import plants, yards

UA = "yard-planner/1.0 (personal garden plan; https://github.com/huevo-cita/yard_planner)"

#: What Wikimedia is asked for. Wide enough that habit and leaf are readable,
#: which is what tells one species from another.
WIDTH = 720

#: The embedded copy. Small enough that a page of them opens over a phone
#: connection, large enough to tell a blue rosette from a trunking shrub.
WEB_WIDTH = 460
WEB_QUALITY = 55

DIR = os.path.join("photos", "plants")
WEB = os.path.join(DIR, "web")
MANIFEST = "credits.json"


def paths(slug):
    root = yards.yard_dir(slug)
    return (os.path.join(root, DIR), os.path.join(root, WEB),
            os.path.join(root, DIR, MANIFEST))


def species_for(slug, traps=True):
    """Every binomial worth a picture, out of the record rather than a list.

    Two sources, and the second is not optional. The design gives the plants
    that are wanted. The call card gives the ones that must be REFUSED, and a
    trap panel showing the right plant beside an empty box is half a warning —
    the whole point is seeing the two together and being able to tell them
    apart on a bench.
    """
    design = yards.load(slug, "design.json") or {}
    out = []
    for p in design.get("plants", []):
        for b in plants.binomials(p):
            if b not in out:
                out.append(b)
    if traps:
        from . import callcard
        try:
            for b in callcard.species(slug):
                if b not in out:
                    out.append(b)
        except (FileNotFoundError, KeyError, ValueError):
            pass          # no tasks or no calls yet; the design alone is fine
    return out


def get(url):
    """Fetch, and wait out a rate limit rather than losing the species.

    Wikimedia returns 429 freely to an unauthenticated client. A species lost
    that way would be written down as "no photograph available", which is a
    different statement and a false one, so the retry is not politeness.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 5:
                raise
            wait = 2 ** attempt
            print(f"        429, waiting {wait}s")
            time.sleep(wait)


def api(host, params):
    params = dict(params, format="json", formatversion="2")
    url = f"https://{host}/w/api.php?" + urllib.parse.urlencode(params)
    return json.loads(get(url))


def lead_image(binomial):
    """The Commons file Wikipedia puts at the top of the species article.

    Returns (file_name, article_title). The title comes back so the caller can
    check what the request actually resolved to: a request for one species
    that lands on another species' article is the failure this whole exercise
    is about, and it is refused rather than used.
    """
    d = api("en.wikipedia.org", {
        "action": "query", "prop": "pageimages", "piprop": "original|name",
        "titles": binomial, "redirects": "1"})
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None, None
    page = pages[0]
    return page.get("pageimage"), page.get("title")


def commons_file(binomial):
    """A Commons file whose own title carries the binomial.

    The fallback for a species with no Wikipedia article. Both the genus and
    the epithet must appear in the file name, so a search for "Carex
    planostachys" cannot come back with a photograph of "Carex texensis".
    """
    parts = binomial.split()
    if len(parts) < 2:
        return None
    genus, epithet = parts[0].lower(), parts[1].lower()
    d = api("commons.wikimedia.org", {
        "action": "query", "list": "search", "srnamespace": "6",
        "srsearch": f'intitle:"{binomial}"', "srlimit": "20"})
    for hit in d.get("query", {}).get("search", []):
        title = hit["title"]
        low = title.lower()
        if genus in low and epithet in low and \
                low.rsplit(".", 1)[-1] in ("jpg", "jpeg", "png"):
            return title.split(":", 1)[1]
    return None


def credit(file_name):
    """Photographer and licence for a Commons file, plus a sized thumbnail."""
    d = api("commons.wikimedia.org", {
        "action": "query", "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": str(WIDTH),
        "titles": "File:" + file_name})
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    info = pages[0]["imageinfo"][0]
    meta = info.get("extmetadata", {})

    def field(key):
        v = meta.get(key, {}).get("value", "")
        # extmetadata returns HTML for the artist field. A caption wants a name.
        out, tag = [], False
        for ch in v:
            if ch == "<":
                tag = True
            elif ch == ">":
                tag = False
            elif not tag:
                out.append(ch)
        return " ".join("".join(out).split())

    return {
        "thumb": info.get("thumburl") or info.get("url"),
        "page": info.get("descriptionurl"),
        "artist": field("Artist") or "unknown",
        "licence": field("LicenseShortName") or "see the Commons page",
    }


def downscale(src, dst, width=WEB_WIDTH, quality=WEB_QUALITY):
    """A smaller copy, by whatever this machine has.

    `sips` ships with macOS and Pillow does not ship with anything, so both
    are tried and neither is required. With neither available the original is
    copied unchanged: a page that is larger than it should be still works, and
    a page with no pictures does not.
    """
    if shutil.which("sips"):
        r = subprocess.run(
            ["sips", "-Z", str(width), "-s", "format", "jpeg",
             "-s", "formatOptions", str(quality), src, "--out", dst],
            capture_output=True)
        if r.returncode == 0 and os.path.exists(dst):
            return "sips"
    try:
        from PIL import Image
        im = Image.open(src)
        im.thumbnail((width, width * 4))
        im.convert("RGB").save(dst, "JPEG", quality=quality, optimize=True)
        return "pillow"
    except Exception:
        pass
    shutil.copyfile(src, dst)
    return "copied"


def web_copy(root, rel, width=900):
    """A smaller copy of any image the record points at, beside the original.

    Used for the bed maps, which are referenced by a couple of dozen tasks
    each. Embedding one of those per task would put the same 400 KB into a
    page twenty-seven times, so a page shows each map once and links to it —
    the same rule as the prose, applied to pictures.
    """
    src = os.path.join(root, rel)
    if not os.path.exists(src):
        return None
    d, name = os.path.split(rel)
    outdir = os.path.join(root, d, "web")
    os.makedirs(outdir, exist_ok=True)
    dst = os.path.join(outdir, name)
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        downscale(src, dst, width=width, quality=70)
    return os.path.join(d, "web", name).replace(os.sep, "/")


def rebuild_web(slug):
    """Small copies for every original, and the manifest entries pointing at them."""
    full, web, manifest_path = paths(slug)
    if not os.path.isdir(full):
        return {}, 0
    os.makedirs(web, exist_ok=True)
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    saved = 0
    for binomial, rec in manifest.items():
        if not rec.get("image"):
            continue
        name = os.path.basename(rec["image"])
        src, dst = os.path.join(full, name), os.path.join(web, name)
        if not os.path.exists(src):
            continue
        if not os.path.exists(dst) or \
                os.path.getmtime(dst) < os.path.getmtime(src):
            downscale(src, dst)
        rec["web"] = f"{WEB}/{name}".replace(os.sep, "/")
        saved += os.path.getsize(src) - os.path.getsize(dst)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    return manifest, saved


def fetch(slug, species=None, pause=1.2):
    full, web, manifest_path = paths(slug)
    os.makedirs(web, exist_ok=True)
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)

    wanted = species or species_for(slug)
    for binomial in wanted:
        stem = binomial.replace(" ", "_")
        path = os.path.join(full, stem + ".jpg")
        if manifest.get(binomial, {}).get("image") and os.path.exists(path):
            print(f"  have  {binomial}")
            continue

        try:
            file_name, title = lead_image(binomial)
        except Exception as exc:                       # network, not data
            print(f"  FAIL  {binomial}: {exc}", file=sys.stderr)
            continue

        # "Salvia rosmarinus" legitimately redirects to "Rosemary", so a
        # redirect is allowed. Landing on a different binomial is not.
        if title and " " in title and title != binomial \
                and title.split()[0] != binomial.split()[0]:
            print(f"  SKIP  {binomial} -> {title}, not the same plant")
            file_name, title = None, None

        source = "the Wikipedia article"
        if not file_name:
            file_name = commons_file(binomial)
            source = "a Commons file named for the species"
        if not file_name:
            manifest[binomial] = {"image": None,
                                  "why": "nothing on Wikipedia or Commons "
                                         "carries this binomial"}
            print(f"  none  {binomial} - no picture, pages will link out")
            continue

        c = credit(file_name)
        if not c:
            manifest[binomial] = {"image": None, "why": "no Commons record"}
            continue

        with open(path, "wb") as fh:
            fh.write(get(c["thumb"]))
        downscale(path, os.path.join(web, stem + ".jpg"))
        manifest[binomial] = {
            "image": f"{DIR}/{stem}.jpg".replace(os.sep, "/"),
            "web": f"{WEB}/{stem}.jpg".replace(os.sep, "/"),
            "file": file_name,
            "article": title,
            "commons": c["page"],
            "artist": c["artist"],
            "licence": c["licence"],
            "found_via": source,
        }
        print(f"  got   {binomial:32s} "
              f"{os.path.getsize(path) // 1024:4d} KB  {c['licence']}")
        time.sleep(pause)

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    return manifest, wanted


def report(slug):
    full, web, manifest_path = paths(slug)
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    wanted = species_for(slug)
    have = [b for b in wanted if manifest.get(b, {}).get("image")]
    missing = [b for b in wanted if not manifest.get(b, {}).get("image")]
    extra = [b for b in manifest if b not in wanted and manifest[b].get("image")]

    def size(d):
        if not os.path.isdir(d):
            return 0
        return sum(os.path.getsize(os.path.join(d, f))
                   for f in os.listdir(d) if f.endswith(".jpg"))

    print(f"  {slug} — {len(have)} of {len(wanted)} design species have a "
          f"photograph")
    print(f"      originals {size(full) // 1024:6d} KB")
    print(f"      web copies{size(web) // 1024:6d} KB   "
          f"(embedded, these are what a page carries)")
    for b in missing:
        why = manifest.get(b, {}).get("why", "never fetched")
        print(f"      no photo: {b} — {why}")
    if extra:
        print(f"      {len(extra)} photograph(s) of species no longer in the "
              f"design: {', '.join(extra)}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--web", action="store_true",
                    help="rebuild the small copies from the originals")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--species", nargs="+",
                    help="fetch these binomials as well as the design's")
    args = ap.parse_args()

    if args.report:
        report(args.slug)
        return
    if args.web:
        manifest, saved = rebuild_web(args.slug)
        n = sum(1 for v in manifest.values() if v.get("web"))
        print(f"  {n} web copies, {saved // 1024} KB smaller than the originals")
        return

    species = species_for(args.slug)
    for b in args.species or []:
        if b not in species:
            species.append(b)
    fetch(args.slug, species)
    report(args.slug)


if __name__ == "__main__":
    main()
