# How to design a wildlife garden with native plants

This document holds the rules for a garden that feeds pollinators, caterpillars, birds and toads, with native plants first. The regional values are for Central Texas. Another region adds its own value under its own key.

`lib.design` and `lib.scheme` read the numbers from `practice/rules.json`. Do not copy a number from this document into code. Read it with `practice.rule(key)` or `practice.regional(key, region)`.

A source is tier 1 when it is peer-reviewed. A source is tier 2 when it is an extension service, a government agency, a conservation body, or a textbook by an established author. A tier 3 source cannot back a rule. A rule marked critical has two or more independent tier 1 or tier 2 sources.

## 1. Native plants and food webs

### 1.1 `wildlife.native_first`

Choose a native plant before a non-native plant for the same role. Native plants support more caterpillars, and caterpillars feed birds.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Berthon et al. 2021 say "the resources a plant provides are more important than its origin". Follow native-first, and use resource value as the tie-breaker (see wildlife.nectar_or_host_wins).

Sources:

- Tier 1, supported: Tallamy DW, Shropshire KJ. 2009. Ranking lepidopteran use of native versus introduced plants. Conservation Biology 23(4):941-947. <https://doi.org/10.1111/j.1523-1739.2009.01202.x>
  - Abstract: "native plants supported more species than introduced plants, and native woody plants with ornamental value supported more Lepidoptera species than introduced woody ornamentals."
- Tier 1, supported: Burghardt KT, Tallamy DW, Shriver WG. 2009. Impact of native plants on bird and butterfly biodiversity in suburban landscapes. Conservation Biology 23(1):219-224. <https://doi.org/10.1111/j.1523-1739.2008.01076.x>
  - Abstract: "Native properties supported significantly more caterpillars and caterpillar species and significantly greater bird abundance, diversity, species richness, biomass, and breeding pairs of native species."
- Tier 1, supported: Richard M, Tallamy DW, Mitchell AB. 2019. Introduced plants reduce species interactions. Biological Invasions 21:983-992. <https://doi.org/10.1007/s10530-018-1876-z>
  - Abstract: "novel hedgerows had 68% fewer caterpillar species, 91% fewer caterpillars, and 96% less caterpillar biomass than native hedgerows."
- Tier 1, supported: Narango DL, Tallamy DW, Marra PP. 2017. Native plants improve breeding and foraging habitat for an insectivorous bird. Biological Conservation 213:42-50. <https://doi.org/10.1016/j.biocon.2017.06.029>
  - Abstract: "Native plants were more likely to host a higher biomass of caterpillars compared to non-native plants."
- Tier 1, supported: Berthon K, Thomas F, Bekessy S. 2021. The role of 'nativeness' in urban greening to support animal biodiversity. Landscape and Urban Planning 205:103959. (Systematic review.) <https://doi.org/10.1016/j.landurbplan.2020.103959>
  - Abstract (systematic review): "most studies show a positive influence of native plants on at least one measure of biodiversity, justifying their priority in urban plantings to support native animals."

### 1.2 `wildlife.native_share`

Make at least 70 percent of the planting native. The study measured plant biomass, so the check must weight by plant size, not by species count.

- Value: `0.7` ratio
- Critical: no

**Where the sources disagree.** Only Narango et al. 2018 gives the 70 percent figure; the other sources support a native-dominated planting without a number. The 70 percent is a floor: the same paper reports mean population growth was sustainable only at <6% nonnative biomass, and the CIs overlapped replacement at <30%. It is one bird species in the mid-Atlantic. Recommend 0.7 as the minimum that the check enforces, and report a higher share as better.

Sources:

- Tier 1, supported: Narango DL, Tallamy DW, Marra PP. 2018. Nonnative plants reduce population growth of an insectivorous bird. Proceedings of the National Academy of Sciences 115(45):11549-11554. <https://pmc.ncbi.nlm.nih.gov/articles/PMC6233133/>
  - Abstract: "unsustainable population growth in these yards compared with those with >70% native plant biomass." Significance: "populations could only be sustained if nonnative plants constituted <30% of plant biomass."
- Tier 1, partial: Narango DL, Tallamy DW, Marra PP. 2017. Native plants improve breeding and foraging habitat for an insectivorous bird. Biological Conservation 213:42-50. <https://doi.org/10.1016/j.biocon.2017.06.029>
  - Abstract: "chickadees were less likely to breed in yards as the dominance of non-native plants increased."
- Tier 1, partial: Burghardt KT, Tallamy DW, Shriver WG. 2009. Impact of native plants on bird and butterfly biodiversity in suburban landscapes. Conservation Biology 23(1):219-224. <https://doi.org/10.1111/j.1523-1739.2008.01076.x>
  - Paired all-native versus conventional yards: native yards had more caterpillars and birds (abstract).

### 1.3 `wildlife.native_share_basis`

Calculate the native share from mature plant size, such as canopy area. Do not calculate it from the number of species.

- Value: `"mature_canopy_area"`
- Critical: no

**Where the sources disagree.** Single source for the unit of measure. Canopy area is the software's proxy for biomass; no source validates that proxy.

Sources:

- Tier 1, supported: Narango DL, Tallamy DW, Marra PP. 2018. Nonnative plants reduce population growth of an insectivorous bird. Proceedings of the National Academy of Sciences 115(45):11549-11554. <https://pmc.ncbi.nlm.nih.gov/articles/PMC6233133/>
  - The threshold is stated as "% native plant biomass" (abstract; Fig. 3 legend: "Yards with plant communities >30% nonnative plants are functioning as population sinks").

## 2. Keystone plants

### 2.1 `wildlife.keystone_first`

Include keystone genera first. A few plant genera host most caterpillar species, so a planting without them supports far fewer.

- Value: `true`
- Critical: no

Sources:

- Tier 1, supported: Narango DL, Tallamy DW, Shropshire KJ. 2020. Few keystone plant genera support the majority of Lepidoptera species. Nature Communications 11:5751. <https://www.nature.com/articles/s41467-020-19565-4>
  - Results: "just 14% of the local plant genera support more than 90% of Lepidoptera diversity." Discussion: "Landscapes that do not include keystone genera may produce on average half the number of species of Lepidoptera."
