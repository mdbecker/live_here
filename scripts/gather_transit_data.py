"""Download and prepare EPA Access to Jobs and Workers via Transit data."""

import argparse
import csv
import json
from pathlib import Path

from live_here.acquire import curl_fetch, download
from live_here.factors.transit import EPA_TRANSIT_URL, SOURCE_VINTAGE, build_transit_rollup
from live_here.io import sha256

ROOT = Path(__file__).resolve().parents[1]
FILENAME = "SLD_Trans45_DBF.zip"


def write_export(path, values):
    fields = ["fips", "value", "value_status", "method", "quality_note", "observation_period"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fips in sorted(values):
            writer.writerow({"fips": fips, **values[fips]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["python", "curl"], default="python")
    args = parser.parse_args()
    raw = ROOT / "data/raw/current" / FILENAME
    receipt = download(EPA_TRANSIT_URL, raw, fetch=curl_fetch if args.transport == "curl" else None)
    rollup, audit = build_transit_rollup(raw)
    target = ROOT / "data/interim/current"
    target.mkdir(parents=True, exist_ok=True)
    values = {}
    for fips, row in rollup.items():
        if row["transit_score"] is not None:
            values[fips] = {"value": row["transit_score"], "value_status": "derived_source",
                            "method": "100 * (0.50*TrAccess_Indexi + 0.30*Pct_Jobs_byTr + 0.10*Pct_Pop_byTr + 0.10*Pct_Wrks_byTr)",
                            "quality_note": "EPA coverage is limited to GTFS-served metropolitan regions; no fallback or old estimate used",
                            "observation_period": SOURCE_VINTAGE}
    export = target / "transit.csv"
    write_export(export, values)
    audit.update({"raw_source": receipt, "release": SOURCE_VINTAGE, "export_rows": len(values),
                  "method": "Source-only county means from EPA block-group observations; missing counties remain missing"})
    (target / "transit-audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    config_path = target / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        config["factors"] = [f for f in config.get("factors", []) if f != "transit"] + ["transit"]
        config.setdefault("adapters", {})["transit"] = {"sources": ["transit"]}
        config["sources"] = [s for s in config.get("sources", []) if s.get("id") != "transit"]
        config["sources"].append({"id": "transit", "path": export.name, "sha256": sha256(export),
                                   "url": EPA_TRANSIT_URL, "vintage": SOURCE_VINTAGE,
                                   "geography_vintage": "2019", "role": "source_export",
                                   "source_geography_vintage": "EPA Trans45 2013 block-group observations (GEOID10)",
                                   "geography_harmonization": "Aggregate each source GEOID10 to its first five-digit county FIPS, then join to the 2019 Census county target; no spatial reaggregation is performed",
                                   "license": "EPA public data",
                                   "method": "Source-only county means from EPA block-group observations",
                                   "raw_parent_sha256": {"epa_transit": receipt["sha256"]},
                                   "raw_parent_urls": {"epa_transit": EPA_TRANSIT_URL}})
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
