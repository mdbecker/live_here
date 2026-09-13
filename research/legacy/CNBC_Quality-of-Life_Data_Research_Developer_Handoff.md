# CNBC Quality-of-Life Data Research — Developer Handoff

## Goal

We investigated the data behind CNBC’s 2026 **“Best States to Live In”** and **“Worst States to Live In”** lists, both of which come from the **Quality of Life** category of CNBC’s *America’s Top States for Business* ranking.

The broader project goal is to:

1. Reproduce CNBC’s state-level Quality of Life ranking as closely as possible using public/open datasets.
2. Extend the same concepts to **all U.S. counties**.
3. Prefer authoritative, downloadable, reproducible datasets rather than hand-entered estimates.
4. Preserve the distinction between:

   * metrics genuinely observed at county level, and
   * state laws/policies that legitimately should be inherited by every county in the state.

No new Python scripts were created during this particular conversation. The work here was source identification, source prioritization, granularity analysis, and model-design guidance.

---

# 1. What CNBC appears to measure

CNBC says its 2026 Quality of Life score is worth **290 points**, representing **11.6%** of its overall business ranking.

The two articles reveal these main Quality of Life dimensions:

* Crime
* Air quality
* Health
* Childcare cost
* Childcare availability
* Worker protections
* Inclusiveness / anti-discrimination protections
* Reproductive rights

The articles also cite or discuss supporting measures including:

* Drug deaths
* Firearm deaths
* Homicides
* Premature deaths
* Primary-care availability
* Mental-health-provider availability
* Uninsured population
* Forgone medical care due to cost
* Self-rated health
* Frequent mental distress
* Dental visits
* Illicit opioid use
* Food insecurity
* Homelessness

CNBC does **not** publicly expose enough of its exact methodology to exactly reproduce the 290-point score. We still lack:

* the complete metric list;
* per-metric weights;
* normalization rules;
* score cutoffs;
* treatment of missing data;
* exact aggregation methods;
* exact historical snapshot dates for some legal/policy datasets.

Therefore the realistic objective is a **close reconstruction**, not an exact replication.

---

# 2. Geographic-granularity conclusion

The published CNBC ranking is entirely **state-level**.

However, many underlying data sources are much more granular.

### Finest available raw data

* **EPA AQS:** individual monitoring station + timestamp
* **CMS NPPES:** individual provider/practice address
* **State childcare licensing data:** often individual facility address
* **FBI NIBRS:** individual reported incident, associated with a law-enforcement agency

### Strong nationwide county data

* CDC mortality
* FBI-derived crime measures
* Air pollution
* Provider supply
* Insurance
* Many health outcomes
* Childcare prices
* Food environment variables

### Other useful geographies

* HUD homelessness: **Continuum of Care**
* ACS: county, tract, block group, ZCTA
* CDC PLACES: county, tract, place, ZCTA

### Important constraint

There is no evidence that CNBC itself calculated anything at ZIP, census tract, block group, or block level.

No confirmed CNBC input is a population measure published at **census-block** level.

For this project, **county is the best practical common geography**.

---

# 3. Best datasets identified

The datasets below were ranked according to:

1. importance for reproducing CNBC;
2. data quality;
3. county-level usefulness;
4. openness/ease of use.

## Tier 1 — highest priority

### 1. America’s Health Rankings / United Health Foundation

Best source for reconstructing CNBC’s **state-level health inputs** because CNBC explicitly cites United Health Foundation repeatedly.

Relevant measures include:

* drug deaths;
* firearm deaths;
* premature mortality;
* primary-care providers;
* mental-health providers;
* uninsured population;
* care avoided because of cost;
* frequent mental distress;
* self-rated health;
* dental visits;
* food insecurity;
* homelessness;
* illicit opioid use.

Many of these measures simply expose or transform data from CDC, CMS, Census, HUD, USDA, BRFSS, etc.

**Best use:** state CNBC reconstruction.

**Weakness:** mostly state-level.

---

### 2. County Health Rankings & Roadmaps

Probably the **single most useful starting dataset for the county model**.

Provides standardized county/FIPS-based files containing many relevant variables:

* violent crime;
* premature death;
* poor/fair health;
* mental-health measures;
* uninsured population;
* primary-care physicians;
* mental-health providers;
* air pollution;
* food insecurity;
* childcare centers;
* housing problems;
* poverty;
* income.

There is also an official open-source ecosystem around the project.

**Best use:** first-pass nationwide county model.

**Caveat:** it mixes source years and derived measures, so it is better for county extrapolation than exact CNBC state replication.

---

### 3. CDC PLACES

Very important for turning state-level BRFSS concepts into local estimates.

Provides modeled estimates at:

* county;
* place;
* census tract;
* ZCTA.

Useful CNBC-related measures include:

* depression;
* frequent mental distress;
* poor/fair self-rated health;
* health insurance;
* dental visits;
* routine checkups;
* other preventive-care measures.

**Best use:** local substitute for CNBC/UHF measures whose original BRFSS data exist primarily at state level.

**Important:** PLACES values are modeled estimates, not direct county surveys.

---

### 4. FBI UCR / Crime Data Explorer

Likely CNBC’s exact source for state violent-crime rates.

Useful for:

* violent crime;
* homicide;
* robbery;
* rape;
* aggravated assault.

Underlying NIBRS data can reach individual incidents.

**State model:** use FBI state estimates directly.

**County model:** initially use an existing prepared county measure such as County Health Rankings. Building an FBI agency-to-county pipeline is possible later but requires jurisdiction mapping and coverage adjustments.

---

### 5. EPA AQS / AirData

Authoritative federal air-quality source.

Relevant inputs:

* PM2.5;
* ozone;
* unhealthy-air days;
* annual/daily measurements.

American Lung Association’s *State of the Air* derives its grades from EPA monitor data.

**County issue:** many counties have no physical monitor.

A county model therefore needs either:

* modeled pollution estimates;
* interpolation;
* another prepared county pollution dataset;
* or an explicit missing/imputation flag.

---

### 6. CDC WONDER / NVSS mortality

High-value county-level source for:

* drug-overdose deaths;
* firearm deaths;
* homicide;
* premature mortality;
* suicide if desired.

This is likely the underlying source for many of the United Health Foundation mortality metrics CNBC quotes.

**Main problem:** suppression for small county counts.

Use:

* multiyear pooling;
* smoothing;
* empirical Bayes;
* or another defensible treatment.

Do not interpret suppressed values as zero.

---

### 7. Census ACS + SAHIE

Use ACS for:

* population denominators;
* household income;
* poverty;
* health insurance;
* demographics;
* housing;
* contextual variables.

Use **SAHIE** for county uninsured estimates because it gives single-year estimates for every county.

Recommended split:

* CNBC/state reconstruction: ACS 1-year where CNBC/UHF used it.
* County model: SAHIE and ACS 5-year.

---

### 8. HRSA Area Health Resources Files + CMS NPPES

Use for healthcare provider access.

Potential county variables:

* primary-care providers per capita;
* mental-health providers per capita;
* physicians;
* other healthcare resources.

**AHRF** is easiest for initial county work.

**NPPES** is more granular and can eventually support custom definitions based on provider taxonomy and practice location.

NPPES reaches individual provider addresses but requires careful deduplication and taxonomy handling.

---

### 9. Department of Labor National Database of Childcare Prices

Best fully open nationwide county-level childcare-price source identified.

Provides county/FIPS-linked prices by:

* age of child;
* childcare type;
* center vs family care.

This is an excellent county source but is older than the Child Care Aware data CNBC cites.

Recommended technique:

1. use newer Child Care Aware state values;
2. use DOL county data to estimate within-state variation;
3. rescale county estimates so state-weighted values agree with the newer state totals.

---

# 4. Policy datasets

These are important for reproducing CNBC but generally remain state-level.

## Oxfam America — Best States to Work Index

Very likely CNBC’s worker-protection input.

Contains policy measures related to:

* minimum wage;
* wage adequacy;
* paid sick leave;
* paid family leave;
* equal pay;
* sexual-harassment protections;
* worker organizing;
* local minimum-wage preemption;
* other labor protections.

**County model:** assign the state score to each county unless a verified local law justifies a local adjustment.

This is not a data deficiency; worker law genuinely operates primarily at the state level.

---

## Movement Advancement Project — LGBTQ Equality Maps

