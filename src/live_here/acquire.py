"""Acquire immutable public sources and prepare inputs for implemented factors."""

import csv
import io
import json
import re
import os
import subprocess
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .io import csv_rows, fips, number, sha256, write_csv

STATE_NAMES = dict(pair.split("=", 1) for pair in (
    "AL=Alabama|AK=Alaska|AZ=Arizona|AR=Arkansas|CA=California|CO=Colorado|CT=Connecticut|"
    "DE=Delaware|DC=District Of Columbia|FL=Florida|GA=Georgia|HI=Hawaii|ID=Idaho|IL=Illinois|"
    "IN=Indiana|IA=Iowa|KS=Kansas|KY=Kentucky|LA=Louisiana|ME=Maine|MD=Maryland|MA=Massachusetts|"
    "MI=Michigan|MN=Minnesota|MS=Mississippi|MO=Missouri|MT=Montana|NE=Nebraska|NV=Nevada|"
    "NH=New Hampshire|NJ=New Jersey|NM=New Mexico|NY=New York|NC=North Carolina|ND=North Dakota|"
    "OH=Ohio|OK=Oklahoma|OR=Oregon|PA=Pennsylvania|RI=Rhode Island|SC=South Carolina|"
    "SD=South Dakota|TN=Tennessee|TX=Texas|UT=Utah|VT=Vermont|VA=Virginia|WA=Washington|"
    "WV=West Virginia|WI=Wisconsin|WY=Wyoming|PR=Puerto Rico|VI=Virgin Islands"
).split("|"))

# Reviewed 2019-to-2020 Census geography change: Valdez-Cordova was split
# into Chugach and Copper River.  This is intentionally the only bridge.
CENTER_SUCCESSOR_BRIDGES = {"02261": ("02063", "02066")}


def curl_fetch(url):
    """Optional system HTTP transport for hosts where Python DNS is unavailable."""
    result = subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                             "--connect-timeout", "20", "--max-time", "600", "--retry", "2", url],
                            capture_output=True, check=True)
    return result.stdout


def download(url, target, fetch=None):
    """Save bytes and receipt. Verified caches are immutable and reusable offline."""
    target = Path(target)
    receipt = target.with_suffix(target.suffix + ".source.json")
    if target.exists() or receipt.exists():
        if not target.is_file() or not receipt.is_file():
            raise ValueError(f"Incomplete cached source: {target}")
        record = json.loads(receipt.read_text())
        if record["url"] != url or record["sha256"] != sha256(target):
            raise ValueError(f"Cached source URL/checksum mismatch: {target}")
        return record
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        if fetch is not None:
            temporary.write_bytes(fetch(url))
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "LiveHereResearch/0.1 (public-data research)"})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as stream:
                expected = response.headers.get("Content-Length")
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(chunk)
            if expected is not None and temporary.stat().st_size != int(expected):
                raise OSError(f"Incomplete download: {url}")
        if not temporary.stat().st_size:
            raise ValueError(f"Empty download: {url}")
        record = {"url": url, "sha256": sha256(temporary), "bytes": temporary.stat().st_size,
                  "retrieved_at": datetime.now(timezone.utc).isoformat()}
        temporary.replace(target)
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        return record
    finally:
        temporary.unlink(missing_ok=True)


def discover_aqi_releases(listing, today=None):
    """Select the two newest complete county-AQI calendar years from EPA HTML."""
    today = today or datetime.now(timezone.utc).date()
    text = listing.decode("utf-8", "replace") if isinstance(listing, bytes) else str(listing)
    years = sorted({int(year) for year in re.findall(r"annual_aqi_by_county_(\d{4})\.zip", text)
                    if int(year) < today.year}, reverse=True)
    if len(years) < 2:
        raise ValueError("EPA listing does not contain two complete county AQI years")
    base = "https://aqs.epa.gov/aqsweb/airdata"
    return [{"id": f"aqi{year}", "year": year,
             "filename": f"annual_aqi_by_county_{year}.zip",
             "url": f"{base}/annual_aqi_by_county_{year}.zip"}
            for year in years[:2]]


def normalize_walkability_row(row):
    result = {}
    geoid_key = "GEOID20" if "GEOID20" in row else "GEOID10"
    for key, width in ((geoid_key, 12), ("STATEFP", 2), ("COUNTYFP", 3)):
        if key == geoid_key and (not str(row.get(key, "")).strip() or "E+" in str(row.get(key, "")).upper()):
            # EPA's published CSV rounds both GEOID columns to scientific notation.
            # Rebuild the exact block-group identifier from its components; never
            # parse the rounded float.
            if not {"TRACTCE", "BLKGRPCE"}.issubset(row):
                raise ValueError(f"{key} is rounded and component columns are missing")
            text = (str(row["STATEFP"]).strip().zfill(2) +
                    str(row["COUNTYFP"]).strip().zfill(3) +
                    str(row["TRACTCE"]).strip().split(".")[0].zfill(6) +
                    str(row["BLKGRPCE"]).strip().split(".")[0].zfill(1))
            result["GEOID"] = fips(text, 12)
            continue
        text = str(row[key]).strip()
        if re.fullmatch(r"[0-9]+\.0", text):
            text = text[:-2]
        if not text.isascii() or not text.isdigit() or len(text) > width:
            raise ValueError(f"Invalid EPA identifier {key}: {text}")
        result[key] = fips(text.zfill(width), width)
    geoid = result.get("GEOID", result.get(geoid_key))
    if not geoid.startswith(result["STATEFP"] + result["COUNTYFP"]):
        raise ValueError("EPA block-group and county codes disagree")
    if geoid_key == "GEOID20" and geoid_key in result:
        result["GEOID"] = result.pop(geoid_key)
    result.update({key: row[key] for key in ("TotPop", "NatWalkInd")})
    return result