- Tier 2, supported: National Wildlife Federation. Keystone Native Plants: Great Plains - Ecoregion 9. Caterpillar data from D. Tallamy (University of Delaware); bee data from J. Fowler. <https://nwf.org/-/media/Documents/PDFs/Garden-for-Wildlife/Keystone-Plants/NWF-GFW-keystone-plant-list-ecoregion-9-great-plains.pdf>
  - Page 1: "Without keystone plants in the landscape, butterflies, native bees, and birds will not thrive." Keystone host plants "feed the young caterpillars of approximately 90% of butterflies and moths."
- Tier 1, partial: Tallamy DW, Shropshire KJ. 2009. Ranking lepidopteran use of native versus introduced plants. Conservation Biology 23(4):941-947. <https://doi.org/10.1111/j.1523-1739.2009.01202.x>
  - Abstract: ranks 1385 plant genera "by their ability to support Lepidoptera richness" so users can select "plants with the greatest capacity for supporting biodiversity."

### 2.2 `wildlife.keystone_genera_central_texas`

Use these keystone genera for Central Texas. Confirm a species that is native to Central Texas for each genus before the software accepts it.

- Value: `{"herbaceous_confirmed": ["Solidago", "Helianthus", "Symphyotrichum", "Verbesina", "Rudbeckia", "Gaillardia", "Ratibida", "Dalea", "Vernonia", "Heterotheca"], "herbaceous_ecoregion_list_unconfirmed": ["Grindelia", "Gutierrezia", "Coreopsis", "Erigeron", "Cirsium", "Machaeranthera", "Senecio", "Bidens", "Isocoma", "Baccharis", "Astragalus", "Chrysopsis", "Heliomeris", "Heliopsis", "Oenothera", "Helenium"], "woody_confirmed": ["Quercus", "Prunus"], "woody_ecoregion_list_unconfirmed": ["Salix", "Populus", "Carya", "Acer", "Ulmus", "Crataegus", "Juglans", "Rubus", "Vitis", "Rosa", "Cornus", "Fraxinus", "Amelanchier", "Corylus"], "excluded_from_ecoregion_list": ["Betula", "Alnus", "Malus", "Vaccinium", "Pinus", "Larix", "Castanea", "Tsuga", "Tilia", "Abies", "Picea", "Pseudotsuga", "Chrysothamnus", "Ericameria", "Baileya"], "species_named_in_sources": {"Prunus": ["P. mexicana", "P. serotina var. eximia", "P. angustifolia"], "Solidago": ["S. altissima", "S. gigantea", "S. speciosa"], "Helianthus": ["H. maximiliani"], "Symphyotrichum": ["S. oblongifolium"], "Verbesina": ["V. virginica (frostweed)"], "Quercus": ["Q. stellata (post oak)"], "Gaillardia": ["G. pulchella"], "Ratibida": ["R. columnifera"], "Dalea": ["D. candida", "D. frutescens"], "Vernonia": ["V. baldwinii"], "Rudbeckia": ["R. hirta"], "Heterotheca": ["H. subaxillaris (camphorweed)"], "Gutierrezia": ["G. texana (Texas broomweed)"]}}`
- Critical: yes

**Where the sources disagree.** The NWF list covers the whole Great Plains ecoregion, not Central Texas. 'Confirmed' means an opened Texas or Southern Plains source names a species. 'Unconfirmed' genera need a Central Texas species check, for example in the Wildflower Center plant database. The 'excluded' genera had no Central Texas species in any opened source; this exclusion is a judgement, not a sourced fact.

Sources:

- Tier 2, supported: National Wildlife Federation. Keystone Native Plants: Great Plains - Ecoregion 9. Caterpillar data from D. Tallamy (University of Delaware); bee data from J. Fowler. <https://nwf.org/-/media/Documents/PDFs/Garden-for-Wildlife/Keystone-Plants/NWF-GFW-keystone-plant-list-ecoregion-9-great-plains.pdf>
  - Great Plains Ecoregion 9 top genera: Quercus 253 caterpillar species, Prunus 222, Salix 214 ... Solidago 71, Helianthus 58; bee keystones include Helianthus 89, Solidago 56, Symphyotrichum 43, Verbesina 34, Rudbeckia 32, Gaillardia 18, Ratibida 14, Dalea 12, Vernonia 12.
- Tier 1, partial: Narango DL, Tallamy DW, Shropshire KJ. 2020. Few keystone plant genera support the majority of Lepidoptera species. Nature Communications 11:5751. <https://www.nature.com/articles/s41467-020-19565-4>
  - Results: "The top 5 genera were Quercus ... Salix ... Prunus ... Pinus ... and Populus"; "Plant identities critical for retaining interaction diversity are similar and independent of geography."
- Tier 2, supported: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - Southern Plains list names Helianthus maximiliani, Solidago gigantea, S. speciosa, Symphyotrichum oblongifolium, Gaillardia pulchella, Ratibida columnifera, Dalea candida, Vernonia baldwinii, Prunus angustifolia.
- Tier 2, supported: Texas A&M AgriLife Extension, Travis County. Butterfly Plants for Austin (guide by Travis County Master Gardener D. Jeffers). <https://travis-tx.tamu.edu/about-2/horticulture/ornamental-plants/annual-and-perennial-flowers-for-austin/butterfly-gardening/butterfly-plants-for-austin/>
  - Austin list names Prunus mexicana, Prunus serotina var. eximia (host for tiger swallowtails and others), Solidago altissima.
- Tier 2, partial: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - Fall nectar list for Texas includes "Frostweed", "Fall aster", "Maximilian sunflower", "Goldenrod varieties".

### 2.3 `wildlife.woody_keystone_preferred`

Where a woody keystone plant fits the space, prefer it to a herbaceous plant. Woody plants host more caterpillar species.

- Value: `true`
- Critical: no

**Where the sources disagree.** Narango et al. 2020 also found herbaceous keystones essential: "comparable richness and interactions were not reached even with a 3-fold increase in plant genera richness." In a 4 ft border, woody plants rarely fit; use herbaceous keystones there and put woody keystones elsewhere in the yard.

Sources:

- Tier 1, supported: Tallamy DW, Shropshire KJ. 2009. Ranking lepidopteran use of native versus introduced plants. Conservation Biology 23(4):941-947. <https://doi.org/10.1111/j.1523-1739.2009.01202.x>
  - Abstract: "Woody plants supported more species of moths and butterflies than herbaceous plants."
- Tier 1, partial: Narango DL, Tallamy DW, Shropshire KJ. 2020. Few keystone plant genera support the majority of Lepidoptera species. Nature Communications 11:5751. <https://www.nature.com/articles/s41467-020-19565-4>
  - Fig. 3 legend: "In woody plants, more than twice the number of plant genera was required to achieve the species and interactions produced by keystone plants."

## 3. Plant selection tie-break

### 3.1 `wildlife.nectar_or_host_wins`

When two plants both fit a position, choose the one that gives nectar or hosts caterpillars. A plant that does both ranks highest.

- Value: `true`
- Critical: yes

Sources:

- Tier 1, partial: Berthon K, Thomas F, Bekessy S. 2021. The role of 'nativeness' in urban greening to support animal biodiversity. Landscape and Urban Planning 205:103959. (Systematic review.) <https://doi.org/10.1016/j.landurbplan.2020.103959>
  - Abstract: "the resources a plant provides are more important than its origin".
- Tier 1, partial: Narango DL, Tallamy DW, Shropshire KJ. 2020. Few keystone plant genera support the majority of Lepidoptera species. Nature Communications 11:5751. <https://www.nature.com/articles/s41467-020-19565-4>
  - Discussion: "native plants, even within biomes, are not all equivalent in terms of their contributions of energy to food webs."
- Tier 2, partial: Lady Bird Johnson Wildflower Center, University of Texas at Austin. Make a Butterfly Garden. <https://www.wildflower.org/learn/how-to/make-a-butterfly-garden>
  - Blueprints: "Ensure that both diverse adult nectar plants and a variety of caterpillar host plants will be present in your garden."

## 4. Larval host plants

### 4.1 `wildlife.min_hosts_per_bed`

Put at least one caterpillar host plant in every wildlife bed. Nectar alone feeds adults but does not let butterflies breed.

- Value: `1` count
- Critical: yes

**Where the sources disagree.** No source gives a count per bed. The value 1 is the smallest number that meets 'include host plants'. LBJWC asks for 'a variety', so report more than one as better.

Sources:

- Tier 2, supported: Lady Bird Johnson Wildflower Center, University of Texas at Austin. Make a Butterfly Garden. <https://www.wildflower.org/learn/how-to/make-a-butterfly-garden>
  - "nectar plants for adult butterflies are entirely different than the host plants sought by larva for food"; "Ensure that both diverse adult nectar plants and a variety of caterpillar host plants will be present."
- Tier 2, supported: Texas A&M AgriLife Extension, Travis County. Butterfly Plants for Austin (guide by Travis County Master Gardener D. Jeffers). <https://travis-tx.tamu.edu/about-2/horticulture/ornamental-plants/annual-and-perennial-flowers-for-austin/butterfly-gardening/butterfly-plants-for-austin/>
  - "Nectar and larval (caterpillar) food are both important considerations to selecting butterfly plants for your garden."
- Tier 2, partial: USDA Natural Resources Conservation Service. 2024. Monarch Butterfly Wildlife Habitat Evaluation Guide and Decision Support Tool: Southern High Plains Region (plant guide and Monarch Planting List). <https://www.nrcs.usda.gov/sites/default/files/2024-11/NRCS_Southern%20Plains%20Plant%20Guide_1024.pdf>
  - National minimum criteria: "plantings should include at least one species of milkweed (Asclepias spp.)".
- Tier 2, partial: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - Principle 2: "Protect and provide bee nest sites and caterpillar host plants".

## 5. Nectar continuity

### 5.1 `wildlife.nectar_species_per_season`

Have at least three different species in bloom in each of spring, summer and fall.

- Value: `3` count
- Critical: yes

Sources:

- Tier 2, supported: Xerces Society. 2017. Pollinator Habitat Installation Plan. Publication 17-002. <https://www.xerces.org/sites/default/files/2018-06/17-002_01_XercesSoc_Pollinator-Habitat-Installation-Plan_web.pdf>
  - "at least three species from each blooming period (early, mid, and late season), should be included."
- Tier 2, supported: Xerces Society. 2025. Small Habitat Plantings in Urban Areas. Publication 25-006. <https://www.xerces.org/sites/default/files/publications/25-006_01_Small%20Habitat%20Plantings%20in%20Urban%20Areas_print.pdf>
  - "Select at least three blooming plant species per season to provide continuous food and resources."
- Tier 2, supported: USDA Natural Resources Conservation Service. 2024. Monarch Butterfly Wildlife Habitat Evaluation Guide and Decision Support Tool: Southern High Plains Region (plant guide and Monarch Planting List). <https://www.nrcs.usda.gov/sites/default/files/2024-11/NRCS_Southern%20Plains%20Plant%20Guide_1024.pdf>
  - "Planners should choose a minimum of three plants in each of three different blooming periods (early, mid, and late)."
- Tier 1, partial: Blaauw BR, Isaacs R. 2014. Flower plantings increase wild bee abundance and the pollination services provided to a pollination-dependent crop. Journal of Applied Ecology 51:890-898. <https://doi.org/10.1111/1365-2664.12257>
  - Abstract: plantings "seeded ... with a mix of 15 perennial wildflower species that provided season-long bloom" increased wild bee and syrphid abundance annually.

### 5.2 `wildlife.min_nectar_species_total`

Plant at least nine nectar species in total, three for each of the three seasons. One long-blooming species can count in two seasons.

- Value: `9` count
- Critical: yes

**Where the sources disagree.** Nine is 3 x 3 and assumes each species blooms in one season. Neither source says whether one species can count in two periods. Recommend the software count a species in every season that its bloom months cover, and still require 3 per season.

Sources:

- Tier 2, partial: USDA Natural Resources Conservation Service. 2024. Monarch Butterfly Wildlife Habitat Evaluation Guide and Decision Support Tool: Southern High Plains Region (plant guide and Monarch Planting List). <https://www.nrcs.usda.gov/sites/default/files/2024-11/NRCS_Southern%20Plains%20Plant%20Guide_1024.pdf>
  - "a minimum of three plants in each of three different blooming periods (early, mid, and late)."
