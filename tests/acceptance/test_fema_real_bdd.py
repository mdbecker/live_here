"""Network acceptance scenarios for the downloaded FEMA NRI release."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class FEMARealDataBDD(unittest.TestCase):
    def test_given_fema_source_when_downloaded_then_receipt_and_national_rows_exist(self):
        raw = ROOT / "data/raw/current/fema-nri-counties.csv"
        receipt = ROOT / "data/raw/current/fema-nri-counties.csv.source.json"
        self.assertTrue(raw.is_file())
        self.assertTrue(receipt.is_file())
        self.assertGreater(json.loads(receipt.read_text())["records"], 3000)

    def test_given_fema_source_when_processed_then_both_composites_cover_nationwide_cohort(self):
        audit = json.loads((ROOT / "data/interim/current/fema-audit.json").read_text())
        self.assertEqual(audit["release"], "FEMA NRI v1.20 (December 2025)")
        self.assertGreater(audit["burden_rows"], 3000)
        self.assertGreater(audit["resilience_rows"], 3000)

    def test_given_current_config_when_read_then_fema_factors_are_selected(self):
        config = json.loads((ROOT / "data/interim/current/config.json").read_text())
        self.assertIn("hazard_burden", config["factors"])
        self.assertIn("resilience", config["factors"])

    def test_given_current_factor_real_run_when_read_then_fema_factors_have_source_coverage(self):
        coverage = json.loads((ROOT / "outputs/coverage.json").read_text())
        self.assertIn("hazard_burden", coverage["selected_factors"])
        self.assertIn("resilience", coverage["selected_factors"])
        self.assertGreater(coverage["ranked_count"], 250)
        self.assertGreater(coverage["adapter_audits"]["hazard_burden"]["matched_counties"], 3000)


if __name__ == "__main__":
    unittest.main()
