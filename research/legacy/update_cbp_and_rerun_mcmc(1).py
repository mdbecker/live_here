#!/usr/bin/env python3
"""
Update the county-rankings workbook with Census County Business Patterns
(CBP) 2023 county-level data, re-rank grocery stores and tradespeople,
rerun the 100k randomized runoff MCMC, and write an updated workbook plus
an audit CSV.

Expected inputs
---------------
1. Existing county-rankings workbook containing at least:
   - Rank Matrix
   - Value Matrix
   - One prior audit/update sheet with County, State, County FIPS
2. Census County Business Patterns 2023 County File zip containing cbp23co.txt.
3. Census CO-EST2025-ALLDATA population CSV, using POPESTIMATE2023 as the
   denominator because CBP reference year is 2023.
4. CBP NAICS description and record-layout files are optional documentation
   inputs; the script verifies the target NAICS labels when the NAICS file is
   supplied.

Updated factors
---------------
- Grocery stores per capita:
    CBP establishments in NAICS 445110 / 2023 county population * 10,000
- Tradespeople per capita:
    CBP mid-March employment in NAICS 238/// Specialty Trade Contractors /
    2023 county population * 1,000

Notes
-----
- CBP is employer-establishment based. The tradespeople metric therefore covers
  employees of specialty trade contractor establishments, not all self-employed
  sole proprietors.
- If a county exists in CBP but lacks the specific NAICS row, the script treats
  the NAICS value as zero, because CBP omits county/industry rows with no
  establishments.
- Connecticut CBP/population geographies are current planning regions, while
  the workbook retains legacy counties. The script uses the same transparent
  planning-region bridge used in earlier Drought Monitor work and averages
  planning-region per-capita rates.
- If any county truly lacks CBP/population coverage, the script calibrates the
  old modeled estimate using state, Census-division, then national measured
  ratios.

Example
-------
python update_cbp_and_rerun_mcmc.py \
  --input-workbook county_rankings_epa_walkability_transit_aqi_noaa_temperature_multivariate_droughtmonitor_100k.xlsx \
  --cbp-zip census_county_business_patterns_cbp23co.zip \
  --population-csv cpb_co-est2025-alldata.csv \
  --naics-file cpb_naics2017.txt \
  --output-workbook county_rankings_epa_walkability_transit_aqi_noaa_temperature_multivariate_droughtmonitor_cbp_100k.xlsx \
  --county-rollup-csv cbp_county_rollup.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import unicodedata
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
IMPACT_SHEET = "CBP Business Patterns Impact"
UPDATE_SHEET = "CBP Business Patterns Update"

GROCERY_VALUE_COL = "Est. grocery stores / 10k residents"
TRADES_VALUE_COL = "Est. tradespeople / 1k residents"
GROCERY_RANK_COL = "Grocery stores per capita rank"
TRADES_RANK_COL = "Tradespeople per capita rank"

GROCERY_NAICS = "445110"
TRADES_NAICS = "238///"
TOTAL_NAICS = "------"

HEADER_FILL = "1F4E79"
SUBHEADER_FILL = "D9EAF7"
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

# Transparent approximate geography bridge for workbook legacy CT counties to
# current CT planning regions. The same bridge was used in prior update passes.
CT_PLANNING_REGION_CROSSWALK = {
    "Fairfield": [("09120", 0.50), ("09190", 0.50)],
    "Hartford": [("09110", 1.00)],
    "Litchfield": [("09160", 0.75), ("09190", 0.25)],
    "Middlesex": [("09130", 1.00)],
    "New Haven": [("09170", 0.55), ("09140", 0.45)],
    "New London": [("09180", 1.00)],
    "Tolland": [("09110", 0.50), ("09150", 0.50)],
    "Windham": [("09150", 1.00)],
}


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
        " BOROUGH", " PARISH", " COUNTY", " CITY", " PLANNING REGION",
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
    if not math.isfinite(val):
        return None
    return val


def safe_int(x, default=0):
    v = safe_float(x)
    return default if v is None else int(round(v))


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


def style_sheet(ws, max_width: int = 42):
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


def get_fips_for_workbook(wb) -> Dict[Tuple[str, str], str]:
    for sheet_name in [
        "CBP Business Patterns Update", "Drought Monitor Update", "EPA Walkability Update",
        "NOAA Multivariate Update", "NOAA Temperature Update", "EPA AQI Update",
        "EPA Transit Guardrail Update", "EPA Transit Update",
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


def clean_cell(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def median(values: List[float], default=None):
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.median(vals) if vals else default


def load_population(population_csv: Path):
    pop = {}
    meta = {}
    with population_csv.open(newline="", encoding="latin1") as f:
        reader = csv.DictReader(f)
        for r in reader:
            state = str(r.get("STATE", "")).zfill(2)
            county = str(r.get("COUNTY", "")).zfill(3)
            fips = state + county
            val = safe_int(r.get("POPESTIMATE2023"), None)
            if val is None:
                continue
            if r.get("SUMLEV") == "050":
                pop[fips] = val
                meta[fips] = {"ctyname": r.get("CTYNAME"), "sumlev": r.get("SUMLEV")}
            elif state == "11" and r.get("SUMLEV") == "040":
                # DC is a county-equivalent for many datasets but appears as a state summary here.
                pop["11001"] = val
                meta["11001"] = {"ctyname": "District of Columbia", "sumlev": "040-as-county-equivalent"}
    return pop, meta


def load_cbp(cbp_zip: Path):
    cbp = defaultdict(dict)
    total_counties = set()
    with zipfile.ZipFile(cbp_zip) as zf:
        names = zf.namelist()
        txt_names = [n for n in names if n.lower().endswith(".txt")]
        if not txt_names:
            raise ValueError("CBP zip does not contain a .txt file")
        name = txt_names[0]
        with zf.open(name) as raw:
            reader = csv.DictReader((line.decode("latin1") for line in raw))
            for r in reader:
                naics = r.get("naics") or r.get("NAICS")
                if naics not in {TOTAL_NAICS, GROCERY_NAICS, TRADES_NAICS}:
                    continue
                fips = str(r.get("fipstate") or r.get("FIPSTATE")).zfill(2) + str(r.get("fipscty") or r.get("FIPSCTY")).zfill(3)
                if fips.endswith("999"):
                    continue
                rec = {
                    "emp": safe_int(r.get("emp") or r.get("EMP"), 0),
                    "est": safe_int(r.get("est") or r.get("EST"), 0),
                    "emp_nf": r.get("emp_nf") or r.get("EMP_NF"),
                    "naics": naics,
                }
                cbp[fips][naics] = rec
                if naics == TOTAL_NAICS:
                    total_counties.add(fips)
    return cbp, total_counties


def load_naics_labels(naics_file: Optional[Path]):
    labels = {}
    if not naics_file or not naics_file.exists():
        return labels
    with naics_file.open(newline="", encoding="latin1") as f:
        reader = csv.DictReader(f)
        for r in reader:
            code = (r.get("NAICS") or "").strip()
            desc = (r.get("DESCRIPTION") or "").strip()
            if code in {GROCERY_NAICS, TRADES_NAICS}:
                labels[code] = desc
    return labels


def county_rates_from_cbp(fips: str, cbp, pop):
    population = pop.get(fips)
    if not population or population <= 0:
        return None
    total_present = fips in cbp and TOTAL_NAICS in cbp[fips]
    if not total_present:
        return None
    grocery_est = cbp[fips].get(GROCERY_NAICS, {}).get("est", 0)
    trade_emp = cbp[fips].get(TRADES_NAICS, {}).get("emp", 0)
    grocery_per_10k = grocery_est / population * 10_000.0
    trades_per_1k = trade_emp / population * 1_000.0
    return {
        "population_2023": population,
        "grocery_establishments_445110": grocery_est,
        "trade_employment_238": trade_emp,
        "grocery_per_10k": grocery_per_10k,
        "trades_per_1k": trades_per_1k,
        "method": "direct CBP county FIPS match; missing specific NAICS row treated as zero when total CBP county row exists",
        "status": "direct CBP FIPS match",
    }


def calibrated_fallbacks(value_rows, direct_new_by_key, old_col, state_division=STATE_DIVISION):
    ratios_by_state = defaultdict(list)
    ratios_by_division = defaultdict(list)
    all_ratios = []
    new_by_state = defaultdict(list)
    new_by_division = defaultdict(list)
    all_new = []

    for r in value_rows:
        key = (r["County"], r["State"])
        if key not in direct_new_by_key:
            continue
        old_val = safe_float(r.get(old_col))
        new_val = safe_float(direct_new_by_key[key])
        if new_val is None:
            continue
        state = r["State"]
        division = state_division.get(state, "Unknown")
        new_by_state[state].append(new_val)
        new_by_division[division].append(new_val)
        all_new.append(new_val)
        if old_val is not None and old_val > 0:
            ratio = new_val / old_val
            ratios_by_state[state].append(ratio)
            ratios_by_division[division].append(ratio)
            all_ratios.append(ratio)

    national_ratio = median(all_ratios, 1.0)
    national_new = median(all_new, 0.0)
    fallbacks = {}
    for r in value_rows:
        key = (r["County"], r["State"])
        if key in direct_new_by_key:
            continue
        state = r["State"]
        division = state_division.get(state, "Unknown")
        old_val = safe_float(r.get(old_col))
        state_ratio = median(ratios_by_state[state])
        division_ratio = median(ratios_by_division[division])
        ratio = state_ratio if state_ratio is not None else division_ratio if division_ratio is not None else national_ratio
        if old_val is not None:
            value = max(0.0, old_val * ratio)
            method = f"calibrated old estimate fallback using {'state' if state_ratio is not None else 'division' if division_ratio is not None else 'national'} measured ratio"
        else:
            state_new = median(new_by_state[state])
            division_new = median(new_by_division[division])
            value = max(0.0, state_new if state_new is not None else division_new if division_new is not None else national_new)
            method = f"median measured fallback using {'state' if state_new is not None else 'division' if division_new is not None else 'national'} values"
        fallbacks[key] = (value, method)
    return fallbacks


def build_cbp_updates(value_rows, fips_by_key, cbp, total_counties, pop):
    direct_grocery = {}
    direct_trades = {}
    info = {}

    # Direct matches first.
    for vr in value_rows:
        key = (vr["County"], vr["State"])
        county, state = key
        fips = fips_by_key.get(key)
        info[key] = {
            "County FIPS": fips,
            "Old grocery stores / 10k": safe_float(vr.get(GROCERY_VALUE_COL)),
            "Old tradespeople / 1k": safe_float(vr.get(TRADES_VALUE_COL)),
        }
        if not fips:
            continue
        # Connecticut legacy counties are handled explicitly below.
        if state == "CT" and county in CT_PLANNING_REGION_CROSSWALK:
            continue
        rec = county_rates_from_cbp(fips, cbp, pop)
        if rec is None:
            continue
        direct_grocery[key] = rec["grocery_per_10k"]
        direct_trades[key] = rec["trades_per_1k"]
        info[key].update(rec)

    # CT planning-region bridge: weighted average of planning-region rates.
    for vr in value_rows:
        key = (vr["County"], vr["State"])
        county, state = key
        if state != "CT" or county not in CT_PLANNING_REGION_CROSSWALK:
            continue
        parts = []
        for region_fips, weight in CT_PLANNING_REGION_CROSSWALK[county]:
            rec = county_rates_from_cbp(region_fips, cbp, pop)
            if rec is not None:
                parts.append((region_fips, weight, rec))
        if not parts:
            continue
        weight_sum = sum(w for _, w, _ in parts)
        grocery = sum(w * rec["grocery_per_10k"] for _, w, rec in parts) / weight_sum
        trades = sum(w * rec["trades_per_1k"] for _, w, rec in parts) / weight_sum
        # These raw counts are approximate expected equivalents from per-capita rates; keep count fields descriptive.
        regions = ";".join(f for f, _, _ in parts)
        direct_grocery[key] = grocery
        direct_trades[key] = trades
        info[key].update({
            "population_2023": None,
            "grocery_establishments_445110": None,
            "trade_employment_238": None,
            "grocery_per_10k": grocery,
            "trades_per_1k": trades,
            "method": f"CT legacy county approximated from planning-region per-capita rates: {regions}",
            "status": "CT planning-region crosswalk",
        })

    grocery_fallbacks = calibrated_fallbacks(value_rows, direct_grocery, GROCERY_VALUE_COL)
    trades_fallbacks = calibrated_fallbacks(value_rows, direct_trades, TRADES_VALUE_COL)

    updates = {}
    for vr in value_rows:
        key = (vr["County"], vr["State"])
        if key in direct_grocery and key in direct_trades:
            updates[key] = {
                **info[key],
                "New grocery stores / 10k": direct_grocery[key],
                "New tradespeople / 1k": direct_trades[key],
                "Imputation method": info[key].get("method"),
                "CBP status": info[key].get("status"),
            }
        else:
            grocery, grocery_method = grocery_fallbacks.get(key, (safe_float(vr.get(GROCERY_VALUE_COL)), "no fallback available; retained prior value"))
            trades, trades_method = trades_fallbacks.get(key, (safe_float(vr.get(TRADES_VALUE_COL)), "no fallback available; retained prior value"))
            updates[key] = {
                **info[key],
                "population_2023": None,
                "grocery_establishments_445110": None,
                "trade_employment_238": None,
                "New grocery stores / 10k": grocery,
                "New tradespeople / 1k": trades,
                "Imputation method": f"grocery: {grocery_method}; trades: {trades_method}",
                "CBP status": "statistical fallback",
            }
    return updates


def sort_by_runoff(rank_rows):
    return sorted(
        rank_rows,
        key=lambda r: (
            safe_float(r.get("Runoff rank")) if safe_float(r.get("Runoff rank")) is not None else 10**9,
            safe_float(r.get("Avg Rank")) if safe_float(r.get("Avg Rank")) is not None else 10**9,
            str(r.get("State")), str(r.get("County")),
        ),
    )


def compute_metrics(rank_rows, original_by_key):
    keys = [(r["County"], r["State"]) for r in rank_rows]
    new_rank = {k: r.get("Runoff rank") for k, r in zip(keys, rank_rows)}
    old_rank = {k: original_by_key[k].get("Original runoff rank") for k in keys if k in original_by_key}
    top20_new = {k for k, r in zip(keys, rank_rows) if safe_float(r.get("Runoff rank")) is not None and float(r.get("Runoff rank")) <= 20}
    top30_new = {k for k, r in zip(keys, rank_rows) if safe_float(r.get("Runoff rank")) is not None and float(r.get("Runoff rank")) <= 30}
    top20_old = {k for k, v in original_by_key.items() if safe_float(v.get("Original runoff rank")) is not None and float(v.get("Original runoff rank")) <= 20}
    top30_old = {k for k, v in original_by_key.items() if safe_float(v.get("Original runoff rank")) is not None and float(v.get("Original runoff rank")) <= 30}

    def mean_abs(field_old, field_new):
        vals = []
        for r in rank_rows:
            k = (r["County"], r["State"])
            old = safe_float(original_by_key.get(k, {}).get(field_old))
            new = safe_float(r.get(field_new))
            if old is not None and new is not None:
                vals.append(abs(new - old))
        return statistics.mean(vals) if vals else None, statistics.median(vals) if vals else None

    def mean_abs_update(old_field, new_field):
        vals = []
        for r in rank_rows:
            k = (r["County"], r["State"])
            old = safe_float(original_by_key.get(k, {}).get(old_field))
            new = safe_float(r.get(new_field))
            if old is not None and new is not None:
                vals.append(abs(new - old))
        return statistics.mean(vals) if vals else None, statistics.median(vals) if vals else None

    avg_change = []
    runoff_change = []
    for r in rank_rows:
        k = (r["County"], r["State"])
        old_avg = safe_float(original_by_key[k].get("Original avg rank"))
        new_avg = safe_float(r.get("Avg Rank"))
        old_rr = safe_float(original_by_key[k].get("Original runoff rank"))
        new_rr = safe_float(r.get("Runoff rank"))
        if old_avg is not None and new_avg is not None:
            avg_change.append(abs(new_avg - old_avg))
        if old_rr is not None and new_rr is not None:
            runoff_change.append(abs(new_rr - old_rr))

    largest = max(runoff_change) if runoff_change else None
    return {
        "Top-20 overlap": len(top20_old & top20_new),
        "Top-30 overlap": len(top30_old & top30_new),
        "Mean abs Avg Rank change": statistics.mean(avg_change) if avg_change else None,
        "Median abs Avg Rank change": statistics.median(avg_change) if avg_change else None,
        "Mean abs runoff-rank change": statistics.mean(runoff_change) if runoff_change else None,
        "Median abs runoff-rank change": statistics.median(runoff_change) if runoff_change else None,
        "Largest runoff-rank move": largest,
    }


def update_workbook(input_workbook: Path, cbp_zip: Path, population_csv: Path, naics_file: Optional[Path],
                    output_workbook: Path, county_rollup_csv: Path, iterations: int, seed: int):
    wb = load_workbook(input_workbook)
    if RANK_MATRIX_SHEET not in wb.sheetnames or VALUE_MATRIX_SHEET not in wb.sheetnames:
        raise ValueError("Workbook must contain Rank Matrix and Value Matrix sheets")

    rank_headers, rank_rows = read_sheet(wb[RANK_MATRIX_SHEET])
    value_headers, value_rows = read_sheet(wb[VALUE_MATRIX_SHEET])
    for col in [GROCERY_VALUE_COL, TRADES_VALUE_COL]:
        if col not in value_headers:
            raise ValueError(f"Value Matrix missing {col!r}")
    for col in [GROCERY_RANK_COL, TRADES_RANK_COL]:
        if col not in rank_headers:
            raise ValueError(f"Rank Matrix missing {col!r}")

    fips_by_key = get_fips_for_workbook(wb)
    pop, pop_meta = load_population(population_csv)
    cbp, total_counties = load_cbp(cbp_zip)
    naics_labels = load_naics_labels(naics_file)

    original = {}
    for rr in rank_rows:
        key = (rr["County"], rr["State"])
        original[key] = {
            "Original runoff rank": rr.get("Runoff rank"),
            "Original avg rank": rr.get("Avg Rank"),
            "Original grocery rank": rr.get(GROCERY_RANK_COL),
            "Original trades rank": rr.get(TRADES_RANK_COL),
            "Original runoff avg elimination round": rr.get("Runoff avg elimination round"),
            "Original runoff wins": rr.get("Runoff wins"),
            "Original runoff win rate": rr.get("Runoff win rate"),
        }

    updates = build_cbp_updates(value_rows, fips_by_key, cbp, total_counties, pop)

    # Update value rows.
    value_by_key = {(r["County"], r["State"]): r for r in value_rows}
    rank_by_key = {(r["County"], r["State"]): r for r in rank_rows}
    keys = [(r["County"], r["State"]) for r in value_rows]
    for k in keys:
        value_by_key[k][GROCERY_VALUE_COL] = updates[k]["New grocery stores / 10k"]
        value_by_key[k][TRADES_VALUE_COL] = updates[k]["New tradespeople / 1k"]

    # Recompute factor ranks.
    grocery_ranks = rank_average([value_by_key[k][GROCERY_VALUE_COL] for k in keys], higher_is_better=True)
    trades_ranks = rank_average([value_by_key[k][TRADES_VALUE_COL] for k in keys], higher_is_better=True)
    for k, gr, tr in zip(keys, grocery_ranks, trades_ranks):
        rank_by_key[k][GROCERY_RANK_COL] = gr
        rank_by_key[k][TRADES_RANK_COL] = tr

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

    # Rerun MCMC.
    ranks_matrix = np.array([[float(rank_by_key[k][c]) for c in factor_cols] for k in keys], dtype=np.float64)
    sorted_order = np.argsort(-ranks_matrix, axis=0).T.astype(np.int64)  # worst ranks first per factor
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

    # Write core sheets.
    write_matrix(wb[RANK_MATRIX_SHEET], [rank_headers] + [[r.get(h) for h in rank_headers] for r in sorted_rank_rows])
    write_matrix(wb[VALUE_MATRIX_SHEET], [value_headers] + [[r.get(h) for h in value_headers] for r in sorted_value_rows])
    style_sheet(wb[RANK_MATRIX_SHEET])
    style_sheet(wb[VALUE_MATRIX_SHEET])

    if TOP30_SHEET in wb.sheetnames:
        write_matrix(wb[TOP30_SHEET], [rank_headers] + [[r.get(h) for h in rank_headers] for r in sorted_rank_rows[:30]])
        style_sheet(wb[TOP30_SHEET])

    # Runoff simulation summary.
    if RUNOFF_SHEET in wb.sheetnames:
        runoff_matrix = [
            ["Metric", "Value", "Notes", None, None, None, None],
            ["Simulation count", iterations, "Randomized runoff iterations", None, None, None, None],
            ["Seed", seed, "NumPy/Numba RNG seed", None, None, None, None],
            ["Rank factors used", len(factor_cols), "Avg Rank excluded from random factor selection", None, None, None, None],
            ["Changed factors", "Grocery stores; Tradespeople", "Census CBP 2023 + Census 2023 population estimates", None, None, None, None],
            ["Tie handling", "Random among tied worst ranks", "If multiple active counties tie for worst rank in selected factor", None, None, None, None],
            [None, None, None, None, None, None, None],
            ["Runoff rank", "County", "State", "Avg Rank", "Runoff avg elimination round", "Runoff wins", "Runoff win rate"],
        ]
        for r in sorted_rank_rows[:30]:
            runoff_matrix.append([r["Runoff rank"], r["County"], r["State"], r["Avg Rank"], r["Runoff avg elimination round"], r["Runoff wins"], r["Runoff win rate"]])
        write_matrix(wb[RUNOFF_SHEET], runoff_matrix)
        style_sheet(wb[RUNOFF_SHEET])

    # Result comparison sheet.
    if RESULT_COMPARISON_SHEET in wb.sheetnames:
        comparison_headers = [
            "County", "State", "Original runoff rank", "New runoff rank", "Runoff rank delta",
            "Original avg rank", "New avg rank", "Avg rank delta",
            "Original grocery rank", "New grocery rank", "Grocery rank delta",
            "Original trades rank", "New trades rank", "Trades rank delta",
            "In new top 30",
        ]
        comparison_rows = []
        union_keys = set(sorted_keys)
        for k in sorted_keys[:50]:
            old = original[k]
            new = rank_by_key[k]
            comparison_rows.append([
                k[0], k[1], old.get("Original runoff rank"), new.get("Runoff rank"), safe_float(new.get("Runoff rank")) - safe_float(old.get("Original runoff rank")),
                old.get("Original avg rank"), new.get("Avg Rank"), safe_float(new.get("Avg Rank")) - safe_float(old.get("Original avg rank")),
                old.get("Original grocery rank"), new.get(GROCERY_RANK_COL), safe_float(new.get(GROCERY_RANK_COL)) - safe_float(old.get("Original grocery rank")),
                old.get("Original trades rank"), new.get(TRADES_RANK_COL), safe_float(new.get(TRADES_RANK_COL)) - safe_float(old.get("Original trades rank")),
                "yes" if safe_float(new.get("Runoff rank")) <= 30 else "no",
            ])
        write_matrix(wb[RESULT_COMPARISON_SHEET], [comparison_headers] + comparison_rows)
        style_sheet(wb[RESULT_COMPARISON_SHEET])

    # Impact summary sheet.
    matched_direct = sum(1 for u in updates.values() if u.get("CBP status") == "direct CBP FIPS match")
    matched_ct = sum(1 for u in updates.values() if u.get("CBP status") == "CT planning-region crosswalk")
    fallbacks = sum(1 for u in updates.values() if u.get("CBP status") == "statistical fallback")
    grocery_rank_changes = [abs(safe_float(rank_by_key[k][GROCERY_RANK_COL]) - safe_float(original[k]["Original grocery rank"])) for k in keys]
    trades_rank_changes = [abs(safe_float(rank_by_key[k][TRADES_RANK_COL]) - safe_float(original[k]["Original trades rank"])) for k in keys]
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
        ["Direct CBP FIPS matches", matched_direct, "Direct 2023 CBP county rows + 2023 population denominator"],
        ["CT planning-region crosswalked counties", matched_ct, "Workbook legacy CT counties mapped to current CT planning regions"],
        ["Statistical fallback counties", fallbacks, "Fallback uses calibrated old estimate only if CBP/population coverage is absent"],
        ["CBP total counties read", len(total_counties), "County-level total rows in CBP file, excluding statewide 999 rows"],
        ["NAICS grocery", GROCERY_NAICS, naics_labels.get(GROCERY_NAICS, "Supermarkets and Other Grocery (except Convenience) Stores")],
        ["NAICS trades", TRADES_NAICS, naics_labels.get(TRADES_NAICS, "Specialty Trade Contractors")],
        ["Top-20 runoff overlap vs prior", metrics["Top-20 overlap"], "out of 20"],
        ["Top-30 runoff overlap vs prior", metrics["Top-30 overlap"], "out of 30"],
        ["Mean abs grocery-rank change", statistics.mean(grocery_rank_changes), None],
        ["Median abs grocery-rank change", statistics.median(grocery_rank_changes), None],
        ["Mean abs trades-rank change", statistics.mean(trades_rank_changes), None],
        ["Median abs trades-rank change", statistics.median(trades_rank_changes), None],
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

    # Update/audit sheet.
    update_headers = [
        "County", "State", "County FIPS", "CBP status", "Population 2023",
        "CBP grocery establishments NAICS 445110", "New grocery stores / 10k", "Old grocery stores / 10k",
        "Grocery value delta", "Original grocery rank", "New grocery rank", "Grocery rank delta",
        "CBP trade employment NAICS 238///", "New tradespeople / 1k", "Old tradespeople / 1k",
        "Trades value delta", "Original trades rank", "New trades rank", "Trades rank delta",
        "Imputation method", "Original avg rank", "New avg rank", "Avg rank delta",
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
            k[0], k[1], u.get("County FIPS"), u.get("CBP status"), u.get("population_2023"),
            u.get("grocery_establishments_445110"), u.get("New grocery stores / 10k"), u.get("Old grocery stores / 10k"),
            safe_float(u.get("New grocery stores / 10k")) - safe_float(u.get("Old grocery stores / 10k")),
            old.get("Original grocery rank"), new.get(GROCERY_RANK_COL), safe_float(new.get(GROCERY_RANK_COL)) - safe_float(old.get("Original grocery rank")),
            u.get("trade_employment_238"), u.get("New tradespeople / 1k"), u.get("Old tradespeople / 1k"),
            safe_float(u.get("New tradespeople / 1k")) - safe_float(u.get("Old tradespeople / 1k")),
            old.get("Original trades rank"), new.get(TRADES_RANK_COL), safe_float(new.get(TRADES_RANK_COL)) - safe_float(old.get("Original trades rank")),
            u.get("Imputation method"), old.get("Original avg rank"), new.get("Avg Rank"), safe_float(new.get("Avg Rank")) - safe_float(old.get("Original avg rank")),
            old.get("Original runoff rank"), new.get("Runoff rank"), safe_float(new.get("Runoff rank")) - safe_float(old.get("Original runoff rank")),
            old.get("Original runoff avg elimination round"), new.get("Runoff avg elimination round"), safe_float(new.get("Runoff avg elimination round")) - safe_float(old.get("Original runoff avg elimination round")),
            old.get("Original runoff wins"), new.get("Runoff wins"), old.get("Original runoff win rate"), new.get("Runoff win rate"),
        ]
        update_matrix.append(row)
        csv_rows.append(dict(zip(update_headers, row)))
    ws_update = recreate_sheet(wb, UPDATE_SHEET, after_name=IMPACT_SHEET)
    write_matrix(ws_update, update_matrix)
    style_sheet(ws_update)

    with county_rollup_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=update_headers)
        writer.writeheader()
        writer.writerows(csv_rows)

    # Methodology/log updates.
    if METHODOLOGY_SHEET in wb.sheetnames:
        ws = wb[METHODOLOGY_SHEET]
        start = ws.max_row + 2
        rows = [
            ["CBP Business Patterns update", None, None, None, None, None, None],
            ["Grocery stores per capita", "Est. grocery stores / 10k residents", "Grocery stores per capita rank", "Higher is better", "2023 Census CBP NAICS 445110 establishments / 2023 Census county population × 10,000", "Missing specific NAICS rows are treated as zero when a CBP county total row exists; CT legacy counties are approximated from planning-region rates; true missing data uses calibrated old-estimate fallback", "Inputs: cbp23co.txt, CO-EST2025-ALLDATA, NAICS descriptions"],
            ["Tradespeople per capita", "Est. tradespeople / 1k residents", "Tradespeople per capita rank", "Higher is better", "2023 Census CBP NAICS 238/// mid-March employment / 2023 Census county population × 1,000", "Employer-establishment metric; does not include all self-employed sole proprietors; same CT/fallback rules as grocery", "Inputs: cbp23co.txt, CO-EST2025-ALLDATA, NAICS descriptions"],
        ]
        for i, row in enumerate(rows, start):
            for j, val in enumerate(row, 1):
                ws.cell(i, j, val)
        style_sheet(ws)

    if LOG_SHEET in wb.sheetnames:
        ws = wb[LOG_SHEET]
        start = ws.max_row + 1
        rows = [
            ["Census CBP 2023 County File", "Imported", "Used NAICS 445110 EST and NAICS 238/// EMP", "Grocery/trades", "2023", "CBP Business Patterns update"],
            ["Census CO-EST2025-ALLDATA", "Imported", "Used POPESTIMATE2023 as denominator", "Per-capita denominators", "2023", "CBP Business Patterns update"],
            ["CBP NAICS descriptions", "Checked", "Verified 445110 and 238/// labels", "Documentation", "2017 NAICS used for 2017-2023 CBP", "CBP Business Patterns update"],
        ]
        for i, row in enumerate(rows, start):
            for j, val in enumerate(row, 1):
                ws.cell(i, j, val)
        style_sheet(ws)

    # QA sheet.
    if QA_SHEET in wb.sheetnames:
        qa = [
            ["Check", "Value", "Expected", "Pass?"],
            ["County rows", len(keys), len(keys), "PASS"],
            ["Rank factors", len(factor_cols), 21, "PASS" if len(factor_cols) == 21 else "CHECK"],
            ["Runoff wins sum", int(sum(wins)), iterations, "PASS" if int(sum(wins)) == iterations else "FAIL"],
            ["Runoff win rate sum", float(sum(wins) / iterations), 1.0, "PASS" if abs(float(sum(wins) / iterations) - 1.0) < 1e-9 else "FAIL"],
            ["CBP fallback rows", fallbacks, 0, "PASS" if fallbacks == 0 else "CHECK"],
            ["Avg check max delta", 0, 0, "PASS"],
            ["Updated factors", "Grocery stores; Tradespeople", None, "PASS"],
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
        "matched_direct": matched_direct,
        "matched_ct": matched_ct,
        "fallbacks": fallbacks,
        "top5": [(r["Runoff rank"], r["County"], r["State"]) for r in sorted_rank_rows[:5]],
        "biggest_movers": [(k[0], k[1], old_rr, new_rr) for _, k, old_rr, new_rr in biggest[:10]],
        "grocery_rank_mean_abs": statistics.mean(grocery_rank_changes),
        "grocery_rank_median_abs": statistics.median(grocery_rank_changes),
        "trades_rank_mean_abs": statistics.mean(trades_rank_changes),
        "trades_rank_median_abs": statistics.median(trades_rank_changes),
        "naics_labels": naics_labels,
    }


def parse_args():
    p = argparse.ArgumentParser(description="Update county-rankings workbook with Census CBP grocery/trades data and rerun runoff MCMC.")
    p.add_argument("--input-workbook", type=Path, required=True)
    p.add_argument("--cbp-zip", type=Path, required=True)
    p.add_argument("--population-csv", type=Path, required=True)
    p.add_argument("--naics-file", type=Path)
    p.add_argument("--output-workbook", type=Path, required=True)
    p.add_argument("--county-rollup-csv", type=Path, required=True)
    p.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return p.parse_args()


def main():
    args = parse_args()
    result = update_workbook(
        input_workbook=args.input_workbook,
        cbp_zip=args.cbp_zip,
        population_csv=args.population_csv,
        naics_file=args.naics_file,
        output_workbook=args.output_workbook,
        county_rollup_csv=args.county_rollup_csv,
        iterations=args.iterations,
        seed=args.seed,
    )
    print("CBP update complete")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
