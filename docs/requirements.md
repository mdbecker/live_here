# V1 requirements and evidence

Initialized from “Project conversation summary,” conversation
`6aa5bdc9-9374-83ea-b04b-693b495e68d4`, retrieved September 12, 2026, and six
accessible attachments. The underlying seven conversations and all 20 reported
attachments were not independently retrieved. `research/summary-1.md` is the
latest summary; older summaries contain conclusions superseded by it.

## Intended product

A proper Python package that computes comparable factors for every US county and
county-equivalent from public/source-backed data, exports machine-readable
results, and later supplies an Excel review output and GIS application.
The target county count must come from the chosen source and vintage, never the
old 413/439 candidate list or a hardcoded current national count.

V1 covers heat, cold, snowfall, drought, AQI, walkability, transit, groceries,
tradespeople, housing, FEMA hazard burden, and FEMA-based resilience. Nine weaker
factors are deferred. Politics is the proposed first V2 addition. Woodland is a
separate exploratory concept requiring forest-cover/protected-land evidence.

## Recovered decisions

1. Existing workbooks are comparison artifacts, never calculation inputs.
2. No old-estimate calibration, preservation of missing values from old estimates,
   or mapping new measurements onto old distributions.
3. Centralize geography, source manifests, factors, ranking, runoff, and QA.
4. Rename housing to actual three-bedroom ZHVI, keeping dollars and dates.
5. Rename FEMA disaster output to hazard burden/risk. Resilience is not an
   explicit future climate projection.
6. Keep source-derived observations, proxies, interpolations, and missing values
   distinguishable. Source-backed does not necessarily mean directly measured.
7. Treat complete national values as an aspiration subject to source coverage;
   never fake completeness with unmarked fallbacks.

## Starter implementation choices

These are new engineering defaults, not claimed historical decisions:

- Standard-library Python core and CSV/JSON outputs to make setup lightweight.
- Explicit `demo` and `research` modes; production mode is not enabled.
- `complete_case` or `error` missing-data policies. All counties remain in the
  factor output; only the complete subset receives comparable composite ranks.
- Exact source-name crosswalks for AQI, avoiding fuzzy matching that conflates
  independent cities with same-named counties.
- Reject mismatched geography vintages pending reviewed harmonization.
- A reference Python runoff with FIPS as the final deterministic tie-breaker.
  It implements the historical procedure but does not reproduce NumPy/Numba's
  random stream or its state/name final tie-break exactly.
- No automatic downloads until raw-file inventory, vintages, and source terms
  are verified. No guessed formulas for the ten unrecovered adapters.

## National V1 completion gates

- All twelve adapters implemented and validated against original source samples.
- Authoritative county universe, territorial scope, and geography vintage pinned.
- Connecticut planning regions and historical county changes handled explicitly;
  source mismatches and excluded geographies reported.
- Every output has units, source IDs, observation period, method, and data status.
- Coverage and plausible-range checks per factor; suppression and sentinel values
  handled according to each source's documentation.
- No runtime imports or reads from `research/legacy/` or any workbook estimates.
- Seeded ranking verified; multiple-seed stability assessed independently from
  measurement uncertainty. Optimized national runoff matches reference rules.
- Historical comparisons explained without forcing old values or old ranks.
- Repeatable machine-readable output from pinned inputs, followed by Excel review.
