---
name: yard-conditions
description: Capture the current state of a yard and of the person working it - soil texture, drainage, compaction and pH from a free USDA lookup plus guided hands-on tests; what ground is already dug, edged, bordered, mulched or irrigated; what soil, compost, mulch, gravel, edging and pots are already on site; what tools are owned or borrowable; and the person's experience, physical limits, weekly hours, budget and deadlines. Use when starting a new yard, before building any schedule or shopping list, when someone asks what their soil is like or whether it drains, or when a plan needs to know what is already on hand. Writes conditions.json.
---

# Yard Conditions

`site.json` says what the yard *is*. This produces `conditions.json`: what is
already true about it today. Without it a schedule invents work that is already
done, and a shopping list buys eight cubic feet of compost when six are sitting
in the garage.

Run this before `yard-design` and always before `yard-schedule`.

## Step 1 — Load what exists

```bash
cd ~/personal/garden
python3 -m lib.conditions <slug>          # what is recorded, and what is stale
python3 -m lib.conditions <slug> --init   # if there is nothing yet
```

Conditions decay, and the tool knows the rate: materials go stale in three
months, ground in a year, soil texture in three. **Re-confirm the stale sections
rather than trusting them.** "You told me in March you had four bags of compost —
still true?" takes one line and prevents a wasted trip.

Only ask about sections that are missing or stale. Never re-run the whole intake
on a yard that already has a record.

## Step 2 — Soil, in three tiers

### Tier 1, free and instant: the national soil survey

```bash
python3 -m lib.soil <slug> --write
```

This queries USDA Soil Data Access for the yard's coordinate and records the map
unit, its components, drainage class and horizon data.

**Expect it to say "Urban land," and know what that means.** Both yards in this
system do. It is the survey stating plainly that the original soil was scraped
off, built on, and backfilled with whatever was to hand. When that happens the
result is context about the neighbourhood, not a measurement of this yard, and
the tool flags it as low confidence. Report it that way. Do not let a map unit
stand in for knowing.

### Tier 2, free and real: hands in the dirt

This is the tier that actually decides things on a house lot. Walk the person
through whichever tests the design will lean on, one at a time, and record each:

**Jar test — texture.** A jar two-thirds water, one-third soil from the top
6 in, a squirt of dish soap. Shake hard for two minutes, then leave it. Sand
settles in a minute, silt over a couple of hours, clay over a day or two.
Measure the three bands in mm. Ignore the raft of organic matter floating on
top; it is not one of the bands.

```bash
python3 -m lib.soil --jar <sand_mm> <silt_mm> <clay_mm>
```

**Percolation test — drainage.** Dig a hole a foot across and a foot deep. Fill
it, let it drain away completely, then fill it again and time the second one.
Timing the first fill instead measures dry ground pulling water sideways and
reads as much as twice too fast.

```bash
python3 -m lib.soil --perc <inches_dropped> <minutes>
```

**Compaction probe.** A long screwdriver or a length of rebar, pushed in with
steady hand pressure. Record how far it goes before it stops. **Only meaningful
on moist soil** — dry ground reads hard whatever its structure, so do this a day
after rain or a good watering, not in a drought.

```bash
python3 -m lib.soil --probe <inches>
```

**pH strips.** Cheap and good to about half a unit, which is enough to tell
"fine for vegetables" from "you will never grow a blueberry here." Take three
readings in different spots; a fill lot can vary wildly across twenty feet.

```bash
python3 -m lib.soil --ph <value>
```

Record each with `lib.conditions.record_test(slug, result, where=...)`.

### Tier 3, $15-30 and one to two weeks: a lab test

A mail-in test through the county extension is the only source of real nutrient
levels, salts, and a trustworthy pH.

**Raise it as a ranked gap, not a routine step.** It is worth the wait when, and
only when, the design turns on it:

- acid-lovers in the plan — blueberries, azaleas, camellias, rhododendrons
- a vegetable bed being fed for the first time, where guessing at fertiliser is
  guessing at the whole season
- a site with a plausible contamination history — old painted structures, a
  former driveway, a demolished building, anything urban and pre-1978
- a persistent problem that nothing else explains

If none of those apply, say so and move on. Do not stall a plan for two weeks
over a number the design does not use.

Also ask about **amendment history**. Someone who limed heavily two years ago
has a different soil than the map says, and it is the only way to know.

## Step 3 — The ground as it stands

Walk the yard section by section and record what is already there. For each area:
is it dug, edged, bordered, mulched, irrigated? Turf, bare soil, gravel, weed
mat, or hardscape? How deep does the existing bed actually go?

Two things that trip up every plan and never get volunteered:

- **Usable depth is not bed depth.** Subtract rock bands, wall setbacks and
  edging. A 40 in bed with a 14 in rock band under the drip line gives 26 in of
  planting, which is one row of shrubs and not two.
- **Where each measurement actually stops.** When someone says "a 19 ft bed and a
  13 ft bed meeting at a corner," the corner square is either inside one of those
  numbers or it is a third, unmeasured piece of ground. Ask directly, then draw
  it. People correct a picture instantly and a paragraph never.

Record hardscape too: paths, patios, walls, steps, and what they are made of.
A path that already exists is a path that does not need building.

## Step 4 — Water

