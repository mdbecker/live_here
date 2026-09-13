"""Given/When/Then scenarios for source-only Zillow three-bedroom ZHVI."""

import tempfile
import unittest
from pathlib import Path

from live_here.factors import housing


class HousingBehaviors(unittest.TestCase):
    def test_given_county_csv_when_month_is_selected_then_all_values_use_one_explicit_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "county-zhvi.csv"
            path.write_text(
                "RegionType,StateCodeFIPS,MunicipalCodeFIPS,RegionName,2025-01-31,2025-02-28\n"
                "county,01,001,Alpha County,100000,110000\n"
                "county,01,003,Beta County,200000,\n"
                "state,01,,Alabama,300000,310000\n",
                encoding="utf-8",
            )
            rows, month, audit = housing.read_zillow_county_csv(path, observation_month="2025-02-28")
            self.assertEqual(month, "2025-02-28")
            self.assertEqual(rows["01001"]["value"], 110000.0)
            self.assertIsNone(rows["01003"]["value"])
            self.assertEqual(audit["county_rows"], 2)

    def test_given_missing_zhvi_when_factor_is_calculated_then_missing_stays_missing(self):
        rows = {
            "01001": {"fips": "01001", "value": 100000.0, "month": "2025-02-28"},
            "01003": {"fips": "01003", "value": None, "month": "2025-02-28"},
        }
        result, audit = housing.calculate(rows, observation_month="2025-02-28")
        self.assertEqual(result["01001"]["value"], 100000.0)
        self.assertEqual(result["01001"]["unit"], "USD")
        self.assertNotIn("01003", result)
        self.assertEqual(audit["missing_count"], 1)

    def test_given_zhvi_values_when_factor_is_calculated_then_dollars_are_not_mapped_to_legacy_scale(self):
        rows = {
            "01001": {"fips": "01001", "value": 100000.0, "month": "2025-02-28"},
            "01003": {"fips": "01003", "value": 200000.0, "month": "2025-02-28"},
        }
        result, _ = housing.calculate(rows, observation_month="2025-02-28")
        self.assertEqual(result["01001"]["value"], 100000.0)
        self.assertEqual(result["01003"]["value"], 200000.0)
        self.assertEqual(result["01003"]["method"], "Zillow county three-bedroom ZHVI")
