# County Ranker Project — Developer Handoff

## 1. Project goal

The project ranks U.S. counties as potential retirement/location candidates using 21 quality-of-life factors and a randomized runoff ranking algorithm.

The project began as an Excel workbook plus a growing sequence of Python scripts that progressively replaced modeled/manual factor values with public datasets.

The next phase is to stop extending that script chain and turn the work into a proper, reproducible Python application.

The long-term roadmap is:

* **v1:** produce the 12 already-real-data-backed factors for every U.S. county/county-equivalent, using only downloaded source data.
* **v2+:** replace the remaining 9 weak/proxy/manual factors with defensible real datasets.
* **Later versions:** add configurable preferences/weights, analytical APIs, and eventually a GIS webapp showing factor and composite “heat” geographically.

---

# 2. Current workbook state

The latest corrected workbook is:

`county_rankings_added_candidates_sourcefix_100k.xlsx`

It contains:

* 439 counties

  * 413 counties from the original analysis universe
  * 26 subsequently added candidate counties
* 21 ranking factors
* Rank Matrix
* Value Matrix
* Top 30
* Result Comparison
* QA
* factor/update audit sheets
* 100,000-iteration randomized runoff results

The latest corrected top five were:

1. Berks, PA
2. Lucas, OH
3. St. Joseph, IN
4. Lorain, OH
5. Lackawanna, PA

The source-fix work corrected an earlier candidate “spot-check” pass that had overwritten some fields for which source-backed or proxy-backed values already existed.

The corrected rule is:

**Do not replace a source-derived value with a manually reasoned estimate simply because the source is imperfect.**

---

# 3. What has been accomplished

## 3.1 Twelve factors now have substantial real-data backing

The strongest existing work is concentrated in these factors:

### 1. 90°F+ days/year

**Primary source:** NOAA/NCEI daily temperature normals.

Current logic:

* Read daily TMAX normals.
* Read daily TMAX standard deviations.
* Model the probability that each day exceeds 90°F.
* Sum those probabilities into expected annual 90°F+ days.
* Blend nearby NOAA stations to county population-weighted centroids.

This is materially better than simply counting days whose normal temperature exceeds 90°F.

---

### 2. Days below 50°F/year

**Primary source:** same NOAA daily-temperature workflow.

Current logic:

* Estimate probability each day's TMAX is below 50°F.
* Sum expected days annually.
* Use the same station interpolation system as the 90°F factor.

These two factors should eventually live in one reusable NOAA temperature module.

---

### 3. Annual snowfall

**Primary source:** NOAA/NCEI annual/seasonal multivariate climate normals.

Current logic:

* Use `ANN-SNOW-NORMAL`.
* Blend nearby station values geographically.
* Convert inches to feet.

Earlier code occasionally relied on calibrated old estimates for missing coverage; that must be removed in v1.

---

### 4. D1+ drought days/year

**Primary source:** U.S. Drought Monitor.

Current logic superseded an earlier NOAA precipitation-based drought proxy.

Method:

* use D1+ non-consecutive drought weeks over a defined multi-year interval
* annualize:

`weeks × 7 / number_of_years`

* bridge Connecticut's newer planning-region geography where necessary

This should remain the authoritative drought factor.

---

### 5. Bad AQI days/year

**Primary source:** EPA annual AQI-by-county files.

Current definition of a “bad AQI day”:

AQI ≥ 101, represented by:

* Unhealthy for Sensitive Groups
* Unhealthy
* Very Unhealthy
* Hazardous

The workflow annualizes observed counts according to the number of days with valid AQI coverage.

Current scripts sometimes fall back using old modeled AQI estimates. That behavior must disappear in v1.

---

### 6. Walkability

**Primary source:** EPA National Walkability Index.

Method:

* read EPA block-group records
* roll `NatWalkInd` up to county
* population-weight using `TotPop`

This is one of the cleaner factor implementations and should be among the first modules migrated into the new application.

---

### 7. Public transportation

**Primary source:** EPA Access to Jobs and Workers via Transit / SLD transit dataset.

