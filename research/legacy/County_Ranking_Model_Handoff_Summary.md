# County Ranking Model Handoff Summary

## Current state

The current working spreadsheet is:

`county_rankings_added_candidates_sourcefix_100k.xlsx`

This is the latest corrected workbook. It contains **439 counties**: the original 413-county universe plus 26 added candidate counties. It includes the full 21-factor ranking matrix, value matrix, average-rank calculation, and a 100,000-iteration randomized runoff/MCMC result.

The latest corrected top 5 are:

1. Berks, PA
2. Lucas, OH
3. St. Joseph, IN
4. Lorain, OH
5. Lackawanna, PA

Two added candidate counties landed in the top 100 in the latest corrected run:

* Lake, OH — runoff rank 87
* Somerset, NJ — runoff rank 98

The earlier file `county_rankings_added_candidates_spotchecked_100k.xlsx` should be treated as superseded because it manually overwrote some fields that already had source-backed or proxy-backed values. The corrected current file is `county_rankings_added_candidates_sourcefix_100k.xlsx`.

---

# What was done

## 1. Rebuilt many original modeled factors with source-backed data

The original workbook had 21 factor columns. Across the project, 12 of those were materially improved with direct or near-direct public datasets:

| Factor                           | Final source/method used                                                                                                |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 90°F+ days/year                  | NOAA daily temperature normals; estimated expected annual days using daily TMAX normals and standard deviations         |
| D1+ drought days/year            | U.S. Drought Monitor D1+ non-consecutive drought weeks, 2015–2025, annualized to days/year                              |
| Grocery stores per 10k residents | CBP 2023 NAICS 445110 establishments per capita, adjusted by USDA ERS Food Environment Atlas grocery-access variables   |
| Single-family housing cost       | Zillow county ZHVI, 3-bedroom SFR/condo middle-tier series, quantile-mapped back to the workbook’s `$ / sq ft` scale    |
| Walkability                      | EPA National Walkability Index, population-weighted from block group to county                                          |
| Public transportation            | EPA Access to Jobs and Workers via Transit, with a guardrail for counties missing GTFS/EPA transit coverage             |
| Future climate resilience        | FEMA National Risk Index resilience / vulnerability / hazard-risk composite                                             |
| Tradespeople per 1k residents    | CBP NAICS 238 specialty-trade employment per capita, adjusted with BLS OEWS selected trade-occupation mix               |
| Natural disasters per decade     | FEMA National Risk Index hazard/frequency/loss burden, quantile-mapped back to the workbook’s disaster-per-decade scale |
| Days below 50°F/year             | NOAA daily temperature normals; expected days where TMAX < 50°F                                                         |
| Annual snowfall                  | NOAA annual/seasonal multivariate snowfall normals, station-blended to county                                           |
| Bad AQI days/year                | EPA annual AQI by county, 2023–2024 average, using AQI ≥ 101 days annualized by valid AQI coverage                      |

---

## 2. Added proxy-backed improvements for several still-modeled factors

After the direct source passes, several still-modeled columns were improved using correlated source-backed data already collected. These are better than the original hand/model estimates, but should still be considered proxy-backed rather than fully solved.

| Factor                          | Proxy method used                                                                                                        | Reliability            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------- |
| Academic medical center density | CBP healthcare/hospital employment, CBP higher-ed signal, OEWS healthcare/technical occupation signal                    | Moderate proxy         |
| College students per capita     | CBP higher-education employment and related proxy signals                                                                | Weak-to-moderate proxy |
| Homelessness                    | Zillow housing cost, USDA poverty/food insecurity, transit/walkability, and socioeconomic pressure proxies               | Weak proxy             |
| Noise pollution                 | EPA walkability/transit density, CBP employment intensity, transportation/warehousing/manufacturing/construction proxies | Weak proxy             |

These were implemented in `update_proxy_reuse_and_rerun_mcmc.py`.

---

## 3. Added 26 candidate counties

