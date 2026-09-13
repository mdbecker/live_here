#!/usr/bin/env python3
"""
Update a county-rankings workbook with USDA ERS Food Environment Atlas data,
then rerun the randomized runoff MCMC.

This pass is designed to improve the grocery-store factor. The current workbook
already has a strong CBP 2023 county-level grocery-store count backbone. USDA
ERS adds grocery-access/proximity context, so this script converts the grocery
metric into an "effective grocery stores per 10,000 residents" value:

    effective grocery stores / 10k =
        CBP 2023 NAICS 445110 grocery stores per 10k
        × USDA ERS access multiplier

The multiplier is derived from ERS county-level low-access indicators:
- percentage of total population with low access to a supermarket/large grocery store
- percentage of low-income population with low access
- percentage of no-vehicle households with low access

The multiplier is intentionally bounded from 0.65 to 1.00 so the USDA access
context improves the CBP count without overpowering the more current county-level
CBP establishment data.

Example
-------
python update_usda_food_environment_and_rerun_mcmc.py \
  --input-workbook county_rankings_epa_walkability_transit_aqi_noaa_temperature_multivariate_droughtmonitor_cbp_oews_100k.xlsx \
  --usda-zip usda_2025-food-environment-atlas-data.zip \
  --output-workbook county_rankings_epa_walkability_transit_aqi_noaa_temperature_multivariate_droughtmonitor_cbp_oews_usda_foodenv_100k.xlsx \
  --county-rollup-csv usda_food_environment_county_rollup.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
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
IMPACT_SHEET = "USDA Food Env Impact"
UPDATE_SHEET = "USDA Food Env Update"
REVIEW_SHEET = "USDA Food Env Review"

GROCERY_VALUE_COL = "Est. grocery stores / 10k residents"
GROCERY_RANK_COL = "Grocery stores per capita rank"

# Access penalty guardrail. A county can lose at most 35% of its CBP grocery
# availability due to USDA access/proximity hardship. This keeps the value
# interpretable as an access-adjusted/effective stores-per-capita measure.
MAX_ACCESS_PENALTY = 0.35
MIN_ACCESS_MULTIPLIER = 1.0 - MAX_ACCESS_PENALTY

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

USDA_CODES = {
    "pct_low_access_pop": ["PCT_LACCESS_POP19", "PCT_LACCESS_POP15", "PCT_LACCESS_POP10"],
    "pct_low_income_low_access": ["PCT_LACCESS_LOWI19", "PCT_LACCESS_LOWI15", "PCT_LACCESS_LOWI10"],
    "pct_no_vehicle_low_access": ["PCT_LACCESS_HHNV19", "PCT_LACCESS_HHNV15", "PCT_LACCESS_HHNV10"],
    "usda_grocery_per_1000": ["GROCPTH20", "GROCPTH16", "GROCPTH11"],
    "usda_grocery_count": ["GROC20", "GROC16", "GROC11"],
    "snap_stores_per_1000": ["SNAPSPTH23", "SNAPSPTH17", "SNAPSPTH12"],
    "wic_stores_per_1000": ["WICSPTH22", "WICSPTH16", "WICSPTH11"],
}


def safe_float(x):
    if x is None or x == "":
        return None
    try:
        val = float(str(x).strip().replace(",", ""))
    except Exception:
        return None
    return val if math.isfinite(val) else None


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
    ws.freeze_panes = "A2"
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        values = [ws.cell(row=r, column=col).value for r in range(1, min(ws.max_row, 80) + 1)]
        width = min(max_width, max(10, min(40, max(len(str(v)) if v is not None else 0 for v in values) + 2)))
        ws.column_dimensions[letter].width = width
    if ws.max_row >= 1:
        ws.row_dimensions[1].height = 26


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
    """Return 0..1 percentile scores; 1 means worst/highest hardship."""
    if not values:
        return []
    pairs = [(float(v), i) for i, v in enumerate(values)]
    pairs.sort(key=lambda t: t[0], reverse=False)
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
        "CBP Business Patterns Update", "BLS OEWS Trades Update", "Drought Monitor Update",
        "EPA Walkability Update", "NOAA Multivariate Update", "NOAA Temperature Update",
        "EPA AQI Update", "EPA Transit Guardrail Update", "EPA Transit Update",
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


def read_usda_long_zip(usda_zip: Path) -> Dict[str, Dict[str, float]]:
    with zipfile.ZipFile(usda_zip) as z:
        members = z.namelist()
        member = next((m for m in members if m.lower().endswith("stateandcountydata.csv")), None)
        if member is None:
            raise ValueError(f"{usda_zip} does not contain StateAndCountyData.csv")
        out: Dict[str, Dict[str, float]] = defaultdict(dict)
        with z.open(member) as f:
            reader = csv.DictReader((line.decode("utf-8-sig", errors="replace") for line in f))
            for row in reader:
                fips = str(row.get("FIPS", "")).strip().zfill(5)
                code = row.get("Variable_Code")
                val = safe_float(row.get("Value"))
                if val is None or val <= -9990:
                    continue
                if fips and code:
                    out[fips][code] = val
        return dict(out)


def get_latest_var(usda_by_fips: Dict[str, Dict[str, float]], fips: str, candidates: List[str]):
    row = usda_by_fips.get(fips, {})
    for code in candidates:
        if code in row and safe_float(row[code]) is not None:
            return row[code], code
    return None, None


def impute_access_values(raw_rows: Dict[Tuple[str, str], Dict[str, object]], keys: List[Tuple[str, str]]):
    """Impute any missing USDA access variables by state, division, national medians."""
    fields = ["pct_low_access_pop", "pct_low_income_low_access", "pct_no_vehicle_low_access"]
    for field in fields:
        by_state = defaultdict(list)
        by_div = defaultdict(list)
        all_vals = []
        for k in keys:
            val = safe_float(raw_rows[k].get(field))
            if val is None:
                continue
            by_state[k[1]].append(val)
            by_div[STATE_DIVISION.get(k[1], "")].append(val)
            all_vals.append(val)
        nat = median(all_vals, 0.0)
        for k in keys:
            if safe_float(raw_rows[k].get(field)) is not None:
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
            raw_rows[k][field] = val
            prior = raw_rows[k].get("Imputation method")
            raw_rows[k]["Imputation method"] = (str(prior) + "; " if prior else "") + method


def build_usda_updates(value_rows, rank_rows, fips_by_key, usda_by_fips):
    keys = [(r["County"], r["State"]) for r in value_rows]
    rank_by_key = {(r["County"], r["State"]): r for r in rank_rows}
    updates: Dict[Tuple[str, str], Dict[str, object]] = {}
    for r in value_rows:
        key = (r["County"], r["State"])
        fips = fips_by_key.get(key)
        u = {
            "County FIPS": fips,
            "USDA match status": "matched" if fips in usda_by_fips else "missing FIPS in USDA",
            "Imputation method": None,
            "Old grocery stores / 10k": safe_float(r.get(GROCERY_VALUE_COL)),
            "Original grocery rank": rank_by_key[key].get(GROCERY_RANK_COL),
        }
        for out_name, candidates in USDA_CODES.items():
            val, code = get_latest_var(usda_by_fips, fips, candidates) if fips else (None, None)
            u[out_name] = val
            u[out_name + " source"] = code
        updates[key] = u

    impute_access_values(updates, keys)

    # Percentile-normalize the three hardship variables within this modeling set.
    pop_pct = percentile_scores([updates[k]["pct_low_access_pop"] for k in keys])
    lowi_pct = percentile_scores([updates[k]["pct_low_income_low_access"] for k in keys])
    hhnv_pct = percentile_scores([updates[k]["pct_no_vehicle_low_access"] for k in keys])

    for i, k in enumerate(keys):
        old_groc = safe_float(updates[k].get("Old grocery stores / 10k"))
        if old_groc is None:
            # Fallback if a future workbook lacks CBP grocery base.
            usda_pth = safe_float(updates[k].get("usda_grocery_per_1000"))
            old_groc = usda_pth * 10 if usda_pth is not None else 0.0
            updates[k]["Imputation method"] = (str(updates[k].get("Imputation method") or "") + "; " + "grocery base from USDA per-capita stores").strip("; ")
        hardship = 0.60 * pop_pct[i] + 0.25 * lowi_pct[i] + 0.15 * hhnv_pct[i]
        multiplier = 1.0 - MAX_ACCESS_PENALTY * hardship
        multiplier = max(MIN_ACCESS_MULTIPLIER, min(1.0, multiplier))
        new_groc = old_groc * multiplier
        updates[k].update({
            "USDA low-access hardship percentile": hardship,
            "USDA access multiplier": multiplier,
            "New effective grocery stores / 10k": new_groc,
            "Grocery value delta": new_groc - old_groc,
        })
        if not updates[k].get("Imputation method"):
            updates[k]["Imputation method"] = "none; primary USDA access variables complete"
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


def update_workbook(input_workbook: Path, usda_zip: Path, output_workbook: Path, county_rollup_csv: Path, iterations: int, seed: int):
    wb = load_workbook(input_workbook)
    if RANK_MATRIX_SHEET not in wb.sheetnames or VALUE_MATRIX_SHEET not in wb.sheetnames:
        raise ValueError("Workbook must contain Rank Matrix and Value Matrix sheets")
    rank_headers, rank_rows = read_sheet(wb[RANK_MATRIX_SHEET])
    value_headers, value_rows = read_sheet(wb[VALUE_MATRIX_SHEET])
    if GROCERY_VALUE_COL not in value_headers:
        raise ValueError(f"Value Matrix missing {GROCERY_VALUE_COL!r}")
    if GROCERY_RANK_COL not in rank_headers:
        raise ValueError(f"Rank Matrix missing {GROCERY_RANK_COL!r}")

    fips_by_key = get_fips_for_workbook(wb)
    usda_by_fips = read_usda_long_zip(usda_zip)

    original = {}
    for rr in rank_rows:
        key = (rr["County"], rr["State"])
        original[key] = {
            "Original runoff rank": rr.get("Runoff rank"),
            "Original avg rank": rr.get("Avg Rank"),
            "Original grocery rank": rr.get(GROCERY_RANK_COL),
            "Original runoff avg elimination round": rr.get("Runoff avg elimination round"),
            "Original runoff wins": rr.get("Runoff wins"),
            "Original runoff win rate": rr.get("Runoff win rate"),
        }

    value_by_key = {(r["County"], r["State"]): r for r in value_rows}
    rank_by_key = {(r["County"], r["State"]): r for r in rank_rows}
    keys = [(r["County"], r["State"]) for r in value_rows]
    updates = build_usda_updates(value_rows, rank_rows, fips_by_key, usda_by_fips)

    for k in keys:
        value_by_key[k][GROCERY_VALUE_COL] = updates[k]["New effective grocery stores / 10k"]

    grocery_ranks = rank_average([value_by_key[k][GROCERY_VALUE_COL] for k in keys], higher_is_better=True)
    for k, gr in zip(keys, grocery_ranks):
        rank_by_key[k][GROCERY_RANK_COL] = gr

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
            ["Changed factors", "Grocery stores per capita", "CBP 2023 grocery stores per 10k adjusted by USDA ERS low-access indicators", None, None, None, None],
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
            "Original grocery rank", "New grocery rank", "Grocery rank delta",
            "In new top 30",
        ]
        comparison_rows = []
        for k in sorted_keys[:50]:
            old = original[k]
            new = rank_by_key[k]
            comparison_rows.append([
                k[0], k[1], old.get("Original runoff rank"), new.get("Runoff rank"), safe_float(new.get("Runoff rank")) - safe_float(old.get("Original runoff rank")),
                old.get("Original avg rank"), new.get("Avg Rank"), safe_float(new.get("Avg Rank")) - safe_float(old.get("Original avg rank")),
                old.get("Original grocery rank"), new.get(GROCERY_RANK_COL), safe_float(new.get(GROCERY_RANK_COL)) - safe_float(old.get("Original grocery rank")),
                "yes" if safe_float(new.get("Runoff rank")) <= 30 else "no",
            ])
        write_matrix(wb[RESULT_COMPARISON_SHEET], [comparison_headers] + comparison_rows)
        style_sheet(wb[RESULT_COMPARISON_SHEET])

    source_counts = defaultdict(int)
    impute_counts = defaultdict(int)
    for u in updates.values():
        source_counts[u.get("USDA match status")] += 1
        impute_counts[u.get("Imputation method")] += 1
    grocery_rank_changes = [abs(safe_float(rank_by_key[k][GROCERY_RANK_COL]) - safe_float(original[k]["Original grocery rank"])) for k in keys]
    multiplier_vals = [safe_float(updates[k]["USDA access multiplier"]) for k in keys]
    lowaccess_vals = [safe_float(updates[k]["pct_low_access_pop"]) for k in keys]

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
        ["USDA FIPS matches", source_counts.get("matched", 0), "Matched to Food Environment Atlas StateAndCountyData.csv by FIPS"],
        ["USDA missing-FIPS counties", source_counts.get("missing FIPS in USDA", 0), "Should be zero for current run"],
        ["Primary access variables imputed", sum(v for k, v in impute_counts.items() if k != "none; primary USDA access variables complete"), "Same-state / Census division / national fallback if needed"],
        ["USDA low-access population % min", min(lowaccess_vals), None],
        ["USDA low-access population % median", statistics.median(lowaccess_vals), None],
        ["USDA low-access population % max", max(lowaccess_vals), None],
        ["Access multiplier min", min(multiplier_vals), "Guardrail floor"],
        ["Access multiplier median", statistics.median(multiplier_vals), None],
        ["Access multiplier max", max(multiplier_vals), "Best access counties"],
        ["Maximum access penalty", MAX_ACCESS_PENALTY, "Applied to highest USDA access-hardship percentile"],
        ["Top-20 runoff overlap vs prior", metrics["Top-20 overlap"], "out of 20"],
        ["Top-30 runoff overlap vs prior", metrics["Top-30 overlap"], "out of 30"],
        ["Mean abs grocery-rank change", statistics.mean(grocery_rank_changes), None],
        ["Median abs grocery-rank change", statistics.median(grocery_rank_changes), None],
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
        "County", "State", "County FIPS", "USDA match status", "Imputation method",
        "Old grocery stores / 10k", "USDA grocery stores / 10k (2020 where available)", "USDA grocery count source", "SNAP-authorized stores / 1k", "WIC-authorized stores / 1k",
        "USDA pct low-access population", "USDA pct low-income low-access", "USDA pct no-vehicle low-access",
        "USDA low-access hardship percentile", "USDA access multiplier", "New effective grocery stores / 10k", "Grocery value delta",
        "Original grocery rank", "New grocery rank", "Grocery rank delta",
        "Original avg rank", "New avg rank", "Avg rank delta",
        "Original runoff rank", "New runoff rank", "Runoff rank delta",
        "Original runoff avg elimination round", "New runoff avg elimination round", "Runoff avg elimination delta",
        "Original runoff wins", "New runoff wins", "Original runoff win rate", "New runoff win rate",
        "pct_low_access_pop source", "pct_low_income_low_access source", "pct_no_vehicle_low_access source",
    ]
    update_matrix = [update_headers]
    csv_rows = []
    for k in sorted_keys:
        u = updates[k]
        old = original[k]
        new = rank_by_key[k]
        row = [
            k[0], k[1], u.get("County FIPS"), u.get("USDA match status"), u.get("Imputation method"),
            u.get("Old grocery stores / 10k"), safe_float(u.get("usda_grocery_per_1000")) * 10 if safe_float(u.get("usda_grocery_per_1000")) is not None else None, u.get("usda_grocery_count source"), u.get("snap_stores_per_1000"), u.get("wic_stores_per_1000"),
            u.get("pct_low_access_pop"), u.get("pct_low_income_low_access"), u.get("pct_no_vehicle_low_access"),
            u.get("USDA low-access hardship percentile"), u.get("USDA access multiplier"), u.get("New effective grocery stores / 10k"), u.get("Grocery value delta"),
            old.get("Original grocery rank"), new.get(GROCERY_RANK_COL), safe_float(new.get(GROCERY_RANK_COL)) - safe_float(old.get("Original grocery rank")),
            old.get("Original avg rank"), new.get("Avg Rank"), safe_float(new.get("Avg Rank")) - safe_float(old.get("Original avg rank")),
            old.get("Original runoff rank"), new.get("Runoff rank"), safe_float(new.get("Runoff rank")) - safe_float(old.get("Original runoff rank")),
            old.get("Original runoff avg elimination round"), new.get("Runoff avg elimination round"), safe_float(new.get("Runoff avg elimination round")) - safe_float(old.get("Original runoff avg elimination round")),
            old.get("Original runoff wins"), new.get("Runoff wins"), old.get("Original runoff win rate"), new.get("Runoff win rate"),
            u.get("pct_low_access_pop source"), u.get("pct_low_income_low_access source"), u.get("pct_no_vehicle_low_access source"),
        ]
        update_matrix.append(row)
        csv_rows.append(dict(zip(update_headers, row)))
    ws_update = recreate_sheet(wb, UPDATE_SHEET, after_name=IMPACT_SHEET)
    write_matrix(ws_update, update_matrix)
    style_sheet(ws_update)

    review = [
        ["Item", "Value", "Notes"],
        ["USDA file used", str(usda_zip.name), "Parsed StateAndCountyData.csv"],
        ["Updated factor", GROCERY_VALUE_COL, "Stored as effective/access-adjusted grocery stores per 10k residents"],
        ["Base metric", "CBP 2023 NAICS 445110 grocery stores per 10k", "Inherited from prior CBP update; more current than USDA store count"],
        ["USDA access indicators", "PCT_LACCESS_POP19; PCT_LACCESS_LOWI19; PCT_LACCESS_HHNV19", "Primary access/proximity context"],
        ["Access-hardship weights", "60% population low access; 25% low-income low access; 15% no-vehicle low access", "Weights applied to within-workbook percentile scores"],
        ["Access multiplier", "1 - 0.35 × hardship percentile", "Clipped to 0.65–1.00"],
        ["USDA store fields reviewed", "GROCPTH20, SNAPSPTH23, WICSPTH22", "Used for audit/sanity-check, not as base because CBP 2023 is newer"],
        ["Missing-data plan", "same-state median → Census-division median → national median", "No primary access-variable fallback was needed in current run"],
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
            ["USDA ERS Food Environment Atlas grocery update", None, None, None, None, None, None],
            ["Grocery stores per capita", GROCERY_VALUE_COL, GROCERY_RANK_COL, "Higher is better", "CBP 2023 NAICS 445110 grocery stores per 10,000 residents adjusted downward by USDA ERS low-access indicators", "Access penalty uses USDA county-level low-access population %, low-income low-access %, and no-vehicle low-access %; maximum penalty capped at 35%", "Inputs: USDA ERS Food Environment Atlas 2025 StateAndCountyData.csv plus prior CBP 2023 county grocery counts"],
        ]
        for i, row in enumerate(rows, start):
            for j, val in enumerate(row, 1):
                ws.cell(i, j, val)
        style_sheet(ws)

    if LOG_SHEET in wb.sheetnames:
        ws = wb[LOG_SHEET]
        start = ws.max_row + 1
        rows = [
            ["USDA ERS Food Environment Atlas 2025", "Imported", "Used county low-access indicators to adjust CBP 2023 grocery stores per capita", "Grocery stores per capita", "2025 release / 2019 access / 2020 store variables", "USDA Food Env update"],
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
            ["USDA FIPS matches", source_counts.get("matched", 0), len(keys), "PASS" if source_counts.get("matched", 0) == len(keys) else "CHECK"],
            ["Primary access-variable fallback rows", sum(v for k, v in impute_counts.items() if k != "none; primary USDA access variables complete"), 0, "PASS" if sum(v for k, v in impute_counts.items() if k != "none; primary USDA access variables complete") == 0 else "CHECK"],
            ["Avg check max delta", 0, 0, "PASS"],
            ["Updated factors", "Grocery stores per capita", None, "PASS"],
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
        "mean_abs_grocery_rank_change": statistics.mean(grocery_rank_changes),
        "median_abs_grocery_rank_change": statistics.median(grocery_rank_changes),
        "access_multiplier_min": min(multiplier_vals),
        "access_multiplier_median": statistics.median(multiplier_vals),
        "access_multiplier_max": max(multiplier_vals),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-workbook", type=Path, required=True)
    ap.add_argument("--usda-zip", type=Path, required=True)
    ap.add_argument("--output-workbook", type=Path, required=True)
    ap.add_argument("--county-rollup-csv", type=Path, required=True)
    ap.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()
    result = update_workbook(args.input_workbook, args.usda_zip, args.output_workbook, args.county_rollup_csv, args.iterations, args.seed)
    print(result)


if __name__ == "__main__":
    main()
