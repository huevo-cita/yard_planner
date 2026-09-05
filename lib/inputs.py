#!/usr/bin/env python3
"""Which parts of site.json each expensive job actually reads.

    python3 -m lib.inputs                    the map, and whether it still holds
    python3 -m lib.inputs <job>              one job, with where each read is
    python3 -m lib.inputs --drift            just the drift check, for a test

Why this file exists
--------------------
The all-clear in `lib.doubts` asks the assistant to say, in writing, why it is
safe to run a job on every input that was assumed or reported rather than
measured. That question is only answerable if "the inputs this job depends on"
is a real set rather than a gesture, and it is only *proportionate* if the set
is the job's own. Making `bom` account for a tree crown it never reads is how a
gate ends up switched off.

So there is a declared map below, and `derive()` recovers the same thing from
the source by static analysis, and `drift()` puts the two side by side. The
declared map is what runs — reading the AST on the way into every gate would be
work for nothing — and the derived one is what stops it going quietly out of
date. `tools/test_gate.py` and `tools/doctor.py` both run the comparison.

How the derivation works, and where it is coarse
------------------------------------------------
`derive()` parses a job's module, follows its first-party imports, and collects
the top-level key of every read against a variable holding the site record —
`site["boundary"]`, `self.S.get("obstructions")`, `siteschema.get_path(site,
"features.trees")`. It is deliberately an over-approximation in three ways,
each of which errs toward demanding more of an all-clear rather than less. A
fourth imprecision runs the other way and is described further down, because it
is the one worth knowing about:

Reads are attributed at **module** granularity. `lib.drawbeds` imports
`lib.yards`, and `lib.yards.latlon` reads `address`, so `drawbeds` is credited
with reading `address` whether or not it ever calls it. Following the call graph
instead of the import graph would be more precise and much easier to get subtly
wrong, and the cost of the coarse version is a handful of extra paths on a
record that has assumed its own street address, which is rare.

Reads are collected at **top-level section** granularity. `lib.sunmodel` reads
`features.trees` and `features.canopy_stacking` but nothing else under
`features`, and the map records `features`. On the yards this was written
against that pulls in a few bed notes filed under `features.beds`, which is
noise but honest noise: it is one section of one file, and the alternative is a
per-path exception list that nobody maintains.

Anything reached only through the gate itself is **not** counted. `lib.doubts`
and `lib.gaps` are on `SKIP` because both read the site record to *price* a
doubt, not to produce the job's output, and every gated job imports `doubts` by
definition. Following them would make every job's map the union of every other
job's, which is the same as having no map.

Where it is coarse in the dangerous direction
---------------------------------------------
There is a fourth imprecision and it goes the other way, so it is the one that
matters. A read is only recognised when it is made through a name the scan
believes holds the record. That starts from `SITE_ALIASES` and grows by
following plain assignments within the module, to a fixed point:

    site["obstructions"]          # seen
    rec = site or {}
    rec.get("obstructions")       # seen: `rec` was learned from the line above

What is still invisible is everything that is not a plain assignment from a name
already known — a record arriving as a function parameter under a new name, one
pulled out of a dict or a list, one passed through a helper in another module:

    def shade(record):            # `record` is a site record, and nothing here
        return record["obstructions"]   # knows that. drift() reports clean.

So `drift()` proves the declared map covers every read it can *see*, which is
not the same as every read the code makes. Closing the rest is dataflow
analysis; the working rule is that `SITE_ALIASES` gets extended by hand when a
module starts calling the record something new, and that a clean `drift()` is
evidence rather than proof.

What the map does not cover
---------------------------
Only `site.json` carries provenance, so only `site.json` is in scope. A job's
real dependencies include `conditions.json`, `vision.json`, `design.json` and
`sun-hours.json`, and nothing here or in the all-clear says anything about them.

Nor is the map transitive through artifacts. `bom` costs a `design.json` that
was written against a `sun-hours.json` that was modelled on an assumed fence
height, and the fence height is genuinely upstream of the total. It is not in
`bom`'s set, because `bom` reads a file that already exists rather than the
fence. The argument for stopping here is that the fence was attested when
`sunmodel` ran and would have to be attested again if it moved; the argument
against is that nothing checks the two runs used the same fence. That gap is
real and is written up in `.cursor/hooks/VALIDATOR.md`.
"""
import ast
import hashlib
import json
import os
import sys

