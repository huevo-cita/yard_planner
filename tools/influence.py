#!/usr/bin/env python3
"""Which numbers in a yard actually carry weight, determined rather than asserted.

    python3 tools/influence.py <slug>                  the four quadrants
    python3 tools/influence.py <slug> --claims         only the unbacked claims
    python3 tools/influence.py <slug> --sensitivity    add perturbation (slow)
    python3 tools/influence.py <slug> --targets        the load-bearing paths,
                                                       one per line, for recompute
    python3 tools/influence.py <slug> --json

Why this exists
---------------
Auditing "the load-bearing numbers" is only worth something if that set was
established rather than nominated by whoever happened to be reading. On this
yard it was nominated, and the value that did the most damage was not on the
list: `zones.front_bed.note = "sunniest ground on the lot"`. No job reads that
string. Nothing could have recomputed it, because there was nothing to recompute
it against. It nonetheless moved a planting decision, because a person read it
and believed it.

So this runs before the recompute pass and answers three questions separately,
because the findings are where the answers disagree:

**Code-reachable.** Does a job actually read this path? `lib.inputs` already
recovers that from source by static analysis, at top-level section granularity.
This pushes the same idea down to leaf paths, and closes one of the blind spots
`lib.inputs` names in its own docstring: it follows a record through container
iteration, so `for key, spec in site["zones"].items(): spec.get("x")` is
recognised as a read of `zones.*.x`. That distinction is the whole point here.
Without it every path under `zones` reads as consumed, including the note, and
the tool would agree with the mistake it was built to find.

**Prose-reachable.** Is the value quoted or relied on in the yard's own
documents and doubt cards? That is, do the humans and the agents believe it,
whatever the code does.

**Sensitive.** Perturb it and measure how far the answers move, through
`gaps.light_spread` — the same machinery `lib.doubts --price` and `lib.gaps`
use, so there is one arguable exchange rate rather than a second one drifting
alongside.

The quadrants, and why three of them are findings
-------------------------------------------------
    prose-reachable, not code-reachable   believed, never computed, never
                                          checked by anything. The front_bed
                                          class. Printed first.
    code-reachable and sensitive          the real load-bearing set. This is
                                          what `recompute.py` audits.
    code-reachable, insensitive           safe to leave alone. A doubt card
                                          about one of these is noise crowding
                                          out a live one.
    neither                               dead weight somebody maintains by
                                          hand.

The unbacked-claim sweep
------------------------
Printed ahead of the quadrants, because it is the sharpest version of the
finding. A free-text field in `site.json` whose content makes a factual claim,
carrying no provenance entry, is an assertion nothing in the system can check
and nothing in the system will ever question. Claims are sorted by how checkable
they are:

    arithmetic   states its own working: `44.5 x 105 / 144`. recompute.py can
                 re-multiply it, and does.
    measurement  a number with a unit. Checkable against the model or the tape.
    judgement    an evaluative claim with no number: "sunniest ground on the
                 lot". **Uncheckable by construction.** Nothing can falsify it
                 except a person going outside. This is the dangerous class and
                 it sorts to the top.

What this honestly cannot do
----------------------------
Reachability is an over-approximation in the safe direction: a read that cannot
be traced is reported as a weaker grade rather than as absent, so the tool
prefers claiming something is read to claiming nothing reads it. The evidence
for each grade is printed — module and line — so a `by-key` grade can be
dismissed by eye when the hit is obviously unrelated, which is common: `note` is
read off tasks in `lib.week` and off prices in `lib.bom`, and neither has
anything to do with a zone note.

Sensitivity is only as good as the perturbation range, and the range is itself
an assumption. Ranges come from a doubt card's own `probe` values where one
exists and are marked `assumed range` where they do not. It only moves light:
a value that changes a price or a date and not a sun hour reads as insensitive
here, which is a real hole and the reason `--sensitivity` is off by default
rather than treated as the last word.

Prose-reachability is string matching, so it misses a paraphrase and
occasionally catches a coincidence. Numbers too short to be distinctive are
reported as `too common to match` rather than as absent, because "6 does not
appear in the plan" would be a lie.

And nothing here finds a number that was load-bearing for a decision somebody
made silently and never wrote down. That residual is real, and it is the whole
argument for writing decisions down.

Scope: `site.json`, because that is the file carrying provenance and the file
`lib.inputs` can reason about. `design.json` and `conditions.json` are audited
by `recompute.py` instead. Read-only.
"""
import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from lib import inputs, siteschema, yards  # noqa: E402

MISSING = object()

# Free text that makes a claim. Split by how checkable the claim is, because
# that ordering is the useful part: an arithmetic claim is a job for recompute,
# and a judgement claim can only ever be settled by somebody going outside.
ARITHMETIC = re.compile(r"\d+(?:\.\d+)?\s*(?:x|×|\*|/)\s*\d+(?:\.\d+)?|=\s*\d")
MEASUREMENT = re.compile(
    r"\d+(?:\.\d+)?\s*(?:h\b|hr\b|hrs\b|hours?\b|in\b|inch(?:es)?\b|ft\b|feet\b"
    r"|foot\b|sq\.? ?ft|cu\.? ?ft|%|deg\b|°)", re.I)
