# How to compose a planted bed

This document holds the rules for composing a planted bed through the year: layers, masses, repetition, density, color and winter structure. Each rule has its sources, and a check opened every source.

`lib.design`, `lib.niches` and `lib.scheme` read the numbers from `practice/rules.json`. Do not copy a number from this document into code. Read it with `practice.rule(key)`.

A source is tier 1 when it is peer-reviewed. A source is tier 2 when it is an extension service, a standard, a professional body, or a textbook by an established author. A tier 3 source cannot back a rule. A rule marked critical has two or more independent tier 1 or tier 2 sources.

## 1. Height layering

### 1.1 `design.height_layers_graded`

Arrange plants in graded height layers. Put the shortest plants at the front and the tallest plants at the back, or at the centre of an island bed.

- Value: `["ground", "foreground", "midground", "background"]`
- Critical: yes

**Where the sources disagree.** Hitchmough and Rainer and West also stack layers vertically on the same ground, so a low layer runs under the tall layer, not only in front of it. See design.stacked_layers.

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'Plant layers in staggered heights, with low plants in front and taller plants in back.' (Figure 1 caption; section 'Creating Vertical Layers')
- Tier 2, supported: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'Tall flowers should be selected for the back part of the bed, with medium-height species in the middle and dwarf varieties along the front as edging plants.'
- Tier 2, supported: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Use taller plants at the back of the bed, or in the middle of a bed viewed from multiple sides.' and 'Place shorter plants toward the front of the bed.'
- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'In general, position tall, substantial plants towards the back of your border.' (step 'Choose the position of your plants')

### 1.2 `design.height_bands_ft`

Classify each plant by mature height. Ground layer is up to 0.5 ft, foreground is 0.5 to 2 ft, midground is 2 to 5 ft, background is above 5 ft.

- Value: `[0.5, 2, 5]` ft
- Critical: no

**Where the sources disagree.** Rainer and West define layers by function, not by a height number. Tier 3 guides use other cut points (for example 1.5 ft and 3 ft).

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'ground layer ... grow about 6 inches high'; 'The foreground layers, plants that are 6 inches to 2 feet'; 'The midground layer consists of plants from 2 feet to 5 feet.'; 'The tallest layer, the background plants, consists of trees and large shrubs'.

### 1.3 `design.no_layer_jump`

Do not place a background plant directly behind a ground or foreground plant with no midground plant between them. Allow a jump only for a deliberate dramatic contrast.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Hansen notes that contemporary design uses the jump on purpose. See-through plants are exempt (design.scrim_exception).

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'Try to avoid large gaps in the vertical heights, such as jumping from the foreground layer to the background layer, unless the intent of the design is to have dramatic differences in the layers'.
- Tier 2, partial: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - Specifies three steps: 'Tall flowers ... back part of the bed, with medium-height species in the middle and dwarf varieties along the front'.
- Tier 2, partial: Hansen, G. Basic Principles of Landscape Design. CIR536/MG086. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG086>
  - 'Gradation can be achieved with a gradual change in height or size (e.g., using small grasses in front, backed by medium grasses, and then large grasses).' Same author as EP449, so not counted as independent.

### 1.4 `design.skyline_varies`

Make the top line of the planting rise and fall along the bed. Do not use one flat height or a regular step profile.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'the height should also vary from side to side along the top of the plant material. The height should undulate from high to low and back to high along the horizon.'
- Tier 2, supported: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'Height lines should be broken up by letting some tall plants extend into the medium height groups ... This gives a more natural effect than a step profile.'
- Tier 2, partial: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Bring select taller plants forward to increase variation in height.'

### 1.5 `design.skyline_min_range_ft`

Along the length of the back layer, make the tallest and shortest plant heights differ by a measurable amount.

- Value: `null` ft
- Critical: no

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'The height should undulate from high to low and back to high along the horizon.' No number is given.

### 1.6 `design.max_height_to_depth`

Keep the tallest plant no taller than about two-thirds of the bed depth. A 6 ft deep border takes plants up to 4 ft.

- Value: `0.67` ratio
- Critical: no

**Where the sources disagree.** Tier 3 guides say one-half. Hansen puts trees and large shrubs in the background layer against a wall, which exceeds this ratio.

Sources:

- Tier 2, supported: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'Plant height is best limited to two-thirds the width of the border, e.g., no plants taller than 4 feet in a border 6 feet wide.'
- Tier 2, supported: Penn State Extension Master Gardeners of Chester County. Perennials (how-to gardening brochure). Penn State Extension. <https://extension.psu.edu/programs/master-gardener/counties/chester/how-to-gardening-brochures/perennials-1>
  - 'Limit plant height to two-thirds the width of the border so that no plant is taller than four feet in a border six feet wide.'

### 1.7 `design.scrim_exception`

