---
name: raised-bed-rotation
description: Plan the seasonal turnover of a raised vegetable bed - decide what to plant now based on the local calendar and the bed's crop-rotation history, lay it out square-foot by square-foot, and give dated prep, seed-starting, trellising, pruning and harvest tasks. Maintains a planting log so rotation advice reflects what actually grew where. Use when the user asks what to plant in the raised bed, wants to rotate or change over a vegetable bed, asks about spring/summer/fall vegetables, mentions tomatoes, okra, or succession planting, or asks how to manage an edible bed through the year.
---

# Raised Bed Rotation

For the recurring turnover of an edible bed, three or four times a year. Distinct from the
`yard-design` skill, which is for standing up or redesigning a garden.

## Step 1: Load the history

Read, in this order:

1. `<yard>/site.json` — bed geometry and zones. `python3 -m lib.yards` lists the yards;
   `python3 -m lib.siteschema <slug>` shows what is measured and what is assumed. Where a yard
   has a `sun-hours.json`, that is the real light figure for the bed, month by month, and it
   beats any remembered impression of how sunny the bed is.
2. `<yard>/conditions.json` — soil, what compost and mulch are already on hand, what tools
   exist. `python3 -m lib.conditions <slug>` reports it and flags anything stale.
3. `<yard>/raised-bed-log.md` — what grew in which zone each past season, plant
   families, fixed zones, and lessons learned.

For a yard not yet in the system, `<yard>/profile.md` holds the older free-text notes. Prefer
the structured files where both exist, and if a yard has no `site.json` at all, run the
`new-yard` skill rather than planning a rotation off prose.

Rotation advice without the log is generic advice. Read it first, every time.

Then ask only what the files can't tell you, in one short round:

- What's actually in the bed right now, and what's coming out?
- Anything from last season worth repeating or never repeating?

## Step 2: Locate the season

Check today's date against the local planting calendar. For Austin, that's
[austin-calendar.md](austin-calendar.md). For any other location, research that region's
extension-service planting calendar and write an equivalent file before proceeding — do not
reuse the Austin dates.

Where the yard has a `climate` block in `site.json`, it carries the frost dates with their
spread, derived from thirty years of daily weather:

```bash
python3 -m lib.climate <slug> --zip <zip>       # or --write to record it
```

Plan from the **10% risk** date rather than the median. The median is a coin flip, and the
derived dates run one to two weeks early against station normals because the underlying
reanalysis does not resolve the shallow cold layer that forms on calm clear nights.

Austin runs on four phases, not the usual two:

| Phase | Window | What it's for |
|---|---|---|
| Spring warm season | Transplants late Feb – mid Mar | Tomatoes, peppers, cucumbers, beans, basil. Short — heat ends fruit set by June. |
| Summer survival | Sow May – mid Jul | Okra, southern peas, sweet potato, Malabar spinach. Almost nothing else produces. |
| Fall warm season | Transplants mid Jul – mid Aug | The second tomato season, often more productive than spring. |
| Cool season | Plant Sept – Oct | Brassicas, greens, roots, garlic. Holds the bed through February. |

**Fall is contested and you have to choose.** Fall tomatoes want the bed from mid-July into
November; the cool-season planting wants it from September. Raise this tradeoff rather than
silently picking one. When a December event is on the calendar, the cool-season planting wins.

## Step 3: Check rotation before proposing anything

Look up each candidate crop's family in [crop-guide.md](crop-guide.md), then check the log for
where that family sat last season and the season before.

**Rules for a single small bed**, in priority order:

1. Never put nightshades (tomato, pepper, eggplant) in the same quadrant two years running.
   This is the one that actually matters — soil-borne wilts and nematodes build up.
2. Follow heavy feeders (brassicas, nightshades, corn) with legumes (beans, southern peas),
   which fix nitrogen.
3. Move brassicas around between cool seasons; they're the other family that builds up disease.
4. Roots and alliums are flexible fillers — use them to make the rotation work.

Be honest about the ceiling. In 32 square feet you cannot achieve real family separation. Say
so, rotate the nightshade block around the quadrants, and lean on soil building instead:
compost between rotations, no-till, and an edible legume cover crop in the summer gap.

## Step 4: Lay it out

