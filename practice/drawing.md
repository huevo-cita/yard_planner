# How to draw a planting plan

This document holds the rules for drawing a planting plan on paper and on a screen. Each rule has its sources, and a check opened every source.

`lib.scheme` and `lib.drawbeds` read the numbers from `practice/rules.json`. Do not copy a number from this document into code. Read it with `practice.rule(key)`.

A source is tier 1 when it is peer-reviewed. A source is tier 2 when it is an extension service, a standard, a platform guideline, or a textbook by an established author. A tier 3 source cannot back a rule. A rule marked critical has two or more independent tier 1 or tier 2 sources.

## 1. Plant symbol size

### 1.1 `drawing.symbol_at`

The solid plant circle has a diameter equal to the on-center spacing. Two neighbours at the planned spacing then touch.

- Value: `"spacing"`
- Critical: no

**Where the sources disagree.** Only one Tier 2 source states the circle-equals-spacing identity directly, so the two-source bar is NOT met. EP456 draws the circle at mature width and sets spacing equal to it, so both readings agree there. Alexandria draws at 60% of spread and Montgomery County spaces at 2/3 of spread; together they imply circle is about spacing, but neither says so. Recommend 'spacing' because it is the only size that makes the drawn count equal the planted count.

Sources:

- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 9: 'a plant spacing of 2' o.c. (2 feet on center) means that plants with a 2-foot mature spread are planted 2 feet apart from center to center, so they touch when at their mature size.'

### 1.2 `drawing.mature_fraction`

Draw the mature-spread outline at 100% of the mature spread. Do not shrink it to a percentage.

- Value: `1.0` ratio
- Critical: yes

**Where the sources disagree.** Alexandria (2019) Ch. 2 item 3 requires symbols 'drawn to scale using ... sixty (60) percent of the total mature spread' for all trees and shrubs, to represent canopy-credit crown area on development plans. ISO 11091 ref. 3.23 says the proposed-tree circle 'is not drawn to scale and does not represent the crown at planting or at maturity.' Recommend 1.0 for a bed-scale garden plan: three sources agree, and 0.6 is a canopy-credit convention for trees on permit drawings.

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 9: 'Draw each plant as an individual circle with a diameter the same size as the width of the mature plant.'
- Tier 2, supported: Spafford, A., M. Wallace, C. Lauderdale, L.K. Bradley, and K.A. Moore. 2022. Landscape Design, Chapter 19. In: K.A. Moore and L.K. Bradley (eds). North Carolina Extension Gardener Handbook, 2nd ed. NC State Extension, Raleigh, NC. <https://content.ces.ncsu.edu/extension-gardener-handbook/19-landscape-design>
  - Step 6: 'Once the specific plants are selected, they can be drawn to scale at their mature size on the plan.'
- Tier 2, supported: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - Plant Information: 'Plant symbols - use clear simple graphics to show location of new trees, shrubs, groundcovers and climbers drawn to mature size.'

### 1.3 `drawing.mature_ring`

Draw the mature spread as a thin, unfilled outline when it is larger than the spacing circle. Always draw it for trees and large shrubs.

- Value: `"when mature spread > spacing, and always for trees"`
- Critical: yes

**Where the sources disagree.** The specific convention 'solid circle at spacing plus dashed circle at mature spread' was NOT found in any Tier 1 or Tier 2 source that could be opened. The sources support an unfilled spread outline, not the dash. ISO reserves thin dashed lines for existing contours and areas to be removed, so a dashed mature ring can be confused with 'to be removed'. Recommend a thin solid or dotted outline, and keep dashes for removal.

Sources:

- Tier 2, partial: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.18 Proposed shrub/plant: 'Spread may be shown.' Ref. 3.22 Existing tree: 'The crown circle is drawn with a thin line.'
- Tier 2, partial: Spafford, A., M. Wallace, C. Lauderdale, L.K. Bradley, and K.A. Moore. 2022. Landscape Design, Chapter 19. In: K.A. Moore and L.K. Bradley (eds). North Carolina Extension Gardener Handbook, 2nd ed. NC State Extension, Raleigh, NC. <https://content.ces.ncsu.edu/extension-gardener-handbook/19-landscape-design>
  - Step 6: 'Trees should be drawn with symbols that are transparent so the elements under the tree's canopy can be seen easily.'
- Tier 2, partial: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - Plant Information: 'Trees should not be heavily branched; use heavy line weight for the canopy outlines this will enable clarity beneath the canopy.'

