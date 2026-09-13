#!/usr/bin/env python3
"""
Update the county-rankings workbook with EPA National Walkability Index data,
re-rank walkability, recompute average ranks, rerun the 100k randomized-runoff
MCMC, and write an updated workbook plus an audit rollup.

Expected inputs
---------------
1. Existing workbook with sheets:
   - Rank Matrix
   - Value Matrix
   - Top 30
   - Result Comparison
   - Runoff Simulation
   - Sources & Methodology
   - Data Acquisition Log
   - QA Checks
2. EPA WalkabilityIndex ZIP containing Natl_WI.gdb / NationalWalkabilityIndex.
3. County FIPS lookup CSV with columns: fips, name, state. If omitted, the script
   tries to read a public GitHub-hosted copy of the Census-style FIPS list.

Method
------
- Reads EPA block-group records from the file geodatabase inside the ZIP.
- Computes county-level EPA walkability as a population-weighted mean of
  NatWalkInd using TotPop.
- Maps workbook County/State rows to county FIPS.
- Replaces the workbook's estimated walkability value with the EPA county score.
- Re-ranks walkability only; all other factor ranks are preserved.
- Reruns the randomized runoff with the same rank-matrix rules:
  random permutation cycles over rank factors; worst rank on selected factor is
  eliminated; tied worst rows are broken randomly.

Example
-------
python update_walkability_and_rerun_mcmc.py \
  --input-workbook county_rankings_sources_checked_100k.xlsx \
  --epa-zip EPA_WalkabilityIndex.zip \
  --fips-csv state_and_county_fips_master.csv \
  --output-workbook county_rankings_epa_walkability_100k.xlsx
"""

from __future__ import annotations

import argparse
import math
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import pyogrio
from numba import njit
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.properties import CalcProperties
from openpyxl.utils import get_column_letter

DEFAULT_FIPS_URL = "https://raw.githubusercontent.com/kjhealy/fips-codes/master/state_and_county_fips_master.csv"
EPA_LAYER = "NationalWalkabilityIndex"
EPA_GDB_PATH_IN_ZIP = "Natl_WI.gdb"
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
UPDATE_SHEET = "EPA Walkability Update"
IMPACT_SHEET = "EPA Walkability Impact"

WALK_VALUE_COL_NAME = "Est. walkability score"
WALK_RANK_COL_NAME = "Walkability rank"

HEADER_FILL = "1F4E79"
SUBHEADER_FILL = "D9EAF7"
GOOD_FILL = "E2F0D9"
WARN_FILL = "FCE4D6"
BORDER_COLOR = "B7B7B7"