- Tier 2, partial: Xerces Society. 2017. Pollinator Habitat Installation Plan. Publication 17-002. <https://www.xerces.org/sites/default/files/2018-06/17-002_01_XercesSoc_Pollinator-Habitat-Installation-Plan_web.pdf>
  - "at least three species from each blooming period (early, mid, and late season)".

## 6. Nectar season in Central Texas

### 6.1 `wildlife.nectar_months_central_texas`

Treat March to November as the nectar season in Central Texas. Winter bloom from December to February is optional.

- Value: `["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]` months
- Critical: yes

**Where the sources disagree.** The Travis County guide also lists winter nectar plants (Dec-Feb). Recommend the check require bloom March to November and give credit for winter bloom without requiring it.

Sources:

- Tier 2, supported: Texas A&M AgriLife Extension, Travis County. Butterfly Plants for Austin (guide by Travis County Master Gardener D. Jeffers). <https://travis-tx.tamu.edu/about-2/horticulture/ornamental-plants/annual-and-perennial-flowers-for-austin/butterfly-gardening/butterfly-plants-for-austin/>
  - Austin tables: "Spring Blooming Plants: March - May"; "Summer through Fall Blooming Plants: June - November"; "Winter Blooming Plants: December - February".
- Tier 2, partial: Texas Parks and Wildlife Department. 2016. Texas Monarch and Native Pollinator Conservation Plan. PWD RP W7000-2070. <https://tpwd.texas.gov/publications/pwdpubs/media/pwd_rp_w7000_2070.pdf>
  - NRCS addendum: "high quality nectar during critical migration time periods (March 1 to Mid-April and Mid-September to November)."

### 6.2 `wildlife.seasons`

Map spring to March-May, summer to June-August and fall to September-November for the per-season check.

- Value: `{"spring": ["Mar", "Apr", "May"], "summer": ["Jun", "Jul", "Aug"], "fall": ["Sep", "Oct", "Nov"]}` months
- Critical: yes

**Where the sources disagree.** The Travis County guide joins summer and fall (June-November). The split at September is derived from the TPWD fall-migration window, not stated by one source. Recommend the split, because it forces fall bloom for the October monarch peak.

Sources:

- Tier 2, partial: Texas A&M AgriLife Extension, Travis County. Butterfly Plants for Austin (guide by Travis County Master Gardener D. Jeffers). <https://travis-tx.tamu.edu/about-2/horticulture/ornamental-plants/annual-and-perennial-flowers-for-austin/butterfly-gardening/butterfly-plants-for-austin/>
  - "Spring Blooming Plants: March - May"; "Summer through Fall Blooming Plants: June - November".
- Tier 2, partial: Texas Parks and Wildlife Department. 2016. Texas Monarch and Native Pollinator Conservation Plan. PWD RP W7000-2070. <https://tpwd.texas.gov/publications/pwdpubs/media/pwd_rp_w7000_2070.pdf>
  - Fall migration nectar window "Mid-September to November"; spring window "March 1 to Mid-April".
- Tier 2, partial: Xerces Society. 2017. Pollinator Habitat Installation Plan. Publication 17-002. <https://www.xerces.org/sites/default/files/2018-06/17-002_01_XercesSoc_Pollinator-Habitat-Installation-Plan_web.pdf>
  - Bloom key: "Early (spring), Mid (summer), Late (late summer/fall)".

## 7. Monarch migration

### 7.1 `wildlife.monarch_peak_central_texas`

Treat October as the fall monarch peak in Austin. The migration window runs from late September to November.

- Value: `{"peak": ["Oct"], "window": ["Sep", "Oct", "Nov"]}` months
- Critical: yes

Sources:

- Tier 2, supported: Taylor OR. 2003. Midpoints and peaks of the migration by latitude. Monarch Watch Update, 21 August 2003. Monarch Watch, University of Kansas. <https://monarchwatch.org/update/2003/0821.html>
  - Table: "31 degrees / 12 October / 4-16 October"; "29 degrees / 18 October / 10-22 October". Austin is about 30.3 degrees N, between these rows.
- Tier 2, supported: Texas Parks and Wildlife Department. Mysterious Monarchs: Background for Teachers (from TPW Magazine, October 2009). <https://tpwd.texas.gov/education/resources/keep-texas-wild/mysterious-monarchs/background-for-teachers>
  - "Monarchs enter the Texas portion of this flyway during the last days of September. By the third week of October, most have passed through into Mexico."
- Tier 2, partial: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - W. Brown (AgriLife, Travis County): "They usually start heading south through Texas around September into November."

### 7.2 `wildlife.monarch_spring_central_texas`

Treat March and April as the spring monarch pass. Returning monarchs lay eggs on new milkweed then, so milkweed must be up in March.

- Value: `["Mar", "Apr"]` months
- Critical: yes

Sources:

- Tier 2, supported: Texas Parks and Wildlife Department. 2016. Texas Monarch and Native Pollinator Conservation Plan. PWD RP W7000-2070. <https://tpwd.texas.gov/publications/pwdpubs/media/pwd_rp_w7000_2070.pdf>
  - NRCS addendum: critical migration nectar period "March 1 to Mid-April".
- Tier 2, partial: Texas Parks and Wildlife Department. Mysterious Monarchs: Background for Teachers (from TPW Magazine, October 2009). <https://tpwd.texas.gov/education/resources/keep-texas-wild/mysterious-monarchs/background-for-teachers>
  - "Then they return to Texas and the southern United States to lay eggs on freshly sprouted milkweeds."

### 7.3 `wildlife.fall_nectar_covers_october`

Make sure that fall nectar plants bloom in October. A fall species that finishes in September does not count for the monarch peak.

- Value: `true`
- Critical: yes

Sources:

- Tier 2, partial: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - M. Arnold: "With a little planning, you can ensure the flowers are in peak bloom during monarch migration."
- Tier 2, supported: Texas Parks and Wildlife Department. 2016. Texas Monarch and Native Pollinator Conservation Plan. PWD RP W7000-2070. <https://tpwd.texas.gov/publications/pwdpubs/media/pwd_rp_w7000_2070.pdf>
  - "high quality nectar during critical migration time periods (... Mid-September to November)".
