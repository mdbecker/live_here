"""Acceptance behavior for the downloaded NOAA temperature source."""

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RealTemperatureBehaviors(unittest.TestCase):
    def test_given_current_noaa_release_when_prepared_then_source_export_has_heat_and_cold(self):
        raw = ROOT / "data/raw/current/us-climate-normals_2006-2020_daily_temperature.tar.gz"
        centers = ROOT / "data/raw/current/CenPop2020_Mean_CO.txt"
        output = ROOT / "data/interim/current/temperature.csv"
        self.assertTrue(raw.is_file(), "download the NOAA normals archive first")
        self.assertTrue(centers.is_file(), "download Census population centers first")
        self.assertTrue(output.is_file(), "prepare the normalized temperature export first")
        with output.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertGreater(len(rows), 3000)
        self.assertTrue({"fips", "hot_days", "cold_days", "value_status", "source_vintage"}.issubset(rows[0]))
        self.assertTrue(all(row["hot_days"] and row["cold_days"] for row in rows))
        audit = json.loads((ROOT / "data/interim/current/temperature-audit.json").read_text())
        self.assertGreater(audit["stations_with_temperature_metrics"], 1000)
