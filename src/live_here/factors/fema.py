"""Source-only FEMA National Risk Index county composites."""

from __future__ import annotations

import csv
import io
import math
import statistics
import zipfile
from pathlib import Path


ALL_HAZARD_PREFIXES = [
    "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN", "ISTM",
    "IFLD", "LNDS", "LTNG", "SWND", "TRND", "TSUN", "VLCN", "WFIR", "WNTW",
]
CLIMATE_HAZARD_PREFIXES = ["CFLD", "CWAV", "DRGT", "HWAV", "HRCN", "IFLD", "SWND", "WFIR", "WNTW"]
REQUIRED_NRI_FIELDS = {
    "STCOFIPS", "EAL_SCORE", "ALR_VRA_NPCTL", "SOVI_SCORE", "RESL_SCORE",
    *{f"{prefix}_{suffix}" for prefix in ALL_HAZARD_PREFIXES for suffix in ("AFREQ", "EVNTS")},
    *{f"{prefix}_RISKS" for prefix in CLIMATE_HAZARD_PREFIXES},
}


def safe_number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number in {-9999.0, -999.0, -8888.0}:
        return None
    return number


def _bounded(value):
    return max(0.0, min(100.0, float(value)))


def hazard_burden_score(expected_annual_loss, adjusted_loss_percentile, frequency_percentile):
    """Return the NRI disaster burden composite on FEMA's 0--100 scale."""
    values = [safe_number(v) for v in (expected_annual_loss, adjusted_loss_percentile, frequency_percentile)]
    if any(v is None for v in values):
        return None
    return _bounded(0.40 * values[0] + 0.30 * values[1] + 0.30 * values[2])


def resilience_score(community_resilience, climate_hazard_risk, adjusted_loss_percentile, social_vulnerability):
    """Return source-only FEMA resilience composite; higher values are better."""
    values = [safe_number(v) for v in (community_resilience, climate_hazard_risk, adjusted_loss_percentile, social_vulnerability)]
    if any(v is None for v in values):
        return None
    return _bounded(0.45 * values[0] + 0.30 * (100.0 - values[1]) +
                    0.15 * (100.0 - values[2]) + 0.10 * (100.0 - values[3]))


def percentile_scores(values):
    """Percentile ranks in [0, 1], with tied values receiving their mean rank."""
    pairs = sorted((float(v), i) for i, v in enumerate(values))
    out = [0.0] * len(pairs)
    n = len(pairs)
    i = 0
    while i < n:
        j = i + 1
        while j < n and pairs[j][0] == pairs[i][0]:
            j += 1
        position = (i + j - 1) / 2.0
        pct = 0.0 if n <= 1 else position / (n - 1)
        for k in range(i, j):
            out[pairs[k][1]] = pct
        i = j
    return out


def _csv_stream(source: Path):
    if source.suffix.lower() == ".zip":
        archive = zipfile.ZipFile(source)
        member = next((name for name in archive.namelist() if name.lower().endswith("nri_table_counties.csv")), None)
        if member is None:
            archive.close()
            raise ValueError(f"{source} does not contain NRI_Table_Counties.csv")
        raw = archive.read(member)
        archive.close()
        return io.StringIO(raw.decode("utf-8-sig", errors="replace"))
    return source.open(newline="", encoding="utf-8-sig")


def _first(row, *names):
    for name in names:
        if name in row:
            return row[name]
    return None


def _component(value):
    """Classify a required NRI component without treating unavailable data as zero.

    FEMA's published county table uses blank component cells for hazards that are
    not applicable to a county. Those cells contribute zero frequency and no
    climate-risk component. A sentinel or malformed nonblank cell is unavailable
    data, which keeps the dependent composite missing.
    """
    if value is None or str(value).strip() == "":
        return 0.0, "non_applicable"
    number = safe_number(value)
    return (number, "reported") if number is not None else (None, "unavailable")