from . import siteschema, yards

LIB = os.path.dirname(os.path.abspath(__file__))

# What each gated job reads out of site.json, and why. `sections` is what runs;
# `derive()` has to agree with it or `drift()` complains. `why` is here so that
# a reviewer can argue with an entry without first reading the module.
JOB_INPUTS = {
    "sunmodel": {
        "sections": ["address", "analysis_bands", "boundary", "features",
                     "frame", "narrative", "obstructions", "pending_site_walk",
                     "zones"],
        "why": "the shade model casts rays at the whole 3D record. The grid "
               "comes from `boundary`, its orientation from `frame`, the sun "
               "from `address`, everything opaque from `obstructions`, the "
               "crowns from `features`, and the reported means from `zones`. "
               "This is the job with the widest reach and the one worth "
               "attesting to most carefully.",
    },
    "design": {
        "sections": ["address", "climate", "zones"],
        "why": "the linter checks a plant list against measured light, water "
               "and soil. The light comes from `sun-hours.json` rather than "
               "from the geometry, so the site record it touches is small: "
               "bed identity and size from `zones`, heat and chill from "
               "`climate`, and latitude from `address` for season length.",
    },
    "drawbeds": {
        "sections": ["address"],
        "why": "it draws the `layout` block of design.json to scale and reads "
               "no geometry of its own. `address` is here only because the "
               "module imports `lib.yards`, whose `latlon` touches it; the "
               "honest reading of this entry is that drawbeds depends on "
               "nothing in site.json.",
    },
    "bom": {
        "sections": ["address", "climate", "zones"],
        "why": "quantities scale with bed area, which comes from `zones` "
               "through `design.zone_areas`. Importing `lib.design` for that "
               "brings `climate` with it.",
    },
    "schedule": {
        "sections": ["address", "climate", "zones"],
        "why": "narrower than it looks, and worth stating exactly because the "
               "obvious reading is wrong. `climate` is read once, by "
               "`frost_dates`, which `build` calls after the plan is already "
               "assembled and only to print beside it — no task is placed by "
               "frost arithmetic, and the seed-start and days-to-maturity "
               "helpers that do count backwards are reachable from the command "
               "line and never from `build`. `zones` is read for bed LABELS, to "
               "match a design zone against the ground record; task hours are "
               "flat archetypes and do not scale with area. What actually sizes "
               "a plan is `conditions.json` — the hours band, the travel gaps "
               "and the blackouts — and that file is outside every all-clear.",
    },
}

# Bookkeeping about the record rather than values the model consumes. `siteschema`
# reads all of these in `validate()` and `migrate()`, and a job that imports it
# would otherwise be credited with depending on its own provenance map.
META_SECTIONS = {"provenance", "assumptions", "verify_on_site", "schema_version",
                 "yard", "label", "updated", "sources"}

# Not part of any job's reading, however it is imported. See the module docstring.
SKIP = {"doubts", "gaps", "inputs"}

# The names a site record travels under. Everything in this package either calls
# it `site` or hangs it off `self.S`, which is what makes the scan tractable —
# and what makes this list load-bearing. A read through any other local name is
# invisible to `derive()`, so `drift()` will report clean on a section it never
# saw. Add to this whenever a module starts calling the record something new.
SITE_ALIASES = {"site", "self.S", "m.S", "self.site"}

# Provenance sources that are a guess rather than an observation, and therefore
# the ones an all-clear has to account for. `derived` is deliberately out: a
# frost date computed from thirty years of reanalysis carries that dataset's
# error and is not somebody's impression.
SOFT_SOURCES = ("assumed", "reported")


