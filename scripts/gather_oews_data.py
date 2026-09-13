"""Acquire and normalize BLS May 2025 OEWS inputs for the trades factor."""

import argparse
import csv
import datetime
import hashlib
import json
import shutil
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.oews import (area_trade_share_details, calculate_trades,
                                    iter_oews_xlsx_rows, occupation_share)
from live_here.io import sha256

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "all": ("oesm25all.zip", "https://www.bls.gov/oes/special-requests/oesm25all.zip"),
    "state": ("oesm25st.zip", "https://www.bls.gov/oes/special-requests/oesm25st.zip"),
    "metro": ("oesm25ma.zip", "https://www.bls.gov/oes/special-requests/oesm25ma.zip"),
    "industry": ("oesm25in4.zip", "https://www.bls.gov/oes/special-requests/oesm25in4.zip"),
}
WALKABILITY = "EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv"
CBP_PARENTS = ("cbp23co.zip", "co-est2023-alldata.csv")
SELECTED = {"47-2111", "47-2152", "49-9021", "47-2181", "47-2031", "47-2141", "47-2061", "49-9041", "49-9071"}


def _provided_source(root, filename):
    """Return the immutable research archive, with old intake layout fallback."""
    root = Path(root)
    for candidate in (root / "research/legacy" / filename, root / "data/incoming" / filename):
        if candidate.is_file():
            return candidate
    return None