Current composite uses:

* Transit Access Index
* percent of jobs accessible by transit
* percent of population accessible by transit
* percent of workers accessible by transit

with approximately:

* 50% Transit Access Index
* 30% jobs
* 10% population
* 10% workers

A guardrail was added so counties missing EPA/GTFS coverage were not incorrectly rewarded.

The current fallback still partly relies on prior values in some places. v1 must replace this with a purely source-derived missing-coverage policy.

---

### 8. Grocery stores per 10k residents

This became a two-source factor.

#### County backbone

**Census County Business Patterns 2023**

NAICS:

`445110` — Grocery Stores

Compute:

`establishments / population × 10,000`

#### Access refinement

**USDA ERS Food Environment Atlas**

Used variables concerning:

* low-access population
* low-income low-access population
* households without vehicles with low grocery access

A bounded access penalty modifies the CBP grocery count.

This preserves actual county grocery establishment density while incorporating practical grocery access.

---

### 9. Tradespeople per 1k residents

Another multi-source factor.

#### County backbone

**Census County Business Patterns**

NAICS `238///` — Specialty Trade Contractors employment.

#### Occupational refinement

**BLS OEWS**

Selected occupations include:

* electricians
* plumbers
* HVAC technicians
* roofers
* carpenters
* painters
* construction laborers
* industrial machinery mechanics
* maintenance/repair workers

OEWS metro/nonmetro or state occupation mix adjusts the county CBP backbone within guardrails.

---

### 10. Future climate resilience

**Primary source:** FEMA National Risk Index.

The current implementation combines information including:

* community resilience
* inverse climate-hazard risk
* inverse adjusted expected annual loss
* inverse social vulnerability

This is fundamentally source-backed.

---

### 11. Natural-disaster burden

**Primary source:** FEMA National Risk Index.

The current implementation derives hazard burden from measures including:

* Expected Annual Loss
* adjusted expected-loss rates
* hazard annualized frequency

Important architectural correction for v1:

The old workbook calls this “natural disasters per decade,” but FEMA NRI does not literally provide that value.

v1 should therefore output a clearly named **FEMA hazard-burden/risk score**, rather than quantile-mapping FEMA scores back onto a fake “disasters per decade” unit.

---

### 12. Housing cost

**Primary source:** Zillow county ZHVI.

The existing implementation uses a county-level 3-bedroom middle-tier ZHVI series.

Important architectural correction:

The spreadsheet currently labels this approximately as single-family `$ / sq ft`, but ZHVI is not a square-foot price measure.

The old script quantile-mapped ZHVI ordering back onto the spreadsheet's old `$ / sq ft` distribution.

That is no longer acceptable.

v1 should output the actual source-native Zillow housing metric, for example:

`Zillow 3-bedroom ZHVI`

and rank lower cost as better.

---

# 4. Factors that still have poor data backing

There are nine factors that should be considered unfinished from a data-quality perspective.

They fall into two groups.

---

# 5. Four factors currently using data-backed proxies

These are better than arbitrary estimates, but should still be replaced with direct datasets.

## 5.1 Academic medical center density

Current approximation uses signals such as:

* hospital employment
* higher-education employment
* healthcare/technical occupation data

This is only an indirect proxy.

### Better future approach

Build an institution-level score from datasets such as:

* AAMC teaching hospitals
* ACGME residency/fellowship sites
* LCME medical schools
* NCI cancer centers
* CMS hospital characteristics
* NIH research funding

The final factor should measure access to real academic/tertiary medicine rather than generic healthcare employment.

**Priority:** high.

---

## 5.2 College students per capita

Current approximation uses higher-education employment and related economic signals.

This is an imperfect proxy for actual student population.

### Better future approach

Use IPEDS enrollment data.

Requirements:

* geocode actual campuses
* associate physical campus enrollment with counties
* avoid online-only enrollment distortion
* optionally distinguish undergraduate/graduate populations

**Priority:** high-to-medium.

---

## 5.3 Homelessness

Current approximation combines source-derived signals such as:

* Zillow housing cost
* USDA poverty
* deep poverty
* SNAP
* food insecurity
* walkability
* transit

The resulting number is still a socioeconomic-pressure proxy, not observed homelessness.

### Better future approach

Use:

* HUD Point-in-Time counts
* HUD Housing Inventory Count
* CoC geography crosswalks
* local PIT reports where useful

The difficult part will be allocating CoC-level counts to individual counties.

**Priority:** medium.

---

## 5.4 Noise pollution

Current approximation uses activity/urban-intensity signals including:

* EPA walkability
* transit
* employment intensity
* transportation/industrial activity

It is a proxy for likely noise rather than noise exposure itself.

### Better future approach

Use the BTS National Transportation Noise Map.

Derive population-weighted exposure to:

* road noise
* aviation noise
* rail noise
* other transportation noise where available

**Priority:** medium.

---

# 6. Five factors still substantially estimated/manual

These are the weakest factors in the current model.

## 6.1 Popular vote closeness

Current values remain manually/model derived.

### Recommended source

MIT Election Data and Science Lab county presidential returns, including 2020 and 2024.

Possible factor:

`abs(two_party_dem_share - 0.50)`

Smaller is better.

Could blend multiple elections to avoid a single-election anomaly.

**Recommended first v2 factor.**

---

## 6.2 Party-affiliation proxy distance

Also currently modeled/manual.

The same election-return module could replace this factor.

Possible approach:

* define the user's target partisan balance
* compute county two-party presidential share
* measure absolute distance from target

One election-data implementation can therefore replace **two weak factors at once**.

**Recommended first v2 work item together with popular-vote closeness.**

---

## 6.3 Airport access

Current values are estimated distances to “international airports.”

That definition itself should be improved.

### Better future approach

Use:

* FAA airport records
* BTS/T-100 or passenger-enplanement data
* road routing via OSRM/OpenStreetMap or another routing system

Do not simply reward an airport because “International” appears in its name.

Better metric:

* drive time to nearest airport with meaningful scheduled commercial service
* optionally a separate drive time to nearest major airport/hub

This is an important GIS factor.

**Priority:** high after politics.

---

## 6.4 Outdoor recreation

Current values remain manually/model estimated.

### Better future approach

Combine GIS sources such as:

* PAD-US protected areas
* OpenStreetMap trails and parks
* National Hydrography Dataset
* state/local park inventories
* possibly ParkServe for urban park access

The factor should distinguish:

* everyday recreation accessibility
* destination/outdoor recreation

Avoid simply scoring counties by raw public-land acreage, which would disproportionately favor huge rural western counties.

**Priority:** medium/high.

---

## 6.5 Trees / woodland

Current values remain estimated.

### Better future approach

Use:

* NLCD Tree Canopy Cover
* NLCD forest land-cover classes
* possibly USDA FIA county summaries

This could eventually support multiple GIS measures:

* county forest percentage
* tree-canopy percentage
* population-weighted residential canopy
* preserved woodland percentage

**Priority:** high because the data is relatively accessible and GIS-friendly.

---

# 7. Current scripts and what they should be used for

The current scripts should be treated as **reference implementations**, not as the architecture for the next version.

## `update_walkability_and_rerun_mcmc.py`

Reuse:

* EPA data reader
* population-weighted aggregation
* FIPS normalization
* county-name normalization

Do not reuse:

* workbook mutation
* embedded ranking/MCMC code

---

## `update_transit_guardrail_and_rerun_mcmc.py`

Reuse:

* EPA transit DBF parsing
* transit component mapping
* composite formula
* coverage-detection concepts

Rewrite:

* fallback policy so it never depends on old spreadsheet values

---

## `update_aqi_and_rerun_mcmc.py`

Reuse:

* annual AQI ZIP parsing
* AQI ≥101 definition
* valid-day annualization
* multi-year aggregation

Replace:

* old-model-calibrated imputation

Use only source-derived state/division/national fallback in v1.

---

## `update_noaa_temperature_and_rerun_mcmc.py`

