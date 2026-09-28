# Regional plant catalogs

One file per region. A catalog holds plant facts only. It holds no address, no
coordinate and no yard, so it is safe to commit and it is shared by every yard
in that region.

`lib/fits.py` reads a catalog, runs every plant in it through
`niches._rejects` against every planting place in a yard, and answers the
question somebody asks in a nursery aisle: does this go anywhere I have?

## Files

| File | Region | Yards |
|---|---|---|
| `central-texas.json` | Austin and the Hill Country, USDA 8a-9a | cloverleaf-austin, loyola-austin |

A yard picks its catalog with `--catalog <region>`. `lib/fits.py` also maps a
yard to a region automatically from `site.json`.

## The record

Every field that `niches.REQUIRED` names is mandatory, because a record missing
one cannot be checked and `_rejects` says so rather than guessing:

```json
{"botanical": "Muhlenbergia lindheimeri",
 "names": ["Lindheimer muhly", "big muhly"],
 "habit": "grass",
 "light": "full sun",
 "water": "low",
 "mature_height_ft": 4.0,
 "mature_spread_ft": 5.0,
 "ph_range": [6.5, 8.5],
 "season": "evergreen",
 "bloom": ["Sep", "Oct", "Nov"],
 "evergreen": true,
 "native": true,
 "maintenance": "low",
 "source": "Lady Bird Johnson Wildflower Center"}
```

`light` must be one of the keys in `design.LIGHT_NEED`. `water` must be one of
the keys in `design.WATER_NEED`. `maintenance` must be one of the keys in
`niches.UPKEEP`.

## Two fields that need care

**`season`** names the months the plant is in active growth and needs light.
`lib/fits.py` expands it into the `months` list that `_rejects` passes to
`design.zone_hours`, so the light question is asked over the right window. The
windows are declared in the `seasons` block of each catalog file, and a plant
may override them with an explicit `months` list.

This is not the same as `bloom`. A plant that flowers in November is still
judged on the light it gets while it grows. `_rejects` falls back to `bloom`
when a record names no months at all, which is the documented `check_light`
behaviour, and the `season` key exists so that fallback is never reached.

**`ph_range`** is the range the plant is documented to grow well in. Where a
plant is demonstrably grown in Austin's alkaline soil, the upper bound is
widened to the observed local limit and the record says so in `ph_note`. This
matters: the in-ground beds read pH 8.2, so a bound of 8.0 rejects a plant that
every nursery in town sells and every garden in town grows.

Set `soil_drainage: "sharp"` where the plant genuinely needs it. `_rejects`
blocks those outright in slow or poor drainage, which is the right answer for
lavender in Austin clay and is the reason this catalog is worth having.

## Flower and fruit color

`flower_color` is one word from `scheme.FLOWER_HEX`. Give it only when one
species or one cultivar gives one color. A genus or "A / B" gets no color.

Give fruit only when it is colorful and a person sees it in the garden:

```json
"fruit_months": ["Aug", "Sep", "Oct", "Nov"],
"fruit_color": "red",
"fruit_what": "red peppers",
"fruit_source": "Lady Bird Johnson Wildflower Center; Texas A&M AgriLife"
```

`fruit_for` names the animals that eat the fruit, for example `["birds"]`,
with its source in `fruit_source`. It counts as wildlife value even when the
fruit is not colorful, because it is food. `seed_for` does the same for seed
that animals eat from the plant, such as goldfinches on coneflower. Its source
goes in `seed_source`. Leave both lists out when no source names an animal.
Do not infer an eater from the genus.

`fruit_color` is one word from `scheme.FRUIT_HEX`. The bed map shows a
cluster of dots in that color in the fruit months. A plant with green,
tan or brown fruit has no fruit fields.

## Adding a plant

`yard fits <slug> --intake <queued.json>` adds records queued from the phone.
Or edit the file. Either way the record needs a real `source`; a plant with no
provenance is a guess wearing a catalog's clothes.
