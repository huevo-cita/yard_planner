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
python3 -m lib.doubts <slug> --inputs bom # what is still a guess, and how to clear it
python3 -m lib.doubts <slug> --clear bom,schedule --because '...=...'
python3 -m lib.bom <slug>
```

Both `bom` and `schedule` refuse to run while a doubt that blocks them is open,
and this is the stage where that matters most in cash terms. A bed whose size is
in question prices the soil, the compost, the mulch and the plant count wrong all
at once and in the same direction. A bed reported as already amended, wrongly,
deletes two weekends from the front of the plan.

They also refuse until an all-clear says, in writing, why it is safe to cost a
bed whose dimensions came from pacing rather than a tape. Both jobs read a narrow
slice of `site.json` — bed geometry from `zones`, frost and heat from `climate` —
so on most yards this is one line covering `zones.*`, and the two can be cleared
in the same filing.

If a run is forced through anyway, the output carries a `provenance` stamp saying
it is provisional and naming what it came past. **Never hand someone a
provisional total without the word.** A number in a document gets acted on long
after the caveat that came with it has been forgotten.

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

**No line is ever dropped for want of a price.** An item nothing has quoted is
estimated from comparable prices and marked, and the total carries the firm and
estimated parts separately along with the range:

```
  $70.48 of that is quoted and $446.50 — 86% — is estimated from comparable prices
  the range across those estimates is $360 to $674
```

An 86% estimated total is not a failure of the tool, it is the true state of the
research, and it says which lines to go and fix:

```bash
python3 -m lib.bom <slug> --price-gaps    # estimated lines, by dollars at risk
```

## Step 2 — Where to buy it, and in what order

Launch the **sourcing-scout** subagent with the netted list and the slug. It
writes `<slug>/sourcing.json` — dated evidence per supplier, not prose — covering
the categories people miss: municipal free-mulch programs, native plant society
sales, county extension soil testing, and trade counters for stone and drip
parts.

```bash
python3 -m lib.sourcing <slug> --geocode   # real distances from the addresses
python3 -m lib.sourcing <slug> --check     # what the evidence is missing
python3 -m lib.sourcing <slug>             # the ranked board
python3 -m lib.sourcing <slug> --rank nursery
```

Four rules decide the order, and they are in code so they can be argued with:

- **Locality is classification, not exclusion.** Every supplier is geocoded and
  carries a real distance to the yard. One outside the metro is reported under
  "not local to this yard" with the mileage rather than silently dropped, and
  **mail order is its own list, never gated out** — some things have no local
  source and a rule that removed them would delete the only way to buy them
- **Quality comes from dated evidence, or the supplier is not ranked at all.**
  Ratings are shrunk toward the local mean by review volume and then tiered on
  the bottom of the confidence interval, so a 5.0 from eight people does not
  outrank a 4.7 from nine hundred, and a shop nobody has checked lands under "not
  ranked" instead of inheriting the neighbourhood's good name
- **Memberships and big sales move a supplier up considerably, and say so.** The
  bump is printed by name — "ranked up +0.80 for access: member preview, 10%
  member discount; Fall native sale" — never folded invisibly into a number
- **Distance breaks ties inside a quality tier, never across one.** Nearest of
  the good ones, not nearest overall

The bill of materials reads `sourcing.json` directly, so quotes gathered there
price the list with no extra step. `--prices local-prices.json` still works and
still overrides per item.

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

## Step 7 — The dates go in tasks.json first

Every dated action the back-plan produced goes into `<slug>/tasks.json` before
any of it is written as prose. That file is the single source for what happens on
a day, and `CALENDAR.md` — the document somebody actually reads on a Saturday
morning — is generated from it:

```bash
python3 -m lib.week <slug> --calendar    # -> CALENDAR.md, then buildhtml it
python3 -m lib.week <slug>               # this week, to the terminal
python3 -m lib.week <slug> --shop 3      # the next three weeks, grouped by supplier
python3 -m lib.week <slug> --check       # has the prose drifted from the file
```

A task carries the day, the duration, the position down to the square or the
foot-mark, what gates it and what to do if the window closes. Everything it
leans on is cited in `source`, and `tasks.json` keeps a digest of each cited
section — so a date later changed in `PLAN.md` and not here is caught rather than
silently disagreeing. `--calendar` refuses while it does.

The schema and the two checks are in [AGENTS.md](../../AGENTS.md), under "A date
goes in tasks.json". Do not hand-write `CALENDAR.md`; it is overwritten on the
next render.

## Step 8 — Deliver the plan

`PLAN.md` in the yard's folder, and it has a shape. This is a specification, not
a suggestion, because the alternative was tried: "write the plan as markdown" is
what the instruction used to say, and one plan reached 9,522 words.

It opens with a line pointing at `CALENDAR.md` for what to do this week, because
the plan is the reference and the calendar is the instruction.

```
# <address> — the plan to <target date>
   One short paragraph: what this document is, where the facts live,
   what lives in another file.