JUDGEMENT = re.compile(
    r"\b(sunniest|shadiest|hottest|coldest|driest|dampest|wettest|best|worst"
    r"|friendliest|healthiest|easiest|hardest|ideal|perfect|full sun|part shade"
    r"|part sun|deep shade|full shade|sunny|shady|the most|the least|the only"
    r"|never|always)\b", re.I)

# Documents and records where a value being quoted means somebody is relying on
# it. The skills are excluded on purpose: they are yard-agnostic templates, so a
# number of theirs matching a number of this yard's is a coincidence, and
# feeding coincidences into a list of "things people believe" devalues the list.
PROSE_FILES = ("PLAN.md", "SCHEDULE.md", "SOWING-CALENDAR.md", "SOURCING.md",
               "SITE-WALK.md", "CALENDAR.md", "doubts.json", "changelog.json",
               "design.json", "tasks.json", "niches.json", "coverage.json")

# Sections whose geometry the shade model casts rays at. Perturbing anything
# else and measuring light would be a slow way to learn nothing.
GEOMETRIC = ("obstructions", "features", "boundary", "frame")


# ------------------------------------------------------- what the code reads

def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and \
        isinstance(node.value, str) else None


class _PathReads(ast.NodeVisitor):
    """Leaf-path patterns one module reads out of a site record.

    Patterns use `*` for a segment the scan could not pin down — a zone reached
    by iterating, a tree reached by index. `zones.*.x` covers `zones.bed_g02.x`
    and says nothing about `zones.bed_g02.note`, which is the discrimination
    this whole file turns on.
    """

    def __init__(self, tree):
        # name (as unparsed source) -> the dotted prefix of the record it holds.
        # The root record is the empty prefix.
        self.aliases = self._seed()
        self.patterns = {}          # pattern -> the line that reads it
        self.keys = {}              # any dict-key literal -> line number
        self._learn(tree)

    def _seed(self):
        """The names known to hold the record before anything is followed.

        A subclass pointed at a different record overrides this and learns its
        roots from the loader calls instead — see `_FileReads`.
        """
        return {a: "" for a in inputs.SITE_ALIASES}

    # ---- learning which local names hold a piece of the record

    def _learn(self, tree):
        """Follow the record through assignment and iteration, to a fixed point.

        `lib.inputs` follows plain assignment only, and says so. Iteration is
        added here because it is how every job actually walks the record, and
        without it a per-zone read is invisible.
        """
        for _ in range(6):
            before = len(self.aliases)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.NamedExpr)):
                    self._learn_assign(node)
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    self._learn_for(node)
                elif isinstance(node, (ast.comprehension,)):
                    self._bind(node.target, self._iterated(node.iter))
            if len(self.aliases) == before:
                return

    def _learn_assign(self, node):
        value = node.value
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
            value = value.values[0]
        prefix = self._resolve(value)
        if prefix is None:
            return
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target])
        for t in targets:
            self._bind(t, prefix)

    def _learn_for(self, node):
        prefix = self._iterated(node.iter)
        if prefix is None:
            return
        target = node.target
        if isinstance(target, ast.Tuple):
            # `for key, spec in site["zones"].items()` — the value is the record
            for elt in target.elts[1:]:
                self._bind(elt, prefix)
        else:
            self._bind(target, prefix)

    def _iterated(self, node):
        """The prefix of a record member produced by iterating `node`.

        `site["zones"].items()`, `.values()`, or the container itself. Iterating
        a dict's keys yields strings rather than records, so this
        over-approximates; the cost is a spurious `zones.*` read pattern and the
        benefit is never missing a real one.
        """
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("items", "values"):
            inner = self._resolve(node.func.value)
        else:
            inner = self._resolve(node)
        if inner is None:
            return None
        return f"{inner}.*" if inner else "*"

    def _bind(self, target, prefix):
        if isinstance(target, (ast.Name, ast.Attribute)):
            name = inputs._unwrap(ast.unparse(target))
            if self.aliases.get(name) != prefix:
                self.aliases.setdefault(name, prefix)

    # ---- resolving an expression to a dotted prefix

    def _resolve(self, node):
        """The dotted prefix this expression reads, or None if it is not a record.

        Returns "" for the record itself, so a caller can tell "this is the root
        record" from "this is not a record at all".
        """
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            node = node.values[0]
        if isinstance(node, (ast.Name, ast.Attribute)):
            return self.aliases.get(inputs._unwrap(ast.unparse(node)))
        if isinstance(node, ast.Subscript):
            base = self._resolve(node.value)
            if base is None:
                return None
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return self._join(base, key.value)
            if isinstance(key, ast.Constant) and isinstance(key.value, int):
                return self._join(base, str(key.value))
            return self._join(base, "*")
        if isinstance(node, ast.Call):
            f = node.func
            if not isinstance(f, ast.Attribute):
                return None
            if f.attr in ("get", "setdefault") and node.args:
                base = self._resolve(f.value)
                if base is None:
                    return None
                s = _const_str(node.args[0])
                return self._join(base, s if s is not None else "*")
            if f.attr in ("get_path", "set_path", "provenance_of",
                          "set_provenance") and len(node.args) >= 2:
                base = self._resolve(node.args[0])
                s = _const_str(node.args[1])
                if base is None or s is None:
                    return None
                return self._join(base, s)
            if f.attr in ("items", "values", "keys", "copy"):
                return self._resolve(f.value)
        return None

    @staticmethod
    def _join(prefix, part):
        return f"{prefix}.{part}" if prefix else part

    # ---- collecting

    def _record(self, node):
        prefix = self._resolve(node)
        if prefix:
            top = prefix.split(".")[0]
            if top not in inputs.META_SECTIONS:
                self.patterns.setdefault(prefix, node.lineno)

    def visit_Subscript(self, node):
        self._record(node)
        s = _const_str(node.slice)
        if s:
            self.keys.setdefault(s, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node):
        self._record(node)
        f = node.func
        if isinstance(f, ast.Attribute) and \
                f.attr in ("get", "setdefault") and node.args:
            s = _const_str(node.args[0])
            if s:
                self.keys.setdefault(s, node.lineno)
        self.generic_visit(node)


