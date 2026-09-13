"""Small explicit contracts for files, geography, and numeric observations."""

import csv
import hashlib
import io
import math
import re
import zipfile
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path, required=()):
    """Read a CSV or a ZIP containing exactly one CSV, preserving identifier text."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if len(members) != 1:
                raise ValueError(f"{path}: expected exactly one CSV in ZIP")
            with archive.open(members[0]) as raw:
                return _read_rows(io.TextIOWrapper(raw, encoding="utf-8-sig"), required, path)
    if path.suffix.lower() != ".csv":
        raise ValueError(f"{path}: only CSV or single-CSV ZIP accepted")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return _read_rows(stream, required, path)


def _read_rows(stream, required, path):
    reader = csv.DictReader(stream)
    headers = reader.fieldnames or []
    if len(set(headers)) != len(headers):
        raise ValueError(f"{path}: duplicate headers")
    missing = set(required) - set(headers)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError(f"{path}: malformed CSV row")
    return rows


def fips(value, width=5):
    """Reject floats, missing components, and implicit geography conversion."""
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]{" + str(width) + r"}", value):
        raise ValueError(f"Expected a {width}-digit geographic code, got {value!r}")
    if width == 5 and (value[:2] == "00" or value[2:] == "000"):
        raise ValueError(f"Not a county code: {value}")
    return value


def number(value, label, minimum=None, maximum=None):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid number {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label}: nonfinite number")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label}: below {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label}: above {maximum}")
    return result


def load_counties(path):
    rows = csv_rows(path, ["fips", "name", "state", "geography_vintage"])
    counties = {}
    for row in rows:
        key = fips(row["fips"])
        if key in counties:
            raise ValueError(f"Duplicate county {key}")
        if not all(row[k].strip() for k in ("name", "state", "geography_vintage")):
            raise ValueError(f"Incomplete county identity: {key}")
        counties[key] = row
    if not counties:
        raise ValueError("County universe is empty")
    if len({r["geography_vintage"] for r in rows}) != 1:
        raise ValueError("County universe mixes geography vintages")
    return dict(sorted(counties.items()))


def write_csv(path, rows, fields):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
