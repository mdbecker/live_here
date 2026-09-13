"""Acceptance behavior for official May 2025 OEWS archives."""

import unittest
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealOewsBehaviors(unittest.TestCase):
    def test_given_may_2025_oews_release_when_gathered_then_four_source_archives_are_pinned_and_the_recovered_cohorts_are_used(self):
        for name in ("oesm25all.zip", "oesm25st.zip", "oesm25ma.zip", "oesm25in4.zip"):
            self.assertTrue((ROOT / "data/raw/current" / name).is_file(), f"missing {name}")
            self.assertTrue((ROOT / "data/raw/current" / f"{name}.source.json").is_file())
        normalized = ROOT / "data/interim/current/oews-national.csv"
        self.assertTrue(normalized.is_file(), "normalize the supplied OEWS workbook before calculating shares")
        shares = ROOT / "data/interim/current/oews-state-shares.csv"
        self.assertTrue(shares.is_file())
        with shares.open(newline="") as stream:
            self.assertGreater(len(list(csv.DictReader(stream))), 45)
        audit = json.loads((ROOT / "data/interim/current/oews-audit.json").read_text())
        self.assertEqual(audit["national_cohort_rows"], 10)
        self.assertGreater(audit["metro_share_count"], 200)
        self.assertGreater(audit["industry_naics_238"]["share"], 0)
        self.assertGreater(audit["trade_status_counts"]["derived_metro_proxy"], 100)
