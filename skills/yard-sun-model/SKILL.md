---
name: yard-sun-model
description: Compute how many hours of direct sun every part of a yard gets in every month of the year, from its measured geometry - accounting for the house, fences, neighbouring buildings, and tree crowns that leaf out and drop. Answers "is this bed full sun or part shade", "why is the rose corner dying", "how much light would I lose to a taller fence", and "when does the patio get afternoon sun". Use before choosing any plant, and whenever a proposed wall, trellis, tree or removal needs pricing in hours of light. Writes sun-hours.json and a set of maps.
---

# Yard Sun Model

Plant tags say full sun, part sun, part shade. Nobody knows which one their bed
actually is. People guess from a memory of standing in the yard at two o'clock in
July, which is the single sunniest moment of the year and tells you almost
nothing about April.

This computes it: for every square foot of the yard, in every month, the hours of
direct beam sunlight reaching the ground, given the house, the fences, the
neighbours' buildings and the trees.

Requires `site.json` from `yard-survey`. The model is only as good as that
geometry, so read the gap report before believing a number to a tenth of an hour.

## Running it

```bash
cd ~/personal/garden
python3 -m lib.doubts <slug> --open        # what is still in question
python3 -m lib.sunmodel <slug> --quick     # coarse, a few seconds, for iterating
python3 -m lib.sunmodel <slug>             # the real run and every drawing
```

**The full run refuses to start while a doubt that blocks it is open.** That is
deliberate, and it is aimed at one specific waste: a geometry doubt voiced in
prose, the model run anyway, the doubt then settled, and the whole run thrown
away. `--quick` is deliberately exempt, because probing across a range is how a
geometry doubt gets settled in the first place.

So when the geometry is in question, the order is: file the doubt, price it,
settle what matters, then run.

```bash
python3 -m lib.doubts <slug> --add "Is the west fence 6 ft board or 3 ft rail?" \
    --kind fact --blocks sunmodel,design \
    --detail "the street photo predates the rebuild" \
    --how "stand at the west line and look" --effort "two minutes"
python3 -m lib.doubts <slug> --price
```

A `probe` on the card is what makes `--price` able to answer it without anyone
going outside — the path into `site.json`, the plausible values, and the zone the
thing actually rules:

```json
"probe": {"path": "obstructions.fences.0.height",
          "values": [36.0, 72.0, 96.0], "zone": "West bed"}
```

Scope it with `zone` where the unknown governs one bed. An awning over a
four-foot bed averages away to nothing over the whole yard and completely decides
the ground underneath it.

A doubt that moves the answer less than about a tenth of an hour a day, and does
not straddle a light-category threshold, settles itself as `probed-immaterial`
with the spread recorded. One that spans 5.7 to 7.5 hours does not, because it
crosses the full-sun line and therefore decides half a plant list.

It writes to the yard's `maps/`:

| output | what it answers |
| --- | --- |
| `sun-hours-monthly.png` | twelve maps, one per month. The main result |
| `sun-hours-leaf-state.png` | the shoulder months in both leaf states |
| `shade-clocks.png` | hour by hour on the solstices and equinoxes: *when*, not just how much |
| `sun-path.png` | the sun's track against the obstruction horizon |
| `crown-sensitivity.png` | how much of the answer rides on the unmeasured tree numbers |
| `sun-hours.json` | every number, machine-readable, for design and gap ranking |

## How it works, and where it can be wrong

The yard floor becomes a grid. For each cell the opaque obstructions — walls,
fences, buildings — collapse once into an obstruction horizon: the highest
blocked altitude in each of 360 compass bins, computed analytically from wall
segments rather than by sampling points, so a fence six inches from a cell does
not produce aliasing gaps.

Tree crowns are handled separately and deliberately. They cannot go in the
horizon, because light passes *underneath* a crown through the bare trunks, which
is exactly why crown base height changes the answer instead of being averaged
away. Each crown is an ellipsoid tested with an exact ray intersection at every
time step. A deciduous crown switches transmissivity on its own leaf-on and
leaf-off dates, so a yard can hold an evergreen and a bare maple at once and the
model treats them differently in March.

The sun steps every five minutes in apparent solar time from sunrise to sunset on
a representative day per month. Each step contributes its five minutes if the
beam is clear, nothing if something opaque is in the way, and the foliage
transmissivity if the only thing in the way is leaves.