Reuse:

* station parsing
* expected exceedance calculations
* station blending
* geospatial centroid logic

Remove:

* old-value-calibrated fallback

---

## `update_noaa_multivariate_and_rerun_mcmc.py`

Reuse:

* snowfall source parsing
* station blending
* geometry utilities

Do not reuse its NOAA precipitation drought proxy.

The U.S. Drought Monitor implementation superseded that approach.

---

## `update_drought_monitor_and_rerun_mcmc.py`

Reuse:

* Drought Monitor parsing
* annualization formula
* CT geography bridge

Replace:

* old-estimate fallback

---

## `update_cbp_and_rerun_mcmc.py`

Reuse:

* Census CBP parsing
* grocery NAICS handling
* specialty-trade NAICS handling
* Census population denominators
* missing-industry-row interpretation
* CT bridge

This should become reusable CBP infrastructure rather than a factor-specific script.

---

## `update_oews_trades_and_rerun_mcmc.py`

Reuse:

* selected trade occupations
* national industry occupational composition
* metro/state fallback structure
* OEWS guardrails

Combine with CBP in one trades factor pipeline.

---

## `update_usda_food_environment_and_rerun_mcmc.py`

Reuse:

* Food Environment Atlas ingestion
* grocery-access variables
* bounded access adjustment

Combine with CBP in one grocery factor pipeline.

---

## `update_fema_nri_and_rerun_mcmc.py`

Reuse:

* FEMA NRI ingestion
* resilience formula
* hazard components
* CT geography bridge

Change:

* do not quantile-map disaster score onto old spreadsheet “disasters per decade” units

Use a source-native hazard score.

---

## `update_zillow_housing_and_rerun_mcmc.py`

Reuse:

* Zillow CSV parsing
* county matching
* latest valid observation handling

Change:

* no quantile mapping onto old `$ / sq ft` values
* no old-estimate calibration

Use Zillow ZHVI directly.

---

## `update_proxy_reuse_and_rerun_mcmc.py`

Do **not** migrate this into v1 factors.

Keep it only as documentation of the interim proxies for:

* academic medicine
* college students
* homelessness
* noise

Those should eventually be replaced in v2+.

---

## `fix_candidate_source_backed_fields_and_rerun.py`

Use primarily as a project-history/control reference.

Useful pieces:

* authoritative factor/value/rank naming
* rank directions
* record of which fields were still genuinely weak
* lessons about not overwriting source-backed fields with manual estimates

Do not make candidate-only logic part of the new architecture.

---

# 8. The major architectural decision made in this conversation

The next version should **not** reproduce the existing script chain.

Instead, build a proper GitHub Python project.

Recommended shape:

```text
county-ranker/
  pyproject.toml
  README.md
  AGENTS.md

  src/
    county_ranker/
      cli.py
      config.py
      schema.py

      geography/
      sources/
      factors/
      ranking/
      runoff/
      qa/
      export/

  configs/
  tests/

  data/
    raw/
    interim/
    processed/
    outputs/
```

---

# 9. Critical v1 rule: no dependency on old spreadsheet estimates

This was the most important requirement established at the end of the conversation.

v1 may use the old spreadsheet for comparison only.

It must never use old workbook values to compute new factor values.

Specifically forbidden:

* old modeled factor values
* old manual estimates
* candidate peer estimates
* quantile mapping to old workbook value distributions
* calibrated measured/old ratios
* state/division fallback derived from old values
* “preserve old value” logic

All v1 factor values must derive solely from the downloaded real-data input files.

---

# 10. Source-only fallback rules

Missing source data is unavoidable, particularly for nationwide coverage.

Permitted fallbacks include:

* nearest measured station
* spatial interpolation
* same-source state median
* same-source Census-division median
* same-source national median
* a documented source-specific missing-coverage band
* zero when source documentation indicates absence of a row represents zero

Every fallback must be recorded.

Suggested metadata:

* `source_status`
* `coverage_status`
* `fallback_method`
* `source_file`
* `source_vintage`
* `qa_flags`

