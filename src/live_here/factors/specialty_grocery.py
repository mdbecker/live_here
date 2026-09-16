"""Adapter for the archived specialty-grocery county workbook."""

import difflib
import math
import re
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
N = "{" + MAIN_NS + "}"

SHEET_NAME = "County Density Ranking"
COUNTY_HEADER = "County"
STATE_HEADER = "State"
FIPS_HEADER = "County FIPS"
VALUE_HEADER = "Proxy / Lower-Bound Stores"
FUZZY_CUTOFF = 0.90
FUZZY_MARGIN = 0.05


def _text(value):
    return "" if value is None else str(value).strip()


def _cell_value(cell, shared_strings):
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(N + "t"))
    value = cell.find(N + "v")
    text = "" if value is None else value.text or ""
    if cell.attrib.get("t") == "s" and text:
        return shared_strings[int(text)]
    return text


def _worksheet_path(archive, sheet_name):
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rels = {node.attrib["Id"]: node.attrib["Target"].lstrip("/") for node in relationships}
    for sheet in workbook.findall(N + "sheets/" + N + "sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get("{" + DOC_REL_NS + "}" + "id")
            target = rels.get(relationship_id)
            if target:
                return target
    raise ValueError(f"Workbook sheet not found: {sheet_name}")


def _read_rows(path):
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"Specialty grocery source must be XLSX: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = ["".join(node.text or "" for node in item.iter(N + "t"))
                                  for item in strings.findall(N + "si")]
            worksheet = ET.fromstring(archive.read(_worksheet_path(archive, SHEET_NAME)))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Unable to read specialty grocery workbook: {path}") from exc

    rows = []
    for row in worksheet.findall(".//" + N + "sheetData/" + N + "row"):
        values = {}
        for cell in row.findall(N + "c"):
            values[cell.attrib["r"]] = _cell_value(cell, shared_strings)
        rows.append((int(row.attrib["r"]), values))

    header_row = None
    headers = {}
    required = {COUNTY_HEADER, STATE_HEADER, FIPS_HEADER, VALUE_HEADER}
    for row_number, values in rows:
        by_column = {reference.rstrip("0123456789"): _text(value) for reference, value in values.items()}
        if required <= set(by_column.values()):
            header_row = row_number
            headers = {value: column for column, value in by_column.items() if value in required}
            break
    if header_row is None:
        raise ValueError(f"Workbook is missing required specialty grocery headers: {sorted(required)}")

    result = []
    for row_number, values in rows:
        if row_number <= header_row:
            continue
        row = {header: _text(values.get(f"{column}{row_number}")) for header, column in headers.items()}
        if not any(row.values()):
            continue
        if not row[COUNTY_HEADER] and not row[STATE_HEADER] and not row[FIPS_HEADER]:
            continue
        row["source_row"] = row_number
        result.append(row)
    return result


def _normalize_name(value):
    value = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode("ascii")
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    for suffix in (" county", " parish", " borough", " census area", " municipality", " city"):
        if value.endswith(suffix):
            value = value[:-len(suffix)].strip()
            break
    return value


def _fuzzy_target(name, state, counties):
    candidates = [county for county in counties.values()
                  if _text(county.get("state")).casefold() == state.casefold()]
    scored = sorted(
        ((difflib.SequenceMatcher(None, _normalize_name(name), _normalize_name(county["name"])).ratio(), county)
         for county in candidates),
        key=lambda item: (item[0], item[1]["fips"]), reverse=True,
    )
    if not scored or scored[0][0] < FUZZY_CUTOFF:
        raise ValueError(f"Unmatched specialty grocery county: {name}, {state}")
    if len(scored) > 1 and scored[0][0] - scored[1][0] < FUZZY_MARGIN:
        raise ValueError(f"Ambiguous specialty grocery county: {name}, {state}")
    return scored[0][1]


def _target_county(row, counties):
    name = row[COUNTY_HEADER]
    state = row[STATE_HEADER]
    source_fips = row[FIPS_HEADER]
    if source_fips:
        if not re.fullmatch(r"\d{5}", source_fips):
            raise ValueError(f"Invalid specialty grocery county FIPS: {source_fips}")
        target = counties.get(source_fips)
        if target is None:
            raise ValueError(f"Unmatched specialty grocery county FIPS: {source_fips}")
        if (_text(target["state"]).casefold() != state.casefold() or
                _normalize_name(target["name"]) != _normalize_name(name)):
            raise ValueError(f"Conflicting specialty grocery county identity for FIPS {source_fips}")
        return target, "fips"

    exact = [county for county in counties.values()
             if _text(county.get("state")).casefold() == state.casefold() and
             _normalize_name(county["name"]) == _normalize_name(name)]
    if len(exact) == 1:
        return exact[0], "normalized"
    if len(exact) > 1:
        raise ValueError(f"Ambiguous specialty grocery county: {name}, {state}")
    return _fuzzy_target(name, state, counties), "fuzzy"


def _store_value(value, row_number):
    if not _text(value):
        return 0, True
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid specialty grocery store value at workbook row {row_number}: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Invalid specialty grocery store value at workbook row {row_number}: {value!r}")
    return (int(number) if number.is_integer() else number), False


def calculate(paths, counties):
    """Return one explicit specialty-grocery value for every target county."""
    if len(paths) != 1:
        raise ValueError("Specialty groceries requires one workbook source")
    rows = _read_rows(paths[0])
    result = {}
    audit = {
        "rows_read": len(rows), "matched_by_fips": 0, "normalized_matches": 0,
        "fuzzy_matches": 0, "zero_filled_count": 0, "source_backed_count": 0,
        "unmatched": [], "ambiguous": [], "conflicts": [], "duplicates": [],
    }
    for row in rows:
        try:
            target, match_method = _target_county(row, counties)
        except ValueError as exc:
            message = str(exc)
            if "Ambiguous" in message:
                audit["ambiguous"].append(message)
            elif "Conflicting" in message:
                audit["conflicts"].append(message)
            else:
                audit["unmatched"].append(message)
            raise
        code = target["fips"]
        if code in result:
            audit["duplicates"].append(code)
            raise ValueError(f"Duplicate specialty grocery county: {code}")
        value, inferred = _store_value(row[VALUE_HEADER], row["source_row"])
        if match_method == "fips":
            audit["matched_by_fips"] += 1
        elif match_method == "normalized":
            audit["normalized_matches"] += 1
        else:
            audit["fuzzy_matches"] += 1
        if inferred:
            audit["zero_filled_count"] += 1
        else:
            audit["source_backed_count"] += 1
        result[code] = {
            "value": value,
            "value_status": "inferred_zero" if inferred else "derived_workbook_proxy",
            "is_inferred": "true" if inferred else "false",
            "observation_period": "as provided in archived workbook",
            "method": "workbook_proxy_lower_bound_zero_fill" if inferred else "workbook_proxy_lower_bound",
            "quality_note": "No workbook value; zero applied per specialty-grocery lower-bound rule." if inferred else
                            "County proxy/lower-bound store count from the archived workbook.",
        }

    for code, county in counties.items():
        if code not in result:
            audit["zero_filled_count"] += 1
            result[code] = {
                "value": 0,
                "value_status": "inferred_zero",
                "is_inferred": "true",
                "observation_period": "as provided in archived workbook",
                "method": "workbook_proxy_lower_bound_zero_fill",
                "quality_note": "County absent from workbook; zero applied per specialty-grocery lower-bound rule.",
            }
    return result, audit