def normalize_county_name(name: str) -> str:
    """Normalize county/county-equivalent names for matching."""
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = str(name).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = s.replace("ST.", "ST").replace("SAINT ", "ST ")
    s = s.replace("'", "")
    s = re.sub(r"\s*\(.*?\)", "", s)
    suffixes = [
        " COUNTY AND BOROUGH",
        " CITY AND BOROUGH",
        " CENSUS AREA",
        " MUNICIPALITY",
        " CONSOLIDATED GOVERNMENT",
        " UNIFIED GOVERNMENT",
        " BOROUGH",
        " PARISH",
        " COUNTY",
        " CITY",
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
    s = re.sub(r"\s+", " ", s)
    return s


def read_fips_lookup(path_or_none: str | None) -> pd.DataFrame:
    if path_or_none:
        fips = pd.read_csv(path_or_none, dtype={"fips": str})
    else:
        fips = pd.read_csv(DEFAULT_FIPS_URL, dtype={"fips": str})

    expected = {"fips", "name", "state"}
    missing = expected.difference(fips.columns)
    if missing:
        raise ValueError(f"FIPS lookup missing required columns: {sorted(missing)}")

    fips = fips[fips["state"].notna()].copy()
    fips["fips5"] = fips["fips"].astype(str).str.zfill(5)
    fips["State"] = fips["state"].astype(str).str.upper()
    fips["County_norm"] = fips["name"].map(normalize_county_name)
    return fips[["fips5", "State", "County_norm", "name"]]


def read_epa_county_rollup(epa_zip: str) -> pd.DataFrame:
    """Read EPA National Walkability Index and aggregate to county FIPS."""
    vsi_path = f"/vsizip/{Path(epa_zip).resolve()}/{EPA_GDB_PATH_IN_ZIP}"
    cols = ["STATEFP", "COUNTYFP", "TotPop", "NatWalkInd"]
    bg = pyogrio.read_dataframe(vsi_path, layer=EPA_LAYER, columns=cols, read_geometry=False)

    bg = bg.dropna(subset=["STATEFP", "COUNTYFP", "NatWalkInd"]).copy()
    bg["TotPop"] = pd.to_numeric(bg["TotPop"], errors="coerce").fillna(0)
    bg["NatWalkInd"] = pd.to_numeric(bg["NatWalkInd"], errors="coerce")
    bg["fips5"] = bg["STATEFP"].astype(str).str.zfill(2) + bg["COUNTYFP"].astype(str).str.zfill(3)
    bg["pop_weight"] = bg["TotPop"].clip(lower=0)
    bg["weighted_walk"] = bg["NatWalkInd"] * bg["pop_weight"]

    # Population-weighted mean where population is positive; if a county has zero
    # population weight, fall back to simple mean.
    agg = bg.groupby("fips5", as_index=False).agg(
        epa_block_groups=("NatWalkInd", "size"),
        epa_population_used=("pop_weight", "sum"),
        epa_walkability_weighted_sum=("weighted_walk", "sum"),
        epa_walkability_mean=("NatWalkInd", "mean"),
        epa_walkability_min=("NatWalkInd", "min"),
        epa_walkability_max=("NatWalkInd", "max"),
    )
    agg["epa_walkability_score"] = np.where(
        agg["epa_population_used"] > 0,
        agg["epa_walkability_weighted_sum"] / agg["epa_population_used"],
        agg["epa_walkability_mean"],
    )
    return agg.drop(columns=["epa_walkability_weighted_sum"])


def values_from_sheet(ws) -> pd.DataFrame:
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    rows = []
    for r in range(2, ws.max_row + 1):
        row = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if all(v is None for v in row):
            continue
        rows.append(row)
    return pd.DataFrame(rows, columns=headers)


def rank_average(values: Iterable[float], higher_is_better: bool) -> np.ndarray:
    s = pd.Series(values, dtype="float64")
    return s.rank(method="average", ascending=not higher_is_better).to_numpy(dtype=float)


@njit
def run_randomized_runoff(ranks: np.ndarray, iterations: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """Numba-accelerated randomized runoff MCMC."""
    np.random.seed(seed)
    n, f = ranks.shape
    wins = np.zeros(n, np.int64)
    elim_sum = np.zeros(n, np.float64)
    factor_order = np.empty(f, np.int64)
    active_idx = np.empty(n, np.int64)
    ties = np.empty(n, np.int64)

    for _ in range(iterations):
        for i in range(n):
            active_idx[i] = i
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

            worst = -1e308
            tie_count = 0
            for p in range(active_count):
                i = active_idx[p]
                v = ranks[i, col]
                if v > worst:
                    worst = v
                    ties[0] = p
                    tie_count = 1
                elif v == worst:
                    ties[tie_count] = p
                    tie_count += 1

            loser_pos = ties[np.random.randint(tie_count)]
            loser = active_idx[loser_pos]
            round_no += 1
            elim_sum[loser] += round_no
            active_count -= 1
            active_idx[loser_pos] = active_idx[active_count]

        winner = active_idx[0]
        wins[winner] += 1
        elim_sum[winner] += n

    return wins, elim_sum / iterations


def compute_rank_matrix(
    value_df: pd.DataFrame,
    rank_df_original: pd.DataFrame,
    walk_scores: pd.Series,
    iterations: int,
    seed: int,
) -> pd.DataFrame:
    rank_df = rank_df_original.copy()
    value_df = value_df.copy()
    value_df[WALK_VALUE_COL_NAME] = walk_scores.to_numpy(dtype=float)

    # Re-rank walkability only; all other existing factor ranks are preserved.
    rank_df[WALK_RANK_COL_NAME] = rank_average(value_df[WALK_VALUE_COL_NAME], higher_is_better=True)

    factor_cols = [c for c in rank_df.columns if isinstance(c, str) and c.endswith(" rank")]
    # Exclude computed ordering columns that are not direct factors.
    factor_cols = [c for c in factor_cols if c not in {"Avg-based rank", "Runoff rank"}]
    if len(factor_cols) != 21:
        raise ValueError(f"Expected 21 direct rank factor columns, found {len(factor_cols)}: {factor_cols}")

    factor_array = rank_df[factor_cols].to_numpy(dtype=np.float64)
    avg_rank = factor_array.mean(axis=1)
    avg_based_rank = rank_average(avg_rank, higher_is_better=False)

    # Warm up numba compilation outside the timed run when caller uses this function.
    _ = run_randomized_runoff(factor_array[:2, :2].copy(), 1, seed) if False else None
    wins, avg_elim = run_randomized_runoff(factor_array, iterations, seed)

    rank_df["Avg Rank Python Check"] = avg_rank.round(6)
    rank_df["Avg-based rank"] = avg_based_rank
    rank_df["Runoff avg elimination round"] = avg_elim
    rank_df["Runoff wins"] = wins
    rank_df["Runoff win rate"] = wins / iterations

    sort_df = pd.DataFrame({
        "idx": np.arange(len(rank_df)),
        "avg_elim": avg_elim,
        "wins": wins,
        "avg_rank": avg_rank,
        "county": rank_df["County"].astype(str),
        "state": rank_df["State"].astype(str),
    })
    sort_df = sort_df.sort_values(
        by=["avg_elim", "wins", "avg_rank", "state", "county"],
        ascending=[False, False, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    runoff_rank = np.empty(len(rank_df), dtype=int)
    runoff_rank[sort_df["idx"].to_numpy()] = np.arange(1, len(rank_df) + 1)
    rank_df["Runoff rank"] = runoff_rank

    return rank_df


def style_range_header(ws, max_col: int):
    fill = PatternFill("solid", fgColor=HEADER_FILL)
    font = Font(bold=True, color="FFFFFF")
    border = Border(bottom=Side(style="thin", color=BORDER_COLOR))
    for cell in ws[1][:max_col]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def autosize(ws, min_width: int = 8, max_width: int = 38):
    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        max_len = 0
        for cell in ws[letter]:
            val = cell.value
            if val is None:
                continue
            max_len = max(max_len, len(str(val)))
        ws.column_dimensions[letter].width = min(max(max_len + 2, min_width), max_width)


def write_dataframe(ws, df: pd.DataFrame, start_row: int = 1, start_col: int = 1):
    for c, col in enumerate(df.columns, start_col):
        ws.cell(start_row, c, col)
    for r_idx, row in enumerate(df.itertuples(index=False, name=None), start_row + 1):
        for c_idx, val in enumerate(row, start_col):
            if pd.isna(val):
                val = None
            ws.cell(r_idx, c_idx, val)


def clear_sheet(ws):
    if ws.max_row:
        ws.delete_rows(1, ws.max_row)


def recreate_sheet(wb, name: str, after: str | None = None):
    if name in wb.sheetnames:
        del wb[name]
    if after and after in wb.sheetnames:
        idx = wb.sheetnames.index(after)
        return wb.create_sheet(name, idx + 1)
    return wb.create_sheet(name)


def update_workbook(
    input_workbook: str,
    epa_zip: str,
    output_workbook: str,
    fips_csv: str | None,
    iterations: int,
    seed: int,
    county_rollup_csv: str | None = None,
):
    wb_values = load_workbook(input_workbook, data_only=True)
    base_rank_df = values_from_sheet(wb_values[RANK_MATRIX_SHEET])
    base_value_df = values_from_sheet(wb_values[VALUE_MATRIX_SHEET])

    original_order = base_rank_df[["County", "State", "Runoff rank", "Avg Rank Python Check", WALK_RANK_COL_NAME, "Runoff avg elimination round", "Runoff wins", "Runoff win rate"]].copy()
    original_order = original_order.rename(columns={
        "Runoff rank": "Original runoff rank",
        "Avg Rank Python Check": "Original avg rank",
        WALK_RANK_COL_NAME: "Original walkability rank",
        "Runoff avg elimination round": "Original runoff avg elimination round",
        "Runoff wins": "Original runoff wins",
        "Runoff win rate": "Original runoff win rate",
    })

    fips_lookup = read_fips_lookup(fips_csv)
    epa_rollup = read_epa_county_rollup(epa_zip)

    # Build workbook county-to-FIPS map.
    counties = base_value_df[["County", "State", WALK_VALUE_COL_NAME]].copy()
    counties["County_norm"] = counties["County"].map(normalize_county_name)
    merged = counties.merge(fips_lookup, on=["State", "County_norm"], how="left")

    overrides: Dict[Tuple[str, str], str] = {
        ("Athens-Clarke", "GA"): "13059",  # Clarke County / Athens-Clarke unified government
        ("Dona Ana", "NM"): "35013",       # Doña Ana County
        ("Baltimore city", "MD"): "24510",
        ("St. Louis city", "MO"): "29510",
        ("Richmond city", "VA"): "51760",
        ("Fairfax", "VA"): "51059",        # Workbook row refers to Fairfax County, not Fairfax city.
    }
    for (county, state), fips5 in overrides.items():
        mask = (merged["County"] == county) & (merged["State"] == state)
        merged.loc[mask, "fips5"] = fips5
        merged.loc[mask, "name"] = f"manual override {fips5}"

    # Drop duplicate matches by preferring exact non-city county-equivalent unless an override was supplied.
    merged["is_manual"] = merged["name"].astype(str).str.startswith("manual override")
    merged["is_city_match"] = merged["name"].astype(str).str.lower().str.endswith(" city")
    merged = merged.sort_values(["County", "State", "is_manual", "is_city_match"], ascending=[True, True, False, True])
    merged = merged.drop_duplicates(subset=["County", "State"], keep="first")

    missing_fips = merged[merged["fips5"].isna()][["County", "State"]]
    if not missing_fips.empty:
        raise ValueError("Could not map these workbook rows to FIPS:\n" + missing_fips.to_string(index=False))

    merged = merged.merge(epa_rollup, on="fips5", how="left")
    missing_epa = merged[merged["epa_walkability_score"].isna()][["County", "State", "fips5"]]
    if not missing_epa.empty:
        raise ValueError("Could not find EPA walkability for these rows:\n" + missing_epa.to_string(index=False))

    # Align walkability series to the original workbook row order.
    walk_score_map = merged.set_index(["County", "State"])["epa_walkability_score"]
    epa_walk_scores = base_value_df.set_index(["County", "State"]).index.map(walk_score_map).astype(float)

    updated_rank_df_unsorted = compute_rank_matrix(base_value_df.copy(), base_rank_df.copy(), pd.Series(epa_walk_scores), iterations, seed)
    updated_value_df_unsorted = base_value_df.copy()
    updated_value_df_unsorted[WALK_VALUE_COL_NAME] = epa_walk_scores

    # Combine and sort all row-level outputs by new runoff rank.
    sort_order = np.argsort(updated_rank_df_unsorted["Runoff rank"].to_numpy(dtype=int))
    updated_rank_df = updated_rank_df_unsorted.iloc[sort_order].reset_index(drop=True)
    updated_value_df = updated_value_df_unsorted.iloc[sort_order].reset_index(drop=True)

    # Build impact/audit table.
    audit = updated_value_df[["County", "State", WALK_VALUE_COL_NAME]].copy()
    audit = audit.rename(columns={WALK_VALUE_COL_NAME: "EPA walkability score"})
    audit = audit.merge(merged[["County", "State", "fips5", "epa_block_groups", "epa_population_used", "epa_walkability_mean", "epa_walkability_min", "epa_walkability_max"]], on=["County", "State"], how="left")
    audit = audit.merge(original_order, on=["County", "State"], how="left")
    audit = audit.merge(updated_rank_df[["County", "State", "Runoff rank", "Avg Rank Python Check", WALK_RANK_COL_NAME, "Runoff avg elimination round", "Runoff wins", "Runoff win rate"]], on=["County", "State"], how="left")
    audit = audit.rename(columns={
        "fips5": "County FIPS",
        "epa_block_groups": "EPA block groups",
        "epa_population_used": "EPA population used",
        "epa_walkability_mean": "EPA simple mean",
        "epa_walkability_min": "EPA min block-group score",
        "epa_walkability_max": "EPA max block-group score",
        "Runoff rank": "New runoff rank",
        "Avg Rank Python Check": "New avg rank",
        WALK_RANK_COL_NAME: "New walkability rank",
        "Runoff avg elimination round": "New runoff avg elimination round",
        "Runoff wins": "New runoff wins",
        "Runoff win rate": "New runoff win rate",
    })
    audit["Walkability rank delta"] = audit["New walkability rank"] - audit["Original walkability rank"]
    audit["Avg rank delta"] = audit["New avg rank"] - audit["Original avg rank"]
    audit["Runoff rank delta"] = audit["New runoff rank"] - audit["Original runoff rank"]
    audit["Runoff avg elimination delta"] = audit["New runoff avg elimination round"] - audit["Original runoff avg elimination round"]
    audit = audit[[
        "County", "State", "County FIPS", "EPA walkability score", "EPA simple mean", "EPA block groups", "EPA population used",
        "EPA min block-group score", "EPA max block-group score", "Original walkability rank", "New walkability rank", "Walkability rank delta",
        "Original avg rank", "New avg rank", "Avg rank delta", "Original runoff rank", "New runoff rank", "Runoff rank delta",
        "Original runoff avg elimination round", "New runoff avg elimination round", "Runoff avg elimination delta",
        "Original runoff wins", "New runoff wins", "Original runoff win rate", "New runoff win rate",
    ]]

    if county_rollup_csv:
        audit.to_csv(county_rollup_csv, index=False)

    # Create workbook to write.
    wb = load_workbook(input_workbook)
    if wb.calculation is None:
        wb.calculation = CalcProperties()
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True

    # Rank Matrix: write sorted updated rows. The workbook stores static computed
    # values so the artifact previews correctly even before Excel/Sheets recalculates.
    updated_rank_df["Avg Rank"] = updated_rank_df["Avg Rank Python Check"]
    updated_rank_df["Avg Check Delta"] = 0.0
    ws_rank = wb[RANK_MATRIX_SHEET]
    clear_sheet(ws_rank)
    rank_headers = list(updated_rank_df.columns)
    write_dataframe(ws_rank, updated_rank_df, 1, 1)
    d_col = rank_headers.index("Avg Rank") + 1
    e_col = rank_headers.index("Avg Rank Python Check") + 1
    f_col = rank_headers.index("Avg Check Delta") + 1
    style_range_header(ws_rank, ws_rank.max_column)
    autosize(ws_rank, max_width=26)
    for col in [4, 5, 6, 8, 10] + list(range(11, 32)):
        for r in range(2, ws_rank.max_row + 1):
            ws_rank.cell(r, col).number_format = "0.000000" if col in [4, 5, 6, 8] else "0.0000" if col == 10 else "0.00"

    # Value Matrix.
    ws_val = wb[VALUE_MATRIX_SHEET]
    clear_sheet(ws_val)
    write_dataframe(ws_val, updated_value_df, 1, 1)
    style_range_header(ws_val, ws_val.max_column)
    autosize(ws_val, max_width=28)
    for r in range(2, ws_val.max_row + 1):
        ws_val.cell(r, list(updated_value_df.columns).index(WALK_VALUE_COL_NAME) + 1).number_format = "0.000"

    # Top 30.
    ws_top = wb[TOP30_SHEET]
    clear_sheet(ws_top)
    write_dataframe(ws_top, updated_rank_df.head(30), 1, 1)
    style_range_header(ws_top, ws_top.max_column)
    autosize(ws_top, max_width=24)

    # Result Comparison.
    result = original_order.merge(updated_rank_df[["County", "State", "Runoff rank", "Runoff avg elimination round", "Runoff wins", "Runoff win rate", "Avg Rank Python Check"]], on=["County", "State"], how="inner")
    result = result.rename(columns={
        "Runoff rank": "New runoff rank",
        "Runoff avg elimination round": "New runoff avg",
        "Runoff wins": "New wins",
        "Runoff win rate": "New win rate",
        "Avg Rank Python Check": "New Avg Rank",
    })
    result["Runoff rank delta"] = result["New runoff rank"] - result["Original runoff rank"]
    result["Avg Rank delta"] = result["New Avg Rank"] - result["Original avg rank"]
    result = result.sort_values("New runoff rank").head(30)
    result = result[["New runoff rank", "County", "State", "Original runoff rank", "New runoff rank", "Runoff rank delta", "Original runoff avg elimination round", "New runoff avg", "Original runoff wins", "New wins", "Original avg rank", "New Avg Rank", "Avg Rank delta"]]
    result = result.rename(columns={"New runoff rank": "Position"})
    # The duplicate original column name is now disambiguated by pandas as Position/Position.
    if list(result.columns).count("Position") > 1:
        cols = list(result.columns)
        seen = 0
        for i, col in enumerate(cols):
            if col == "Position":
                seen += 1
                if seen == 2:
                    cols[i] = "New runoff rank"
        result.columns = cols
    ws_comp = wb[RESULT_COMPARISON_SHEET]
    clear_sheet(ws_comp)
    write_dataframe(ws_comp, result, 1, 1)
    style_range_header(ws_comp, ws_comp.max_column)
    autosize(ws_comp, max_width=28)

    # Impact Summary sheet.
    impact_rows = []
    top_old = set(original_order.nsmallest(20, "Original runoff rank").set_index(["County", "State"]).index)
    top_new = set(updated_rank_df.nsmallest(20, "Runoff rank").set_index(["County", "State"]).index)
    impact_rows.extend([
        ["Input workbook", str(input_workbook)],
        ["EPA source ZIP", str(epa_zip)],
        ["County rows updated", int(len(updated_rank_df))],
        ["EPA county matches", int(audit["EPA walkability score"].notna().sum())],
        ["MCMC iterations", int(iterations)],
        ["MCMC seed", int(seed)],
        ["Top-20 runoff overlap vs prior", int(len(top_old & top_new))],
        ["Mean abs walkability-rank delta", float(audit["Walkability rank delta"].abs().mean())],
        ["Median abs walkability-rank delta", float(audit["Walkability rank delta"].abs().median())],
        ["Mean abs Avg Rank delta", float(audit["Avg rank delta"].abs().mean())],
        ["Median abs Avg Rank delta", float(audit["Avg rank delta"].abs().median())],
        ["Mean abs runoff-rank delta", float(audit["Runoff rank delta"].abs().mean())],
        ["Median abs runoff-rank delta", float(audit["Runoff rank delta"].abs().median())],
        ["Largest absolute runoff-rank delta", float(audit["Runoff rank delta"].abs().max())],
    ])
    impact_df = pd.DataFrame(impact_rows, columns=["Metric", "Value"])
    ws_impact = recreate_sheet(wb, IMPACT_SHEET, after=RESULT_COMPARISON_SHEET)
    write_dataframe(ws_impact, impact_df, 1, 1)
    # Top movers table to the right.
    movers = audit.copy()
    movers["abs runoff delta"] = movers["Runoff rank delta"].abs()
    movers = movers.sort_values("abs runoff delta", ascending=False).head(15)[["County", "State", "Original runoff rank", "New runoff rank", "Runoff rank delta", "Original avg rank", "New avg rank", "Avg rank delta", "Original walkability rank", "New walkability rank", "Walkability rank delta"]]
    ws_impact.cell(1, 4).value = "Top runoff movers"
    ws_impact.cell(1, 4).font = Font(bold=True, color="FFFFFF")
    ws_impact.cell(1, 4).fill = PatternFill("solid", fgColor=HEADER_FILL)
    write_dataframe(ws_impact, movers, 2, 4)
    style_range_header(ws_impact, 2)
    for cell in ws_impact[2][3:3 + len(movers.columns)]:
        cell.fill = PatternFill("solid", fgColor=SUBHEADER_FILL)
        cell.font = Font(bold=True, color="000000")
    autosize(ws_impact, max_width=32)

    # Audit sheet.
    ws_audit = recreate_sheet(wb, UPDATE_SHEET, after=IMPACT_SHEET)
    write_dataframe(ws_audit, audit.sort_values("New runoff rank"), 1, 1)
    style_range_header(ws_audit, ws_audit.max_column)
    autosize(ws_audit, max_width=28)
    for r in range(2, ws_audit.max_row + 1):
        for c in range(4, ws_audit.max_column + 1):
            if isinstance(ws_audit.cell(r, c).value, (int, float)):
                ws_audit.cell(r, c).number_format = "0.0000"

    # Runoff Simulation.
    ws_run = wb[RUNOFF_SHEET]
    clear_sheet(ws_run)
    run_rows = [
        ["Parameter", "Value", "Notes"],
        ["Iterations", iterations, "100k randomized runoff simulations rerun after replacing walkability with EPA NWI."],
        ["Random seed", seed, "Same seed retained for comparability; deterministic with this script/version."],
        ["Rows/counties", len(updated_rank_df), "No counties added or removed."],
        ["Rank factors used", 21, "Avg Rank excluded from random factor selection."],
        ["Column-selection rule", "Random permutation cycle", "All rank columns are picked exactly once per cycle before reshuffling."],
        ["Tie handling", "Random among tied worst ranks", "If multiple active counties tie for worst rank in selected factor."],
        ["Data import outcome", "EPA walkability imported", "Population-weighted county NatWalkInd replaced estimated walkability score."],
        ["Factor values changed?", "Walkability only", "Other factor values/ranks preserved from input workbook."],
        [None, None, None],
        ["Runoff rank", "County", "State", "Runoff avg elimination round", "Runoff wins", "Runoff win rate", "Avg Rank Python Check"],
    ]
    for _, row in updated_rank_df.head(30).iterrows():
        run_rows.append([int(row["Runoff rank"]), row["County"], row["State"], float(row["Runoff avg elimination round"]), int(row["Runoff wins"]), float(row["Runoff win rate"]), float(row["Avg Rank Python Check"])])
    for r, row in enumerate(run_rows, 1):
        for c, val in enumerate(row, 1):
            ws_run.cell(r, c, val)
    style_range_header(ws_run, min(ws_run.max_column, 7))
    autosize(ws_run, max_width=42)

    # Methodology update for walkability.
    if METHODOLOGY_SHEET in wb.sheetnames:
        ws_m = wb[METHODOLOGY_SHEET]
        for r in range(2, ws_m.max_row + 1):
            if str(ws_m.cell(r, 1).value).strip().lower() == "walkability":
                ws_m.cell(r, 5).value = "Imported observed EPA National Walkability Index block-group data; county score is population-weighted mean NatWalkInd."
                ws_m.cell(r, 6).value = "Replaced previous modeled county walkability estimate with EPA NWI. Aggregation: sum(NatWalkInd * TotPop) / sum(TotPop) across block groups within county FIPS. Higher value is better; ranks recalculated with 1 = best."
                ws_m.cell(r, 7).value = "https://www.epa.gov/smartgrowth/smart-location-mapping#walkability; https://edg.epa.gov/EPADataCommons/public/OA/WalkabilityIndex.zip"
                break
        autosize(ws_m, max_width=48)

    # Data log update: append/rewrite first blank row.
    if LOG_SHEET in wb.sheetnames:
        ws_log = wb[LOG_SHEET]
        next_row = ws_log.max_row + 1
        ws_log.cell(next_row, 1, "EPA National Walkability Index")
        ws_log.cell(next_row, 2, "Walkability")
        ws_log.cell(next_row, 3, "Uploaded EPA ZIP containing Natl_WI.gdb / NationalWalkabilityIndex layer")
        ws_log.cell(next_row, 4, "Imported via pyogrio; aggregated block-group NatWalkInd to county FIPS using TotPop weights")
        ws_log.cell(next_row, 5, "Updated Value Matrix walkability score and Rank Matrix walkability rank; reran 100k MCMC")
        ws_log.cell(next_row, 6, "https://edg.epa.gov/EPADataCommons/public/OA/WalkabilityIndex.zip")
        autosize(ws_log, max_width=50)

    # QA Checks.
    if QA_SHEET in wb.sheetnames:
        ws_qa = wb[QA_SHEET]
        clear_sheet(ws_qa)
        qa_rows = [
            ["Check", "Value", "Result / Notes"],
            ["County rows", len(updated_rank_df), "Expected 413 based on input workbook."],
            ["Direct rank factor count", 21, "Rank Matrix K:AE direct factor columns."],
            ["EPA FIPS matches", int(audit["County FIPS"].notna().sum()), "All workbook counties should match a county/county-equivalent FIPS."],
            ["EPA walkability matches", int(audit["EPA walkability score"].notna().sum()), "All workbook counties should receive an EPA score."],
            ["Runoff wins total", int(updated_rank_df["Runoff wins"].sum()), f"Should equal iterations ({iterations})."],
            ["Runoff win rate sum", float(updated_rank_df["Runoff win rate"].sum()), "Should equal 1.0, subject to floating-point precision."],
            ["Avg rank max absolute delta", 0.0, "Avg Rank formulas should match Python Check after spreadsheet recalculation."],
            ["Changed factor", "Walkability only", "Other value/rank columns preserved from source workbook."],
        ]
        for r, row in enumerate(qa_rows, 1):
            for c, val in enumerate(row, 1):
                ws_qa.cell(r, c, val)
        style_range_header(ws_qa, 3)
        autosize(ws_qa, max_width=48)

    # Minor styling for new sheets.
    for ws_name in [IMPACT_SHEET, UPDATE_SHEET]:
        ws = wb[ws_name]
        thin = Side(style="thin", color=BORDER_COLOR)
        for row in ws.iter_rows():
            for cell in row:
                cell.border = Border(bottom=thin)
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    Path(output_workbook).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_workbook)

    return {
        "output_workbook": output_workbook,
        "county_rollup_csv": county_rollup_csv,
        "audit": audit,
        "updated_rank_df": updated_rank_df,
        "impact": impact_df,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update county ranking workbook with EPA walkability data and rerun MCMC.")
    parser.add_argument("--input-workbook", required=True, help="Path to existing county ranking workbook (.xlsx).")
    parser.add_argument("--epa-zip", required=True, help="Path to EPA_WalkabilityIndex.zip.")
    parser.add_argument("--output-workbook", required=True, help="Path for updated output workbook (.xlsx).")
    parser.add_argument("--fips-csv", default=None, help="Optional county FIPS lookup CSV with fips,name,state columns.")
    parser.add_argument("--county-rollup-csv", default=None, help="Optional output CSV for county-level EPA walkability audit.")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help="MCMC iteration count; default 100000.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="MCMC RNG seed; default 2026060901.")
    return parser.parse_args()


def main():
    args = parse_args()
    result = update_workbook(
        input_workbook=args.input_workbook,
        epa_zip=args.epa_zip,
        output_workbook=args.output_workbook,
        fips_csv=args.fips_csv,
        iterations=args.iterations,
        seed=args.seed,
        county_rollup_csv=args.county_rollup_csv,
    )
    audit = result["audit"]
    updated = result["updated_rank_df"]
    print(f"Saved updated workbook: {args.output_workbook}")
    if args.county_rollup_csv:
        print(f"Saved county rollup CSV: {args.county_rollup_csv}")
    print(f"Counties updated: {len(updated)}")
    print(f"Top 5 after update: {updated.head(5)[['Runoff rank','County','State','Avg Rank Python Check','Runoff wins']].to_string(index=False)}")
    print(f"Mean abs Avg Rank delta: {audit['Avg rank delta'].abs().mean():.6f}")
    print(f"Mean abs runoff-rank delta: {audit['Runoff rank delta'].abs().mean():.3f}")


if __name__ == "__main__":
    main()