Allow a few tall, see-through plants near the front. Each must have thin stems, sparse leaves or a thin canopy, so the plants behind stay visible.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'some tall, slender plants, or those with a thin canopy, can be placed near the front to create an attractive, more natural look.'
- Tier 2, partial: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'The composition is often more interesting, however, if a few tall plants are added to the foreground or midground layer.'
- Tier 2, partial: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Bring select taller plants forward to increase variation in height.'
- Tier 2, partial: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'Aim to include variety in flower shape ... and ethereal ‘see-through’ plants'.
- Tier 2, supported: Oudolf, P. and Kingsbury, N. (1999). Designing with Plants. Portland: Timber Press. Not opened; quotations relayed by Beautiful Botany (2008) and by J. Davis, The Paintbox Garden. <http://www.beautifulbotany.com/Latest/Latest-Stories-2008/June/See-Through%20Plants.htm>
  - Relayed quote: 'Transparent plants are mostly air, and their loose growth creates another perspective as you look through them to the plants growing behind.' and 'Transparency can be overdone; it can destroy patterns if too many such plants are used'.

### 1.8 `design.stacked_layers`

In a naturalistic bed, plant a low, shade-tolerant ground layer under and between the taller plants. Do not leave soil or mulch under taller layers.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Conventional extension guidance (Hansen) arranges layers front to back only and spaces plants to touch at maturity. The two models agree at the front edge and differ under the tall plants.

Sources:

- Tier 1, supported: Hitchmough, J. D. (2017). The plant community: a model for horticultural thought and practice in the 21st century? Acta Horticulturae 1189, 113-118 (VI International Conference on Landscape and Urban Horticulture). Accepted version, White Rose eprint 126014. <https://doi.org/10.17660/ActaHortic.2017.1189.23>
  - 'this stacking up of layers on top of one another maximizes light extinction at ground level. This reduces establishment of the shade intolerant weedy ruderal species'.
- Tier 1, supported: Hitchmough, J., Wagner, M. and Ahmad, H. (2017). Extended flowering and high weed resistance within two layer designed perennial 'prairie-meadow' vegetation. Urban Forestry & Urban Greening 27, 117-126. <https://doi.org/10.1016/j.ufug.2017.06.022>
  - 'The winter green canopies of the two dominant under-storey forbs closed down gaps within a winter deciduous, prairie-like vegetation, improving winter appearance'.
- Tier 2, supported: University of Illinois Extension (2023, 9 January). Planning a new perennial garden? Plant for the whole garden ecosystem (quoting L. Knoche, Red Oak Rain Garden, on the Rainer and West layer method). <https://extension.illinois.edu/news-releases/planning-new-perennial-garden-plant-whole-garden-ecosystem>
  - Groundcover layer: 'low-growing, densely planted grasses, sedges, ferns, and forbs that form a “green mulch” that serves to shade out weeds.'
- Tier 2, supported: Rainer, T. and West, C. (2015). Planting in a Post-Wild World: Designing Plant Communities for Resilient Landscapes. Portland: Timber Press. Not opened; percentages confirmed through Seppanen, S. (2019), MSc thesis, Swedish University of Agricultural Sciences, and through two independent reviews. <https://stud.epsilon.slu.se/15190/7/seppanen_s_191017.pdf>
  - Book p. 180, as quoted in the Gardenopolis Cleveland review: 'Plant ground covers wherever there is space for them: under trees, shrubs, and taller perennials. Fill all gaps between taller plants'.
- Tier 2, partial: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'planning in layers. Start with a low understory of spring perennials with a mix of taller perennials to follow'.

## 2. Layer proportions

### 2.1 `design.front_layer_share`

Put at least half of all plants in the ground or groundcover layer. Put fewer plants in each taller layer.

- Value: `0.5` ratio
- Critical: yes

**Where the sources disagree.** The Hitchmough figures are for sown seedlings, not plugs or pots. Rainer and West give 50% for planted schemes. Use 0.5 as the minimum for planted beds.

Sources:

- Tier 2, partial: Rainer, T. and West, C. (2015). Planting in a Post-Wild World: Designing Plant Communities for Resilient Landscapes. Portland: Timber Press. Not opened; percentages confirmed through Seppanen, S. (2019), MSc thesis, Swedish University of Agricultural Sciences, and through two independent reviews. <https://stud.epsilon.slu.se/15190/7/seppanen_s_191017.pdf>
  - Seppanen (2019) summarising the book: 'Ground cover plants should make up for 50 % or the planting.'
- Tier 1, partial: Hitchmough, J. D. (2008). New approaches to ecologically based, designed urban plant communities in Britain: do these have any relevance in the United States? Cities and the Environment (CATE) 1(2), Article 10. <https://doi.org/10.15365/1932-7048.1019>
  - 'most of the seed sown is of ground layer species (typically around 70% on a target seedling emergence basis) with intermediate canopy layers at 20% ... and tall canopy species 10% or less.'
- Tier 1, partial: Jiang, M. and Hitchmough, J. D. (2022). Can sowing density facilitate a higher level of forb abundance, biomass, and richness in urban, perennial 'wildflower' meadows? Urban Forestry & Urban Greening 74, 127657. <https://doi.org/10.1016/j.ufug.2022.127657>
  - 'The ratio of emerged seedlings designed into each layer (low: medium; tall) was 4:2:1.' (low layer is 57%)

### 2.2 `design.layer_shares`

Use the Rainer and West split as a default for a planted naturalistic bed. Structural 10 to 15%, seasonal theme 25 to 40%, groundcover 50%, filler 5 to 10%.

- Value: `{"structural": [0.1, 0.15], "seasonal_theme": [0.25, 0.4], "groundcover": 0.5, "filler": [0.05, 0.1]}` ratio
- Critical: no