class _FileReads(_PathReads):
    """Leaf-path patterns one module reads out of one named yard file.

    Same machinery as `_PathReads`, pointed at a different record. Two
    differences, and both matter for the question this is asked:

    `_PathReads` starts from `inputs.SITE_ALIASES` — the names a *site* record
    travels under. A design record travels under `design`, `dsn`, `d`, and
    nobody is going to keep a list of those current. So this starts from
    nothing and learns its roots from the loader calls instead: a name bound to
    `yards.load(slug, "design.json")` holds a design record, whatever it is
    called. Everything downstream is `_PathReads`'s own alias-and-iteration
    following.

    And writes are not reads. `_PathReads` records `site["zones"] = {}` and
    `siteschema.set_path(site, path, v)` as reads, which is harmless where the
    question is "does any job touch this" and fatal here: a key a module
    *creates* would read as a key it consumes and nothing writes.
    """

    def __init__(self, tree, filename, module, roots=()):
        self.filename = filename
        self.module = module
        self.roots = tuple(roots)
        super().__init__(tree)
        self._poison(tree)

    def _seed(self):
        return {name: "" for name in self.roots}

    def _poison(self, tree):
        """Drop any name a scope binds to two different things.

        `lib.bom` binds `p` to a design plant and, fifty lines later in the same
        function, to a row out of its own price table. First-binding-wins then
        reads the price table's keys as if they were plant fields, which is a
        fabricated finding rather than a loose one. A name that is not one thing
        throughout its scope is not evidence about anything, so it goes.

        This makes the scan miss reads, which is the safe direction: a missed
        read is a finding that never appears, and an invented one is a person
        sent to look at working code.
        """
        bad = set()
        for node in ast.walk(tree):
            pairs = []
            if isinstance(node, (ast.Assign, ast.NamedExpr)):
                value = node.value
                if isinstance(value, ast.BoolOp) and \
                        isinstance(value.op, ast.Or):
                    value = value.values[0]
                prefix = self._resolve(value)
                pairs = [(t, prefix) for t in
                         (node.targets if isinstance(node, ast.Assign)
                          else [node.target])]
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                prefix = self._iterated(node.iter)
                target = node.target
                pairs = ([(e, prefix) for e in target.elts[1:]]
                         if isinstance(target, ast.Tuple)
                         else [(target, prefix)])
            elif isinstance(node, ast.comprehension):
                pairs = [(node.target, self._iterated(node.iter))]
            for target, prefix in pairs:
                if not isinstance(target, (ast.Name, ast.Attribute)):
                    continue
                name = inputs._unwrap(ast.unparse(target))
                if name in self.aliases and self.aliases[name] != prefix:
                    bad.add(name)
        for name in bad:
            self.aliases.pop(name, None)

    def _is_root(self, node):
        """Does this call load the file being asked about?"""
        if not isinstance(node, ast.Call):
            return False
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else \
            (f.id if isinstance(f, ast.Name) else None)
        if name is None:
            return False
        if name == "load":
            if len(node.args) >= 2 and _const_str(node.args[1]):
                return _const_str(node.args[1]) == self.filename
            # `week.load(slug)` from outside, `load(slug)` from within week.py
            owner = (inputs._unwrap(ast.unparse(f.value))
                     if isinstance(f, ast.Attribute) else self.module)
            return MODULE_LOADERS.get(owner) == self.filename
        return DEDICATED.get(name) == self.filename

    def _resolve(self, node):
        if self._is_root(node):
            return ""
        return super()._resolve(node)

    def _record(self, node):
        prefix = self._resolve(node)
        if prefix:
            self.patterns.setdefault(prefix, node.lineno)

    def visit_Subscript(self, node):
        if isinstance(getattr(node, "ctx", None), ast.Store):
            self.generic_visit(node)
            return
        super().visit_Subscript(node)

    def visit_Call(self, node):
        f = node.func
        setter = isinstance(f, ast.Attribute) and \
            f.attr in ("set_path", "set_provenance", "setdefault", "pop")
        if not setter:
            self._record(node)
        self.generic_visit(node)


