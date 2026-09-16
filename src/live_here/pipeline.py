"""Reproducible local-file pipeline with explicit missingness and source lineage."""

import json
import math
import platform
from collections import Counter
from pathlib import Path

from . import __version__
from .catalog import FACTORS
from .factors import aqi, snowfall, specialty_grocery, temperature, transit, walkability
from .inference import infer_missing
from .io import load_counties, sha256, write_csv
from .ranking import average_ranks, runoff

SUPPORTED = {"aqi", "walkability", "heat", "cold", "snowfall", "transit", "drought", "tradespeople", "groceries", "specialty_groceries", "housing", "hazard_burden", "resilience"}
FACTOR_FIELDS = ["fips", "factor", "value", "value_status", "is_inferred", "observation_period", "method",
                 "quality_note", "inference_donor_fips", "nearest_donor_km", "farthest_donor_km", "unit",
                 "source_ids", "geography_vintage"]


def _normalized_factor(path, counties):
    from .io import csv_rows
    result = {}; seen = set(); outside_universe = []
    for row in csv_rows(path):
        code = str(row.get("fips", "")).strip()
        if code in seen:
            raise ValueError(f"Duplicate normalized factor county: {code}")
        seen.add(code)
        if code not in counties:
            outside_universe.append(code)
            continue
        try:
            value = float(row.get("value", ""))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        result[code] = {"value": value, "value_status": row.get("value_status", "derived_source"),
                        "observation_period": row.get("observation_period", ""),
                        "method": row.get("method", "normalized_source_export"),
                        "quality_note": row.get("quality_note", "")}
    return result, {"rows_read": len(seen), "matched_counties": len(result),
                    "outside_universe_fips": sorted(outside_universe)}


def read_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    if config.get("mode") not in {"demo", "research"}:
        raise ValueError("V1 production is not implemented. Use explicit demo or research mode.")
    factors = config.get("factors", [])
    if not factors or len(factors) != len(set(factors)):
        raise ValueError("Select at least one factor, without duplicates")
    unsupported = set(factors) - SUPPORTED
    if unsupported:
        raise ValueError(f"Factors awaiting implementation: {sorted(unsupported)}")
    sources = {}
    for entry in config.get("sources", []):
        required = {"id", "path", "sha256", "url", "vintage", "geography_vintage", "role", "license"}
        if required - entry.keys() or any(not isinstance(entry[k], str) or not entry[k].strip() for k in required):
            raise ValueError(f"Source needs nonempty fields {sorted(required)}")
        if entry["id"] in sources:
            raise ValueError(f"Duplicate source id {entry['id']}")
        local_path = (path.parent / entry["path"]).resolve()
        if "legacy" in local_path.parts or "research" in local_path.parts:
            raise ValueError("Historical research artifacts cannot be pipeline inputs")
        if local_path.suffix.lower() not in {".csv", ".zip", ".xlsx"}:
            raise ValueError("Source files must be CSV, single-CSV ZIP, or XLSX")
        if not local_path.is_file():
            raise ValueError(f"Missing source file: {local_path}")
        if sha256(local_path) != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {entry['id']}")
        if config["mode"] != "demo" and entry["role"] == "fixture":
            raise ValueError("Synthetic fixtures are only allowed in demo mode")
        sources[entry["id"]] = {**entry, "resolved_path": local_path}
    if not sources:
        raise ValueError("Source manifest is empty")
    return config, sources


