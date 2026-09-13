"""Acceptance behavior for the official USDA Food Environment Atlas."""

import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealUsdaBehaviors(unittest.TestCase):
    def test_given_current_usda_release_when_prepared_then_grocery_export_is_populated(self):
        raw = ROOT / "data/raw/current/food-environment-atlas-csv-files.zip"
        output = ROOT / "data/interim/current/grocery.csv"
        self.assertTrue(raw.is_file(), "download the USDA Atlas archive first")
        self.assertTrue(output.is_file(), "prepare the access-adjusted grocery export first")
        with output.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertGreater(len(rows), 2000)
        audit = json.loads((ROOT / "data/interim/current/usda-audit.json").read_text())
        self.assertGreater(audit["matched_counties"], 2000)
        self.assertEqual(audit["percentile_cohort"], "national_usda_fea_rows_with_all_three_2019_access_indicators")
        self.assertEqual(audit["percentile_cohort_count"], 2989)
        self.assertEqual(audit["access_indicator_observation_period"], "2019")
        self.assertEqual(audit["base_observation_period"], "2023")
        self.assertEqual(rows[0]["observation_period"], "USDA access indicators 2019; CBP business and population 2023")
        config = json.loads((ROOT / "data/interim/current/config.json").read_text())
        self.assertIn("groceries", config["factors"])

    def test_given_grocery_export_when_manifested_then_all_input_parents_are_pinned(self):
        config = json.loads((ROOT / "data/interim/current/config.json").read_text())
        source = next(item for item in config["sources"] if item["id"] == "groceries")
        self.assertTrue(
            {"usda", "cbp23co.zip", "co-est2023-alldata.csv"}
            <= set(source["raw_parent_sha256"]),
            "the derived grocery export must pin USDA, CBP, and population inputs",
        )