# --------------------------------------------------------------- the derivation

def _unwrap(text):
    """Strip the parentheses and `or {}` guards this codebase reads site through."""
    t = text.strip()
    prev = None
    while prev != t:
        prev = t
        for suffix in (" or {}", " or []", " or 0", " or ''", " or None"):
            if t.endswith(suffix):
                t = t[:-len(suffix)].strip()
        if t.startswith("(") and t.endswith(")"):
            depth = 0
            closes_at_end = True
            for i, ch in enumerate(t):
                depth += (ch == "(") - (ch == ")")
                if depth == 0 and i != len(t) - 1:
                    closes_at_end = False
                    break
            if closes_at_end:
                t = t[1:-1].strip()
    return t


class _Reads(ast.NodeVisitor):
    """Top-level site sections read in one module, and the first-party imports."""

    def __init__(self, tree=None):
        self.sections = {}          # section -> the source line that reads it
        self.imports = set()
        self.aliases = set(SITE_ALIASES)
        if tree is not None:
            self._learn_aliases(tree)

    def _learn_aliases(self, tree):
        """`rec = site or {}` makes `rec` a site record too.

        Only the trivial forms, and only within the module: a name bound
        directly to something already known to be the record, optionally with an
        `or {}` after it. Run to a fixed point so a second hop is followed. This
        narrows the blind spot described in the docstring; it does not close it,
        because a record arriving as a function parameter or out of a container
        is still invisible.
        """
        for _ in range(4):
            before = len(self.aliases)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.NamedExpr)):
                    continue
                value = node.value
                if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
                    value = value.values[0]
                if _unwrap(ast.unparse(value)) not in self.aliases:
                    continue
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                for t in targets:
                    if isinstance(t, (ast.Name, ast.Attribute)):
                        self.aliases.add(_unwrap(ast.unparse(t)))
            if len(self.aliases) == before:
                return

    def _note(self, section, node):
        if section in META_SECTIONS:
            return
        self.sections.setdefault(section, ast.unparse(node)[:72])

    def visit_ImportFrom(self, node):
        if node.level == 1:
            if node.module:
                self.imports.add(node.module.split(".")[0])
            else:
                self.imports.update(a.name for a in node.names)
        self.generic_visit(node)

    def visit_Subscript(self, node):
        if _unwrap(ast.unparse(node.value)) in self.aliases:
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                self._note(key.value, node)
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Attribute) and node.args:
            first = node.args[0]
            if f.attr in ("get", "setdefault") and \
                    _unwrap(ast.unparse(f.value)) in self.aliases and \
                    isinstance(first, ast.Constant) and \
                    isinstance(first.value, str):
                self._note(first.value, node)
            # siteschema.get_path(site, "features.trees.0.height") and friends
            elif f.attr in ("get_path", "set_path", "provenance_of",
                            "set_provenance") and len(node.args) >= 2 and \
                    _unwrap(ast.unparse(first)) in self.aliases and \
                    isinstance(node.args[1], ast.Constant) and \
                    isinstance(node.args[1].value, str):
                self._note(node.args[1].value.split(".")[0], node)
        self.generic_visit(node)


def _scan(module):
    path = os.path.join(LIB, module + ".py")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        tree = ast.parse(fh.read(), filename=path)
    v = _Reads(tree)
    v.visit(tree)
    return v


def closure(job):
    """The job's module and every first-party module it pulls in, minus SKIP."""
    seen, out, stack = set(), [], [job]
    while stack:
        name = stack.pop()
        if name in seen or name in SKIP:
            continue
        scanned = _scan(name)
        if scanned is None:
            continue
        seen.add(name)
        out.append((name, scanned))
        stack.extend(sorted(scanned.imports - seen))
    return sorted(out)