#: Loaders whose name alone says which file comes back.
DEDICATED = {"load_conditions": "conditions.json",
             "load_vision": "vision.json",
             "load_site": "site.json"}

#: Modules with a `load(slug)` of their own, and the file it returns.
MODULE_LOADERS = {"week": "tasks.json", "doubts": "doubts.json",
                  "changelog": "changelog.json", "niches": "niches.json",
                  "sourcing": "sourcing.json", "siteschema": "site.json"}

#: The yard records this asks about. Each is a file some module reads by name,
#: so a key read against one either exists in it or does not.
YARD_FILES = ("site.json", "design.json", "conditions.json", "tasks.json",
              "vision.json", "niches.json", "sun-hours.json", "coverage.json",
              "sourcing.json", "doubts.json", "changelog.json")


def _scopes(tree):
    """Each function, plus the module body with the functions taken out.

    Aliases are learned from names, and a name is only that name inside the
    function that binds it. Scanning a module as one tree makes every `site` the
    same `site`, and `lib.gaps.report` rebinds `site` to a slice of
    `coverage.json` eleven lines after another function bound it to the site
    record. First-binding-wins then attributes the second function's reads to
    the first function's record, which is not an over-approximation — it is a
    fabricated finding, and module-wide scanning produced about ninety of them.

    Nested definitions are scanned again as part of their parent, which
    double-counts a pattern and cannot invent one.
    """
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    bare = ast.Module(
        body=[s for s in tree.body
              if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef))],
        type_ignores=[])
    return [bare] + funcs


def file_reads(filename):
    """Every read pattern any module in `lib/` makes against one yard file.

    Each pattern comes back with every site that reads it, because the first one
    is often the least interesting.

    A site is only seen where the record is bound to a name *in that scope*. An
    accessor taking the record as a parameter — `conditions.on_hand(cond, item)`
    — says nothing about what it holds, so its reads are invisible here.
    Seeding parameter names the module binds from a loader elsewhere was tried
    and abandoned: it found the accessor and, with it, forty-five findings out
    of `lib.siteschema` and `lib.drawsite`, which read parameters holding dicts
    those modules had just built themselves. The key still surfaces from
    wherever the record *is* bound; only the sharpest line number is lost.
    """
    out = {}
    for name in sorted(os.listdir(os.path.join(ROOT, "lib"))):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        module = name[:-3]
        path = os.path.join(ROOT, "lib", name)
        with open(path) as fh:
            tree = ast.parse(fh.read(), filename=path)
        for scope in _scopes(tree):
            v = _FileReads(scope, filename, module)
            v.visit(scope)
            for pattern, line in v.patterns.items():
                sites = out.setdefault(pattern, [])
                if (module, line) not in sites:
                    sites.append((module, line))
    return {p: sorted(s) for p, s in out.items()}


def _containers(data, parts):
    """Every dict or list the parent path of a pattern reaches in this record."""
    nodes = [data]
    for part in parts[:-1]:
        nxt = []
        for node in nodes:
            if part == "*":
                members = (list(node.values()) if isinstance(node, dict)
                           else node if isinstance(node, list) else [])
                nxt += [m for m in members if isinstance(m, (dict, list))]
            elif isinstance(node, dict) and part in node:
                nxt.append(node[part])
            elif isinstance(node, list) and part.lstrip("-").isdigit():
                i = int(part)
                if -len(node) <= i < len(node):
                    nxt.append(node[i])
        nodes = [n for n in nxt if isinstance(n, (dict, list))]
        if not nodes:
            return []
    return nodes