The pipeline should make it possible to distinguish immediately between:

* direct source measurement
* spatial interpolation
* regional same-source imputation
* structural zero
* unavailable source coverage

---

# 11. v1 target

v1 should compute only the 12 solid source-backed factors, but compute them for **every U.S. county/county-equivalent**, rather than the current curated 439-county universe.

The county universe should itself come from a real source such as Census county/FIPS/population data.

The old workbook must not define the national county universe.

---

# 12. v1 outputs

Primary machine-readable output should be normalized data, not Excel.

Recommended files:

```text
counties.parquet
factor_values.parquet
ranks.parquet
runoff.parquet
source_manifest.json
qa.json
factor_audits/*.parquet
```

CSV equivalents should also be generated for convenient inspection.

Excel should remain as a generated review artifact:

`county_rankings_v1_source_only.xlsx`

Suggested sheets:

* Rank Matrix
* Value Matrix
* Top 30
* Runoff Simulation
* QA Checks
* Sources & Methodology
* Factor Coverage Summary
* factor-specific audit sheets

---

# 13. Shared functionality to extract from the script pile

A lot of code is duplicated across the current scripts.

This should be centralized early.

## Geography

Create shared functionality for:

* FIPS normalization
* county-name normalization
* state mapping
* county-equivalent handling
* Connecticut planning-region crosswalk
* county centroids
* population-weighted centroids
* CBSA mapping

---

## Source management

Create a source manifest such as `sources.yaml`.

For every source record:

* provider
* dataset
* local path
* vintage
* checksum
* geography
* variables used
* factors affected
* required/optional
* acquisition notes

The initial application should run entirely from local downloaded files.

No live web dependency should be necessary to reproduce a run.

---

## Factor interface

Each factor should behave approximately like:

```python
class Factor:
    factor_id
    display_name
    unit
    rank_direction
    required_sources

    def build(context):
        ...

    def qa(result):
        ...
```

Factors should return normalized records, not edit Excel directly.

---

## Ranking

Centralize:

* tie-aware ranking
* higher/lower direction
* average rank
* average-based rank

---

## Randomized runoff

Centralize the existing 100k-run algorithm.

Requirements:

* deterministic with fixed seed
* configurable iteration count
* shared implementation
* tests verifying:

  * wins sum to iterations
  * win rates sum to 1
  * same seed/input produces same result

---

## QA

Create centralized QA instead of per-script ad hoc checks.

Track at least:

* county count
* duplicate FIPS
* factor count
* missing values
* direct-source coverage
* fallback rate
* source vintage
* extreme interpolation distances
* rank validity
* runoff integrity

---

# 14. Suggested implementation order for the new developer

## Phase 1 — Project scaffolding

Create:

* GitHub repository
* proper Python package
* `pyproject.toml`
* dependency lock
* CLI
* test framework
* CI
* `AGENTS.md`

Do not migrate all factor logic immediately.

---

## Phase 2 — Core schemas and county universe

Build:

* national county table
* FIPS utilities
* factor result schema
* source manifest
* QA result schema

The application should understand all U.S. counties before working on rankings.

---

## Phase 3 — Ranking and runoff extraction

Move the common ranking/MCMC code into standalone tested packages.

This removes one of the largest duplicated pieces of the current scripts.

---

## Phase 4 — First factor migration

Start with EPA Walkability because it is relatively clean:

input source → block groups → county aggregation → factor output → QA.

Use it to validate the plugin architecture.

---

## Phase 5 — Migrate remaining v1 factors

Recommended order:

1. Walkability
2. Transit
3. AQI
4. NOAA temperature — both factors
5. NOAA snowfall
6. U.S. Drought Monitor
7. CBP shared infrastructure
8. Grocery + USDA adjustment
9. Trades + OEWS adjustment
10. FEMA NRI — both factors
11. Zillow

At each migration:

* eliminate old workbook dependence
* add tests
* add audit output
* validate nationwide coverage

---

## Phase 6 — National run

Run all twelve factors for every county.

