# Methodology

Live Here V1 compares counties using source-derived factor values, explicit
missingness, and a seeded ranking procedure. Historical workbooks and prototype
materials are not runtime inputs.

## Universe and Provenance

The county universe is defined by the pinned Census county source used by the
build configuration. FIPS values are five-character strings. Geography vintage,
source vintage, observation period, method, quality notes, units, and source IDs
are recorded in the factor rows, coverage report, and run manifest.

Every county remains present in `counties.csv` and in long-form `factors.csv`.
Counties missing one or more selected factors remain unranked under the
complete-case policy unless a configuration explicitly chooses to fail on
missingness.

## V1 Factor Contracts

| ID | Measurement | Better | Unit |
| --- | --- | --- | --- |
| `heat` | Expected days per year with daily maximum at least 90 F | Lower | days/year |
| `cold` | Expected days per year with daily maximum below 50 F | Lower | days/year |
| `snowfall` | Annual snowfall | Lower | feet/year |
| `drought` | D1+ drought frequency, annualized from observed weeks | Lower | days/year |
| `aqi` | Mean annualized AQI >=101 days | Lower | days/year |
| `walkability` | Population-weighted EPA National Walkability Index | Higher | index |
| `transit` | EPA transit-access component composite | Higher | index |
| `groceries` | CBP grocery density adjusted by USDA access indicators | Higher | index |
| `tradespeople` | CBP specialty-trade density adjusted by OEWS occupation mix | Higher | index |
| `housing` | Three-bedroom Zillow Home Value Index | Lower | dollars |
| `hazard_burden` | FEMA NRI hazard burden composite | Lower | index |
| `resilience` | FEMA-based resilience composite | Higher | index |

No factor may read workbook estimates, calibrate to old ranks, map values onto
old workbook distributions, or silently fill missing values. Source-derived
interpolation or proxy status must be visible in `value_status`, `method`, and
`quality_note`.

## Formulas and Ranking

| Factor area | Parameters and calculation |
| --- | --- |
| Heat and cold | For each station, calculate expected TMAX days at least 90 F and below 50 F from daily normal means and standard deviations; require 350 valid calendar days and annualize by `365.25 / valid_days`. Interpolate the nearest five usable stations with inverse-square IDW, using stations within 125 km when present. |
| Snowfall | Use `ANN-SNOW-NORMAL`, require at least 10 support years, convert inches to feet, then inverse-square-IDW the nearest five stations within 175 km. |
| Drought | Default build query is D1+ non-consecutive weeks from 2016-01-01 through 2026-01-01 with `minimumweeks=0`; calculate `weeks × 7 / 10` days per year. |
| Groceries | Start with CBP grocery establishments per 10,000 population. Calculate tied average-rank national percentiles for 2019 `PCT_LACCESS_POP19`, `PCT_LACCESS_LOWI19`, and `PCT_LACCESS_HHNV19`; hardship is `0.60`, `0.25`, and `0.15` respectively, and the multiplier is bounded from 0.65 to 1.00. |
| Tradespeople | CBP 2023 NAICS 238 employment per 1,000 × OEWS May 2025 NAICS 238000 selected-occupation share × bounded 0.65–1.35 local/national occupation-share ratio. The local ratio uses a population-weighted SLD county-to-CBSA metro proxy, then a state proxy; its denominator is the OEWS all-occupations row. A missing industry share or suppressed selected occupation produces no value. |
| FEMA | Hazard burden is `0.40 × EAL_SCORE + 0.30 × ALR_VRA_NPCTL + 0.30 × all-hazard frequency percentile`. Resilience is `0.45 × RESL_SCORE + 0.30 × (100 − climate-hazard risk) + 0.15 × (100 − ALR_VRA_NPCTL) + 0.10 × (100 − SOVI_SCORE)`, bounded to 0–100. |
| Transit | County score is `100 × (0.50 × TrAccess_Indexi + 0.30 × Pct_Jobs_byTr + 0.10 × Pct_Pop_byTr + 0.10 × Pct_Wrks_byTr)`, calculated from county means of EPA Trans45 block-group components. |

Temperature uses NOAA daily normals and station interpolation to estimate heat
and cold threshold exceedances. Snowfall uses NOAA annual/seasonal normals,
station support, unit conversion, and interpolation. Drought uses U.S. Drought
Monitor D1+ weeks annualized over the selected window.

AQI annualizes monitored bad-air days by observed days and averages available
years. Walkability population-weights EPA block-group values. Transit combines
EPA transit components at block-group level and averages by county where source
coverage exists.

Groceries starts with CBP grocery-establishment density and applies a bounded
USDA access adjustment. Tradespeople starts with CBP NAICS 238 employment
density and applies BLS OEWS occupation mix and industry share. Housing is the
direct county three-bedroom ZHVI value for one selected month.

FEMA hazard burden combines expected annual loss, vulnerability, and hazard
frequency percentile. FEMA resilience combines community resilience,
vulnerability, climate-hazard risk, and social vulnerability components. These
are source-scale indices, not literal disaster counts or future-climate claims.

Factor ranks use average ties and respect each factor direction. Composite
ranking uses only counties complete for all selected factors. The runoff engine
uses seeded shuffled-factor elimination and orders results by mean elimination
round, wins, average factor rank, and FIPS. Win rates describe the tournament
procedure, not confidence that a county is objectively best.