def unwritten(slug, files=YARD_FILES):
    """Keys a module reads off a yard file that the file never writes.

    Two bugs of exactly this shape landed on one yard in one day. `lib.niches`
    read `overhang_ft` off `niches.json` and `derive` never wrote it, so every
    bed was budgeted at zero apron and one bed's declared fourteen inches was
    silently ignored. `lib.schedule` read `hardscape["name"]` against a design
    that writes `item`, and four of seventeen build archetypes could not fire.
    Both are static, both are cheap, and neither was visible to any check.

    What comes back is a pattern, where it is read, how many objects the pattern
    reaches, and the sibling keys those objects do carry — because the sibling
    list is usually the answer. `hardscape.*.name` over thirteen entries whose
    siblings are `item, zone, count, cost_usd, note` names its own fix.

    What this does NOT distinguish, and the report says so: a missing writer
    from a reader with a working fallback. `plants.*.needs_support` is read by
    `lib.schedule` and written by no plant, and the guard behind it also reads
    `layer` and the plant's name, so the archetype fires anyway. Only a person
    can tell those apart, which is why this reports and files nothing.

    And the honest limit, which a previous audit stated better than this
    docstring can: this would have caught both of the bugs above outright, and
    would not have caught the one alongside them. `usable_depth_ft` was written,
    read, and correct — the failure was that nothing multiplied it by anything.
    Two readers agreeing because they share an assumption is not a question
    presence can answer, and no cheap general check for it exists.
    """
    out = []
    for filename in files:
        data = yards.load(slug, filename)
        if not isinstance(data, (dict, list)):
            continue
        for pattern, sites in sorted(file_reads(filename).items()):
            parts = pattern.split(".")
            leaf = parts[-1]
            if leaf == "*" or leaf.lstrip("-").isdigit():
                continue        # names no key of its own
            holders = [n for n in _containers(data, parts)
                       if isinstance(n, dict)]
            if not holders or any(leaf in h for h in holders):
                continue
            siblings = sorted({k for h in holders for k in h})
            out.append({
                "file": filename, "pattern": pattern, "leaf": leaf,
                "read_at": [f"lib.{m}:{ln}" for m, ln in sites],
                "reaches": len(holders),
                "siblings": siblings[:12],
                "more_siblings": max(0, len(siblings) - 12),
            })
    out.sort(key=lambda f: (-f["reaches"], f["file"], f["pattern"]))
    return out


def report_unwritten(rows, slug):
    print("=" * 78)
    print(f"READ BY A MODULE, WRITTEN BY NOTHING  ({len(rows)})")
    print("=" * 78)
    for line in _wrap(
            "A key some module in lib/ reads off one of this yard's records, "
            "which no object in that record carries. Either the writer is "
            "missing or the reader has a fallback, and this cannot tell those "
            "apart — the sibling keys are printed because they are usually the "
            "answer. Nothing here is filed.", 74):
        print(f"  {line}")
    print()
    if not rows:
        print("  every key any module reads off this yard's records is in "
              "them.\n")
        return
    for r in rows:
        print(f"  {r['file']}  {r['pattern']}")
        for line in _wrap(
                "read in " + ", ".join(r["read_at"]) + f", over {r['reaches']} "
                f"object{'s' if r['reaches'] != 1 else ''} that do not carry "
                f"{r['leaf']!r}", 66):
            print(f"      {line}")
        sibs = ", ".join(r["siblings"])
        if r["more_siblings"]:
            sibs += f", and {r['more_siblings']} more"
        for i, line in enumerate(_wrap("they carry: " + sibs, 66)):
            print(f"      {line}")
    print()


def code_reads():
    """Read patterns and key literals per job, across each job's import closure.

    Patterns are attributed to the job whose closure contains the read; key
    literals are collected repo-wide, because the whole use of a key literal is
    as the weaker fallback when no pattern matched.
    """
    per_job, keys = {}, {}
    for job in sorted(inputs.JOB_INPUTS):
        pats = {}
        for module, _ in inputs.closure(job):
            path = os.path.join(ROOT, "lib", module + ".py")
            with open(path) as fh:
                tree = ast.parse(fh.read(), filename=path)
            v = _PathReads(tree)
            v.visit(tree)
            for pattern, line in v.patterns.items():
                pats.setdefault(pattern, (module, line))
            for key, line in v.keys.items():
                keys.setdefault(key, (module, line))
        per_job[job] = pats
    return per_job, keys


def covers(pattern, path):
    """Does a read pattern reach this leaf path? Ancestor-or-self, `*` wild."""
    p, q = pattern.split("."), path.split(".")
    if len(p) > len(q):
        return False
    return all(a == "*" or a == b for a, b in zip(p, q))


def _names_leaf(pattern, parts):
    """Does this read pattern reach the leaf itself, rather than its container?

    The pattern has to be as deep as the path, and its last segment has to
    actually name the leaf. A wildcard tail — `z.get(f"no_{item}")`, or a key
    held in a variable — names nothing, and counting it would grade every key
    in the container as consumed.

    The exception is a list index. `spec["x"][i]` genuinely reaches every
    element of `x`, so a wildcard tail against a numeric segment is a real read.
    """
    p = pattern.split(".")
    if len(p) != len(parts):
        return False
    if p[-1] != "*":
        return True
    return parts[-1].lstrip("-").isdigit()


