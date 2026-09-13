# Implementation sequence

## 1. Recover and pin inputs

Inventory `data/incoming/`, identify duplicate versions by hash, read the three
handoffs, and recover the ten factor scripts plus correction script. Record
source licenses, URLs, retrieval dates, releases and original filenames. Inspect
scripts before executing anything. Select the authoritative county universe and
explicit territorial scope. Resolve the Connecticut geography change.

## 2. Validate the first source-only adapters

Add reproducible extraction of NWI geodatabase fields into the CSV contract.
Verify population totals and county rollups against the source. Build reviewed
AQI name/FIPS mapping and audit unmatched source names. Decide monitoring coverage
and common-year policies. Compare directly measured legacy cells only; exclude
calibrated AQI imputations from the expected-output reference.

## 3. Port source-backed factors

The CBP, NOAA, USDA, OEWS, FEMA, Drought Monitor, EPA transit, and Zillow
three-bedroom ZHVI ports are complete. Each port has source fixtures,
field/sentinel handling, units, vintage checks, coverage QA, a red-phase BDD log,
and a real-data acceptance scenario. Do not substitute a new speculative
composite for an unavailable historical method.

## 4. Complete national QA and ranking

Run all twelve factors over the pinned national universe. Report measured,
derived, interpolated and missing shares separately. Define any source-only
fallbacks before enabling them. Benchmark and optimize runoff against the
reference engine, and compare multiple seeds (for example 42, 43 and 44).
Measure ranking stability separately from input uncertainty and missingness.

Historical workbooks provide diagnostic comparisons, not an equality target:
the factor count, coverage, units, cohort and imputation policies are changing.
Keep average-rank and randomized-runoff results side by side.

## 5. Review exports and later product work

Add optional Parquet and Excel review outputs after schemas stabilize. Excel
should reflect machine-readable results, provenance and QA. Then add GIS using
the same versioned county identifiers. V2 begins with source-backed politics;
CNBC-style metrics and protected woodland remain separate research workstreams.