**Where the sources disagree.** Oudolf's '70% structural' uses 'structural' for any plant that holds its form through the season. That is a different meaning from the Rainer and West tall structural layer. The splits agree only that the lowest layer holds most plants and the tall layer holds few.

Sources:

- Tier 2, supported: Rainer, T. and West, C. (2015). Planting in a Post-Wild World: Designing Plant Communities for Resilient Landscapes. Portland: Timber Press. Not opened; percentages confirmed through Seppanen, S. (2019), MSc thesis, Swedish University of Agricultural Sciences, and through two independent reviews. <https://stud.epsilon.slu.se/15190/7/seppanen_s_191017.pdf>
  - Seppanen (2019), p. on 'Creating layers': 'The structural/framework plants should comprise 10-15 % of the planting ... 25-40 % ... seasonal theme plants ... Ground cover plants should make up for 50 % ... Filler plants make up for 5-10 %'. The same figures appear in an independent review (ongardening.com).
- Tier 1, partial: Hitchmough, J. D. (2008). New approaches to ecologically based, designed urban plant communities in Britain: do these have any relevance in the United States? Cities and the Environment (CATE) 1(2), Article 10. <https://doi.org/10.15365/1932-7048.1019>
  - Ground 70%, intermediate 20%, tall 10% or less, by target seedling emergence.
- Tier 2, partial: Dunnett, N. and Hitchmough, J. (eds.) (2004). The Dynamic Landscape: Design, Ecology and Management of Naturalistic Urban Planting. London: Spon Press. Not opened; chapter content confirmed through Seppanen (2019) and Hitchmough (2008). <https://doi.org/10.4324/9780203402870>
  - Seppanen (2019) citing Dunnett, Kircher and Kingsbury (2004): Kircher's mixes use, per 100 m², '1-5 emerging perennials, 10-50 companion perennials, 30-80 ground-covering perennials and 30-300 scattered perennials'.

### 2.3 `design.tall_layer_share_max`

Keep structural and emergent plants to 15% or less of the plant count. A few tall plants carry the design; many tall plants shade out the lower layers.

- Value: `0.15` ratio
- Critical: yes

Sources:

- Tier 1, supported: Hitchmough, J. D. (2008). New approaches to ecologically based, designed urban plant communities in Britain: do these have any relevance in the United States? Cities and the Environment (CATE) 1(2), Article 10. <https://doi.org/10.15365/1932-7048.1019>
  - 'tall canopy species 10% or less' and 'plants present in the mid- and tall canopy layers present at much lower densities to prevent the elimination of shade intolerant ground layers species.'
- Tier 2, supported: Rainer, T. and West, C. (2015). Planting in a Post-Wild World: Designing Plant Communities for Resilient Landscapes. Portland: Timber Press. Not opened; percentages confirmed through Seppanen, S. (2019), MSc thesis, Swedish University of Agricultural Sciences, and through two independent reviews. <https://stud.epsilon.slu.se/15190/7/seppanen_s_191017.pdf>
  - Seppanen (2019): 'The structural/framework plants should comprise 10-15 % of the planting.'
- Tier 2, partial: Dunnett, N. and Hitchmough, J. (eds.) (2004). The Dynamic Landscape: Design, Ecology and Management of Naturalistic Urban Planting. London: Spon Press. Not opened; chapter content confirmed through Seppanen (2019) and Hitchmough (2008). <https://doi.org/10.4324/9780203402870>
  - Kircher proportions via Seppanen (2019): '1-5 emerging perennials' per 100 m² against 30-80 ground-covering perennials.

## 3. Massing

### 3.1 `design.mass_sizes`

Plant each seasonal or midground species in odd-numbered groups of 3, 5 or 7. Let structural plants stand alone or in 3s; mass groundcovers in 10 or more.

- Value: `{"default": [3, 5, 7], "structural": [1, 3, 5], "groundcover_min": 10}` count
- Critical: yes

**Where the sources disagree.** RHS prairie guidance asks for drifts of at least 5. Hansen says a small courtyard needs smaller masses. For a 4 ft bed, recommend 3 or 5 for seasonal plants and 1 or 3 for structural plants.

Sources:

- Tier 2, supported: Hansen, G. Basic Principles of Landscape Design. CIR536/MG086. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG086>
  - 'Features that are grouped in threes, or in other groups of odd numbers, such as in groups of five or seven, feel more balanced to the eye'.
- Tier 2, supported: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Place plants of the same variety in groups of three, five, or seven to increase the impact of color or texture.'
- Tier 2, partial: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Planting these in groups, ideally with an odd number of plants, helps prevent the border looking ‘bitty’.'
- Tier 2, partial: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'As a rule, five to seven plants will create the desired effect. A large delphinium or peony will be of sufficient size to be attractive'.
- Tier 2, supported: University of Illinois Extension (2023, 9 January). Planning a new perennial garden? Plant for the whole garden ecosystem (quoting L. Knoche, Red Oak Rain Garden, on the Rainer and West layer method). <https://extension.illinois.edu/news-releases/planning-new-perennial-garden-plant-whole-garden-ecosystem>
  - Groundcover: 'may be planted in groups of 10 or more'; structural: 'Individual plants or small groupings – three or five, typically – are appropriate for this layer.'