def grade(path, per_job, keys):
    """How strongly the code can be shown to consume this leaf.

    named   code names this leaf key on a path that reaches it, so it is
            definitely consumed
    maybe   the container is read wholesale, or the key is read as a literal
            somewhere else, and the scan cannot tell whether this leaf is ever
            looked at
    no      the key never appears as a key literal anywhere in lib/, so nothing
            can be reading it

    The distinction between `named` and `maybe` is the one that matters, and it
    is why this file exists rather than deferring to `lib.inputs`. Every leaf
    under `zones` is reached by `site["zones"]`, so treating a wholesale
    container read as proof would grade `zones.front_bed.note` as consumed and
    the tool would agree with the mistake it was built to find.
    """
    parts = path.split(".")
    named, subtree = [], []
    for job, pats in per_job.items():
        if parts[0] not in inputs.declared(job):
            continue
        for pattern, (module, line) in pats.items():
            if not covers(pattern, path):
                continue
            hit = (job, pattern, module, line)
            (named if _names_leaf(pattern, parts) else subtree).append(hit)
    if named:
        named.sort(key=lambda h: h[1].count("*"))
        return "named", named
    leaf = path.split(".")[-1]
    evidence = []
    if leaf in keys:
        module, line = keys[leaf]
        evidence.append((None, f"the key {leaf!r} read elsewhere", module, line))
    if subtree:
        subtree.sort(key=lambda h: -len(h[1].split(".")))
        job, pattern, module, line = subtree[0]
        evidence.append((job, f"`{pattern}` taken wholesale", module, line))
    if evidence:
        return "maybe", evidence
    return "no", []


# ------------------------------------------------------ what the prose reads

def prose_corpus(slug):
    """The documents and records, plus their lowercased and shingled forms.

    Precomputed once. Shingling a 9,000-word plan for each of a thousand values
    is the difference between this tool being cheap enough to run before every
    audit and being something nobody runs.
    """
    out = {}
    d = yards.yard_dir(slug)
    for name in PROSE_FILES:
        p = os.path.join(d, name)
        if not os.path.exists(p):
            continue
        with open(p, errors="replace") as fh:
            text = fh.read()
        out[name] = {"text": text, "lower": text.lower(),
                     "shingles": _shingles(text)}
    return out


def _shingles(text, n=5):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))} \
        if len(words) >= n else ({" ".join(words)} if words else set())


def _digits(text):
    """The digits that carry information: no sign, no point, no padding zeros.

    This is what decides whether searching prose for a number means anything.
    `0.00` and `6` carry one or no digits and will match by accident in any
    document; `630.34` carries five and will not. Getting this wrong in the
    lax direction is worse than useless, because it manufactures evidence that
    somebody believes a value when all that happened was a collision.
    """
    return re.sub(r"[^0-9]", "", str(text)).strip("0")


def _number_forms(value, path):
    """Ways a number might legitimately be written down in prose.

    Includes the inches-to-feet conversion for geometry, because the record
    keeps inches and every document quotes feet, and a check that missed that
    would report the whole geometry as unbelieved.
    """
    candidates = {}
    v = float(value)
    if v == int(v):
        candidates[str(int(v))] = "as written"
    for fmt in ("%g", "%.1f", "%.2f"):
        candidates.setdefault(fmt % v, "as written")
    top = path.split(".")[0]
    if top in ("zones", "obstructions", "features", "boundary") and abs(v) >= 12:
        for fmt in ("%g", "%.1f", "%.2f"):
            candidates.setdefault(fmt % (v / 12.0), "converted to feet")
    return {form: how for form, how in candidates.items()
            if len(_digits(form)) >= 3}


def prose_hit(path, value, corpus):
    """Where this value is quoted, or why the question could not be answered."""
    if isinstance(value, bool) or value is None:
        return None, "not a quotable value"
    if isinstance(value, str):
        if len(value) < 12:
            return None, "too short to match"
        low = value.lower()
        for name, doc in corpus.items():
            if low in doc["lower"]:
                return (name, "verbatim"), None
        mine = _shingles(value)
        for name, doc in corpus.items():
            if mine & doc["shingles"]:
                return (name, "phrase from it"), None
        return None, None
    if isinstance(value, (int, float)):
        forms = _number_forms(value, path)
        if not forms:
            return None, "too common to match"
        for name, doc in corpus.items():
            for form in sorted(forms, key=len, reverse=True):
                if re.search(r"(?<![\d.])" + re.escape(form) + r"(?![\d])",
                             doc["text"]):
                    return (name, forms[form]), None
        return None, None
    return None, "not a quotable value"


# ------------------------------------------------------------- sensitivity

def sensitivity(site, path, value, probe_values=None, zone=None):
    """How far the yard's light moves when this number is perturbed.

    Straight through `gaps.light_spread`, which is what `lib.doubts --price`
    and `lib.gaps` both call, so the number here is comparable with the ones
    on the doubt board rather than a second opinion.
    """
    from lib import gaps
    if probe_values:
        values, basis = [float(v) for v in probe_values], "probe range"
    else:
        v = float(value)
        if v == 0:
            return None, "zero, so there is no proportional range to try"
        values, basis = [v * 0.8, v, v * 1.2], "assumed range, +/-20%"
    spread = gaps.light_spread(site, gaps._set_path(path), values, zone=zone)
    if spread is None:
        return None, "the model would not run across that range"
    return dict(spread, basis=basis), None


