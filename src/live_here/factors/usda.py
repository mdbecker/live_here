"""USDA Food Environment access adjustment for CBP grocery density."""

from __future__ import annotations

import csv
import math
import zipfile
from collections import defaultdict
from pathlib import Path


ACCESS_INDICATOR_CODES = (
    "PCT_LACCESS_POP19",
    "PCT_LACCESS_LOWI19",
    "PCT_LACCESS_HHNV19",
)
ACCESS_INDICATOR_OBSERVATION_PERIOD = "2019"
PERCENTILE_COHORT = "national_usda_fea_rows_with_all_three_2019_access_indicators"


def safe_number(value):
    text = str(value or "").strip()
    if not text or text in {"-9999", "-8888", "-9999.0", "-8888.0", "NA", "N/A"}:
        return None
    try:
        number = float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def access_multiplier(hardship):
    try:
        value = float(hardship)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return max(0.65, min(1.0, 1.0 - 0.35 * max(0.0, min(1.0, value))))


def read_atlas_zip(path):
    with zipfile.ZipFile(path) as archive:
        member = next((name for name in archive.namelist() if name.lower().endswith("stateandcountydata.csv")), None)
        if member is None:
            raise ValueError("USDA archive lacks StateAndCountyData.csv")
        output = defaultdict(dict)
        with archive.open(member) as stream:
            reader = csv.DictReader((line.decode("utf-8-sig", "replace") for line in stream))
            for row in reader:
                fips = str(row.get("FIPS", "")).strip().zfill(5)
                code = str(row.get("Variable_Code", "")).strip()
                value = safe_number(row.get("Value"))
                if len(fips) == 5 and code and value is not None:
                    output[fips][code] = value
        return dict(output)


def percentile_scores(values):
    """Return 0..1 ascending percentiles using average positions for ties."""
    clean = [float(v) for v in values]
    if not clean:
        return []
    order = sorted(range(len(clean)), key=lambda i: clean[i])
    scores = [0.5] * len(clean)
    if len(clean) == 1:
        return scores
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and clean[order[end]] == clean[order[start]]:
            end += 1
        score = ((start + end - 1) / 2) / (len(clean) - 1)
        for position in range(start, end):
            scores[order[position]] = score
        start = end
    return scores


def calculate_grocery(cbp_rows, atlas_rows):
    """Apply access adjustment to CBP grocery density where all inputs exist."""
    keys = sorted(set(cbp_rows) & set(atlas_rows))
    raw = []
    for fips in keys:
        row = atlas_rows[fips]
        values = [row.get(code) for code in ACCESS_INDICATOR_CODES]
        if all(value is not None for value in values):
            raw.append((fips, values))
    percentiles = [percentile_scores([values[i] for _, values in raw]) for i in range(3)]
    output = {}
    for index, (fips, _) in enumerate(raw):
        base = safe_number(cbp_rows[fips].get("grocery_establishments_per_10k"))
        if base is None:
            continue
        hardship = 0.60 * percentiles[0][index] + 0.25 * percentiles[1][index] + 0.15 * percentiles[2][index]
        output[fips] = {"value": base * access_multiplier(hardship), "value_status": "derived_usda_access_adjusted",
                        "method": "cbp_grocery_density_times_usda_low_access_multiplier",
                        "quality_note": f"hardship_percentile={hardship:.6f}; percentile_cohort={PERCENTILE_COHORT}; cohort_n={len(raw)}"}
    return output, {
        "matched_counties": len(output),
        "eligible_usda_rows": len(raw),
        "missing_or_suppressed": len(keys) - len(raw),
        "percentile_cohort": PERCENTILE_COHORT,
        "percentile_cohort_count": len(raw),
        "access_indicator_codes": list(ACCESS_INDICATOR_CODES),
        "access_indicator_observation_period": ACCESS_INDICATOR_OBSERVATION_PERIOD,
    }
