# Live Here

Reproducible county comparisons for choosing where to live. The project is moving
from an exploratory, 21-factor workbook to a national, source-only Python model.

**This repository is a working starter, not the completed national production model.**
It includes the recovered research, a 12-factor catalog, tested source adapters,
a shared ranking engine, source checksums, and coverage reporting. All twelve V1
adapters are implemented and exercised against current official downloads. The CBP 2023 business base, same-year
population denominator, BLS May 2025 OEWS trade adjustment, USDA FEA 2025
adjustment, and FEMA NRI v1.20 composites are normalized.

## Start locally

Python 3.11 or newer. The core has no third-party runtime dependencies.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
live-here catalog
live-here run --config examples/demo/config.json --output outputs/my-first-demo
python -m unittest discover -s tests -v
```

The current official inputs can be downloaded and prepared with:

```sh
PYTHONPATH=src python scripts/gather_current_data.py --transport curl
PYTHONPATH=src python scripts/gather_temperature_data.py --transport curl
PYTHONPATH=src python scripts/gather_snowfall_data.py --transport curl
PYTHONPATH=src python scripts/gather_cbp_data.py --transport curl
PYTHONPATH=src python scripts/gather_oews_data.py --transport curl
PYTHONPATH=src python scripts/gather_usda_data.py --transport curl
PYTHONPATH=src python scripts/gather_fema_data.py --transport curl
PYTHONPATH=src python scripts/gather_drought_data.py --transport curl
PYTHONPATH=src python scripts/gather_transit_data.py --transport curl
PYTHONPATH=src python scripts/gather_housing_data.py --transport curl
PYTHONPATH=src python -m live_here run --config data/interim/current/config.json --output outputs/current-real-closure-final
```

The first command caches the 2019 Census county universe, EPA annual AQI files,
and EPA Smart Location Database. The second caches the NOAA 2006–2020 daily
temperature normals and Census 2020 county population centres, then writes the
source-only heat/cold export to `data/interim/current/temperature.csv`.
Snowfall is prepared with `PYTHONPATH=src python scripts/gather_snowfall_data.py
--transport curl`, using the NOAA annual/seasonal multivariate normals and the
same Census population centres.
Raw and interim files are intentionally ignored by Git; each download has a
sidecar receipt containing its URL, retrieval time, byte count, and SHA-256.

To run without installing:

```sh
PYTHONPATH=src python3 -m live_here run --config examples/demo/config.json --output outputs/another-demo
```

The demo uses **invented data for three example counties**, with real-format FIPS
codes. Two counties can be ranked and one remains missing. It demonstrates the
pipeline; its values and rankings say nothing about the real counties.
Use a new output directory for each execution.

## What is here

| Location | Purpose |
| --- | --- |
| `src/live_here/` | Package, CLI, geography validation, factor adapters, ranking, provenance |
| `examples/demo/` | Small synthetic inputs and a complete hashed run configuration |
| `tests/` | Calculation, missing-data, geography, source-acquisition, BDD, and runoff tests |
| `docs/requirements.md` | Recovered project scope and completion criteria |
| `docs/factors.md` | Definitions, directions, caveats, and implementation status |
| `docs/data-contracts.md` | Input/output schemas and source onboarding |
| `docs/missing-files.md` | Files to supply next |
| `docs/roadmap.md` | Ordered implementation work |
| `docs/research/` | Retrieved conversation, historical summaries, and workbook audit |
| `research/legacy/` | Completed intake artifacts, unchanged, for research/comparison only |
| `data/incoming/` | Empty drop folder for future materials; ignored by Git |
| `.github/workflows/ci.yml` | Package install, tests, and demo on Python 3.11–3.14 |

Each run produces `counties.csv`, long-form `factors.csv`, `rankings.csv`,
`coverage.json`, and `run-manifest.json`. The manifest contains the configuration,
source hashes, code hashes, Python/package versions, and output hashes.

## Non-negotiable model rules

- Derive values from source files. Never calibrate to old workbook estimates or
  map measurements onto old workbook distributions.
- Define the county universe from a versioned authoritative geography source,
  retain five-digit FIPS strings, and explicitly handle county-equivalent changes.
- Preserve missingness and provenance. Zero is a measurement, not a missing value.
- Keep measured values, derived indices, normalized ranks, and simulation results
  distinct. ZHVI is dollars; FEMA hazard burden is not disasters per decade.
- Compare ranks only within a declared cohort. The starter ranks complete cases
  and lists excluded counties, or fails on missingness when configured to do so.
- Keep the historical 439-county corrected workbook as a comparison baseline.
  The woodland workbook is a separate branch, not that baseline plus a column.

The runoff repeatedly eliminates the worst remaining county on a factor selected
from shuffled cycles. It orders results by mean elimination round, then wins,
average factor rank, and FIPS. Win rates describe this procedure, not the
probability that a county is objectively best. The reference engine is intended
for small runs; nationwide 100,000-run performance is future work.

## Incoming materials

All 25 non-README files from the September 2026 intake were reviewed, classified,
and moved unchanged to `research/legacy/`. See the
[processing ledger](docs/incoming-processing.md), [closure audit](docs/incoming-closure-audit.md),
and [checklist](docs/missing-files.md). `data/incoming/` now contains only its
README and is ready for another intake batch.

```sh
live-here inventory data/incoming > /tmp/live-here-incoming-inventory.json
```

Do not execute the archived scripts as the new pipeline. They modify workbooks
and preserve old estimates. Source calculations were ported into the package
one item at a time using [the onboarding contract](docs/data-contracts.md).

The current real-data run covers all 3,220 counties in the pinned 2019 Census
universe. All twelve V1 factors are selected; 305 counties have complete
observations in the current source releases and are ranked. It remains a
research-mode run with explicit missingness: source coverage, production policy,
Excel export, GIS interface, and remote publication are still future work.
