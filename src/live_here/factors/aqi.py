"""Port of measured AQI calculation; deliberately excludes old-value imputation."""

import calendar
from collections import defaultdict
from statistics import mean

from ..io import csv_rows, fips, number

BAD_DAY_COLUMNS = (
    "Unhealthy for Sensitive Groups Days", "Unhealthy Days",
    "Very Unhealthy Days", "Hazardous Days",
)


def calculate(paths, counties, crosswalk_path):
    mapping = {}
    for row in csv_rows(crosswalk_path, ["State", "County", "fips", "geography_vintage"]):
        key = (row["State"].strip(), row["County"].strip())
        code = fips(row["fips"])
        if key in mapping:
            raise ValueError(f"Duplicate AQI name mapping: {key}")
        if code not in counties or row["geography_vintage"] != counties[code]["geography_vintage"]:
            raise ValueError(f"AQI crosswalk geography mismatch: {key}")
        mapping[key] = code
    observations = defaultdict(list)
    seen = set()
    unmatched = set()
    for path in paths:
        for row in csv_rows(path, ["State", "County", "Year", "Days with AQI", *BAD_DAY_COLUMNS]):
            name = (row["State"].strip(), row["County"].strip())
            if name not in mapping:
                unmatched.add(name)
                continue
            code = mapping[name]
            year = int(row["Year"])
            if not 1900 <= year <= 2200:
                raise ValueError(f"Invalid AQI year {year}")
            if (code, year) in seen:
                raise ValueError(f"Duplicate county/year AQI observation: {code}/{year}")
            seen.add((code, year))
            days = number(row["Days with AQI"], "Days with AQI", 0, 366 if calendar.isleap(year) else 365)
            counts = [number(row[c], c, 0) for c in BAD_DAY_COLUMNS]
            if not days.is_integer() or any(not c.is_integer() for c in counts):
                raise ValueError("AQI day counts must be integers")
            bad = sum(counts)
            if bad > days:
                raise ValueError(f"Bad AQI days exceed monitored days: {code}/{year}")
            if days:
                observations[code].append((year, bad / days * 365.25, days))
    result = {}
    for code, records in observations.items():
        records.sort()
        result[code] = {
            "value": mean(r[1] for r in records), "value_status": "derived",
            "observation_period": ",".join(str(r[0]) for r in records),
            "method": "mean(bad_days / monitored_days * 365.25) by county-year",
            "quality_note": f"min_monitored_days={min(r[2] for r in records):g}; annualization assumes observed days are representative",
        }
    return result, {"unmatched_source_names": [list(k) for k in sorted(unmatched)],
                    "zero_monitoring_county_years": len(seen) - sum(len(v) for v in observations.values())}