Where are the spigots, and how far does a hose actually reach? Is there
irrigation, and does it work? Does rain reach every bed, or does a roof throw it
somewhere else?

**Rain shadow is the quiet killer.** A bed under an overhang or a dense canopy
may get almost no natural rain even in a wet climate. Three consequences worth
stating out loud: irrigation there is the entire water supply rather than a
supplement; it cannot be winterised by shutting it off, only by reducing
frequency; and even drought-tolerant natives need occasional deep water forever,
because "natives need no water" quietly assumes they get rain.

Ask directly: *"Does rain actually land in that bed, or does the roof throw it
somewhere else?"*

**Roof drip lines.** Where a roof has no gutter, water falls in a concentrated
line and hits hard. Find out how far from the wall it lands. Record it in
`conditions.json`, because it dictates a river-rock band and rules out
rot-prone plants like rosemary and lavender anywhere near it.

## Step 5 — What is already on site

This is the section that pays for the whole skill. Go through the garage, the
shed, the side return, the pile behind the fence.

**Materials**, with quantities in the units they are bought in: compost, topsoil,
garden soil, mulch, wood chips, gravel, sand, decomposed granite, edging, lumber,
pavers, block, flagstone, landscape fabric, cardboard, pots, stakes, trellises,
drip line and emitters, fertiliser, lime, sulphur, leftover seed. Bagged soil
counts in cubic feet: a standard bag is 1.5 cu ft, and a cubic yard is 27.

**Tools**, split three ways: owned, borrowable from a neighbour or family, and
rentable nearby. The split matters — a borrowable tiller has to be scheduled
around its owner, and a rental has to be paid for and returned the same day,
which shapes the weekend it belongs in.

Also worth asking: is there anywhere to put a cubic yard of bulk mulch, and can a
truck reach it? Bulk beats bags above about a cubic yard, but only if there is
somewhere for it to be dumped.

## Step 6 — The person

Not optional, and not a formality. The schedule is gated on this.

- **Experience**: none, beginner, some, confident, or expert. Then, separately,
  **what they have actually done before** — this beats the general level. Someone
  who has built a raised bed has built a raised bed, whatever they call
  themselves.
- **Physical limits**: back, knees, shoulders, how much they can lift, whether
  they can kneel. A plan involving forty 40 lb bags is a different plan for
  different people, and this is the difference between a schedule that happens
  and one that does not.
- **Hours a week**, honestly. Then **which days** — a Saturday-only person cannot
  do a task that needs watering the next morning.
- **Travel gaps** in the window, so the schedule works around them instead of
  quietly assuming forty consecutive weekends.

## Step 7 — Budget and constraints

**Budget**: the ceiling, and whether it is a lump sum available now or a monthly
trickle. That single distinction changes the whole sequence — a monthly budget
means phasing, and phasing means deciding what has to be right the first time
and what can wait.

Ask what has already been spent, so the running total is real.

**Constraints**: HOA rules, landlord permission, pets that will dig or chew,
children, deer, rabbits, gophers. And **deadlines** — a party, a season, a
harvest, a visit. A date lets everything downstream be back-planned; without one
the schedule is just a list.

## Step 8 — Write it and report the confidence

Everything goes into `conditions.json` through `lib/conditions.py`, with
`last_verified` stamped on each section touched.

Then report the soil confidence honestly, in the tool's own terms:

| Confidence | What it means |
|---|---|
| `good` | a lab test exists |
| `workable` | two or more hands-on tests |
| `thin` | one hands-on test |
| `map only` | the USDA lookup and nothing else |
| `none` | nothing recorded |

Finish by running the gap report, so what is still missing is ranked rather than
merely listed:

```bash
python3 -m lib.gaps <slug>
```

A `map only` or `none` confidence is a fact about the record and belongs in the
gap report, which already prices it. It is not a doubt card. The board is for
things you have looked at and do not believe, and a soil you have never tested is
simply untested.

What does belong on the board, because the schedule and the bill of materials both
refuse to run while it is open:

- **A quantity you were given and do not trust.** "Four bags of compost, I think"
  becomes a card, not a number. `bom` nets against it and buys twice if it is
  wrong
- **Ground you were told is done and have not seen.** A bed reported as edged and
  amended changes the whole first month of the schedule. If the report is
  second-hand, file it
- **An experience level you are unsure you read correctly.** The task gates turn
  on it, and getting it wrong either patronises someone or hands them a retaining
  wall

```bash
python3 -m lib.doubts <slug> --add "Is the back bed already amended, or just dug?" \
    --kind fact --blocks schedule,bom --usd 220 \
    --detail "reported second-hand, and it decides two weekends of prep" \
    --how "look at it, or ask what went in" --effort "one question"
```

## What not to do

- Do not present a USDA "Urban land" result as if it described this yard's soil.
- Do not skip the pre-soak on a percolation test and report the number anyway.
- Do not run a compaction probe in dry ground.
- Do not recommend a lab test reflexively. Name the decision that depends on it,
  or leave it off.
- Do not record a quantity as "some." The whole point is netting against a bill
  of materials, and "some compost" nets to nothing.
- Do not put a never-tested thing on the doubt board. That is a gap, the gap
  report already prices it, and padding the board is how a board stops being read.
- Do not record a quantity or a state you do not believe without filing the doubt
  alongside it. A number you distrust in `conditions.json` reads as measured to
  every tool downstream.