### 1.4 `drawing.circles_touch`

Adjacent circles of one mass touch and do not overlap when the circles are drawn at the on-center spacing.

- Value: `true`
- Critical: no

**Where the sources disagree.** Only one source states this directly, so the two-source bar is NOT met. It follows geometrically from drawing.symbol_at and drawing.oc_definition. Montgomery County spaces plants at 2/3 of mature spread, so mature-spread outlines overlap at maturity even when spacing circles touch.

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 9: '...planted 2 feet apart from center to center, so they touch when at their mature size.' Also: 'Fill the bubble with plants by staggering the circles in a rickrack pattern to fit the plants as closely as possible.'

## 2. Spacing

### 2.1 `drawing.oc_definition`

On-center (o.c.) spacing is the distance from the center of one plant to the center of the next plant.

- Value: `null` ft
- Critical: yes

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: 'The spacing shows the distance from center to center of each plant at the time of installation.'
- Tier 2, supported: Montgomery County (Maryland) Department of Environmental Protection. RainScapes: Plant Spacing Guide. <https://www.montgomerycountymd.gov/department-environmental-protection/property-care/rainscapes/rainscapes-plant-spacing-guide>
  - Definitions: 'On Center (o.c.) refers to the distance between the centers of two adjacent plants.'
- Tier 2, partial: City of Alexandria, Virginia. 2019. Landscape Guidelines (approved February 2019). Department of Planning and Zoning / RPCA. <https://media.alexandriava.gov/docs-archives/recreation/parkplanning/landscapeguidelinesfinalv2final.pdf>
  - Street trees: 'spaced a minimum of every twenty-five (25) linear feet and a maximum of every thirty (30) linear feet (specified on-center, O.C.)'

### 2.2 `drawing.spacing_default`

Use the spacing that the plant record states. If there is no spacing, use the mature spread and mark the value as assumed.

- Value: `1.0` ratio
- Critical: no

**Where the sources disagree.** EP456 uses spacing = 1.0 x mature spread for a general home landscape. Montgomery County uses 0.67 x mature spread for stormwater plantings that 'must be planted more densely than traditional gardens'. Recommend 1.0 as the fallback for an ordinary garden bed, and 0.67 only where fast cover is the goal. This is a default, not a drawing convention, so it is not critical.

Sources:

- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 9: plants with a 2-foot mature spread are planted '2 feet apart from center to center'.

## 3. Masses and drifts

### 3.1 `drawing.mass_as_bubble`

Draw a mass of one species as one outline. Individual circles inside a large groundcover mass are optional.

- Value: `true`
- Critical: yes

**Where the sources disagree.** EP456 fills each bubble with individual circles for the final plan so that the count is exact; ISO allows the outline alone. Recommend both: draw the outline, and draw the individual circles when there are few enough to tap.

Sources:

- Tier 2, supported: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.18: 'For even distribution of large numbers (e.g. ground cover) individual dots are not essential (see figure A.1).'
- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 7: 'draw free-form or irregular "bubbles" within the plant beds to show the location and extent of a particular plant cluster' and 'each bubble represents a different mass or cluster of the same plant.'
- Tier 2, partial: Spafford, A., M. Wallace, C. Lauderdale, L.K. Bradley, and K.A. Moore. 2022. Landscape Design, Chapter 19. In: K.A. Moore and L.K. Bradley (eds). North Carolina Extension Gardener Handbook, 2nd ed. NC State Extension, Raleigh, NC. <https://content.ces.ncsu.edu/extension-gardener-handbook/19-landscape-design>
  - Step 6: 'ground covers can be darkly or densely drawn as nothing is planted underneath them.'

### 3.2 `drawing.one_label_per_mass`

Give each mass one label with the plant count and the plant name or code. Do not label every plant.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: 'Each symbol represents a different plant that must be identified by a count and the name of the plant. The count represents the number of plants that are in the cluster or mass.'
- Tier 2, supported: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.18: 'Number of species may be linked together with a thin line and annotated on drawing, or numbered by reference to a schedule.'
- Tier 2, partial: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - Plant Information: 'Plant labelling and numbering - should be brief and clear, preferably based on plant numbers or names such as 3 (5) or Cr (4)'.

## 4. Labels and leaders

### 4.1 `drawing.leaders_short_thin`

