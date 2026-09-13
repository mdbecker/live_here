"""Source-only helpers for BLS OEWS occupation and industry adjustments."""

from __future__ import annotations

import math
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_SUPPRESSED = {"*", "**", "#", "NA", "N/A", "D"}


def _number(value):
    text = str(value or "").strip()
    if not text or text in _SUPPRESSED:
        return None
    try:
        number = float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _column_index(reference):
    letters = "".join(character for character in str(reference) if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + ord(character.upper()) - ord("A") + 1
    return index - 1


def _xlsx_shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(item.itertext()) for item in root.findall(f".//{_NS}si")]


def iter_oews_xlsx_rows(path):
    """Yield OEWS rows while honoring sparse A1 references in an XLSX sheet."""
    with zipfile.ZipFile(path) as archive:
        sheets = sorted(name for name in archive.namelist()
                        if name.startswith("xl/worksheets/") and name.endswith(".xml"))
        if not sheets:
            raise ValueError("OEWS workbook has no worksheet")
        shared = _xlsx_shared_strings(archive)
        with archive.open(sheets[0]) as stream:
            headers = None
            for _, element in ET.iterparse(stream, events=("end",)):
                if element.tag != f"{_NS}row":
                    continue
                cells = {}
                for fallback_index, cell in enumerate(element.findall(f"{_NS}c")):
                    reference = cell.get("r")
                    index = _column_index(reference) if reference else fallback_index
                    kind = cell.get("t")
                    value = cell.findtext(f"{_NS}v", default="")
                    if kind == "s" and value.isdigit() and int(value) < len(shared):
                        value = shared[int(value)]
                    elif kind == "inlineStr":
                        inline = cell.find(f"{_NS}is")
                        value = "".join(inline.itertext()) if inline is not None else ""
                    cells[index] = value or ""
                if headers is None:
                    headers = [str(cells.get(index, "")).strip().upper()
                               for index in range(max(cells, default=-1) + 1)]
                elif cells:
                    source = {header: cells.get(index, "") for index, header in enumerate(headers) if header}
                    employment = str(source.get("TOT_EMP", source.get("EMPLOYMENT", ""))).strip()
                    occ_code = str(source.get("OCC_CODE", source.get("SOC_CODE", ""))).strip()
                    yield {
                        "area_code": str(source.get("AREA", source.get("AREA_CODE", ""))).strip(),
                        "area_title": str(source.get("AREA_TITLE", "")).strip(),
                        "area_type": str(source.get("AREA_TYPE", "")).strip(),
                        "prim_state": str(source.get("PRIM_STATE", "")).strip(),
                        "naics": str(source.get("NAICS", "")).strip(),
                        "naics_title": str(source.get("NAICS_TITLE", "")).strip(),
                        "industry_group": str(source.get("I_GROUP", "")).strip(),
                        "own_code": str(source.get("OWN_CODE", "")).strip(),
                        "occ_code": occ_code,
                        "soc_code": occ_code,
                        "occ_title": str(source.get("OCC_TITLE", "")).strip(),
                        "occ_group": str(source.get("O_GROUP", "")).strip(),
                        "employment": employment,
                        "employment_status": "suppressed" if employment in _SUPPRESSED else "reported",
                    }
                element.clear()


def parse_oews_xlsx_rows(path):
    """Return normalized OEWS rows; retained for small tests and CSV exports."""
    return list(iter_oews_xlsx_rows(path))


def _cohort_key(row):
    return (str(row.get("area_code", "")).strip(), str(row.get("naics", "")).strip(),
            str(row.get("own_code", "")).strip())