- Tier 2, partial: Texas Parks and Wildlife Department. Mysterious Monarchs: Background for Teachers (from TPW Magazine, October 2009). <https://tpwd.texas.gov/education/resources/keep-texas-wild/mysterious-monarchs/background-for-teachers>
  - "Monarchs enter Texas in the fall weighing 400 milligrams but leave weighing 650 milligrams", stored as fat from nectar.

### 7.4 `wildlife.monarch_fall_nectar_central_texas`

Prefer these native fall nectar plants for the October migration in Central Texas.

- Value: `["Conoclinium greggii (Gregg's mistflower)", "Verbesina virginica (frostweed)", "Symphyotrichum oblongifolium (aromatic or fall aster)", "Helianthus maximiliani (Maximilian sunflower)", "Liatris spp. (blazing star)", "Solidago spp. (goldenrod)", "Anisacanthus wrightii (flame acanthus)", "Cephalanthus occidentalis (buttonbush, wet soil only)"]`
- Critical: yes

Sources:

- Tier 2, supported: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - List: "Gregg's mistflower. Frostweed. Fall aster. Maximilian sunflower. Blazing star varieties. Goldenrod varieties. Flame acanthus. Buttonbush."
- Tier 2, partial: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - Late bloomers: Aromatic aster, Giant goldenrod, Maximilian sunflower, Showy goldenrod; Buttonbush "Prefers wet or moist soil"; Liatris punctata "attracts ... monarchs".
- Tier 2, partial: Texas A&M AgriLife Extension, Travis County. Butterfly Plants for Austin (guide by Travis County Master Gardener D. Jeffers). <https://travis-tx.tamu.edu/about-2/horticulture/ornamental-plants/annual-and-perennial-flowers-for-austin/butterfly-gardening/butterfly-plants-for-austin/>
  - June-November list: Gregg's Mistflower, Flame Acanthus, Goldenrod ("All, especially Monarch").

## 8. Milkweed

### 8.1 `wildlife.native_milkweed_only`

Plant only milkweed native to the region. Never plant tropical milkweed, Asclepias curassavica, in Central Texas.

- Value: `{"allow": "native Asclepias only", "avoid": ["Asclepias curassavica"]}`
- Critical: yes

**Where the sources disagree.** AgriLife Today (2024) reports that The Gardens at Texas A&M grow tropical milkweed and prune it to the ground before fall. MJV accepts pruning as a fix for existing plants only. The owner forbids anything that harms butterflies, so follow MJV and NRCS: never plant it.

Sources:

- Tier 1, supported: Satterfield DA, Maerz JC, Altizer S. 2015. Loss of migratory behaviour increases infection risk for a butterfly host. Proceedings of the Royal Society B 282:20141734. <https://pmc.ncbi.nlm.nih.gov/articles/PMC4308991/>
  - Abstract: "some monarchs have become non-migratory and breed year-round on exotic milkweed in the southern US ... Infection prevalence was markedly higher among sedentary monarchs."
- Tier 1, supported: Satterfield DA, Villablanca FX, Maerz JC, Altizer S. 2016. Migratory monarchs wintering in California experience low infection risk compared to monarchs breeding year-round on non-native milkweed. Integrative and Comparative Biology 56(2):343-352. <https://doi.org/10.1093/icb/icw030>
  - Abstract: "infection frequency was over nine times higher for monarchs sampled in gardens with year-round milkweed"; south-central US year-round breeders "face extremely high risk of infection."
- Tier 1, partial: Faldyn MJ, Hunter MD, Elderd BD. 2018. Climate change and an invasive, tropical milkweed: an ecological trap for monarch butterflies. Ecology 99(5):1031-1038. <https://doi.org/10.1002/ecy.2198>
  - Abstract: under warmer conditions "monarchs fared much worse on A. curassavica"; it "may have pushed the larvae over a tipping point into an ecological trap."
- Tier 2, supported: Monarch Joint Venture. Tropical Milkweed and OE: Potential Risks for Monarchs (handout). <https://mjv.nyc3.cdn.digitaloceanspaces.com/documents/Tropical-Milkweed-and-OE-Potential-Risks-for-Monarchs.pdf>
  - "Only plant milkweed native to your region." "Monarchs that encounter these plants during migration may become reproductive and forego migration."
- Tier 2, supported: USDA Natural Resources Conservation Service. 2024. Monarch Butterfly Wildlife Habitat Evaluation Guide and Decision Support Tool: Southern High Plains Region (plant guide and Monarch Planting List). <https://www.nrcs.usda.gov/sites/default/files/2024-11/NRCS_Southern%20Plains%20Plant%20Guide_1024.pdf>
  - "Regardless, NRCS does not support the use of nonnative milkweeds for monarch habitat plantings."

### 8.2 `wildlife.native_milkweeds_central_texas`

Use a native milkweed such as antelope horns, zizotes or butterfly milkweed. Use swamp milkweed only in wet soil.

- Value: `["Asclepias asperula (antelope horns)", "Asclepias oenotheroides (zizotes)", "Asclepias tuberosa (butterfly milkweed)", "Asclepias incarnata (swamp milkweed, wet soil only)"]`
- Critical: no

**Where the sources disagree.** Both sources cover the Southern Plains, not Central Texas specifically. TPWD (2016) says Texas has 37 native milkweed species. Confirm each species for Austin and for alkaline clay before the software accepts it.

Sources:

- Tier 2, supported: USDA Natural Resources Conservation Service. 2024. Monarch Butterfly Wildlife Habitat Evaluation Guide and Decision Support Tool: Southern High Plains Region (plant guide and Monarch Planting List). <https://www.nrcs.usda.gov/sites/default/files/2024-11/NRCS_Southern%20Plains%20Plant%20Guide_1024.pdf>
  - Southern High Plains plant guide contents: Antelope Horn (Asclepias asperula), Butterfly Milkweed (A. tuberosa), Swamp Milkweed (A. incarnata), Zizotes Milkweed (A. oenotheroides). Also: "gravid females do not utilize butterfly milkweed (Asclepias tuberosa) as often as common milkweed."
