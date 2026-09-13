"""Acceptance BDD scenarios against the downloaded official EPA transit DBF."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TransitRealDataBDD(unittest.TestCase):
    def test_given_official_epa_archive_when_prepared_then_receipt_and_coverage_are_preserved(self):
        # Given the archive downloaded by gather_transit_data.py
        raw = ROOT / "data/raw/current/SLD_Trans45_DBF.zip"
        receipt = json.loads((raw.with_suffix(raw.suffix + ".source.json")).read_text())
        audit = json.loads((ROOT / "data/interim/current/transit-audit.json").read_text())
        export = ROOT / "data/interim/current/transit.csv"
        # Then its endpoint, hash, and observed source coverage are explicit
        self.assertEqual(receipt["url"], "https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip")
        self.assertEqual(receipt["sha256"], "d77e64df11f4722e68aed86e709ac86724c90bc475f90f75ac2664c8ecb7dd70")
        self.assertGreater(receipt["bytes"], 8_000_000)
        self.assertEqual(audit["records_read"], 126228)
        self.assertEqual(audit["covered_counties"], 532)
        with export.open() as stream:
            self.assertEqual(sum(1 for _ in stream) - 1, 530)

    def test_given_current_real_run_when_transit_is_selected_then_missing_source_coverage_is_reported(self):
        # Given the source-only national run including the recovered V1 factors
        coverage = json.loads((ROOT / "outputs/coverage.json").read_text())
        # Then transit is selected and its incomplete source coverage remains visible
        self.assertIn("transit", coverage["selected_factors"])
        self.assertEqual(coverage["per_factor"]["transit"]["derived_source"], 530)
        self.assertGreater(coverage["per_factor"]["transit"]["missing"], 2000)

    def test_given_transit_export_when_manifested_then_source_and_target_geographies_are_distinguished(self):
        config = json.loads((ROOT / "data/interim/current/config.json").read_text())
        source = next(item for item in config["sources"] if item["id"] == "transit")
        self.assertIn("source_geography_vintage", source)
        self.assertIn("geography_harmonization", source)


if __name__ == "__main__":
    unittest.main()