def derive(job):
    """Sections read by the job, recovered from the source rather than declared."""
    found = {}
    for module, scanned in closure(job):
        for section, where in scanned.sections.items():
            found.setdefault(section, (module, where))
    return found


def declared(job):
    return set(JOB_INPUTS.get(job, {}).get("sections") or [])


def drift():
    """Where the declared map and the source disagree. Empty means it holds."""
    from . import doubts

    problems = []
    for job in sorted(doubts.JOBS):
        if job not in JOB_INPUTS:
            problems.append(f"{job} is gated but has no entry in JOB_INPUTS, so "
                            f"its all-clear would attest to nothing")
            continue
        found = derive(job)
        want = declared(job)
        for section in sorted(set(found) - want):
            module, where = found[section]
            problems.append(
                f"{job} reads site[{section!r}] in lib.{module} — `{where}` — "
                f"and JOB_INPUTS does not list it. Anything assumed under "
                f"{section} is being run on without an all-clear ever asking "
                f"about it")
        for section in sorted(want - set(found)):
            problems.append(
                f"{job} declares {section!r} and nothing in its import closure "
                f"reads it. Harmless except that it makes every all-clear "
                f"longer than it needs to be, which is how this gets disabled")
    for job in sorted(set(JOB_INPUTS) - set(doubts.JOBS)):
        problems.append(f"JOB_INPUTS has {job!r}, which is not a gated job")
    return problems


# ------------------------------------------------------- the soft input set

MISSING = object()


def _effective_source(prov, path):
    """The source covering a path, falling back to whatever covers its parent.

    A survey stamps `features.trees` once for all fourteen trees. `lib.gaps`
    resolves the same way, and the two have to agree or a path can be soft to
    one and hard to the other.
    """
    parts = path.split(".")
    for n in range(len(parts), 0, -1):
        hit = prov.get(".".join(parts[:n]))
        if hit:
            return hit.get("source")
    return None


