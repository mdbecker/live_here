Below is the handoff summary I’d give the next developer. The key point is that the ranking/MCMC machinery is in decent shape; the main remaining work is replacing modeled factor values with reproducible raw-data pipelines.

## 1. Project goal and current state

The project ranks U.S. counties as potential retirement locations using **21 independent factors**. Each factor has:

* a raw/value column in **Value Matrix**
* a corresponding rank in **Rank Matrix**
* a common rank convention of **1 = best, N = worst**
* average ranks for ties
* an overall simple **Avg Rank**
* a separate randomized **runoff/MCMC rank**

The current workbook from this conversation is:

**`county_rankings_sources_checked_100k.xlsx`**

Its principal sheets are:

* `Rank Matrix`
* `Value Matrix`
* `Top 30`
* `Result Comparison`
* `Runoff Simulation`
* `Sources & Methodology`
* `Data Acquisition Log`
* `Sources Not Imported`
* `QA Checks`

The workbook currently contains roughly **413 counties**, not every U.S. county. The longer-term direction should be to generate values for **every U.S. county directly from source datasets**, rather than continuing to expand a hand-curated candidate set.

The latest 100k-run MCMC still had the top five as approximately:

1. Berks County, PA
2. La Crosse County, WI
3. New Haven County, CT
4. Lackawanna County, PA
5. Eau Claire County, WI

The most recent source-research pass did **not** alter the 21 underlying values, so any minor MCMC movement in that pass was just stochastic simulation variation, not new source data.

---

# 2. How the ranking system works

For each factor, counties are ranked independently.

For a factor where lower is better:

```text
lowest value -> rank 1
highest value -> rank N
```

For a factor where higher is better:

```text
highest value -> rank 1
lowest value -> rank N
```

Ties receive average ranks.

`Avg Rank` is simply:

```text
mean(all 21 factor ranks)
```

The runoff ranking deliberately behaves differently.

For each MCMC simulation:

1. Start with every county still active.
2. Randomly select one of the 21 factor-rank columns.
3. Eliminate the currently active county with the **worst rank** on that factor.
4. If several counties tie for worst, randomly choose one of the tied counties.
5. Every factor must be selected exactly once before beginning another randomized 21-factor cycle.
6. Continue until only one county survives.
7. Record each county's elimination round.
8. Repeat **100,000 times**.

The primary output is:

```text
Runoff avg elimination round
```

Higher means the county tends to survive longer.

We also retain:

* runoff wins
* runoff win rate
* runoff rank

This favors counties that are **consistently decent across many dimensions** rather than counties that are spectacular in a few factors and terrible in others.

---

# 3. How the county universe expanded

The analysis initially centered around counties whose presidential voting most closely resembled the national popular vote, using **absolute percentage-point difference**, not a binary red/blue match.

Over time we deliberately expanded the universe so that this initial political screen would not prevent excellent retirement counties from being considered.

Additions included, among others:

* Montgomery County, PA
* Tompkins County, NY / Ithaca
* Niagara County, NY
* Cumberland County, ME / Portland
* Lake George-area counties
* Finger Lakes counties
* the Corning Museum area
* counties containing major colleges
* counties surrounding the leading runoff counties
* counties containing major academic medical centers
* top cancer-center counties
* top NIH-funded medical-school counties
* counties likely to be extreme/top performers in an individual factor
* counties likely to rank top-50 on **two or more factors**

One broader screen considered **72 candidate counties** and added **52 missing counties**.

A later "possible missing top-20" screen added:

* Hampden County, MA
* Bristol County, MA
* Tolland County, CT

Once those three were actually entered and the full 21-factor MCMC rerun, they did **not** make the top 20:

* Bristol, MA: ~61
* Hampden, MA: ~74
* Tolland, CT: ~89

That is an important lesson for the next developer: **intuition about individual factor strengths is not sufficient to predict the runoff result.**

---

# 4. The 21 factors: current implementation and desired replacement

The table below is the most important part of the handoff.