- Tier 2, partial: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'In small areas, plant in informal drifts of at least five plants.'

### 3.2 `design.mass_small_below_ft`

Mass every species with a mature height below 2 ft. A single small plant has little impact and makes a checkerboard.

- Value: `2.0` ft
- Critical: no

Sources:

- Tier 2, supported: Alvarez, E. and Hansen, G. Landscape Design: Aesthetic Characteristics of Plants. ENH1172/EP433. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP433>
  - 'Groundcover or bedding plants ... typically look better in masses because they are often small and have little impact as individual plants.'
- Tier 2, supported: Park Brown, S. Gardening with Perennials in Florida. ENH-68/MG035 (rev. December 2022). UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG035/pdf>
  - 'Evergreen and flowering shrubs provide an attractive backdrop for masses of small perennials, whereas large-growing perennials can be used as specimen plants.'
- Tier 2, supported: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'A large delphinium or peony will be of sufficient size to be attractive, but a random collection of different small- to medium-sized plants will present a disorganized, checkerboard appearance.'

### 3.3 `design.masses_interlock`

Overlap and interlock adjacent masses, with no bare gaps between them. Vary the size and shape of masses; use long, narrow drifts as well as clumps.

- Value: `{"overlap": true, "no_voids": true, "vary_shape": true, "vary_size": true}`
- Critical: yes

