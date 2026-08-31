---
name: yard-schedule
description: Turn a garden design into a dated, costed, weekend-by-weekend build plan - netting the bill of materials against what is already in the garage, back-planning from the target date, counting seed-start and days-to-maturity deadlines backwards, gating tasks on the person's actual experience and hours, sourcing everything locally, and producing a cut list when it comes in over budget. Use when a design is ready to build, when someone asks what to do this weekend or what it will cost, or when a harvest or bloom date has to be hit.
---

# Yard Schedule

The last stage. Takes `design.json`, `conditions.json` and the target date, and
produces what to do on which weekend, what to buy, where, and what it costs.

Its whole reason for existing is that it knows what is already on site. A
shopping list that does not is a list that buys eight cubic feet of compost when
six are in the garage, and that is the failure the entire conditions stage exists
to prevent.

## Step 1 — What has to be bought

```bash
cd ~/personal/garden
python3 -m lib.doubts <slug> --open       # both jobs below refuse while this is open
python3 -m lib.bom <slug>
```

Both `bom` and `schedule` refuse to run while a doubt that blocks them is open,
and this is the stage where that matters most in cash terms. A bed whose size is
in question prices the soil, the compost, the mulch and the plant count wrong all
at once and in the same direction. A bed reported as already amended, wrongly,
deletes two weekends from the front of the plan.

If a run is forced through anyway, the output carries a `provenance` stamp saying
it is provisional. **Never hand someone a provisional total without the word.** A
number in a document gets acted on long after the caveat that came with it has
been forgotten.

Derives quantities from the design and the zone areas, subtracts what
`conditions.json` says is on hand, and prices the remainder. Two things it does
that a hand-written list will not:

**It handles settling and unit confusion.** Mulch and compost settle, so a
three-inch finished layer needs about three and a half inches delivered. Bulk
sells by the cubic yard and bags by the cubic foot, and there are 27 cubic feet
in a yard. Both are why hand estimates come up short.

**It works out bags against bulk from the actual numbers.** The received wisdom
is that bulk wins above a cubic yard. With a delivery fee it does not: at $75
delivered the crossover is about two cubic yards for compost and over three for
mulch, because the saving has to earn the fee back first.

```bash
python3 -m lib.bom <slug> --crossover
```

The default prices are national ballpark figures and are labelled as such
wherever they print. **Do not quote them as costs.** They exist so the plan has a
number before anyone drives anywhere.

## Step 2 — Where to buy it

Launch the **sourcing-scout** subagent with the netted list and the location. It
returns real local suppliers with real prices, delivery fees and minimums, and it
covers the categories people miss: municipal free-mulch programs, native plant
society sales, county extension soil testing, and trade counters for stone and
drip parts.

Feed its prices back in:

```bash
python3 -m lib.bom <slug> --prices local-prices.json
```

Then the total says `local` instead of `national ballpark`, and it can be quoted.

Flag date-bound opportunities loudly. A native plant sale on one Saturday in
April is worth more than a five per cent saving elsewhere, and it belongs in the
schedule as a fixed point rather than a note.

## Step 3 — Count the deadlines backwards

Three different kinds of arithmetic, and all three are quiet failures if skipped:

```bash
python3 -m lib.schedule <slug> --seed-start "tomato,pepper,zinnia"
python3 -m lib.schedule <slug> --crop "bush bean" --harvest-by 2027-06-01
```

**Seed start.** Tomatoes and peppers want six to eight weeks indoors before the
last frost, brassicas five to six, cucurbits three to four and they resent being
started earlier. Counting backwards from the frost date turns "start seeds in
spring" into a dated task.

**Days to maturity.** A harvest date minus days to maturity gives a sow-by date,
plus a fortnight, because catalogue figures assume conditions nobody has.

**Frost conflicts.** The tool checks the sow-by date against the last frost and
says so when a tender crop's date lands before it. This is the classic way a
back-planned harvest fails, and the answer differs by crop: something
transplantable gets started indoors, and something direct-sown like beans or okra
does not, because transplanting sets it back further than the head start gains.

Everything counts from the **10% risk frost date**, not the median. The median is
a coin flip, and the derived dates run one to two weeks early against station
normals. If the county extension publishes a local figure, it beats both.

