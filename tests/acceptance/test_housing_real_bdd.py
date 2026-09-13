"""Acceptance BDD scenarios for the downloaded Zillow three-bedroom ZHVI."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HousingRealDataBDD(unittest.TestCase):
    def test_given_zillow_county_release_when_prepared_then_receipt_and_month_are_pinned(self):
        raw = ROOT / "data/raw/current/County_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
        receipt = json.loads((raw.with_suffix(raw.suffix + ".source.json")).read_text())
        audit = json.loads((ROOT / "data/interim/current/housing-audit.json").read_text())
        self.assertTrue(raw.is_file())
        self.assertEqual(receipt["sha256"], "2be1a7da5e652dcda42e798eea3f8939db5bd3f1b6bb151a495d72ca2c76f192")
        self.assertEqual(audit["observation_month"], "2026-07-31")
        self.assertGreater(audit["matched_counties"], 2500)

    def test_given_current_real_run_when_housing_is_selected_then_dollar_values_remain_source_derived(self):
        coverage = json.loads((ROOT / "outputs/coverage.json").read_text())
        self.assertIn("housing", coverage["selected_factors"])
        self.assertGreater(coverage["per_factor"]["housing"].get("derived_source", 0), 2500)


if __name__ == "__main__":
    unittest.main()