**Where the sources disagree.** Colorado State says 'Consider adding spaces of void within the plan.' Hansen says voids 'attract more attention than the plantings'. Recommend no voids inside a 4 ft bed.

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'overlap the masses of plants and connect them so that they flow without space between them. Avoid gaps or large open areas between masses.' and 'Vary the shape of the masses ... Vary the size of the masses, particularly those that are adjacent.'
- Tier 2, partial: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'The length of drifts and the diameter of clumps, as well as their heights, should be varied' and 'Each group of flowers should have an irregular shape.'
- Tier 2, partial: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'Drifts can be variable in shape, but are usually longer and thinner than blocks'.
- Tier 2, partial: Kingsbury, N. (2019, 20 June). Mind the Gap! Noel Kingsbury (author's own essay summarising his density trial published in The Plantsman). <https://www.noelkingsbury.com/noelsgarden-blog/2019/6/20/mind-the-gap>
  - 'Why do so many gardens ... look like displays of soil or exhibitions of mulch?'

## 4. Repetition

### 4.1 `design.repeat_across_beds`

Repeat the same species, or the same form, texture or colour, along the bed and across beds. Repetition creates rhythm and unity.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Hansen (MG086) warns that 'too much repetition can create monotony, and too little can create confusion.'

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'Repeating colors, forms, or textures of plants throughout the different beds creates a rhythm that is recognized as a pattern in the landscape.'
- Tier 2, supported: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Repeat groups of the same plant two or three times in the space to create continuity and harmony.'
- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Repeat the groups along the border to create a sense of flow and to unify the planting scheme.'
- Tier 2, supported: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'Try to repeat groupings to give coherence and rhythm'.

### 4.2 `design.repeat_min_beds`

Place each key species or group in at least two locations. Three locations in a triangle is better.

- Value: `2` count
- Critical: yes

Sources:

- Tier 2, supported: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Repeat groups of the same plant two or three times in the space'.
- Tier 2, partial: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'The most common pattern is a triangle shape between three plant beds.'

## 5. Matrix, block and intermingled

### 5.1 `design.arrangement_mode`

Choose the arrangement by layer. Use drifts or blocks for seasonal and structural plants; use an intermingled matrix for the groundcover layer.

- Value: `{"structural": "single or small group", "seasonal_theme": "drift or block", "groundcover": "intermingled matrix", "filler": "scatter"}`
- Critical: yes

**Where the sources disagree.** Kingsbury favours full intermingling; Hitchmough's sown communities are random; Hansen and most extension sources use discrete masses. Blocks read as cared-for; intermingling meshes and resists weeds better.

Sources:

- Tier 2, partial: Rainer, T. (2013, August). Intermingling and the Aesthetics of Ecology. Grounded Design (author's own essay). <http://landscapeofmeaning.blogspot.com/2013/08/intermingling-and-aesthetics-of-ecology.html>
  - 'Plant community-based design may use masses of plants in certain layers and mixed plantings in others. The degree of mixing or massing can be determined as a result of the designer’s aesthetic and functional goals'.
- Tier 2, supported: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - Planted method: 'drifts or blocks of varying proportions'; matrix method: 'The matrix is a species, planted in large numbers that acts as the background ... Planted among the matrix are groups or drifts of strong or ‘primary’ flowering plants ... scatter plants add a natural, random feel.'
- Tier 1, partial: Hitchmough, J. D. (2008). New approaches to ecologically based, designed urban plant communities in Britain: do these have any relevance in the United States? Cities and the Environment (CATE) 1(2), Article 10. <https://doi.org/10.15365/1932-7048.1019>
  - Block planting 'makes it clear to viewers that the plantings are intentional and probably cared for; some of the requirements of the “Cues to Care” hypothesis (Nassauer 1995) are therefore satisfied.'
- Tier 2, partial: Kingsbury, N. (2019, 20 June). Mind the Gap! Noel Kingsbury (author's own essay summarising his density trial published in The Plantsman). <https://www.noelkingsbury.com/noelsgarden-blog/2019/6/20/mind-the-gap>
  - 'single cultivar blocks of upright growers often never do [mesh], which is a good reason for using an ‘intermingled’ approach to planting.'
- Tier 2, partial: Oudolf, P. and Kingsbury, N. (2013). Planting: A New Perspective. Portland: Timber Press. ISBN 9781604697315. Not opened; content confirmed through RHS Prairie Planting guide and Rainer (2013). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - RHS attributes the matrix / primary / scatter ranking to Oudolf: 'This is a principle of Piet Oudolf ... He ranks plants according to visual impact.'

## 6. Spacing and density

### 6.1 `design.density_plants_per_m2`

Plant herbaceous naturalistic beds at about 7 to 9 plants per square metre. This is about one plant per 1.2 to 1.5 sq ft.

- Value: `{"per_m2": [7, 9], "per_ft2": [0.65, 0.84], "conventional_per_m2": [5, 12]}` count
- Critical: yes

**Where the sources disagree.** RHS gives 5 per m² for a conventional border. Groundcover plugs go denser (12 in apart). Count shrubs separately at mature spread.

Sources:

- Tier 2, supported: Kingsbury, N. (2019, 20 June). Mind the Gap! Noel Kingsbury (author's own essay summarising his density trial published in The Plantsman). <https://www.noelkingsbury.com/noelsgarden-blog/2019/6/20/mind-the-gap>
  - 'Modern thinking on perennial planting density tends to favour around seven to nine plants per square metre, considerably more so than conventionally.'
- Tier 1, partial: Hitchmough, J. D. (2017). The plant community: a model for horticultural thought and practice in the 21st century? Acta Horticulturae 1189, 113-118 (VI International Conference on Landscape and Urban Horticulture). Accepted version, White Rose eprint 126014. <https://doi.org/10.17660/ActaHortic.2017.1189.23>
  - 'Planted herbaceous vegetation for example, typically involve between 6-12 plants per m2, whereas meadows, or tall forb vegetation, generally have plant densities >150 plants per m2'.
- Tier 2, partial: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'aim for five herbaceous perennials, or three small shrubs, or one large shrub per sq m (11 sq ft).'
- Tier 2, partial: University of Illinois Extension (2023, 9 January). Planning a new perennial garden? Plant for the whole garden ecosystem (quoting L. Knoche, Red Oak Rain Garden, on the Rainer and West layer method). <https://extension.illinois.edu/news-releases/planning-new-perennial-garden-plant-whole-garden-ecosystem>
  - Groundcover 'planted as little as 12 inches apart' (about 10.8 per m²).

### 6.2 `design.plant_dense_then_thin`

Plant perennials and groundcovers closer than their mature spread, then edit out the dominant spreaders from the second year. Space shrubs at mature spread.

- Value: `{"applies": true, "herbaceous": "7-9 per m2", "groundcover": "12 in on centre", "woody": "mature spread, barely touching", "edit_from_year": 3, "keep_clear_of_wall": true}`
- Critical: yes

**Where the sources disagree.** Hansen (EP375, EP449) and Colorado State say to space every plant so it touches neighbours only at maturity. Kingsbury, Rainer and West, and RHS plant herbaceous layers denser and manage by editing.

Sources:

- Tier 2, partial: Kingsbury, N. (2019, 20 June). Mind the Gap! Noel Kingsbury (author's own essay summarising his density trial published in The Plantsman). <https://www.noelkingsbury.com/noelsgarden-blog/2019/6/20/mind-the-gap>
  - 'Plantings quickly look full and potentially a good canopy can develop, but only if the plant forms used mesh together'.
- Tier 2, partial: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'After the second year, thinning out dominant species will be necessary'. A planted border is 'Less dense than a seeded prairie, so there are more opportunities for weed seedlings'.
- Tier 2, partial: University of Illinois Extension (2023, 9 January). Planning a new perennial garden? Plant for the whole garden ecosystem (quoting L. Knoche, Red Oak Rain Garden, on the Rainer and West layer method). <https://extension.illinois.edu/news-releases/planning-new-perennial-garden-plant-whole-garden-ecosystem>
  - Groundcover 'planted as little as 12 inches apart. As they fill in and mature, they protect from soil erosion'.
- Tier 2, partial: Hansen, G. Landscape Design: Ten Important Things to Consider. ENH1112/EP375. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP375>
  - Counter-view and wall rule: 'If plants are spaced too closely (to simulate a fully grown landscape) the overcrowded plants will present a maintenance issue.' and 'leave space so the plant does not touch the side of the house'.

## 7. Year-round interest

### 7.1 `design.interest_every_season`

Give the bed at least one feature of interest in every season. Stagger bloom by layer: low plants in spring, mid plants in summer, tall plants in late summer and autumn.

- Value: `{"seasons": ["spring", "summer", "autumn", "winter"], "min_features_per_season": 1, "succession_by_layer": {"low": "spring", "mid": "late spring to summer", "tall": "midsummer to autumn"}}`
- Critical: yes

Sources:

- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Aim to have something in flower or looking good in every month of the year.'
- Tier 2, partial: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'Perennial gardens should ... provide a progression of bloom and textures all season.'
- Tier 2, supported: University of Illinois Extension (2023, 9 January). Planning a new perennial garden? Plant for the whole garden ecosystem (quoting L. Knoche, Red Oak Rain Garden, on the Rainer and West layer method). <https://extension.illinois.edu/news-releases/planning-new-perennial-garden-plant-whole-garden-ecosystem>
  - 'Plan for seasonality. Make sure to include some spring ephemerals, summer bloomers, fall color, and winter visual interest.'
- Tier 1, supported: Hitchmough, J. D. (2008). New approaches to ecologically based, designed urban plant communities in Britain: do these have any relevance in the United States? Cities and the Environment (CATE) 1(2), Article 10. <https://doi.org/10.15365/1932-7048.1019>
  - 'a low growing, spring flowering shade tolerant understory layer ..., a mid-canopy late spring to summer flowering layer and a taller mid-summer to autumn flowering layer'.
- Tier 2, supported: Royal Horticultural Society Advice Team. Prairie Planting Ideas and Maintenance (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/prairie-planting-creation-maintenance>
  - 'Start with a low understory of spring perennials with a mix of taller perennials to follow, with flowering progressing through to autumn'.
- Tier 1, partial: Hitchmough, J., Wagner, M. and Ahmad, H. (2017). Extended flowering and high weed resistance within two layer designed perennial 'prairie-meadow' vegetation. Urban Forestry & Urban Greening 27, 117-126. <https://doi.org/10.1016/j.ufug.2017.06.022>
  - The winter-green under-canopy gave 'a major flowering display in spring' and improved 'winter appearance'.

### 7.2 `design.evergreen_share`

Make about one-third of the planting hold structure in winter. Count evergreen shrubs, winter-green groundcovers and species with persistent stems.

- Value: `0.33` ratio
- Critical: no

**Where the sources disagree.** K-State counts evergreens only. Oudolf and Hitchmough get winter structure from standing skeletons and winter-green understoreys. Recommend counting all three toward one-third.

Sources:

- Tier 2, supported: Patton, D. Create Year-Round Interest by Thoughtful Placement of 'Garden Bones'. K-State Research and Extension, Johnson County. <https://www.johnson.k-state.edu/programs/lawn-garden/agent-articles-fact-sheets-and-more/agent-articles/trees-shrubs/Create%20Year-Round%20Interest%20by%20Thoughtful%20Placement%20of%20Garden%20Bones.html>
  - 'The plant materials in the entrance planting should be at least one-third evergreen. This basic landscape rule can be applied throughout the entire garden' and 'Too many evergreens do not create the landscape changes throughout the year'.
- Tier 2, partial: Hansen, G. Landscape Design: Ten Important Things to Consider. ENH1112/EP375. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP375>
  - 'All plant compositions begin with the main structure plants, the large, mostly evergreen background plants'. No number.
- Tier 2, partial: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Start by positioning evergreen and large structural plants, to create the ‘bones’ of the border.' No number.

### 7.3 `design.winter_stems`

Choose species with stems and seed heads that stand through winter, and leave them standing. Cut them in late winter to a 1 to 2 ft stubble.

- Value: `{"leave_standing": true, "stubble_ft": [0.67, 2.0], "cut_window": "between first autumn frost and last spring frost"}` ft
- Critical: yes

**Where the sources disagree.** Colorado State asks for a full autumn clean-up where disease is present, for example powdery mildew.

Sources:

- Tier 2, supported: Oudolf, P. (2023). Piet Oudolf at Work. London: Phaidon. Interview with H. U. Obrist and T. Sehgal, excerpt reproduced by permission of Phaidon in Domino, 17 April 2023. <https://www.domino.com/design-by-room/piet-oudolf-at-work-excerpt/>
  - 'We found that the best way was to leave plants to go to seed. We stopped cutting back the plants too early—the skeletons were attractive enough to leave.'
- Tier 2, supported: Youngsteadt, E., Levenson, H., Rose, L. and Glen, C. (2025). Garden Cleanup for Pollinators: Trim Perennial Stems in Their First Winter. AG-984. NC State Extension. <https://content.ces.ncsu.edu/garden-cleanup-for-pollinators-trim-perennial-stems-in-their-first-winter>
  - 'To create maximum habitat for stem-nesting bees, trim stems back to leave a stubble 12 to 24 inches tall' and 'You can leave the seed heads in place long enough to feed the birds'.
- Tier 2, supported: Xerces Society for Invertebrate Conservation. Nesting & Overwintering Habitat for Pollinators & Other Beneficial Insects. Publication 18-014. <https://xerces.org/sites/default/files/publications/18-014.pdf>
  - 'In a wildflower garden, leave flower stalks (and seed heads) intact over the winter.' and 'make your cuts at a variety of heights from about 8–24" above the ground.'
- Tier 2, partial: Waltman, D., Cox, R. A., Greene, L. H. and Klett, J. E. Perennial Gardening. Fact Sheet 7.402. Colorado State University Extension (reviewed August 2025). <https://extension.colostate.edu/resource/perennial-gardening/>
  - 'In order to support winter pollinator and wildlife habitat, less perennial cutback and clean-up are suggested during the fall season.'

## 8. Form and texture

### 8.1 `design.form_texture_first`

Compose the bed with form and texture first, then add colour. The bed must still look balanced when nothing is in flower.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'A good strategy is to design the entire plan, including the focal points, with form and texture as the first consideration and then use color for additional emphasis if needed. The composition should be balanced and visually pleasing with or without color.'
- Tier 2, supported: Hansen, G. Landscape Design: Ten Important Things to Consider. ENH1112/EP375. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP375>
  - 'Form and texture both trump color in the garden for most of the year.'
- Tier 2, partial: Park Brown, S. Gardening with Perennials in Florida. ENH-68/MG035 (rev. December 2022). UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG035/pdf>
  - 'When designing a bed, think of plant form and texture ... Pleasing foliage combinations ... give the garden interest long after the flowers are gone.'
- Tier 1, partial: Hoyle, H., Hitchmough, J. and Jorgensen, A. (2017). All about the 'wow factor'? The relationships between aesthetics, restorative effect and perceived biodiversity in designed urban planting. Landscape and Urban Planning 164, 109-123. <https://doi.org/10.1016/j.landurbplan.2017.03.011>
  - 'green planting outside the narrow flowering season of most species is greatly valued.'

### 8.2 `design.adjacent_contrast`

Place contrasting forms and leaf textures next to each other. Put spiky or upright forms beside mounding forms, and fine leaves beside bold leaves.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Hansen (EP433) also warns: 'too many complex forms tend to look chaotic, and too many simple forms can be boring.'

Sources:

- Tier 2, supported: Alvarez, E. and Hansen, G. Landscape Design: Aesthetic Characteristics of Plants. ENH1172/EP433. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP433>
  - 'For variety, choose plants that contrast with strikingly different forms; for example, place a spiky form next to a soft, mounding form.'
- Tier 2, supported: Park Brown, S. Gardening with Perennials in Florida. ENH-68/MG035 (rev. December 2022). UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG035/pdf>
  - 'Pleasing foliage combinations (clumping with upright forms; delicate with bold textures)'.
- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Place different sizes, forms and textures of foliage near each other to create attractive combinations.'

## 9. Placement order

### 9.1 `design.place_order`

Place plants in this order: structure, anchors, masses, fillers. Start with the back layer against the wall and work forward.

- Value: `["structure", "anchors", "masses", "fillers"]`
- Critical: yes

**Where the sources disagree.** Some matrix practitioners lay the groundcover grid first and set other layers into it. Only Tier 3 sources state that order.

Sources:

- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Start by positioning evergreen and large structural plants, to create the ‘bones’ of the border. Then position groups of herbaceous perennials or small deciduous shrubs'.
- Tier 2, supported: Hansen, G. Landscape Design: Ten Important Things to Consider. ENH1112/EP375. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP375>
  - 'All plant compositions begin with the main structure plants ... provide the starting point for choosing ... the second layer, midground plants, for massing and infill. The final layer of plants, the foreground plants'.
- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'The background or tallest layer is typically located along a fence, wall, or property line, so it is usually best to locate this layer first and work forward to the foreground.'

## 10. Colour

### 10.1 `design.color_theme_count`

Limit a small bed to two or three main flower colours. Use adjacent hues on the colour wheel, or one complementary pair.

- Value: `[2, 3]` count
- Critical: yes

**Where the sources disagree.** Hoyle et al. (2018) found that public aesthetic response rose with flower colour diversity. Designers limit hues for coherence. Recommend 2 or 3 dominant hues, plus neutrals and small accents.

Sources:

- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Small borders are generally pleasing to the eye when the colour palette is limited; lots of different colours can look chaotic. Selecting three colours next to each other on the colour wheel ... or selecting colours from opposite sides of the wheel ... generally creates pleasing results.'
- Tier 2, partial: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'Repeat one distinct form or texture, or two to three colors in selected beds'.
- Tier 2, partial: Hansen, G. Landscape Design: Ten Important Things to Consider. ENH1112/EP375. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP375>
  - 'Typically one color, two contrasting colors, or several analogous (similar) colors are repeated throughout the garden.'

### 10.2 `design.color_in_drifts`

Place colour in drifts and masses, not as single dots. Let each colour flow through the layers.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Scatter plants in the Oudolf matrix model are dotted on purpose. Keep scatter to the filler share.

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Arranging Plants in the Landscape. ENH1188/EP449. UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/EP449>
  - 'avoid scattering different colors in small clumps or spots throughout the garden. Color should flow through the layers from top to bottom and front to back'.
- Tier 2, supported: Park Brown, S. Gardening with Perennials in Florida. ENH-68/MG035 (rev. December 2022). UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG035/pdf>
  - 'The bold displays of color they provide are much more pleasing than individual plants placed here and there.'
- Tier 2, supported: Penn State Extension Master Gardeners of Chester County. Perennials (how-to gardening brochure). Penn State Extension. <https://extension.psu.edu/programs/master-gardener/counties/chester/how-to-gardening-brochures/perennials-1>
  - 'Mass plants of the same kind to create color drifts several feet long, or clumps two to three feet around.'
- Tier 2, supported: K-State Research and Extension. Extension Master Gardener Handbook, Chapter 8: Herbaceous Plants (section 'Planning the Flower Border'). <https://www.meadowlark.k-state.edu/docs/lawn_garden/extension-master-gardener/handouts/EMG%20Handbook%20chapter%208%20Herbaceous%20Plants.pdf>
  - 'Establish plants in groups large enough to form masses of color or texture.'

### 10.3 `design.color_placement`

Group warm colours together and away from cool colours and pastels. Put hot colours nearest the main view; use white, blue, silver and green as buffers.

- Value: `{"warm_grouped": true, "warm_near_viewer": true, "buffers": ["white", "blue", "silver", "green"]}`
- Critical: yes

Sources:

- Tier 2, supported: Park Brown, S. Gardening with Perennials in Florida. ENH-68/MG035 (rev. December 2022). UF/IFAS Extension, University of Florida. <https://edis.ifas.ufl.edu/publication/MG035/pdf>
  - '“Warm” colors, such as orange, red, and yellow, should be grouped together and segregated from “cool” hues and pastels. White, blue, silver/gray, and green go with everything and can be used as transition colors'.
- Tier 2, supported: Royal Horticultural Society Advice Team. Planning a Beautiful Garden Border (RHS Advice Guide). <https://www.rhs.org.uk/garden-design/how-to-plan-a-border>
  - 'Placing bright, hot colours and larger flowers closest to where you will most often view the border from works well, with paler, smaller flowers located at the far end.' and green offers 'a rest between other colours.'

### 10.4 `design.public_preference`

People prefer plantings with more species, some height structure and plenty of flower at peak. Aim for more than 27% flower cover at peak bloom.

- Value: `{"prefer_species_rich": true, "prefer_even_mix": true, "flower_cover_peak_min": 0.27}` ratio
- Critical: yes

**Where the sources disagree.** Hansen (EP449) advises larger masses and fewer species. Hoyle (2018) favours more colours than the RHS limited palette. All studies are UK or Swiss public greenspace, not home borders.

Sources:

- Tier 1, supported: Lindemann-Matthies, P., Junge, X. and Matthies, D. (2010). The influence of plant diversity on people's perception and aesthetic appreciation of grassland vegetation. Biological Conservation 143(1), 195-202. <https://doi.org/10.1016/j.biocon.2009.10.003>
  - 'Lay people’s aesthetic appreciation of both the experimental grassland arrays and the natural meadows increased with true species richness.' and communities 'were appreciated more when their evenness was high.'
- Tier 1, supported: Southon, G. E., Jorgensen, A., Dunnett, N., Hoyle, H. and Evans, K. L. (2017). Biodiverse perennial meadows have aesthetic value and increase residents' perceptions of site quality in urban green-space. Landscape and Urban Planning 158, 105-118. <https://doi.org/10.1016/j.landurbplan.2016.08.003>
  - 'Meadows that contained more plant species and some structural diversity (i.e. were tall or of medium height) were most preferred.'
- Tier 1, supported: Hoyle, H., Hitchmough, J. and Jorgensen, A. (2017). All about the 'wow factor'? The relationships between aesthetics, restorative effect and perceived biodiversity in designed urban planting. Landscape and Urban Planning 164, 109-123. <https://doi.org/10.1016/j.landurbplan.2017.03.011>
  - 'Colourful planting with flower cover above a critical threshold (27%) was associated with the highest level of aesthetic preference.'
- Tier 1, partial: Hoyle, H., Norton, B., Dunnett, N., Richards, J. P., Russell, J. M. and Warren, P. (2018). Plant species or flower colour diversity? Identifying the drivers of public and invertebrate response to designed annual meadows. Landscape and Urban Planning 180, 103-113. <https://doi.org/10.1016/j.landurbplan.2018.08.017>
  - 'Flower colour diversity had effects on human aesthetic response' and 'people used colour diversity as a cue to assessing species diversity'.

## 11. Legibility

### 11.1 `design.cues_to_care`

Show clear signs of intention in a naturalistic bed. Use a neat, continuous low front edge and recognisable masses so the bed reads as cared for.

- Value: `{"neat_front_edge": true, "visible_masses": true}`
- Critical: yes

**Where the sources disagree.** Hoyle et al. (2017) found planting of moderate or most natural structure the most restorative, which suggests growing acceptance of a messier look.

Sources:

- Tier 1, supported: Nassauer, J. I. (1995). Messy ecosystems, orderly frames. Landscape Journal 14(2), 161-170. <https://doi.org/10.3368/lj.14.2.161>
  - 'Novel landscape designs that improve ecological quality may not be appreciated or maintained if recognizable landscape language that communicates human intention is not part of the landscape.'
- Tier 1, supported: Hitchmough, J. D. (2008). New approaches to ecologically based, designed urban plant communities in Britain: do these have any relevance in the United States? Cities and the Environment (CATE) 1(2), Article 10. <https://doi.org/10.15365/1932-7048.1019>
  - Planting 'in groups or blocks ... makes it clear to viewers that the plantings are intentional and probably cared for'.
- Tier 2, supported: Dunnett, N. and Hitchmough, J. (eds.) (2004). The Dynamic Landscape: Design, Ecology and Management of Naturalistic Urban Planting. London: Spon Press. Not opened; chapter content confirmed through Seppanen (2019) and Hitchmough (2008). <https://doi.org/10.4324/9780203402870>
  - Seppanen (2019): 'Dunnet and Hitchmough (2004) state that nature-like plantings that do not seem clearly designed and cared for are not particularly valued by the public.'
