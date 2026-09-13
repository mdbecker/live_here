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
