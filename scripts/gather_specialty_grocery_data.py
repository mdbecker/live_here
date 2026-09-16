"""Register and validate the archived specialty-grocery workbook."""

import json
import os
from pathlib import Path

from live_here.factors.specialty_grocery import calculate
from live_here.io import load_counties, sha256


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/sources/specialty_grocery_density_1020_city_restricted_statewide_expansion.xlsx"


def main():
    if not SOURCE.is_file():
        raise ValueError(f"Missing archived specialty grocery source: {SOURCE}")
    target = ROOT / "data/interim/current"
    config_path = target / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    counties = load_counties(target / "counties.csv")
    _, audit = calculate([SOURCE], counties)
    (target / "specialty-grocery-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )

    factor = "specialty_groceries"
    config["factors"] = [item for item in config.get("factors", []) if item != factor] + [factor]
    config.setdefault("adapters", {})[factor] = {"sources": [factor]}
    config["sources"] = [item for item in config.get("sources", []) if item.get("id") != factor]
    config["sources"].append({
        "id": factor,
        "path": os.path.relpath(SOURCE, target),
        "sha256": sha256(SOURCE),
        "url": "project://data/sources/specialty_grocery_density_1020_city_restricted_statewide_expansion.xlsx",
        "vintage": "as provided in archived workbook",
        "geography_vintage": "2019",
        "role": "source_export",
        "license": "Project-supplied recovery/proxy dataset; see archived workbook guide",
        "method": "County Density Ranking / Proxy / Lower-Bound Stores; FIPS-first county join with guarded name fallback; absent counties set to zero",
    })
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(SOURCE), "audit": audit}, indent=2))


if __name__ == "__main__":
    main()
