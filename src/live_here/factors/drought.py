"""Source-only U.S. Drought Monitor D1+ frequency calculations."""

from __future__ import annotations

import csv
import math
from pathlib import Path


MISSING_SENTINELS = {-9999.0, -999.0, -8888.0}


def safe_number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number in MISSING_SENTINELS:
        return None
    return number


def days_per_year_from_weeks(weeks, window_years):
    """Annualize observed D1+ weeks without turning censored rows into zero."""
    value = safe_number(weeks)
    years = safe_number(window_years)
    if value is None or years is None or years <= 0 or value < 0:
        return None
    return value * 7.0 / years


def _first(row, *names):
    for name in names:
        if name in row:
            return row[name]
    return None


def normalize_drought_row(row, window_years=10.0, observation_period=""):
    """Normalize one official USDM weeks-in-drought row.

    The official REST export uses ``FIPS``, ``State``, ``County`` and
    ``NonConsecutiveWeeks``. A few downloaded exports use a hyphen in the last
    header, so both spellings are accepted. Missing/censored weeks return
    ``None`` to keep coverage explicit.
    """
    raw_fips = _first(row, "FIPS", "fips", "County FIPS")
    fips = str(raw_fips or "").strip()
    if not fips.isdigit() or len(fips) > 5:
        return None
    weeks = _first(row, "NonConsecutiveWeeks", "Non-Consecutive Weeks", "non_consecutive_weeks")
    value = days_per_year_from_weeks(weeks, window_years)
    if value is None:
        return None
    return {
        "fips": fips.zfill(5),
        "value": value,
        "value_status": "derived_source",
        "method": "USDM D1+ non-consecutive weeks × 7 / declared window years",
        "quality_note": "Observed U.S. Drought Monitor frequency; missing/censored rows remain missing",
        "observation_period": observation_period,
        "state": str(_first(row, "State", "state") or "").strip(),
        "county": str(_first(row, "County", "Name", "county") or "").strip(),
        "weeks": safe_number(weeks),
    }


def read_drought_csv(path: Path, window_years=10.0, observation_period=""):
    """Read a USDM county export and return usable rows keyed by FIPS plus audit."""
    path = Path(path)
    rows = {}
    rows_read = 0
    unusable = 0
    duplicates = 0
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for raw in csv.DictReader(stream):
            if not any(str(value or "").strip() for value in raw.values()):
                continue
            rows_read += 1
            row = normalize_drought_row(raw, window_years, observation_period)
            if row is None:
                unusable += 1
                continue
            if row["fips"] in rows:
                duplicates += 1
                raise ValueError(f"Duplicate drought source FIPS: {row['fips']}")
            rows[row["fips"]] = row
    return rows, {"rows_read": rows_read, "usable_rows": len(rows), "unusable_rows": unusable,
                  "duplicate_rows": duplicates, "source": path.name,
                  "window_years": float(window_years), "observation_period": observation_period}
