# Retirement Town County Ranking — Developer Handoff

## 1. Current state

We built an exploratory county-ranking system for identifying attractive U.S. retirement locations using **21 factors**. The system has gradually expanded the county universe, recalculated every factor rank whenever counties were added, and used a randomized runoff / Monte Carlo process to generate the final ranking.

The latest workbook is:

**`county_rankings_top20_additions_100k.xlsx`**

It contains approximately **413 counties** and uses **100,000 MCMC/runoff iterations**.

The current spreadsheet should be treated as a **research/prototyping model**, not yet as a fully data-backed production dataset. A substantial portion of the values for newly introduced counties, and several entire factors, are still modeled/estimated rather than calculated directly from downloaded source files.

That is the main thing the next developer should fix.

---

# 2. Current factor set

The workbook currently ranks counties on these 21 factors:

1. Popular vote closeness
2. Party-affiliation proxy
3. Academic medical center density
4. Days ≥90°F
5. Drought days
6. Grocery stores per capita
7. College students per capita
8. Single-family home cost / $ per sq. ft.
9. Walkability
10. Distance to international airport
11. Public transportation
12. Future climate resilience
13. Homelessness per capita
14. Tradespeople per capita
15. Outdoor recreation
16. Noise pollution
17. Trees per acre
18. Natural disasters
19. Days below 50°F
20. Annual snowfall
21. Bad AQI days

All rank columns use:

**1 = best**

Ranks are recomputed over the entire county universe whenever counties are added. Ties receive average ranks.

---

# 3. Workbook structure

The recent workbooks generally contain:

### `Rank Matrix`

County/state plus:

* Runoff rank
* Avg Rank
* Python-computed Avg Rank check
* Difference/check column
* Avg-rank-based rank
* Average runoff elimination round
* Runoff wins
* Runoff win rate
* 21 individual factor ranks

### `Value Matrix`

The raw/model values behind each of the 21 factor ranks.

This is deliberately separate from the Rank Matrix.

### `Top 30`

Convenience copy of the leading counties.

### Screening / coverage sheets

Depending on the workbook generation:

* Top10 Neighbor Coverage
* Academic Med Coverage
* High-Level Candidate Screen
* Top50 Candidate Screen
* Top20 Added Screen

These document why counties were added.

### `Runoff Simulation`

MCMC parameters and leading simulation results.

### `Added Counties Log`

Tracks counties added during expansion passes.

### `QA Checks`

Basic consistency checks and rank-range checks.

### `Sources & Methodology`

Current source ideas / URLs and notes describing how each factor was estimated.

---

# 4. MCMC / randomized runoff algorithm

The runoff is intentionally different from simply sorting by average rank.

For every simulation:

1. Start with every county active.
2. Randomly shuffle the 21 factor columns.
3. Select one factor.
4. Eliminate the currently active county with the **worst numeric rank** for that factor.
5. If multiple counties are tied for worst, choose randomly between them.
6. Continue through the shuffled factors.
7. When all 21 factors have been used, reshuffle the 21 factors and continue.
8. Repeat until only one county remains.
9. The surviving county gets an elimination round equal to the number of counties.

Across 100,000 runs, track:

* average elimination round
* number of wins
* win rate

Final runoff ranking is primarily ordered by **average elimination round**.

The point of this procedure is to reward counties that are consistently hard to eliminate rather than counties that merely have a good arithmetic average.

### Implementation

The faster implementation uses:

**`runoff_mcmc.c`**

The C helper:

* pre-sorts counties worst-to-best for each factor
* uses a lightweight RNG
* handles random factor permutations / tie-breaking
* returns elimination sums and wins

Python uses the C function through `ctypes`.

This is dramatically faster than implementing 100,000 complete elimination runs in pure Python.

---

# 5. Important scripts created during this work

The relevant scripts include approximately:

### Core / earlier expansion

* `update_round2.py`
* `rerun_100k_mcmc.py`
* `runoff_mcmc.c`

### Academic-medical-center expansion

* `update_academic_med_centers.py`

This added counties corresponding to missing major cancer centers and high-NIH-funding medical schools.

### Top-10 neighboring-county expansion

* `update_surrounding_top10.py`

This checked counties physically touching the previous runoff top 10 and added missing neighbors.

### National factor-specialist expansion

* `update_highlevel_extremes.py`

This screened counties that appeared likely to rank extremely well in at least one factor, such as:

* college towns
* major transit counties
* mountain/outdoor counties
* forest counties
* Hawaii / low-cold counties
* low-cost counties

### Top-50 / two-factor expansion

* `update_top50_twoplus_candidates.py`

