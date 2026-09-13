"""Download and prepare a source-only USDM D1+ drought-frequency factor."""

import argparse
import json
import urllib.parse
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.drought import read_drought_csv
from live_here.io import sha256


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://usdmdataservices.unl.edu/api/ConsecutiveNonConsecutiveStatistics/GetNonConsecutiveStatisticsCounty"


def source_url(start_date, end_date, minimum_weeks):
    return ENDPOINT + "?" + urllib.parse.urlencode({
        "aoi": "", "dx": "1", "minimumweeks": str(minimum_weeks),
        "startdate": start_date, "enddate": end_date,
    })


def write_export(path, rows):
    import csv
    fields = ["fips", "value", "value_status", "method", "quality_note", "observation_period"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fips in sorted(rows):
            writer.writerow({field: rows[fips].get(field, "") for field in fields} | {"fips": fips})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    parser.add_argument("--start-date", default="1/1/2016")
    parser.add_argument("--end-date", default="1/1/2026")
    parser.add_argument("--minimum-weeks", type=int, default=0)
    args = parser.parse_args()
    if args.minimum_weeks < 0:
        raise ValueError("minimum weeks cannot be negative")
    url = source_url(args.start_date, args.end_date, args.minimum_weeks)
    raw = ROOT / "data/raw/current" / "usdm-d1-plus-county-weeks.csv"
    receipt = download(url, raw, fetch=curl_fetch if args.transport == "curl" else None)
    start_year = int(args.start_date.rsplit("/", 1)[-1])
    end_year = int(args.end_date.rsplit("/", 1)[-1])
    years = float(end_year - start_year)
    if years <= 0:
        raise ValueError("end date must be after start date and span at least one year")
    period = f"{start_year}-01-01 through {end_year}-01-01; D1; non-consecutive weeks"
    rows, audit = read_drought_csv(raw, window_years=years, observation_period=period)
    target = ROOT / "data/interim/current"
    target.mkdir(parents=True, exist_ok=True)
    export = target / "drought.csv"
    write_export(export, rows)
    audit.update({"raw_source": receipt, "url": url, "start_date": args.start_date,
                  "end_date": args.end_date, "minimum_weeks": args.minimum_weeks,
                  "method": "Observed USDM D1+ non-consecutive weeks × 7 / declared complete-window years; no old estimate calibration"})
    (target / "drought-audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    config_path = target / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        config["factors"] = [f for f in config.get("factors", []) if f != "drought"] + ["drought"]
        config.setdefault("adapters", {})["drought"] = {"sources": ["drought"]}
        config["sources"] = [s for s in config.get("sources", []) if s.get("id") != "drought"]
        config["sources"].append({
            "id": "drought", "path": export.name, "sha256": sha256(export), "url": url,
            "vintage": period, "geography_vintage": "2019", "role": "source_export",
            "license": "U.S. Drought Monitor public data",
            "method": "Observed D1+ non-consecutive weeks × 7 / declared complete-window years; no old estimate calibration",
            "raw_parent_sha256": {"usdm": receipt["sha256"]}, "raw_parent_urls": {"usdm": url},
        })
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
