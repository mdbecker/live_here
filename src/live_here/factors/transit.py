"""Source-only EPA Access to Jobs and Workers via Transit adapter.

EPA publishes this product as a DBF inside a ZIP.  Its values are block-group
observations with coverage limited to GTFS-served metropolitan regions.  The
adapter aggregates means by the first five digits of GEOID10 and deliberately
leaves counties absent from the archive absent from the normalized export.
"""

from __future__ import annotations

import math
import statistics
import struct
import zipfile
from collections import defaultdict
from pathlib import Path


EPA_TRANSIT_URL = "https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip"
SOURCE_VINTAGE = "EPA Access to Jobs and Workers via Transit (2013 release)"
FIELDS = {
    "geoid": ("GEOID10", "GEOID"),
    "access": ("TrAccess_I", "TrAccess_Indexi"),
    "jobs": ("Pct_Jobs_b", "Pct_Jobs_byTr"),
    "population": ("Pct_Pop_by", "Pct_Pop_byTr"),
    "workers": ("Pct_Wrks_b", "Pct_Wrks_byTr"),
}


def _number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0:
        return None
    return result


def transit_composite(access, jobs, population, workers):
    """Return EPA's recovered 50/30/10/10 composite on a 0--100 scale."""
    values = [_number(value) for value in (access, jobs, population, workers)]
    if any(value is None for value in values):
        return None
    # The source guide describes proportions that can exceed 1 for cross-region
    # service. Preserve those observations while preventing malformed negatives.
    return 100.0 * (0.50 * values[0] + 0.30 * values[1] +
                    0.10 * values[2] + 0.10 * values[3])


def _header(data: bytes):
    if len(data) < 33 or data[0] not in range(0, 256):
        raise ValueError("Invalid DBF header")
    count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    fields = []
    position = 32
    while position < header_length - 1:
        descriptor = data[position:position + 32]
        if descriptor[0] == 0x0D:
            break
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", "ignore")
        fields.append((name, chr(descriptor[11]), descriptor[16], descriptor[17]))
        position += 32
    return count, header_length, record_length, fields


def iter_dbf_records(source: Path):
    """Yield undeleted records from the first DBF member in *source* ZIP."""
    with zipfile.ZipFile(source) as archive:
        member = next((name for name in archive.namelist() if name.lower().endswith(".dbf")), None)
        if member is None:
            raise ValueError(f"{source} does not contain a DBF member")
        data = archive.read(member)
    count, header_length, record_length, fields = _header(data)
    position = header_length
    for _ in range(count):
        record = data[position:position + record_length]
        position += record_length
        if len(record) < record_length or record[:1] == b"*":
            continue
        output = {}
        offset = 1
        for name, kind, width, decimals in fields:
            text = record[offset:offset + width].decode("latin-1", "ignore").strip()
            offset += width
            if not text:
                output[name] = None
            elif kind in {"N", "F"}:
                try:
                    output[name] = float(text)
                except ValueError:
                    output[name] = None
            else:
                output[name] = text
        yield output


def _first(row, names):
    for name in names:
        if name in row:
            return row[name]
    return None


def build_transit_rollup(source: Path):
    """Aggregate block-group component means by five-digit county FIPS."""
    fields = ("access", "jobs", "population", "workers")
    aggregates = defaultdict(lambda: {field: [] for field in fields})
    records_read = 0
    for row in iter_dbf_records(Path(source)):
        records_read += 1
        geoid = str(_first(row, FIELDS["geoid"]) or "").strip()
        if len(geoid) < 5 or not geoid[:5].isdigit():
            continue
        fips = geoid[:5]
        for field in fields:
            value = _number(_first(row, FIELDS[field]))
            if value is not None:
                aggregates[fips][field].append(value)
    result = {}
    for fips, values in aggregates.items():
        means = {field: (statistics.mean(values[field]) if values[field] else None)
                 for field in fields}
        score = transit_composite(*(means[field] for field in fields))
        result[fips] = {"fips": fips, "block_groups": max((len(values[field]) for field in fields), default=0),
                        "access_mean": means["access"], "jobs_mean": means["jobs"],
                        "population_mean": means["population"], "workers_mean": means["workers"],
                        "transit_score": score}
    return result, {"records_read": records_read, "covered_counties": len(result),
                    "scoring_method": "100 * (0.50*TrAccess_Indexi + 0.30*Pct_Jobs_byTr + 0.10*Pct_Pop_byTr + 0.10*Pct_Wrks_byTr)",
                    "source_vintage": SOURCE_VINTAGE}


def calculate_transit(source: Path, counties):
    """Return normalized factor rows, preserving missing counties."""
    rollup, audit = build_transit_rollup(source)
    values = {}
    for fips in counties:
        row = rollup.get(fips)
        if row and row["transit_score"] is not None:
            values[fips] = {"value": row["transit_score"], "value_status": "derived_source",
                            "observation_period": SOURCE_VINTAGE, "method": audit["scoring_method"],
                            "quality_note": "EPA coverage is limited to GTFS-served metropolitan regions; no fallback or old estimate used"}
    audit["matched_counties"] = len(values)
    audit["missing_counties"] = len(counties) - len(values)
    return values, audit