def _zone_of(path):
    parts = path.split(".")
    if parts[0] == "zones" and len(parts) >= 2:
        return parts[1]
    return None


def _probe_ranges(slug):
    """Perturbation ranges already argued for on the doubt board, by path."""
    board = yards.load(slug, "doubts.json") or {}
    out = {}
    for c in board.get("cards", []):
        p = c.get("probe") or {}
        if p.get("path") and p.get("values"):
            out[p["path"]] = (p["values"], p.get("zone"))
        if p.get("trees_field") and p.get("values"):
            out["features.trees.*." + p["trees_field"]] = (p["values"],
                                                           p.get("zone"))
    return out


# ------------------------------------------------------------ the enumeration

def leaves(site):
    """Every leaf path in the record, skipping the bookkeeping sections."""
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}.{i}")
        else:
            if path and path.split(".")[0] not in inputs.META_SECTIONS:
                out.append(path)

    walk(site, "")
    return out


def claim_kind(text):
    if ARITHMETIC.search(text):
        return "arithmetic"
    if MEASUREMENT.search(text):
        return "measurement"
    if JUDGEMENT.search(text):
        return "judgement"
    return None


def analyse(slug, do_sensitivity=False, limit=12):
    site = yards.load(slug, "site.json")
    if site is None:
        raise SystemExit(f"{slug} has no site.json")
    prov = (site or {}).get("provenance") or {}
    per_job, keys = code_reads()
    corpus = prose_corpus(slug)
    probes = _probe_ranges(slug)

    rows = []
    for path in leaves(site):
        value = siteschema.get_path(site, path, MISSING)
        if value is MISSING:
            continue
        g, hits = grade(path, per_job, keys)
        where, why_not = prose_hit(path, value, corpus)
        source = inputs._effective_source(prov, path)
        exact = path in prov
        rows.append({
            "path": path,
            "value": value,
            "type": type(value).__name__,
            "code": g,
            "code_evidence": hits[:1],
            "jobs": sorted({h[0] for h in hits if h[0]}),
            "prose": where,
            "prose_note": why_not,
            "provenance": source,
            "provenance_exact": exact,
            "claim": (claim_kind(value) if isinstance(value, str) else None),
            "sensitivity": None,
            "sensitivity_note": "not probed",
        })

    if do_sensitivity:
        probed = 0
        for r in rows:
            if probed >= limit:
                r["sensitivity_note"] = f"skipped, past the --limit of {limit}"
                continue
            if r["type"] not in ("int", "float") or r["code"] != "named":
                continue
            if r["path"].split(".")[0] not in GEOMETRIC:
                r["sensitivity_note"] = ("not geometry, so light is the wrong "
                                         "yardstick for it")
                continue
            pv, zone = None, _zone_of(r["path"])
            for pattern, (values, pzone) in probes.items():
                if covers(pattern, r["path"]):
                    pv, zone = values, (pzone or zone)
                    break
            spread, note = sensitivity(site, r["path"], r["value"], pv, zone)
            r["sensitivity"], r["sensitivity_note"] = spread, note
            probed += 1
    return rows


# ----------------------------------------------------------------- reporting

def quadrant(r):
    code = r["code"] == "named"
    prose = r["prose"] is not None
    if prose and not code:
        return "believed-but-uncomputed"
    if code and prose:
        return "load-bearing"
    if code:
        return "computed-but-unquoted"
    return "neither"


def _fmt(value, width=44):
    s = json.dumps(value) if not isinstance(value, str) else value
    s = " ".join(str(s).split())
    return s if len(s) <= width else s[:width - 1] + "…"


def report_claims(rows):
    """Free-text claims in the record, worst-checkable first."""
    order = {"judgement": 0, "measurement": 1, "arithmetic": 2}
    claims = sorted((r for r in rows if r["claim"]),
                    key=lambda r: (order[r["claim"]], r["path"]))
    print("=" * 78)
    print("FREE-TEXT CLAIMS IN site.json")
    print("=" * 78)
    if not claims:
        print("  none.\n")
        return
    print("  A string field asserting a fact. `judgement` first: it carries no")
    print("  number, so nothing can falsify it except somebody going outside.")
    print("  `unbacked` means no provenance entry covers it, at that path or")
    print("  any parent.\n")
    for r in claims:
        backed = "backed by " + r["provenance"] if r["provenance"] \
            else "UNBACKED"
        print(f"  [{r['claim']:11s}] {r['path']}")
        print(f"      {_fmt(r['value'], 66)}")
        quoted = f"quoted in {r['prose'][0]}" if r["prose"] else "not quoted"
        print(f"      {backed}, read by code: {r['code']}, {quoted}")
    print()