Draw each leader line as short as possible and with the thinnest line weight on the plan.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Knox (2024) allows 'longer extension leaders if required' to move text off line work. Recommend short by default, and longer only to clear line work.

Sources:

- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: 'Draw the leader lines as short as possible and don't cross lines to avoid confusion.'
- Tier 2, partial: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.18: plants of one species 'may be linked together with a thin line and annotated on drawing'.

### 4.2 `drawing.leaders_do_not_cross`

Leader lines do not cross each other. All label text stays at one angle.

- Value: `true`
- Critical: no

**Where the sources disagree.** Only one Tier 2 source states either part, so the two-source bar is NOT met. Knox supports the intent ('Do not place plant and plan annotation over hatch or line work'). Cartographic label-placement literature probably supports it but no copy could be opened. Keep the rule; treat it as unverified by a second source.

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: 'don't cross lines to avoid confusion' and 'For clarity, it is best to keep all of the text at the same angle and group the labels so they are easier to find on the plan.'

### 4.3 `drawing.label_clear_of_linework`

Put each label in clear space. Do not put label text on top of line work, hatching or plant symbols.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - Plant Information: 'Do not place plant and plan annotation over hatch or line work where is becomes obscured or difficult to read and comprehend. Move the text or use longer extension leaders if required.'
- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: 'Leader lines are drawn from one of the plant symbols in the mass to a blank space on the plan where the count and name can be written.'

### 4.4 `drawing.label_on_plan`

Label masses directly on the plan. Do not make the reader match colours against a separate key.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Okabe, M., and K. Ito. 2002, modified 2008. Color Universal Design (CUD): How to make figures and presentations that are friendly to colorblind people. <https://jfly.uni-koeln.de/color/>
  - 'For graphs and line drawings, label elements of the graph on the graph itself rather than making a separate color-coded key, since matching same colors in distant places is extremely difficult.'
- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: every mass carries a count and name label on the plan, joined to it by a leader line.
- Tier 2, partial: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - Plant labels such as '3 (5) or Cr (4)' sit on the plan and link to the Plant Schedule.

## 5. Plant schedule

### 5.1 `drawing.schedule_columns`

The plant schedule lists each plant once with its code, names, total quantity, size, spacing and mature dimensions.

- Value: `["code", "common name", "botanical name", "quantity", "size at planting", "spacing (o.c.)", "mature height", "mature spread"]`
- Critical: yes

**Where the sources disagree.** Sources differ on which columns are required. EP456 has spacing but no mature size; Knox and NC State have mature size but no spacing. ISO puts name first and allows the rest. Recommend the union, because the map draws from both spacing and mature spread. Code is first so the reader can match the plan label to the row (Knox checklist: 'plant code, name, height, width, pot size and quantity').

Sources:

- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10 and Table 2: 'Each plant is listed by the common name and the scientific name... The size of the container for each plant and the spacing for installation is indicated.' Table 2 columns: Common name, Scientific name, Quantity, Size, Spacing.
- Tier 2, partial: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Clause 4: 'A planting schedule may contain ... name; classification/designation; root system; planting location; quantity. Other information such as height, spread, form, cost, etc. may be included.'
- Tier 2, partial: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - Plant Information: 'It must show all proposed plants with botanical name, common name, mature height, width, pot size and quantity.'
- Tier 2, partial: City of Alexandria, Virginia. 2019. Landscape Guidelines (approved February 2019). Department of Planning and Zoning / RPCA. <https://media.alexandriava.gov/docs-archives/recreation/parkplanning/landscapeguidelinesfinalv2final.pdf>
  - Ch. 2: 'A plant legend/index or schedule that indicates the plan species with botanic and common names, height/ size, and total quantity of all proposed plantings at time of installation.'
- Tier 2, partial: Spafford, A., M. Wallace, C. Lauderdale, L.K. Bradley, and K.A. Moore. 2022. Landscape Design, Chapter 19. In: K.A. Moore and L.K. Bradley (eds). North Carolina Extension Gardener Handbook, 2nd ed. NC State Extension, Raleigh, NC. <https://content.ces.ncsu.edu/extension-gardener-handbook/19-landscape-design>
  - Table 19-1 columns: 'Plot Plan Reference | Plant Type | Botanical Name | Common Name(s) | Cultivar(s) | Mature Height | Mature Spread'.

### 5.2 `drawing.botanical_name_required`