Strong candidate for CNBC’s broader inclusiveness score.

Tracks dozens of laws and policies including:

* nondiscrimination;
* public accommodations;
* employment;
* housing;
* education;
* healthcare;
* identity documents;
* LGBTQ youth;
* religious exemptions;
* family recognition.

It also tracks local ordinances in some states.

**Advantage:** one of the few policy sources capable of introducing legitimate city/county variation.

**Problem:** bulk historical data are less convenient than federal statistical datasets and the live map changes over time.

Need to preserve a dated snapshot for reproducibility.

---

## Guttmacher Institute

Best likely source for CNBC’s reproductive-rights dimension.

Potential variables:

* abortion bans;
* gestational limits;
* state protection of abortion rights;
* shield laws;
* medication abortion;
* telehealth;
* insurance/funding restrictions;
* provider restrictions.

**County model:** primarily inherit state law.

Optionally add a separate local access measure such as travel distance to an abortion provider, but do not confuse access with legal rights.

---

## NCSL

CNBC explicitly cites NCSL for public-accommodation laws.

Useful as a narrower supplementary inclusiveness input.

NCSL confirms state-level anti-discrimination/public-accommodation statutes but is not sufficient by itself for a complete inclusiveness score.

---

# 5. Childcare sources

## Child Care Aware of America

Likely CNBC’s direct source for:

* number of licensed childcare centers;
* childcare supply per capita;
* childcare prices;
* price as a percentage of household income.

This is the right source for state-level CNBC replication.

The major weakness is county granularity.

County alternatives:

1. DOL National Database of Childcare Prices;
2. County Health Rankings childcare-center counts;
3. individual state licensing datasets.

A later high-quality implementation could download childcare licensing records separately for every state and geocode/count facilities by county.

---

# 6. Air-quality sources

CNBC reveals two distinct sources:

### American Lung Association

Uses EPA measurements and produces:

* county grades;
* metropolitan rankings;
* ozone measures;
* PM2.5 measures.

Useful primarily as a validation layer.

The preferred reproducible upstream source is EPA itself.

### First Street Foundation

The “best states” article reveals First Street as an additional CNBC air-quality source.

First Street can model risk at very fine spatial resolution, potentially individual properties.

However:

**First Street bulk data are not fully open.**

Therefore it is not recommended as a required dependency for the open-data version of this project.

Best substitute:

* EPA AQS;
* plus a fully open modeled PM2.5/air-quality surface or prepared county estimates.

This remains a potential gap if exact CNBC reproduction requires First Street.

---

# 7. Additional sources uncovered in the “best states” article

## HUD PIT/HIC homelessness

Underlying source for UHF homelessness measures.

Provides estimates at:

* state;
* Continuum of Care.

A CoC can be:

* a county;
* city;
* multiple counties;
* or another regional grouping.

Therefore it cannot be naively treated as county data.

Potential county approximation requires allocation or a crosswalk.

---

## RADARS NMURx

Used for illicit-opioid-use prevalence cited through United Health Foundation.

Appears to be essentially **state-level** for national comparative purposes.

This is a weak county candidate.

Use a different local opioid measure at county level, likely CDC overdose mortality or other local indicators.

---

## Commonwealth Fund State Health System Scorecard

CNBC cites this for New Jersey.

High-quality dataset, but probably contextual rather than a direct CNBC scoring input.

It overlaps substantially with:

* CDC;
* CMS;
* ACS;
* UHF.

Do not include it by default because doing so risks double counting health.

Use it for validation only unless further evidence shows CNBC directly scored it.

---

## Giffords Law Center

Mentioned in connection with Maine gun-law changes.

Almost certainly narrative/contextual rather than a CNBC scoring variable.

Do not add it unless evidence emerges that gun-law policy itself was explicitly scored.

---

## VCU Ceasefire Virginia evaluation

Useful context for Virginia crime policy.

Not nationally comparable.

Do not use in the national scoring model.

---

# 8. Factors with strong data backing

These are in good shape and should be implemented first.

### Crime

**State:** FBI UCR.

**County:** County Health Rankings initially; later custom FBI mapping if necessary.

Confidence: **high**.

---

### Mortality / serious health outcomes

**State:** America’s Health Rankings.

**County:** CDC WONDER.