def _receipt_from_incoming(incoming, target, url):
    shutil.copy2(incoming, target)
    record = {"url": url, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "bytes": target.stat().st_size,
              "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "provided_in": str(incoming)}
    target.with_suffix(target.suffix + ".source.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def _member_rows(archive_path, suffix):
    with zipfile.ZipFile(archive_path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(suffix))
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "source.xlsx"
            workbook.write_bytes(archive.read(member))
            yield from iter_oews_xlsx_rows(workbook)


def _needed(row, *, area=None, naics="000000", ownership=None):
    return ((area is None or row["area_code"] == area) and row["naics"] == naics
            and (ownership is None or row["own_code"] == ownership)
            and row["occ_code"] in SELECTED | {"00-0000"})


def _county_cbsa(path):
    weights = defaultdict(lambda: defaultdict(float))
    names = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            code = str(row.get("CBSA", "")).strip()
            if not code or code.lower() == "nan":
                continue
            fips = str(row.get("STATEFP", "")).strip().zfill(2) + str(row.get("COUNTYFP", "")).strip().zfill(3)
            try:
                population = float(str(row.get("TotPop", "0")).replace(",", ""))
            except ValueError:
                population = 0.0
            weights[fips][code] += max(population, 0.0)
            names[code] = str(row.get("CBSA_Name", "")).strip()
    return {fips: max(choices, key=choices.get) for fips, choices in weights.items()}, names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    fetch = curl_fetch if args.transport == "curl" else None
    raw_dir = ROOT / "data/raw/current"; raw_dir.mkdir(parents=True, exist_ok=True)
    receipts = {}
    for key, (filename, url) in SOURCES.items():
        provided, target = _provided_source(ROOT, filename), raw_dir / filename
        receipts[key] = _receipt_from_incoming(provided, target, url) if provided and not target.exists() else download(url, target, fetch=fetch)
    target = ROOT / "data/interim/current"; target.mkdir(parents=True, exist_ok=True)

    national_rows = []
    national_export = target / "oews-national.csv"
    fields = ["area_code", "area_title", "area_type", "prim_state", "naics", "naics_title", "industry_group", "own_code", "occ_code", "occ_title", "occ_group", "employment", "employment_status", "source_vintage"]
    with national_export.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in _member_rows(raw_dir / "oesm25all.zip", "all_data_M_2025.xlsx"):
            if _needed(row, area="99", ownership="1235"):
                national_rows.append(row)
                writer.writerow({field: row.get(field, "") for field in fields[:-1]} | {"source_vintage": "BLS OEWS May 2025"})
                if {item["occ_code"] for item in national_rows} == SELECTED | {"00-0000"}:
                    break
    national = occupation_share(national_rows, SELECTED, naics="000000")

    state_rows = [row for row in _member_rows(raw_dir / "oesm25st.zip", "state_M2025_dl.xlsx") if _needed(row, ownership="1235")]
    state_details = area_trade_share_details(state_rows, SELECTED)
    metro_rows = [row for row in _member_rows(raw_dir / "oesm25ma.zip", "MSA_M2025_dl.xlsx") if _needed(row, ownership="1235")]
    metro_details = area_trade_share_details(metro_rows, SELECTED)
    industry_rows = [row for row in _member_rows(raw_dir / "oesm25in4.zip", "nat3d_M2025_dl.xlsx") if _needed(row, naics="238000")]
    industry = occupation_share(industry_rows, SELECTED, naics="238000")

    for filename, details in (("oews-state-shares.csv", state_details), ("oews-metro-shares.csv", metro_details)):
        with (target / filename).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["area_code", "selected_trade_numerator", "all_occupations_denominator", "selected_trade_share", "suppressed_selected_codes", "missing_selected_codes", "source_vintage"])
            writer.writeheader()
            for area, detail in sorted(details.items()):
                writer.writerow({"area_code": area, "selected_trade_numerator": detail["numerator"], "all_occupations_denominator": detail["denominator"], "selected_trade_share": detail["share"], "suppressed_selected_codes": ";".join(detail["suppressed_selected_codes"]), "missing_selected_codes": ";".join(detail["missing_selected_codes"]), "source_vintage": "BLS OEWS May 2025"})
    (target / "oews-industry-share.json").write_text(json.dumps({"naics": "238000", "selected_trade_numerator": industry["numerator"], "all_occupations_denominator": industry["denominator"], "selected_trade_share": industry["share"], "suppressed_selected_codes": industry["suppressed_selected_codes"], "missing_selected_codes": industry["missing_selected_codes"], "source_vintage": "BLS OEWS May 2025"}, indent=2) + "\n")

    cbsa_path = raw_dir / WALKABILITY
    if not cbsa_path.is_file():
        raise ValueError("OEWS metro adjustment requires the already-pinned EPA SLD CSV")
    county_cbsa, cbsa_names = _county_cbsa(cbsa_path)
    with (target / "oews-county-cbsa.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["fips", "cbsa", "cbsa_name", "source_geography_vintage"]); writer.writeheader()
        for fips, cbsa in sorted(county_cbsa.items()):
            writer.writerow({"fips": fips, "cbsa": cbsa, "cbsa_name": cbsa_names.get(cbsa, ""), "source_geography_vintage": "EPA SLD 2021; published county identifiers documented as 2019"})

    state_shares = {area: detail["share"] for area, detail in state_details.items() if detail["share"] is not None}
    metro_shares = {area: detail["share"] for area, detail in metro_details.items() if detail["share"] is not None}
    cbp_path = target / "cbp-densities.csv"
    cbp_rows = {}
    if cbp_path.exists():
        with cbp_path.open(newline="", encoding="utf-8") as stream:
            cbp_rows = {row["fips"]: row for row in csv.DictReader(stream)}
    trades = calculate_trades(cbp_rows, state_shares, national["share"], metro_shares=metro_shares, county_cbsa=county_cbsa, industry_share=industry["share"])
    with (target / "tradespeople.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["fips", "value", "value_status", "method", "quality_note", "observation_period"]); writer.writeheader()
        for fips, row in sorted(trades.items()):
            writer.writerow({"fips": fips, **row, "observation_period": "BLS OEWS May 2025 / CBP 2023"})

    walk_receipt = json.loads((cbsa_path.with_suffix(cbsa_path.suffix + ".source.json")).read_text())
    audit = {"sources": receipts, "walkability_parent": walk_receipt, "national": national, "industry_naics_238": industry,
             "national_cohort_rows": len(national_rows),
             "state_share_count": len(state_shares), "metro_share_count": len(metro_shares), "county_cbsa_count": len(county_cbsa),
             "tradespeople_counties": len(trades), "trade_status_counts": {status: sum(1 for row in trades.values() if row["value_status"] == status) for status in {row["value_status"] for row in trades.values()}}}
    (target / "oews-audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    config_path = target / "config.json"
    if config_path.exists() and trades:
        config = json.loads(config_path.read_text())
        config["factors"] = [factor for factor in config.get("factors", []) if factor != "tradespeople"] + ["tradespeople"]
        config.setdefault("adapters", {})["tradespeople"] = {"sources": ["tradespeople"]}
        config["sources"] = [source for source in config.get("sources", []) if source.get("id") != "tradespeople"]
        cbp_receipts = {filename: json.loads((raw_dir / filename).with_suffix((raw_dir / filename).suffix + ".source.json").read_text()) for filename in CBP_PARENTS}
        parents = {**{key: value["sha256"] for key, value in receipts.items()}, "walkability": walk_receipt["sha256"], **{filename: value["sha256"] for filename, value in cbp_receipts.items()}}
        urls = {**{key: value["url"] for key, value in receipts.items()}, "walkability": walk_receipt["url"], **{filename: value["url"] for filename, value in cbp_receipts.items()}}
        config["sources"].append({"id": "tradespeople", "path": "tradespeople.csv", "sha256": sha256(target / "tradespeople.csv"), "url": SOURCES["all"][1], "vintage": "BLS OEWS May 2025 / CBP 2023", "geography_vintage": "2019", "role": "source_export", "license": "BLS, Census, and EPA public data", "method": "CBP NAICS 238 density × BLS NAICS 238 selected occupation share × bounded BLS metro/state occupation mix; EPA SLD county-CBSA mapping", "raw_parent_sha256": parents, "raw_parent_urls": urls})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