The model was expanded from 413 to 439 counties by adding the counties from both the “highest-priority” and “high-upside with caveats” lists.

Added counties included examples such as:

* Montour, PA
* Lake, OH
* Westmoreland, PA
* Butler, PA
* Henrico, VA
* Hanover, VA
* Dubuque, IA
* Minnehaha, SD
* Brown, MN
* Cerro Gordo, IA
* Washington, PA
* Kanawha, WV
* Harrison, WV
* Lycoming, PA
* St. Johns, FL
* Fairfax city, VA
* Falls Church city, VA
* Fredericksburg city, VA
* Salem city, VA
* Colonial Heights city, VA
* Hunterdon, NJ
* Somerset, NJ
* Plymouth, MA
* Norfolk, MA
* Williamson, TN
* Oakland, MI

The first candidate-add pass was too mechanical and allowed some candidate weak fields to remain blank or over-penalized. A later spot-check overcorrected by manually overwriting some fields that already had data. The final source-fix pass restored source-backed/proxy-backed values where available and kept manual estimates only where no adequate source existed.

The final candidate-related script is:

`fix_candidate_source_backed_fields_and_rerun.py`

---

# Main scripts produced

Use these as the reproducibility trail. Some are superseded by later scripts, but they show the full evolution.

## Core source update scripts

* `update_walkability_and_rerun_mcmc.py`
* `update_transit_and_rerun_mcmc.py`
* `update_transit_guardrail_and_rerun_mcmc.py`
* `update_aqi_and_rerun_mcmc.py`
* `update_noaa_temperature_and_rerun_mcmc.py`
* `update_noaa_multivariate_and_rerun_mcmc.py`
* `update_drought_monitor_and_rerun_mcmc.py`
* `update_cbp_and_rerun_mcmc.py`
* `update_oews_trades_and_rerun_mcmc.py`
* `update_usda_food_environment_and_rerun_mcmc.py`
* `update_fema_nri_and_rerun_mcmc.py`
* `update_zillow_housing_and_rerun_mcmc.py`
* `update_proxy_reuse_and_rerun_mcmc.py`

## Candidate county scripts

* `add_candidate_counties_fast_rerun.py`
* `spot_check_candidate_weak_factors_and_rerun.py` — superseded; do not treat this as final
* `fix_candidate_source_backed_fields_and_rerun.py` — final candidate correction script

---

# Important modeling conventions

## Rank direction

All direct factor ranks use:

`1 = best`

Higher rank numbers are worse.

For negative factors such as housing cost, bad AQI days, drought days, disaster risk, homelessness, noise, hot days, cold days, and snowfall, lower raw value is generally better.

For positive factors such as walkability, grocery access, public transit, climate resilience, tradespeople, outdoor recreation, tree cover, college students, and academic medical center density, higher raw value is generally better.

## Avg Rank vs Avg-based rank

`Avg Rank` is the raw average of a county’s direct factor ranks.

`Avg-based rank` is the rank order produced by sorting counties by `Avg Rank`.

`Runoff rank` is separate. It comes from the 100,000-iteration randomized runoff/MCMC simulation.

## MCMC/runoff

The model uses a randomized runoff process:

1. Randomly cycles through the factor ranks.
2. On each factor, eliminates the currently worst remaining county.
3. Repeats until one county wins.
4. Runs this 100,000 times.
5. Counties are ranked by average elimination round, wins, Avg Rank, then tie-breakers.

The later scripts use an optimized version of this algorithm to avoid O(iterations × counties²) slowdowns.

## Quantile mapping

When a new source had a strong ordering signal but not the same unit as the existing workbook factor, the update generally:

1. Used the source to determine county ordering.
2. Quantile-mapped that ordering back onto the existing factor’s value scale.

This preserved workbook interpretability while replacing the old ordering with a better data-driven ordering.

Examples:

* Zillow ZHVI → existing `$ / sq ft` scale
* FEMA NRI disaster burden → existing “natural disasters per decade” scale
* FEMA climate/resilience composite → existing climate-resilience score scale
* NOAA/Drought Monitor intermediate drought proxy was later superseded by direct Drought Monitor annualized days