Includes:

* drug deaths;
* firearm deaths;
* homicide;
* premature mortality.

Confidence: **very high**.

---

### Health insurance

**State:** ACS/AHR.

**County:** SAHIE.

Confidence: **very high**.

---

### Provider availability

**State:** AHR/CMS.

**County:** HRSA AHRF or NPPES.

Confidence: **high**.

---

### Behavioral/self-reported health

**State:** AHR/BRFSS.

**County:** CDC PLACES.

Confidence: **high**, with the qualification that county estimates are modeled.

---

### Air quality

**State:** EPA/American Lung Association.

**County:** EPA plus modeled/fallback pollution estimates.

Confidence: **high for monitored locations; moderate for nationwide county coverage**.

---

### Worker protections

**State:** Oxfam.

**County:** inherit state score.

Confidence: **high**.

---

### Reproductive rights

**State:** Guttmacher.

**County:** inherit state law.

Confidence: **high conceptually**, although CNBC’s exact scoring formula is unknown.

---

# 9. Factors that still have weak or incomplete data backing

These deserve most of the next developer’s research effort.

## A. Inclusiveness

### What we have

* MAP LGBTQ Equality Maps
* NCSL public-accommodation laws
* state/local antidiscrimination statutes

### Problem

CNBC does not disclose exactly which inclusiveness laws are scored or how they are weighted.

MAP is likely the best broad proxy, but:

* no simple frozen national historical CSV has yet been identified;
* local-law coverage is uneven;
* CNBC may combine MAP/NCSL with other civil-rights datasets.

### Next work

Create an explicit inclusiveness schema and determine which variables can be bulk downloaded historically.

Priority: **very high**.

---

## B. Childcare supply

### What we have

* Child Care Aware state totals
* County Health Rankings childcare centers
* individual state licensing databases

### Problem

There is no single authoritative national facility-level open dataset matching CNBC’s Child Care Aware totals.

### Next work

Decide between:

1. CHR&R as the practical county proxy, or
2. building a national state-by-state childcare-license ingestion pipeline.

Priority: **high**.

---

## C. Childcare affordability

### What we have

* Child Care Aware newer state values
* DOL NDCP older county prices

### Problem

The best county file is not contemporaneous with CNBC’s 2025/2026 state data.

### Next work

Implement state calibration/rescaling:

$$
county_{new}
=
county_{old}
\times
\frac{state_{new}}{state_{old}}
$$

or a more careful version by care type and child age.

Priority: **high**.

---

## D. Air quality in unmonitored counties

### What we have

* EPA AQS
* American Lung Association
* First Street, but proprietary

### Problem

EPA monitors do not cover every county, while First Street’s national modeled data are not fully open.

### Next work

Identify the best **100% open nationwide modeled PM2.5/ozone surface** and use it to fill counties lacking EPA monitors.

Priority: **high**.

---

## E. Homelessness

### What we have

HUD PIT/HIC at CoC level.

### Problem

CoCs do not align cleanly with counties.

### Next work

Build a CoC-to-county crosswalk and choose a transparent allocation strategy, or use an alternate county homelessness dataset.

Priority: **medium** unless homelessness proves to have substantial CNBC weight.

---

## F. Food insecurity

### What we have

* USDA state food-security survey
* UHF state values
* CHR&R county food insecurity
* USDA Food Environment Atlas

### Problem

The exact USDA household food-security statistic used by CNBC/UHF does not have an equivalent direct county estimate nationwide.

### Next work

Use CHR&R’s county estimate or another established modeled county food-insecurity dataset while keeping the UHF/USDA value for state reproduction.

Priority: **medium**.

---

## G. Illicit opioid use

### What we have

RADARS NMURx state survey.

### Problem

No good equivalent national county prevalence dataset.

### Next work

Probably do **not** attempt to fabricate county prevalence. Replace it locally with a better observed indicator such as:

* overdose mortality;
* opioid-related ED visits where available;
* prescribing rates;
* other CDC/local opioid indicators.

Priority: **low-to-medium** because drug mortality is already a strong county measure.

---

# 10. Proposed architecture

The county model should explicitly distinguish local observations from state policy.

For county \(c\):