def run(config_path, output_path):
    config, sources = read_config(config_path)
    factors = config["factors"]

    def source(source_id):
        if source_id not in sources:
            raise ValueError(f"Unknown source id: {source_id}")
        return sources[source_id]

    geography = source(config["geography_source"])
    counties = load_counties(geography["resolved_path"])
    vintage = next(iter(counties.values()))["geography_vintage"]
    if geography["geography_vintage"] != vintage:
        raise ValueError("Geography manifest and county file disagree")
    results, audits, lineage = {}, {}, {}
    for factor in factors:
        settings = config["adapters"][factor]
        ids = settings["sources"]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError(f"{factor}: source ids must be nonempty and unique")
        inputs = [source(i) for i in ids]
        if any(s["geography_vintage"] != vintage for s in inputs):
            raise ValueError(f"{factor}: source geography differs; supply a reviewed harmonization first")
        paths = [s["resolved_path"] for s in inputs]
        lineage[factor] = list(ids)
        if factor == "aqi":
            crosswalk = source(settings["crosswalk"])
            if crosswalk["geography_vintage"] != vintage:
                raise ValueError("AQI crosswalk manifest vintage differs")
            lineage[factor].append(settings["crosswalk"])
            result, audit = aqi.calculate(paths, counties, crosswalk["resolved_path"])
        elif factor in {"heat", "cold"}:
            if len(inputs) != 1:
                raise ValueError("Temperature requires one normalized county export")
            result, audit = temperature.calculate(paths, counties, settings.get("field", "hot_days" if factor == "heat" else "cold_days"))
            for row in result.values():
                row["observation_period"] = row.get("observation_period") or inputs[0]["vintage"]
        elif factor == "snowfall":
            if len(inputs) != 1:
                raise ValueError("Snowfall requires one normalized county export")
            result, audit = snowfall.calculate(paths, counties)
            for row in result.values():
                row["observation_period"] = row.get("observation_period") or inputs[0]["vintage"]
        elif factor == "transit":
            if len(inputs) != 1:
                raise ValueError("Transit requires one normalized county export")
            result, audit = _normalized_factor(paths[0], counties)
            for row in result.values():
                row["observation_period"] = row.get("observation_period") or inputs[0]["vintage"]
        elif factor == "specialty_groceries":
            if len(inputs) != 1:
                raise ValueError("Specialty groceries requires one workbook source")
            result, audit = specialty_grocery.calculate(paths, counties)
        elif factor in {"drought", "tradespeople", "groceries", "housing", "hazard_burden", "resilience"}:
            if len(inputs) != 1:
                raise ValueError(f"{factor} requires one normalized county export")
            result, audit = _normalized_factor(paths[0], counties)
            for row in result.values():
                row["observation_period"] = row.get("observation_period") or inputs[0]["vintage"]
        else:
            if len(inputs) != 1:
                raise ValueError("Walkability requires one consistent block-group export")
            result, audit = walkability.calculate(paths, counties)
            for row in result.values():
                row["observation_period"] = row.get("observation_period") or inputs[0]["vintage"]
        results[factor], audits[factor] = result, audit

    factor_records, inferred_by_factor, source_backed_by_factor = {}, {}, {}
    factor_rows = []
    for factor in factors:
        source_observations = results[factor]
        provided_codes = set(source_observations)
        flagged_inferred_codes = {code for code, observation in source_observations.items()
                                  if str(observation.get("is_inferred", "false")).casefold() == "true"}
        inferred_codes = flagged_inferred_codes | (set(counties) - provided_codes)
        source_codes = provided_codes - flagged_inferred_codes
        if set(counties) - provided_codes:
            completed = infer_missing(counties, source_observations)
        else:
            completed = {code: dict(observation) for code, observation in source_observations.items()}
        inferred_by_factor[factor] = inferred_codes
        source_backed_by_factor[factor] = source_codes
        factor_records[factor] = {}
        for code in counties:
            if code not in completed or not math.isfinite(float(completed[code]["value"])):
                raise ValueError(f"{factor}: county {code} remains without a finite value after inference")
            if code in provided_codes:
                observation = dict(completed[code])
                observation.update({"is_inferred": "true" if code in inferred_codes else "false",
                                   "inference_donor_fips": observation.get("inference_donor_fips", ""),
                                   "nearest_donor_km": observation.get("nearest_donor_km", ""),
                                   "farthest_donor_km": observation.get("farthest_donor_km", "")})
            else:
                observation = dict(completed[code])
                periods = sorted({str(completed[donor].get("observation_period", "")).strip()
                                  for donor in observation["inference_donor_fips"].split(";")
                                  if str(completed.get(donor, {}).get("observation_period", "")).strip()})
                observation.update({"value_status": "inferred_geographic_idw", "is_inferred": "true",
                                   "observation_period": ";".join(periods),
                                   "method": "geographic_idw_k5_p2",
                                   "quality_note": "Synthetic geographic estimate from nearest pre-inference factor donors; not a direct/source-derived county observation."})
            source_ids = list(lineage[factor])
            if code not in source_codes and config["geography_source"] not in source_ids:
                source_ids.append(config["geography_source"])
            record = {"fips": code, "factor": factor, **observation,
                      "unit": FACTORS[factor].unit, "source_ids": ";".join(source_ids),
                      "geography_vintage": vintage}
            factor_records[factor][code] = record
            factor_rows.append(record)

    if any(record["value_status"] == "missing" for record in factor_rows):
        raise ValueError("No selected factor may remain missing after inference")

    codes = list(counties)
    columns = [average_ranks([factor_records[f][code]["value"] for code in codes],
                             FACTORS[f].higher_is_better) for f in factors]
    matrix = [list(row) for row in zip(*columns)]
    wins, elimination = runoff(matrix, config["iterations"], config["seed"])
    averages = [sum(r) / len(r) for r in matrix]
    avg_based = average_ranks(averages)
    order = sorted(range(len(codes)), key=lambda i: (-elimination[i], -wins[i], averages[i], codes[i]))
    rankings = []
    for position, i in enumerate(order, 1):
        code = codes[i]
        inferred_factors = ";".join(f for f in factors if code in inferred_by_factor[f])
        rankings.append({"runoff_rank": position, "fips": code,
                         "name": counties[code]["name"], "state": counties[code]["state"],
                         "average_factor_rank": averages[i], "average_based_rank": avg_based[i],
                         "mean_elimination_round": elimination[i], "wins": wins[i],
                         "win_rate": wins[i] / config["iterations"], "inferred_factors": inferred_factors,
                         **{f"{f}_rank": matrix[i][j] for j, f in enumerate(factors)}})
    coverage = {
        "mode": config["mode"], "production_ready": False, "geography_vintage": vintage,
        "universe_count": len(counties), "ranked_count": len(counties), "selected_factors": factors,
        "omitted_v1_factors": [f for f in FACTORS if f not in factors],
        "per_factor": {f: dict(Counter(r["value_status"] for r in factor_rows if r["factor"] == f)) for f in factors},
        "inference": {
            "method": "geographic_idw_k5_p2",
            "coordinate_source": "Census 2020 county mean centers of population",
            "counties_with_inference": len({code for factor in factors for code in inferred_by_factor[factor]}),
            "counties_without_inference": len(counties) - len({code for factor in factors for code in inferred_by_factor[factor]}),
            "county_inference_rate": len({code for factor in factors for code in inferred_by_factor[factor]}) / len(counties),
            "per_factor": {
                factor: {"source_backed_count": len(source_backed_by_factor[factor]),
                         "inferred_count": len(inferred_by_factor[factor]),
                         "inference_rate": len(inferred_by_factor[factor]) / len(counties)}
                for factor in factors
            },
        },
        "adapter_audits": audits,
        "interpretation": "All counties are ranked. Inferred values are deterministic geographic estimates, except specialty-grocery lower-bound zero fills, which are explicit absence-of-source values; neither is a confidence interval. Win rates describe tournaments, not measurement confidence.",
    }
    output = Path(output_path)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output directory must be new or empty; previous runs are preserved")
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "counties.csv", [{k: r[k] for k in ("fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage")} for r in counties.values()],
              ["fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage"])
    write_csv(output / "factors.csv", factor_rows, FACTOR_FIELDS)
    rank_fields = ["runoff_rank", "fips", "name", "state", "average_factor_rank", "average_based_rank",
                   "mean_elimination_round", "wins", "win_rate", *[f"{f}_rank" for f in factors], "inferred_factors"]
    write_csv(output / "rankings.csv", rankings, rank_fields)
    presentation_fields = ["fips", "name", "state", "runoff_rank", "average_factor_rank", "average_based_rank",
                           "mean_elimination_round", "wins", "win_rate"]
    for factor in factors:
        presentation_fields.extend([factor, f"{factor}_rank"])
    presentation_fields.append("inferred_factors")
    presentation_rows = []
    for ranking in rankings:
        code = ranking["fips"]
        inferred = set(ranking["inferred_factors"].split(";")) if ranking["inferred_factors"] else set()
        any_inferred = bool(inferred)
        row = {"fips": code, "name": ranking["name"] + ("*" if any_inferred else ""),
               "state": ranking["state"], "inferred_factors": ranking["inferred_factors"]}
        for field in ("runoff_rank", "average_factor_rank", "average_based_rank", "mean_elimination_round", "wins", "win_rate"):
            value = ranking[field]
            row[field] = f"{value}*" if any_inferred else value
        for factor in factors:
            value = factor_records[factor][code]["value"]
            rank = ranking[f"{factor}_rank"]
            row[factor] = f"{value}*" if factor in inferred else value
            row[f"{factor}_rank"] = f"{rank}*" if factor in inferred else rank
        presentation_rows.append(row)
    write_csv(output / "county_rankings.csv", presentation_rows, presentation_fields)
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
    manifest = {
        "package_version": __version__, "python_version": platform.python_version(),
        "config_sha256": sha256(config_path), "config": config,
        "source_files": [{k: v for k, v in s.items() if k != "resolved_path"} for s in sources.values()],
        "code_sha256": {str(p.relative_to(Path(__file__).parent)): sha256(p)
                        for p in sorted(Path(__file__).parent.rglob("*.py"))},
        "output_sha256": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()},
        "algorithm": "permutation-cycle randomized runoff, Python random.Random; winner round=N; ties random; final ties use FIPS",
    }
    (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return coverage
