"""Download and prepare NOAA heat/cold normals for the current county universe.

The resulting CSV is a source-derived export keyed to 2020 Census population
centres and can be used offline after the immutable downloads are cached.
"""

import argparse
import csv
import json
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.io import sha256
from live_here.factors.temperature import blend_counties, parse_noaa_tar

ROOT = Path(__file__).resolve().parents[1]
NOAA_URL = "https://www.ncei.noaa.gov/data/normals-daily/2006-2020/archive/us-climate-normals_2006-2020_v1.0.1_daily_temperature_by-variable_c20230403.tar.gz"
CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"
NOAA_FILE = "us-climate-normals_2006-2020_daily_temperature.tar.gz"
CENTER_FILE = "CenPop2020_Mean_CO.txt"


def _centers(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
    rows = csv.DictReader(text.splitlines(), dialect=dialect)
    output = []
    for row in rows:
        state = str(row.get("STATEFP", "")).strip().zfill(2)
        county = str(row.get("COUNTYFP", "")).strip().zfill(3)
        try:
            lat = float(row.get("LATITUDE", ""))
            lon = float(row.get("LONGITUDE", ""))
        except (TypeError, ValueError):
            continue
        if len(state) == 2 and len(county) == 3:
            output.append({"fips": state + county, "latitude": lat, "longitude": lon})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    raw_dir = ROOT / "data/raw/current"
    fetch = curl_fetch if args.transport == "curl" else None
    receipts = {
        "noaa": download(NOAA_URL, raw_dir / NOAA_FILE, fetch=fetch),
        "centers": download(CENTER_URL, raw_dir / CENTER_FILE, fetch=fetch),
    }
    if args.download_only:
        print(json.dumps(receipts, indent=2))
        return
    stations, audit = parse_noaa_tar(raw_dir / NOAA_FILE)
    values = blend_counties(stations, _centers(raw_dir / CENTER_FILE))
    target = ROOT / "data/interim/current"
    target.mkdir(parents=True, exist_ok=True)
    with (target / "temperature.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["fips", "hot_days", "cold_days", "value_status", "method", "stations_used", "max_distance_km", "source_vintage"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fips, row in sorted(values.items()):
            writer.writerow({"fips": fips, **{field: row.get(field, "") for field in fields[1:-1]}, "source_vintage": "NOAA 2006-2020 normals"})
    audit.update({"county_rows": len(_centers(raw_dir / CENTER_FILE)), "counties_with_temperature_metrics": len(values),
                  "raw_sources": receipts, "method": "station expected TMAX days; local equirectangular IDW inverse-square interpolation within 125 km"})
    (target / "temperature-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    config_path = target / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        config["factors"] = [f for f in config.get("factors", []) if f not in {"heat", "cold"}] + ["heat", "cold"]
        config.setdefault("adapters", {}).update({"heat": {"sources": ["temperature"], "field": "hot_days"},
                                                    "cold": {"sources": ["temperature"], "field": "cold_days"}})
        config["sources"] = [s for s in config.get("sources", []) if s.get("id") != "temperature"]
        config["sources"].append({"id": "temperature", "path": "temperature.csv", "sha256": sha256(target / "temperature.csv"),
                                   "url": NOAA_URL, "vintage": "2006-2020", "geography_vintage": "2019", "role": "source_export",
                                   "license": "NOAA and Census public data", "method": "NOAA expected TMAX threshold days; Census population-centre IDW interpolation",
                                   "raw_parent_sha256": {"noaa": receipts["noaa"]["sha256"], "centers": receipts["centers"]["sha256"]},
                                   "raw_parent_urls": {"noaa": receipts["noaa"]["url"], "centers": receipts["centers"]["url"]}})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