$$
Q_c = \sum_i w_i L_{ic} + \sum_j w_j S_{j,s(c)}
$$

where:

* \(L_{ic}\) = genuinely local/county observations;
* \(S_{j,s(c)}\) = state-level policies inherited by the county.

Examples of local variables:

* violent crime;
* overdose deaths;
* premature mortality;
* provider availability;
* insurance;
* childcare prices;
* air pollution;
* mental-health prevalence.

Examples of state variables:

* worker protections;
* abortion/reproductive-rights laws;
* statewide civil-rights protections.

Local ordinances should modify only the appropriate policy components.

---

# 11. Recommended implementation order

## Phase 1 — reproduce state rankings

Create one table with all 50 states and the strongest candidate input variables from:

* America’s Health Rankings;
* FBI;
* EPA / ALA;
* Child Care Aware;
* Oxfam;
* MAP/NCSL;
* Guttmacher.

Compare variables with CNBC’s published 0–290 scores.

Fit a constrained model to infer likely weights.

A reasonable approach is:

* standardized inputs;
* directionality encoded explicitly;
* nonnegative weights;
* regularization;
* broad category-level weight constraints.

Evaluate:

* Pearson correlation;
* Spearman rank correlation;
* mean absolute ranking error;
* performance on CNBC’s top/bottom states.

Do not optimize purely for correlation if it produces implausible weights.

---

## Phase 2 — county version

Build one row per county keyed by FIPS.

Preferred initial sources:

* County Health Rankings
* CDC PLACES
* CDC WONDER
* SAHIE
* ACS
* HRSA AHRF
* FBI/CHR&R crime
* EPA or modeled air data
* DOL childcare prices

Then join state-policy variables by state FIPS.

---

## Phase 3 — replace convenience datasets with upstream sources

Once the model works, gradually replace derived aggregators where worthwhile.

Examples:

* CHR&R crime → FBI
* CHR&R mortality → CDC WONDER
* CHR&R provider counts → NPPES
* CHR&R demographics → Census
* CHR&R air → EPA/modeled pollution source

This creates a cleaner and more reproducible long-term pipeline.

---

# 12. Recommended source priority for the next developer

### Download/use immediately

1. America’s Health Rankings
2. County Health Rankings & Roadmaps
3. CDC PLACES
4. FBI UCR/CDE
5. CDC WONDER
6. EPA AQS/AirData
7. Census ACS
8. Census SAHIE
9. HRSA AHRF
10. DOL National Database of Childcare Prices

### Add next

11. Oxfam Best States to Work
12. Guttmacher state abortion-policy data
13. MAP LGBTQ Equality Maps
14. Child Care Aware
15. HUD PIT/HIC
16. USDA food datasets

### Validation/context only unless further research changes this

* American Lung Association
* Commonwealth Fund
* NCSL
* Giffords
* VCU Ceasefire evaluation
* NBER abortion/migration study

---

# 13. Biggest remaining unknown

The biggest unresolved issue is **not lack of basic health/crime data**.

Those dimensions now have strong public sources.

The largest remaining uncertainty is CNBC’s proprietary scoring process, especially:

1. which exact policy variables constitute **Inclusiveness**;
2. how **Reproductive Rights** is scored;
3. how **Worker Protections** is weighted;
4. how childcare **price vs supply** are combined;
5. how ALA and First Street air-quality measures are combined;
6. how many separate health metrics CNBC includes;
7. the metric-level weights and transformations used to convert all these data into a 290-point score.

The next developer should therefore focus less on finding yet another mortality or demographic dataset and more on **formalizing the poorly documented policy and childcare components and reverse-engineering CNBC’s weights from the 50 published state scores**.

---

# Recommended v1 data philosophy

A robust v1 should only use reproducible inputs with documented provenance.

Every field should store or be traceable to:

* source dataset;
* source year;
* download/version date;
* original geography;
* transformation;
* whether the value is observed, modeled, inherited from state policy, or imputed;
* confidence/data-quality flag.

Avoid inserting hand-estimated county values merely to eliminate nulls.

Where county data genuinely do not exist, either:

* inherit the state policy value when conceptually appropriate;
* use a clearly labeled modeled proxy;
* or leave the value unavailable until a defensible source is found.

That will make the county rankings much easier to audit and improve over time.