def occupation_share(rows, selected_codes, *, naics=None):
    """Measure selected detailed occupations against one OEWS all-occupations row.

    Hierarchical SOC totals are excluded. Suppressed or absent requested detailed
    occupations make the cohort unavailable rather than contributing a zero.
    """
    selected_codes = {str(code) for code in selected_codes}
    cohorts = defaultdict(list)
    for row in rows:
        if naics is None or str(row.get("naics", "")).strip() == str(naics):
            cohorts[_cohort_key(row)].append(row)
    valid, incomplete = [], []
    for key, cohort in cohorts.items():
        total_rows = [row for row in cohort if str(row.get("occ_code") or row.get("soc_code") or "").strip() == "00-0000"]
        if len(total_rows) != 1 or _number(total_rows[0].get("employment")) is None:
            continue
        selected = {str(row.get("occ_code") or row.get("soc_code") or "").strip(): row
                    for row in cohort if str(row.get("occ_code") or row.get("soc_code") or "").strip() in selected_codes}
        suppressed = sorted(code for code in selected_codes if code in selected and _number(selected[code].get("employment")) is None)
        missing = sorted(code for code in selected_codes if code not in selected)
        if suppressed or missing:
            incomplete.append((suppressed, missing))
            continue
        numerator = sum(_number(selected[code].get("employment")) for code in selected_codes)
        denominator = _number(total_rows[0].get("employment"))
        if denominator and denominator > 0:
            valid.append((key, numerator, denominator))
    if len(valid) == 1:
        key, numerator, denominator = valid[0]
        return {"cohort": key, "numerator": numerator, "denominator": denominator,
                "share": numerator / denominator, "suppressed_selected_codes": [], "missing_selected_codes": []}
    if len(valid) > 1:
        raise ValueError("OEWS rows contain multiple cohorts; select one area/industry/ownership cohort")
    return {"cohort": None, "numerator": None, "denominator": None, "share": None,
            "suppressed_selected_codes": sorted({code for codes, _ in incomplete for code in codes}),
            "missing_selected_codes": sorted({code for _, codes in incomplete for code in codes})}


def selected_trade_share(rows, selected_codes):
    """Legacy fixture helper; production code uses ``occupation_share``."""
    total = selected = 0.0
    any_row = False
    for row in rows:
        value = _number(row.get("employment") or row.get("TOT_EMP"))
        if value is None:
            continue
        any_row = True
        total += value
        if str(row.get("soc_code") or row.get("OCC_CODE") or "").strip() in selected_codes:
            selected += value
    return selected / total if any_row and total > 0 else None


def area_trade_share_details(rows, selected_codes, *, naics="000000"):
    grouped = defaultdict(list)
    for row in rows:
        if str(row.get("naics", "")).strip() == naics:
            grouped[str(row.get("area_code", "")).strip()].append(row)
    return {area: occupation_share(area_rows, selected_codes, naics=naics)
            for area, area_rows in grouped.items()}


def area_trade_shares(rows, selected_codes):
    return {area: detail["share"] for area, detail in area_trade_share_details(rows, selected_codes).items()
            if detail["share"] is not None}


def bounded_ratio(local_share, national_share, lower=0.65, upper=1.35):
    try:
        local, national = float(local_share), float(national_share)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(local) or not math.isfinite(national) or national <= 0:
        return None
    return min(upper, max(lower, local / national))


def calculate_trades(cbp_rows, state_shares, national_share, *, metro_shares=None, county_cbsa=None, industry_share=None):
    """Apply recovered industry share and local OEWS mix to CBP density."""
    if _number(industry_share) is None:
        return {}
    metro_shares, county_cbsa = metro_shares or {}, county_cbsa or {}
    results = {}
    for fips, row in cbp_rows.items():
        base = _number(row.get("trade_employment_per_1k"))
        area = str(county_cbsa.get(str(fips), "")).strip()
        local_share = metro_shares.get(area)
        source = "metro" if local_share is not None else "state"
        if local_share is None:
            local_share = state_shares.get(str(fips)[:2])
        ratio = bounded_ratio(local_share, national_share) if local_share is not None else None
        if base is None or ratio is None:
            continue
        results[fips] = {
            "value": base * float(industry_share) * ratio,
            "value_status": "derived_metro_proxy" if source == "metro" else "derived_state_proxy",
            "method": "cbp_naics238_density_times_oews_naics238_selected_share_times_bounded_oews_mix",
            "quality_note": f"OEWS {source} proxy; multiplier bounded to 0.65-1.35",
        }
    return results
