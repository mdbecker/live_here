# Specialty Grocery Density Workbook Guide

## City Density Ranking
- Use this sheet for the **city-level** ranking.
- The new **County** column uses the exact county/county-equivalent naming found in `rankings.csv`.
- Join to the reference table using **County + State**. County names are not unique nationwide.

## County Density Ranking
- This sheet aggregates the city rows by county.
- **Proxy / Lower-Bound Stores** is the sum of the store-count columns for cities assigned to that county.
- **Stores per sq mi** = aggregated proxy/lower-bound stores ÷ **county land area**.
- Counties are ranked from highest to lowest density.
- **County FIPS** is included as the safest join key when available.

## Important caveats
- The workbook is still a **recovery/proxy dataset**, not the final exact store-by-store GIS result.
- County totals aggregate city rows and do **not** deduplicate stores that could be counted by overlapping 5-mile city catchments.
- Cities spanning multiple counties are assigned one primary/central county because the city table has a single County field.

## Other sheets
- **Chain Coverage**: chains included in the original scope and which are represented in the proxy counts.
- **Methodology**: calculation details and limitations.
- **Sources**: store-directory, Census, and county-reference sources.
