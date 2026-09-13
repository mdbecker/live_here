# Live Here

Reproducible county comparisons for choosing where to live. The repository builds
a source-only V1 research dataset for twelve county factors and writes one
canonical machine-readable output set.

The project is intentionally small: standard-library Python, CSV/JSON outputs,
explicit provenance, and no workbook-derived estimates.

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
`data/raw/current/`, runs the ten source gatherers in the fixed V1 order, then
runs the ranking pipeline from `data/interim/current/config.json`.

Successful builds replace the canonical generated output directory:

```text
outputs/
  counties.csv
  factors.csv
  rankings.csv
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

## Incompleteness

V1 is a research output, not a final product. It preserves all counties in
factor and coverage outputs, but rankings compare only complete cases. Missing
source observations remain missing; zero is treated as a measurement, not a
placeholder.

Deferred work includes geographic inference/provenance review, national transit
coverage decisions, source QA, performance/determinism hardening, v1 release
packaging, nine V2 factors, and the later GIS/web application.

## Repository Layout

| Location | Purpose |
| --- | --- |
| `src/live_here/` | Package, CLI, factor adapters, ranking, provenance, build orchestration |
| `scripts/` | Fixed V1 source gatherers used by `live-here build` |
| `tests/` | BDD, numerical, source, ranking, and acceptance tests |
| `examples/demo/` | Small synthetic pipeline fixtures retained for internal tests |
| `docs/methodology.md` | Factor contracts, ranking rules, and missingness policy |
| `docs/sources.md` | Current source list, vintages, methods, coverage limits |
| `docs/roadmap.md` | Remaining V1 and V2 work |

Raw downloads, interim normalized files, outputs, and local prototype material
are generated or local state and are ignored by Git.
