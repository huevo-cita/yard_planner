# Yard Planner

Turns an address into a measured yard, works out how much sun every part of it
gets in every month of the year, and plans a planting against that — then costs
it and schedules it weekend by weekend.

It is built around one idea: **a garden plan should be checkable.** Most advice
about what to plant where rests on somebody's impression of how sunny a bed is.
This measures it, states where every number came from, and refuses to place a
plant the light cannot support.

```
address ──> site.json ──> sun-hours.json ──┐
                                            ├──> design.json ──> schedule + costed list
current state ──> conditions.json ──────────┤
taste ──────────> vision.json ──────────────┘
                     │
                     ├──> coverage.json: what is still unknown, ranked by what it costs
                     │
                     ├──> doubts.json: what is in question — and a gate that stops
                     │    the expensive stages until it is settled
                     │
                     └──> all-clear.json: what was assumed and run on anyway, per
                          job, with the reason, bound to the values it covers
```

## What it actually does

**Measures a property from public data.** County and city GIS for lot lines,
OpenStreetMap for neighbouring buildings, USGS 3DEP classified lidar for tree
heights, crown spreads and roof eaves, USGS elevation for slope, USDA Soil Data
Access for soil, and thirty years of ERA5 reanalysis for frost dates. All free,
none needing an API key.

**Measures what public data cannot.** A four-point homography turns one
photograph of a wall into eave heights, awning projections and window
dimensions, with error bars from a Monte Carlo over the click precision. It
refuses to answer where a photograph genuinely cannot — tree crowns, anything
off the reference plane.

**Models the light.** A ray-traced shade model over a grid of the yard, at
five-minute steps, accounting for the house, fences, neighbouring buildings,
overhead planes like awnings and pergolas, and tree crowns that leaf out and
drop on dates. It reports hours per zone per month, and — because this turns out
to matter more than the hour count — **when** those hours arrive. Four hours of
morning sun and four hours of afternoon sun are not the same place to plant.

**Ranks what it does not know by what the ignorance costs.** Not a checklist of
missing fields: it re-runs the sun model across the plausible range of each
unknown and reports the answer's spread in hours of light a day. Soil and
inventory gaps are priced in dollars at risk. A gap that changes nothing sinks
to the bottom on its own.

**Objects.** The design stage checks every plant against the measured light,
water and soil and against what was actually asked for, and raises blocking
objections rather than quietly substituting something easier.

**Refuses to run on a doubt.** The expensive stages — the shade model, the
design, the bed maps, the bill of materials, the schedule — stop while there is
an open doubt on the yard's board that would change what they produce. This
exists because of one specific waste: a doubt gets voiced in prose just before an
expensive run, the run goes ahead anyway, the doubt is then settled, and the run
is thrown away. A doubt gets written to `doubts.json` instead, where something
reads it. Most are settled automatically by re-running the model across the
plausible range and discovering the answer barely moves; the rest come back as a
decision with its options priced. See [AGENTS.md](AGENTS.md).

**And refuses to run on silence.** An empty doubt board used to be permission,
which reads the absence of a written doubt as confidence — when absence is
exactly what the failure above produces. So the same five stages want a positive
**all-clear** first: for every value the job reads whose provenance is `assumed`
or `reported` rather than measured, either a doubt card id or a written reason
for proceeding. `yard doubts <slug> --inputs sunmodel` prints that list, per job,
with the command that files it. Each clearance is bound to a digest of the values
it covers, so changing one of those makes it stale, and stale blocks like
missing — with `yard doubts <slug> --clear sunmodel --renew` to carry forward
every reason whose value did not move. What it covers is narrower than the whole
file: the assumed and reported values, and a census that notices something being
added or removed. A measured value can be corrected underneath it without
invalidating it. Nothing prevents a lazy blanket clearance either —
`--because '*=fine, I looked'` is accepted — and what it buys is only that the
omission becomes a dated artifact making specific claims instead of a silence.
The holes are set out in
[.cursor/hooks/VALIDATOR.md](.cursor/hooks/VALIDATOR.md).