def fingerprint(site, path, source):
    """A short hash of what an all-clear was actually looking at.

    Covers the value *and* its provenance source, so that both editing a fence
    height and downgrading it from measured to assumed invalidate the clearance
    that was filed over it.
    """
    value = siteschema.get_path(site, path, MISSING)
    body = json.dumps(
        {"source": source,
         "value": None if value is MISSING else value,
         "present": value is not MISSING},
        sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def census(site, job):
    """How many things there are, in the parts of the record this job reads.

    `soft_inputs` and its fingerprints only ever look at values that carry a
    provenance entry saying `assumed` or `reported`. A whole new obstruction
    added with no provenance entry at all is therefore invisible to them: a
    ten-foot wall can appear in front of a bed and every clearance still reads
    as current. This is the cheapest thing that notices, and it is deliberately
    coarse — the length of every collection under the sections the job reads,
    which changes when something is added or removed and does not change when a
    number inside one is corrected.

    So it catches a new fence, a new tree and a deleted bed. It does not catch
    an existing measured value being edited, which is a separate and defensible
    hole named in VALIDATOR.md.
    """
    out = {}

    def walk(node, path):
        if isinstance(node, dict):
            members, keys = list(node.values()), list(node.keys())
        elif isinstance(node, list):
            members, keys = node, list(range(len(node)))
        else:
            return
        if any(isinstance(m, (dict, list)) for m in members):
            out[path] = len(members)
        for k, v in zip(keys, members):
            walk(v, f"{path}.{k}")

    for section in sorted(declared(job)):
        if section in (site or {}):
            walk(site[section], section)
    return out


# --------------------------------------------- staleness of derived artifacts

#: Which job's declared input set governs each derived artifact. Taking the
#: scope from `JOB_INPUTS` rather than writing a second list of paths is the
#: whole point: `drift()`, `tools/doctor.py` and `tools/test_gate.py` already
#: enforce that this map matches what the code reads, so the staleness question
#: and the gate question cannot come apart.
#:
#: `coverage.json` is written by `lib.gaps`, which is deliberately *not* a gated
#: job and has no entry of its own. It ranks every gap in the record by how much
#: light the unknown is worth, so it depends on the same geometry the shade model
#: does, and `sunmodel` is the widest declared set. Pointing it at a declared
#: job's set keeps it inside the agreement `doctor.py` checks; giving it a set of
#: its own would put it outside.
#:
#: `design.json` is deliberately absent, and used to be here. Nothing generates
#: it — `lib.design` writes it once with `--init` and thereafter only lints it —
#: so there is no run that could stamp it, and "the design was linted against a
#: site record that has since changed" is the question `lib.doubts --clear
#: design` already answers, by going stale and naming the value that moved.
ARTIFACTS = {"sun-hours.json": "sunmodel", "coverage.json": "sunmodel"}

#: Leaf keys holding prose *about* a value rather than a value the model
#: consumes. A digest that covers these is the mtime check's false positive with
#: extra steps: correcting a note or a citation rewrites nothing a ray traces.
#:
#: The direction of error here is worth stating, because this repo has been bitten
#: by it. A prose key holding a number a scalar should hold — `"note": "call it 6
#: ft"` where `height_in` is absent — is excluded from the digest, so editing it
#: goes unnoticed. That is a real hole, and the answer to it is that the number
#: belongs in a scalar, which is a separate check. `provenance` is not listed
#: because it is a `META_SECTIONS` entry and no job declares it.
PROSE_LEAVES = {"note", "notes", "comment", "comments", "why", "description",
                "detail", "source", "sources", "citation", "cite", "verify",
                "verify_on_site", "narrative", "caveat", "reasoning",
                "last_verified", "read_on", "provenance_note"}


def input_leaves(site, job):
    """Every leaf under the sections this job declares, minus the prose."""
    out = {}

    def walk(node, path, key):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}", str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}.{i}", key)
        elif key not in PROSE_LEAVES:
            out[path] = node

    for section in sorted(declared(job)):
        if section in (site or {}) and section not in META_SECTIONS:
            walk(site[section], section, section)
    return out


#: How deep the recorded fingerprints go. A subtree, not a leaf.
#:
#: `FIX-STALENESS-DIGEST.txt` asked for a finding naming
#: `obstructions.fences[3].height_in`, and this names `obstructions.fences`.
#: The reason is size: this yard's shade model declares 833 leaves, and a
#: fingerprint each is 18 KB written into a `sun-hours.json` that is 26 KB of
#: numbers somebody reads. The digest would be most of the file. At this depth
#: it is 51 entries and 2 KB, the finding names the subtree, and
#: `python3 -m lib.inputs sunmodel` gets from there to the value.
#:
#: This costs nothing in *detection* — a leaf moving changes its subtree's
#: fingerprint either way — only in how precisely the finding can point.
STAMP_DEPTH = 2


def _hash(value):
    body = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def _subtrees(site, job):
    """The job's declared leaves, bucketed by subtree and fingerprinted."""
    buckets = {}
    for path, value in sorted(input_leaves(site, job).items()):
        buckets.setdefault(".".join(path.split(".")[:STAMP_DEPTH]),
                           []).append((path, value))
    return {key: _hash(members) for key, members in buckets.items()}


def stamp(site, job):
    """What a derived artifact should record about the inputs it was built from.

    Same shape as the all-clear in `lib.doubts` — a fingerprint per path, plus
    `census` so that an addition or a removal inside a subtree is noticed — for
    the same reason: one digest over everything can only say *something* moved,
    and the finding worth printing names the thing.
    """
    trees = _subtrees(site, job)
    cens = census(site, job)
    return {"job": job, "subtrees": trees, "census": cens,
            "digest": _digest_of(trees, cens)}