Every schedule row carries the botanical name. A common name alone is not enough.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 10: 'Common names can vary, and some plants have more than one common name, so the scientific name is required to ensure that the correct plant is purchased.'
- Tier 2, supported: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - 'It must show all proposed plants with botanical name, common name...'
- Tier 2, supported: City of Novi, Michigan. Landscape Design Manual. <https://cityofnovi.org/media/gpqnrjm3/landscapedesignmanual.pdf>
  - Plan requirements k: 'A planting schedule ... showing the quantity of materials for each species, botanical and common names of plant materials, caliper sizes or container sizes'.

## 6. Line weight

### 6.1 `drawing.line_hierarchy`

Use a thick line for proposed planting outlines and a thin line for existing features, leaders and text. Boundaries take the heaviest line.

- Value: `["boundary: extra-thick", "proposed plant or canopy outline: thick", "existing plant: thin", "leader, dimension, centre mark: thin"]`
- Critical: yes

Sources:

- Tier 2, supported: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.21 Proposed hedge 'Thick irregular line' vs 3.20 Existing hedge 'Thin irregular line'; 3.23 Proposed tree 'crown circle is drawn with a thick line and the cross with a thin line'; 3.22 Existing tree 'crown circle is drawn with a thin line'; A.1.8 Contract boundary 'Extra-thick chain line'.
- Tier 2, partial: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - 'use heavy line weight for the canopy outlines' and 'Grey scale/colour must not be used for primary line work.'

## 7. Existing, proposed, removed

### 7.1 `drawing.existing_line`

Draw an existing plant that stays with a thin solid line and a label style that differs from proposed plants.

- Value: `"thin"`
- Critical: yes

**Where the sources disagree.** The brief expected 'dashed' for existing. The sources do not support that for retained plants: ISO uses a thin dashed line for existing contours (ref. 3.3) and for areas to be removed (ref. 3.9), and a thin solid line for existing trees and hedges. Recommend 'thin' for retained plants and keep 'dashed' for removal (drawing.removed_line).

Sources:

- Tier 2, supported: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.20 'Existing hedge to be retained: Thin irregular line'; 3.22 'Existing tree: The crown circle is drawn with a thin line and the trunk circle with a thick line. Trunk and crown circles shall be drawn approx. to scale'.
- Tier 2, partial: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - 'The labelling system for existing plants must be clearly different and separate from that used for the proposed plants.'

### 7.2 `drawing.removed_line`

Draw a plant or area to be removed with a dashed outline. An X on the symbol is an accepted alternative.

- Value: `"dashed"`
- Critical: yes

**Where the sources disagree.** Novi uses an X or R mark instead of a dash. Recommend the dashed outline plus an X, so that removal does not depend on one cue.

Sources:

- Tier 2, supported: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - 'Vegetation to be removed - should be plotted with a dashed circle.' Example plan note: 'Existing trees to be removed identified to species level, shown to scale with a dashed circle'.
- Tier 2, supported: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Ref. 3.9 'General area to be removed: Thin dashed line; this symbol is an alternative to ISO 7518'.
- Tier 2, partial: City of Novi, Michigan. Landscape Design Manual. <https://cityofnovi.org/media/gpqnrjm3/landscapedesignmanual.pdf>
  - 'All removals shall be clearly marked as to be removed with an X or R on the tree symbol on the plan view, and on the accompanying tree chart/list (show as Saved or Removed).'

## 8. Symbols by habit

### 8.1 `drawing.habit_marks`

Give each plant habit a different symbol, so that tree, shrub, evergreen, grass and perennial read apart without colour.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 9: 'Distinguish circles of the same size that represent different plants by using different symbols (see graphic plan, Figure 9) or a different color to be graphically clear.'
- Tier 2, partial: Spafford, A., M. Wallace, C. Lauderdale, L.K. Bradley, and K.A. Moore. 2022. Landscape Design, Chapter 19. In: K.A. Moore and L.K. Bradley (eds). North Carolina Extension Gardener Handbook, 2nd ed. NC State Extension, Raleigh, NC. <https://content.ces.ncsu.edu/extension-gardener-handbook/19-landscape-design>
  - Step 6: 'Evergreen versus deciduous trees and shrubs should be graphically easy to distinguish.'
- Tier 2, partial: City of Alexandria, Virginia. 2019. Landscape Guidelines (approved February 2019). Department of Planning and Zoning / RPCA. <https://media.alexandriava.gov/docs-archives/recreation/parkplanning/landscapeguidelinesfinalv2final.pdf>
  - Ch. 2 item 3: symbols 'shall graphically differentiate between shade, ornamental and evergreen trees'.
