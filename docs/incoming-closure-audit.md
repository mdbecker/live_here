# Incoming closure audit — September 13, 2026

## Verdict

**Every incoming artifact now has an explicit, tested disposition and the current
source-backed model has been rebuilt.** The directory has **25 non-README files**,
not 21: the four supplied OEWS archives were absent from the original ledger.
All 25 were hash-verified and moved unchanged to `research/legacy/` on September
13, 2026; `data/incoming/` now contains only its README. No additional upload is
presently required. Two shared
operational follow-ups remain: discovery/cache refresh for publishers other than
AQI and a documented review of remaining county-equivalent changes.

This is a local implementation/evidence audit, not a new certification that the
cached releases are the latest available. Incoming Python files were inspected
without executing them. All archive CRC checks passed; the five previously
identified duplicate artifacts match their archived copies. The four BLS ZIPs
match their raw-cache copies. File hashes, sizes, Python function inventories,
document headings and archive member lists are in
[the closure inventory](research/incoming-closure-inventory.json). README is
included there as directory guidance, not a migration item.

Every ranked item in the per-file disposition table below is therefore safe to
archive. The four OEWS ZIPs remain local and Git-ignored because of their size;
the other artifacts are normal research-history files. Archiving does not close
the cross-cutting C4/C5 freshness and geography follow-ups.

The completed suites pass: 96 offline tests and 20 acceptance tests. These
results establish the documented scenarios, not a claim that every publisher
offers an automatically discoverable current release.

## Required closure work, in priority order

### C1. OEWS processing — completed September 13, 2026

Affected: `update_oews_trades_and_rerun_mcmc(1).py`, `oesm25all.zip`,
`oesm25st.zip`, `oesm25ma.zip`, `oesm25in4.zip` (ledger rank 10 and 22–25).

The closure implementation parses the all-data, state, MSA and national
three-digit-industry members with their `AREA`, `NAICS`, `OWN_CODE`,
`OCC_CODE`, and `O_GROUP` fields. It uses only the one `00-0000` all-occupations
row in each cohort as denominator, excludes overlapping SOC rollups, and marks a
share unavailable when a requested detailed occupation is absent or suppressed.
The XLSX reader honors sparse A1 cell references. The EPA SLD's published
`STATEFP`, `COUNTYFP`, `CBSA`, and `TotPop` fields provide a population-weighted
county-to-CBSA map; a county without a usable MSA match uses the state proxy.

The cached release produced a national all-industry selected-occupation share of
`5,729,620 / 155,495,730 = 0.03684744`, a NAICS 238000 industry share of
`2,157,710 / 5,243,000 = 0.41154110`, 905 metro-proxy counties, 2,080
state-proxy counties, and 246 missing counties. `tests/test_oews_closure_bdd.py`
records the red-first hierarchy, sparse-cell, suppression, metro and no-default
share scenarios; `docs/testing/oews-closure-red.txt` preserves the actual red
result. C4, C5, C6 and C7 still apply to this source family.

### C2. USDA tied percentiles — closed September 13, 2026

Affected: `update_usda_food_environment_and_rerun_mcmc(1).py` (rank 11).

Red-first tied-value and permutation-invariance scenarios were captured in
`docs/testing/usda-ties-red.txt`. `percentile_scores` now assigns the average
ordinal position to every equal value, matching the incoming script's ranking
rule. The refreshed official USDA export records its cohort as the 2,989
national FEA county rows with all three 2019 access indicators. Its components
are `PCT_LACCESS_POP19`, `PCT_LACCESS_LOWI19`, and `PCT_LACCESS_HHNV19`; the
CBP grocery base and population denominator are 2023. The rerun in
`outputs/usda-tie-correction` retains 3,220 counties and ranks 304 complete
cases. This closes C2 only; C4, C5, C6, and C7 remain open for the USDA item.

### C3. FEMA component missingness — completed September 13, 2026

Affected: `update_fema_nri_and_rerun_mcmc(1).py` (rank 12).

Red-first scenarios are preserved in `docs/testing/fema-components-red.txt`.
The adapter now requires every core and component header, distinguishes blank
non-applicable components from unavailable sentinel/unparseable values, and
keeps an unavailable frequency or climate-risk dependency missing rather than
converting it to zero. The audit reports component counts and affected rows. The
cached FEMA service export has 3,232 rows, all required component headers, zero
unavailable frequency components and zero unavailable climate-risk components;
it has 12,323 non-applicable blank components and 3,144 rows eligible for each
FEMA composite before target-geography matching.

### C4. Latest-release discovery and safe refresh — partially completed

Affected: all eleven factor-update scripts (ranks 6–16), and supplied BLS sources.