|  # | Factor                              | Direction | Current state                                             | Intended improved source / methodology                                                                                                              |
| -: | ----------------------------------- | --------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
|  1 | Presidential popular-vote closeness | Lower     | Relatively strong/data-informed                           | MIT Election Lab county presidential returns; compute exact absolute county-vs-national Democratic vote-share differences across selected elections |
|  2 | Party-affiliation proxy             | Lower     | **Weak/model-based**                                      | State voter-registration files where available; election-result proxy only where registration isn't comparable                                      |
|  3 | Academic medical-center density     | Higher    | **Medium/model-based**                                    | AAMC teaching hospitals + ACGME residencies + medical schools + NIH/BRIMR funding + NCI cancer centers; distinguish main campuses from satellites   |
|  4 | Days ≥90°F                          | Lower     | **Currently estimated**                                   | NOAA/NCEI 1991–2020 daily temperature normals                                                                                                       |
|  5 | Drought days                        | Lower     | **Currently estimated**                                   | U.S. Drought Monitor D1+ historical county exposure                                                                                                 |
|  6 | Grocery stores per capita           | Higher    | **Currently estimated; source now downloaded**            | 2023 Census County Business Patterns + Census 2023 county population                                                                                |
|  7 | College students per capita         | Higher    | Medium/model-based                                        | IPEDS / College Scorecard enrollment geocoded to campuses                                                                                           |
|  8 | Single-family home $/sq ft          | Lower     | **Modeled**                                               | Zillow/Redfin county data; ideally property-type-specific single-family metric                                                                      |
|  9 | Walkability                         | Higher    | **Weak/model-based**                                      | EPA National Walkability Index / Smart Location Database, population-weighted from block groups                                                     |
| 10 | Distance to international airport   | Lower     | Medium/model-based                                        | FAA airport data + actual scheduled international-service definition + routing from population-weighted county center                               |
| 11 | Public transportation               | Higher    | **Weak/model-based**                                      | EPA Access to Jobs and Workers Via Transit + FTA National Transit Database                                                                          |
| 12 | Future climate resilience           | Higher    | **Very weak/model-based**                                 | FEMA NRI/RAPT + CMRA + NOAA projections + wildfire/flood/sea-level/heat/water-stress layers                                                         |
| 13 | Homelessness per capita             | Lower     | **Probably weakest current factor**                       | HUD PIT/HIC + CoC→county crosswalk + local PIT data                                                                                                 |
| 14 | Tradespeople per capita             | Higher    | **Currently estimated; source now downloaded**            | 2023 Census CBP employment in selected NAICS categories / county population; BLS OEWS as supplementary evidence                                     |
| 15 | Outdoor recreation access           | Higher    | **Weak/subjective model**                                 | GIS: parks, PAD-US/public lands, trails, lakes, beaches/coast, waterways, ParkServe                                                                 |
| 16 | Noise pollution                     | Lower     | **Weak/model-based**                                      | BTS National Transportation Noise Map county/population-weighted exposure                                                                           |
| 17 | Trees per acre                      | Higher    | **Weak/model-based**                                      | USFS FIA and/or NLCD forest/tree-canopy GIS                                                                                                         |
| 18 | Natural disasters per decade        | Lower     | **Modeled**                                               | OpenFEMA county declarations + FEMA hazard/risk measures                                                                                            |
| 19 | Days below 50°F                     | Lower     | **Currently estimated**                                   | NOAA daily normals                                                                                                                                  |
| 20 | Annual snowfall                     | Lower     | **Currently estimated**                                   | NOAA annual/seasonal snowfall normal                                                                                                                |
| 21 | Bad AQI days                        | Lower     | **Currently estimated; excellent replacement identified** | EPA annual AQI-by-county files, preferably a recent multi-year average                                                                              |

---

# 5. Factor-specific details and decisions already made

## Presidential voting

Original definition was corrected early in the project.

It is **not**:

> did the county vote for the national winner?

It is:

