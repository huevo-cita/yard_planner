# Fieldcraft

The generic half of a site walk: how to take a measurement that can be trusted,
and how to get a height without a ladder. Copy what a given walk needs into the
checklist; leave out what it does not. The yard-specific half — which sections
exist at all, and what the record already believes — comes from `SKILL.md`.

Most of this is worth stating even to someone experienced, because the failure
modes are not obvious and they are silent. A chained measurement looks exactly
like a good one.

## Kit

Worth buying before a first walk:

- **100 ft open-reel tape**, about $20, and the single most important item. A
  25 ft tape cannot cross a 115 ft lot without chaining, and chaining
  accumulates error
- **Marking flags**, golf tees or bamboo skewers, twenty or more, for trunks,
  bed corners and tape crossings
- **A story pole**: an 8 ft 1×2 banded every foot in alternating black and
  white. The cheapest measuring tool anyone will ever make, and it solves
  heights and photo scale at once
- **Mason's string** and a **line level**, about $5, for the slope check

Usually already owned: a 25 ft retractable tape, a long screwdriver or two feet
of rebar for probing, jars and ziplock bags for soil, a clipboard, and a
**pencil** rather than a pen because pencil still writes on damp paper. An
extendable painter's pole, if there is one, is the best eave-height tool there
is.

Two people roughly halves the error rate: one holds the tape end, one reads and
writes. Budget two to three hours for a first walk on a suburban lot.

## The rules that make a measurement real

1. **Baseline and offsets, never a chain.** Stretch the long tape along a
   straight fixed line — a house wall, a fence run — leave it lying there, and
   record everything as *(distance along the tape, perpendicular distance out
   from it)*. Measuring A to B to C to D instead makes every error permanent and
   cumulative.
2. **Triangulate any point off two fixed references.** For a trunk or a bed
   corner, take its distance from **two** points that can be identified again;
   house corners are ideal. Two distances pin a point. One does not.
3. **Read running dimensions off one tape**, not tip to tip. If a bed starts at
   12 ft along the wall and ends at 19 ft 6 in, record both numbers rather than
   "7 ft 6 in long."
4. **Nearest inch, and write the unit every time.** Feet-and-inches or decimal
   feet are both fine. Mixing them silently is how a 6 ft 3 in fence becomes
   6.3 ft.
5. **Photograph the tape in place** for anything that matters. A photo with the
   tape visible can be re-read later; a number in a notebook cannot be checked.
6. **Measure twice, from opposite ends.** If the two disagree by more than an
   inch, measure a third time. Do not average two numbers you do not trust.
7. **3-4-5 to test a right angle.** Three feet along one edge, four along the
   other, and the diagonal between the marks must be exactly five. Works at any
   multiple.
8. **Do not trust a phone compass near a building.** Stucco wire, wiring,
   flashing and fences deflect a magnetometer badly. On one yard in this system
   the phone read **13° off** against a recorded plat and a lidar survey that
   agreed with each other to 0.4°. Orientation comes from the lot lines; a phone
   will not improve it.
9. **Write down what was not measured.** A known gap is manageable. A gap that
   looks like a measurement is not.
10. **Bring back raw readings, not tidied ones.** "6 ft 2 in at the west end,
    5 ft 9 in at the east" is far more useful than "about 6 ft," because the
    variation is itself the finding.

## Heights, without a ladder

In descending order of accuracy:

1. **Painter's pole.** Extend until it touches the eave underside, mark it, lay
   it down and measure the pole. Good to an inch, and the best method there is.
2. **Story pole in a photograph.** Stand the banded pole flat against the wall,
   photograph square-on from 20 ft or more, count bands. Good to a few inches.
3. **Courses.** Measure **ten** courses of brick or siding with the tape and
   divide by ten, then count courses to the eave. Never assume a nominal course
   height; brick sizes vary and siding exposure varies more.
4. **Clinometer app.** Stand a measured distance back, sight the target, then
   `height = distance × tan(angle) + eye height`. Pace the distance with the
   tape, not with feet. Expect ±5%, which is fine for a ridge and too coarse for
   an eave.

Measure an eave at **three points** along a wall, not one. Ground falls across
most lots, so a single reading is a single reading rather than the eave height.

Also take the **roof overhang projection**, wall face to the outer edge of the
fascia. It is a small number with large consequences: it sets how much summer
sun the wall blocks and where the drip line lands.

## Positions and outlines

Label the four outside house corners and use the labels all day. **A** front-left,
**B** front-right, **C** back-left, **D** back-right, with left and right taken
from the street. Then tie the house into the lot with perpendicular offsets from
each corner out to the nearest boundary.

Those offsets are usually the highest-value measurements of the whole walk,
because they are what lets everything else measured on the ground be fitted into
the recorded lot geometry.

Take all four walls **and one diagonal**. Four wall lengths alone can describe
several different shapes; the diagonal fixes which one, and reveals that the
building is not square when it is not.

A property line is not the kerb. Where there is no fence or marker, measure to
something real, and write down what was measured to.

## Slope

String between two stakes, levelled with a line level, then measure string to
ground every 10 ft. Do it across the width and again front to back.

This is worth ten minutes because it catches what a 1 m bare-earth elevation
model structurally cannot see: retaining walls, terraces, swales, a raised
patio, a berm.

## Trees

Usually the most valuable thing on the walk, because crown geometry is routinely
the largest unknown in the sun model, and because **evergreen or deciduous
decides what a shaded area is for**. A leaf-off lidar flight cannot tell the
difference, and the commonest large shade tree in much of the south — live oak —
is evergreen.

Per tree, on the lot or overhanging it:

- **Four identification photos**, and all four are needed: a leaf top *and*
  underside, since the underside carries the diagnostic hairs; bark filling the
  frame; a twig showing how the buds sit on the stem; and the whole tree for
  form. Plus any acorn, nut, fruit or seed, on the tree or on the ground
- **Evergreen or deciduous.** If they have lived through a winter there, what
  they remember counts as an answer
- **Trunk position**, triangulated from two house corners
- **Trunk diameter at 4 ft 6 in.** Measure the circumference and divide by 3.14;
  easier than a diameter. This is the standard forestry measure and it is how
  growth gets tracked over years
- **Crown spread in four directions** from the trunk, walking out to the drip
  line. Crowns are rarely round, and a leaf-off survey reads them narrow
- **Lowest live branch.** This decides whether low morning and evening sun
  passes underneath, and lidar-derived crown base often sits at the method's
  floor rather than at a measured value
- **Health**: deadwood, cavities, lean, storm damage, surface roots

## Soil

The tests themselves and the commands that record them belong to
`yard-conditions`; do not restate its detail. What matters here is the field
logistics, which is the part that gets a walk wrong:

**The compaction probe and the percolation test need moist soil**, a day after
rain. Dry clay reads like concrete whatever its structure, and a dry perc test
reads up to twice too fast. The rest of the walk wants a dry day. So a walk that
includes soil work is **two trips**, and saying that up front is better than
having the numbers come back useless.

Sample from at least three places. A fill lot varies wildly across twenty feet.

## Photographs

- Something of known size in every frame. One exactly measured door or window
  opening turns every later photograph into a measuring tool
- Square-on to the plane being measured, and as far back as the space allows
- Name or number the files against the section they belong to
- Photograph the **sketch** as well. A rough plan with dimensions written on it
  beats a tidy list every time