AQI now has a red-first release-selection test in
`docs/testing/aqi-discovery-red.txt`. Its gatherer parses EPA AirData's download
listing, excludes the in-progress current year, chooses the newest two completed
annual files, and stores `aqi-release-discovery.json`. On September 13 it selected
and downloaded 2025 while retaining 2024. The [EPA AirData listing](https://aqs.epa.gov/aqsweb/airdata/download_files.html)
also exposes partial current-year data, which the policy intentionally excludes.

Remaining: implement equivalent publisher-listing discovery and explicit cache
refresh for NOAA, Census, BLS, USDA, FEMA, USDM, transit and Zillow. The drought
window must also validate full start/end dates rather than infer duration only
from the years. Every current cache is pinned by receipt and SHA-256, so these
are freshness workflow gaps, not missing data needed for the current run.

### C5. Provenance and geography audits — partially completed

Affected: CBP/OEWS/USDA, transit, and all composite source exports.

The red-first geography tests in `docs/testing/geography-audit-red.txt` now
require the grocery manifest to pin USDA, CBP and PEP parents, transit to
separate its 2013 GEOID10 source geography from the 2019 target and describe its
first-five-digit FIPS aggregation, and normalized adapters to list every
out-of-universe FIPS. The current final run reports those IDs per factor. Its
11 FEMA/drought/trades exclusions are visible target-vintage differences, not
unusable source observations.

Remaining: document a human-reviewed disposition for each remaining historical
county-equivalent difference and add source-vintage/harmonization declarations
where a source has a different geography. This is review documentation work;
the code no longer silently discards those IDs.

### C6. Intake dispositions and BDD evidence — completed September 13, 2026

Affected: all files, especially ranks 17–21 and the four BLS archives.

The red-first all-artifact scenario is preserved in
`docs/testing/intake-all-artifacts-red.txt`. `live_here.intake.DISPOSITIONS` and
its BDD test classify all 25 non-README artifacts, including every source port,
the historical control and deferred proxy scripts, both workbooks, correction
rollup and four BLS archives. Classification does not execute incoming code or
make historical workbooks runtime inputs. The hash inventory remains the
identity/retention reference for ignored uploads.

### C7. Auditable final run — completed September 13, 2026

`outputs/current-real-closure-final` was generated after the repairs from the
unchanged pinned raw cache. It contains the 3,220-county 2019 target universe,
12 selected factors, and 305 complete-case rankings. The final-run red log
captures the missing-output failure; acceptance now verifies the current config
and `pipeline.py` hashes against the manifest, as well as coverage, rank counts
and simulation-win reconciliation. The historical `current-real-twelve` output
remains a historical artifact and is not relabeled as the final run.

## Per-file disposition

Ranks refer to the processing ledger; the inventory records exact identities.

| Files | Verified disposition | Remaining before intake closure |
| --- | --- | --- |
| Rank 1: County Ranker handoff | Governing scope captured in design | Retain source-only/reproducibility requirements during remaining C4/C5 follow-up |
| Rank 2: data-quality handoff | Constraints recorded | C4/C5 follow-up only; no requirement to restore old estimates |
| Ranks 3–4: model summary and earlier retirement handoff | Historical design/reference | Classification exists; preserve scope distinction from later product milestones |
| Rank 5: CNBC handoff | Deferred research | No CNBC data implementation required for V1 intake closure |
| Rank 6: walkability script | Port and cached source available | C4 refresh remains; CSV alternative to GDB is intentional |
| Rank 7: temperature script | Heat/cold port and cached inputs available | C4/C5 follow-up; retain explicit source-only interpolation status |
| Rank 8: multivariate script | Snowfall port available | C4/C5 follow-up; precipitation drought proxy intentionally superseded |
| Rank 9: CBP script | Population-matched base exported | C4/C5 follow-up; no approximate legacy Connecticut weights |
| Rank 10: OEWS script | Corrected metro/state proxy implementation with NAICS 238 share | C4/C5 follow-up |
| Rank 11: USDA script | Access adjustment uses average tied percentiles; 2019 USDA indicators and 2023 CBP base are audited | C4/C5 follow-up |
| Rank 12: FEMA script | Two composites implemented | C4/C5 follow-up |
| Rank 13: drought script | Fixed-window source normalized | C4/C5 follow-up |
| Rank 14: transit script | Source component means exported | C4/C5 follow-up; no-coverage guardrail estimates intentionally removed |
| Rank 15: AQI script | Latest two completed annual files discovered and crosswalk audited | C5 follow-up; calibrated estimates intentionally removed |
| Rank 16: Zillow script | Direct three-bedroom dollars exported | C4/C5 follow-up; old-scale mapping intentionally removed |
| Rank 17: candidate correction script | Historical control; not executed | Tested historical disposition and baseline linkage |
| Rank 18: proxy-reuse script | Estimate-blended factors excluded | Tested deferred disposition; no requirement to implement proxies now |
| Rank 19: corrected workbook | Archived copy matches; prior 439-row audit exists | Tested historical-baseline disposition; no equality target for new rankings |
| Rank 20: correction rollup CSV | Archived copy matches | Tested audit-only disposition and baseline linkage |
| Rank 21: woodland workbook | Archived copy matches; prior audit identifies divergent 26 candidate rows | Tested separate-branch disposition; protected woodland remains deferred |
| Rank 22: oesm25all.zip | Parsed national all-industry cohort; source receipt retained | C4/C5 follow-up |
| Rank 23: oesm25st.zip | Parsed state cohorts with explicit suppression handling | C4/C5 follow-up |
| Rank 24: oesm25ma.zip | Parsed MSA cohorts; SLD county-CBSA mapping applied | C4/C5 follow-up |
| Rank 25: oesm25in4.zip | Parsed NAICS 238000 cohort; industry share applied | C4/C5 follow-up |
| README.md | Drop-folder instructions read | No factor processing required; wording can be refreshed after closure |

## Intentionally outside this closure

The nine deferred factors, protected woodland GIS intersection, CNBC metric
reconstruction, Excel/GIS product outputs, production mode and large-run
performance/stability work remain future milestones. Historical workbook
mutation, old-value calibration and candidate-specific imputation should not be
ported. Limited source coverage alone is not an intake defect when correctly
reported; the confirmed calculation, provenance and workflow gaps above are.