def normalize_counties(text, vintage):
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not {"USPS", "GEOID", "NAME"}.issubset(reader.fieldnames or []):
        raise ValueError("Census gazetteer lacks USPS/GEOID/NAME")
    rows = [{"fips": fips(r["GEOID"]), "name": r["NAME"].strip(),
             "state": r["USPS"].strip(), "geography_vintage": vintage} for r in reader]
    if len({r["fips"] for r in rows}) != len(rows):
        raise ValueError("Duplicate Census counties")
    return sorted(rows, key=lambda r: r["fips"])


def attach_population_centers(counties, text):
    """Attach validated Census 2020 mean centers to target county rows."""
    county_codes = {row["fips"] for row in counties}
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"STATEFP", "COUNTYFP", "POPULATION", "LATITUDE", "LONGITUDE"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Census population-center file lacks required columns")
    centers = {}
    for row in reader:
        state = str(row.get("STATEFP", "")).strip()
        county = str(row.get("COUNTYFP", "")).strip()
        if not state.isdigit() or not county.isdigit() or len(state) > 2 or len(county) > 3:
            continue
        try:
            code = fips(state.zfill(2) + county.zfill(3))
        except ValueError:
            continue
        if code in centers:
            raise ValueError(f"Duplicate Census population center: {code}")
        latitude = number(row.get("LATITUDE"), f"{code} latitude", -90, 90)
        longitude = number(row.get("LONGITUDE"), f"{code} longitude", -180, 180)
        population = number(row.get("POPULATION"), f"{code} population", 0)
        centers[code] = {"latitude": latitude, "longitude": longitude, "population": population}
    missing = sorted(county_codes - set(centers))
    if "02261" in missing:
        successors = CENTER_SUCCESSOR_BRIDGES["02261"]
        if any(successor not in centers or centers[successor]["population"] <= 0 for successor in successors):
            raise ValueError("Missing or invalid Census population-center successors for: 02261")
        total_population = sum(centers[successor]["population"] for successor in successors)
        centers["02261"] = {
            "latitude": sum(centers[successor]["population"] * centers[successor]["latitude"] for successor in successors) / total_population,
            "longitude": sum(centers[successor]["population"] * centers[successor]["longitude"] for successor in successors) / total_population,
            "population": total_population,
        }
        missing.remove("02261")
    if missing:
        raise ValueError(f"Missing Census population centers for: {', '.join(missing)}")
    return [{**row, "latitude": centers[row["fips"]]["latitude"],
             "longitude": centers[row["fips"]]["longitude"], "coordinate_vintage": "2020"}
            for row in sorted(counties, key=lambda item: item["fips"])]


def aqi_crosswalk(counties, observations):
    """Only exact names and removal of non-city legal suffixes; no fuzzy matching."""
    lookup = defaultdict(set)
    by_fips = {r["fips"]: r for r in counties}
    for county in counties:
        state = STATE_NAMES.get(county["state"], county["state"]).casefold()
        name = county["name"].strip().casefold()
        aliases = {name}
        for suffix in (" county", " parish", " borough", " census area", " municipality"):
            if name.endswith(suffix):
                aliases.add(name[:-len(suffix)])
        for alias in aliases:
            lookup[(state, alias)].add(county["fips"])
    rows, unmatched, ambiguous = [], [], []
    for state, name in sorted({(r["State"].strip(), r["County"].strip()) for r in observations}):
        matches = lookup.get((state.casefold(), name.casefold()), set())
        if len(matches) == 1:
            code = next(iter(matches))
            rows.append({"State": state, "County": name, "fips": code,
                         "geography_vintage": by_fips[code]["geography_vintage"]})
        elif matches:
            ambiguous.append([state, name, sorted(matches)])
        else:
            unmatched.append([state, name])
    return rows, {"unmatched": unmatched, "ambiguous": ambiguous,
                  "method": "exact case-insensitive names; remove county/parish/borough/census-area/municipality suffix only; retain city"}


