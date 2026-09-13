"""NOAA annual/seasonal normals snowfall calculations."""

from __future__ import annotations

import csv
import math
import tarfile
from pathlib import Path


def annual_snowfall_feet(value, years):
    try:
        inches = float(str(value).strip())
        support = float(str(years).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(inches) or not math.isfinite(support) or inches < 0 or support < 10:
        return None
    return inches / 12.0


def parse_noaa_multivariate_tar(path):
    rows = []
    files_read = 0
    with tarfile.open(Path(path), "r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.lower().endswith(".csv"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            reader = csv.DictReader((line.decode("utf-8", "replace") for line in handle))
            row = next(reader, None)
            if not row:
                continue
            files_read += 1
            snow = annual_snowfall_feet(row.get("ANN-SNOW-NORMAL"), row.get("years_ANN-SNOW-NORMAL"))
            if snow is None:
                continue
            try:
                lat = float(row.get("LATITUDE", "")); lon = float(row.get("LONGITUDE", ""))
            except (TypeError, ValueError):
                continue
            rows.append({"station_id": row.get("STATION") or Path(member.name).stem,
                         "lat": lat, "lon": lon, "elevation_m": row.get("ELEVATION"),
                         "snowfall_feet": snow, "value_status": "derived_direct",
                         "method": "noaa_annual_snow_normal"})
    return rows, {"files_read": files_read, "stations_with_snowfall": len(rows), "minimum_support_years": 10}


def calculate(paths, counties):
    """Load a normalized county snowfall export."""
    from ..io import csv_rows
    if len(paths) != 1:
        raise ValueError("Snowfall requires one normalized county export")
    result = {}
    seen = set()
    for row in csv_rows(paths[0]):
        code = str(row.get("fips", "")).strip()
        if code in seen:
            raise ValueError(f"Duplicate snowfall county: {code}")
        seen.add(code)
        if code not in counties:
            continue
        try:
            value = float(row.get("snowfall_feet", ""))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            result[code] = {"value": value, "value_status": row.get("value_status", "derived_source"),
                            "observation_period": row.get("source_vintage", ""),
                            "method": row.get("method", "noaa_annual_snow_normal"),
                            "quality_note": f"stations_used={row.get('stations_used', '')}; max_distance_km={row.get('max_distance_km', '')}"}
    return result, {"matched_counties": len(result), "rows_read": len(seen)}


def blend_counties(stations, centroids, *, radius_km=175.0):
    """Interpolate direct station snow normals to county population centres."""
    output = {}
    for centroid in centroids:
        try:
            lat = float(centroid["latitude"]); lon = float(centroid["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        candidates = []
        for station in stations:
            try:
                y = (float(station["lat"]) - lat) * 111.32
                x = (float(station["lon"]) - lon) * 111.32 * math.cos(math.radians(lat))
                distance = math.hypot(x, y)
                if distance <= radius_km:
                    candidates.append((distance, station))
            except (KeyError, TypeError, ValueError):
                continue
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0])
        selected = candidates[:5]
        if selected[0][0] == 0:
            selected = selected[:1]
        weights = [1.0 / max(distance * distance, 1e-12) for distance, _ in selected]
        total = sum(weights)
        output[str(centroid["fips"])] = {
            "snowfall_feet": sum(weight * station["snowfall_feet"] for weight, (_, station) in zip(weights, selected)) / total,
            "value_status": "derived_nearby", "method": "idw_inverse_square",
            "stations_used": len(selected), "max_distance_km": max(distance for distance, _ in selected),
        }
    return output
