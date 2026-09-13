# Incoming file processing ledger

The initial order covered 21 non-README files. The September 13 closure audit
found 25: four supplied BLS archives were omitted from this ledger. Five match
previously recovered files byte-for-byte (AQI, walkability, two workbooks, rollup).
The main County Ranker handoff is the controlling source-only specification.
Dependencies and importance precede complexity; among otherwise independent
source ports, more complex work comes first. Independent items may be assigned
to separate agents under the governing design.

**All incoming artifacts now have a tested disposition.** The source-backed
implementation has a fresh, hash-verified national run. See
[incoming-closure-audit.md](incoming-closure-audit.md) for the two remaining
cross-cutting follow-ups: publisher-wide release discovery/cache refresh and
documented review of remaining geography changes.

All 25 listed artifacts were hash-verified against the closure inventory and
moved unchanged from `data/incoming/` to `research/legacy/` on September 13,
2026. The four large OEWS ZIPs are kept there as Git-ignored local research
archives; their identical raw-cache copies, receipts and reacquisition code remain
available. The intake directory now contains only its README.

The archive transition is covered by the green archive-state BDD scenario in
`tests/test_intake_bdd.py`. The OEWS gatherer checks the research archive as its
offline supplied-file fallback; its behavior is covered by the corresponding
green scenario in `tests/test_oews_closure_bdd.py`.

| Rank | Incoming file | Design impact / disposition | Status |
| --- | --- | --- | --- |
| 1 | County_Ranker_Project_Developer_Handoff.md | Governing source-only 12-factor architecture; tested scope contract | reviewed; design incorporated |
| 2 | Retirement_County_Ranking_Project_Developer_Handoff_Data_Quality_Gaps_Next_Steps.md | Provenance and unresolved-source constraints; superseded formula suggestions retained as history | reviewed |
| 3 | County_Ranking_Model_Handoff_Summary.md | Corrected baseline and candidate history; comparison-only | reviewed |
| 4 | Retirement_Town_County_Ranking_Developer_Handoff.md | Earlier 413-county history/ranking semantics; newer scope supersedes estimates | reviewed |
| 5 | CNBC_Quality-of-Life_Data_Research_Developer_Handoff.md | Separate deferred state/local policy research; no new V1 factors | reviewed |
| 6 | update_walkability_and_rerun_mcmc(1).py | Complete source ingestion/geography prerequisite; preserve weighted calculation | processed; official EPA source downloaded, scientific-ID reconstruction tested, real run accepted |
| 7 | update_noaa_temperature_and_rerun_mcmc(1).py | Complex shared stations/coordinates; expected heat and cold | processed; NOAA 2006-2020 archive and Census population centres downloaded, BDD and real-data acceptance green |
| 8 | update_noaa_multivariate_and_rerun_mcmc(1).py | Snowfall using climate infrastructure; discard drought proxy | processed; NOAA multivariate archive downloaded, source-only snowfall export and pipeline adapter green |
| 9 | update_cbp_and_rerun_mcmc(1).py | Shared source-year population and business bases; prerequisite to two refinements | processed; CBP 2023 and Census PEP 2023 downloaded, joined, density export and BDD acceptance green |
| 10 | update_oews_trades_and_rerun_mcmc(1).py | Complex occupation/area refinement after CBP | processed; May 2025 all/state/MSA/industry cohorts parsed with all-occupations denominators, suppression audit, NAICS 238000 share and EPA SLD metro/state proxy |
| 11 | update_usda_food_environment_and_rerun_mcmc(1).py | Access refinement after CBP; sentinel and cohort rules | processed; tied-percentile BDD evidence, a 2,989-row national USDA 2019 indicator cohort, CBP/PEP 2023 parents, and audited base period |
| 12 | update_fema_nri_and_rerun_mcmc(1).py | Two explicit composite factors; nationwide cohort | processed; required component headers, unavailable-versus-non-applicable policy and audit are tested; source-only composites included in final run |
| 13 | update_drought_monitor_and_rerun_mcmc(1).py | Explicit latest complete multiyear window; censored coverage | processed; USDM D1+ county REST export downloaded for 2016-01-01 through 2026-01-01, normalized and accepted in the final run |
| 14 | update_transit_guardrail_and_rerun_mcmc(1).py | Historical latest EPA regional-relative access; remove estimate guardrails | processed; official EPA Trans45 DBF downloaded, source-only 50/30/10/10 county adapter and 530-county final-run coverage; 2,690 counties remain explicitly missing due to EPA/GTFS coverage |
| 15 | update_aqi_and_rerun_mcmc(1).py | Existing port; discover latest complete years and audit geography | processed; red-first discovery chooses the latest two complete EPA annual files, 2024 and 2025, and stores the listing evidence |
| 16 | update_zillow_housing_and_rerun_mcmc(1).py | Direct dollars at one selected month; no inherited scales | processed; Zillow county three-bedroom ZHVI downloaded, normalized, and accepted in the final run |
| 17 | fix_candidate_source_backed_fields_and_rerun(1).py | Historical control only; prohibit candidate whitelist/estimate restoration | processed as historical control; explicitly excluded from runtime |
| 18 | update_proxy_reuse_and_rerun_mcmc(1).py | Defer four estimate-blended proxies; test exclusion from V1 | processed as deferred proxy work; explicitly excluded from V1 |
| 19 | county_rankings_added_candidates_sourcefix_100k(1).xlsx | Hash-preserved 439-county comparison baseline | processed as historical baseline; identical to archived copy, not a runtime input |
| 20 | added_candidate_sourcefix_rollup.csv | Historical correction audit, not runtime data | processed as historical audit; identical to archived copy |
| 21 | county_rankings_with_preserved_woodland_estimate.xlsx | Separate exploratory branch; woodland is not a ranked V1 factor | processed as exploratory woodland branch; identical to archived copy |
| 22 | oesm25all.zip | OEWS all-data source; one national cohort is normalized | processed; national cohort and source receipt retained |
| 23 | oesm25st.zip | State occupation rates; all-occupations denominator and suppression handling | processed; state cohorts and suppression handling retained |
| 24 | oesm25ma.zip | Metro source for recovered local adjustment | processed; MSA rows parsed and EPA SLD CBSA matching applied |
| 25 | oesm25in4.zip | Industry occupation share used by incoming trades method | processed; NAICS 238000 selected-occupation share is source-derived |

The four added ranks preserve existing item references; process them with rank
10 before dependent final ranking validation.

The older 413-county full-data-reuse workbook is already archived. Missing
candidate spot-check/intermediate workbooks and older expansion scripts are
historical, not prerequisites for source-only factor migration. Original raw
downloads remain the responsibility of the acquisition workflow, not the user.

Latest-source discoveries from the reviews: NOAA published normals archives,
Census CBP latest advertised 2023, OEWS May 2025, USDA Atlas 2025, EPA SLD 2021,
and EPA Trans45 2013 release (archive posted in 2014). FEMA NRI v1.20 (December 2025) is served by FEMA's
current ArcGIS county layer. Discovery code must verify these rather than treating
this paragraph as a permanently current release manifest.

All twelve adapters exist and the current final run passes acceptance checks.
Ranks 17–21 are intentionally historical/deferred and have tested intake
dispositions. Exact file identities are recorded in
[the closure inventory](research/incoming-closure-inventory.json).