```text
absolute difference between county vote percentage
and national popular-vote percentage
```

Ideally calculate this across several presidential elections and average it.

This is one of the factors that should be straightforward to make fully reproducible.

---

## Party-affiliation proxy

This remains conceptually problematic.

Party registration is not collected consistently across states, and some states do not have comparable partisan registration at all.

The current factor therefore functions largely as an electoral/partisan-composition proxy.

Future implementation should explicitly distinguish:

```text
states with usable party-registration data
vs.
states requiring modeled partisan affiliation
```

A provenance/confidence flag would help.

---

## Academic medicine

We deliberately wanted **actual academic medical access**, not simply "number of hospitals."

The desired future measure should account for:

* major teaching hospitals
* medical schools
* residency/fellowship programs
* NIH-funded schools of medicine
* NCI-designated cancer centers

Main academic campuses should count more than satellites.

The county population denominator matters substantially because a smaller county containing a major center can rank very highly.

---

# 6. NOAA climate work already scoped

We investigated the NOAA/NCEI **1991–2020 Climate Normals** in detail.

The daily access directory consists of a very large number of individual station CSVs, which is why the bulk archives are preferable for automation. 

The particularly useful bulk archive identified was:

```text
us-climate-normals_1991-2020_v1.0.1_daily_temperature_by-variable_c20230403.tar.gz
```

This should improve two current factors:

### 90°F+ days

Proposed future definition:

```text
count of normal calendar days where DLY-TMAX-NORMAL >= 90°F
```

### Days below 50°F

We specifically decided the better retirement-oriented definition is:

```text
count of normal calendar days where DLY-TMAX-NORMAL < 50°F
```

That means a day that normally **fails to warm above 50°F**.

Do **not** use `TMIN < 50°F`; that would count mild nights over a huge portion of the country and would not capture the intended "cold-day burden."

### Snowfall

Prefer an Annual/Seasonal normal containing something equivalent to:

```text
ANN-SNOW-NORMAL
```

Then:

```text
annual snowfall ft = snowfall inches / 12
```

This is preferable to reconstructing annual snow from hundreds of daily values.

---

# 7. Drought work already scoped

The current `Drought days` column is an estimate and should be replaced.

We found the U.S. Drought Monitor county report interface and decided to use:

```text
Section: Non-consecutive Weeks in Drought
State: All States
Dates: 1/1/2015 through 1/1/2025
Level: D1
Min Weeks: 2
Output: CSV
```

Why D1:

* D0 = "Abnormally Dry"
* D1 = actual **Moderate Drought**
* therefore D1+ better matches the intended factor

Approximate conversion:

```text
Drought days/year =
D1+ weeks over 10 years × 7 / 10
```

The form does not allow `Min Weeks = 1`; its minimum is 2.

That is acceptable. A county omitted from the result might have had either 0 or 1 D1+ week over a decade, a difference of at most:

```text
7 / 10 = 0.7 days/year
```

which is negligible for the ranking.

NOAA precipitation normals can be used as **climate dryness context**, but should not replace actual Drought Monitor history for this factor.

We identified **monthly precipitation normals** as most useful for drought/climate context, followed by monthly temperature for an aridity/evapotranspiration proxy.

---

# 8. AQI work already scoped

EPA AirData is one of the easiest major quality upgrades.

EPA explicitly provides annual AQI files with **one row per county/year and counts by AQI category**, which maps almost perfectly to our factor. 

EPA also notes that its downloadable files are updated twice yearly and reporting agencies can have up to six months to submit data. 

Files identified:

```text
annual_aqi_by_county_2020.zip
annual_aqi_by_county_2021.zip
annual_aqi_by_county_2022.zip
annual_aqi_by_county_2023.zip
annual_aqi_by_county_2024.zip
```

Those files all exist in the EPA listing. 

Recommended future metric:

```text
Bad AQI days =
Unhealthy for Sensitive Groups
+ Unhealthy
+ Very Unhealthy
+ Hazardous
```

