# Yard Design — Method Notes

Detail behind the SKILL.md workflow. Read the section you need.

## Site quirks that break plans

Most of these are now measured rather than asked about — `site.json` carries the
geometry and `sun-hours.json` the light. What survives as a question is what no
dataset knows.

**Rain shadow.** Beds under a roof overhang, awning or dense canopy may get
almost no natural rain even in a wet climate. Consequences: irrigation is the
entire water supply rather than a supplement; it cannot be winterised by shutting
off, only by turning down; and even drought-tolerant natives need occasional deep
water forever, because "natives need no water" quietly assumes they get rain.
Worth asking directly: does rain actually reach that bed, or does the roof throw
it somewhere else? Record it as `water.rain_shadow_zones` in `conditions.json` and
the design linter will use it.

**Roof drip lines.** Where a roof has no gutter, water falls in a concentrated
line and hits hard. Find how far from the wall it lands — usually near the eave
edge, which can be most of the way across a narrow bed. A river-rock band under
the line absorbs the impact and stops soil splash, which spreads fungal leaf
spot. Site splash-tolerant plants beside it and keep rot-prone plants like
rosemary and lavender well away, crowns set high.

**Usable depth is not bed depth.** Subtract rock bands, wall setbacks and edging.
A 40-inch bed with a 14-inch rock band gives 26 inches: one row of shrubs, not
two. Getting this wrong is how beds end up overplanted and half the plants die in
their second summer. Record the loss as `unplantable_sqft` on the zone so the
space check is honest.

**Corners and junctions.** Two beds meeting at a corner get planted
independently and the join looks accidental. Repeat a plant, or a texture, on
both sides of the turn.

Before designing the turn, pin down **where each bed's measurement actually
stops.** This is the single most common geometry error. When someone says "a
19-foot bed and a 13-foot bed that meet at the corner," the corner square itself
is either included in one of those numbers or it is a third, unmeasured piece of
ground. Ask directly: does the 19 feet run to the house wall, or all the way out
to the far edge of the other bed? Then draw it and show them; they will correct
it instantly from a picture and never from a paragraph.

A planted corner also behaves differently from the rest of both beds. It usually
sits past the wall and past any overhang, so it catches rain the sheltered
stretches do not, and it is viewed from two sides instead of one, which rules out
anything that only looks good from the front.

**Slope and drainage.** Water moves downhill and collects. The bottom of a slope
is a different microclimate from the top. `python3 -m lib.parcel <slug> --slope`
gives the fall across the lot; a bare-earth model on a 1 m grid will not see a
low wall or a raised bed, so walk it too.

## Design rules

**Space by mature spread, not by pot size.** A 1-gallon perennial that matures at
3 feet needs 3 feet. First-year beds should look slightly sparse. If a new bed
looks full, it is overplanted.

**Sort along the gradient.** Every bed has one — sun to shade along its length,
wet to dry across its depth. Place each plant where its conditions are rather
than distributing evenly for visual balance.

**Layer by height, accounting for the sun's path.** Tall at the back is the
default, but in winter the sun sits low, so tall plants on the equator-facing
side cast much longer shadows than they do in summer. `shade-clocks.png` from the
sun model shows this directly.

**Odd numbers, repeated.** Groups of 3 or 5 of the same plant, with that grouping
repeated along the bed, reads as designed. One of everything reads as a plant
collection.

**Evergreen bones.** Some percentage of every bed should hold structure when
nothing is blooming. Aromatic evergreen mounds do double duty in beds people walk
past.

**Bloom succession against the target date.** Chart what blooms in each month of
the goal window. It is easy to assemble a beautiful palette that all peaks in the
wrong month.

**Guaranteed colour as insurance.** For a hard deadline, include bulletproof
seasonal annuals that will look right on the day regardless of how the perennials
perform.

**A hard edge buys a loose middle.** The most useful single move in the whole
craft. Steel, stone, brick set flush or a mown strip reads as intent, and the eye
then forgives a great deal of looseness inside it. This is how someone gets a
cottage garden that does not look neglected, and it resolves the most common
tension in `vision.json` outright.

## Pest management for pollinator and amphibian gardens

The philosophy: healthy plants, physical barriers, and tolerance for minor
damage. A garden with chewed leaves and butterflies beats a perfect garden with
neither.

**Products people believe are safe but are not**, in a garden built for
butterflies:

| Product | Why it is a problem |
|---|---|
| Bt (Bacillus thuringiensis) | Kills all caterpillars, including the butterflies you planted host plants for |
| Neem | Kills caterpillars and harms bees on contact |
| Spinosad | Highly toxic to bees while wet; kills caterpillars |
| Pyrethrin / pyrethrum | Broad-spectrum; kills beneficials indiscriminately |
| Systemics / neonicotinoids | Make the entire plant toxic for months, including nectar and pollen |

Frogs and toads absorb chemicals through their skin, so anything near a water
feature or damp shelter needs a higher bar still.

**Actually safe interventions:** water blasts, hand-picking, floating row cover
installed before pests arrive, iron phosphate slug bait, and Bti dunks for
mosquito larvae in standing water. Insecticidal soap on a specific overwhelmed
vegetable, applied at dusk, is the realistic ceiling.

**Escalation ladder** for any pest: identify it, confirm it is actually causing
damage worth acting on, physical removal, barrier, then targeted treatment on
that plant only, at dusk.

**Ask about neonicotinoids at the nursery.** Plants treated with systemics poison
caterpillars for months after purchase. This single question matters more than
anything else on a butterfly garden shopping trip.

## Nursery questions worth asking

1. "Has this been treated with neonicotinoids or systemic insecticides?"
2. "Is this greenhouse-grown or hardened off?"
3. Slide the plant out of its pot: circling matted roots mean root-bound. A
   smaller plant with good roots beats a bigger root-bound one every time.
4. "When did this shipment arrive?"
5. "What would you substitute?" — bring the bed maps; staff at good independents
   will point to an equivalent on the spot.

## Freeze and heat contingency

For a plan with a hard date near a seasonal risk, sort every plant into three
buckets: shrugs it off, cosmetically damaged but structural, and dies back
entirely. Then the contingency plan writes itself, and the person knows what not
to panic about.

Practical notes: frost cloth works by trapping ground heat, so it must reach the
ground and be weighted at the edges — draping it over the tops of plants does
nothing. Water deeply before a freeze, since moist soil holds far more heat than
dry. Protect irrigation hardware separately from plants; battery timers crack and
hoses split.

`site.json` carries the frost dates and their spread under `climate`. Plan from
the 10% risk date rather than the median, and remember the derived dates run
early against station normals.

## Where the old garden-planning skill went

This skill replaced `garden-planning`'s design half. The rest distributed:

| was | now |
|---|---|
| intake | `new-yard` and `yard-conditions` |
| climate and frost research | `yard-survey`, via `lib/climate.py` |
| bed geometry, sun questions | `yard-survey` and `yard-sun-model` |
| `draw_beds.py` | `lib/drawbeds.py` |
| `build_doc.py` | `lib/builddoc.py` |
| schedule and shopping | `yard-schedule` and the `sourcing-scout` subagent |

`raised-bed-rotation` stays as its own skill. It is a genuinely distinct
recurring workflow and it now reads bed geometry from `site.json` and what is on
hand from `conditions.json`.