Propose a square-foot layout with quantities and spacing from [crop-guide.md](crop-guide.md).
Account for:

- **Fixed zones.** Perennial or host-plant corners stay put across rotations (in this bed,
  parsley and dill for black swallowtails). Treat as unavailable, don't re-plan it.
- **Height and shading.** Tall crops and trellises go where they won't shade the rest —
  in this bed, the north end.
- **Sprawl.** Melons and sweet potatoes will consume a 4x8 bed. Offer a trellis with fabric
  slings for small melons, or a grow bag off to the side for sweet potatoes. Don't quietly
  plant something that swallows the bed.
- **Succession.** Fast crops (radish, lettuce, bush beans) get re-sown every 2–3 weeks rather
  than all at once.

Render the map:

```bash
python3 ~/.cursor/skills/raised-bed-rotation/scripts/draw_bed.py layout.json -o maps/bed-spring-2027.png
```

It colors cells by plant family, so the rotation is legible at a glance. Read the docstring for
the schema. Look at the output before shipping it.

## Step 5: Dated tasks, not just a plant list

Work backward from the transplant window and give real dates:

- **Seed-start-by dates.** Count back from transplant: tomatoes and peppers 6–8 weeks,
  brassicas 5–6, cucurbits 3–4. Miss these and the season is buying transplants instead.
  `python3 -m lib.schedule <slug> --seed-start "tomato,pepper,okra"` does the arithmetic and
  knows which crops are direct-sown and should never be started indoors.
- **Harvest-by dates.** Working backwards from a date something has to be ready to eat:
  `python3 -m lib.schedule <slug> --crop "bush bean" --harvest-by 2027-06-01`. It adds a
  fortnight to the catalogue days-to-maturity, because those figures assume conditions nobody
  has, and it flags the case where the sow-by date lands before the last frost for a
  frost-tender crop — which is the usual way a back-planned harvest quietly fails.
- **Soil prep** in the two weeks before planting: 1–2 inches of compost, fork it without
  flipping, water it in and let it settle. Check `conditions.json` before buying any: bags
  already in the garage are the cheapest compost there is.
- **Infrastructure before planting, not after.** Trellises and cages go in at transplant time;
  installing them around an established tomato damages roots.
- **The management technique each crop needs** — suckering tomatoes, harvest cadence for okra,
  hand-pollination for melons. Per crop in [crop-guide.md](crop-guide.md). The user wants to
  learn this bed, so explain the why briefly, not just the what.
- **Pest watch** for this season's crops specifically. Physical-first, and in a garden with
  butterflies and frogs, Bt, neem, spinosad and pyrethrins are all off the table.

## Step 6: Write it down

A sowing calendar is a dated document with its own budget — `SOWING-CALENDAR.md`,
not a section bolted onto `PLAN.md`, and the plan should say only that the dates
live there. It is held to the same contract as the plan: sowing dates, transplant
dates, technique, and no account of what the dates used to be. When a date moves,
move it and file the reason:

```bash
python3 -m lib.changelog <slug> --add "Carrots direct-sown, not started indoors" \
  --kind change --subject carrots --was "..." --now "..." --why "..." \
  --affects SOWING-CALENDAR.md
python3 -m lib.changelog <slug> --lint
```

The full rule is in [AGENTS.md](../../AGENTS.md).

Two updates below, both required, or the next rotation starts blind.

**The log.** Append a new section to `<yard>/raised-bed-log.md`: the season, the
crops by zone with families, and a placeholder for the outcome. Fill in the previous season's
outcome line while it's still fresh.

**Conditions**, if anything physical changed. Compost used, a trellis bought, the bed topped
up: `python3 -m lib.conditions <slug>` shows what is recorded, and next season's plan is only
as good as what this one wrote down.

**The Yearbook.** One Google Doc that accumulates every season's plan and how it went. The doc
ID is recorded at the top of the log file.

- If no ID is recorded, create the doc (`gdrive.createGoogleDoc`, titled
  "Raised Bed Yearbook — <garden name>") and write the ID into the log.
- Otherwise append this season's section to the existing doc so the link stays stable.

Keep the chat answer itself light. The Yearbook is the archive; the conversation should read
like advice, not a report.