- Tier 2, partial: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - "Antelope horns milkweed Asclepias asperula ssp. capricornu ... host plants for monarch, queen, and soldier".

### 8.3 `wildlife.tropical_milkweed_cutback`

If tropical milkweed already grows on site, cut it to about 6 inches before fall migration. Cut it again as it resprouts through February. Replace it with natives.

- Value: `{"cut_to_in": 0, "first_cut_by": "mid-September", "months": ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb"]}`
- Critical: no

**Where the sources disagree.** The 6 inch height and October-February months come from an MJV fact sheet seen only in search results; the MJV handout that was opened says 'before the fall migration' and 'through February'. AgriLife cuts to the ground. Either height meets the goal.

Sources:

- Tier 2, partial: Monarch Joint Venture. Tropical Milkweed and OE: Potential Risks for Monarchs (handout). <https://mjv.nyc3.cdn.digitaloceanspaces.com/documents/Tropical-Milkweed-and-OE-Potential-Risks-for-Monarchs.pdf>
  - "prune the milkweed stalks before the fall migration ... Re-cut the milkweed every few weeks through February as leaves re-sprout. When possible, remove and replace tropical milkweed plants with native species."
- Tier 2, partial: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - M. Arnold: "we prune our tropical milkweed all the way to the ground as we approach fall."
- Tier 2, partial: USDA Natural Resources Conservation Service. 2024. Monarch Butterfly Wildlife Habitat Evaluation Guide and Decision Support Tool: Southern High Plains Region (plant guide and Monarch Planting List). <https://www.nrcs.usda.gov/sites/default/files/2024-11/NRCS_Southern%20Plains%20Plant%20Guide_1024.pdf>
  - Tropical milkweed concerns "primarily target lands adjacent to the Gulf of Mexico where tropical milkweed does not dieback in the winter."

## 9. Planting in patches

### 9.1 `wildlife.patch_min_ft`

Plant each nectar species as a clump about 3 feet across. Use 3 to 6 plants of the same species for each clump.

- Value: `{"min_width_ft": 3, "min_plants": 3, "typical_plants": [3, 6]}`
- Critical: no

**Where the sources disagree.** Clumping has several sources. The 3 ft number has only one opened Tier 2 source, a UC Master Gardener newsletter; the Xerces sources say 'within a few feet' and give a plant count instead. So this is critical:false. In a 4 ft deep border a 3 ft clump fills most of the depth; recommend the software enforce min_plants 3 and treat 3 ft as a target.

Sources:

- Tier 2, supported: Beltramo P. 2017. Planting to Attract Pollinators. Curious Gardener 24(4), University of California Cooperative Extension and UC Master Gardeners of Placer and Nevada Counties. <https://ucanr.edu/sites/default/files/2025-09/Fall%202017%20CG%20final.pdf>
  - "plant several plants of the same type to create a swath of flowers at least three feet by three feet."
- Tier 2, supported: Xerces Society. 2023. Creating Perennial Habitat for Pollinators and Beneficial Insects Using Plugs. Publication 23-028. <https://www.xerces.org/sites/default/files/publications/23-028_01_Creating-Perennial-Habitat-Using-Plugs-FS_web.pdf>
  - "Plant the same species in groups of 3-6 plugs to improve garden aesthetics and create the larger bloom displays"; plugs "12-36\" apart (center-to-center)."
- Tier 2, partial: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - "Flowers clustered into clumps of one species will attract more pollinators than individual plants scattered through a habitat patch."
- Tier 1, partial: Plascencia M, Philpott SM. 2017. Floral abundance, richness, and spatial distribution drive urban garden bee communities. Bulletin of Entomological Research 107:658-667. <https://doi.org/10.1017/S0007485317000153>
  - Abstract: "bee species richness and bee diversity was higher in sites with more clustered floral resources."

### 9.2 `wildlife.plant_diversity`

Use several plant families and genera, with different flower shapes and heights. Diverse flower patches hold more pollinator species.

- Value: `null`
- Critical: no

**Where the sources disagree.** No source gives a minimum number of families for a small bed. Leave the value null until a source gives one.

Sources:

- Tier 2, supported: Xerces Society. 2025. Small Habitat Plantings in Urban Areas. Publication 25-006. <https://www.xerces.org/sites/default/files/publications/25-006_01_Small%20Habitat%20Plantings%20in%20Urban%20Areas_print.pdf>
  - "Select multiple plant families and genera, with differing bloom colors, shapes, and heights, to support biodiversity."
- Tier 1, partial: Blaauw BR, Isaacs R. 2014. Larger patches of diverse floral resources increase insect pollinator density, diversity, and their pollination of native wildflowers. Basic and Applied Ecology 15(8):701-711. <https://doi.org/10.1016/j.baae.2014.10.001>
  - Title: larger patches of "diverse floral resources increase insect pollinator density, diversity".

### 9.3 `wildlife.bloom_together`

Place plants that bloom at the same time near each other. Butterflies find them more easily.

- Value: `true`
- Critical: no

**Where the sources disagree.** Single source. It is a layout preference only.

Sources:

- Tier 2, supported: Lady Bird Johnson Wildflower Center, University of Texas at Austin. Make a Butterfly Garden. <https://www.wildflower.org/learn/how-to/make-a-butterfly-garden>
  - "Place plants that bloom simultaneously together (easier to spot plus more visually pleasing)."

### 9.4 `wildlife.sun_for_nectar`

Put butterfly nectar plants in full or near-full sun, with some shelter from wind.

- Value: `true`
- Critical: no

Sources:

- Tier 2, supported: Lady Bird Johnson Wildflower Center, University of Texas at Austin. Make a Butterfly Garden. <https://www.wildflower.org/learn/how-to/make-a-butterfly-garden>
  - "Be mindful to give your visitors plenty of sun, yet also provide protection from wind and rain."
- Tier 2, supported: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - "Most pollinator-friendly plants prefer sites that receive full sun throughout most of the day."

## 10. Habitat structure

### 10.1 `wildlife.leave_stems_and_litter`

Leave leaves and standing stems through winter. Cut stems back only when spring is well underway.