This screened counties that appeared likely to rank in the top 50 on **at least two factors**.

### Latest top-20-candidate expansion

* `add_top20_candidates_and_rerun.py`

This added:

* Hampden County, MA
* Bristol County, MA
* Tolland County, CT

and reran the 100,000-round simulation.

### Utility

* `parse_xlsx.py`

Used in some passes for reading workbook values.

The next developer should consolidate these into a proper Python package rather than continuing to create one-off scripts.

---

# 6. County-universe expansion history

The workbook initially contained a substantially smaller hand-selected candidate universe.

We repeatedly expanded it.

## Surrounding counties

We first added another ring of counties touching leading runoff counties.

For example, expansion around New Haven, La Crosse, Lackawanna, Berks, etc. ultimately took the universe to roughly **285 counties**.

A subsequent pass around the top five found additional missing counties surrounding Eau Claire, including:

* Chippewa WI
* Clark WI
* Buffalo WI
* Pepin WI
* Dunn WI

This brought the universe to roughly **290**.

## Academic medicine / cancer centers

We then checked that counties containing leading academic cancer centers and NIH-funded schools of medicine were included.

Missing counties added included:

* Harris TX — MD Anderson
* Suffolk MA — Harvard / Dana-Farber / MGH
* Olmsted MN — Mayo Rochester
* Baltimore city MD — Johns Hopkins
* St. Louis city MO — Washington University
* Davidson TN — Vanderbilt

Universe grew to roughly **296**.

## Neighbor expansion around the new top 10

We checked every county directly touching the prior runoff top 10.

This generated another substantial set, particularly around:

* Kalamazoo MI
* Allen IN
* Tippecanoe IN
* Chester PA

About **23 counties** were added, bringing the universe to roughly **319**.

## National specialist search

We then asked:

> Are there obvious counties likely to be top 10 on at least one factor that we have omitted?

Examples added included:

* King WA
* Multnomah OR
* Middlesex MA
* Brazos TX
* Whitman WA
* Teton WY
* Summit CO
* Aroostook ME
* Piscataquis ME
* Cook MN
* Honolulu HI
* Maui HI
* Ventura CA
* Broward FL
* Hidalgo TX
* Cameron TX

This took the universe to approximately **358 counties**.

## Top-50-on-two-factors search

We next screened counties likely to rank top 50 in at least two factors.

About **52 additional counties** were added.

Examples include many counties in:

* coastal California
* Colorado
* New England
* northern Wisconsin/Michigan
* Florida
* Texas
* Georgia / Carolinas
* Oregon

Universe became approximately **410 counties**.

## Latest top-20 candidate check

The final pass looked specifically for omitted counties that might plausibly enter the overall runoff top 20.

We identified and added:

* Hampden MA
* Bristol MA
* Tolland CT

After the actual 100,000-run simulation they did **not** finish in the top 20, which is useful evidence that the screening process is now reaching diminishing returns.

Final universe is approximately **413 counties**.

---

# 7. Current broad leaders

The exact order moves slightly from simulation to simulation / expansion pass, but counties repeatedly appearing near the very top include:

* Berks PA
* La Crosse WI
* New Haven CT
* Lackawanna PA
* Eau Claire WI
* Kalamazoo MI
* Ulster NY
* Chester PA
* Kent MI
* Isabella MI
* Dauphin PA

The important takeaway is that adding hundreds of plausible competitors has not caused the leading cluster to collapse completely.

That is encouraging, although better source data could still reshuffle it significantly.

---

# 8. The biggest technical caveat

## Many values are still estimates

The county-expansion work optimized for **candidate discovery**, not perfect source-data provenance.

When a new county was introduced, we generally supplied plausible values for all 21 factors based on:

* nearby counties
* regional climate
* known universities
* known hospitals
* geographic characteristics
* housing markets
* political results
* urban/rural character
* known transit / recreation context

Then every factor was reranked and the runoff rerun.

That is reasonable for identifying potentially omitted counties.

It is **not adequate for the final production model**.

The next major development phase should stop manually estimating county values and calculate them deterministically from downloaded source datasets.

---

# 9. Factor data-quality ranking

## Tier A — relatively strong / straightforward to make fully data-backed

### Presidential vote closeness

**Current backing:** good.

Suggested:

* MIT Election Data + Science Lab county presidential returns

This is probably the cleanest factor.

---

### College students per capita

**Current backing:** concept is good; implementation still partly modeled.

Suggested:

* IPEDS
* College Scorecard
* Census population

Need:

* institution → county FIPS
* actual on-campus enrollment
* avoid double-counting satellite / online enrollment

This should become highly reliable.

---

