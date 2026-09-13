"""Acceptance behavior for the downloaded NOAA annual snowfall source."""

import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealSnowfallBehaviors(unittest.TestCase):
    def test_given_current_noaa_multivariate_release_when_prepared_then_snowfall_export_is_populated(self):
        raw = ROOT / "data/raw/current/us-climate-normals_2006-2020_annualseasonal_multivariate.tar.gz"
        output = ROOT / "data/interim/current/snowfall.csv"
        self.assertTrue(raw.is_file(), "download the NOAA annual/seasonal normals archive first")
        self.assertTrue(output.is_file(), "prepare the normalized snowfall export first")
        with output.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertGreater(len(rows), 2500)
        self.assertTrue(all(float(row["snowfall_feet"]) >= 0 for row in rows))
        audit = json.loads((ROOT / "data/interim/current/snowfall-audit.json").read_text())
        self.assertGreater(audit["stations_with_snowfall"], 1000)
