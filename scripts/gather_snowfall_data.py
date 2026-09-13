"""Download and prepare NOAA annual snowfall normals."""

import argparse
import csv
import json
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.snowfall import blend_counties, parse_noaa_multivariate_tar
from live_here.io import sha256
from gather_temperature_data import CENTER_FILE, _centers

ROOT = Path(__file__).resolve().parents[1]
NOAA_URL = "https://www.ncei.noaa.gov/data/normals-annualseasonal/2006-2020/archive/us-climate-normals_2006-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz"
NOAA_FILE = "us-climate-normals_2006-2020_annualseasonal_multivariate.tar.gz"
CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    raw_dir = ROOT / "data/raw/current"
    fetch = curl_fetch if args.transport == "curl" else None
    receipts = {"noaa": download(NOAA_URL, raw_dir / NOAA_FILE, fetch=fetch)}
    center_path = raw_dir / CENTER_FILE
    if not center_path.exists():
        receipts["centers"] = download(CENTER_URL, center_path, fetch=fetch)
    else:
        receipts["centers"] = json.loads(center_path.with_suffix(center_path.suffix + ".source.json").read_text())
    if args.download_only:
        print(json.dumps(receipts, indent=2)); return
    stations, audit = parse_noaa_multivariate_tar(raw_dir / NOAA_FILE)
    centers = _centers(center_path)
    values = blend_counties(stations, centers)
    target = ROOT / "data/interim/current"; target.mkdir(parents=True, exist_ok=True)
    fields = ["fips", "snowfall_feet", "value_status", "method", "stations_used", "max_distance_km", "source_vintage"]
    with (target / "snowfall.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for fips, row in sorted(values.items()):
            writer.writerow({"fips": fips, **{field: row.get(field, "") for field in fields[1:-1]}, "source_vintage": "NOAA 2006-2020 normals"})
    audit.update({"county_rows": len(centers), "counties_with_snowfall": len(values), "raw_sources": receipts,
                  "method": "NOAA annual snow normal in inches converted to feet; IDW inverse-square within 175 km"})
    (target / "snowfall-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    config_path = target / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        config["factors"] = [f for f in config.get("factors", []) if f != "snowfall"] + ["snowfall"]
        config.setdefault("adapters", {})["snowfall"] = {"sources": ["snowfall"]}
        config["sources"] = [s for s in config.get("sources", []) if s.get("id") != "snowfall"]
        config["sources"].append({"id": "snowfall", "path": "snowfall.csv", "sha256": sha256(target / "snowfall.csv"),
                                   "url": NOAA_URL, "vintage": "2006-2020", "geography_vintage": "2019", "role": "source_export",
                                   "license": "NOAA and Census public data", "method": "NOAA annual snowfall normal converted to feet; Census population-centre IDW interpolation",
                                   "raw_parent_sha256": {"noaa": receipts["noaa"]["sha256"], "centers": receipts["centers"]["sha256"]},
                                   "raw_parent_urls": {"noaa": receipts["noaa"]["url"], "centers": receipts["centers"]["url"]}})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
