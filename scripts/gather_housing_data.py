"""Download and prepare the current Zillow county three-bedroom ZHVI series."""

import argparse
import csv
import json
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.housing import METHOD, calculate, read_zillow_county_csv
from live_here.io import sha256

ROOT = Path(__file__).resolve().parents[1]
URL = "https://files.zillowstatic.com/research/public_csvs/zhvi/County_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
FILENAME = "County_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"


def write_export(path, rows):
    fields = ["fips", "value", "value_status", "method", "quality_note", "observation_period"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fips in sorted(rows):
            writer.writerow({"fips": fips, **{field: rows[fips].get(field, "") for field in fields if field != "fips"}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    parser.add_argument("--observation-month", help="Explicit YYYY-MM-DD month; defaults to the latest CSV column")
    args = parser.parse_args()

    raw = ROOT / "data/raw/current" / FILENAME
    receipt = download(URL, raw, fetch=curl_fetch if args.transport == "curl" else None)
    parsed, month, audit = read_zillow_county_csv(raw, args.observation_month)
    values, factor_audit = calculate(parsed, month)
    target = ROOT / "data/interim/current"
    target.mkdir(parents=True, exist_ok=True)
    export = target / "housing.csv"
    write_export(export, values)
    audit.update(factor_audit, raw_source=receipt, release="Zillow Research ZHVI", url=URL)
    (target / "housing-audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    config_path = target / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        config["factors"] = [factor for factor in config.get("factors", []) if factor != "housing"] + ["housing"]
        config.setdefault("adapters", {})["housing"] = {"sources": ["housing"]}
        config["sources"] = [source for source in config.get("sources", []) if source.get("id") != "housing"]
        config["sources"].append({"id": "housing", "path": export.name, "sha256": sha256(export),
                                   "url": URL, "vintage": month, "geography_vintage": "2019",
                                   "role": "source_export", "license": "Zillow Research public data",
                                   "method": METHOD, "raw_parent_sha256": {"zillow_zhvi": receipt["sha256"]},
                                   "raw_parent_urls": {"zillow_zhvi": URL}})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
