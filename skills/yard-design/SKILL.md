---
name: yard-design
description: Turn measured facts and stated taste into a planting and hardscape plan - research the regional plant palette, place plants where the light, water and soil actually support them, draw to-scale bed maps, and check the result against the sun model before anything is bought. Objects when the yard cannot support what was asked for, and names the trade rather than silently substituting. Use when designing or redesigning beds, choosing plants for a yard, or checking whether a plan will actually work. Writes design.json and bed maps.
---

# Yard Design

This is where measured facts meet taste. It reads `site.json`, `sun-hours.json`,
`conditions.json` and `vision.json`, and produces `design.json` plus to-scale bed
maps.

The one job that distinguishes it from a nice plant list: **it refuses things the
yard cannot support.** It is easy to assemble a beautiful, coherent, regionally
appropriate planting that quietly needs six hours of sun in a bed that gets three,
and nothing about it looks wrong until August.

Method notes, site quirks, pest management and nursery questions are in
[reference.md](reference.md). Read the section you need rather than the whole
file.

## Step 0 — Refuse to start without the inputs

```bash
cd ~/personal/garden
python3 -m lib.yards <slug>          # what exists
python3 -m lib.gaps <slug>           # what is missing, and what it costs
python3 -m lib.doubts <slug> --open  # what is claimed and not believed
python3 -m lib.doubts <slug> --clearances  # what has been attested, per job
```

`sun-hours.json` is not optional. Designing without it is guessing, and the guess
is always optimistic — people remember the yard as sunnier than it is because
they remember standing in it in July at two o'clock.

If a top-ranked gap would change the design, close it first. When crown spread is
worth two and a half hours a day, the difference is a vegetable bed or a shade
garden, and no amount of careful plant selection survives getting that backwards.

**The linter refuses to run while a doubt that blocks the design is open, and
while there is no current all-clear for it.** An objection list computed on
doubtful geometry is the most misleading thing this skill can produce, because it
reads as a verdict — and a `blocking` objection that evaporates once the fence
turns out to be open rail has cost someone a replanning session for nothing.

`design` reads far less of `site.json` than the sun model does — bed identity and
size from `zones`, heat and chill from `climate` — so its all-clear is usually a
line or two. `python3 -m lib.doubts <slug> --inputs design` prints the list and
the command; `--clear design,drawbeds` covers the bed maps in the same filing.

Three moves before designing:

- **Check `sun-hours.json` is not provisional.** If it carries a `provenance`
  field, the geometry behind it was never settled and every light figure below is
  an order of magnitude rather than a measurement. Say so, and re-run the model
  properly before placing anything. Note that the gate cannot do this for you: an
  all-clear for `design` says nothing about the run that produced the light
  figures, and a `sun-hours.json` written under a clearance that has since gone
  stale looks exactly like a fresh one.
- **Turn a design fork into a card rather than a paragraph.** A choice you are
  about to resolve on the person's behalf — bed here or there, one large tree or
  three small, gravel or flagstone — goes on the board with its options priced,
  and comes back to them as a decision:

```bash
python3 -m lib.doubts <slug> --add "Bed against the house, or out in the open?" \
    --kind choice --blocks design,bom --decisions 3 \
    --option "against the house|shelter, reads as intentional|rain shadow, needs irrigation|about \$120 of drip" \
    --option "out in the open|gets real rain|exposed to wind|no extra cost"
```

Design objections and doubt cards do different jobs and both are needed. An
objection says the yard will not support what was asked for. A doubt says nobody
is sure what the yard even is yet.

## Step 1 — Research the region, every time

Never carry a plant list from one garden to another. Search for:

- Native and regionally adapted plants matching each zone's **actual** light
  hours and the bloom window that matters
- The land-grant extension service planting calendar for that region
- What is genuinely available locally, which is narrower than what is hardy
- Mature size in *that* climate. The same shrub is three feet in Minnesota and
  eight in Georgia

Anchor choices to what blooms in the target month in that region. The single most
common failure is a garden that peaks six weeks off the date that mattered.

## Step 2 — Place by gradient, not by symmetry

Every bed has a gradient: sun to shade along its length, wet to dry across its
depth, exposed to sheltered. Put each plant where its conditions are, rather than
distributing evenly for visual balance. The sun model gives this per zone and per
month; use the months the plant is actually growing, not the annual average.

