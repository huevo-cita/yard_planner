# Working in this repo

The engine is `lib/`, one module per job, each runnable as `python3 -m lib.<name>`
or through `./bin/yard <name>`. Per-yard facts live in the yard's own JSON files
and never in code. Every number carries provenance. `README.md` has the rest.

This file is about two specific failures, because both have happened over and
over. The first costs real money every time. The second costs the reader's
attention, every time the plan is opened, forever.

Both are the same bug: a sentence that should have gone into a file went into
prose instead, where nothing reads it and nothing acts on it.

# A doubt goes in a file

## The failure

The pattern goes like this. Work is going well. The next step is expensive — the
full sun model, a design rewrite, a bill of materials, a schedule. Just before
kicking it off, the assistant says something like:

> One caveat: I've assumed that west fence is solid board. Worth checking.

Then the run starts. Then someone checks the fence, it turns out to be open rail,
and the run is worthless. The model has to be stopped and re-run, the design
reworked, the plan redone.

The doubt was **correct** and it was **early**. That is the maddening part. The
only thing wrong was where it went: into prose, which nothing reads, instead of
into a file, which the gate reads.

## The rule

**If you are about to write a sentence hedging the inputs to an expensive job,
that sentence is a doubt card. File it before you run anything.**

The phrases that should trigger this, because they are the ones that actually get
used:

- "one caveat", "worth noting", "worth flagging", "one thing to watch"
- "I've assumed", "assuming", "taking it as", "on the assumption that"
- "I'm not certain", "not sure whether", "it's possible that", "this might be"
- "we could either ... or ...", "there's a choice here", "two options"
- "this may change", "if that turns out to be", "pending confirmation"
- "I read that as", "it looks like", "probably", "should be"

When one of those is about to describe an input to the sun model, the design, the
bed maps, the bill of materials or the schedule:

```bash
python3 -m lib.doubts <slug> --add "Is the west fence solid board or open rail?" \
    --kind fact --blocks sunmodel,design \
    --detail "the street photo predates the rebuild" \
    --how "stand at the west line and look" --effort "two minutes"
```

Then keep working. The card is not an interruption; it is a note that survives
the turn.

## Never file and run in the same turn

Filing a doubt and then immediately running the job it blocks is the same bug
with an extra step. If a doubt is worth writing down, it is worth settling or
consciously waiving before the expensive thing runs.

Concretely: a turn that files a card must end, or move on to settling it. It must
not go on to run `lib.sunmodel`, `lib.design`, `lib.drawbeds`, `lib.bom` or
`lib.schedule` on that yard.

## Settle it the cheap way first

Most doubts do not matter, and interrupting Casey over every one of them is how
the whole mechanism gets ignored within a week. So before escalating anything:

```bash
python3 -m lib.doubts <slug> --price
```

For any `fact` card carrying a `probe`, this re-runs the shade model across the
plausible range of the unknown and measures how far the answer actually moves. A
doubt that changes nothing settles itself as `probed-immaterial`, with the
measured spread recorded as the evidence. That is a real answer, not a shrug.

Give a `fact` card a probe wherever the unknown is a number in `site.json`:

```json
"probe": {"path": "obstructions.fences.0.height",
          "values": [36.0, 72.0, 96.0],
          "zone": "West bed"}
```

Use `zone` when the thing rules one bed rather than the yard. An awning over a
four-foot bed averages away to nothing measured over the whole yard and completely
governs the ground underneath it, and the honest number is the second one.

## Bring choices as choices

A `kind: choice` card is a decision that is not yours to make. Record the options
with their pros, cons and costs, then put them in front of the person as options —
not as prose, and not as a recommendation with the alternatives buried.

```bash
python3 -m lib.doubts <slug> --add "Bed against the house, or out in the open?" \
    --kind choice --blocks design,bom --decisions 3 \
    --option "against the house|shelter, reads as intentional|rain shadow, needs irrigation|about \$120 of drip" \
    --option "out in the open|gets real rain|exposed to wind|no extra cost"
```

Then record what they chose with `--settle <id> --answer "..." --by decided`.

## Batch at stage boundaries

Do not drip-feed doubts one at a time. Between stages — after the survey, after
conditions, after vision, before design — read the board out as a set, alongside
the ranked gap report:

```bash
python3 -m lib.doubts <slug> --open
python3 -m lib.doubts <slug> --clearances
python3 -m lib.gaps <slug>
```

