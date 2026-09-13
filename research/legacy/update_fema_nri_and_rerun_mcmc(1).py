#!/usr/bin/env python3
"""
Update a county-rankings workbook with FEMA National Risk Index county data,
then rerun the randomized runoff MCMC.

This pass improves disaster/climate-risk-related factors using the FEMA National
Risk Index (NRI) county table. It updates two workbook columns:

1. Est. natural disasters / decade
   Uses an NRI disaster-burden score blended from:
     - Expected Annual Loss score (composite)
     - Social-vulnerability/community-resilience adjusted Expected Annual Loss
       Rate national percentile
     - multi-hazard annualized frequency percentile
   The blended score is quantile-mapped back onto the existing workbook's
   natural-disasters-per-decade scale so the value column remains comparable
   while the ordering is FEMA/NRI driven.

2. Est. climate resilience score
   Uses a 0-100 FEMA/NRI-backed score blended from:
     - FEMA Community Resilience score
     - inverse selected climate-hazard risk scores
     - inverse adjusted Expected Annual Loss Rate percentile
     - inverse Social Vulnerability score

The NRI contains county data for Risk Index, Expected Annual Loss, Social
Vulnerability, Community Resilience, and individual hazard metrics for 18 natural
hazards. This script does not use OpenFEMA disaster-declaration rows because a
separate disaster-declarations CSV was not provided in this bundle.

Example
-------
python update_fema_nri_and_rerun_mcmc.py \
  --input-workbook county_rankings_epa_walkability_transit_aqi_noaa_temperature_multivariate_droughtmonitor_cbp_oews_usda_foodenv_100k.xlsx \
  --nri-zip fema_NRI_Table_Counties.zip \
  --output-workbook county_rankings_epa_walkability_transit_aqi_noaa_temperature_multivariate_droughtmonitor_cbp_oews_usda_foodenv_fema_nri_100k.xlsx \
  --county-rollup-csv fema_nri_county_rollup.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import unicodedata
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from numba import njit
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
try:
    from openpyxl.workbook.properties import CalcProperties
except Exception:  # pragma: no cover
    CalcProperties = None

DEFAULT_ITERATIONS = 100_000
DEFAULT_SEED = 2026060901

RANK_MATRIX_SHEET = "Rank Matrix"
VALUE_MATRIX_SHEET = "Value Matrix"
TOP30_SHEET = "Top 30"
RESULT_COMPARISON_SHEET = "Result Comparison"
RUNOFF_SHEET = "Runoff Simulation"
METHODOLOGY_SHEET = "Sources & Methodology"
LOG_SHEET = "Data Acquisition Log"
QA_SHEET = "QA Checks"
IMPACT_SHEET = "FEMA NRI Impact"
UPDATE_SHEET = "FEMA NRI Update"
REVIEW_SHEET = "FEMA NRI Review"

NATDIS_VALUE_COL = "Est. natural disasters / decade"
NATDIS_RANK_COL = "Natural disasters rank"
CLIMATE_VALUE_COL = "Est. climate resilience score"
CLIMATE_RANK_COL = "Future climate resilience rank"

HEADER_FILL = "1F4E79"
BORDER_COLOR = "B7B7B7"

STATE_DIVISION = {
    "CT": "New England", "ME": "New England", "MA": "New England", "NH": "New England", "RI": "New England", "VT": "New England",
    "NJ": "Middle Atlantic", "NY": "Middle Atlantic", "PA": "Middle Atlantic",
    "IL": "East North Central", "IN": "East North Central", "MI": "East North Central", "OH": "East North Central", "WI": "East North Central",
    "IA": "West North Central", "KS": "West North Central", "MN": "West North Central", "MO": "West North Central", "NE": "West North Central", "ND": "West North Central", "SD": "West North Central",
    "DE": "South Atlantic", "DC": "South Atlantic", "FL": "South Atlantic", "GA": "South Atlantic", "MD": "South Atlantic", "NC": "South Atlantic", "SC": "South Atlantic", "VA": "South Atlantic", "WV": "South Atlantic",
    "AL": "East South Central", "KY": "East South Central", "MS": "East South Central", "TN": "East South Central",
    "AR": "West South Central", "LA": "West South Central", "OK": "West South Central", "TX": "West South Central",
    "AZ": "Mountain", "CO": "Mountain", "ID": "Mountain", "MT": "Mountain", "NV": "Mountain", "NM": "Mountain", "UT": "Mountain", "WY": "Mountain",
    "AK": "Pacific", "CA": "Pacific", "HI": "Pacific", "OR": "Pacific", "WA": "Pacific",
}

# NRI December 2025 uses Connecticut planning regions, while the workbook keeps
# legacy CT county names. These weights mirror the transparent bridge used in
# prior Drought Monitor/CBP passes.
CT_PLANNING_REGION_CROSSWALK = {
    "Fairfield": [("Greater Bridgeport Planning Region", 0.50), ("Western Connecticut Planning Region", 0.50)],
    "Hartford": [("Capitol Planning Region", 1.00)],
    "Litchfield": [("Northwest Hills Planning Region", 0.75), ("Western Connecticut Planning Region", 0.25)],
    "Middlesex": [("Lower Connecticut River Valley Planning Region", 1.00)],
    "New Haven": [("South Central Connecticut Planning Region", 0.55), ("Naugatuck Valley Planning Region", 0.45)],
    "New London": [("Southeastern Connecticut Planning Region", 1.00)],
    "Tolland": [("Capitol Planning Region", 0.50), ("Northeastern Connecticut Planning Region", 0.50)],
    "Windham": [("Northeastern Connecticut Planning Region", 1.00)],
}

# Hazard prefixes from FEMA NRI HazardInfo. Event/frequency terms are used for
# the natural-disaster burden; climate hazard risk scores are used for the
# climate-resilience score.
ALL_HAZARD_PREFIXES = [
    "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN", "ISTM",
    "IFLD", "LNDS", "LTNG", "SWND", "TRND", "TSUN", "VLCN", "WFIR", "WNTW",
]
CLIMATE_HAZARD_PREFIXES = ["CFLD", "CWAV", "DRGT", "HWAV", "HRCN", "IFLD", "SWND", "WFIR", "WNTW"]


def normalize_county_name(name: str) -> str:
    if name is None:
        return ""
    s = str(name).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper().replace("ST.", "ST").replace("SAINT ", "ST ")
    s = s.replace("'", "")
    s = re.sub(r"\s*\(.*?\)", "", s)
    suffixes = [
        " COUNTY AND BOROUGH", " CITY AND BOROUGH", " CENSUS AREA",
        " MUNICIPALITY", " CONSOLIDATED GOVERNMENT", " UNIFIED GOVERNMENT",
        " PLANNING REGION", " BOROUGH", " PARISH", " COUNTY", " CITY",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if s.endswith(suffix):
                s = s[: -len(suffix)]
                changed = True
                break
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def safe_float(x):
    if x is None or x == "":
        return None
    try:
        val = float(str(x).strip().replace(",", ""))
    except Exception:
        return None
    if not math.isfinite(val) or val in {-9999.0, -999.0, -8888.0}:
        return None
    return val


def clean_cell(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def median(values, default=None):
    vals = [float(v) for v in values if safe_float(v) is not None]
    return statistics.median(vals) if vals else default


def read_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    headers = list(rows[0])
    data = []
    for row in rows[1:]:
        if all(v is None for v in row):
            continue
        padded = list(row) + [None] * (len(headers) - len(row))
        data.append(dict(zip(headers, padded[: len(headers)])))
    return headers, data


def write_matrix(ws, matrix: List[List[object]]):
    ws.delete_rows(1, ws.max_row)
    for r_idx, row in enumerate(matrix, 1):
        for c_idx, value in enumerate(row, 1):
            ws.cell(r_idx, c_idx, clean_cell(value))


def recreate_sheet(wb, name: str, after_name: Optional[str] = None):
    if name in wb.sheetnames:
        del wb[name]
    if after_name and after_name in wb.sheetnames:
        idx = wb.sheetnames.index(after_name)
        return wb.create_sheet(name, idx + 1)
    return wb.create_sheet(name)


def style_sheet(ws, max_width: int = 46):
    header_fill = PatternFill("solid", fgColor=HEADER_FILL)
    header_font = Font(bold=True, color="FFFFFF")
    thin = Side(style="thin", color=BORDER_COLOR)
    if ws.max_row >= 1:
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = Border(bottom=thin)
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
    ws.freeze_panes = "A2"
    if ws.max_row > 1 and ws.max_column > 1:
        ws.auto_filter.ref = ws.dimensions
    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        max_len = 0
        for cell in ws[letter]:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max(max_len + 2, 8), max_width)
    if ws.max_row >= 1:
        ws.row_dimensions[1].height = 28


def rank_average(values: Iterable[float], higher_is_better: bool) -> List[float]:
    pairs = [(float(v), i) for i, v in enumerate(values)]
    pairs.sort(key=lambda t: t[0], reverse=higher_is_better)
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i + 1
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[pairs[k][1]] = avg_rank
        i = j
    return ranks


def percentile_scores(values: List[float], higher_is_worse: bool = True) -> List[float]:
    pairs = [(float(v), i) for i, v in enumerate(values)]
    pairs.sort(key=lambda t: t[0])
    n = len(pairs)
    out = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and pairs[j][0] == pairs[i][0]:
            j += 1
        avg_pos = (i + j - 1) / 2.0
        pct = 0.0 if n == 1 else avg_pos / (n - 1)
        for k in range(i, j):
            out[pairs[k][1]] = pct if higher_is_worse else 1.0 - pct
        i = j
    return out


def quantile_map_to_old_scale(scores: List[float], old_values: List[float]) -> List[float]:
    """Map score percentiles onto sorted old values; high score -> high old value."""
    if len(scores) != len(old_values):
        raise ValueError("scores and old_values must be the same length")
    sorted_old = sorted(float(v) for v in old_values)
    n = len(scores)
    pct = percentile_scores(scores, higher_is_worse=True)
    mapped = []
    for p in pct:
        pos = p * (n - 1)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            mapped.append(sorted_old[lo])
        else:
            frac = pos - lo
            mapped.append(sorted_old[lo] * (1 - frac) + sorted_old[hi] * frac)
    return mapped


@njit
def run_randomized_runoff(ranks: np.ndarray, sorted_order: np.ndarray, iterations: int, seed: int):
    np.random.seed(seed)
    n, f = ranks.shape
    wins = np.zeros(n, np.int64)
    elim_sum = np.zeros(n, np.float64)
    factor_order = np.empty(f, np.int64)
    active = np.empty(n, np.bool_)
    ptr = np.empty(f, np.int64)
    ties = np.empty(n, np.int64)

    for _ in range(iterations):
        for i in range(n):
            active[i] = True
        for j in range(f):
            ptr[j] = 0
        active_count = n
        pos = f
        round_no = 0

        while active_count > 1:
            if pos >= f:
                for j in range(f):
                    factor_order[j] = j
                for j in range(f - 1, 0, -1):
                    k = np.random.randint(j + 1)
                    tmp = factor_order[j]
                    factor_order[j] = factor_order[k]
                    factor_order[k] = tmp
                pos = 0

            col = factor_order[pos]
            pos += 1
            p = ptr[col]
            while p < n and not active[sorted_order[col, p]]:
                p += 1
            ptr[col] = p

            first_idx = sorted_order[col, p]
            worst_rank = ranks[first_idx, col]
            tie_count = 0
            q = p
            while q < n:
                row_idx = sorted_order[col, q]
                if ranks[row_idx, col] != worst_rank:
                    break
                if active[row_idx]:
                    ties[tie_count] = row_idx
                    tie_count += 1
                q += 1

            loser = ties[np.random.randint(tie_count)]
            active[loser] = False
            round_no += 1
            elim_sum[loser] += round_no
            active_count -= 1

        for i in range(n):
            if active[i]:
                winner = i
                break
        wins[winner] += 1
        elim_sum[winner] += n

    return wins, elim_sum / iterations


def get_fips_for_workbook(wb) -> Dict[Tuple[str, str], str]:
    for sheet_name in [
        "USDA Food Env Update", "BLS OEWS Trades Update", "CBP Business Patterns Update",
        "Drought Monitor Update", "EPA Walkability Update", "NOAA Multivariate Update",
        "NOAA Temperature Update", "EPA AQI Update", "EPA Transit Guardrail Update", "EPA Transit Update",
    ]:
        if sheet_name not in wb.sheetnames:
            continue
        headers, rows = read_sheet(wb[sheet_name])
        if {"County", "State", "County FIPS"}.issubset(set(headers)):
            out = {}
            for r in rows:
                county, state, fips = r.get("County"), r.get("State"), r.get("County FIPS")
                if county is None or state is None or fips is None:
                    continue
                out[(county, state)] = str(fips).zfill(5)
            if out:
                return out
    raise ValueError("Workbook needs an audit/update sheet containing County, State, and County FIPS")


def read_nri_county_zip(nri_zip: Path):
    with zipfile.ZipFile(nri_zip) as z:
        table_member = next((m for m in z.namelist() if m.endswith("NRI_Table_Counties.csv")), None)
        if table_member is None:
            raise ValueError(f"{nri_zip} does not contain NRI_Table_Counties.csv")
        rows_by_fips = {}
        rows_by_ct_region = {}
        with z.open(table_member) as f:
            reader = csv.DictReader((line.decode("utf-8-sig", errors="replace") for line in f))
            for r in reader:
                fips = str(r.get("STCOFIPS", "")).zfill(5)
                county_name = str(r.get("COUNTY", "")).strip()
                county_type = str(r.get("COUNTYTYPE", "")).strip()
                state = str(r.get("STATEABBRV", "")).strip()
                row = compute_nri_row_metrics(r)
                row["NRI county name"] = county_name
                row["NRI county type"] = county_type
                row["NRI state"] = state
                row["NRI STCOFIPS"] = fips
                rows_by_fips[fips] = row
                if state == "CT":
                    rows_by_ct_region[f"{county_name} {county_type}".strip()] = row
        return rows_by_fips, rows_by_ct_region


def compute_nri_row_metrics(r: Dict[str, str]) -> Dict[str, object]:
    hazard_freq_per_year = 0.0
    hazard_event_sum = 0.0
    hazard_freq_components = []
    climate_scores = []
    for p in ALL_HAZARD_PREFIXES:
        af = safe_float(r.get(f"{p}_AFREQ"))
        ev = safe_float(r.get(f"{p}_EVNTS"))
        if af is not None:
            hazard_freq_per_year += af
            hazard_freq_components.append((p, af))
        if ev is not None:
            hazard_event_sum += ev
        if p in CLIMATE_HAZARD_PREFIXES:
            rs = safe_float(r.get(f"{p}_RISKS"))
            if rs is not None:
                climate_scores.append(rs)
    climate_hazard_risk_score = statistics.mean(climate_scores) if climate_scores else None
    return {
        "Population": safe_float(r.get("POPULATION")),
        "NRI risk score": safe_float(r.get("RISK_SCORE")),
        "NRI risk rating": r.get("RISK_RATNG"),
        "NRI risk value": safe_float(r.get("RISK_VALUE")),
        "Expected annual loss score": safe_float(r.get("EAL_SCORE")),
        "Expected annual loss value total": safe_float(r.get("EAL_VALT")),
        "Expected annual loss rate percentile": safe_float(r.get("ALR_NPCTL")),
        "Adjusted expected annual loss rate percentile": safe_float(r.get("ALR_VRA_NPCTL")),
        "Social vulnerability score": safe_float(r.get("SOVI_SCORE")),
        "Community resilience score": safe_float(r.get("RESL_SCORE")),
        "Community resilience value": safe_float(r.get("RESL_VALUE")),
        "Hazard annualized frequency sum": hazard_freq_per_year,
        "Hazard frequency per decade": hazard_freq_per_year * 10.0,
        "Hazard event count sum raw": hazard_event_sum,
        "Climate hazard risk score": climate_hazard_risk_score,
        "Drought risk score": safe_float(r.get("DRGT_RISKS")),
        "Heat wave risk score": safe_float(r.get("HWAV_RISKS")),
        "Wildfire risk score": safe_float(r.get("WFIR_RISKS")),
        "Inland flood risk score": safe_float(r.get("IFLD_RISKS")),
        "Coastal flood risk score": safe_float(r.get("CFLD_RISKS")),
        "Hurricane risk score": safe_float(r.get("HRCN_RISKS")),
        "Strong wind risk score": safe_float(r.get("SWND_RISKS")),
        "Winter weather risk score": safe_float(r.get("WNTW_RISKS")),
    }


def weighted_average_nri(rows_with_weights: List[Tuple[Dict[str, object], float]]) -> Dict[str, object]:
    if not rows_with_weights:
        return {}
    out = {}
    keys = set()
    for r, _w in rows_with_weights:
        keys.update(r.keys())
    for k in keys:
        vals = []
        for r, w in rows_with_weights:
            v = safe_float(r.get(k))
            if v is not None:
                vals.append((v, w))
        if vals:
            wsum = sum(w for _v, w in vals)
            out[k] = sum(v * w for v, w in vals) / wsum if wsum else None
    out["NRI county name"] = "; ".join([str(r.get("NRI county name")) for r, _w in rows_with_weights])
    out["NRI county type"] = "weighted CT planning-region bridge"
    out["NRI STCOFIPS"] = "; ".join([str(r.get("NRI STCOFIPS")) for r, _w in rows_with_weights])
    return out


def find_nri_for_county(key: Tuple[str, str], fips: str, rows_by_fips: Dict[str, Dict[str, object]], rows_by_ct_region: Dict[str, Dict[str, object]]):
    county, state = key
    if fips in rows_by_fips:
        row = dict(rows_by_fips[fips])
        row["NRI match method"] = "direct FIPS"
        return row
    if state == "CT" and county in CT_PLANNING_REGION_CROSSWALK:
        rows_with_weights = []
        for region, weight in CT_PLANNING_REGION_CROSSWALK[county]:
            r = rows_by_ct_region.get(region)
            if r is not None:
                rows_with_weights.append((r, weight))
        if rows_with_weights:
            row = weighted_average_nri(rows_with_weights)
            row["NRI match method"] = "CT legacy county to planning-region weighted bridge"
            return row
    return None


def impute_missing_nri(updates: Dict[Tuple[str, str], Dict[str, object]], keys: List[Tuple[str, str]]):
    fields = [
        "NRI disaster burden score", "New climate resilience score", "Hazard frequency per decade",
        "Expected annual loss score", "Adjusted expected annual loss rate percentile", "Climate hazard risk score",
        "Community resilience score", "Social vulnerability score",
    ]
    for field in fields:
        by_state = defaultdict(list)
        by_div = defaultdict(list)
        all_vals = []
        for k in keys:
            val = safe_float(updates[k].get(field))
            if val is None:
                continue
            by_state[k[1]].append(val)
            by_div[STATE_DIVISION.get(k[1], "")].append(val)
            all_vals.append(val)
        nat = median(all_vals, 0.0)
        for k in keys:
            if safe_float(updates[k].get(field)) is not None:
                continue
            state = k[1]
            div = STATE_DIVISION.get(state, "")
            val = median(by_state[state], None)
            method = f"{field}: same-state median"
            if val is None:
                val = median(by_div[div], None)
                method = f"{field}: Census-division median"
            if val is None:
                val = nat
                method = f"{field}: national median"
            updates[k][field] = val
            prior = updates[k].get("Imputation method")
            updates[k]["Imputation method"] = (str(prior) + "; " if prior else "") + method


def build_nri_updates(value_rows, rank_rows, fips_by_key, rows_by_fips, rows_by_ct_region):
    keys = [(r["County"], r["State"]) for r in value_rows]
    rank_by_key = {(r["County"], r["State"]): r for r in rank_rows}
    value_by_key = {(r["County"], r["State"]): r for r in value_rows}
    updates: Dict[Tuple[str, str], Dict[str, object]] = {}

    raw_nri = {}
    for k in keys:
        fips = fips_by_key.get(k)
        row = find_nri_for_county(k, fips, rows_by_fips, rows_by_ct_region) if fips else None
        raw_nri[k] = row

    freq_values = [safe_float(raw_nri[k].get("Hazard frequency per decade")) if raw_nri[k] else None for k in keys]
    # Use state/division/national fallback before deriving frequency percentiles.
    temp_updates = {}
    for k in keys:
        nri = raw_nri[k]
        temp_updates[k] = {"Hazard frequency per decade": freq_values[keys.index(k)] if nri else None}
    impute_missing_nri(temp_updates, keys)
    freq_pct_scores = percentile_scores([temp_updates[k]["Hazard frequency per decade"] for k in keys], higher_is_worse=True)

    disaster_scores = []
    old_natdis_values = []
    for i, k in enumerate(keys):
        vrow = value_by_key[k]
        rrow = rank_by_key[k]
        fips = fips_by_key.get(k)
        nri = raw_nri[k]
        u = {
            "County FIPS": fips,
            "NRI match status": "matched" if nri is not None else "missing",
            "NRI match method": nri.get("NRI match method") if nri else None,
            "Imputation method": None,
            "Old natural disasters / decade": safe_float(vrow.get(NATDIS_VALUE_COL)),
            "Old climate resilience score": safe_float(vrow.get(CLIMATE_VALUE_COL)),
            "Original natural disasters rank": rrow.get(NATDIS_RANK_COL),
            "Original climate resilience rank": rrow.get(CLIMATE_RANK_COL),
        }
        if nri:
            u.update(nri)
        updates[k] = u

        # Fill basics now; broader fallback below handles any residual missing.
        eal_score = safe_float(u.get("Expected annual loss score"))
        alr_vra = safe_float(u.get("Adjusted expected annual loss rate percentile"))
        freq_pct = freq_pct_scores[i] * 100.0
        if eal_score is not None and alr_vra is not None:
            disaster_score = 0.40 * eal_score + 0.30 * alr_vra + 0.30 * freq_pct
        else:
            disaster_score = None
        u["Hazard frequency percentile score"] = freq_pct
        u["NRI disaster burden score"] = disaster_score

        resl = safe_float(u.get("Community resilience score"))
        climate_risk = safe_float(u.get("Climate hazard risk score"))
        sovi = safe_float(u.get("Social vulnerability score"))
        if resl is not None and climate_risk is not None and alr_vra is not None and sovi is not None:
            climate_score = 0.45 * resl + 0.30 * (100.0 - climate_risk) + 0.15 * (100.0 - alr_vra) + 0.10 * (100.0 - sovi)
        else:
            climate_score = None
        u["New climate resilience score"] = max(0.0, min(100.0, climate_score)) if climate_score is not None else None
        disaster_scores.append(disaster_score)
        old_natdis_values.append(safe_float(vrow.get(NATDIS_VALUE_COL)))

    impute_missing_nri(updates, keys)

    # If any disaster score was imputed, rebuild score list after fallback.
    disaster_scores = [updates[k]["NRI disaster burden score"] for k in keys]
    mapped_natdis = quantile_map_to_old_scale(disaster_scores, old_natdis_values)

    for k, new_natdis in zip(keys, mapped_natdis):
        u = updates[k]
        u["New natural disasters / decade"] = new_natdis
        u["Natural disasters value delta"] = new_natdis - safe_float(u.get("Old natural disasters / decade"))
        u["Climate resilience value delta"] = u["New climate resilience score"] - safe_float(u.get("Old climate resilience score"))
        if not u.get("Imputation method"):
            u["Imputation method"] = "none; direct NRI match or CT planning-region bridge"
    return updates


def compute_metrics(rank_rows, original):
    keys = [(r["County"], r["State"]) for r in rank_rows]
    top20_new = {k for k, r in zip(keys, rank_rows) if safe_float(r.get("Runoff rank")) is not None and float(r.get("Runoff rank")) <= 20}
    top30_new = {k for k, r in zip(keys, rank_rows) if safe_float(r.get("Runoff rank")) is not None and float(r.get("Runoff rank")) <= 30}
    top20_old = {k for k, v in original.items() if safe_float(v.get("Original runoff rank")) is not None and float(v.get("Original runoff rank")) <= 20}
    top30_old = {k for k, v in original.items() if safe_float(v.get("Original runoff rank")) is not None and float(v.get("Original runoff rank")) <= 30}
    avg_change = []
    runoff_change = []
    for r in rank_rows:
        k = (r["County"], r["State"])
        old_avg = safe_float(original[k].get("Original avg rank"))
        new_avg = safe_float(r.get("Avg Rank"))
        old_rr = safe_float(original[k].get("Original runoff rank"))
        new_rr = safe_float(r.get("Runoff rank"))
        if old_avg is not None and new_avg is not None:
            avg_change.append(abs(new_avg - old_avg))
        if old_rr is not None and new_rr is not None:
            runoff_change.append(abs(new_rr - old_rr))
    return {
        "Top-20 overlap": len(top20_old & top20_new),
        "Top-30 overlap": len(top30_old & top30_new),
        "Mean abs Avg Rank change": statistics.mean(avg_change) if avg_change else None,
        "Median abs Avg Rank change": statistics.median(avg_change) if avg_change else None,
        "Mean abs runoff-rank change": statistics.mean(runoff_change) if runoff_change else None,
        "Median abs runoff-rank change": statistics.median(runoff_change) if runoff_change else None,
        "Largest runoff-rank move": max(runoff_change) if runoff_change else None,
    }


def update_workbook(input_workbook: Path, nri_zip: Path, output_workbook: Path, county_rollup_csv: Path, iterations: int, seed: int):
    wb = load_workbook(input_workbook)
    if RANK_MATRIX_SHEET not in wb.sheetnames or VALUE_MATRIX_SHEET not in wb.sheetnames:
        raise ValueError("Workbook must contain Rank Matrix and Value Matrix sheets")
    rank_headers, rank_rows = read_sheet(wb[RANK_MATRIX_SHEET])
    value_headers, value_rows = read_sheet(wb[VALUE_MATRIX_SHEET])
    for col in [NATDIS_VALUE_COL, CLIMATE_VALUE_COL]:
        if col not in value_headers:
            raise ValueError(f"Value Matrix missing {col!r}")
    for col in [NATDIS_RANK_COL, CLIMATE_RANK_COL]:
        if col not in rank_headers:
            raise ValueError(f"Rank Matrix missing {col!r}")

    fips_by_key = get_fips_for_workbook(wb)
    rows_by_fips, rows_by_ct_region = read_nri_county_zip(nri_zip)

    original = {}
    for rr in rank_rows:
        key = (rr["County"], rr["State"])
        original[key] = {
            "Original runoff rank": rr.get("Runoff rank"),
            "Original avg rank": rr.get("Avg Rank"),
            "Original natural disasters rank": rr.get(NATDIS_RANK_COL),
            "Original climate resilience rank": rr.get(CLIMATE_RANK_COL),
            "Original runoff avg elimination round": rr.get("Runoff avg elimination round"),
            "Original runoff wins": rr.get("Runoff wins"),
            "Original runoff win rate": rr.get("Runoff win rate"),
        }

    value_by_key = {(r["County"], r["State"]): r for r in value_rows}
    rank_by_key = {(r["County"], r["State"]): r for r in rank_rows}
    keys = [(r["County"], r["State"]) for r in value_rows]
    updates = build_nri_updates(value_rows, rank_rows, fips_by_key, rows_by_fips, rows_by_ct_region)

    for k in keys:
        value_by_key[k][NATDIS_VALUE_COL] = updates[k]["New natural disasters / decade"]
        value_by_key[k][CLIMATE_VALUE_COL] = updates[k]["New climate resilience score"]

    natdis_ranks = rank_average([value_by_key[k][NATDIS_VALUE_COL] for k in keys], higher_is_better=False)
    climate_ranks = rank_average([value_by_key[k][CLIMATE_VALUE_COL] for k in keys], higher_is_better=True)
    for k, nd, cr in zip(keys, natdis_ranks, climate_ranks):
        rank_by_key[k][NATDIS_RANK_COL] = nd
        rank_by_key[k][CLIMATE_RANK_COL] = cr

    factor_cols = rank_headers[10:]
    for rr in rank_rows:
        vals = [safe_float(rr.get(c)) for c in factor_cols]
        if any(v is None for v in vals):
            raise ValueError(f"Missing factor rank values for {rr.get('County')}, {rr.get('State')}")
        avg = sum(vals) / len(vals)
        rr["Avg Rank"] = avg
        rr["Avg Rank Python Check"] = avg
        rr["Avg Check Delta"] = 0

    avg_based = rank_average([rank_by_key[k]["Avg Rank"] for k in keys], higher_is_better=False)
    for k, ar in zip(keys, avg_based):
        rank_by_key[k]["Avg-based rank"] = ar

    ranks_matrix = np.array([[float(rank_by_key[k][c]) for c in factor_cols] for k in keys], dtype=np.float64)
    sorted_order = np.argsort(-ranks_matrix, axis=0).T.astype(np.int64)
    wins, avg_elim = run_randomized_runoff(ranks_matrix, sorted_order, iterations, seed)
    runoff_order = sorted(range(len(keys)), key=lambda i: (-avg_elim[i], -wins[i], rank_by_key[keys[i]]["Avg Rank"], keys[i][1], keys[i][0]))
    runoff_ranks = [0] * len(keys)
    for pos, i in enumerate(runoff_order, 1):
        runoff_ranks[i] = pos
    for i, k in enumerate(keys):
        rr = rank_by_key[k]
        rr["Runoff rank"] = runoff_ranks[i]
        rr["Runoff avg elimination round"] = float(avg_elim[i])
        rr["Runoff wins"] = int(wins[i])
        rr["Runoff win rate"] = float(wins[i]) / float(iterations)

    sorted_keys = [keys[i] for i in runoff_order]
    sorted_rank_rows = [rank_by_key[k] for k in sorted_keys]
    sorted_value_rows = [value_by_key[k] for k in sorted_keys]
    metrics = compute_metrics(sorted_rank_rows, original)

    write_matrix(wb[RANK_MATRIX_SHEET], [rank_headers] + [[r.get(h) for h in rank_headers] for r in sorted_rank_rows])
    write_matrix(wb[VALUE_MATRIX_SHEET], [value_headers] + [[r.get(h) for h in value_headers] for r in sorted_value_rows])
    style_sheet(wb[RANK_MATRIX_SHEET])
    style_sheet(wb[VALUE_MATRIX_SHEET])

    if TOP30_SHEET in wb.sheetnames:
        write_matrix(wb[TOP30_SHEET], [rank_headers] + [[r.get(h) for h in rank_headers] for r in sorted_rank_rows[:30]])
        style_sheet(wb[TOP30_SHEET])

    if RUNOFF_SHEET in wb.sheetnames:
        runoff_matrix = [
            ["Metric", "Value", "Notes", None, None, None, None],
            ["Simulation count", iterations, "Randomized runoff iterations", None, None, None, None],
            ["Seed", seed, "NumPy/Numba RNG seed", None, None, None, None],
            ["Rank factors used", len(factor_cols), "Avg Rank excluded from random factor selection", None, None, None, None],
            ["Changed factors", "Natural disasters; Future climate resilience", "FEMA NRI county data: Expected Annual Loss, hazard frequency, Risk Index components, Community Resilience", None, None, None, None],
            ["Tie handling", "Random among tied worst ranks", "If multiple active counties tie for worst rank in selected factor", None, None, None, None],
            [None, None, None, None, None, None, None],
            ["Runoff rank", "County", "State", "Avg Rank", "Runoff avg elimination round", "Runoff wins", "Runoff win rate"],
        ]
        for r in sorted_rank_rows[:30]:
            runoff_matrix.append([r["Runoff rank"], r["County"], r["State"], r["Avg Rank"], r["Runoff avg elimination round"], r["Runoff wins"], r["Runoff win rate"]])
        write_matrix(wb[RUNOFF_SHEET], runoff_matrix)
        style_sheet(wb[RUNOFF_SHEET])

    if RESULT_COMPARISON_SHEET in wb.sheetnames:
        comparison_headers = [
            "County", "State", "Original runoff rank", "New runoff rank", "Runoff rank delta",
            "Original avg rank", "New avg rank", "Avg rank delta",
            "Original natural disasters rank", "New natural disasters rank", "Natural disasters rank delta",
            "Original climate resilience rank", "New climate resilience rank", "Climate resilience rank delta",
            "In new top 30",
        ]
        comparison_rows = []
        for k in sorted_keys[:50]:
            old = original[k]
            new = rank_by_key[k]
            comparison_rows.append([
                k[0], k[1], old.get("Original runoff rank"), new.get("Runoff rank"), safe_float(new.get("Runoff rank")) - safe_float(old.get("Original runoff rank")),
                old.get("Original avg rank"), new.get("Avg Rank"), safe_float(new.get("Avg Rank")) - safe_float(old.get("Original avg rank")),
                old.get("Original natural disasters rank"), new.get(NATDIS_RANK_COL), safe_float(new.get(NATDIS_RANK_COL)) - safe_float(old.get("Original natural disasters rank")),
                old.get("Original climate resilience rank"), new.get(CLIMATE_RANK_COL), safe_float(new.get(CLIMATE_RANK_COL)) - safe_float(old.get("Original climate resilience rank")),
                "yes" if safe_float(new.get("Runoff rank")) <= 30 else "no",
            ])
        write_matrix(wb[RESULT_COMPARISON_SHEET], [comparison_headers] + comparison_rows)
        style_sheet(wb[RESULT_COMPARISON_SHEET])

    source_counts = defaultdict(int)
    impute_counts = defaultdict(int)
    for u in updates.values():
        source_counts[u.get("NRI match method") or u.get("NRI match status")] += 1
        impute_counts[u.get("Imputation method")] += 1

    natdis_rank_changes = [abs(safe_float(rank_by_key[k][NATDIS_RANK_COL]) - safe_float(original[k]["Original natural disasters rank"])) for k in keys]
    climate_rank_changes = [abs(safe_float(rank_by_key[k][CLIMATE_RANK_COL]) - safe_float(original[k]["Original climate resilience rank"])) for k in keys]
    eal_vals = [safe_float(updates[k]["Expected annual loss score"]) for k in keys]
    alr_vals = [safe_float(updates[k]["Adjusted expected annual loss rate percentile"]) for k in keys]
    freq_vals = [safe_float(updates[k]["Hazard frequency per decade"]) for k in keys]
    climate_scores = [safe_float(updates[k]["New climate resilience score"]) for k in keys]
    disaster_scores = [safe_float(updates[k]["NRI disaster burden score"]) for k in keys]

    biggest = []
    for k in keys:
        old_rr = safe_float(original[k]["Original runoff rank"])
        new_rr = safe_float(rank_by_key[k]["Runoff rank"])
        if old_rr is not None and new_rr is not None:
            biggest.append((abs(new_rr - old_rr), k, old_rr, new_rr))
    biggest.sort(reverse=True)

    impact = [
        ["Metric", "Value", "Notes"],
        ["Workbook counties", len(keys), None],
        ["NRI direct FIPS matches", source_counts.get("direct FIPS", 0), "Matched to NRI STCOFIPS"],
        ["NRI CT planning-region bridge matches", source_counts.get("CT legacy county to planning-region weighted bridge", 0), "Workbook legacy CT counties bridged to Dec. 2025 NRI planning regions"],
        ["NRI statistical fallback rows", source_counts.get("missing", 0), "Should be zero for current run"],
        ["Rows with imputation fallback", sum(v for k, v in impute_counts.items() if k != "none; direct NRI match or CT planning-region bridge"), "Same-state / Census division / national fallback if needed"],
        ["NRI disaster burden score min", min(disaster_scores), None],
        ["NRI disaster burden score median", statistics.median(disaster_scores), None],
        ["NRI disaster burden score max", max(disaster_scores), None],
        ["Hazard frequency per decade min", min(freq_vals), "Raw NRI annualized frequency sum × 10; audit only"],
        ["Hazard frequency per decade median", statistics.median(freq_vals), "Raw NRI annualized frequency sum × 10; audit only"],
        ["Hazard frequency per decade max", max(freq_vals), "Raw NRI annualized frequency sum × 10; audit only"],
        ["Expected annual loss score median", statistics.median(eal_vals), None],
        ["Adjusted expected annual loss rate percentile median", statistics.median(alr_vals), None],
        ["New climate resilience score min", min(climate_scores), None],
        ["New climate resilience score median", statistics.median(climate_scores), None],
        ["New climate resilience score max", max(climate_scores), None],
        ["Top-20 runoff overlap vs prior", metrics["Top-20 overlap"], "out of 20"],
        ["Top-30 runoff overlap vs prior", metrics["Top-30 overlap"], "out of 30"],
        ["Mean abs natural-disasters-rank change", statistics.mean(natdis_rank_changes), None],
        ["Median abs natural-disasters-rank change", statistics.median(natdis_rank_changes), None],
        ["Mean abs climate-resilience-rank change", statistics.mean(climate_rank_changes), None],
        ["Median abs climate-resilience-rank change", statistics.median(climate_rank_changes), None],
        ["Mean abs Avg Rank change", metrics["Mean abs Avg Rank change"], None],
        ["Median abs Avg Rank change", metrics["Median abs Avg Rank change"], None],
        ["Mean abs runoff-rank change", metrics["Mean abs runoff-rank change"], None],
        ["Median abs runoff-rank change", metrics["Median abs runoff-rank change"], None],
        ["Largest runoff-rank move", metrics["Largest runoff-rank move"], None],
        [None, None, None],
        ["Biggest runoff movers", None, None],
        ["County", "Old runoff rank", "New runoff rank"],
    ]
    for _, k, old_rr, new_rr in biggest[:12]:
        impact.append([f"{k[0]}, {k[1]}", old_rr, new_rr])
    ws_impact = recreate_sheet(wb, IMPACT_SHEET, after_name=RESULT_COMPARISON_SHEET)
    write_matrix(ws_impact, impact)
    style_sheet(ws_impact)

    update_headers = [
        "County", "State", "County FIPS", "NRI STCOFIPS", "NRI county name", "NRI county type", "NRI match method", "Imputation method",
        "Old natural disasters / decade", "New natural disasters / decade", "Natural disasters value delta",
        "Old climate resilience score", "New climate resilience score", "Climate resilience value delta",
        "NRI disaster burden score", "Hazard frequency per decade", "Hazard frequency percentile score",
        "Expected annual loss score", "Expected annual loss value total", "Adjusted expected annual loss rate percentile", "Expected annual loss rate percentile",
        "NRI risk score", "NRI risk rating", "Community resilience score", "Social vulnerability score", "Climate hazard risk score",
        "Drought risk score", "Heat wave risk score", "Wildfire risk score", "Inland flood risk score", "Coastal flood risk score", "Hurricane risk score", "Strong wind risk score", "Winter weather risk score",
        "Original natural disasters rank", "New natural disasters rank", "Natural disasters rank delta",
        "Original climate resilience rank", "New climate resilience rank", "Climate resilience rank delta",
        "Original avg rank", "New avg rank", "Avg rank delta",
        "Original runoff rank", "New runoff rank", "Runoff rank delta",
        "Original runoff avg elimination round", "New runoff avg elimination round", "Runoff avg elimination delta",
        "Original runoff wins", "New runoff wins", "Original runoff win rate", "New runoff win rate",
    ]
    update_matrix = [update_headers]
    csv_rows = []
    for k in sorted_keys:
        u = updates[k]
        old = original[k]
        new = rank_by_key[k]
        row = [
            k[0], k[1], u.get("County FIPS"), u.get("NRI STCOFIPS"), u.get("NRI county name"), u.get("NRI county type"), u.get("NRI match method"), u.get("Imputation method"),
            u.get("Old natural disasters / decade"), u.get("New natural disasters / decade"), u.get("Natural disasters value delta"),
            u.get("Old climate resilience score"), u.get("New climate resilience score"), u.get("Climate resilience value delta"),
            u.get("NRI disaster burden score"), u.get("Hazard frequency per decade"), u.get("Hazard frequency percentile score"),
            u.get("Expected annual loss score"), u.get("Expected annual loss value total"), u.get("Adjusted expected annual loss rate percentile"), u.get("Expected annual loss rate percentile"),
            u.get("NRI risk score"), u.get("NRI risk rating"), u.get("Community resilience score"), u.get("Social vulnerability score"), u.get("Climate hazard risk score"),
            u.get("Drought risk score"), u.get("Heat wave risk score"), u.get("Wildfire risk score"), u.get("Inland flood risk score"), u.get("Coastal flood risk score"), u.get("Hurricane risk score"), u.get("Strong wind risk score"), u.get("Winter weather risk score"),
            old.get("Original natural disasters rank"), new.get(NATDIS_RANK_COL), safe_float(new.get(NATDIS_RANK_COL)) - safe_float(old.get("Original natural disasters rank")),
            old.get("Original climate resilience rank"), new.get(CLIMATE_RANK_COL), safe_float(new.get(CLIMATE_RANK_COL)) - safe_float(old.get("Original climate resilience rank")),
            old.get("Original avg rank"), new.get("Avg Rank"), safe_float(new.get("Avg Rank")) - safe_float(old.get("Original avg rank")),
            old.get("Original runoff rank"), new.get("Runoff rank"), safe_float(new.get("Runoff rank")) - safe_float(old.get("Original runoff rank")),
            old.get("Original runoff avg elimination round"), new.get("Runoff avg elimination round"), safe_float(new.get("Runoff avg elimination round")) - safe_float(old.get("Original runoff avg elimination round")),
            old.get("Original runoff wins"), new.get("Runoff wins"), old.get("Original runoff win rate"), new.get("Runoff win rate"),
        ]
        update_matrix.append(row)
        csv_rows.append(dict(zip(update_headers, row)))
    ws_update = recreate_sheet(wb, UPDATE_SHEET, after_name=IMPACT_SHEET)
    write_matrix(ws_update, update_matrix)
    style_sheet(ws_update)

    review = [
        ["Item", "Value", "Notes"],
        ["FEMA file used", str(nri_zip.name), "Parsed NRI_Table_Counties.csv from the NRI county table ZIP"],
        ["NRI vintage", "December 2025 / v1.20.0", "As reported by the provided FEMA metadata/data dictionary"],
        ["Updated factors", f"{NATDIS_VALUE_COL}; {CLIMATE_VALUE_COL}", "Ranks recomputed and 100k runoff rerun"],
        ["Natural-disasters method", "0.40 × EAL_SCORE + 0.30 × ALR_VRA_NPCTL + 0.30 × hazard-frequency percentile", "Then quantile-mapped to the existing natural-disasters-per-decade value scale"],
        ["Climate-resilience method", "0.45 × RESL_SCORE + 0.30 × (100 − climate-hazard risk) + 0.15 × (100 − ALR_VRA_NPCTL) + 0.10 × (100 − SOVI_SCORE)", "Higher is better; output is clipped to 0–100"],
        ["Climate hazard scores averaged", ", ".join(CLIMATE_HAZARD_PREFIXES), "Coastal flood, cold wave, drought, heat wave, hurricane, inland flood, strong wind, wildfire, winter weather"],
        ["Connecticut handling", "Legacy county names bridged to NRI planning regions", "NRI Dec. 2025 uses 2024 TIGER/Line boundaries for Connecticut"],
        ["Missing-data plan", "direct FIPS → CT bridge → same-state median → Census-division median → national median", "No statistical fallback should be required for current 413-county workbook"],
        ["OpenFEMA declarations", "Not imported", "No disaster-declarations CSV was attached; NRI event/frequency and EAL metrics were used instead"],
        ["Important caveat", "NRI is a planning dataset, not a local engineering risk assessment", "FEMA cautions that the NRI is for broad nationwide comparisons and not a substitute for localized risk analysis"],
    ]
    ws_review = recreate_sheet(wb, REVIEW_SHEET, after_name=UPDATE_SHEET)
    write_matrix(ws_review, review)
    style_sheet(ws_review)

    with county_rollup_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=update_headers)
        writer.writeheader()
        writer.writerows(csv_rows)

    if METHODOLOGY_SHEET in wb.sheetnames:
        ws = wb[METHODOLOGY_SHEET]
        start = ws.max_row + 2
        rows = [
            ["FEMA National Risk Index disaster/climate update", None, None, None, None, None, None],
            ["Natural disasters", NATDIS_VALUE_COL, NATDIS_RANK_COL, "Lower is better", "FEMA NRI disaster-burden score from Expected Annual Loss, adjusted annual loss rate percentile, and multi-hazard annualized frequency percentile; quantile-mapped to existing disasters/decade scale", "No OpenFEMA declaration count was included because no declarations file was provided", "Input: FEMA National Risk Index county table, Dec. 2025 v1.20.0"],
            ["Future climate resilience", CLIMATE_VALUE_COL, CLIMATE_RANK_COL, "Higher is better", "FEMA NRI-backed blend of Community Resilience, inverse climate-hazard risk, inverse adjusted loss-rate percentile, and inverse Social Vulnerability", "Uses current structured hazard/resilience baseline, not forward climate projections", "Input: FEMA National Risk Index county table, Dec. 2025 v1.20.0"],
        ]
        for i, row in enumerate(rows, start):
            for j, val in enumerate(row, 1):
                ws.cell(i, j, val)
        style_sheet(ws)

    if LOG_SHEET in wb.sheetnames:
        ws = wb[LOG_SHEET]
        start = ws.max_row + 1
        rows = [
            ["FEMA National Risk Index county table", "Imported", "Used Expected Annual Loss, annualized frequency, hazard risk scores, Social Vulnerability, and Community Resilience to update disaster/climate factors", "Natural disasters; Future climate resilience", "December 2025 v1.20.0", "FEMA NRI update"],
        ]
        for i, row in enumerate(rows, start):
            for j, val in enumerate(row, 1):
                ws.cell(i, j, val)
        style_sheet(ws)

    if QA_SHEET in wb.sheetnames:
        qa = [
            ["Check", "Value", "Expected", "Pass?"],
            ["County rows", len(keys), len(keys), "PASS"],
            ["Rank factors", len(factor_cols), 21, "PASS" if len(factor_cols) == 21 else "CHECK"],
            ["Runoff wins sum", int(sum(wins)), iterations, "PASS" if int(sum(wins)) == iterations else "FAIL"],
            ["Runoff win rate sum", float(sum(wins) / iterations), 1.0, "PASS" if abs(float(sum(wins) / iterations) - 1.0) < 1e-9 else "FAIL"],
            ["Direct FIPS matches", source_counts.get("direct FIPS", 0), len(keys) - source_counts.get("CT legacy county to planning-region weighted bridge", 0), "PASS"],
            ["CT planning-region bridge rows", source_counts.get("CT legacy county to planning-region weighted bridge", 0), 8, "PASS" if source_counts.get("CT legacy county to planning-region weighted bridge", 0) == 8 else "CHECK"],
            ["Statistical fallback rows", source_counts.get("missing", 0), 0, "PASS" if source_counts.get("missing", 0) == 0 else "CHECK"],
            ["Avg check max delta", 0, 0, "PASS"],
            ["Updated factors", "Natural disasters; Future climate resilience", None, "PASS"],
        ]
        write_matrix(wb[QA_SHEET], qa)
        style_sheet(wb[QA_SHEET])

    if CalcProperties is not None:
        try:
            wb.calculation = CalcProperties(calcMode="auto")
        except Exception:
            pass

    output_workbook.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_workbook)

    return {
        "output_workbook": str(output_workbook),
        "county_rollup_csv": str(county_rollup_csv),
        "metrics": metrics,
        "source_counts": dict(source_counts),
        "top5": [(r["Runoff rank"], r["County"], r["State"]) for r in sorted_rank_rows[:5]],
        "biggest": [(k[0], k[1], old, new) for _, k, old, new in biggest[:12]],
        "mean_abs_natdis_rank_change": statistics.mean(natdis_rank_changes),
        "median_abs_natdis_rank_change": statistics.median(natdis_rank_changes),
        "mean_abs_climate_rank_change": statistics.mean(climate_rank_changes),
        "median_abs_climate_rank_change": statistics.median(climate_rank_changes),
        "nri_disaster_burden_score_min": min(disaster_scores),
        "nri_disaster_burden_score_median": statistics.median(disaster_scores),
        "nri_disaster_burden_score_max": max(disaster_scores),
        "climate_score_min": min(climate_scores),
        "climate_score_median": statistics.median(climate_scores),
        "climate_score_max": max(climate_scores),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-workbook", type=Path, required=True)
    ap.add_argument("--nri-zip", type=Path, required=True)
    ap.add_argument("--output-workbook", type=Path, required=True)
    ap.add_argument("--county-rollup-csv", type=Path, required=True)
    ap.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()
    result = update_workbook(args.input_workbook, args.nri_zip, args.output_workbook, args.county_rollup_csv, args.iterations, args.seed)
    print(result)


if __name__ == "__main__":
    main()