def _digest_of(trees, cens):
    body = json.dumps([sorted(trees.items()), sorted(cens.items())],
                      sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def moved(recorded, site, job=None):
    """Which declared inputs have changed since an artifact recorded them.

    Returns `None` when the artifact carries no stamp. That is a different
    answer from "current" and has to read differently: the question cannot be
    asked yet, rather than nothing having moved.
    """
    if not isinstance(recorded, dict) or not recorded.get("subtrees"):
        return None
    job = job or recorded.get("job")
    now = _subtrees(site, job)
    was = recorded["subtrees"]
    cens = census(site, job)
    return {"job": job,
            "changed": sorted(k for k, v in now.items()
                              if k in was and was[k] != v),
            "added": sorted(set(now) - set(was)),
            "removed": sorted(set(was) - set(now)),
            "counted": sorted(k for k, n in cens.items()
                              if (recorded.get("census") or {}).get(k, n) != n),
            "current": recorded.get("digest") == _digest_of(now, cens)}


def soft_inputs(site, job):
    """Every assumed-or-reported provenance entry the job depends on.

    Keyed by the provenance path rather than by anything derived, so the list an
    all-clear has to answer is exactly the list `python3 -m lib.siteschema`
    prints, and nobody has to reconcile two vocabularies.
    """
    prov = (site or {}).get("provenance") or {}
    want = declared(job)
    out = []
    for path in sorted(prov):
        section = path.split(".")[0]
        if section not in want:
            continue
        source = _effective_source(prov, path)
        if source not in SOFT_SOURCES:
            continue
        out.append({"path": path, "source": source,
                    "fingerprint": fingerprint(site, path, source),
                    "note": (prov[path] or {}).get("note") or ""})
    return out


def _is_index(part):
    return part.lstrip("-").isdigit()


def group(paths):
    """Collapse list indices so fourteen trees are one line, not fourteen.

    `features.trees.0.height` and `features.trees.11.height` become
    `features.trees.*.height`, which is a pattern an all-clear entry can be
    written against. Nothing else is collapsed: a bed called `g02` is a name,
    not an index, and folding names together would let one reason quietly cover
    two unrelated things.
    """
    buckets = {}
    for path in paths:
        pattern = ".".join("*" if _is_index(p) else p for p in path.split("."))
        buckets.setdefault(pattern, []).append(path)
    return [(pattern, sorted(members))
            for pattern, members in sorted(buckets.items())]


# ---------------------------------------------------------------------- the CLI

def report(job=None):
    from . import doubts

    jobs = [job] if job else sorted(doubts.JOBS)
    for j in jobs:
        spec = JOB_INPUTS.get(j)
        if not spec:
            print(f"{j}: not in JOB_INPUTS")
            continue
        print(f"\n{j} — {', '.join(spec['sections'])}")
        for line in _wrap(spec["why"], 72):
            print(f"    {line}")
        if job:
            print()
            for section, (module, where) in sorted(derive(j).items()):
                print(f"    site[{section!r}]".ljust(36)
                      + f"lib.{module}: {where}")


def _wrap(text, width):
    from .vision import _wrap as w
    return w(str(text), width)


def main():
    args = [a for a in sys.argv[1:]]
    if "--drift" in args:
        problems = drift()
        if not problems:
            print("the declared input map matches what the jobs read")
            return
        print("the declared input map has drifted from the source:\n")
        for p in problems:
            print(f"  {p}")
        sys.exit(1)

    if args and not args[0].startswith("-"):
        if args[0] in JOB_INPUTS:
            report(args[0])
        else:
            # a slug, then: show what an all-clear would have to answer for
            site = yards.load(args[0], "site.json") or {}
            for j in sorted(JOB_INPUTS):
                soft = soft_inputs(site, j)
                print(f"{j:10s} {len(soft):3d} assumed or reported input"
                      f"{'s' if len(soft) != 1 else ''}")
        return

    report()
    print()
    problems = drift()
    print("drift: " + ("none" if not problems else f"{len(problems)} problems"))
    for p in problems:
        print(f"  {p}")


if __name__ == "__main__":
    main()