Open doubts also appear in `coverage.json` and in the `lib.gaps` output, ranked
against every other gap on the same exchange rate, so there is one list to read
rather than two.

## An empty board is not permission

Everything above catches a doubt that got written down. The failure this file is
about is the one that did not, and against that failure an empty board is not
evidence of confidence — it is the signature of the problem.

So the five expensive jobs also want a positive **all-clear**. For each value the
job reads that came from a guess or from somebody's memory — provenance `assumed`
or `reported` — the all-clear carries either a doubt card id or a written reason
for running on it anyway. Nothing filed is a refusal, exactly like an open card.

Start by asking what the job actually leans on. This is cheap, never gated, and
prints the filing command with the paths already in it:

```bash
python3 -m lib.doubts <slug> --inputs sunmodel
```

Then file it, replacing each `TODO` with the real reason:

```bash
python3 -m lib.doubts <slug> --clear sunmodel \
    --because 'obstructions.fences.*.height=stock 6 ft panels, and d4 measured the one that shades the bed' \
    --cite 'features.trees.*.crown_base_height=d7'
```

`--because` takes a glob against the provenance path, so fourteen trees are one
line. `--cite` points at a card that is already **settled or waived** — citing one
that is still open is the original failure with a reference number on it, and it
is refused. One filing can cover several jobs: `--clear sunmodel,design`, or
`--clear all`.

Each clearance is bound to a digest of the values it covers. Edit `site.json` and
it goes stale, and stale blocks exactly like missing, naming which value moved.
Measuring something it covered does not invalidate it: that is an improvement,
not a change of subject.

What is honestly *not* solved: nothing stops `--because '*=looks fine'`. The gain
is that the omission becomes an artifact with a date on it, which a person can
disagree with, rather than a silence nobody can point at.

## The gate, and what it will not let you do

Five jobs refuse to run unless the yard is clear for them: `sunmodel`, `design`,
`drawbeds`, `bom`, `schedule`. Clear means both — nothing open on the board
against that job, and a current all-clear for it. Two layers enforce it.

1. `doubts.gate()` inside each module, which raises `SystemExit` with the open
   cards and the missing clearance printed. This always holds, including for
   programmatic callers.
2. `.cursor/hooks/doubt-gate.sh`, a `beforeShellExecution` hook that denies the
   shell command outright and tells you what to do instead. This exists because
   the in-process gate only fires after the command has been chosen, and the
   moment worth catching is earlier than that.

Which values each job is answerable for is declared in `lib/inputs.py` and
recovered from the source by static analysis, and `tools/doctor.py` and
`tools/test_gate.py` both check the two still agree. `python3 -m lib.inputs`
prints the map with the argument for each entry.

The cheap paths are deliberately never gated, because they are how a doubt gets
settled: `--quick` on the sun model, `lib.gaps`, `lib.inputs`, `lib.doubts`
itself including `--inputs` and `--clear`, `lib.design --init`,
`lib.bom --crossover`, the seed-date lookups.

**`--force` is not the way past this.** It exists for the case where someone has
looked at the board and decided to proceed anyway, and it costs a human approval
through the hook. Output produced that way is stamped provisional, and the stamp
names what it came past — `PROVISIONAL - forced past 2 open doubts and a stale
all-clear` — because "provisional" on its own is not something anyone can act
on. Do not reach for it to get unblocked; settle the doubt or waive it on the
record, and write the all-clear:

```bash
python3 -m lib.doubts <slug> --waive <id> --reason "..."
```

A waive with no reason is refused. That is the point of it.

## What this is not for

Not every uncertainty is a doubt card. The board is for things that would change
what an expensive job produces. Model limits that are always true — no clouds, no
far horizon, catalogue days-to-maturity being optimistic, default prices being
ballpark rather than quotes — belong in the reporting, where the skills already
say them. Putting them on the board buries the doubts that are actually live.

Run `python3 -m lib.doubts <slug> --check` if the board starts looking noisy; it
flags cards that block nothing, choices with no alternatives, anything settled
without a reason, and an all-clear that has stopped covering what it claims to.

# The plan says what is true now

The second failure this file is about, and it is the same shape as the first: a
sentence goes into prose where nothing can act on it, and stays there.

## The failure

The plan gets revised. The revision is narrated where it happened, because that
is where the reason for it is to hand:

