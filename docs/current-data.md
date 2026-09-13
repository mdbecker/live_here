# Gathering and running the implemented factors

> Closure audit: the adapters run and the current configuration has a fresh,
> hash-verified national output. See [incoming-closure-audit.md](incoming-closure-audit.md)
> for the remaining publisher-wide release-discovery and geography-review work.
> AQI now discovers the latest two completed annual files before download; the
> other releases below remain pinned cached inputs until their publishers receive
> equivalent discovery adapters.

The current runtime implements all twelve V1 factors: **AQI, walkability, heat,
cold, snowfall, drought, transit, housing, tradespeople, groceries, FEMA hazard
burden, and FEMA resilience**. The first
acquisition workflow downloads the sources needed for AQI/walkability and the
second downloads NOAA temperature normals plus Census population centres. The
third downloads NOAA annual/seasonal multivariate normals for snowfall. The
CBP 2023 county rows, the matching Census PEP 2023 population denominator, the
supplied BLS May 2025 OEWS archives, USDA FEA 2025, and FEMA NRI v1.20 county
service data and the USDM D1+ county API export for 2016–2026 are cached and
normalized. The EPA transit and Zillow three-bedroom housing exports are also
cached and included in the current configuration.

## Reproduce

From the repository root, with the package installed in `.venv`:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/gather_current_data.py --transport curl
.venv/bin/python scripts/gather_temperature_data.py --transport curl
.venv/bin/python scripts/gather_snowfall_data.py --transport curl
.venv/bin/python scripts/gather_cbp_data.py --transport curl
.venv/bin/python scripts/gather_oews_data.py --transport curl
.venv/bin/python scripts/gather_usda_data.py --transport curl
.venv/bin/python scripts/gather_fema_data.py --transport curl
.venv/bin/python scripts/gather_drought_data.py --transport curl
.venv/bin/python scripts/gather_transit_data.py --transport curl
.venv/bin/python scripts/gather_housing_data.py --transport curl
.venv/bin/live-here run --config data/interim/current/config.json --output outputs/current-real-closure-final
.venv/bin/python -m unittest discover -s tests/acceptance -v
```

The system `curl` command is an optional HTTP transport. The downloader also
supports `--transport python` using the standard library. The system transport
was added after Python's DNS resolution failed on this host. Both transports
use HTTPS, reject download failures, and save source receipts with SHA-256 hashes,
URLs, byte counts, and retrieval times. Verified cached downloads are reused;
modified cache contents are rejected. No source script or workbook is executed.

The pipeline preserves existing nonempty output directories. To rerun, select a
new directory; the opt-in acceptance tests check the named hash-verified output
directory `outputs/current-real-closure-final`. Raw downloads and normalized exports are ignored
by Git; acquisition code, tests and documentation are kept in the repository.

## Sources

| Input | Official source | Release used |
| --- | --- | --- |
| County universe | [Census Gazetteer](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2019_Gazetteer/) | 2019 national counties |
| Air quality | [EPA AirData annual summaries](https://aqs.epa.gov/aqsweb/airdata/download_files.html) | Automatically discovered latest two complete years: 2024 and 2025 county AQI |
| Walkability and population | [EPA public data directory](https://edg.epa.gov/data/public/OA/) | Smart Location Database 3.0, 2021 CSV |
| Heat and cold | [NOAA daily normals](https://www.ncei.noaa.gov/data/normals-daily/2006-2020/) plus [Census population centres](https://www2.census.gov/geo/docs/reference/cenpop2020/county/) | 2006–2020 normals, 2020 county centres |
| Snowfall | [NOAA annual/seasonal normals](https://www.ncei.noaa.gov/data/normals-annualseasonal/2006-2020/) plus Census population centres | 2006–2020 normals, 2020 county centres |
| Business base | [Census CBP datasets](https://www2.census.gov/programs-surveys/cbp/datasets/2023/) | 2023 county file joined to Census PEP 2023 population |
| Grocery access | [USDA ERS Food Environment Atlas](https://www.ers.usda.gov/data-products/food-environment-atlas/) | FEA 2025 release: 2019 access indicators joined to a CBP 2023 base |
| FEMA hazard burden and resilience | [FEMA National Risk Index county service](https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0) | v1.20, December 2025; source-only composites |
| Drought | [U.S. Drought Monitor county statistics REST service](https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx) | D1, non-consecutive weeks, 2016-01-01 through 2026-01-01; minimum weeks 0 |
| Transit | [EPA Access to Jobs and Workers via Transit](https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip) | Trans45 DBF release; county means of source block-group access components |
| Housing | [Zillow Research county ZHVI](https://files.zillowstatic.com/research/public_csvs/zhvi/County_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv) | Latest available three-bedroom smoothed/seasonally adjusted month |

The walkability input is the official CSV containing `NatWalkInd` and `TotPop`.
It avoids downloading a geodatabase and installing GIS libraries solely to
extract the same published columns. The full downloaded CSV is retained unchanged.
Its broader attributes are not automatically treated as additional implemented
factors.

## Geography and measurement limits

The [EPA technical guide](https://www.epa.gov/system/files/documents/2023-10/epa_sld_3.0_technicaldocumentationuserguide_may2021_0.pdf)
documents county identifiers as 2019 geography and distinguishes `GEOID10` from
the updated `GEOID20` field. The guide's narrative has inconsistent references to
2018/2019 boundaries, so this run pins the 2019 county universe and audits actual
identifier matches. `GEOID20` must not be interpreted as 2020 Census geography.
The normalized export uses the generic column `GEOID`, retaining the source's
identifier value. Original demo inputs using `GEOID10` remain supported.

The 2019 Census universe includes the 50 states, DC and Puerto Rico. Other Island
Areas are outside this source. All rows from that universe remain in the factor
and coverage outputs, whether their observations can be ranked or not.

AQI county names are mapped explicitly into that universe. Case and selected
legal suffixes are normalized; independent-city suffixes are preserved.
Unmatched and ambiguous names are audited, never fuzzily guessed. Name matching
alone cannot certify unchanged geographic boundaries between 2019 and the source years.
This remains a research run, with source-year and target-geography distinctions
recorded in its manifest. No spatial reaggregation is claimed.

AQI is an available-year mean of monitored-day annualizations. Walkability is
population weighted. Heat and cold are expected TMAX threshold days from NOAA
normal means/standard deviations, annualized after a 350-day station-coverage
check, then interpolated with inverse-square weights within 125 km of each
county population centre. Neither missing monitoring, missing walkability, nor
missing station coverage is replaced with an old estimate. Rankings compare
complete cases only and are not the full retirement-location ranking.
Snowfall uses `ANN-SNOW-NORMAL` in inches, requires at least ten years of
station support, converts to feet, and interpolates within 175 km.

FEMA hazard burden is `0.40 × EAL_SCORE + 0.30 × ALR_VRA_NPCTL + 0.30 ×
hazard-frequency percentile`, with frequency summed across all 18 NRI hazards.
FEMA resilience is `0.45 × RESL_SCORE + 0.30 × (100 − climate-hazard risk) +
0.15 × (100 − ALR_VRA_NPCTL) + 0.10 × (100 − SOVI_SCORE)`, clipped to 0–100.
These composites remain on the FEMA source scale; old workbook values are never
used for calibration.

Drought is the observed USDM D1+ non-consecutive-week count annualized as
`weeks × 7 / 10`. The current query uses a pinned ten-year window and
`minimumweeks=0`; it returned 3,220 usable source rows, of which 3,209
matched the pinned target universe. Censored or missing rows remain missing in the pipeline and are never
replaced with workbook estimates or zeros.

Tradespeople is CBP 2023 NAICS 238 employment density multiplied by the BLS May
2025 NAICS 238000 selected-occupation share and a 0.65–1.35 bounded local mix.
The local mix uses an EPA SLD population-weighted county-to-CBSA mapping when an
MSA cohort is available, then falls back to the state cohort. The BLS
all-occupations row is the denominator; hierarchical SOC rollups are excluded
and suppressed selected occupations remain unavailable. The current release has
905 metro proxies, 2,080 state proxies and 246 missing trades observations.

Transit is a source-only county mean of EPA Trans45 block-group components:
`100 × (0.50×TrAccess_Indexi + 0.30×Pct_Jobs_byTr + 0.10×Pct_Pop_byTr +
0.10×Pct_Wrks_byTr)`. EPA coverage is limited to the published GTFS-served
regions, so uncovered counties remain missing. Housing is the direct Zillow
three-bedroom ZHVI value for one selected month; it remains in dollars and is
never mapped to an inherited workbook scale.

Groceries start with the CBP 2023 grocery-establishment density and apply a
bounded access penalty. The three USDA FEA indicators are all observed in 2019:
`PCT_LACCESS_POP19`, `PCT_LACCESS_LOWI19`, and `PCT_LACCESS_HHNV19`. Their
percentiles use the 2,989 national FEA county rows with all three values, and
ties receive the same average percentile. The audit records this cohort and the
separate 2019/2023 periods; counties without a usable USDA indicator or CBP
base remain missing.

## BDD evidence

Tests use executable Given/When/Then scenario names in `unittest`, keeping the
core dependency-free. Before acquisition implementation, six scenarios failed
because the module did not exist and two real-data acceptance scenarios failed
because the sources and real run did not exist. Additional geography, preparation
and system-transport scenarios were each run red before their implementation.

Unit scenarios exercise downloads with controlled responses and small source-
shaped fixtures. Acceptance scenarios explicitly inspect downloaded real files,
source hashes, the national universe, ranked/excluded counts and simulation-win
totals. The temperature acceptance scenario also checks the NOAA archive,
Census centre file, station coverage audit, and normalized county export.
Ordinary CI runs the offline scenarios; network-dependent acceptance is an
explicit local step after acquisition and the real pipeline run.

Red-phase logs are preserved under `docs/testing/`. The real run's configuration,
acquisition audit and coverage report record the final downloaded inputs and
coverage rather than relying on the historical conversation's claims.
The FEMA adapter's red phase is recorded in `docs/testing/fema-red.txt`; its
acceptance scenarios verify the v1.20 service receipt, composite coverage, and
twelve-factor run. Drought, transit, and housing each have their own preserved
red-phase BDD logs and real-data acceptance scenarios.

The final BDD rebuild was verified before the current output was generated:
acceptance verifies the current configuration and pipeline hashes. The run covers
3,220 counties and ranks 305
complete cases. FEMA component validation, USDA parent provenance, transit
source-versus-target geography, generic excluded-FIPS audits, AQI discovery, and
the complete intake manifest each also have preserved red-phase evidence.