- Tier 2, supported: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Clause 3 gives separate conventions for proposed tree (3.23), proposed shrub/plant (3.18), climber (3.19), hedge (3.20, 3.21) and grass (3.16).

## 9. Colour and outline

### 9.1 `drawing.outline_over_fill`

The outline and the symbol mark identify each plant. Colour fill is extra information and never the only cue.

- Value: `true`
- Critical: yes

**Where the sources disagree.** EP456 Step 9 allows 'a different color' as an alternative to different symbols, and Oudolf's plans are colour-coded (Tier 3 coverage only). Knox bans colour for print legibility. Recommend colour as a redundant fill on a screen, with outline and mark doing the identifying work, which also satisfies drawing.color_not_alone.

Sources:

- Tier 2, supported: Knox City Council (Victoria, Australia). 2024. Landscape Plan Guidelines: How to prepare a Landscape Plan for planning applications. April 2024. <https://www.knox.vic.gov.au/sites/default/files/2024-04/Landscape%20Guidelines%20April_2024.pdf>
  - 'These should be drawn in black ink only. The use of colour often is not very clear and is difficult to comprehend.' and 'If a colour plan is printed in black and white the plan will lose clarity'.
- Tier 2, partial: ISO 11091:1994. Construction drawings - Landscape drawing practice. International Organization for Standardization, Geneva. (Clauses 3 and 4 read in the iTeh public preview.) <https://cdn.standards.iteh.ai/samples/19080/afb2b5ab93dc4687b30d6aa25c7ab795/ISO-11091-1994.pdf>
  - Every plant convention in clause 3 is defined by line weight and line type (thick, thin, dashed, irregular), not by colour.

### 9.2 `drawing.color_not_alone`

Do not use colour as the only way to show plant identity, bloom state or status. Add a shape, pattern, line type or text.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, supported: W3C. 2023. Web Content Accessibility Guidelines (WCAG) 2.2. W3C Recommendation. SC 1.4.1, 1.4.3, 1.4.11, 2.5.5, 2.5.8. <https://www.w3.org/TR/WCAG22/>
  - SC 1.4.1 Use of Color (Level A): 'Color is not used as the only visual means of conveying information, indicating an action, prompting a response, or distinguishing a visual element.'
- Tier 2, supported: Apple Inc. Human Interface Guidelines: Color. <https://developer.apple.com/design/human-interface-guidelines/color>
  - 'When you use color to convey information, be sure to provide the same information in alternative ways so people with color blindness or other visual disabilities can understand it. For example, you can use text labels or glyph shapes.'
- Tier 2, supported: Okabe, M., and K. Ito. 2002, modified 2008. Color Universal Design (CUD): How to make figures and presentations that are friendly to colorblind people. <https://jfly.uni-koeln.de/color/>
  - 'Use not only different colors but also a combination of different shapes, positions, line types and coloring patterns'.