Then use approximately a **5-year average, 2020–2024**.

We considered 2023+2024, but 2023 was unusually smoke-heavy, so a multi-year average is preferable.

We also investigated 2025. The available version in the source material was dated 2025-11-24 and had fewer county records than 2024, so we decided not to use it until a finalized post-year reporting cycle is available. 

This factor should be one of the easiest to upgrade from "estimated" to "real observed data."

---

# 9. CBP data: now actually downloaded by the user

This is the biggest concrete progress at the end of the conversation.

The user confirmed downloading the Census/CBP package we selected.

The bundle should contain:

### Main data

**2023 County Business Patterns — County File**

CBP provides industry-level subnational data including establishments, employment, payroll, etc. ([Census.gov][1])

### Supporting files

* County Record Layout
* 2017 NAICS Descriptions, applicable to 2017–2023
* State and County Reference, 2022–2023

### Population denominator

* `CO-EST2025-alldata`
* its File Layout

Use the **2023 population estimate** from that file so numerator and denominator refer to the same year.

## Grocery calculation planned

Primary NAICS:

```text
445110
```

Full-service supermarkets/grocery retailers.

Proposed metric:

```text
grocery establishments per 10,000 =
2023 NAICS 445110 ESTAB
/ 2023 county population
× 10,000
```

Possible future enhancements can give partial weight to:

* convenience stores
* specialty food stores

but `445110` is the clean initial definition.

## Trades calculation planned

Primary group:

```text
238 — Specialty Trade Contractors
```

Important detailed categories include, for example:

```text
238210 Electrical Contractors
238220 Plumbing / Heating / Air Conditioning
238160 Roofing
238320 Painting
238330 Flooring
238350 Finish Carpentry
238130 Framing
238310 Drywall / Insulation
```

Prefer **employment**, not number of firms:

```text
tradespeople per 1,000 =
selected CBP trade employment
/ 2023 county population
× 1,000
```

CBP covers paid-employee establishments, so it will undercount sole-proprietor/nonemployer tradespeople. That is one reason BLS OEWS and/or Census Nonemployer Statistics could eventually supplement it.

BLS OEWS May 2025 publishes occupation estimates at national, state, metro and nonmetro levels and also provides downloadable all-data files, so it remains a useful supplementary source but does not solve county geography by itself. ([Bureau of Labor Statistics][2])

---

# 10. Walkability / transit work identified but not yet implemented

These are currently relatively weak modeled scores.

High-value sources identified:

### EPA National Walkability Index

Use block-group-level values and aggregate to county using **population weighting**, not land-area averaging.

### EPA Smart Location Database

Potentially useful underlying measures:

* residential/employment density
* land-use mix
* intersection/street connectivity
* destination accessibility
* transit access

### EPA Access to Jobs and Workers Via Transit

Good candidate for a much more meaningful transit score than simply counting systems/stops.

### FTA National Transit Database

Useful supporting data:

* service miles/hours
* passenger trips
* agency coverage
* modes

The difficult part is assigning multi-county transit agencies back to individual counties.

---

# 11. Housing

Current single-family $/sqft values are still partly modeled.

We identified Zillow Research county files as a likely replacement.

The desired measure is something close to:

```text
single-family home cost per square foot
```

The user's likely purchase target is roughly a **3-bedroom single-family home**, so property-type-specific Zillow data would be preferable over "all homes" if available.

This factor still needs a clean reproducible definition.

---

# 12. Homelessness

This was judged the **largest likely source of input error**.

Problems:

* HUD PIT is a one-night count
* unsheltered homelessness is difficult to count consistently
* geography is commonly **Continuum of Care**, not county
* methodology varies by jurisdiction

Future pipeline:

```text
HUD PIT/HIC
+ CoC-to-county geographic crosswalk
+ local county/city PIT reports where necessary
```

This factor should carry a confidence/provenance flag even after improvement.

---

# 13. Future climate resilience

This is probably the second-most uncertain factor.