The rules that hold everywhere are in [reference.md](reference.md#design-rules).
The four that get broken most:

- **Space by mature spread, not by pot size.** A first-year bed should look
  slightly sparse. If it looks full on planting day, it is overplanted, and the
  plants that lose are the expensive slow ones
- **Usable depth is not bed depth.** Subtract rock bands, wall setbacks and
  edging. A 40-inch bed with a 14-inch drip-line rock band gives 26 inches, which
  is one row of shrubs, not two
- **Odd numbers, repeated.** Three or five of the same thing, and repeat the
  group. One of everything reads as a collection
- **Evergreen bones.** Most perennials look like nothing from November to March.
  A bed with no structure reads as abandoned rather than dormant

## Step 3 — Write it down as data

```bash
python3 -m lib.design <slug> --init
```

Each plant carries its own requirements, researched, with a source. There is no
plant database in this system on purpose: a shipped one would be wrong about half
of it, would not know the local cultivar, and would tempt everyone into skipping
the research that actually matters.

```json
{"name": "Gulf muhly", "botanical": "Muhlenbergia capillaris",
 "count": 5, "zone": "back_bed", "light": "full sun",
 "mature_spread_ft": 3.0, "mature_height_ft": 3.0,
 "water": "low", "ph_range": [6.0, 8.0], "bloom": ["Oct", "Nov"],
 "months": ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"],
 "evergreen": false, "role": "accent",
 "source": "Lady Bird Johnson Wildflower Center, 2026-08"}
```

`months` is when the plant is actively growing and therefore when its light
requirement applies. It matters: a spring ephemeral needs March, before the
canopy closes, and genuinely does not care what July looks like.

Record what is being kept, too. A tree that stays is part of the design and the
`must_keep` check looks for it.

## Step 4 — Let it object

```bash
python3 -m lib.design <slug>
```

This checks every plant against the measured yard and reports what it finds at
three levels:

- **blocking** — it will not survive, or the design contradicts a stated `must`.
  Change it
- **serious** — it will survive and disappoint. Usually a trade worth naming
- **note** — worth knowing, not worth changing anything for

What it checks: light against the zone's hours in the months that plant grows;
too *much* sun for a shade plant in a hot climate, which is a real failure people
never anticipate; water need against whether a hose reaches and whether the bed
sits in a rain shadow; sharp-drainage plants in slow soil, which is how rosemary
and lavender die over two years without anyone connecting it to the soil; pH;
total mature spread against the zone's actual square footage in both directions,
overplanted and sparse; every `must` in the vision; whether anything blooms on
the target date; winter structure; and one-of-everything.

**Nothing is silently substituted.** A `serious` objection is often a trade the
person is happy to make, and there is no way to know that from here. Raise it,
say what it costs, and let them choose.

When the model says a zone averages 4.7 hours but its sunniest cell reaches 6.3,
that is not a failure — that is a hot corner, and it is where the tomatoes go.

## Step 5 — Draw it

```bash
python3 -m lib.drawbeds <slug>              # from design.json's "layout" block
python3 -m lib.drawbeds layout.json --outdir maps/
```

Three bed types: `grid` for square-foot raised beds, `border` for long beds with
plants as circles at mature spread, `overview` for the yard plan. The schema is
in the module docstring.

**Render it and look at it.** Overlapping labels are the norm on a first pass.
More importantly, a plant placed at the wrong end of a bed is invisible in JSON
and obvious in a drawing, and so is a bed that is 40% empty at maturity.

Show the person the drawing before the plant list. They will correct a picture
instantly and a paragraph never.

## Step 6 — Say what it looks like when it is not at its best

Every design gets three sentences that nobody asks for and everybody needs:

- **Year one.** Small plants and a lot of mulch. Say it plainly, with when it
  fills in — usually year two for perennials, year three for shrubs
- **Off season.** What is standing in February
- **The bad year.** A late freeze, a hot dry August, a plant that fails. Which
  ones shrug it off, which are cosmetically damaged, and which die back entirely.
  Once sorted into those three buckets the contingency plan writes itself and the
  person knows what not to panic about

## Rules

- No plant goes in without a light requirement and a source for it
- Never quote a sun figure without saying whether the geometry behind it was
  measured or assumed. When the geometry is assumed, design to the pessimistic
  end of the range
- A fork in the design is theirs to settle. File it as a `choice` card with the
  options priced and put it in front of them, rather than picking quietly and
  mentioning the alternative in passing
- Never design against a provisional `sun-hours.json` without saying that is what
  is happening
- Where the site cannot support what they asked for, say so and offer the version
  that works. "You can't have a cottage garden" is unhelpful and usually wrong;
  "a loose planting inside a steel edge gives you that look and stays legible"
  is the same answer made useful
- A photograph of a garden in a different climate is not a plant list. Name the
  substitution that gives the same effect where they live
- Pollinator and amphibian gardens rule out several products people believe are
  organic and safe. Say which and why before anyone buys a spray, not after —
  see [reference.md](reference.md#pest-management-for-pollinator-and-amphibian-gardens)
