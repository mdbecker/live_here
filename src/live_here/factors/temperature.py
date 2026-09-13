"""Source-only NOAA daily-normal temperature calculations.

The NOAA normals archive stores a normal and standard deviation for each
station/day.  We turn those distributions into expected annual exceedance
days and interpolate only between stations with usable observations.  The
module deliberately has no workbook or legacy-estimate fallback.
"""

from __future__ import annotations

import csv
import math
import tarfile
from collections import defaultdict
from pathlib import Path

from ..io import csv_rows


_MISSING = {"", "-9999", "-9999.0", "-999.00", "-99", "-999"}


def _number(value):
    text = str(value or "").strip()
    if text in _MISSING:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= -9000:
        return None
    return number


def _ndtr(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def expected_threshold_days(rows, threshold, direction):
    """Return annual expected days for a TMAX threshold.

    ``direction`` is ``gte`` for TMAX >= threshold and ``lt`` for TMAX below
    threshold.  NOAA stations need at least 350 valid calendar days; shorter
    records remain missing rather than receiving an estimate.
    """
    if direction not in {"gte", "lt"}:
        raise ValueError("direction must be gte or lt")
    probabilities = []
    for row in rows:
        normal = _number(row.get("DLY-TMAX-NORMAL", row.get("normal")))
        sd = _number(row.get("DLY-TMAX-STDDEV", row.get("sd")))
        if normal is None or sd is None:
            continue
        sd = max(sd, 0.1)
        below = _ndtr((float(threshold) - normal) / sd)
        probabilities.append(1.0 - below if direction == "gte" else below)
    if len(probabilities) < 350:
        return None
    return sum(probabilities) * (365.25 / len(probabilities))


def blend_stations(stations, x, y, *, distance_unit="km", radius_km=125.0):
    """Blend nearby station metrics with inverse-square distance weights.

    Coordinates are in the same units as the query when ``distance_unit`` is
    ``km`` (the small, generic helper is also useful for projected tests).
    """
    if distance_unit != "km":
        raise ValueError("distance_unit must be km")
    candidates = []
    for station in stations:
        if station.get("hot_days") is None or station.get("cold_days") is None:
            continue
        try:
            distance = math.hypot(float(station["x"]) - float(x), float(station["y"]) - float(y))
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(distance):
            candidates.append((distance, station))
    if not candidates:
        return None
    nearby = [item for item in candidates if item[0] <= radius_km]
    selected = sorted(nearby or candidates, key=lambda item: item[0])[:5]
    if selected[0][0] == 0:
        selected = [selected[0]]
    weights = [1.0 / max(distance * distance, 1e-12) for distance, _ in selected]
    total = sum(weights)
    result = {
        "hot_days": sum(weight * station["hot_days"] for weight, (_, station) in zip(weights, selected)) / total,
        "cold_days": sum(weight * station["cold_days"] for weight, (_, station) in zip(weights, selected)) / total,
        "value_status": "derived_nearby" if nearby else "derived_fallback",
        "method": "idw_inverse_square",
        "stations_used": len(selected),
        "max_distance_km": max(distance for distance, _ in selected),
        "quality_note": "Source-derived station interpolation; no legacy estimate fallback",
    }
    return result


def _member(archive, basename):
    for info in archive.getmembers():
        if Path(info.name).name == basename:
            return info
    raise ValueError(f"NOAA archive is missing required member {basename}")


def _inventory_line(line):
    line = line.rstrip("\n")
    if "|" in line:  # compact fixture form used by the BDD test
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3:
            return {
                "station_id": parts[0], "lat": _number(parts[1]), "lon": _number(parts[2]),
                "elevation_m": _number(parts[3]) if len(parts) > 3 else None,
                "state": parts[4] if len(parts) > 4 else "", "name": parts[5] if len(parts) > 5 else "",
            }
    return {
        "station_id": line[0:11].strip(), "lat": _number(line[12:20]), "lon": _number(line[21:30]),
        "elevation_m": _number(line[31:37]), "state": line[38:40].strip(), "name": line[41:71].strip(),
    }


def parse_noaa_tar(path):
    """Parse the NOAA daily temperature normals archive.

    Returns station metric rows and an audit dictionary.  Only stations with
    350 or more valid TMAX normal/standard-deviation days receive metrics.
    """
    path = Path(path)
    normal_rows = defaultdict(dict)
    std_rows = defaultdict(dict)
    with tarfile.open(path, "r:*") as archive:
        normal_member = _member(archive, "dly-temp-normal.csv")
        std_member = _member(archive, "dly-temp-stddev.csv")
        inventory_member = _member(archive, "dly_inventory.txt")
        with archive.extractfile(normal_member) as handle:
            for row in csv.DictReader((line.decode("utf-8", "replace") for line in handle)):
                key = (row.get("GHCN_ID", "").strip(), row.get("month", "").strip(), row.get("day", "").strip())
                normal_rows[key] = row
        with archive.extractfile(std_member) as handle:
            for row in csv.DictReader((line.decode("utf-8", "replace") for line in handle)):
                key = (row.get("GHCN_ID", "").strip(), row.get("month", "").strip(), row.get("day", "").strip())
                std_rows[key] = row
        inventory = {}
        with archive.extractfile(inventory_member) as handle:
            for raw in handle:
                parsed = _inventory_line(raw.decode("utf-8", "replace"))
                if parsed["station_id"]:
                    inventory[parsed["station_id"]] = parsed

    grouped = defaultdict(list)
    for key, normal in normal_rows.items():
        station_id = key[0]
        std = std_rows.get(key)
        if std is None:
            continue
        grouped[station_id].append({
            "DLY-TMAX-NORMAL": normal.get("DLY-TMAX-NORMAL"),
            "DLY-TMAX-STDDEV": std.get("DLY-TMAX-STDDEV"),
        })
    stations = []
    valid_station_count = 0
    for station_id, rows in grouped.items():
        hot = expected_threshold_days(rows, 90.0, "gte")
        cold = expected_threshold_days(rows, 50.0, "lt")
        metadata = inventory.get(station_id, {"station_id": station_id})
        if hot is None or cold is None:
            # Keep the source station in the audit-facing parse result while
            # leaving its values missing so interpolation cannot use it.
            stations.append({**metadata, "hot_days": None, "cold_days": None,
                             "value_status": "missing", "method": "insufficient_valid_days"})
            continue
        valid_station_count += 1
        stations.append({**metadata, "hot_days": hot, "cold_days": cold, "value_status": "derived_direct", "method": "noaa_normals_expected_days"})
    return stations, {
        "archive": str(path), "inventory_station_count": len(inventory),
        "stations_with_temperature_metrics": valid_station_count,
        "station_records_with_normals": len(grouped),
        "minimum_valid_days": 350,
    }


def blend_counties(stations, centroids, *, radius_km=125.0):
    """Interpolate station metrics to Census population-centre rows."""
    result = {}
    for centroid in centroids:
        try:
            lat = float(centroid["latitude"])
            lon = float(centroid["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        projected = []
        for station in stations:
            if station.get("lat") is None or station.get("lon") is None:
                continue
            # Local equirectangular approximation is accurate enough for the
            # 125-km neighborhood and avoids adding a GIS dependency.
            y = (float(station["lat"]) - lat) * 111.32
            x = (float(station["lon"]) - lon) * 111.32 * math.cos(math.radians(lat))
            projected.append({**station, "x": x, "y": y})
        blended = blend_stations(projected, 0.0, 0.0, radius_km=radius_km)
        if blended is not None:
            result[str(centroid["fips"])] = blended
    return result


def calculate(paths, counties, field):
    """Load one normalized county temperature export for a heat/cold factor."""
    if len(paths) != 1:
        raise ValueError("Temperature requires one normalized county export")
    seen = set()
    results = {}
    missing = 0
    for row in csv_rows(paths[0]):
        code = str(row.get("fips", "")).strip()
        if code in seen:
            raise ValueError(f"Duplicate temperature county: {code}")
        if code not in counties:
            continue
        seen.add(code)
        value = _number(row.get(field))
        if value is None:
            missing += 1
            continue
        results[code] = {
            "value": value,
            "value_status": row.get("value_status", "derived_source"),
            "observation_period": row.get("source_vintage", ""),
            "method": row.get("method", "noaa_normals_expected_days"),
            "quality_note": f"stations_used={row.get('stations_used', '')}; max_distance_km={row.get('max_distance_km', '')}",
        }
    return results, {"rows_read": len(seen), "matched_counties": len(results), "missing_values": missing, "factor_field": field}
