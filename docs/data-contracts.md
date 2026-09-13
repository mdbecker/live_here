# Data contracts and onboarding

## Files and manifests

Use `examples/demo/config.json` as the executable schema example. All paths are
relative to the configuration file, not the shell's working directory. Every
source requires `id`, `path`, `sha256`, `url`, `vintage`, `geography_vintage`, `role`,
and `license`. Keep retrieval date and raw-parent hashes as additional metadata
when recording real downloads or derived exports; they are retained in the run
manifest. The starter checks local bytes against the supplied SHA-256, but it
cannot independently establish that a file's claimed provenance is true.

Store downloads unchanged in `data/raw/`. Derived CSV exports and crosswalks
belong in `data/interim/`, accompanied by the exact extraction command, parent
raw-file hashes, source field descriptions, and geography treatment. Do not
register a workbook export as a source. The pipeline rejects research/legacy
paths and XLSX inputs, and its adapters accept specific source schemas.

`live-here inventory <directory>` reports relative names, sizes and SHA-256s.
Inventory is read-only; it neither registers files nor runs supplied code.

## Geography

The normalized county universe requires:

```csv
fips,name,state,geography_vintage
01001,Autauga County,AL,2020
```

This row illustrates format, not a national universe. Obtain the full universe
from an authoritative release. Keep leading zeros. Codes must be five ASCII
digits, unique, and not state aggregate rows ending 000. All rows must have one
geography vintage. File validation is structural; national completeness and
membership must be checked against the pinned authoritative source during V1.

Use FIPS for joins. Do not strip “city” from independent-city names or silently
reuse obsolete county codes. A 2020 block-group dataset and a newer Connecticut
planning-region universe need an explicit harmonization step. Until implemented,
the starter rejects manifest vintage differences. Territories and county
equivalents must be documented as part of universe scope.

## AQI adapter

Accepts CSV or a ZIP with exactly one CSV. Required original column names:

`State`, `County`, `Year`, `Days with AQI`,
`Unhealthy for Sensitive Groups Days`, `Unhealthy Days`,
`Very Unhealthy Days`, `Hazardous Days`.

Provide a reviewed crosswalk CSV with `State,County,fips,geography_vintage`.
Names are matched exactly after trimming whitespace. Crosswalk names must be
unique; mapped FIPS must belong to the selected universe. Unmatched source names
are listed in the adapter audit. Multiple names mapping to one county in the
same year fail as duplicate observations; aggregation across changed geography
requires a deliberate preprocessing method.

Day counts must be finite nonnegative integers, monitored days within the actual
calendar-year length, and bad days no greater than monitored days. Years are
averaged only when at least one day is monitored. Missing counties stay missing.

## Walkability adapter

Accepts a CSV export with `GEOID10,STATEFP,COUNTYFP,TotPop,NatWalkInd`.
`GEOID10` is a 12-digit block-group identifier; STATEFP and COUNTYFP are two/three
digits and must agree with it. If the source uses another identifier column,
rename it in a documented export. Do not merely relabel a different vintage as
GEOID10. Duplicate block groups fail. Scores must be 1–20 when present;
population must be finite and nonnegative. One consistent export per run is
accepted to avoid accidentally averaging releases.

## Run configuration

- `mode`: `demo` for synthetic data; `research` for real, explicitly partial work.
- `geography_source`: manifest ID of county-universe CSV.
- `factors`: unique implemented factor IDs; order participates in seeded results.
- `adapters`: source ID list per factor and AQI crosswalk ID.
- `iterations`, `seed`: reproducible randomized-runoff settings.
- `missing_policy`: `complete_case` retains all factor rows and ranks only
  complete counties; `error` rejects any incomplete county before writing.

Production mode is deliberately unavailable until the national V1 gates pass.

## Outputs

`counties.csv` preserves the declared universe. `factors.csv` has one row per
county/selected factor, including missing observations, with:

`fips`, `factor`, `value`, `value_status`, `observation_period`, `method`,
`quality_note`, `unit`, `source_ids`, `geography_vintage`.

CSV missing values are empty, not zero. Current nonmissing calculations are
`derived`; future adapters should explicitly distinguish directly observed,
source-derived proxy, and interpolated values. No legacy-estimate status is
allowed in V1. Geography source lineage is recorded at run level.

`rankings.csv` contains complete cases only, average tie ranks per factor, mean
factor rank, average-based rank, mean elimination round, wins and win rate.
Factor ranks are computed within the same complete-case cohort. Exact numeric
ties receive average ranks; the runoff breaks tied worst ranks randomly.

`coverage.json` includes universe/ranked counts, excluded FIPS, selected and
omitted V1 factors, status counts, and adapter diagnostics. Always inspect it
before interpreting rankings. A run with no complete counties has a header-only
ranking CSV and still reports all missingness.

`run-manifest.json` records input, configuration, source-code and output hashes.
Deterministic outputs are expected with the same Python version, code, inputs,
factor order, seed and settings. The reference algorithm does not reproduce the
archived NumPy/Numba random stream bit for bit.