## Missing-data policy

Most scripts use this fallback order:

1. Direct FIPS match
2. Connecticut planning-region bridge where necessary
3. Same-state median or same-state calibration
4. Census-division median/calibration
5. National median/calibration
6. Preserve prior estimate only when a direct source is missing and the prior estimate is clearly the least-bad fallback

The Connecticut issue came up repeatedly because several newer federal datasets use Connecticut planning regions, while the workbook uses legacy Connecticut county names/FIPS.

---

# What is still weak / left to do

The largest remaining accuracy risk is concentrated in the factors that still lack direct high-quality county-level data.

## 1. Popular vote closeness

Current status: still mostly modeled/manual, especially for added counties.

Why weak:

* This can be measured directly from county election returns, but it has not yet been rebuilt from a canonical election dataset.
* The current values are likely directionally reasonable for many counties but not fully reproducible.

Recommended next source:

* MIT Election Data and Science Lab county presidential returns
* Dave Leip / county election returns if licensed/available
* State election office county returns

Recommended method:

* Use 2020 and 2024 presidential two-party margin.
* Possibly average or blend recent elections.
* Smaller margin = better if the goal is political competitiveness.

## 2. Party-affiliation proxy

Current status: still mostly modeled/manual.

Why weak:

* Voter registration by party is not consistently available or comparable across states.
* Presidential vote share is probably a better national proxy unless state-by-state registration data is collected.

Recommended method:

* Use normalized county presidential Democratic/Republican margin as the main national proxy.
* Optionally supplement with state voter registration only in states where reliable party-registration data exists.

## 3. Airport distance

Current status: still estimated/manual, especially for added counties.

Why weak:

* Existing data does not include a clean drive-time or airport-service dataset.
* Distance to nearest “international” airport can be misleading because some international airports have little practical service, while some non-international airports have strong commercial service.

Recommended next sources:

* FAA airport master records
* BTS/T-100 passenger enplanements
* OpenStreetMap or OSRM drive-time routing

Recommended method:

* Identify airports with meaningful scheduled passenger service.
* Compute county-population-weighted drive time to nearest service airport and nearest major/hub airport.
* Use drive time, not straight-line distance.

## 4. Outdoor recreation access

Current status: still modeled/manual, with no strong direct source imported.

Why weak:

* Outdoor recreation depends on trails, public land, parks, water access, mountains, beaches, and usable local recreation.
* Large remote public-land acreage is not the same as convenient recreation access.

Recommended next sources:

* PAD-US protected areas
* National Hydrography Dataset
* OpenStreetMap trails/parks
* Trust for Public Land ParkServe where available
* State/local park inventories

Recommended method:

* Compute population-weighted access to parks/trails/water/public lands.
* Separate “nearby everyday recreation” from “large destination public lands.”
* Use a capped score to avoid over-rewarding enormous but remote counties.

## 5. Trees per acre

Current status: still modeled/manual.

Why weak:

* Existing collected data does not directly measure canopy or forest cover.
* Manual estimates can be wrong in mixed farmland/forest counties, arid counties, and urban/suburban counties.

Recommended next sources:

* NLCD Tree Canopy Cover
* NLCD land cover forest classes
* USDA Forest Service FIA county summaries

Recommended method:

* Compute tree-canopy or forested land share by county.
* Consider using population-weighted canopy for urban/suburban counties, not just total acreage.

## 6. Homelessness

Current status: proxy-backed, but still weak.

Why weak:

* The current proxy uses housing cost, poverty, food insecurity, transit/walkability, and related signals.
* Actual homelessness data is usually reported by Continuum of Care, not always county.
* Visible/service-counted homelessness can be higher in counties with more shelters and services, not necessarily because underlying housing instability is worse.

Recommended next sources:

* HUD PIT and HIC data
* CoC-to-county crosswalks
* Local county/city PIT reports

