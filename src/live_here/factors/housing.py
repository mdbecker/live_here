"""Source-only Zillow county three-bedroom ZHVI adapter."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path


DATE_COLUMN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
METHOD = "Zillow county three-bedroom ZHVI"


def safe_number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _fips(value, width):
    text = str(value or "").strip()
    if not text or not text.isdigit():
        return None
    text = text.split(".", 1)[0].zfill(width)
    return text if len(text) == width else None


def read_zillow_county_csv(path: Path, observation_month: str | None = None):
    """Read one fixed monthly observation from Zillow's county CSV.

    The CSV contains a time series.  A single selected month is used for every
    county so that the output never mixes observation dates.  Missing values
    remain missing and are not filled from another county or a prior workbook.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        dates = [field for field in fields if DATE_COLUMN.fullmatch(field or "")]
        if not dates:
            raise ValueError("Zillow CSV has no YYYY-MM-DD monthly columns")
        month = observation_month or dates[-1]
        if month not in dates:
            raise ValueError(f"Zillow observation month is not present: {month}")
        rows = {}
        duplicates = 0
        county_rows = 0
        for raw in reader:
            if str(raw.get("RegionType", "")).strip().lower() != "county":
                continue
            state = _fips(raw.get("StateCodeFIPS"), 2)
            county = _fips(raw.get("MunicipalCodeFIPS"), 3)
            if state is None or county is None:
                continue
            fips = state + county
            county_rows += 1
            if fips in rows:
                duplicates += 1
            rows[fips] = {
                "fips": fips,
                "value": safe_number(raw.get(month)),
                "month": month,
                "region_id": raw.get("RegionID"),
                "region_name": raw.get("RegionName"),
                "state_name": raw.get("StateName"),
                "state": raw.get("State"),
                "metro": raw.get("Metro"),
            }
    return rows, month, {"county_rows": county_rows, "matched_counties": len(rows), "duplicate_fips": duplicates,
                         "missing_count": sum(1 for row in rows.values() if row["value"] is None)}


def calculate(rows_by_fips, observation_month: str | None = None):
    """Return normalized dollar observations while retaining source missingness."""
    result = {}
    missing = 0
    for fips, row in rows_by_fips.items():
        if observation_month and row.get("month") != observation_month:
            raise ValueError(f"Housing row {fips} has a different observation month")
        value = safe_number(row.get("value"))
        if value is None:
            missing += 1
            continue
        result[fips] = {
            "value": value,
            "unit": "USD",
            "value_status": "derived_source",
            "method": METHOD,
            "quality_note": "Zillow Research smoothed, seasonally adjusted county ZHVI; no fallback or legacy scale mapping",
            "observation_period": row.get("month") or observation_month or "",
        }
    return result, {"rows_read": len(rows_by_fips), "matched_counties": len(result),
                    "missing_count": missing, "observation_month": observation_month or ""}