- Value: `{"leave_leaves": true, "leave_stems": true, "do_not_shred_leaves": true, "cut_back_after": "spring well underway"}`
- Critical: no

**Where the sources disagree.** Meets the two-source bar, but it changes maintenance, not what is planted, so critical is false.

Sources:

- Tier 2, supported: Wheeler J, Black SH, Seiler D. 2026. Leave the Leaves! Xerces Society, 17 September 2026. <https://xerces.org/blog/leave-the-leaves>
  - "The vast majority of butterflies and moths don't migrate! Instead, they overwinter in the landscape ... and use leaf litter for winter cover." "Wait until spring is underway to trim stems and clean up." "Avoid shredding leaves."
- Tier 2, supported: Xerces Society. 2025. Small Habitat Plantings in Urban Areas. Publication 25-006. <https://www.xerces.org/sites/default/files/publications/25-006_01_Small%20Habitat%20Plantings%20in%20Urban%20Areas_print.pdf>
  - "Roughly 30% of species nest in tunnels, such as in last year's hollow dead standing plant stems."
- Tier 2, partial: Beltramo P. 2017. Planting to Attract Pollinators. Curious Gardener 24(4), University of California Cooperative Extension and UC Master Gardeners of Placer and Nevada Counties. <https://ucanr.edu/sites/default/files/2025-09/Fall%202017%20CG%20final.pdf>
  - "Pithy stems of plants can be left in the garden to become housing."

### 10.2 `wildlife.bare_ground_for_bees`

Keep some bare, unmulched, undisturbed soil in sun for ground-nesting bees. About 70 percent of bee species nest in the ground.

- Value: `true`
- Critical: yes

**Where the sources disagree.** Critical because the layout must leave ground unplanted and unmulched. No source gives a minimum area for a small bed.

Sources:

- Tier 2, supported: Xerces Society. 2025. Small Habitat Plantings in Urban Areas. Publication 25-006. <https://www.xerces.org/sites/default/files/publications/25-006_01_Small%20Habitat%20Plantings%20in%20Urban%20Areas_print.pdf>
  - "Approximately 70% of species nest in the ground. Limit ground disturbance and provide access to bare soil."
- Tier 2, partial: Wheeler J, Black SH, Seiler D. 2026. Leave the Leaves! Xerces Society, 17 September 2026. <https://xerces.org/blog/leave-the-leaves>
  - "Approximately 70 percent of all bee species nest in the ground ... try to keep any disturbances as limited and shallow as possible."
- Tier 2, supported: Beltramo P. 2017. Planting to Attract Pollinators. Curious Gardener 24(4), University of California Cooperative Extension and UC Master Gardeners of Placer and Nevada Counties. <https://ucanr.edu/sites/default/files/2025-09/Fall%202017%20CG%20final.pdf>
  - "Some native insect pollinators nest in bare soil ... Pull back some mulch to allow the ground nesters to build housing also."
- Tier 1, partial: Harmon-Threatt A. 2020. Influence of nesting characteristics on health of wild bee communities. Annual Review of Entomology 65:39-56. <https://doi.org/10.1146/annurev-ento-011019-024955>
  - Abstract: "Nest site availability and quality are important for maintaining robust populations and communities of wild bees."

## 11. Pesticides

### 11.1 `wildlife.no_pesticide_on_hosts`

Do not use insecticide on or near host or nectar plants. This includes Btk and systemic neonicotinoids.

- Value: `{"no_insecticide": true, "includes": ["Bacillus thuringiensis kurstaki (Btk)", "systemic neonicotinoids"]}`
- Critical: yes

Sources:

- Tier 2, supported: Lady Bird Johnson Wildflower Center, University of Texas at Austin. Make a Butterfly Garden. <https://www.wildflower.org/learn/how-to/make-a-butterfly-garden>
  - "The caterpillar is in greatest peril from insecticides ... if you can avoid chemicals completely, do so."
- Tier 2, supported: Washington State Department of Agriculture. Btk FAQs. <https://agr.wa.gov/departments/insects-pests-and-weeds/insects/invasive-moths/btk/btk-faqs>
  - Btk "is detrimental to the caterpillars of most moth or butterfly species that feed at the time of treatment."
- Tier 1, supported: Knight SM, Flockhart DTT, Derbyshire R, Bosco MG, Norris DR. 2021. Experimental field evidence shows milkweed contaminated with a common neonicotinoid decreases larval survival of monarch butterflies. Journal of Animal Ecology 90:1742-1752. <https://doi.org/10.1111/1365-2656.13492>
  - Abstract: "Larval survival was lower in clothianidin-treated plots compared to control plots."
- Tier 1, partial: Forister ML, Cousens B, Harrison JG, et al. 2016. Increasing neonicotinoid use and the declining butterfly fauna of lowland California. Biology Letters 12:20160475. <https://pmc.ncbi.nlm.nih.gov/articles/PMC5014040/>
  - Abstract: "A negative association between butterfly populations and increasing neonicotinoid application is detectable while controlling for land use."
- Tier 2, supported: Xerces Society. 2017. Pollinator Plants: Southern Plains Region. Publication 17-054. <https://xerces.org/sites/default/files/2018-05/17-054_03_XercesSoc_PollinatorPlants_Southern-Plains-Region_web-4page.pdf>
  - Principle 3: "Avoid using pesticides, especially insecticides".

### 11.2 `wildlife.neonic_free_nursery_stock`

Buy plants that are free of neonicotinoid residues. Ask the nursery before purchase, especially for milkweed.

- Value: `true`
- Critical: yes

**Where the sources disagree.** The Xerces 'Buying Bee-Safe Plants' page was opened, but only its summary was readable ("choose plants free from harmful pesticide residues").

Sources:

- Tier 1, partial: Knight SM, Flockhart DTT, Derbyshire R, Bosco MG, Norris DR. 2021. Experimental field evidence shows milkweed contaminated with a common neonicotinoid decreases larval survival of monarch butterflies. Journal of Animal Ecology 90:1742-1752. <https://doi.org/10.1111/1365-2656.13492>
  - Abstract: "milkweed near clothianidin-treated crops can reduce larval survival of monarch butterflies."
