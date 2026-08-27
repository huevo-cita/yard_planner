---
name: yard-survey
description: Turn an address into a measured yard - lot lines from county GIS, neighbouring building heights from OpenStreetMap, tree and roof heights from USGS 3DEP lidar, dimensions from photographs, ground slope from USGS elevation, and frost dates and hardiness zone derived from thirty years of daily weather. Use when starting a new yard, when lot dimensions or tree heights are unknown, when someone asks how big their yard is or how tall that tree is, or when a shade model needs an obstruction model to run on. Writes site.json.
---

# Yard Survey

Produces `site.json`: the yard's geometry and everything solid enough to cast a
shadow. `yard-sun-model` runs on it, `yard-design` places beds inside it, and
`yard-schedule` prices work against it. Everything downstream inherits its errors,
so measure what can be measured and label the rest as assumed.

The order below is deliberate. Each step narrows what the next one has to guess.

```bash
cd ~/personal/garden          # every command below runs from here
```

## Step 1 — Register the yard and find it on the earth

```bash
python3 -m lib.yards --new <slug> --address "<full street address>"
python3 -m lib.parcel --geocode "<full street address>"
```

Geocoding returns several candidates. **Show them and let the person pick.**
Addresses are ambiguous and silently choosing the first one is how a yard ends up
in the wrong state.

Then set the frame. The yard's plan coordinates are inches from an origin, and
`frame.anchor` pins that origin to a real lon/lat so that everything imported
later lands in the right place. Use a corner that is unambiguous on an aerial
image and identifiable on the ground: a fence corner, a building corner, the
intersection of two property lines.

Record the yard's rotation too. Almost no lot is square to north, and a shade
model that thinks it is will put the afternoon shadow in the wrong place.

## Step 2 — The lot itself

Launch the **parcel-scout** subagent with the address and coordinates. It works
through the county GIS portal, the city open-data portal, the assessor and OSM,
and comes back with the parcel polygon, the recorded dimensions, the building
footprint, and the local setback and fence-height rules.

It has a high dead-end rate, which is why it runs in its own context. If it comes
back empty, that is a real answer: the lot gets measured with a tape instead, and
the boundary is recorded with `provenance: measured`.

Whatever it returns, say this out loud when handing over a boundary: **a parcel
polygon is good enough to decide where a bed goes and not good enough to decide
where a fence goes.** A foot of error is normal and does not matter for planting.
It matters enormously for a structure on a property line, and that is a survey.

Where the recorded lot area and the polygon's computed area disagree, the polygon
is the suspect one. Report both.

## Step 3 — What the neighbours block

```bash
python3 -m lib.parcel <slug> --context [--radius 80]
```

OpenStreetMap building footprints within the radius, converted into the yard's
frame as vertical prisms. In US cities the height tags are frequently imported
straight from municipal lidar, so they are real numbers rather than guesses; the
tool records which for each building, and anything it had to assume shows up as
`assumed, no height or levels tagged`.

This step matters more than people expect. A three-storey row house across a
narrow street takes the entire morning off a side yard, and no amount of
measuring your own fence will reveal it.

Two things to watch:

- **The yard's own house must be excluded** and modelled explicitly under
  `obstructions.house`, because OSM often merges an attached row into one polygon
  with one height. If yours is the short house in a tall row, importing that
  polygon is a building-sized error
- **A merged row needs clipping** at the property line. Use `--exclude-way` for
  whole buildings and the `clip` argument for a partial one

## Step 4 — Heights from lidar

```bash
python3 -m lib.lidar <slug>            # look first
python3 -m lib.lidar <slug> --write    # then commit
```

USGS 3DEP classified point clouds, free and needing no key. This is the step that
answers the question the sun model cares most about, because tree crown size is
routinely the largest single unknown in the whole model. On one measured yard it
was worth two and a half hours of light a day, which is the difference between a
vegetable bed and a shade garden.

Per tree it derives height, crown radius, crown base height and trunk position.
Per building, eave and ridge height.

Read what it says about the survey before trusting it:

- **The flight date.** It reads the GPS timestamps in the points, so the date is
  the real one rather than something inferred from a project name. A tree planted
  after the flight is not in the data, and the tool refuses to overwrite a
  modelled tree where the survey demonstrably predates it