Recommended method:

* Allocate CoC PIT counts to counties using shelter locations, population, poverty, renter burden, and local reports where available.
* Separate sheltered and unsheltered counts if possible.

## 7. Academic medical center density

Current status: proxy-backed, moderate but not direct.

Why weak:

* Healthcare employment is not the same as academic medical center presence.
* A true academic-medical score should identify teaching hospitals, residency programs, medical schools, research intensity, and tertiary/quaternary care.

Recommended next sources:

* AAMC teaching hospital lists
* ACGME residency/fellowship sites
* Liaison Committee on Medical Education medical schools/campuses
* NCI-designated cancer centers
* NIH/BRIMR funding by institution
* CMS hospital data for tertiary services

Recommended method:

* Geocode institutions.
* Score counties using in-county and nearby-drive-time access.
* Weight by teaching/research intensity, residency slots, hospital beds, and specialty services.

## 8. College students per capita

Current status: proxy-backed, but not direct.

Why weak:

* CBP higher-ed employment is only an indirect proxy.
* Enrollment may be in a different county than administrative employment.
* Online enrollment and multi-campus systems complicate measurement.

Recommended next sources:

* IPEDS campus-level enrollment
* College Scorecard
* Carnegie classifications

Recommended method:

* Use physical campus enrollment, not online-only enrollment.
* Assign campuses to county by geocoded location.
* Optionally weight nearby counties by drive time if the factor is intended to measure access rather than in-county student density.

## 9. Noise pollution

Current status: proxy-backed, weak.

Why weak:

* Current proxy uses urban density, transit, walkability, and employment/industrial intensity.
* It does not directly measure highway, rail, aviation, or freight noise.

Recommended next source:

* BTS National Transportation Noise Map

Recommended method:

* Use county-level or gridded exposure to estimate population-weighted noise burden.
* Include highway, aviation, rail, and possibly port/freight corridors.
* Lower noise = better.

---

# Factors that are improved but still worth future refinement

## Public transportation

Current source:

* EPA Access to Jobs and Workers via Transit

Remaining caveat:

* The EPA dataset is older and GTFS coverage is incomplete.
* The current method uses a guardrail so counties missing EPA/GTFS coverage rank below measured counties, while preserving old-model order among missing counties.

Future improvement:

* Use current GTFS feeds plus Census LEHD/LODES access-to-jobs calculations.

## Housing cost

Current source:

* Zillow ZHVI

Remaining caveat:

* The factor is labeled single-family `$ / sq ft`, but Zillow provided ZHVI, not true price per square foot.
* The current update uses Zillow ordering quantile-mapped back onto the old `$ / sq ft` scale.

Future improvement:

* Use Zillow or Redfin price-per-square-foot series if available at county level.
* Alternatively use ACS median home value plus ACS rooms/sq-ft proxies, though that is weaker.

## Future climate resilience

Current source:

* FEMA NRI

Remaining caveat:

* FEMA NRI is a strong structured hazard-risk baseline, but it is not a future climate projection model.
* It mixes expected annual loss, social vulnerability, and community resilience.

Future improvement:

* Add CMRA, First Street, NOAA climate projections, or downscaled future heat/flood/wildfire risk.

## Natural disasters

Current source:

* FEMA NRI

Remaining caveat:

* NRI is likely better than raw federal disaster declaration counts.
* However, it is still a model of expected annual loss/frequency, not an observed event history.

Future improvement:

* Optionally add OpenFEMA disaster declarations as a secondary historical-administrative signal, but do not use it alone because declarations are political/administrative.

## Tradespeople

Current source:

* CBP NAICS 238 plus OEWS occupation mix

Remaining caveat:

* CBP excludes some sole proprietors/nonemployers.
* OEWS is metro/state geography, not county-level.

Future improvement:

* Add Census Nonemployer Statistics for construction/trade NAICS.
* Add county-level ACS occupation data if precision is acceptable.

## Grocery access

Current source:

* CBP 2023 grocery establishments plus USDA Food Environment Atlas access variables

Remaining caveat:

* USDA grocery-access variables are older than the CBP 2023 store count.
* The current method keeps CBP as the current-count backbone and USDA as an access/proximity adjustment.

Future improvement:

* Use current SNAP retailer data or commercial grocery location data if available.

---

# Suggested next development priorities

## Highest value next fixes

1. Election returns for vote closeness and party proxy
2. Airport drive-time/service-access model
3. NLCD tree canopy / forest cover
4. IPEDS campus enrollment for college students
5. AAMC/ACGME/NCI/NIH medical-center score
6. BTS National Transportation Noise Map
7. HUD homelessness PIT/HIC with CoC-to-county allocation
8. PAD-US / OSM outdoor recreation access

## Why these matter

The model is now much less dependent on hand estimates than it was at the beginning. Most climate, environment, housing, grocery, trades, walkability, transit, disaster, and AQI columns have been replaced or heavily improved.

The remaining biggest error sources are no longer broad environmental data. They are the harder human/infrastructure/access factors where the model still relies on proxies or manual estimates:

* politics
* airports
* outdoor recreation
* tree cover
* homelessness
* academic medicine
* college students
* noise

Those should be the next handoff focus.

---

# Files the next developer should receive

At minimum:

## Current final workbook

* `county_rankings_added_candidates_sourcefix_100k.xlsx`

## Final/relevant scripts

* `fix_candidate_source_backed_fields_and_rerun.py`
* `update_proxy_reuse_and_rerun_mcmc.py`
* `update_zillow_housing_and_rerun_mcmc.py`
* `update_fema_nri_and_rerun_mcmc.py`
* `update_usda_food_environment_and_rerun_mcmc.py`
* `update_oews_trades_and_rerun_mcmc.py`
* `update_cbp_and_rerun_mcmc.py`
* `update_drought_monitor_and_rerun_mcmc.py`
* `update_noaa_multivariate_and_rerun_mcmc.py`
* `update_noaa_temperature_and_rerun_mcmc.py`
* `update_aqi_and_rerun_mcmc.py`
* `update_transit_guardrail_and_rerun_mcmc.py`
* `update_walkability_and_rerun_mcmc.py`

## Useful audit/rollup CSVs

* `added_candidate_sourcefix_rollup.csv`
* `proxy_reuse_county_rollup.csv`
* `zillow_housing_county_rollup.csv`
* `fema_nri_county_rollup.csv`
* `usda_food_environment_county_rollup.csv`
* `oews_trades_county_rollup.csv`
* `cbp_county_rollup.csv`
* `drought_monitor_county_rollup.csv`
* `noaa_multivariate_county_rollup.csv`
* `noaa_temperature_county_rollup.csv`
* `epa_aqi_county_rollup.csv`
* `epa_transit_county_rollup_guardrailed.csv`
* `epa_walkability_county_rollup.csv`

## Source datasets

The next developer should also receive the original source archives/files used by the scripts, including:

* EPA Walkability Index ZIP and methodology PDF
* EPA SLD Transit DBF ZIP and user guide PDF
* EPA annual AQI by county ZIPs for 2023 and 2024
* NOAA daily temperature normals archive
* NOAA annual/seasonal multivariate normals archive
* U.S. Drought Monitor export CSV
* CBP 2023 county file and supporting references
* Census 2023 population estimate file
* BLS OEWS metro/state/all/industry ZIPs
* USDA ERS Food Environment Atlas files
* FEMA NRI county table ZIP, metadata, glossary, and data dictionary
* Zillow county ZHVI CSV

---

# Final caution

The current workbook is much stronger than the original and much more source-backed. But it should not be treated as finished. The biggest remaining model risk is concentrated in the weak/proxy/manual factors, especially politics, airport access, outdoor recreation, tree cover, homelessness, academic medicine, college students, and noise.

The next developer should focus on replacing those with direct datasets before adding many more counties or tuning the MCMC behavior.