### Heat / cold / snowfall

Factors:

* ≥90°F days
* days below 50°F
* annual snowfall

**Current backing:** conceptually solid, but many current county values remain approximations.

Best improvement:

* NOAA/NCEI 1991–2020 Climate Normals
* station coordinates
* county polygons

Aggregate nearby / within-county stations.

These are among the easiest major improvements.

---

### AQI days

**Current backing:** currently modeled in many rows.

Use:

* EPA AirData
* annual AQI-by-county files or daily AQI files

Could become a nearly direct county-level factor.

High priority.

---

### Natural disasters

Use:

* FEMA OpenFEMA Disaster Declarations

Count county-designated disaster events over a fixed historical period.

Could become fully reproducible relatively easily.

Need to decide whether declarations are actually the desired definition of "natural disaster."

---

### Airport distance

The underlying geography is straightforward.

Need:

* fixed list of airports qualifying as "international"
* airport lat/lon
* county population centroid / primary city
* road distance or straight-line distance

Main uncertainty is **definition**, not source availability.

---

# 10. Medium-quality factors that have good replacement datasets

## Walkability

### Current state

One of the major weak factors.

Current numbers are essentially Walk Score-style estimates.

### Better data

Download:

**EPA National Walkability Index**

and ideally:

**EPA Smart Location Database**

These contain block-group measures for:

* density
* land-use diversity
* street intersection density
* transit proximity
* destination accessibility

Aggregate block groups to counties using population weighting.

This would be a major improvement.

---

## Public transportation

### Current state

Modeled.

### Better data

Use:

* EPA Smart Location Database
* EPA Access to Jobs and Workers Via Transit
* FTA National Transit Database
* ACS commute mode share

A strong county metric could combine:

1. population near transit
2. transit service density
3. jobs reachable within 45 minutes by transit
4. percentage of commuters using transit

This would be much more defensible.

---

## Grocery stores per capita

### Current state

Modeled.

### Better data

Download:

* Census County Business Patterns
* USDA Food Environment Atlas

Use NAICS grocery categories and divide establishments by population.

Potentially supplement with USDA food-access indicators.

Easy and valuable improvement.

---

## Tradespeople per capita

### Current state

One of the weaker factors.

### Better data

Use:

* BLS OEWS
* Census County Business Patterns

Relevant occupational groups include:

* construction and extraction
* installation, maintenance and repair

Problem:
OEWS geography is usually metro / nonmetro rather than county.

Possible method:

1. obtain occupation counts from OEWS
2. allocate metro values using CBP county employment / establishments
3. normalize by population

Alternatively use CBP NAICS contractor businesses directly, which may actually be more robust for this use case.

---

## Trees per acre

### Current state

Modeled.

### Better data

Use:

* USFS Forest Inventory & Analysis
* possibly NLCD tree canopy / land cover

For retirement purposes, **percent forest/tree canopy** may be a better and easier-to-explain metric than literal "trees per acre."

The user has also expressed interest in preserved woodland.

A future version could distinguish:

* % forest cover
* % permanently protected forest
* tree canopy around developed areas

---

## Noise pollution

### Current state

Modeled.

### Better data

Use:

* BTS National Transportation Noise Map

GIS aggregate noise raster / polygons to county population areas.

Population-weighted exposure would be better than land-area-weighted exposure.

This requires some GIS work but is feasible.

---

# 11. Weakest factors / biggest sources of uncertainty

These deserve the most scrutiny.

## #1 Homelessness

Probably the single most problematic input.

HUD PIT counts:

* are essentially one-night snapshots
* often use Continuum-of-Care geography rather than counties
* undercount unsheltered populations differently across locations

Still worth downloading:

* HUD PIT
* HUD HIC
* CoC geography crosswalks

But do not pretend the resulting county numbers are highly precise.

Possible alternative:

Treat homelessness as an ordinal / coarse-bucket factor rather than a fine-grained numeric rank.

---

## #2 Future climate resilience

Very difficult to define.

Current score attempts to blend:

* heat
* drought
* wildfire
* flooding
* hurricanes
* sea-level rise
* smoke
* future adaptation

That is too much for a manually constructed score.

Potential data:

* FEMA National Risk Index
* NOAA hazard data
* First Street data if obtainable
* US Climate Resilience Toolkit
* NCA climate projections
* wildfire probability
* sea-level / flood datasets

Recommended redesign:

Break this into measurable hazard components instead of one opaque score, or construct a documented composite.

---

## #3 Outdoor recreation

Current score is subjective.

Potential data:

* Trust for Public Land ParkServe
* USGS PAD-US protected lands
* National Park Service
* USFS lands
* state park GIS
* trail datasets
* lakes / coastline
* recreation-access datasets

