---
name: new-yard
description: Start a yard from nothing but an address and run it all the way to a costed weekend-by-weekend build plan - registering the yard, sequencing survey, current-state, taste, sun model, design and schedule, and reporting after each stage what is still unknown and what that ignorance costs. Use when someone says "start a new yard", asks to plan a property from scratch, wants to know where a yard project stands, or asks what to do next on one.
---

# New Yard

The conductor. It registers a yard, runs the other skills in the order that makes
each one's job easier, and after every stage says what is still missing and what
that costs.

Nobody has to run this. Any of the skills below work alone on a yard that already
has the files they need. This exists so that "start a new yard" is one sentence
rather than seven.

## The order, and why it is this order

```
  yard-survey     address to measured geometry, plus climate and frost dates
       |
  yard-sun-model  hours of light per zone per month
       |
  yard-conditions soil, existing ground, materials, tools, the person
       |
  yard-vision     what they actually want
       |
  yard-design     the two joined, with the site allowed to object
       |
  yard-schedule   netted materials, weekends, costs, sourcing
```

Survey first, because everything else is measured against it. Sun model second,
because it takes minutes and it changes what is worth asking — there is no point
discussing a vegetable bed in a corner that gets three hours.

Conditions and vision can go in either order and can interleave with the survey,
since both are conversations rather than computations. Do them while waiting on
anything slow.

Design cannot start before all four. Schedule cannot start before design.

`yard-site-walk` is the loop back to the survey, not a stage of its own. Run it
when the record is still mostly public data, or when the yard has changed since
the data was captured — a new deck, new beds, a tree down. It reads the ranked
gaps, writes a field checklist aimed at the ones a tape can settle, and folds the
readings back into `site.json` as `measured`. Then re-run the sun model, because
real tree species and real fence heights are the two largest corrections it ever
gets.

## Step 1 — Register it

```bash
cd ~/personal/garden
python3 -m lib.yards                                   # what already exists
python3 -m lib.yards --new <slug> --address "<address>"
```

Check the registry first. Someone asking about "the Austin yard" usually means
one that already exists, and re-running intake on a yard with a record is the
fastest way to lose their patience.

## Step 2 — Run the stages

Each is its own skill. Load it and follow it; do not summarise it from here.

| stage | skill | produces |
| --- | --- | --- |
| doubts raised along the way | any stage | `doubts.json` |
| geometry, obstructions, climate | `yard-survey` | `site.json` |
| ground truth for a thin record | `yard-site-walk` | `SITE-WALK.md`, then `measured` values |
| light by zone and month | `yard-sun-model` | `sun-hours.json`, maps |
| soil, ground, inventory, person | `yard-conditions` | `conditions.json` |
| purpose, style, constraints | `yard-vision` | `vision.json` |
| planting and hardscape | `yard-design` | `design.json`, bed maps |
| materials, dates, cost | `yard-schedule` | the plan |

Four subagents do the context-heavy work: **parcel-scout** for county GIS,
**photo-surveyor** for measuring from photographs, **vision-scout** for
inspiration boards, **sourcing-scout** for local suppliers and prices.

## Step 3 — Report the gaps after every stage

```bash
python3 -m lib.gaps <slug>
```

This is the part that makes the whole thing worth sequencing, and it is the part
that gets skipped.

Gaps are ranked by consequence in their own units. A geometry gap is priced by
re-running the sun model across the plausible range of the unknown and reporting
the spread in hours of light a day. A conditions gap is priced in dollars at risk
or plants likely to die. A vision gap is priced in design decisions it blocks.

On one measured yard the top gap was crown spread, worth two and a half hours of
light a day — the model runs from 2.2 to 4.7 hours across the plausible range,
which is the difference between a vegetable bed and a shade garden. Ten minutes
with a lidar query settles it.

**Show the ranked list and let them choose.** "Here are three things worth
knowing, here is what each is worth, and here is the quickest way to settle each"
respects the fact that some people will go and measure and some will not, and
both are legitimate. What is not legitimate is designing on an assumption without
saying it was one.

## Step 4 — Clear the board before each expensive stage

A gap is something the record never knew. A doubt is something the record claims
and nobody believes — usually because you formed it yourself while working. Both
change what happens next, and only one of them used to have anywhere to live.

```bash
python3 -m lib.doubts <slug> --open        # what is in question, worst first
python3 -m lib.doubts <slug> --price       # probe the ones a model can settle
python3 -m lib.doubts <slug> --clearances  # what has been attested, and for which job
```

The sun model, the design, the bed maps, the bill of materials and the schedule
all refuse to run while a doubt that blocks them is open. That refusal is the
whole point: settling a fence height takes two minutes, and re-running the model
and reworking the design because the fence turned out to be open rail takes an
afternoon.

They also refuse until an **all-clear** has been filed for that job on that yard.
An empty board is not permission — it is what a doubt that was thought and never
written down looks like from outside. So before each expensive stage, ask what
the job is leaning on and answer for it:

```bash
python3 -m lib.doubts <slug> --inputs sunmodel   # every assumed or reported value
                                                 # it reads, and the filing command
python3 -m lib.doubts <slug> --clear sunmodel --because 'path.glob.*=why this is fine'
```

Each job is asked only about the part of `site.json` it actually reads, so
`sunmodel` carries most of it and `bom` usually carries a line. The clearance is
bound to the values it covers: change one and it goes stale, and the refusal says
which. When that happens use `--clear <job> --renew`, which carries forward every
reason whose value has not moved — retyping sixteen sentences to correct one tree
height is how this ends up being `--force`d instead. Nothing stops a blanket
reason covering everything at once — that hole is real and named in `AGENTS.md`,
along with the fact that a `measured` value can change underneath a clearance
without staling it — but a lazy sentence with a date on it is still something a
person can read and disagree with, which silence is not.

**File the doubt when you form it, not when you report.** If you are about to
write "one caveat", "I've assumed", "not sure whether" or "we could either" about
something the next stage depends on, that sentence is a card. `AGENTS.md` has the
full trigger list and the commands.

**Probe before you interrupt.** `--price` re-runs the shade model across the
plausible range of any `fact` card carrying a probe, and settles the ones that do
not move the answer as `probed-immaterial` with the measured spread as evidence.
Most doubts die there, unread, which is what keeps the board worth reading.

**Bring what is left as a batch, at the stage boundary.** Not one at a time
mid-stage. Open doubts also appear in the `lib.gaps` output and in
`coverage.json`, ranked against every other gap on the same exchange rate, so
Step 3 and this step are one list rather than two.

**A `choice` card is theirs to settle, not yours.** Put the options up with their
pros, cons and costs and let them pick. Recording "bed against the house, or out
in the open — shelter and a rain shadow against real rain and wind, and $120 of
drip either way" is the difference between a decision and a guess that gets
discovered in August.

## Step 5 — Stop when it is good enough

A complete record is not the goal. A good decision is.

Stop asking when the remaining gaps cannot change what happens next. If every
outstanding unknown is worth less than an hour of light a day and under a hundred
dollars of risk, the design will not change, and continuing to ask is stalling
dressed as diligence.

Say so out loud when it happens: "there is more that could be measured, and none
of it would change this plan."

## Working with a yard that already exists

Most conversations are this, not a new yard.

```bash
python3 -m lib.yards <slug>      # what it has
python3 -m lib.gaps <slug>       # what it is missing
python3 -m lib.changelog <slug>  # what has already been decided, and why
```

Read the log before re-arguing something. It is the record of decisions already
made, and reopening one that was settled for a good reason is how a plan loses a
week. Then go to the stage that answers the question. Someone asking why their roses
are dying needs `yard-sun-model` and possibly `yard-conditions`, not a fresh
intake.

Conditions decay and the tools track it: materials go stale in three months,
ground in a year, soil texture in three. Re-confirm stale sections rather than
trusting them. "You told me in March you had four bags of compost — still true?"
takes one line and saves a trip.

## What this system will not do

Worth saying plainly at the start rather than at the end:

- **It does not survey a property line.** Parcel polygons are good enough to
  decide where a bed goes and not good enough to decide where a fence goes
- **It models clear-sky geometric sun.** Clouds, reflected light and diffuse
  light are not in it, and a north wall reading zero direct sun still grows
  things
- **It has no plant database.** Plant choice is researched fresh for every
  region, because a plant list does not travel and mature size is not the same
  in Minnesota and Georgia
- **Its default prices are not quotes.** They exist so a plan has a number before
  anyone drives anywhere

## Rules

- Never start intake on a yard that already has a record. Read it first
- Ask in rounds. Three good questions, then the answers, then three more. Twenty
  at once gets four answered
- Every value carries where it came from, and an assumption stays labelled an
  assumption until something measures it
- A doubt goes in `doubts.json` before the stage it affects runs, never into
  prose on the way past. Filing a card and running the job it blocks in the same
  breath is the same mistake with an extra step
- `--force` is not how you get unblocked. Settle the doubt, or waive it with a
  reason on the record, and file the all-clear
- Every assumed or reported value the next job reads gets a sentence before that
  job runs. If you cannot finish the sentence, you have found a doubt card
- A change goes in `changelog.json`, never into the plan as a paragraph about
  what the plan used to say. Correct the document to the new fact, file what moved
  and why, and leave a `[cNN]` reference where the reason is worth finding.
  `python3 -m lib.changelog <slug> --lint` is the check; the rule is in
  [AGENTS.md](../../AGENTS.md)
- After every stage, say what is now known and what it changed. A person who has
  answered twenty questions deserves to see them add up to something
- Where two sources disagree, report both and say which is better. Never average
  them
- The person knows things no dataset does: which tree came down, where it floods,
  what the neighbour is planning. Ask, and record it