## The next seven days
   Dated actions with hours. Nothing else.
## Weekend by weekend to <date>
   Each item: the action, the date, the duration, the cost, at most one
   sentence of reason, and a bare [cNN] if there is more to say. Bare —
   lib.buildhtml makes it a link into CHANGELOG.html when it publishes.
## The beds
   A table — bed, size, measured light, planting, state on the target date.
## What it costs
   A table — item, quantity, price, source. The cut list underneath.
## Standing calendars
   Water, pruning, pests. Tables, not prose.
## Open decisions
   From doubts.json. What is owed, and by whom.
```

**Four things do not go in it.** Any sentence about what the plan used to say. A
reason longer than one sentence. Second-person argument — "you were right to
ask", "you asked for butterflies". A heading that asks a question or rebuts one.

All four are change-log entries. File them and the plan gets shorter without
losing anything:

```bash
python3 -m lib.changelog <slug> --add "Rose walk moved to Wednesday" \
  --kind change --subject "rose walk" \
  --was "Tuesday 1 September" --now "Wednesday 2 September" \
  --why "the seed tray arrives Tuesday and that sowing is date-bound" \
  --affects PLAN.md
python3 -m lib.changelog <slug> --from-doubts   # the settled cards, once each
python3 -m lib.changelog <slug> --render        # -> CHANGELOG.md
python3 -m lib.changelog <slug> --lint          # what is still in the wrong file
```

The full rule, with the phrase list that should trigger it, is in
[AGENTS.md](../../AGENTS.md). A separate calendar — sowing dates, a rotation — is
its own document with its own budget, not a section bolted onto the plan, and its
dates go into `tasks.json` along with everything else's.

For something printable:

```bash
python3 -m lib.builddoc plan.md -o plan.docx     # .docx, with the maps embedded
python3 -m lib.buildhtml <slug>/PLAN.md --strict # HTML, refusing on narration
                                                 # add --budget to refuse on length too
```

`builddoc` embeds the maps and produces real tables. Upload with
`gdrive.uploadFile` and `convertToGoogleFormat: true` for a new doc, or with
`fileId` to update an existing one in place and keep the link stable. The two
options cannot be used together.

Then update `conditions.json` with anything that changed — materials bought,
ground worked, tools acquired. The schedule is disposable; the conditions record
is not, and next season's plan is only as good as what this one wrote down.

## Rules

- Never price from the defaults and call it a cost. Run sourcing-scout first, or
  label the number as a ballpark every time it appears
- Never quote a total without its estimated share. "About $1,600" and "about
  $1,600, of which $1,100 is estimated from comparable prices" are different
  claims, and only the second one can be planned against
- Never present a provisional total or a provisional calendar without saying so.
  A quantity in doubt is a quantity bought twice, and the doubt is cheaper to
  settle than the second delivery
- Never schedule work into a stated travel gap, and never quietly drop the tasks
  that no longer fit
- A task the person has not done before gets the how-to, in the schedule, at the
  weekend it happens. Not a link
- Never narrate a revision in the plan. Correct the plan to the new fact and file
  what moved in the change log. A reader on a Wednesday evening should not have
  to read past the history of the Tuesday it is no longer on
- Say how long things take honestly. Doubling a first-timer's estimate is closer
  than halving it
- The heaviest work belongs in the best planting season for that region, which is
  often not the season closest to the deadline. In most hot climates that is
  autumn, and saying so may be worth more than the whole rest of the plan
