# Live Here

Reproducible county comparisons for choosing where to live. The repository builds
a source-only V1 research dataset for thirteen county factors and writes one
canonical machine-readable output set.

The project is intentionally small: standard-library Python, CSV/JSON outputs,
explicit provenance, and no historical workbook calibration.

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Build

From the repository root:

```sh
live-here build
```

Use the optional system curl transport when Python networking is not suitable:

```sh
live-here build --transport curl
```

Every build is a clean normalized-data build. It recreates
`data/interim/current/`, reuses verified immutable cache files in
`data/raw/current/`, runs the twelve source gatherers in the fixed V1 order, then
runs the ranking pipeline from `data/interim/current/config.json`.

Successful builds replace the canonical generated output directory:

```text
outputs/
  counties.csv
  factors.csv
  rankings.csv
  county_rankings.csv
  coverage.json
  run-manifest.json
```

Failed builds stop at the failing stage and preserve the last successful
`outputs/` directory. Partial interim files may remain; the next build clears
them before starting.

## Catalog

```sh
live-here catalog
```

The catalog lists the implemented V1 factors, units, directions, and source
status.

## Missing values and presentation

V1 ranks the full target county universe. Most factor adapters preserve source
missingness; the specialty-grocery lower-bound factor explicitly assigns zero
to counties absent from its screening workbook. Other residual gaps use
deterministic geographic inverse-distance estimates from two to five nearby
source-backed counties. Inferred values are explicitly marked in `factors.csv`
and `coverage.json` and are never reused as donors. Machine-readable outputs
remain numeric.

`county_rankings.csv` is the human-facing presentation CSV. A trailing `*`
marks a county result that uses one or more inferred factor values, and marks
the individual inferred factor value and rank. The star is not a confidence
interval or a claim that the county was directly observed.

The 2019 Valdez-Cordova county (`02261`) uses the reviewed Census geography
bridge to the 2020 Chugach (`02063`) and Copper River (`02066`) centers,
weighted by their published populations. Other county coordinate joins remain
exact-FIPS only.

Deferred work includes national transit coverage decisions, source QA,
performance/determinism hardening, v1 release packaging, nine V2 factors, and
the later GIS/web application.

## Repository Layout

| Location | Purpose |
| --- | --- |
| `src/live_here/` | Package, CLI, factor adapters, ranking, provenance, build orchestration |
| `scripts/` | Fixed V1 source gatherers used by `live-here build` |
| `tests/` | BDD, numerical, source, ranking, and acceptance tests |
| `examples/demo/` | Small synthetic pipeline fixtures retained for internal tests |
| `docs/methodology.md` | Factor contracts, ranking rules, and missingness behavior |
| `docs/sources.md` | Current source list, vintages, methods, coverage limits |
| `docs/roadmap.md` | Remaining V1 and V2 work |
| `data/sources/` | Archived project-supplied source workbooks and guides |

Raw downloads, interim normalized files, outputs, and local prototype material
are generated or local state and are ignored by Git. Archived files under
`data/sources/` are stable project inputs.