def _row_metrics(raw):
    frequency_components = [_component(raw[f"{prefix}_AFREQ"]) for prefix in ALL_HAZARD_PREFIXES]
    event_components = [_component(raw[f"{prefix}_EVNTS"]) for prefix in ALL_HAZARD_PREFIXES]
    climate_components = [_component(raw[f"{prefix}_RISKS"]) for prefix in CLIMATE_HAZARD_PREFIXES]
    frequency = None if any(state == "unavailable" for _, state in frequency_components) else sum(value for value, _ in frequency_components)
    event_sum = None if any(state == "unavailable" for _, state in event_components) else sum(value for value, _ in event_components)
    climate = [value for value, state in climate_components if state == "reported"]
    climate_risk = None if any(state == "unavailable" for _, state in climate_components) else (statistics.mean(climate) if climate else None)
    return {
        "fips": str(_first(raw, "STCOFIPS", "COUNTYFIPS", "NRI_ID") or "").zfill(5),
        "county": str(raw.get("COUNTY", "")).strip(),
        "state": str(raw.get("STATEABBRV", "")).strip(),
        "population": safe_number(raw.get("POPULATION")),
        "expected_annual_loss_score": safe_number(raw.get("EAL_SCORE")),
        "adjusted_loss_percentile": safe_number(raw.get("ALR_VRA_NPCTL")),
        "loss_percentile": safe_number(raw.get("ALR_NPCTL")),
        "social_vulnerability": safe_number(raw.get("SOVI_SCORE")),
        "community_resilience": safe_number(raw.get("RESL_SCORE")),
        "hazard_frequency_per_year": frequency,
        "hazard_frequency_per_decade": frequency * 10.0 if frequency is not None else None,
        "hazard_event_count": event_sum,
        "climate_hazard_risk_score": climate_risk,
        "frequency_component_count": sum(state == "reported" for _, state in frequency_components),
        "frequency_non_applicable_component_count": sum(state == "non_applicable" for _, state in frequency_components),
        "frequency_unavailable_component_count": sum(state == "unavailable" for _, state in frequency_components),
        "event_component_count": sum(state == "reported" for _, state in event_components),
        "event_non_applicable_component_count": sum(state == "non_applicable" for _, state in event_components),
        "event_unavailable_component_count": sum(state == "unavailable" for _, state in event_components),
        "climate_hazard_component_count": sum(state == "reported" for _, state in climate_components),
        "climate_non_applicable_component_count": sum(state == "non_applicable" for _, state in climate_components),
        "climate_unavailable_component_count": sum(state == "unavailable" for _, state in climate_components),
    }


def read_nri_zip(source: Path):
    """Read the FEMA county table from ZIP or CSV and return rows plus audit."""
    source = Path(source)
    with _csv_stream(source) as stream:
        reader = csv.DictReader(stream)
        missing = sorted(REQUIRED_NRI_FIELDS - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"missing required NRI fields: {', '.join(missing)}")
        rows = [_row_metrics(row) for row in reader if any(str(v or "").strip() for v in row.values())]
    rows = [row for row in rows if row["fips"] != "00000"]
    audit = {"rows_read": len(rows), "source": source.name,
             "required_component_headers": len(REQUIRED_NRI_FIELDS),
             "non_applicable_frequency_components": sum(row["frequency_non_applicable_component_count"] for row in rows),
             "unavailable_frequency_components": sum(row["frequency_unavailable_component_count"] for row in rows),
             "non_applicable_event_components": sum(row["event_non_applicable_component_count"] for row in rows),
             "unavailable_event_components": sum(row["event_unavailable_component_count"] for row in rows),
             "non_applicable_climate_risk_components": sum(row["climate_non_applicable_component_count"] for row in rows),
             "unavailable_climate_risk_components": sum(row["climate_unavailable_component_count"] for row in rows),
             "rows_with_unavailable_frequency_components": sum(row["frequency_unavailable_component_count"] > 0 for row in rows),
             "rows_with_unavailable_climate_risk_components": sum(row["climate_unavailable_component_count"] > 0 for row in rows)}
    return {row["fips"]: row for row in rows}, audit


def calculate_factors(rows_by_fips):
    """Build hazard-burden and resilience normalized rows from NRI counties."""
    rows = list(rows_by_fips.values())
    frequency_rows = [row for row in rows if row["hazard_frequency_per_decade"] is not None]
    percentiles = dict(zip((row["fips"] for row in frequency_rows), percentile_scores([row["hazard_frequency_per_decade"] for row in frequency_rows])))
    burden, resilience = {}, {}
    for row in rows:
        pct = percentiles.get(row["fips"])
        burden_value = hazard_burden_score(row["expected_annual_loss_score"], row["adjusted_loss_percentile"], pct * 100.0) if pct is not None else None
        resilience_value = resilience_score(row["community_resilience"], row["climate_hazard_risk_score"], row["adjusted_loss_percentile"], row["social_vulnerability"])
        common = {"fips": row["fips"], "value_status": "derived_source", "method": "FEMA NRI v1.20 source-only composite", "quality_note": "Official FEMA county service; no legacy workbook scale mapping", "observation_period": "FEMA NRI v1.20 (December 2025)"}
        if burden_value is not None:
            burden[row["fips"]] = {**common, "value": burden_value}
        if resilience_value is not None:
            resilience[row["fips"]] = {**common, "value": resilience_value}
    return burden, resilience, {"rows_read": len(rows), "burden_rows": len(burden), "resilience_rows": len(resilience),
                                "frequency_eligible_rows": len(frequency_rows),
                                "frequency_ineligible_rows": len(rows) - len(frequency_rows)}