Four things it does not model, all worth saying when reporting results:

- **Clouds.** These are geometric sun hours: the light available if the sky is
  clear. A bed with six geometric hours in a cloudy June gets less usable light
  than the number suggests. It is the right basis for comparing one part of a
  yard to another and the wrong basis for comparing two climates
- **Reflected and diffuse light.** A north-facing bed against a white wall grows
  things the direct-beam number says it should not. The model floors at zero
  direct sun; the plant does not
- **The far horizon.** Hills and distant tree lines are not in the model unless
  they are in `site.json`
- **The future.** A tree grows about a foot a year. A five-year plan should ask
  what the model says with the crowns ten to twenty per cent larger

## Reading the output

The zone table is the practical result. Per zone, per month, three numbers:

- **effective** — hours weighted by foliage transmissivity. This is the honest
  one and the one to plan from
- **clear** — hours with no obstruction at all, which is what the sky offers
- **best_cell** — the sunniest single cell in the zone. When effective is low and
  best_cell is high, the zone is not uniformly shady; it has a hot corner, and
  that is a design opportunity rather than a limitation

Thresholds, matching how nurseries label plants:

| hours | category |
| --- | --- |
| 6 or more | full sun |
| 4 to 6 | part sun |
| 3 to 4 | part shade |
| 1.5 to 3 | shade |
| under 1.5 | deep shade |

Two things get missed when reading only the monthly maps:

**Which months matter depends on the plant.** A tomato needs June and July. A
spring ephemeral needs March, before the canopy closes, and does not care what
July looks like. A rose needs the whole season. When a zone is being judged, judge
it against the months that plant is actually growing.

**Timing is not the same as quantity.** Four hours of morning sun and four hours
of afternoon sun are not interchangeable in a hot climate. Afternoon sun in Texas
in August is a stress, not a benefit, and the same four hours in the morning is a
gift. That is what `shade-clocks.png` is for. Look at it before recommending a
plant into a hot-climate west-facing bed.

## Pricing a change

The model's most useful trick is answering what-if in hours rather than in
opinions.

```bash
python3 -m lib.sunmodel <slug>       # renders <barrier>-scenarios.png for each
                                     # proposed barrier in site.json
```

Add a candidate to `obstructions.proposed_barriers` in `site.json` — a taller
fence, a privacy screen, a trellis, a pergola — and the run reports what each
zone loses. This turns "would a six-foot screen there be a problem" into "it costs
the vegetable bed 1.2 hours in May and nothing in July."

The same applies in reverse. To price removing a tree or limbing it up, edit its
height or crown base in `site.json`, re-run with `--quick`, and compare. Always
say which direction the assumption cuts.

## When the answer is uncertain

```bash
python3 -m lib.gaps <slug>       # gaps and open doubts, one ranked list
```

Geometry gaps are priced in hours of light a day by re-running the model across
the plausible range of each unknown. On one measured yard, crown spread alone
spans 2.2 to 4.7 hours a day, which is the difference between a vegetable bed and
a shade garden and is not a rounding error.

**Report the spread, not the midpoint,** when the inputs are assumed. "This bed
gets between two and five hours depending on how big those crowns really are, and
here is the ten-minute way to settle it" is a true statement. "This bed gets 3.4
hours" is not, and it will get a hundred dollars of sun-loving plants killed.

`crown-sensitivity.png` shows this visually and is worth putting in front of
someone before they buy anything.

## Rules

- Never quote a sun-hour figure without saying whether the geometry behind it was
  measured or assumed
- A geometry doubt goes on the board before the full run, not into a caveat
  alongside its results. If the doubt is worth voicing it is worth blocking on,
  and if it is not worth blocking on, probe it and say it settled
- A run forced past an open doubt stamps `sun-hours.json` provisional. Never
  quote a provisional figure without the word
- Quote hours to one decimal at most. The model steps in five-minute intervals on
  one representative day a month; a second decimal is invented
- Say "geometric direct-beam hours under a clear sky" the first time a number is
  given. It is what makes the number comparable across a yard and it is not the
  same as what a plant experiences
- A north-facing wall reading zero is a real result and not a dead zone. Say what
  grows there rather than only what does not