A better objective score might combine:

* protected/recreational acres per resident
* % population within X minutes of recreation
* trail miles per resident
* lake/coast access
* park access

This requires GIS.

---

## #4 Walkability

Currently estimated.

Fortunately this has an easy solution:

**EPA National Walkability Index / Smart Location Database.**

One of the first factors the developer should replace.

---

## #5 Public transportation

Currently a subjective composite.

Replace with EPA/FTA/ACS data.

Also high priority.

---

## #6 Noise pollution

Currently a heuristic.

Replace with BTS Transportation Noise Map.

GIS required.

---

## #7 Trees / forest

Currently approximate.

Replace with FIA / NLCD.

---

## #8 Tradespeople

Currently modeled.

Replace with CBP + OEWS.

---

## #9 Party-affiliation proxy

This is inherently fuzzy because party registration is not comparable nationally.

Some states:

* register by party
* have open primaries
* do not make meaningful party registration available

Current solution uses election results as a proxy.

Possible options:

A. Keep presidential-vote closeness and **remove party affiliation** because it partly duplicates politics.

or

B. construct a standardized multi-election partisan index.

For example:

average county margin over:

* 2016 presidential
* 2020 presidential
* 2024 presidential
* relevant Senate/governor races

This would be more reproducible than a "party registration proxy."

---

# 12. Housing factor — important recent decision

The current workbook uses:

**Estimated single-family $ / sq. ft.**

This has weak / inconsistent backing.

We recently reviewed Zillow's downloadable datasets.

For the user's actual decision problem, the recommended Zillow source is:

**ZHVI 3-Bedroom Time Series — County**

Specifically a filename like:

`County_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv`

Reason:

The user currently lives in a **3-bedroom home and is likely to buy something similar again**.

Therefore, the actual relevant question is:

> What does a typical 3-bedroom home cost in this county?

rather than:

> What is the county's price per square foot?

### Recommended change

Replace:

**Single-family $/sq ft rank**

with:

**Typical 3-bedroom home value rank**

using the latest month of Zillow's county 3-bedroom ZHVI.

Lower = better.

### Optional sensitivity analysis

Also download:

**County ZHVI Single-Family Homes Time Series**

Then compare:

* 3-bedroom all-home ZHVI
  vs.
* overall single-family ZHVI

If rankings materially diverge, decide whether detached single-family housing should explicitly be a requirement.

This is a high-priority easy improvement.

---

# 13. Best downloadable datasets to acquire next

If only downloading a small number of files, prioritize roughly:

## 1. EPA National Walkability Index

Improves:

* walkability

## 2. EPA Smart Location Database

Improves:

* walkability
* transit
* accessibility

## 3. EPA Access to Jobs and Workers Via Transit

Improves:

* public transportation

## 4. EPA AirData county AQI

Improves:

* bad AQI days

## 5. NOAA Climate Normals

Improves:

* ≥90°F days
* <50°F days
* snowfall

## 6. Census County Business Patterns

Improves:

* grocery stores
* tradespeople

## 7. USDA Food Environment Atlas

Improves:

* grocery access

## 8. FEMA disaster / risk data

Improves:

* disasters
* future climate resilience

## 9. Zillow 3-bedroom county ZHVI

Improves:

* housing affordability

These datasets alone could dramatically improve roughly half the model.

---

# 14. Recommended engineering architecture

The next version should stop being a collection of scripts.

Suggested repository:

```text
retirement-town/
    pyproject.toml
    README.md

    data/
        raw/
        processed/

    src/retirement_town/
        config.py
        counties.py

        factors/
            politics.py
            academic_medicine.py
            heat.py
            drought.py
            groceries.py
            colleges.py
            housing.py
            walkability.py
            airports.py
            transit.py
            climate_resilience.py
            homelessness.py
            trades.py
            recreation.py
            noise.py
            trees.py
            disasters.py
            cold.py
            snowfall.py
            aqi.py

        ranking.py
        runoff.py
        export.py

    tests/
```

Every factor module should expose something like:

```python
calculate_factor(input_data) -> dataframe[fips, raw_value]
```

No factor should read values from the existing workbook.

The workbook should become **output only**.

---

# 15. County identifier

Stop joining primarily on:

`County + State`

Use:

**5-digit county FIPS**

everywhere.

Names become labels only.

This will prevent problems involving:

* Baltimore city
* St. Louis city
* Virginia independent cities
* duplicate county names
* spelling differences
* renamed counties

---

# 16. What production v1 should do

The ideal next milestone is:

