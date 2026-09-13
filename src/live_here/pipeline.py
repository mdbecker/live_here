"""Reproducible local-file pipeline with explicit missingness and source lineage."""

import json
import platform
from collections import Counter
from pathlib import Path

from . import __version__
from .catalog import FACTORS
from .factors import aqi, snowfall, temperature, transit, walkability
from .io import load_counties, sha256, write_csv
from .ranking import average_ranks, runoff

SUPPORTED = {"aqi", "walkability", "heat", "cold", "snowfall", "transit", "drought", "tradespeople", "groceries", "housing", "hazard_burden", "resilience"}


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
    if config.get("missing_policy") not in {"complete_case", "error"}:
        raise ValueError("missing_policy must be complete_case or error")
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
        if local_path.suffix.lower() not in {".csv", ".zip"}:
            raise ValueError("Source files must be CSV or single-CSV ZIP")
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
                row["observation_period"] = inputs[0]["vintage"]
        elif factor == "snowfall":
            if len(inputs) != 1:
                raise ValueError("Snowfall requires one normalized county export")
            result, audit = snowfall.calculate(paths, counties)
            for row in result.values():
                row["observation_period"] = inputs[0]["vintage"]
        elif factor == "transit":
            if len(inputs) != 1:
                raise ValueError("Transit requires one normalized county export")
            result, audit = _normalized_factor(paths[0], counties)
            for row in result.values():
                row["observation_period"] = inputs[0]["vintage"]
        elif factor in {"drought", "tradespeople", "groceries", "housing", "hazard_burden", "resilience"}:
            if len(inputs) != 1:
                raise ValueError(f"{factor} requires one normalized county export")
            result, audit = _normalized_factor(paths[0], counties)
            for row in result.values():
                row["observation_period"] = inputs[0]["vintage"]
        else:
            if len(inputs) != 1:
                raise ValueError("Walkability requires one consistent block-group export")
            result, audit = walkability.calculate(paths, counties)
            for row in result.values():
                row["observation_period"] = inputs[0]["vintage"]
        results[factor], audits[factor] = result, audit

    eligible = [code for code in counties if all(code in results[f] for f in factors)]
    excluded = [code for code in counties if code not in eligible]
    if excluded and config["missing_policy"] == "error":
        raise ValueError(f"{len(excluded)} counties lack selected factors; no outputs written")
    factor_rows = []
    for code in counties:
        for factor in factors:
            observation = results[factor].get(code, {
                "value": None, "value_status": "missing", "observation_period": "",
                "method": "not_imputed", "quality_note": "No usable matched source observation",
            })
            factor_rows.append({"fips": code, "factor": factor, **observation,
                                "unit": FACTORS[factor].unit,
                                "source_ids": ";".join(lineage[factor]),
                                "geography_vintage": vintage})
    rankings = []
    if eligible:
        columns = [average_ranks([results[f][code]["value"] for code in eligible],
                                 FACTORS[f].higher_is_better) for f in factors]
        matrix = [list(row) for row in zip(*columns)]
        wins, elimination = runoff(matrix, config["iterations"], config["seed"])
        averages = [sum(r) / len(r) for r in matrix]
        avg_based = average_ranks(averages)
        order = sorted(range(len(eligible)), key=lambda i: (
            -elimination[i], -wins[i], averages[i], eligible[i]))
        for position, i in enumerate(order, 1):
            code = eligible[i]
            rankings.append({"runoff_rank": position, "fips": code,
                             "name": counties[code]["name"], "state": counties[code]["state"],
                             "average_factor_rank": averages[i], "average_based_rank": avg_based[i],
                             "mean_elimination_round": elimination[i], "wins": wins[i],
                             "win_rate": wins[i] / config["iterations"],
                             **{f"{f}_rank": matrix[i][j] for j, f in enumerate(factors)}})
    else:
        # Validate run settings even when no county has complete observations.
        runoff([[1]], config["iterations"], config["seed"])
    coverage = {
        "mode": config["mode"], "production_ready": False, "geography_vintage": vintage,
        "universe_count": len(counties), "ranked_count": len(eligible),
        "excluded_fips": excluded, "selected_factors": factors,
        "omitted_v1_factors": [f for f in FACTORS if f not in factors],
        "missing_policy": config["missing_policy"],
        "per_factor": {f: dict(Counter(r["value_status"] for r in factor_rows if r["factor"] == f)) for f in factors},
        "adapter_audits": audits,
        "interpretation": "Ranks compare complete cases only. Missingness can bias the ranked subset. Win rates describe tournaments, not measurement confidence.",
    }
    output = Path(output_path)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output directory must be new or empty; previous runs are preserved")
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "counties.csv", [{k: r[k] for k in ("fips", "name", "state", "geography_vintage")} for r in counties.values()],
              ["fips", "name", "state", "geography_vintage"])
    write_csv(output / "factors.csv", factor_rows, list(factor_rows[0]))
    rank_fields = ["runoff_rank", "fips", "name", "state", "average_factor_rank", "average_based_rank",
                   "mean_elimination_round", "wins", "win_rate", *[f"{f}_rank" for f in factors]]
    write_csv(output / "rankings.csv", rankings, rank_fields)
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
