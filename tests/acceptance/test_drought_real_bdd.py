import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DroughtRealDataBDD(unittest.TestCase):
    def test_given_the_official_usdm_download_when_acquisition_finishes_then_receipt_and_many_rows_exist(self):
        raw = ROOT / "data/raw/current/usdm-d1-plus-county-weeks.csv"
        receipt = raw.with_suffix(raw.suffix + ".source.json")
        self.assertTrue(raw.is_file())
        self.assertTrue(receipt.is_file())
        record = json.loads(receipt.read_text())
        self.assertIn("usdmdataservices.unl.edu/api", record["url"])
        self.assertGreater(record["bytes"], 1000)

    def test_given_real_usdm_rows_when_prepared_then_source_only_drought_export_has_national_coverage(self):
        audit = json.loads((ROOT / "data/interim/current/drought-audit.json").read_text())
        self.assertGreater(audit["usable_rows"], 2000)
        self.assertEqual(audit["minimum_weeks"], 0)
        self.assertIn("no old estimate calibration", audit["method"])

    def test_given_current_config_when_read_then_drought_factor_is_selected(self):
        config = json.loads((ROOT / "data/interim/current/config.json").read_text())
        self.assertIn("drought", config["factors"])
        self.assertEqual(config["adapters"]["drought"]["sources"], ["drought"])


if __name__ == "__main__":
    unittest.main()