- Tier 2, supported: Monarch Joint Venture. Tropical Milkweed and OE: Potential Risks for Monarchs (handout). <https://mjv.nyc3.cdn.digitaloceanspaces.com/documents/Tropical-Milkweed-and-OE-Potential-Risks-for-Monarchs.pdf>
  - "Create demand for native, pesticide-free milkweeds by asking for them at your local nursery."

## 12. Toads and frogs

### 12.1 `wildlife.toad_habitat`

Give toads a shaded, damp retreat and a shallow water dish sunk at ground level. Use no pesticides anywhere they live.

- Value: `{"water_dish": "shallow saucer about 16 in across, sunk level with the soil, in shade, refilled often", "retreat": "half-buried pot on its side, an upturned pot with no floor, or flat rocks with a toad-sized gap, in the dampest shaded spot, near a downspout or AC drip", "soil": "loose, compost-amended soil that toads can dig into", "pesticides": "none, including herbicides and fungicides", "breeding_pond": "not required in a 4 ft border; no opened Tier 1 or Tier 2 source sets pond rules for the Gulf Coast toad", "species_note": "Gulf Coast toad (Incilius nebulifer) breeding details are not verified in a Tier 1 or Tier 2 source"}`
- Critical: no

**Where the sources disagree.** Critical is false because this places features, not plants. Gulf Coast toad specifics (rain-triggered breeding March-September in temporary pools, 20-30 days to metamorphosis) appear only in Tier 3 sources found during the search. Do not build rules on those numbers until a Tier 1 or Tier 2 source confirms them.

Sources:

- Tier 2, supported: Berger C. 2006. How to Dote on Toads. National Wildlife, National Wildlife Federation, 1 August 2006. <https://www.nwf.org/Magazines/National-Wildlife/2006/Backyard-Houses-for-Toads>
  - "Toads do need a ready source of water ... we use a 16-inch terra-cotta saucer ... Choose a shady location, nestle the container in the dirt"; abode "in the dampest spot in your yard, near a gutter downspout, air-conditioner drip"; "don't buy a toad abode with a floor"; "Pesticides and lawn chemicals are deadly to toads."
- Tier 1, partial: Bruhl CA, Schmidt T, Pieper S, Alscher A. 2013. Terrestrial pesticide exposure of amphibians: an underestimated cause of global decline? Scientific Reports 3:1135. <https://pmc.ncbi.nlm.nih.gov/articles/PMC3553602/>
  - Abstract: juvenile frog "Mortality ranged from 100% after one hour to 40% after seven days at the recommended label rate of currently registered products."

### 12.2 `wildlife.mosquito_safe_water`

Empty and refill every small water dish at least every 5 days. Mosquitoes breed in water that stands for about a week.

- Value: `{"max_days_standing": 5}`
- Critical: no

**Where the sources disagree.** Toad breeding needs water that lasts for weeks, which conflicts with this rule. AgriLife (Swiger) tells owners to stock ponds with fish against mosquitoes; fish-free ponds for amphibians appear only in sources seen in search, not opened. Recommend a soaking dish only, refreshed within 5 days, and no breeding pond in a small bed.

Sources:

- Tier 2, supported: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - W. Brown: "In order to avoid mosquitoes, you want something that will dry out every three to five days, but that also means you will need to refill with clean water."
- Tier 2, partial: Texas A&M AgriLife Extension. DIY - Do It Yourself Backyard Mosquito Control. <https://agrilifeextension.tamu.edu/wp-content/uploads/2025/07/Mosquitoes-Backyard-Mosquito-Control-1.pdf>
  - "Mosquitoes breed in standing water, especially if it stands for at least 7 days."
- Tier 2, partial: Texas A&M AgriLife Extension. 2008. Mosquito Control Around the Home. Publication E-333. <https://agrilifeextension.tamu.edu/wp-content/uploads/2025/06/Mosquito-Control-Around-The-Home-1.pdf>
  - "Drain water from flower pots, bird baths ... pet dishes ... at least once a week."
- Tier 2, partial: Swiger SL. Mosquitoes and the Diseases They Transmit. Texas A&M AgriLife Extension Service. <https://agrilifeextension.tamu.edu/wp-content/uploads/2025/07/mosquitos-and-the-diseases-they-transmit-1.pdf>
  - Table: "Bird baths Change the water at least once a week." "Ponds Stock the pond with fish."

## 13. Cool-season annuals

### 13.1 `wildlife.annuals_as_makeup`

Allow non-native annuals only as seasonal color. They count against the native share and must be neonicotinoid-free and non-invasive.

- Value: `{"allowed": true, "counts_as_non_native": true, "max_share": 0.3}`
- Critical: yes

**Where the sources disagree.** The max_share of 0.3 is derived from wildlife.native_share, not stated by these sources. The Travis County guide says adult butterflies 'aren't particular whether it be native or not' for nectar. Nectar value does not replace host value, so keep annuals inside the non-native 30 percent.

Sources:

- Tier 2, partial: Xerces Society. 2025. Small Habitat Plantings in Urban Areas. Publication 25-006. <https://www.xerces.org/sites/default/files/publications/25-006_01_Small%20Habitat%20Plantings%20in%20Urban%20Areas_print.pdf>
  - "Flowering herbs, vegetables, and annuals can provide some pollen and nectar, but prioritize native perennials for native pollinators."
- Tier 2, partial: Fuller S. 2024. Beyond milkweed: creating a migratory oasis for monarchs. AgriLife Today, Texas A&M AgriLife, 22 May 2024. <https://agrilifetoday.tamu.edu/2024/05/22/beyond-milkweed-creating-a-migratory-oasis-for-monarchs/>
  - "Although not native to Texas, annuals like zinnias, marigolds and cosmos thrive within the region and provide dynamic colors."
- Tier 2, partial: Texas A&M AgriLife Extension, Travis County. Butterfly Plants for Austin (guide by Travis County Master Gardener D. Jeffers). <https://travis-tx.tamu.edu/about-2/horticulture/ornamental-plants/annual-and-perennial-flowers-for-austin/butterfly-gardening/butterfly-plants-for-austin/>
  - "While we always encourage you to landscape with native and adapted plants, having areas of annual flowers that attract pollinators can bring extra enjoyment."
