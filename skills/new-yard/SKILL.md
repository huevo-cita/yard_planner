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
| geometry, obstructions, climate | `yard-survey` | `site.json` |
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

## Step 4 — Stop when it is good enough

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
```

Then go to the stage that answers the question. Someone asking why their roses
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
- After every stage, say what is now known and what it changed. A person who has
  answered twenty questions deserves to see them add up to something
- Where two sources disagree, report both and say which is better. Never average
  them
- The person knows things no dataset does: which tree came down, where it floods,
  what the neighbour is planning. Ask, and record it