Current score blends concepts like:

* future heat
* drought/water stress
* wildfire/smoke
* flooding
* hurricanes
* coastal/sea-level exposure
* adaptive capacity

A better implementation should be explicitly decomposed rather than assigning one subjective score.

Potential components:

```text
FEMA NRI/RAPT risk
NOAA climate projections
CMRA hazard layers
flood exposure
wildfire exposure
sea-level/storm surge
heat projections
water stress
```

Then define transparent weights.

Do not let this become a black-box score.

---

# 14. Outdoor recreation

Current score is subjective/model-based.

A future GIS pipeline could combine:

* PAD-US/public land
* local/state/federal parks
* trails
* lakes
* rivers
* coastline/beaches
* recreational water access
* TPL ParkServe where available

Important design question:

Should the factor measure:

```text
amount of outdoor land
```

or:

```text
actual accessible recreation near residents?
```

The latter is probably preferable for retirement.

---

# 15. Noise pollution

Current factor is modeled using:

* airports
* roads
* rail
* ports
* density/urbanization

Replacement:

**BTS National Transportation Noise Map**

Ideally calculate a population-weighted noise exposure rather than county land-area average.

---

# 16. Trees per acre

Current estimates were based on general forest/canopy context.

Better sources:

* USFS Forest Inventory & Analysis
* NLCD forest cover
* NLCD/other tree-canopy data

A future definition needs to decide whether this is literally:

```text
estimated number of trees / acre
```

or whether a more robust metric such as:

```text
% tree canopy
```

would better represent what we care about.

Percent canopy is likely easier to measure consistently.

---

# 17. Natural disasters

Current values remain approximate.

Proposed replacement:

```text
OpenFEMA Disaster Declarations
+ FEMA NRI/RAPT
```

But the developer needs to decide whether the actual concept is:

* number of declared disasters
* probability of hazardous events
* expected annual loss
* severity
* or some combination

Declarations alone have an administrative/political component.

---

# 18. Main data-quality ranking

The factors previously judged most likely to contain substantial error, approximately from worst downward, were:

1. **Homelessness**
2. **Future climate resilience**
3. **Tradespeople per capita**
4. **Outdoor recreation**
5. **Walkability**
6. **Public transportation**
7. **Noise pollution**
8. **Trees per acre**
9. **Bad AQI days**
10. **Natural disasters**
11. **Party-affiliation proxy**
12. **Grocery stores**
13. **Housing $/sqft**
14. **Academic medical centers**
15. **College students**
16. **Airport distance**
17. **Drought**
18. **Snowfall**
19. **Days below 50°F**
20. **90°F+ days**
21. **Presidential vote closeness**

Several of those should move dramatically upward in quality once the newly identified raw datasets are integrated.

In particular:

* AQI can become quite strong.
* heat/cold/snow can become quite strong.
* drought can become quite strong.
* grocery/trades can become substantially stronger using CBP.

---

# 19. Python/code artifacts explicitly referenced in this conversation

At minimum, these were created or used here:

### `update_top50_twoplus_candidates.py`

Purpose:

* load existing workbook
* screen likely omitted counties that could place top-50 in ≥2 factors
* add qualifying candidates
* calculate all 21 factor ranks
* rerun 100k MCMC
* rebuild formatted workbook
* maintain source/methodology sheets
* perform QA/formula checks

### `add_top20_candidates_and_rerun.py`

Purpose:

* add Hampden MA, Bristol MA and Tolland CT
* assign provisional 21-factor values
* recalculate all ranks
* rerun 100k MCMC
* rebuild workbook

### `rerun_100k_mcmc.py`

Referenced as a reusable MCMC rerun script.

### `runoff_mcmc.c`

Compiled C implementation used to make the 100,000 simulations fast enough.

The Python scripts call the compiled shared library through `ctypes`.

The new developer should **not** continue indefinitely with a pile of one-off workbook-update scripts. These should be mined for logic and consolidated into a proper package.

---

