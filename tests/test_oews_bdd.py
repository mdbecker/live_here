"""Given/When/Then scenarios for the May 2025 OEWS trades refinement."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors import oews


class OewsBehaviors(unittest.TestCase):
    def test_given_selected_trade_occupations_when_summed_then_local_share_is_explicit(self):
        rows = [
            {"soc_code": "47-2111", "employment": "100", "employment_status": "reported"},
            {"soc_code": "47-2152", "employment": "50", "employment_status": "reported"},
            {"soc_code": "11-0000", "employment": "1000", "employment_status": "reported"},
        ]
        result = oews.selected_trade_share(rows, {"47-2111", "47-2152"})
        self.assertAlmostEqual(result, 150 / 1150)

    def test_given_suppressed_or_missing_occupation_when_summed_then_share_is_missing(self):
        rows = [{"soc_code": "47-2111", "employment": "**", "employment_status": "suppressed"}]
        self.assertIsNone(oews.selected_trade_share(rows, {"47-2111"}))

    def test_given_local_and_national_shares_when_adjusted_then_ratio_is_bounded(self):
        self.assertEqual(oews.bounded_ratio(0.01, 0.02), 0.65)
        self.assertEqual(oews.bounded_ratio(0.08, 0.02), 1.35)
        self.assertAlmostEqual(oews.bounded_ratio(0.03, 0.02), 1.35)

    def test_given_minimal_oews_xlsx_when_parsed_then_rows_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oews.xlsx"
            workbook = b'''<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'''
            rels = b'''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>'''
            sheet = b'''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>SOC_CODE</t></is></c><c t="inlineStr"><is><t>TOT_EMP</t></is></c></row><row><c t="inlineStr"><is><t>47-2111</t></is></c><c t="inlineStr"><is><t>100</t></is></c></row></sheetData></worksheet>'''
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook); archive.writestr("xl/_rels/workbook.xml.rels", rels); archive.writestr("xl/worksheets/sheet1.xml", sheet)
            rows = oews.parse_oews_xlsx_rows(path)
            self.assertEqual(rows[0]["soc_code"], "47-2111")
            self.assertEqual(rows[0]["employment"], "100")

    def test_given_cbp_trade_density_and_state_occupation_share_when_adjusted_then_trades_factor_is_source_derived(self):
        result = oews.calculate_trades({"01001": {"trade_employment_per_1k": 5.0}}, {"01": 0.03}, 0.02, industry_share=1.0)
        self.assertEqual(result["01001"]["value"], 6.75)
        self.assertEqual(result["01001"]["value_status"], "derived_state_proxy")

    def test_given_all_occupations_and_overlapping_rows_when_share_is_calculated_then_all_occupations_is_the_denominator(self):
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

    def test_given_suppressed_selected_occupation_when_share_is_calculated_then_area_is_incomplete(self):
        rows = [
            {"area_code": "01", "naics": "000000", "occ_code": "00-0000", "employment": "1000"},
            {"area_code": "01", "naics": "000000", "occ_code": "47-2111", "employment": "100"},
            {"area_code": "01", "naics": "000000", "occ_code": "47-2152", "employment": "**"},
        ]
        result = oews.occupation_share(rows, {"47-2111", "47-2152"})
        self.assertIsNone(result["share"])
        self.assertEqual(result["suppressed_selected_codes"], ["47-2152"])

    def test_given_sparse_xlsx_cells_when_parsed_then_values_remain_in_referenced_columns(self):
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

    def test_given_metro_and_state_shares_when_county_has_metro_match_then_metro_proxy_is_used(self):
        cbp = {"01001": {"trade_employment_per_1k": 10.0}, "01003": {"trade_employment_per_1k": 10.0}}
        result = oews.calculate_trades(
            cbp, {"01": 0.10}, 0.10,
            metro_shares={"13820": 0.20}, county_cbsa={"01001": "13820"}, industry_share=0.50,
        )
        self.assertEqual(result["01001"]["value"], 6.75)
        self.assertEqual(result["01001"]["value_status"], "derived_metro_proxy")
        self.assertEqual(result["01003"]["value"], 5.0)
        self.assertEqual(result["01003"]["value_status"], "derived_state_proxy")

    def test_given_missing_industry_share_when_trades_are_calculated_then_no_share_is_invented(self):
        result = oews.calculate_trades({"01001": {"trade_employment_per_1k": 10.0}}, {"01": 0.10}, 0.10)
        self.assertEqual(result, {})