> Produce raw values and ranks for every U.S. county/county-equivalent using only downloaded source files and deterministic code.

No manually entered county estimates.

The pipeline should:

1. Load canonical county/FIPS universe.
2. Calculate every implemented factor for every county.
3. Record raw values.
4. Rank values.
5. Run 100k runoff simulations.
6. Export Excel.
7. Produce QA/provenance output.

---

# 17. Provenance requirements

For every factor, record:

* dataset name
* dataset version/year
* source URL
* downloaded filename
* geographic granularity
* transformations applied
* missing-data handling
* direction: higher/lower better
* units
* update frequency

Ideally the Value Matrix should eventually have machine-readable provenance accompanying it.

---

# 18. Missing-data rules need to be explicit

Currently many missing inputs effectively became expert estimates.

That should stop.

For production, define rules such as:

### Option A — impute

Use state / neighboring-county / metro median.

### Option B — penalize

Missing = conservative/worst-case rank.

### Option C — exclude

Do not rank factor for that county and normalize average.

I would generally recommend:

* imputation only where defensible
* plus a **data confidence column**

For example:

```text
county_fips
factor
value
confidence
source
```

This would make uncertainty visible instead of hiding it.

---

# 19. MCMC improvements

The current runoff works well for experimentation.

Future improvements:

### Reproducibility

Keep:

* fixed seed
* recorded iteration count
* factor count
* algorithm version

### Stability testing

Run multiple independent 100k batches and calculate:

* mean runoff rank
* rank standard deviation
* probability of top 10
* probability of top 20
* probability of winning

This would be more informative than one single deterministic ordering.

### Data uncertainty simulation

Eventually, the more interesting Monte Carlo may be:

1. Sample uncertain **input factor values**
2. recompute ranks
3. run runoff

rather than randomizing only the elimination order.

That would quantify uncertainty caused by weak data.

---

# 20. Important interpretation of current results

Do not overinterpret small rank differences.

The current model is much better at saying:

> These 20–40 counties repeatedly look promising.

than:

> County #6 is definitively better than county #9.

Why:

Several factors still have enough measurement uncertainty that rank changes of tens of positions are plausible.

The current MCMC adds robustness against factor ordering, but it **does not fix inaccurate source values**.

Garbage-in/garbage-out still applies.

---

# 21. Suggested development priority

If I were taking over the project, I would work in this order:

### Phase 1 — infrastructure

1. Proper Python package
2. Canonical full U.S. county/FIPS table
3. Factor interface
4. Automated rank engine
5. Automated MCMC
6. Excel exporter
7. Tests

### Phase 2 — replace easiest weak factors

8. Zillow 3-bedroom ZHVI
9. EPA AQI
10. NOAA heat/cold/snow
11. EPA walkability
12. Census/USDA grocery
13. FEMA disasters

### Phase 3 — moderate GIS / joining work

14. EPA transit accessibility
15. BTS noise
16. FIA/NLCD trees
17. CBP/OEWS tradespeople
18. outdoor recreation

### Phase 4 — difficult conceptual factors

19. homelessness
20. future climate resilience
21. reconsider party-affiliation proxy

---

# 22. Factors I would consider redesigning entirely

Three deserve a fundamental rethink rather than merely finding a better file.

### Future climate resilience

Split into measurable subfactors or define a transparent composite.

### Outdoor recreation

Replace subjective scores with measurable physical access.

### Party affiliation

Potentially eliminate it because presidential-vote closeness already captures much of what this factor is trying to measure.

---

# 23. Factors that should be very good once upgraded

There is a realistic path to making these extremely defensible:

* presidential vote
* 3-bedroom home value
* college students
* heat
* cold
* snowfall
* AQI
* grocery establishments
* disasters
* airport distance
* walkability
* public transit

That would give the model a very strong quantitative backbone before tackling the harder factors.

---

# 24. Bottom line

The project has already done a lot of useful **search-space work**:

* hundreds of counties were added
* obvious neighboring counties were checked
* academic medical hubs were added
* cancer-center / NIH counties were added
* college, outdoor, transit, forest, climate, and housing specialists were screened
* top-50-on-multiple-factor counties were screened
* additional potential top-20 counties were tested
* the leading counties remained reasonably stable through expansion
* the runoff engine now supports 100,000 fast iterations

The main problem is no longer:

> "Did we forget an obvious county?"

The main problem is now:

> "Are the 21 raw factor values objectively calculated from authoritative datasets?"

That should be the next developer's primary focus.

The existing workbook and scripts are an excellent specification of **what the system is supposed to do**.

The next version should turn that prototype into a fully reproducible, source-data-driven pipeline.
