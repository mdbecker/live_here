"""Download and prepare the USDA ERS Food Environment Atlas grocery adjustment."""

import argparse
import csv
import json
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.usda import calculate_grocery, read_atlas_zip
from live_here.io import sha256

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.ers.usda.gov/media/5570/food-environment-atlas-csv-files.zip?v=18315"
FILENAME = "food-environment-atlas-csv-files.zip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    raw = ROOT / "data/raw/current" / FILENAME
    receipt = download(URL, raw, fetch=curl_fetch if args.transport == "curl" else None)
    atlas = read_atlas_zip(raw)
    cbp_path = ROOT / "data/interim/current/cbp-densities.csv"
    cbp = {}
    with cbp_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            cbp[row["fips"]] = row
    values, audit = calculate_grocery(cbp, atlas)
    target = ROOT / "data/interim/current"; target.mkdir(parents=True, exist_ok=True)
    with (target / "grocery.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["fips", "value", "value_status", "method", "quality_note", "observation_period"]
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for fips, row in sorted(values.items()):
            writer.writerow({"fips": fips, **row, "observation_period": "USDA access indicators 2019; CBP business and population 2023"})
    audit.update({
        "raw_source": receipt,
        "cbp_raw_parent": json.loads((ROOT / "data/raw/current/cbp23co.zip.source.json").read_text()),
        "population_raw_parent": json.loads((ROOT / "data/raw/current/co-est2023-alldata.csv.source.json").read_text()),
        "atlas_counties": len(atlas),
        "method": "CBP grocery density times bounded USDA low-access multiplier",
        "base_observation_period": "2023",
        "output_observation_period": "USDA access indicators 2019; CBP business and population 2023",
    })
    (target / "usda-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    config_path = target / "config.json"
    if config_path.exists() and values:
        config = json.loads(config_path.read_text())
        cbp_parent = json.loads((ROOT / "data/raw/current/cbp23co.zip.source.json").read_text())
        population_parent = json.loads((ROOT / "data/raw/current/co-est2023-alldata.csv.source.json").read_text())
        config["factors"] = [f for f in config.get("factors", []) if f != "groceries"] + ["groceries"]
        config.setdefault("adapters", {})["groceries"] = {"sources": ["groceries"]}
        config["sources"] = [s for s in config.get("sources", []) if s.get("id") != "groceries"]
        config["sources"].append({"id": "groceries", "path": "grocery.csv", "sha256": sha256(target / "grocery.csv"),
                                   "url": URL, "vintage": "USDA FEA 2025 release; access indicators 2019 / CBP 2023", "geography_vintage": "2019",
                                   "role": "source_export", "license": "USDA ERS and Census public data",
                                   "method": "CBP grocery density times bounded USDA low-access multiplier",
                                   "raw_parent_sha256": {"usda": receipt["sha256"], "cbp23co.zip": cbp_parent["sha256"], "co-est2023-alldata.csv": population_parent["sha256"]},
                                   "raw_parent_urls": {"usda": URL, "cbp23co.zip": cbp_parent["url"], "co-est2023-alldata.csv": population_parent["url"]}})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
