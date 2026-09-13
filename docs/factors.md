# Factor dictionary

Directions reflect the inherited preference model. They are preferences, not
universal judgments. Every V1 factor below has a source adapter and BDD coverage;
the original workbook remains a comparison artifact rather than a validation
target.

| ID | Intended measurement | Better | Inputs and work remaining |
| --- | --- | --- | --- |
| `heat` | Expected days/year with daily maximum >=90°F | Lower | **Implemented NOAA adapter.** Daily normals and variability are interpolated from population-centre stations with explicit coverage checks. |
| `cold` | Expected days/year with daily maximum <50°F | Lower | **Implemented NOAA adapter.** This is daytime maximum, not minimum temperature; station coverage and missingness are retained. |
| `snowfall` | Annual snowfall in feet | Lower | **Implemented NOAA adapter.** Annual normals are converted from inches to feet and interpolated with a ten-year station-support rule. |
| `drought` | D1+ drought frequency | Lower | **Implemented source-only adapter.** USDM D1+ non-consecutive weeks ×7÷10 for the latest complete 2016-01-01–2026-01-01 window; minimum-weeks=0 preserves zero-frequency rows and missing/censored values remain missing. |
| `aqi` | Mean annualized AQI >=101 days/year | Lower | **Implemented CSV/ZIP adapter.** Sum four bad-day categories; divide by monitored days ×365.25, then mean over available years. No old-estimate imputation. |
| `walkability` | Population-weighted EPA NWI, index 1–20 | Higher | **Implemented CSV adapter.** Sum NatWalkInd × TotPop / sum valid TotPop. Original GDB extraction remains to be added and checked. |
| `transit` | County transit-access index | Higher | **Implemented DBF adapter.** EPA Trans45 source components are combined at block-group level and averaged by county; uncovered counties remain missing. No fallback band ordered by old workbook values. |
| `groceries` | Grocery availability adjusted for access | Higher | **Implemented CBP/USDA adapter.** CBP 2023 density is adjusted by bounded 2019 USDA access indicators, using average-rank national percentiles for ties; raw density remains distinguishable. |
| `tradespeople` | Specialty-trade employment adjusted by occupations | Higher | **Implemented CBP/OEWS adapter.** CBP 2023 NAICS 238 density × May 2025 OEWS NAICS 238000 selected-occupation share × bounded May 2025 metro occupation mix where EPA SLD maps a county to a CBSA, otherwise a state mix. Suppressed detailed occupations leave the share unavailable. Employer employment is not a count of available contractors. |
| `housing` | Three-bedroom ZHVI, USD at a fixed month | Lower | **Implemented CSV adapter.** Zillow Research county three-bedroom, single-family/condo, middle-tier, smoothed/seasonally adjusted series. One selected month is used for every county; missing values stay missing and no old scale or estimate fallback is used. |
| `hazard_burden` | FEMA NRI hazard burden/risk index | Lower | Implemented from FEMA NRI v1.20 source components and all-18-hazard frequency percentile; report raw components and do not call index values disaster counts. |
| `resilience` | FEMA-based resilience index | Higher | Implemented from FEMA NRI v1.20 resilience, vulnerability and climate-hazard components; no claim of future climate scenario modeling. |

The released catalog uses explicit units and source status for all twelve V1
factors. Deferred factors remain outside the pipeline until a source and formula
are approved.

## Implemented adapter limitations

AQI annualization assumes monitoring days represent the year. The adapter retains
the minimum monitored-day count and actual observed years per county. It does not
equalize different year coverage, impose a minimum-coverage cutoff, or claim
observed counts are true annual exposure. Those policies require validation.
Zero monitored days remain missing. Duplicate county/year rows fail.

Walkability excludes block groups with missing scores from numerator and
denominator, flags their count, and leaves counties with no valid positive
population missing. It gives zero-population block groups zero weight. The
archived script substituted a simple mean when an entire county had zero
population weight; that fallback was deliberately removed. Missing population currently fails input
validation and must be handled explicitly during source normalization.

## Deferred scope

Academic medical centers, college students, homelessness and noise were interim
proxies. Popular-vote closeness, party-affiliation distance, airport access,
outdoor recreation and trees were substantially estimated. None enters V1.

Preserved woodland is not one of the original 21 ranked factors. Its historical
formula combines estimated tree density and recreation scores. A future measure
requires an explicit protection definition and spatial forest/protected-land
intersection. State-level CNBC reconstruction is a separate research track.