def report_quadrants(rows, verbose=False):
    buckets = {}
    for r in rows:
        buckets.setdefault(quadrant(r), []).append(r)

    titles = [
        ("believed-but-uncomputed",
         "BELIEVED BUT NEVER COMPUTED",
         "Quoted in the yard's own documents, and no job reads it. Nothing has "
         "ever checked these, and nothing can: there is no computation to "
         "compare them against. This is the quadrant the front_bed note was "
         "in."),
        ("load-bearing",
         "LOAD-BEARING",
         "Read by a job and quoted by a person. recompute.py audits these."),
        ("computed-but-unquoted",
         "COMPUTED, NOT QUOTED",
         "A job reads it; no document leans on it. Wrong here is still wrong, "
         "but it moves an output rather than a belief."),
        ("neither",
         "NEITHER",
         "No job reads it and no document quotes it. Either dead weight kept "
         "up by hand, or reached by code this scan cannot see — check the "
         "grade before deleting anything."),
    ]
    for key, title, why in titles:
        group = buckets.get(key, [])
        print("=" * 78)
        print(f"{title}  ({len(group)})")
        print("=" * 78)
        for line in _wrap(why, 74):
            print(f"  {line}")
        print()
        if not group:
            print("  none.\n")
            continue
        shown = group if (verbose or len(group) <= 18) else group[:18]
        for r in sorted(shown, key=lambda r: r["path"]):
            print(f"  {r['path']:<46} {_fmt(r['value'], 26)}")
            bits = [f"code {r['code']}"]
            if r["jobs"]:
                bits.append("for " + ",".join(r["jobs"]))
            if r["code_evidence"]:
                _, pat, module, line = r["code_evidence"][0]
                bits.append(f"lib.{module}:{line} via `{pat}`")
            if r["prose"]:
                bits.append(f"quoted in {r['prose'][0]} ({r['prose'][1]})")
            elif r["prose_note"]:
                bits.append(r["prose_note"])
            bits.append("provenance " + (r["provenance"] or "NONE"))
            s = r["sensitivity"]
            if s:
                bits.append(f"moves {s['spread_hours']:.2f} h/day over "
                            f"{s['measured_over']} ({s['basis']})")
            print(f"      {'; '.join(bits)}")
        if len(group) > len(shown):
            print(f"      ... and {len(group) - len(shown)} more "
                  f"(--verbose for all)")
        print()


def targets(rows):
    """The paths recompute.py should audit: anything code reads or prose quotes.

    The union rather than the intersection, deliberately. A value a job reads is
    load-bearing for an output; a value a document quotes is load-bearing for a
    decision; and the second is the one that went wrong here.
    """
    return [r["path"] for r in sorted(rows, key=lambda r: r["path"])
            if r["code"] == "named" or r["prose"] is not None]


def _wrap(text, width):
    out, line = [], ""
    for word in str(text).split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--claims", action="store_true",
                    help="only the free-text claim sweep")
    ap.add_argument("--sensitivity", action="store_true",
                    help="perturb the geometry and measure the light. Slow: "
                         "three shade-model runs per value")
    ap.add_argument("--limit", type=int, default=12,
                    help="cap on values perturbed (default 12)")
    ap.add_argument("--targets", action="store_true",
                    help="the load-bearing paths, one per line")
    ap.add_argument("--unwritten", action="store_true",
                    help="keys a module reads off a yard record that no "
                         "object in that record carries. Exits non-zero on "
                         "findings")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true",
                    help="every row, not the first 18 of each quadrant")
    args = ap.parse_args()

    if args.unwritten:
        gone = unwritten(args.slug)
        stamp = yards.sandbox_stamp(args.slug)
        if stamp:
            print(f"** {stamp}. A rehearsal copy, not the plan. **\n")
        if args.json:
            print(json.dumps({"yard": args.slug, "unwritten": gone}, indent=2,
                             default=str))
        else:
            print(f"{args.slug} — lib/ against this yard's records\n")
            report_unwritten(gone, args.slug)
        raise SystemExit(1 if gone else 0)

    rows = analyse(args.slug, do_sensitivity=args.sensitivity,
                   limit=args.limit)

    if args.targets:
        for p in targets(rows):
            print(p)
        return
    if args.json:
        print(json.dumps({"yard": args.slug, "rows": rows,
                          "targets": targets(rows)}, indent=2, default=str))
        return

    stamp = yards.sandbox_stamp(args.slug)
    if stamp:
        print(f"** {stamp}. A rehearsal copy, not the plan. **\n")
    print(f"{args.slug} — {len(rows)} values in site.json\n")
    report_claims(rows)
    if not args.claims:
        report_quadrants(rows, verbose=args.verbose)
        unbacked = [r for r in rows
                    if r["claim"] == "judgement" and not r["provenance"]]
        believed = [r for r in rows if quadrant(r) == "believed-but-uncomputed"]
        print(f"{len(believed)} value{'s' if len(believed) != 1 else ''} "
              f"believed but never computed; "
              f"{len(unbacked)} unbacked judgement claim"
              f"{'s' if len(unbacked) != 1 else ''}.")
        print(f"\nrecompute targets: python3 tools/influence.py {args.slug} "
              f"--targets")


if __name__ == "__main__":
    main()
