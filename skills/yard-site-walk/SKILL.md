---
name: yard-site-walk
description: Generate a yard-specific field checklist for measuring a property on foot, targeted at what that yard's record actually gets wrong - clustering the ranked gaps into sections, naming the disagreements between data sources in real units, printing what the record expects so it can be falsified, and teaching the measuring technique. Publishes to markdown and to a Google Doc with tickable checkboxes, then folds the returned readings back into site.json as measured. Use when someone is going outside to measure a yard, asks for a site walk or a measuring checklist, says the yard has changed since the data, wants to verify lot lines or tree or fence or house heights on the ground, or asks what to measure while they are out there.
---

# Yard Site Walk

Produces `<slug>/SITE-WALK.md`, and optionally a Google Doc with real checkboxes.
Its job is to convert a record built from public data into one built from
measurement — to move values from `parcel`, `osm`, `lidar` and `assumed`
provenance to `measured`.

**The checklist is generated from the record, never from a template.** A generic
"measure your fences, test your soil" list is a chore list, freely available
online, and it wastes the one asset a site walk has: someone standing in the yard
willing to hold a tape. What makes this worth writing is that it knows what *this*
yard's record is missing, what it is guessing at, and where its sources contradict
each other.

The test for every item: **the design will otherwise have to guess this.** If an
item fails that test, cut it. Say so in the checklist too, because a person who
believes the list is padded starts skipping things, and they will skip the wrong
ones.

## Step 1 — Read the record before writing anything

```bash
cd ~/personal/garden
python3 -m lib.yards <slug>                    # what this yard has
python3 -m lib.siteschema <slug> --assumed     # every assumption, with its note
python3 -m lib.gaps <slug>                     # ranked, priced, worst first
python3 -m lib.drawsite <slug>                 # look at the plan
```

Read `site.json`, and `vision.json` and `conditions.json` if they exist. Look at
the plan drawing; a checklist that asks for something already recorded reads as
carelessness.

`--assumed` is the single best input, because each assumption already carries a
note saying what it was based on and what would settle it. Those notes become
checklist items nearly verbatim.

Also read the **dates**. A lidar flight date and a city mapping vintage are what
justify asking someone to re-count their own trees, and stating the date is what
makes the request land as reasoning rather than busywork.

## Step 2 — Let the gaps choose the sections

```bash
python3 -m lib.gaps <slug> --json      # coverage.json, structured
```

`coverage.json` gives each gap a `section`, `label`, `unit`, `amount`, `detail`
and `how_to_close`. Two transformations turn that into a checklist:

**Cluster.** The raw list repeats — twenty separate `species of tNN` gaps are one
instruction, "identify the trees," with a table of which ones. Never ship the
unclustered list.

**Filter to what a person on foot can settle.** A gap closed by a lab, an API or
another skill does not belong in a field checklist. `no conditions.json at all`
is the top-priced gap on a fresh yard and it is a conversation, not a
measurement. Mention it as a pointer to `yard-conditions`; do not put it on the
list of things to measure.

Sections then exist because the record is weak there, and their order follows the
pricing. A section with nothing unknown in it should not exist at all.

## Step 3 — Name the disagreements, with numbers

Where sources conflict, the checklist's job is to say so and let one measurement
settle it. This is the most persuasive material available, so use it explicitly:

> Three data sources put the house 14.2, 15.7 and 20.6 ft off the front line, a
> 6.4 ft spread.

That sentence turns a tedious offset measurement into the resolution of a known
problem. Carry the spread in real units, and say which source is currently
trusted and why.

Never average conflicting sources, in the checklist or anywhere else. Report both
and let the tape decide.

## Step 4 — Print what the record expects, so it can be falsified

For anything the record already holds, give the person the current value and ask
them to contradict it. This is far more productive than an open question, because
it is much easier to notice that a tree is missing than to inventory a garden
from scratch.

A tree table is the standard case — id, height, crown radius, and roughly where,
with the survey date in the heading:

| id | height | crown radius | roughly where |
|---|---|---|---|
| t06 | 48 ft | 25 ft | back yard, west side — 15 ft E, 85 ft S |

Positions come from `site.json` in the yard's frame; convert to whatever the
person can pace out, and say the distances are for matching trees to records
rather than for precision.

Then ask the three questions the table cannot answer itself: which of these still
exist, what has been **removed**, and what has been **planted since** and is
therefore absent from the table entirely.

Flag the contradictions the record cannot see. On one yard the person named a
young lacey oak in the front garden, while the only front-garden tree on record
was 38 ft tall with a 22 ft crown — so either it postdates the flight or the two
are different trees, and one look settles which.

## Step 5 — Take the must-keeps from vision.json

Anything named as beloved, must-keep or to-be-removed has to be on the map before
it can be designed around or budgeted for, and it appears in no dataset. Pull
them by name — the paddle cactus, the peach, the roses coming out, the straggler
daisy worth cultivating — and ask for position, size, condition, and how much sun
each one gets.

Ask where a wanted plant is **already thriving unaided**. That is direct evidence
of where it will thrive, and it is cheaper than any amount of modelling.

