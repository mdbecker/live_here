"""Census County Business Patterns shared business/population densities."""

from __future__ import annotations

import math
from collections import defaultdict


def _number(value):
    text = str(value or "").strip()
    if not text or text in {"D", "S", "X", "-", "NA", "N"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def calculate_rows(rows):
    grouped = defaultdict(lambda: {"pop": None, "grocery_establishments": None, "trade_employment": None})
    suppressed = 0
    for row in rows:
        fips = str(row.get("fips") or row.get("GEO_ID") or "").strip()
        naics = str(row.get("NAICS") or row.get("NAICS2017") or "").strip()
        if not fips:
            continue
        record = grouped[fips]
        population = _number(row.get("POP") or row.get("population"))
        if population is not None:
            record["pop"] = population
        if naics == "445110":
            value = _number(row.get("ESTAB"))
            if value is None:
                suppressed += 1
            else:
                record["grocery_establishments"] = value
        elif naics.startswith("238"):
            value = _number(row.get("EMP"))
            if value is None:
                suppressed += 1
            else:
                record["trade_employment"] = value
    result = {}
    for fips, record in grouped.items():
        pop = record["pop"]
        if pop is None or pop <= 0:
            continue
        grocery = record["grocery_establishments"]
        trade = record["trade_employment"]
        output = {}
        if grocery is not None:
            output["grocery_establishments_per_10k"] = grocery / pop * 10000
        if trade is not None:
            output["trade_employment_per_1k"] = trade / pop * 1000
        if output:
            result[fips] = output
    return result, {"suppressed_or_missing_rows": suppressed, "matched_counties": len(result)}


def calculate_rows_with_population(rows, populations, *, population_vintage):
    """Join CBP industry rows to a declared same-vintage county population."""
    enriched = []
    for row in rows:
        copy = dict(row)
        copy["POP"] = populations.get(str(row.get("fips") or "").strip())
        enriched.append(copy)
    result, audit = calculate_rows(enriched)
    audit["population_vintage"] = population_vintage
    audit["population_counties"] = len(populations)
    return result, audit