**Costs and schedules it.** The bill of materials is netted against what the
inventory says is already in the garage. The schedule back-plans in weekends
from the target date, counts seed-start and days-to-maturity deadlines
backwards, works around travel, reserves a catch-up weekend, gates tasks on the
person's actual experience, and produces a cut list when it comes in over
budget.

## Install

```bash
git clone git@github.com:huevo-cita/yard_planner.git
cd yard_planner
pip install -r requirements.txt

./bin/yard install         # link the skills and subagents into ~/.cursor
./bin/yard doctor          # check the environment, and say what any gap costs

python3 tools/test_gate.py   # prove the doubt gate actually refuses
python3 tools/mutate_gate.py # prove those tests would notice if it stopped
```

`test_gate.py` builds a scratch yard in a temporary directory, files a doubt, and
checks that each of the five expensive jobs refuses, that it refuses *quickly*
rather than after the work, that a yard nobody has said anything about refuses
too, that an all-clear goes stale the moment a value it covers moves, that
`--force` stamps what it came past, and that the cheap paths stay open. A
non-zero exit that does not name the gate is reported as inconclusive rather than
passing, because a job that dies for an unrelated reason also exits non-zero and
would otherwise score as a win.

`mutate_gate.py` answers the next question, which is whether those tests would
notice. It breaks the gate seven ways on purpose — silence clears again, the
freshness check goes away, the hook stops denying — runs the suite against each,
restores the file, and fails if anything survived unnoticed.

`doctor` names what breaks for anything missing, rather than only reporting its
absence. The optional packages only limit what can be measured automatically;
everything else still runs.

Put `bin/` on your `PATH` and the rest of this reads as `yard <command>`.

## Use

The skills are the front door — in Cursor, say "start a new yard" and the
`new-yard` skill sequences the rest. Everything underneath is also a plain
command:

```bash
yard                              # what yards exist and what each one has
yard lidar    <slug> --write      # tree and roof heights from USGS 3DEP
yard sunmodel <slug>              # sun hours per zone per month, and the maps
yard gaps     <slug>              # what is missing, worst first, with the cost
yard doubts   <slug>              # what is in question, and what it blocks
yard doubts   <slug> --price      # probe them, and settle the ones that do not matter
yard doubts   <slug> --inputs bom # what an all-clear for that job has to answer
yard doubts   <slug> --clear bom  # file it, and unblock the job
yard doubts   <slug> --clear bom --renew   # re-file, keeping the reasons that stand
yard inputs                       # which part of site.json each gated job reads
yard design   <slug>              # check a design against the measured site
yard bom      <slug>              # bill of materials, netted against what is here
yard schedule <slug>              # the weekend plan, back-planned from the date
yard --help                       # every module
```

### Skills

| Skill | What it does |
|---|---|
| `new-yard` | The conductor. Registers a yard and sequences the rest, reporting ranked gaps after each stage |
| `yard-survey` | Address to measured geometry: lot lines, obstruction heights, slope, frost dates |
| `yard-conditions` | Soil, existing ground work, materials and tools on hand, and the person's hours, skill and budget |
| `yard-vision` | What they want, with a strength on each preference, and the contradictions between them |
| `yard-sun-model` | Runs the shade model and prices proposed changes in hours of light |
| `yard-design` | Joins taste to measured fact and rejects what the site cannot support |
| `yard-schedule` | Bill of materials, local sourcing, weekend plan, budget and cut list |
| `raised-bed-rotation` | The seasonal edible turnover, with a planting log driving crop rotation |

### Subagents

`parcel-scout` finds authoritative lot geometry from county GIS.
`photo-surveyor` measures real dimensions from photographs.
`vision-scout` reads a board or folder of inspiration images.
`sourcing-scout` finds local nurseries, bulk yards and municipal programs with
real prices. Each runs in its own context because each has a high dead-end rate.

## Data, and why none of it is in this repo

A yard record is the most identifying kind of file a person can write. It holds
a street address, a latitude and longitude accurate to a rooftop, a parcel
number that resolves to an owner name in a public registry, and a written
profile naming who lives there, when they travel, and what they can spend.

