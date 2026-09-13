"""Given/When/Then closure scenarios for the May 2025 OEWS source port."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors import oews
from scripts import gather_oews_data


class OewsClosureBehaviors(unittest.TestCase):
    def test_given_a_completed_intake_archive_when_raw_oews_is_absent_then_the_archived_source_is_the_offline_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archived = root / "research/legacy/oesm25all.zip"
            archived.parent.mkdir(parents=True)
            archived.write_bytes(b"pinned archive")
            selected = gather_oews_data._provided_source(root, "oesm25all.zip")
        self.assertEqual(selected, archived)

    def test_given_an_all_occupations_row_and_overlapping_soc_rows_when_share_is_calculated_then_only_the_all_occupations_total_is_the_denominator(self):
        rows = [
            {"area_code": "0000000", "area_title": "U.S.", "naics": "000000", "occ_code": "00-0000", "employment": "1000"},
            {"area_code": "0000000", "area_title": "U.S.", "naics": "000000", "occ_code": "47-0000", "employment": "200"},
            {"area_code": "0000000", "area_title": "U.S.", "naics": "000000", "occ_code": "47-2111", "employment": "100"},
            {"area_code": "0000000", "area_title": "U.S.", "naics": "000000", "occ_code": "47-2152", "employment": "50"},
        ]
        result = oews.occupation_share(rows, {"47-2111", "47-2152"})
        self.assertEqual(result["denominator"], 1000.0)
        self.assertEqual(result["numerator"], 150.0)
        self.assertAlmostEqual(result["share"], 0.15)

    def test_given_a_suppressed_selected_occupation_when_share_is_calculated_then_the_area_is_flagged_incomplete_not_treated_as_zero(self):
        rows = [
            {"area_code": "01", "naics": "000000", "occ_code": "00-0000", "employment": "1000"},
            {"area_code": "01", "naics": "000000", "occ_code": "47-2111", "employment": "100"},
            {"area_code": "01", "naics": "000000", "occ_code": "47-2152", "employment": "**"},
        ]
        result = oews.occupation_share(rows, {"47-2111", "47-2152"})
        self.assertIsNone(result["share"])
        self.assertEqual(result["suppressed_selected_codes"], ["47-2152"])

    def test_given_sparse_xlsx_cells_when_parsed_then_values_remain_in_their_referenced_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse.xlsx"
            workbook = b'''<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'''
            sheet = b'''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>AREA</t></is></c><c r="C1" t="inlineStr"><is><t>OCC_CODE</t></is></c><c r="F1" t="inlineStr"><is><t>TOT_EMP</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>01</t></is></c><c r="C2" t="inlineStr"><is><t>00-0000</t></is></c><c r="F2" t="inlineStr"><is><t>1,000</t></is></c></row></sheetData></worksheet>'''
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook)
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            rows = oews.parse_oews_xlsx_rows(path)
        self.assertEqual(rows[0]["area_code"], "01")
        self.assertEqual(rows[0]["occ_code"], "00-0000")
        self.assertEqual(rows[0]["employment"], "1,000")

    def test_given_metro_and_state_shares_when_county_has_a_metro_match_then_the_bounded_metro_multiplier_is_used_and_fallback_is_reported(self):
        cbp = {"01001": {"trade_employment_per_1k": 10.0}, "01003": {"trade_employment_per_1k": 10.0}}
        result = oews.calculate_trades(
            cbp, {"01": 0.10}, 0.10,
            metro_shares={"13820": 0.20}, county_cbsa={"01001": "13820"}, industry_share=0.50,
        )
        self.assertEqual(result["01001"]["value"], 6.75)
        self.assertEqual(result["01001"]["value_status"], "derived_metro_proxy")
        self.assertEqual(result["01003"]["value"], 5.0)
        self.assertEqual(result["01003"]["value_status"], "derived_state_proxy")

    def test_given_missing_industry_share_when_trades_are_calculated_then_no_default_share_is_invented(self):
        result = oews.calculate_trades({"01001": {"trade_employment_per_1k": 10.0}}, {"01": 0.10}, 0.10)
        self.assertEqual(result, {})
