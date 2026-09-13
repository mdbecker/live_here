"""Download the latest advertised Census County Business Patterns county file."""

import argparse
import csv
import json
import zipfile
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.cbp import calculate_rows_with_population

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip"
POP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    receipt = download(URL, ROOT / "data/raw/current/cbp23co.zip",
                       fetch=curl_fetch if args.transport == "curl" else None)
    pop_receipt = download(POP_URL, ROOT / "data/raw/current/co-est2023-alldata.csv",
                           fetch=curl_fetch if args.transport == "curl" else None)
    raw = ROOT / "data/raw/current/cbp23co.zip"
    target = ROOT / "data/interim/current/cbp-source.csv"
    rows = []
    with zipfile.ZipFile(raw) as archive, archive.open("cbp23co.txt") as stream:
        reader = csv.DictReader((line.decode("latin-1") for line in stream))
        for row in reader:
            rows.append({"fips": row["fipstate"] + row["fipscty"], "NAICS": row["naics"],
                         "EMP": row.get("emp", ""), "ESTAB": row.get("est", "")})
    populations = {}
    with (ROOT / "data/raw/current/co-est2023-alldata.csv").open(newline="", encoding="latin-1") as stream:
        for row in csv.DictReader(stream):
            if row.get("SUMLEV") == "050" and row.get("POPESTIMATE2023"):
                populations[row["STATE"] + row["COUNTY"]] = row["POPESTIMATE2023"]
    target = ROOT / "data/interim/current/cbp-source.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["fips", "NAICS", "EMP", "ESTAB", "POP", "source_vintage"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "POP": populations.get(row["fips"], ""), "source_vintage": "CBP 2023 / Census PEP 2023"})
    values, audit = calculate_rows_with_population(rows, populations, population_vintage="2023")
    normalized = ROOT / "data/interim/current/cbp-densities.csv"
    with normalized.open("w", newline="", encoding="utf-8") as output:
        fields = ["fips", "grocery_establishments_per_10k", "trade_employment_per_1k", "population_vintage", "source_vintage"]
        writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
        for fips, value in sorted(values.items()):
            writer.writerow({"fips": fips, **value, "population_vintage": "2023", "source_vintage": "CBP 2023 / Census PEP 2023"})
    print(json.dumps({"cbp": receipt, "population": pop_receipt, "audit": audit}, indent=2))


if __name__ == "__main__":
    main()