So `.gitignore` here is a **whitelist**, not a blacklist. Everything is ignored
and the code is added back by name, which means a new yard directory is excluded
the moment it is created, without anyone having to remember.

Two more layers behind it:

- `yard scrub` scans every tracked file for addresses, rooftop coordinates,
  parcel identifiers and home-directory paths. `yard scrub --install-hook` wires
  it into `pre-commit` so a leak stops the commit. It caught two real
  coordinates in docstrings that a manual read had missed.
- The vault, below, is the only supported way for yard data to travel.

### The vault

Encrypting the data means the system is actually portable — code without data
draws nothing.

```bash
yard vault lock <slug>       # -> vault/<slug>.tar.gz.enc, safe to commit
yard vault unlock <slug>     # restore it on the other machine
yard vault list              # what is in there, and whether a local copy exists
```

AES-256-CBC, key stretched from a passphrase by PBKDF2-HMAC-SHA256 at 600,000
iterations over a random salt, through the `openssl` binary that ships with
macOS and every Linux distribution. Nothing to install. The passphrase is read
from `YARD_VAULT_PASSPHRASE` or prompted for, and is passed to openssl on a file
descriptor rather than the command line, where `ps` would show it to every other
process on the machine.

Three things worth being plain about:

- **The passphrase is the whole security of it.** A public repo means an
  attacker gets unlimited offline guesses. 600,000 iterations only raises the
  price per guess. Use a long passphrase, and keep it somewhere other than this
  repo.
- **CBC is confidential, not authenticated.** Tampering shows up as a failed
  decryption rather than as silently altered data, but this is not AEAD. For a
  single author's own backup that trade is fine. For anything adversarial, use
  `age` or GPG.
- **`vault/manifest.json` is committed in the clear** and deliberately says
  nothing about content — dates and sizes only. A manifest listing streets would
  undo the encryption it describes.

If you would rather the personal data never sit inside a checkout at all, point
`GARDEN_ROOT` somewhere else:

```bash
export GARDEN_ROOT=~/Documents/yards
```

The code root and the data root are separate; they only default to the same
place because that is the simple case.

## Layout

```
lib/          the engine. One module per job, each runnable as python3 -m lib.<name>
skills/       the agent skills, symlinked into ~/.cursor/skills
agents/       the subagents, symlinked into ~/.cursor/agents
bin/yard      one entry point, runnable from any directory
tools/        install, doctor, and the PII scrubber
vault/        encrypted yard bundles, committed
.cursor/      the doubt gate: a hook that denies the expensive jobs while a
              doubt is open, or while nothing has been attested about what they
              are running on. See .cursor/hooks/VALIDATOR.md
AGENTS.md     how to work in here, and the doubt rule in full
<slug>/       one directory per yard. Never committed.
```

Each yard holds `site.json` (geometry and the 3D obstruction model),
`conditions.json` (soil, inventory, the person), `vision.json` (taste, with a
strength on each want), `design.json`, `sun-hours.json`, `coverage.json`,
`doubts.json` (what is in question, and what it blocks), `all-clear.json` (what
was assumed and run on anyway, and why), a prose `profile.md`, and `maps/`,
`photos/` and `design/`.

`site.json`, `conditions.json` and `vision.json` are the sources of truth.
Correct one and re-run, and every drawing, figure and cost regenerates.

## House rules

Every number carries provenance — measured, lidar, photo, parcel, osm, survey,
reported, derived, or assumed — and, where estimated, an uncertainty. An
assumption stays labelled as one. No invented precision. Where a data source has
a known bias, the code says so out loud: ERA5 minimum temperatures run warm, so
the frost dates report the ten-percent-risk date rather than the median, and a
locally published figure overrides the model.

A doubt goes in a file, not into a sentence on the way past. Provenance records
where a number came from; the doubt board records whether anyone believes it, and
those are different questions. Nothing gets settled silently: a waived doubt
carries its reason, an automatically settled one carries the measured spread that
justified it, and anything produced by forcing past an open doubt is stamped
provisional and says why.

Python 3.9 with numpy and matplotlib, `urllib` over `requests`, and no
dependency added without a reason that survives being written down.

## Licence

MIT. See `LICENSE`.
