"""Deterministic geographic inference for residual county factor gaps."""

import math


EARTH_RADIUS_KM = 6371.0088
MAX_DONORS = 5
MIN_DONORS = 2


def haversine_km(latitude_a, longitude_a, latitude_b, longitude_b):
    """Return the great-circle distance between two latitude/longitude pairs."""
    lat_a, lon_a, lat_b, lon_b = map(
        math.radians, (float(latitude_a), float(longitude_a), float(latitude_b), float(longitude_b))
    )
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    hav = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(min(1.0, hav)))


def _coordinates(county):
    try:
        latitude = float(county["latitude"])
        longitude = float(county["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Geographic inference requires validated county coordinates") from exc
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Geographic inference requires finite county coordinates")
    return latitude, longitude


def infer_missing(counties, observations):
    """Fill missing observations using a frozen, source-backed donor set.

    The input mappings are not mutated. Existing observations are copied into
    the returned mapping, while each inferred row includes only inference
    calculation metadata; the pipeline adds factor-level provenance fields.
    """
    source_donors = []
    for donor_fips, observation in observations.items():
        try:
            value = float(observation["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and donor_fips in counties:
            latitude, longitude = _coordinates(counties[donor_fips])
            source_donors.append((donor_fips, value, latitude, longitude, observation))
    if len(source_donors) < MIN_DONORS:
        raise ValueError("A selected factor requires at least two pre-inference donors")

    result = {fips: dict(observation) for fips, observation in observations.items()}
    for target_fips, target_county in counties.items():
        if target_fips in result:
            continue
        target_lat, target_lon = _coordinates(target_county)
        candidates = []
        for donor_fips, donor_value, donor_lat, donor_lon, observation in source_donors:
            distance = haversine_km(target_lat, target_lon, donor_lat, donor_lon)
            candidates.append((distance, donor_fips, donor_value, observation))
        selected = sorted(candidates, key=lambda item: (item[0], item[1]))[:MAX_DONORS]
        weights = [1.0 / max(distance, 1.0) ** 2 for distance, _, _, _ in selected]
        value = sum(weight * item[2] for weight, item in zip(weights, selected)) / sum(weights)
        result[target_fips] = {
            "value": value,
            "inference_donor_fips": ";".join(item[1] for item in selected),
            "nearest_donor_km": selected[0][0],
            "farthest_donor_km": selected[-1][0],
        }
    return result
