"""Gather Census geography, EPA walkability, and the latest complete EPA AQI years.

Run: .venv/bin/python scripts/gather_current_data.py [--download-only]
"""
import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from live_here.acquire import curl_fetch, discover_aqi_releases, download

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "counties": ("2019_Gaz_counties_national.zip", "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2019_Gazetteer/2019_Gaz_counties_national.zip"),
    "centers": ("CenPop2020_Mean_CO.txt", "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"),
    "walkability": ("EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv", "https://edg.epa.gov/data/public/OA/EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv"),
}
AQI_LISTING_URL = "https://aqs.epa.gov/aqsweb/airdata/download_files.html"


def listing_bytes(transport):
    if transport == "curl":
        return curl_fetch(AQI_LISTING_URL)
    request = urllib.request.Request(AQI_LISTING_URL, headers={"User-Agent": "LiveHereResearch/0.1 (public-data research)"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def discover_sources(transport):
    path = ROOT / "data/raw/current/aqi-release-discovery.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        discovery = json.loads(path.read_text())
        releases = discovery["selected_releases"]
    else:
        releases = discover_aqi_releases(listing_bytes(transport))
        discovery = {"url": AQI_LISTING_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(), "selected_releases": releases}
        path.write_text(json.dumps(discovery, indent=2) + "\n")
    return {**SOURCES, **{release["id"]: (release["filename"], release["url"]) for release in releases}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    sources = discover_sources(args.transport)
    receipts = {}
    for ident, (filename, url) in sources.items():
        print(f"Gathering {ident}: {url}", flush=True)
        receipts[ident] = download(url, ROOT / "data/raw/current" / filename,
                                  fetch=curl_fetch if args.transport == "curl" else None)
        print(f"Verified {receipts[ident]['bytes']:,} bytes", flush=True)
    if not args.download_only:
        from live_here.acquire import prepare_current
        result = prepare_current(ROOT, sources, receipts)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