- **Leaf-off surveys.** Much 3DEP flying is done in late winter for better ground
  returns. A leaf-off crown radius is an underestimate, and the tool says so
- **Coverage.** Not everywhere is flown. No coverage means falling back to photo
  measurement or a clinometer

## Step 5 — What lidar cannot reach

Launch the **photo-surveyor** subagent for anything left: eave heights, fence
heights, awning projections, window sills, wall dimensions. It needs a photograph
and one object of known size in the frame, prefers a known rectangle so it can
rectify the whole plane, and returns every number with an error bar.

It will refuse tree crowns, and it is right to. Photogrammetry cannot find the
edge of a fuzzy object at unknown depth; lidar can.

Fences are usually simplest to measure with a tape. Record height, position and
opacity — a solid board fence and a picket fence with 40% gaps do very different
things to low winter sun, and the model takes a transmissivity for each.

## Step 6 — Slope

```bash
python3 -m lib.parcel <slug> --slope
```

USGS 1 m bare-earth elevation at each corner, and the fall across the lot. This
decides whether water leaves the yard or sits in it, and where it goes.

It is a bare-earth model on a 1 m grid, so it will not see a low retaining wall
or a raised bed, and a fall of under a foot across a small lot is inside its
noise. It tells you the lie of the land. A level and a string line tell you the
grade.

## Step 7 — Climate

```bash
python3 -m lib.climate <slug> --zip <zip> --write
```

Thirty years of daily minimum and maximum temperature for the actual coordinate,
from which it computes the frost dates directly rather than quoting a station
average: last spring frost and first fall frost at 10%, 50% and 90% risk, the
frost-free season and its spread, growing degree days, days over 95 and 100 F,
and the hardiness zone from the mean annual extreme minimum. It cross-checks that
zone against the published USDA 2023 map and flags a disagreement rather than
splitting the difference.

**Use the 10% risk date, not the median.** The median is a coin flip, and the
underlying reanalysis runs warm on overnight minima because it does not resolve
the shallow cold layer that forms on calm clear nights — so the median last-frost
date comes out one to two weeks early against station normals. The tool says so
in its output. The 10% date is both what a schedule should plan from and far less
sensitive to the bias.

If the county extension office publishes a frost date for the actual town, it
beats all of this. Pass it in:

```bash
python3 -m lib.climate <slug> --local-last-frost "Mar 01" \
    --local-first-frost "Nov 30" --local-source "Travis County AgriLife" --write
```

Worth one web search per yard, and worth asking whether the person already knows
their local date — someone who has gardened a place for a decade usually does,
and their answer is better than a grid cell.

## Step 8 — Check the work

```bash
python3 -m lib.siteschema <slug>       # validate, and list every assumption
python3 -m lib.drawsite <slug>         # plan, context map, elevation, section
python3 -m lib.gaps <slug>             # what is still missing, worst first
```

Look at the drawings. A number that is wrong by a factor of ten is invisible in
JSON and obvious in a plan view. Check that the house is where the house is, that
north points where north is, and that the trees are on the correct side.

Then report the gaps. `lib.gaps` ranks them by consequence in real units — a
geometry gap is priced by re-running the sun model across the plausible range and
reporting the spread in hours of light a day, so "we do not know the crown base
height" arrives as "this is worth 1.4 hours a day, and here is the ten-minute way
to settle it."

## Recording provenance

Every value carries where it came from: `measured`, `lidar`, `photo`, `parcel`,
`osm`, `survey`, `reported`, `derived`, or `assumed`. This is not bookkeeping. It
is what makes the gap ranking work, and it is what stops an assumption made in
week one from being quoted as a fact in week six.

```bash
python3 -m lib.siteschema <slug> --assumed    # every assumption, with its note
```

When recording an assumption, write down what it was based on and what would
settle it. "20 ft crown base assumed; if the leafy crown starts high, low western
sun passes under it through bare trunks" is a note that tells the next reader why
to care. "assumed" alone is not.

## Rules

- No invented precision. A tape gives inches, lidar gives a foot, OSM gives what
  the city uploaded, and a satellite estimate gives whatever you were willing to
  believe. Carry the difference through
- An assumption stays labelled an assumption until something measures it
- Where two sources disagree, report both and say which is better and why. Never
  average them
- The person often knows things no dataset does: which tree came down, where it
  floods, what the neighbour is planning. Ask, and record it as `reported`
