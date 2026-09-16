# Sources

`live-here build` downloads or reuses SHA-256-verified source files under
`data/raw/current/`, writes normalized inputs to `data/interim/current/`, and
records source receipts and parent hashes in `outputs/run-manifest.json`.

Raw files are immutable cache entries. A missing receipt, changed byte hash, or
unexpected URL fails the build. AQI has an additional pinned-selection rule:
the first acquisition reads the EPA listing and writes
`data/raw/current/aqi-release-discovery.json` with two complete calendar-year
releases. Later builds reuse that record and its raw files without listing EPA
again. Refreshing that pinned selection is a deliberate source-freshness action,
not an implicit build step.

| Factor area | Provider and vintage | Acquisition | Prepared/runtime inputs | Coverage limits |
| --- | --- | --- | --- | --- |
| County universe | Census Gazetteer, 2019 plus Census 2020 mean centers | HTTPS GET [Gazetteer ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2019_Gazetteer/2019_Gaz_counties_national.zip) and [population-center file](https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt) | `counties.csv` | 2019 target identity joined to 2020 coordinates by exact FIPS; the one reviewed bridge is legacy Valdez-Cordova `02261` to positive-population-weighted `02063`/`02066`; 50 states, DC, and Puerto Rico; other Island Areas absent |
| AQI | EPA AirData, pinned two complete years | First use: [EPA listing](https://aqs.epa.gov/aqsweb/airdata/download_files.html), then HTTPS GET pinned annual county ZIPs | `aqi-release-discovery.json`, annual raw files, `aqi-crosswalk.csv` | Monitored-day annualization; unmatched names remain missing |
| Walkability | EPA Smart Location Database 3.0, 2021 | HTTPS GET [official CSV](https://edg.epa.gov/data/public/OA/EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv) | `walkability.csv` | Counties without valid population-weighted data remain missing |
| Heat and cold | NOAA daily normals 2006–2020; shared Census 2020 county coordinates | HTTPS GET [NOAA archive](https://www.ncei.noaa.gov/data/normals-daily/2006-2020/archive/us-climate-normals_2006-2020_v1.0.1_daily_temperature_by-variable_c20230403.tar.gz); coordinates are acquired with the county source | `temperature.csv` | Station support and interpolation limits are explicit |
| Snowfall | NOAA annual/seasonal normals 2006–2020; shared Census 2020 county coordinates | HTTPS GET [NOAA archive](https://www.ncei.noaa.gov/data/normals-annualseasonal/2006-2020/archive/us-climate-normals_2006-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz); coordinates are acquired with the county source | `snowfall.csv` | Requires at least ten years of station support |
| Drought | U.S. Drought Monitor county statistics | HTTPS GET [county statistics service](https://usdmdataservices.unl.edu/api/ConsecutiveNonConsecutiveStatistics/GetNonConsecutiveStatisticsCounty) with the configured dates and `minimumweeks=0` | `drought.csv` | Censored or absent county rows remain missing |
| CBP base | Census CBP and PEP, 2023 | HTTPS GET [CBP ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip) and [PEP CSV](https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv) | `cbp-source.csv`, `cbp-densities.csv` | Disclosure suppression is not treated as zero |
| Groceries | USDA Food Environment Atlas 2025 release, 2019 indicators | HTTPS GET [FEA ZIP](https://www.ers.usda.gov/media/5570/food-environment-atlas-csv-files.zip?v=18315) | `grocery.csv` | Sentinel values and incomplete USDA rows remain missing |
| Tradespeople | BLS OEWS May 2025 special-request files | HTTPS GET [national ZIP](https://www.bls.gov/oes/special-requests/oesm25all.zip), [state ZIP](https://www.bls.gov/oes/special-requests/oesm25st.zip), [metro ZIP](https://www.bls.gov/oes/special-requests/oesm25ma.zip), and [industry ZIP](https://www.bls.gov/oes/special-requests/oesm25in4.zip) | `oews-national.csv`, `oews-state-shares.csv`, `oews-metro-shares.csv`, `oews-industry-share.json`, `oews-county-cbsa.csv`, `tradespeople.csv` | Suppressed occupations and unavailable local shares remain visible |
| FEMA | FEMA National Risk Index v1.20, December 2025 | Paged HTTPS queries to the [county service](https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0/query) | `fema-hazard-burden.csv`, `fema-resilience.csv` | Composite indices retain FEMA source limitations |
| Transit | EPA Access to Jobs and Workers via Transit, 2013 Trans45 | HTTPS GET [Trans45 DBF ZIP](https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip) | `transit.csv` | Published GTFS-served regions only; uncovered counties remain missing |
| Housing | Zillow Research three-bedroom county ZHVI | HTTPS GET [county CSV](https://files.zillowstatic.com/research/public_csvs/zhvi/County_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv) | `housing.csv` | Missing county values remain missing |