# 20. Recommended new project structure

A cleaner next version would look roughly like:

```text
retirement_counties/
    pyproject.toml
    src/
        retirement_counties/
            geography.py
            ranking.py
            runoff.py

            factors/
                elections.py
                party.py
                academic_medicine.py
                temperature.py
                drought.py
                grocery.py
                colleges.py
                housing.py
                walkability.py
                airports.py
                transit.py
                climate_resilience.py
                homelessness.py
                trades.py
                outdoor.py
                noise.py
                trees.py
                disasters.py
                aqi.py

            sources/
                census.py
                noaa.py
                epa.py
                fema.py
                hud.py
                ipeds.py
                bls.py
                zillow.py

            export/
                excel.py

    data/
        raw/
        processed/

    tests/
```

Each factor function should take raw source data and return something like:

```python
county_fips
value
source_year
source
is_imputed
confidence
```

That is much safer than embedding estimates directly into scripts.

---

# 21. Highest-priority remaining work

For the new developer, I would do the next work in this order.

1. **Integrate the CBP bundle you just downloaded.** Replace grocery and trades estimates with 2023 data and 2023 population denominators.

2. **Integrate EPA AQI 2020–2024.** This should be easy and turns a weak factor into a strongly data-backed one.

3. **Integrate NOAA Climate Normals.** Replace ≥90°F days, below-50°F days and snowfall.

4. **Integrate U.S. Drought Monitor.** Replace drought estimates with actual D1+ historical exposure.

5. **EPA Walkability/Smart Location/Transit.** Replace two particularly subjective factors.

6. **FEMA/OpenFEMA.** Replace natural-disaster estimates and start decomposing climate resilience.

7. **BTS Noise Map.**

8. **FIA/NLCD tree/canopy data.**

9. **IPEDS/College Scorecard.** Make enrollment/counties completely reproducible.

10. **Housing.** Select one consistent Zillow/Redfin county metric.

11. **Academic medicine.** Formalize what qualifies and build an authoritative facility list.

12. **Homelessness.** Do last among the easier factors because geographic crosswalking makes it intrinsically messy.

13. **Outdoor recreation.** Build as a GIS factor rather than manually scoring counties.

14. **Party affiliation.** Either build a proper state-by-state registration pipeline or explicitly rename it as a partisan-vote proxy.

---

# 22. One important methodological improvement still missing

Once real data starts replacing estimates, the project should add **uncertainty/provenance**.

For every county-factor pair, ideally store:

```text
value
source
source vintage/year
method
direct vs derived
imputed?
confidence
coverage
```

Then we can eventually run sensitivity analyses such as:

```text
How often is County A top 10 if uncertain factors move within plausible bounds?
```

That will be much more informative than pretending every rank has equal precision.

The current runoff MCMC randomizes **which preference dimension eliminates a county**. It does **not** currently model **measurement uncertainty** in the factor values themselves.

That is a valuable future enhancement.

---

## Handoff bottom line

The project has successfully established the **21-factor framework, Excel structure, common ranking scale, county-expansion logic, and 100k randomized runoff algorithm**.

The remaining problem is primarily **data engineering, not ranking math**.

The next developer should stop refining hand estimates and build reproducible nationwide source pipelines. The first concrete raw-data bundle already available for that transition is the **2023 Census CBP + county population bundle**, which should immediately replace the current grocery/trades estimates. Census describes CBP as subnational industry data containing establishments, employment and payroll, which is exactly why it fits those two factors. ([Census.gov][1])

After that, EPA AQI, NOAA climate normals and U.S. Drought Monitor are the clearest high-return upgrades.

[1]: https://www.census.gov/data/developers/data-sets/cbp-zbp/cbp-api.html?utm_source=chatgpt.com "County Business Patterns (CBP) APIs"
[2]: https://www.bls.gov/oes/tables.htm?utm_source=chatgpt.com "Occupational Employment and Wage Statistics (OEWS) Tables : U.S. Bureau of Labor Statistics"