## Step 4 — Back-plan it

```bash
python3 -m lib.schedule <slug>
python3 -m lib.schedule <slug> --hours 4      # override hours a weekend
```

Weekends, not weeks. A schedule in weeks quietly assumes Wednesday evenings
exist, and for most people they do not.

What it does:

- **Orders by dependency.** Marking out, killing turf, edging, soil, irrigation,
  hardscape, then planting, then mulch, then grooming
- **Splits tasks that do not fit in one weekend** and numbers the parts in the
  order they will be worked. A ten-hour path is not a task, it is two Saturdays
- **Works around travel.** A weekend inside a stated gap holds no work, and the
  plan reaches further back rather than silently dropping what fell off the end
- **Reserves a catch-up weekend.** Something always slips, and a plan with no
  slack fails on the first rainy Saturday
- **Keeps the last weekend for grooming.** Tidying and filling gaps with
  something already in flower. Nothing structural
- **Gates on experience.** Tasks the person has not done get the how-to written
  in; tasks beyond their level get flagged for hiring out or a simpler
  substitute. Explicit experience beats the general level — someone who has built
  a raised bed has built a raised bed, whatever they call themselves

When the work does not fit, it says which tasks did not, and they will be the
groundwork the rest depends on. **Do not present a plan that plants into a bed
that was never edged or amended.** The three honest options are starting earlier,
hiring out the heavy items, or cutting scope and phasing — and it gives the date
by which starting earlier would have to begin.

## Step 5 — Establishment watering belongs in the plan

Daily for the first week, every other day for two to three weeks, twice weekly
through about eight weeks, then weekly deeply through the first summer.

This is the task that actually kills plantings, and it is the one that gets
written as a footnote. Put it in the schedule where it can be seen, and if
someone is travelling in the first month, write a separate one-page note for
whoever is covering — scoped to keeping things alive: check moisture, hand-water
anything wilted, change nothing else.

## Step 6 — The budget, and the cut list

The cut list comes out with the total, not after someone flinches at it. It is
ordered by what the vision said mattered least, and it protects soil prep,
edging and irrigation, because those are what make everything else survive and
read as finished. Skimping there turns a planting into a patch of ground with
plants in it.

Most cuts are downsizing rather than dropping, and the distinction matters:

- A 1-gallon shrub catches a 5-gallon in about three years, costs a quarter as
  much, and establishes better because the root ball is not circling
- Halving a plant count and spacing the rest at mature spread is what the bed
  wanted anyway
- Free wood chips do the same job as bagged mulch, coarser and less tidy
- Gravel or decomposed granite instead of pavers, upgraded in place later

Ask whether the budget is a lump sum or spread. It changes the schedule as much
as it changes the list: a monthly budget phases naturally into "infrastructure
this spring, planting next autumn," which is usually the better garden anyway
because autumn planting establishes better in most climates.

## Step 7 — Deliver it

Write the plan as markdown into the yard's folder. For something printable:

```bash
python3 -m lib.builddoc plan.md -o plan.docx
```

It embeds the maps and produces real tables. Upload with `gdrive.uploadFile` and
`convertToGoogleFormat: true` for a new doc, or with `fileId` to update an
existing one in place and keep the link stable. The two options cannot be used
together.

Then update `conditions.json` with anything that changed — materials bought,
ground worked, tools acquired. The schedule is disposable; the conditions record
is not, and next season's plan is only as good as what this one wrote down.

## Rules

- Never price from the defaults and call it a cost. Run sourcing-scout first, or
  label the number as a ballpark every time it appears
- Never present a provisional total or a provisional calendar without saying so.
  A quantity in doubt is a quantity bought twice, and the doubt is cheaper to
  settle than the second delivery
- Never schedule work into a stated travel gap, and never quietly drop the tasks
  that no longer fit
- A task the person has not done before gets the how-to, in the schedule, at the
  weekend it happens. Not a link
- Say how long things take honestly. Doubling a first-timer's estimate is closer
  than halving it
- The heaviest work belongs in the best planting season for that region, which is
  often not the season closest to the deadline. In most hot climates that is
  autumn, and saying so may be worth more than the whole rest of the plan