Produce coverage report.

Do not silently invent values to achieve 100% completeness.

Any source-only fallback should be visible and auditable.

---

## Phase 7 — Export

Once normalized outputs are trusted:

* build ranks
* run MCMC
* generate Excel
* generate trust report

Excel export should be one of the final pipeline steps.

---

# 15. What should be done after v1

Once the 12-factor source-only national pipeline is reliable, work through the remaining nine factors.

Recommended sequence:

### 1. Politics bundle

Implement together:

* popular-vote closeness
* party-affiliation distance

Use county presidential election returns.

This replaces two weak factors with one source ingestion system.

### 2. Airport access

Important and relatively tractable GIS factor.

Use scheduled commercial-service data plus drive-time routing.

### 3. Tree canopy / woodland

Good GIS dataset availability and useful for the eventual web map.

### 4. College students

Use IPEDS.

### 5. Academic medicine

Institution-level academic/tertiary healthcare model.

### 6. Noise

Use BTS transportation noise data.

### 7. Homelessness

Use HUD PIT/HIC with explicit CoC-to-county allocation.

### 8. Outdoor recreation

Likely the most complicated GIS composite because the concept itself requires careful definition.

---

# 16. Future webapp/GIS direction

The final architecture should anticipate a map-based frontend.

Desired future capability:

* county choropleth for any factor
* composite desirability heatmap
* factor toggles
* customizable weights
* filters
* county comparison
* uncertainty/source-quality display
* click county for detailed profile
* identify geographic clusters rather than just ranked county lists

Because of this, processed outputs should eventually support:

* GeoParquet
* PostGIS
* GeoJSON/PMTiles where appropriate
* spatial overlays
* raster zonal statistics
* population-weighted GIS analysis

Do not hard-code the domain so tightly to U.S. counties that future non-U.S. administrative areas become impossible.

---

# 17. Main technical debt to avoid carrying forward

Do not reproduce these patterns from the current codebase:

* one script per sequential workbook update
* input workbook → modify one factor → write next workbook
* repeated MCMC code
* repeated Excel formatting code
* repeated FIPS normalization
* repeated state/division maps
* hard-coded `/mnt/data` locations
* factor logic coupled to workbook cells
* values mapped onto fake historical units
* old estimates used as fallback truth
* manually curated county universe
* candidate-specific branches inside core factor code

The scripts contain useful data-engineering logic, but their orchestration architecture should be discarded.

---

# 18. Key conceptual cleanup needed in v1

Three current factor labels deserve particular attention.

## Housing

Old:

`Est. single-family $/sq ft`

v1:

Use actual Zillow ZHVI units/naming.

---

## Natural disasters

Old:

`Est. natural disasters / decade`

v1:

Use a clearly named FEMA hazard-burden/risk score unless a true event-frequency dataset is introduced.

---

## Transit missingness

Old behavior partially ordered unmeasured counties using old estimates.

v1:

Use only EPA/source-derived coverage information and explicit fallback status.

---

# 19. Definition of v1 completion

v1 is complete when:

1. Repository installs from a clean clone.
2. Pipeline runs from local downloaded source files.
3. National county universe comes from source data.
4. All 12 v1 factors are produced nationwide.
5. No factor reads old spreadsheet values.
6. No factor quantile-maps onto an old spreadsheet distribution.
7. Every non-direct value has a documented source-only fallback.
8. Every value has provenance.
9. Ranking is centralized and tested.
10. Runoff is centralized, deterministic, and tested.
11. CSV/Parquet outputs are generated.
12. Excel is generated from normalized output.
13. QA/trust report reports direct vs fallback coverage.
14. The architecture makes adding v2 factors straightforward.

---

# 20. Most important takeaway for the new developer

The existing scripts are a **research prototype and source of proven extraction/transformation logic**.

They are not the architecture to preserve.

The new application's first job is to reproduce the strongest twelve factors nationwide from real input data alone.

Only after that foundation is trustworthy should the remaining nine weaker factors be replaced and the project expanded into the GIS/web application.
