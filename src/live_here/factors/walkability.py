"""Aggregate a CSV export of EPA NWI block groups using actual population weights."""

from collections import defaultdict

from ..io import csv_rows, fips, number


def calculate(paths, counties):
    totals = defaultdict(lambda: [0.0, 0.0, 0, 0])
    seen = set()
    outside = set()
    for path in paths:
        for row in csv_rows(path, ["STATEFP", "COUNTYFP", "TotPop", "NatWalkInd"]):
            code = fips(fips(row["STATEFP"], 2) + fips(row["COUNTYFP"], 3))
            geoid = fips(row.get("GEOID", row.get("GEOID10", "")), 12)
            if not geoid.startswith(code):
                raise ValueError(f"Block group and county disagree: {geoid}/{code}")
            if geoid in seen:
                raise ValueError(f"Duplicate block group {geoid}")
            seen.add(geoid)
            if code not in counties:
                outside.add(code)
                continue
            population = number(row["TotPop"], "TotPop", 0)
            total = totals[code]
            total[3] += 1
            if not row["NatWalkInd"].strip():
                total[2] += 1
                continue
            score = number(row["NatWalkInd"], "NatWalkInd", 1, 20)
            total[0] += population * score
            total[1] += population
    result = {}
    for code, (weighted, population, missing, count) in totals.items():
        if population:
            result[code] = {
                "value": weighted / population, "value_status": "derived",
                "observation_period": "source_manifest",
                "method": "sum(NatWalkInd * TotPop) / sum(TotPop) over valid block groups",
                "quality_note": f"weighted_population={population:g}; block_groups={count}; missing_score_groups={missing}",
            }
    return result, {"outside_universe_fips": sorted(outside),
                    "zero_valid_population_counties": sum(v[1] == 0 for v in totals.values())}
