"""Download and prepare FEMA National Risk Index v1.20 county composites."""

import argparse
import csv
import json
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from live_here.acquire import curl_fetch
from live_here.factors.fema import calculate_factors, read_nri_zip
from live_here.io import sha256

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0/query"
RELEASE = "FEMA NRI v1.20 (December 2025)"
ALL_HAZARD_PREFIXES = [
    "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN", "ISTM",
    "IFLD", "LNDS", "LTNG", "SWND", "TRND", "TSUN", "VLCN", "WFIR", "WNTW",
]
FIELDS = [
    "STCOFIPS", "COUNTY", "COUNTYTYPE", "STATEABBRV", "POPULATION", "EAL_SCORE",
    "ALR_VRA_NPCTL", "ALR_NPCTL", "SOVI_SCORE", "RESL_SCORE",
    "CFLD_RISKS", "CWAV_RISKS", "DRGT_RISKS", "HWAV_RISKS", "HRCN_RISKS",
    "IFLD_RISKS", "SWND_RISKS", "WFIR_RISKS", "WNTW_RISKS",
]
FIELDS += [f"{p}_{suffix}" for p in ALL_HAZARD_PREFIXES for suffix in ("AFREQ", "EVNTS")]


def query(params, transport="python"):
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    if transport == "curl":
        payload = curl_fetch(url)
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "LiveHereResearch/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    result = json.loads(payload)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def download_counties(path: Path, transport="python"):
    base = {"where": "1=1", "returnGeometry": "false", "f": "json"}
    ids = query({**base, "returnIdsOnly": "true"}, transport)
    object_ids = ids.get("objectIds", [])
    if not object_ids:
        raise RuntimeError("FEMA NRI query returned no county object IDs")
    features = []
    # Use short OBJECTID ranges so the system curl transport does not exceed URL
    # limits; the service may have gaps, which are harmless.
    max_id = max(object_ids)
    for start in range(1, max_id + 1, 500):
        result = query({"where": f"OBJECTID >= {start} AND OBJECTID < {start + 500}", "returnGeometry": "false", "f": "json", "outFields": ",".join(FIELDS)}, transport)
        features.extend(result.get("features", []))
    fields = ["STCOFIPS", "COUNTY", "COUNTYTYPE", "STATEABBRV", "POPULATION", "EAL_SCORE", "ALR_VRA_NPCTL", "ALR_NPCTL", "SOVI_SCORE", "RESL_SCORE"]
    fields += [f"{p}_RISKS" for p in ("CFLD", "CWAV", "DRGT", "HWAV", "HRCN", "IFLD", "SWND", "WFIR", "WNTW")]
    fields += [f"{p}_{suffix}" for p in ALL_HAZARD_PREFIXES for suffix in ("AFREQ", "EVNTS")]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for feature in features:
            attrs = feature.get("attributes", {})
            writer.writerow({field: attrs.get(field, "") for field in fields})
    receipt = {"url": ENDPOINT, "query": {"release": RELEASE, "fields": fields}, "sha256": sha256(path), "bytes": path.stat().st_size, "retrieved_at": datetime.now(timezone.utc).isoformat(), "records": len(features)}
    path.with_suffix(path.suffix + ".source.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def write_export(path, rows):
    fields = ["fips", "value", "value_status", "method", "quality_note", "observation_period"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fips in sorted(rows):
            writer.writerow({"fips": fips, **rows[fips]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    raw = ROOT / "data/raw/current/fema-nri-counties.csv"
    receipt_path = raw.with_suffix(raw.suffix + ".source.json")
    if raw.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("url") != ENDPOINT or receipt.get("sha256") != sha256(raw):
            raise ValueError("Cached FEMA source URL/checksum mismatch")
    else:
        receipt = download_counties(raw, args.transport)
    rows, audit = read_nri_zip(raw)
    burden, resilience, factor_audit = calculate_factors(rows)
    target = ROOT / "data/interim/current"
    target.mkdir(parents=True, exist_ok=True)
    write_export(target / "fema-hazard-burden.csv", burden)
    write_export(target / "fema-resilience.csv", resilience)
    audit.update(factor_audit, release=RELEASE, raw_source=receipt)
    (target / "fema-audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    config_path = target / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        for factor in ("hazard_burden", "resilience"):
            if factor not in config["factors"]:
                config["factors"].append(factor)
            config.setdefault("adapters", {})[factor] = {"sources": [factor]}
            config["sources"] = [s for s in config.get("sources", []) if s.get("id") != factor]
            export = target / ("fema-hazard-burden.csv" if factor == "hazard_burden" else "fema-resilience.csv")
            config["sources"].append({"id": factor, "path": export.name, "sha256": sha256(export), "url": ENDPOINT, "vintage": RELEASE, "geography_vintage": "2019", "role": "source_export", "license": "FEMA public data", "method": "Source-only FEMA NRI v1.20 composite; no legacy workbook mapping", "raw_parent_sha256": {"fema_nri": receipt["sha256"]}, "raw_parent_urls": {"fema_nri": ENDPOINT}})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