## Step 6 — Add the technique

Read [FIELDCRAFT.md](FIELDCRAFT.md) and copy in what this walk needs: the kit,
the rules that make a measurement real, the height methods, the tree
identification photographs.

Include it generously for a first-time walker, and do not assume experience means
they know it. The failure modes are silent — a chained measurement looks exactly
like a good one, and a phone compass is confidently wrong indoors.

Two items earn their place on nearly every walk:

- **House corner labels A/B/C/D and the perpendicular offsets out to the
  boundary.** These are what let every other measurement be fitted to the
  recorded lot. Usually the highest-value items on the page
- **Fence height and opacity.** Rarely recorded, because lidar cannot resolve
  anything that thin, and decisive for low winter sun on any bed near a boundary.
  The sun model takes a different transmissivity for solid board than for a
  picket fence with 40% gaps

## Step 7 — Rank it, so a partial walk still pays

End with **"if you only do five things."** Most walks are partial: it gets hot,
the tape kinks, someone has to collect a child. An unranked list degrades badly,
because the items that get dropped are the ones at the bottom of the page rather
than the ones that matter least.

Say the trip length honestly, and if soil work is involved say it is two trips
and why — the probe and the perc test need moist ground and everything else wants
a dry day.

## Step 8 — Publish

Write `<slug>/SITE-WALK.md`, then record the pointer in `site.json` under
`pending_site_walk` alongside the existing `verify_on_site` list, with a note
saying that until the walk returns, every geometry figure is public-data
provenance rather than ground truth.

For a Google Doc with tickable checkboxes:

```bash
python3 skills/yard-site-walk/scripts/publish_checklist.py <slug>/SITE-WALK.md
```

It writes `SITE-WALK.html` and `SITE-WALK.runs.json`, then:

1. `gdrive createDocFromHTML(name=..., html=<the .html>)`
2. For each string in `runs.json`, in order, `gdrive createParagraphBullets(
   documentId=..., bulletPreset='BULLET_CHECKBOX', textToFind=<string>)`. One
   call converts one whole run of consecutive items
3. Verify with `gdrive downloadFile(exportMimeType='text/markdown')`, then

```bash
python3 skills/yard-site-walk/scripts/publish_checklist.py <slug>/SITE-WALK.md \
    --verify <the exported .md>
```

The script's docstring explains the seven Docs and MCP defects it works around.
Three are worth knowing before you start:

- **Never put a horizontal rule before a heading.** The importer gives the rule
  the heading's style and demotes the heading to bold body text. Rules are
  dropped for that reason
- **The whole document travels as one inline `html` argument.** Drive converts
  text/html to a Doc, but the MCP `uploadFile` tool rejects it —
  `convertToGoogleFormat` allows only Office formats — so `localPath` is not an
  escape route. A 107-item walk is about 33 KB of argument. Do not spend a call
  looking for a file-based path
- **Do not hand-roll the verification count.** The markdown export wraps every
  list item in a blockquote, so items come back as `> - [ ] Tape the...`. A
  regex anchored on whitespace matches nothing and reports total failure on a
  document that is perfectly fine. `--verify` counts them correctly, and
  distinguishes a genuine miscount from a `createParagraphBullets` pass that
  never ran — the latter leaves items as plain bullets that look right and do
  not tick. It also allows for ordinary `-` bullets that are prose rather than
  items to tick, such as a revision summary, and reports only the surplus. If
  it says **OVERREACHED**, a `textToFind` ran past the end of its own list and
  converted a prose bullet, which means that run matched the wrong paragraphs

A "not found" from step 2 means the markdown and the HTML have drifted.
Regenerate both; do not hand-patch a string.

## Step 9 — Fold the answers back in

The checklist is worthless if the readings never reach the record, and this is
the step most likely to be skipped.

When the measurements come back:

- Write each into `site.json` with `provenance: measured`, replacing the
  assumption and **deleting its note** rather than leaving a stale one behind
- Where a measurement contradicts a source, record what it contradicted. That is
  how the next yard learns which sources to distrust
- Re-run `python3 -m lib.siteschema <slug>` and `python3 -m lib.drawsite <slug>`
  and look at the plan again
- Re-run the sun model, because real tree species and real fence heights are
  usually the two largest corrections it will ever get
- Clear `pending_site_walk` and re-run `python3 -m lib.gaps <slug>` to show what
  the walk actually bought

Then say what changed. Someone who spent three hours in the sun with a tape has
earned a straight answer about what it moved.

## What not to do

- Do not ship a template. If the checklist would read the same for a different
  yard, it has not done its job
- Do not include an item the design will not use. Padding teaches people to skip
- Do not ask for something the record already holds at good provenance
- Do not ask an open question where the record can offer a value to contradict
- Do not put soil tests on a dry-day walk without saying it needs a second trip
- Do not average two disagreeing sources instead of letting a measurement settle it
- Do not leave the returned readings sitting in the conversation. They go into
  `site.json` with provenance, or the walk did not happen