- Tier 2, supported: Apple Inc. Human Interface Guidelines: Accessibility. (Read through the page's JSON data endpoint because the HTML page needs JavaScript.) <https://developer.apple.com/design/human-interface-guidelines/accessibility>
  - 'Convey information with more than color alone. ... people who are color blind may have particular difficulty with pairings such as red-green and blue-orange.'

### 9.3 `drawing.cvd_palette`

Pick categorical colours from a colour-vision-deficiency-safe set. Do not pair red and green of similar lightness.

- Value: `["black", "orange", "sky blue", "bluish green", "yellow", "blue", "vermilion", "reddish purple"]`
- Critical: yes

**Where the sources disagree.** The Okabe-Ito page gives the palette as an image, so this file records the colour names only. Take exact hex values from the published figure, not from memory. Okabe and Ito warn that sky blue and yellow are hard to read as thin lines, so use them as fills only.

Sources:

- Tier 2, supported: Okabe, M., and K. Ito. 2002, modified 2008. Color Universal Design (CUD): How to make figures and presentations that are friendly to colorblind people. <https://jfly.uni-koeln.de/color/>
  - Fig. 16 'Colorblind barrier-free color pallet': 'For red, vermilion is used...', 'For green, bluish green is chosen...', 'reddish purple is chosen', 'Sky blue and blue are chosen...'. Also: 'For thin lines and small objects, use darker blue and orange'.
- Tier 2, partial: Wong, B. 2011. Points of view: Color blindness. Nature Methods 8(6). (Editorial column, not a research article.) <https://doi.org/10.1038/nmeth.1618>
  - Figure 2: 'Colors optimized for color-blind individuals', with simulated protanopia and deuteranopia; text: 'as many as 8 percent of men and 0.5 percent of women experience the common form of red-green color blindness'.
- Tier 1, partial: Crameri, F., G.E. Shephard, and P.J. Heron. 2020. The misuse of colour in science communication. Nature Communications 11: 5444. <https://doi.org/10.1038/s41467-020-19160-7>
  - 'Colour maps that include both red and green colours with similar lightness cannot be read by a large fraction of the readership' and 'worldwide 0.5% of women and 8% of men are subject to a colour-vision deficiency'.

## 10. Screen legibility

### 10.1 `drawing.tap_target_px`

Make every tappable plant at least 44 by 44 CSS px. Use 48 px where the layout allows it.

- Value: `44` px
- Critical: yes

**Where the sources disagree.** Values range from 44 (Apple, WCAG AAA) to 48 dp (Android, about 9 mm) to 9.2 mm (Parhi). Recommend 44 CSS px as the rule, because iOS Safari maps 1 CSS px to 1 pt and WCAG uses CSS px; 48 is preferred.

Sources:

- Tier 2, supported: W3C. 2023. Web Content Accessibility Guidelines (WCAG) 2.2. W3C Recommendation. SC 1.4.1, 1.4.3, 1.4.11, 2.5.5, 2.5.8. <https://www.w3.org/TR/WCAG22/>
  - SC 2.5.5 Target Size (Enhanced) (Level AAA): 'The size of the target for pointer inputs is at least 44 by 44 CSS pixels'.
- Tier 2, supported: Apple Inc. Human Interface Guidelines: Accessibility. (Read through the page's JSON data endpoint because the HTML page needs JavaScript.) <https://developer.apple.com/design/human-interface-guidelines/accessibility>
  - Table 'Default control size / Minimum control size': 'iOS, iPadOS 44x44 pt 28x28 pt'.
- Tier 2, partial: Google. Make apps more accessible. Android Developers, App quality (last updated 2026-09-22). <https://developer.android.com/guide/topics/ui/accessibility/apps>
  - 'we recommend that each interactive UI element have a focusable area, or touch target size, of at least 48dpx48dp. Larger is even better.'
- Tier 1, partial: Parhi, P., A.K. Karlson, and B.B. Bederson. 2006. Target size study for one-handed thumb use on small touchscreen devices. Proceedings of MobileHCI 2006, pp. 203-210. ACM. <https://doi.org/10.1145/1152215.1152260>
  - Abstract and Conclusions: 'target sizes should be at least 9.2 mm for single-target tasks and 9.6 mm for multi-target tasks'.

### 10.2 `drawing.tap_target_floor_px`

No tap target is smaller than 24 by 24 CSS px, unless a 24 px circle around it touches no other target.

- Value: `24` px
- Critical: yes

**Where the sources disagree.** Apple's floor (28 pt) is stricter than WCAG AA (24 px). Recommend 24 px as the absolute floor for conformance and 28 px as the practical floor on iOS.

Sources:

- Tier 2, supported: W3C. 2023. Web Content Accessibility Guidelines (WCAG) 2.2. W3C Recommendation. SC 1.4.1, 1.4.3, 1.4.11, 2.5.5, 2.5.8. <https://www.w3.org/TR/WCAG22/>
  - SC 2.5.8 Target Size (Minimum) (Level AA): 'at least 24 by 24 CSS pixels, except when: Spacing - Undersized targets ... are positioned so that if a 24 CSS pixel diameter circle is centered on the bounding box of each, the circles do not intersect another target'.
- Tier 2, partial: Apple Inc. Human Interface Guidelines: Accessibility. (Read through the page's JSON data endpoint because the HTML page needs JavaScript.) <https://developer.apple.com/design/human-interface-guidelines/accessibility>
  - Minimum control size for iOS and iPadOS: '28x28 pt'.

### 10.3 `drawing.hit_area_beyond_symbol`

Let the tap area extend past a small drawn circle. The drawn circle stays at scale; the invisible hit area meets the target size.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Android notes that 'very small and close-together buttons' cannot always be expanded 'without causing touchable regions to overlap'. When hit areas would overlap, apply drawing.dense_target_equivalent.

Sources:

- Tier 2, supported: Google. Touch target size. Android Accessibility Help (cites the Material Design accessibility guidelines). <https://support.google.com/accessibility/android/answer/7101858?hl=en>
  - 'Touch targets extend beyond the visual bounds of an element: An element like an icon may appear to be 24x24dp but the padding surrounding it comprises the full 48x48dp touch target.'
- Tier 2, supported: W3C WAI. Understanding Success Criterion 2.5.8: Target Size (Minimum). Understanding WCAG 2.2. <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>
  - 'This success criterion defines a minimum size and, if this can't be met, a minimum spacing.' The spacing test measures a 24 px circle around the target, not the drawn glyph.

### 10.4 `drawing.dense_target_equivalent`

When plants sit too close for full-size targets, give an equivalent way to reach each plant, such as its schedule row or zoom.

- Value: `"schedule row or zoom"`
- Critical: no

**Where the sources disagree.** Only W3C addresses dense map targets directly, so the two-source bar is NOT met (WCAG 2.5.5's 'Equivalent' exception is the same authority). A to-scale plan is exactly the WCAG map case: moving circles apart to enlarge them would falsify the plan.

Sources:

- Tier 2, supported: W3C WAI. Understanding Success Criterion 2.5.8: Target Size (Minimum). Understanding WCAG 2.2. <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>
  - Essential exception: 'in digital maps, the position of pins is analogous to the position of places shown on the map... It is essential to show the pins at the correct map location... When the "Essential" exception is applicable, authors are strongly encouraged to provide equivalent functionality through alternative means'.

### 10.5 `drawing.min_text_px`

No label on the map is smaller than 11 px. Body text and the schedule use 16 to 17 px.

- Value: `11` px
- Critical: yes

**Where the sources disagree.** WCAG sets no minimum text size; it requires text to resize (SC 1.4.4) and Apple asks apps to allow enlargement 'by at least 200 percent'. Recommend 11 px as the floor, 12 px for plant labels where space allows, and text that scales with the user's setting.

Sources:

- Tier 2, supported: Apple Inc. Human Interface Guidelines: Typography. <https://developer.apple.com/design/human-interface-guidelines/typography>
  - Table 'Default size / Minimum size': 'iOS, iPadOS 17 pt 11 pt'.
- Tier 2, partial: Google. Material Components for Android: Typography theming (Material 3 baseline type scale). docs/theming/Typography.md. <https://github.com/material-components/material-components-android/blob/master/docs/theming/Typography.md>
  - Material 3 baseline scale: 'textAppearanceLabelSmall | Medium 11sp', 'textAppearanceBodySmall | Regular 12sp', 'textAppearanceBodyLarge | Regular 16sp'.

### 10.6 `drawing.text_contrast`

Label and schedule text has a contrast ratio of at least 4.5:1 against its background. Large text needs 3:1.

- Value: `4.5` ratio
- Critical: no

**Where the sources disagree.** Apple and Android both adopt the WCAG number, so they confirm it rather than derive it independently. Apple also mentions APCA as an alternative measure.

Sources:

- Tier 2, supported: W3C. 2023. Web Content Accessibility Guidelines (WCAG) 2.2. W3C Recommendation. SC 1.4.1, 1.4.3, 1.4.11, 2.5.5, 2.5.8. <https://www.w3.org/TR/WCAG22/>
  - SC 1.4.3 Contrast (Minimum) (Level AA): 'The visual presentation of text and images of text has a contrast ratio of at least 4.5:1 ... Large-scale text ... at least 3:1'.
- Tier 2, supported: Apple Inc. Human Interface Guidelines: Accessibility. (Read through the page's JSON data endpoint because the HTML page needs JavaScript.) <https://developer.apple.com/design/human-interface-guidelines/accessibility>
  - Contrast table: 'Up to 17 pts All 4.5:1; 18 pts All 3:1; All Bold 3:1'.
- Tier 2, supported: Google. Make apps more accessible. Android Developers, App quality (last updated 2026-09-22). <https://developer.android.com/guide/topics/ui/accessibility/apps>
  - 'If the text is smaller than 18sp, or if the text is bold and smaller than 14sp, use foreground and background colors that result in a color contrast ratio of at least 4.5:1.'

### 10.7 `drawing.non_text_contrast`

Plant outlines, symbol marks and bed edges have a contrast ratio of at least 3:1 against adjacent colours.

- Value: `3.0` ratio
- Critical: no

**Where the sources disagree.** Only WCAG gives a number for graphical objects, so the two-source bar is NOT met. Knox (2024) and Okabe-Ito support the intent without a number ('sufficient contrast to ensure drawing lines and text are legible'; 'enough contrasts in brightness'). Follow 3:1 anyway, because WCAG AA is the conformance target.

Sources:

- Tier 2, supported: W3C. 2023. Web Content Accessibility Guidelines (WCAG) 2.2. W3C Recommendation. SC 1.4.1, 1.4.3, 1.4.11, 2.5.5, 2.5.8. <https://www.w3.org/TR/WCAG22/>
  - SC 1.4.11 Non-text Contrast (Level AA): 'The visual presentation of the following have a contrast ratio of at least 3:1 against adjacent color(s): ... Graphical Objects: Parts of graphics required to understand the content'.

### 10.8 `drawing.label_text_px`

Set plant labels at 12 px where the space allows. The floor stays at 11 px.

- Value: `12` px
- Critical: no

**Where the sources disagree.** Apple gives 11 pt as the minimum and 17 pt as the default. 12 px sits between them and keeps a code label inside a small circle.

Sources:

- Tier 2, supported: Google. Material Components for Android: Typography theming (Material 3 baseline type scale). docs/theming/Typography.md. <https://github.com/material-components/material-components-android/blob/master/docs/theming/Typography.md>
  - Material 3 baseline scale: 'textAppearanceBodySmall | Regular 12sp'.

## 11. Seasonal change

### 11.1 `drawing.bloom_calendar`

Record the bloom months of every plant and show them as a bloom calendar, so that gaps in the sequence are visible.

- Value: `true`
- Critical: yes

**Where the sources disagree.** None of the sources prescribes a graphic form for the calendar. Oudolf's month-by-month charts and colour-coded plans are documented only in Tier 3 coverage (gallery and magazine pages), and no copy of Oudolf and Kingsbury or Rainer and West could be opened. They are context, not rule sources.

Sources:

- Tier 2, partial: Pennisi, B., P. Thomas, and S. Dorn. Landscape Basics: Success with Herbaceous Perennials. UGA Cooperative Extension Bulletin 1424 (full review 19 May 2022). <https://fieldreport.caes.uga.edu/publications/B1424/landscape-basics-success-with-herbaceous-perennials/>
  - Perennial Bed Design: 'Know the bloom period to plan a continuous bloom sequence and year-round interest. Arrange plants so certain areas of the bed are in bloom at same time.'
- Tier 2, partial: Alvarez, E., and G. Hansen. Landscape Design: Aesthetic Characteristics of Plants. ENH1172/EP433. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP433>
  - Color: 'Consider the length of bloom for the flowers...' and 'Consider the seasonal timing of the color. Plan for a sequence of flowering color throughout the year for year-round color.'
- Tier 2, partial: Spafford, A., M. Wallace, C. Lauderdale, L.K. Bradley, and K.A. Moore. 2022. Landscape Design, Chapter 19. In: K.A. Moore and L.K. Bradley (eds). North Carolina Extension Gardener Handbook, 2nd ed. NC State Extension, Raleigh, NC. <https://content.ces.ncsu.edu/extension-gardener-handbook/19-landscape-design>
  - 'Key design factors to consider in plant selection include plant growth habit, mature size, bloom cycle, and seasonal interest.'

### 11.2 `drawing.bloom_month_state`

For the selected month, mark each plant as in bloom or not with a shape or pattern change, not colour alone.

- Value: `"per-month bloom flag"`
- Critical: no

**Where the sources disagree.** This is an application behaviour inferred from the bloom-calendar and colour rules. No drawing standard describes a month slider, so it is not critical.

Sources:

- Tier 2, partial: Hansen, G. Landscape Design: Drawing a Planting Plan. ENH1195/EP456. University of Florida IFAS Extension, EDIS. <https://edis.ifas.ufl.edu/publication/EP456>
  - Step 2: 'Additional information can include the mature height and spread, seasonal changes, and the bloom period.'
- Tier 2, partial: W3C. 2023. Web Content Accessibility Guidelines (WCAG) 2.2. W3C Recommendation. SC 1.4.1, 1.4.3, 1.4.11, 2.5.5, 2.5.8. <https://www.w3.org/TR/WCAG22/>
  - SC 1.4.1: colour is not 'the only visual means of conveying information'.