> **Wed evening, 30 min — walk both roses with a torch.** *(Moved off Tuesday:
> the seed tray arrives Tuesday and that sowing is date-bound, this walk is
> not.)*

Nobody deletes that later, because it is true and it took thought. So it
accumulates. One `PLAN.md` reached 9,522 words this way, and the person reading it
on a Wednesday evening has to get past the history of the Tuesday it is not on
before finding out what to do.

The argument does the same at greater length. A decision that needed real
reasoning gets the reasoning written beside it — `### What dropping the yaupon
actually cost`, `### Are the violas enough for g03? No.` — and the conclusion ends
up in the middle of eight hundred words defending it.

Neither is worthless. That is exactly why they survive. They are in the wrong
file.

## The rule

**A plan document states what is true now. The history and the argument go to
`changelog.json`, and the plan carries the current fact, one sentence of reason,
and a reference.**

The documents this covers: `PLAN.md`, `SCHEDULE.md`, `SOWING-CALENDAR.md`,
`SOURCING.md`, `SITE-WALK.md`, `CALENDAR.md`. Reference material — the
`research-*.md` files — is exempt, because it is long for a good reason.

The phrases that mean a log entry is being written into a plan:

- "previously", "originally", "used to be", "the earlier draft", "the previous
  version", "changed from", "two things changed"
- "you were right", "you asked", "you said", "you thought", "you chose"
- "was wrong", "with one correction", "nobody had flagged", "I checked the
  reasoning", "I had assumed"
- "rewritten on", "revised against", "this replaces", "superseded", "moved off
  Tuesday", "no longer applies"

When one of those is about to go into an action document:

```bash
python3 -m lib.changelog <slug> --add "Rose walk moved to Wednesday" \
  --kind change --subject "rose walk" \
  --was "Tuesday 1 September" --now "Wednesday 2 September" \
  --why "the seed tray arrives Tuesday and that sowing is date-bound; the walk is not" \
  --affects PLAN.md
```

Then write the plan line as the instruction alone, with a bare `[c7]` after it if
the reason is worth finding. **Bare, not a markdown link** — `lib.buildhtml` makes
the link into `CHANGELOG.html` at publish time, so the plan source keeps reading
like a plan. Run `--render` after adding entries, or the anchor has nothing to
land on.

## Three kinds, and the one distinction that matters

    change      the plan said X and now says Y. Needs --was, --now, --why
    correction  the record was wrong and is now right. Needs --why and --source
    rationale   no prior state: why the plan is the way it is. Needs --why

`change` and `correction` are not interchangeable. "The walk moved to Wednesday"
is a change — both days were defensible. "The plan said g02 was bare in December
and it is not" is a correction, and someone deciding whether to trust the document
needs to be able to find those on their own. A correction without a `--source`
is refused: it is only worth more than the error if it says what settled it.

`rationale` is where the argument goes, and it is where most of the words go.

## The reference is the point

A log nobody can navigate is a bin. So every entry carries a `--subject` — the
bed, the task, the plant — and `--subject g03` reads that thread on its own.
Reference entries from the plan as `[c14]`, and check them:

```bash
python3 -m lib.changelog <slug> --lint
```

It reports the retrospective prose, the argument-shaped headings, any `[cNN]`
pointing at an entry that does not exist, and any action document over a
4,000-word budget. The budget counts **prose only** — tables and fenced blocks
are excluded, because a table is scanned rather than read straight through, and a
check that fires on a document full of dense well-formed tables is the one that
gets switched off. `.cursor/hooks/plan-prose.sh` runs the lint the moment a plan
document is written and hands the findings back; `lib.buildhtml` runs it on the
way to publishing, and `--strict` makes it refuse.

The budget is advisory and reported apart from the prose findings, so "long but
clean" stays distinguishable from "short and narrating its own history." The
second is the failure this is for.

Import the settled doubt cards rather than retyping them — a settled card is
already a rationale entry carrying better provenance than a retyped one:

```bash
python3 -m lib.changelog <slug> --from-doubts
```

## What this is not for

Not a version-control substitute. The log holds what a reader of the plan would
otherwise ask about — why this plant, why this date, what this replaced. It does
not hold every edit. "Fixed a typo" and "reworded the intro" belong nowhere, and
filling the log with them buries the entries someone came to find.

And it is not a place to put a decision that has not been made. That is a `choice`
card on the doubt board, and it stays there until somebody chooses.