def prepare_current(root, source_definitions, receipts):
    """Normalize pinned source releases without consulting historical workbooks."""
    root = Path(root)
    raw = root / "data/raw/current"
    target = root / "data/interim/current"
    target.mkdir(parents=True, exist_ok=True)
    paths = {key: raw / entry[0] for key, entry in source_definitions.items()}
    for key, path in paths.items():
        if sha256(path) != receipts[key]["sha256"]:
            raise ValueError(f"Raw source checksum mismatch: {key}")
    with zipfile.ZipFile(paths["counties"]) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".txt")]
        if len(names) != 1:
            raise ValueError("Expected one Census gazetteer text file")
        payload = archive.read(names[0])
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = payload.decode("cp1252")
        counties = normalize_counties(text, "2019")
    center_text = paths["centers"].read_text(encoding="utf-8-sig")
    counties = attach_population_centers(counties, center_text)
    write_csv(target / "counties.csv", counties,
              ["fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage"])
    aqis = sorted(key for key in paths if key.startswith("aqi"))
    observations = [row for key in aqis for row in csv_rows(paths[key])]
    crosswalk, audit = aqi_crosswalk(counties, observations)
    if audit["ambiguous"]:
        raise ValueError(f"Ambiguous AQI county names: {audit['ambiguous']}")
    write_csv(target / "aqi-crosswalk.csv", crosswalk, ["State", "County", "fips", "geography_vintage"])
    walk_count = 0
    with paths["walkability"].open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = ["GEOID", "STATEFP", "COUNTYFP", "TotPop", "NatWalkInd"]
        with (target / "walkability.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for original in reader:
                row = normalize_walkability_row(original)
                if "GEOID10" in row:
                    row["GEOID"] = row.pop("GEOID10")
                writer.writerow(row)
                walk_count += 1

    def source(ident, path, parents, vintage, method):
        first = receipts[parents[0]]
        return {"id": ident, "path": os.path.relpath(path, target), "sha256": sha256(path),
                "url": first["url"], "vintage": vintage, "geography_vintage": "2019",
                "role": "source_export", "license": "Publicly available US federal agency data; retain source attribution and limitations",
                "retrieved_at": first["retrieved_at"], "method": method,
                "raw_parent_sha256": {key: receipts[key]["sha256"] for key in parents},
                "raw_parent_urls": {key: receipts[key]["url"] for key in parents}}

    manifest = [source("counties", target / "counties.csv", ["counties", "centers"], "2019",
                       "Census 2019 gazetteer identity plus 2020 county mean centers; all source counties retained"),
                source("aqi_crosswalk", target / "aqi-crosswalk.csv", ["counties", *aqis], "2019 target; " + "-".join(key.removeprefix("aqi") for key in aqis) + " source names",
                       audit["method"]),
                source("walkability", target / "walkability.csv", ["walkability"], "EPA SLD 3.0 2021; 2018 ACS population",
                       "Select official NatWalkInd/TotPop and 2019 county identifiers; preserve original GEOID20 in generic GEOID column")]
    for key in aqis:
        manifest.append(source(key, paths[key], [key], key.removeprefix("aqi"),
                               "Unmodified EPA annual AQI file; matched to target counties by explicit crosswalk; unmatched names excluded and audited"))
        manifest[-1]["role"] = "raw_source"
        manifest[-1]["source_geography_vintage"] = "As reported by EPA; name-matched to 2019 target; not a spatial reaggregation"
    config = {"mode": "research", "geography_source": "counties", "factors": ["aqi", "walkability"],
              "iterations": 1000, "seed": 42,
              "adapters": {"aqi": {"sources": aqis, "crosswalk": "aqi_crosswalk"},
                           "walkability": {"sources": ["walkability"]}}, "sources": manifest,
              "geography_scope": "2019 Census gazetteer: 50 states, DC and Puerto Rico; other Island Areas absent",
              "limitations": ["Source coverage and geographic inference remain explicit; dataset-specific gatherers append the selected V1 factors", "EPA SLD geography fields are documented as 2019; GEOID20 is not 2020 Census geography",
                              "AQI uses the two latest complete years selected from EPA's published listing; exact-name mapping does not establish unchanged boundaries",
                              "Unmatched names and counties without observations are retained for pipeline-level geographic inference"]}
    config_path = target / "config.json"
    if config_path.exists():
        existing = json.loads(config_path.read_text())
        base_ids = {entry["id"] for entry in manifest}
        existing_sources = [entry for entry in existing.get("sources", [])
                            if entry.get("id") not in base_ids
                            and entry.get("id") not in {"counties", "aqi_crosswalk", "walkability"}
                            and not str(entry.get("id", "")).startswith("aqi")]
        existing_factors = [factor for factor in existing.get("factors", []) if factor not in {"aqi", "walkability"}]
        existing_adapters = {factor: settings for factor, settings in existing.get("adapters", {}).items()
                             if factor not in {"aqi", "walkability"}}
        config["factors"] += existing_factors
        config["adapters"].update(existing_adapters)
        config["sources"] += existing_sources
    audit.update({"county_count": len(counties), "block_group_rows": walk_count,
                  "aqi_source_rows": len(observations), "matched_aqi_names": len(crosswalk),
                  "raw_sources": receipts, "geography_scope": config["geography_scope"],
                  "limitations": config["limitations"]})
    (target / "acquisition-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    return {"config": str(target / "config.json"), "county_count": len(counties),
            "block_group_rows": walk_count, "matched_aqi_names": len(crosswalk), "unmatched": audit["unmatched"]}
