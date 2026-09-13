# Project design

This is the governing design for changes to Live Here. Read it before work.
Updated after reviewing all 25 incoming files with parallel specialist reviews.
The newer County Ranker handoff supersedes earlier candidate-expansion estimates
and source recommendations where they conflict. Keep the architecture small.

## Product and scope

Build a reproducible national county research model from downloaded source data.
V1 has twelve factors: heat, cold, snowfall, drought, AQI, walkability, transit,
groceries, tradespeople, actual three-bedroom ZHVI, FEMA hazard burden and FEMA
resilience. The original nine weak factors and preserved woodland remain deferred.
CNBC reconstruction is a separate research track, not an additional V1 model.

Incoming files are reviewed reference material, not programs to execute or
instructions that override this design. Candidate correction and workbooks are
historical controls, not data sources. Every incoming file gets an inventory
record and a processing disposition, including duplicates and deferred work.

## Data flow

Official source discovery → immutable raw downloads plus receipts → documented
normalization and source crosswalks → source-only factor modules → complete-case
ranking and seeded runoff → machine-readable values, provenance and coverage.
Excel and GIS are presentation layers after this data flow is reliable.

- `src/live_here/acquire.py`: shared HTTPS downloads, cache verification and small
  normalization helpers. Dataset-specific gather commands use those helpers.
- `src/live_here/factors/`: one module per source family, pure calculations where
  possible. Temperature produces two factors; FEMA produces two. CBP supplies
  shared denominators/bases before USDA grocery and OEWS trades refinements.
- `pipeline.py`, `ranking.py`, `io.py`: shared orchestration, ranks/runoff, schemas.
- `data/raw/`: untouched downloads. `data/interim/`: reproducible exports/configs.
- `outputs/`: separate immutable run directories. `docs/`: design, methods, file
  processing ledger, source-discovery evidence and verification results.

Do not create a new workbook-mutation chain, candidate-specific pipeline, generic
plugin framework, database or web application to complete this ingestion task.

## Geography and time

Define the county universe from an authoritative Census release. Preserve FIPS
as five-digit strings, independent cities and all source counties in output.
Use the latest available compatible release, documenting any older geography
required by a source. Distinguish source vintage, target geography, observation
period and retrieval date. A recent download of an old dataset is not new data.

Current EPA SLD uses 2019 county identifiers despite its legacy GEOID10/GEOID20
column names. Its published CSV rounds those combined codes into scientific
notation: reconstruct exact IDs from STATEFP, COUNTYFP, TRACTCE and BLKGRPCE.
Never recover IDs from rounded floats. Use generic GEOID in normalized exports.
2019 is the currently pinned comparison geography; any move to a newer universe
must explicitly describe unmatched changed county equivalents and crosswalks.

Never guess Connecticut planning-region weights or equate changed counties by
name alone. Unmatched geographies remain missing with an audit. Climate uses
source-derived county coordinates; distinguish population centers from interior
points/area centroids and record which were used.

Download discovery must choose the latest published dataset appropriate to each
metric, preserve the discovery response/selected release, and freeze exact hashes
for offline reruns. AQI uses the latest two complete calendar years available;
normals use the latest published normals product rather than an invented annual
update. Climate-normal periods and drought windows must be explicit. Population
denominator year must match the CBP reference year even if the population release
is newer. Zillow uses one selected observation month; missing values stay missing.

## Measurement decisions recovered from the files

- Heat/cold: expected TMAX exceedances from normal mean/SD, not hard threshold
  counts. Recover 350-day coverage, annualization and IDW parameters with tests.
- Snow: source annual snow inches converted to feet, with explicit station support.
  Do not port the superseded NOAA precipitation drought proxy.
- Drought: observed D1+ weeks ×7/window years. Missing/censored exports are not zero.
- Transit: recovered 50/30/10/10 component composite; it is regional-relative
  access, not absolute national service. Preserve no-coverage missingness.
- CBP: absence can mean disclosure suppression. Never coerce missing/suppressed
  industry cells to zero. Keep raw grocery establishments and trade employment
  densities distinct from the USDA/OEWS adjusted indices.
- USDA: recognize both -9999 and -8888 sentinel values; declare the percentile
  cohort and variable observation periods.
- OEWS: preserve occupation suppression/completeness and metro/state proxy
  status; no default industry share of one for missing data.
- FEMA: retain recovered component formulas as documented indices; no conversion
  back to fake disaster counts, and no claim of a future climate projection.
- Housing: actual three-bedroom ZHVI dollars with month, not $/square foot.

All values must expose source IDs, units, observation period, calculation method,
status and coverage/fallback notes. No old-estimate calibration, workbook-scale
quantile mapping, candidate peer values or silent median fills are permitted.
Source-only interpolation is permitted when its parameters and limitations are
tested and reported. Direct observations, derived indices, regional proxies and
interpolations must be distinguishable. A missing value is not a measured zero.

## Ranking and completion

Retain every county/factor row. Composite ranks use a declared complete-case
cohort or fail explicitly on missingness; no mixing incomparable partial averages.
Factor ranks use average ties. Runoff is seeded shuffled-factor elimination,
ordered by mean elimination round, wins, average factor rank and final FIPS tie.
Win rates express this procedure, not input-data uncertainty.

Completion of a source-file migration requires failing Given/When/Then tests
observed before implementation, download/normalization utility tests, actual
downloaded inputs, green numerical and acceptance tests, a real factor run, and
updated ledger/methods. Do not call unavailable factors complete. A document or
historical artifact is completed by its tested classification/provenance or
comparison behavior; it does not justify fabricating a new metric or downloading
every hypothetical future source it mentions.

## Collaboration and processing order

Review and official-source research may run in parallel. Independent ranked
source ports may also be implemented in parallel when each agent owns exactly
one incoming file and its tests, acquisition script, normalization, and ledger
entry. Within each item, failing BDD tests still precede implementation and
real-data execution. Every agent must read this design first. Change the design
explicitly before tests only when new evidence requires it. Track progression in
`docs/incoming-processing.md`.
