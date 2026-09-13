"""Acceptance behavior for the official CBP source download."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealCbpBehaviors(unittest.TestCase):
    def test_given_current_cbp_release_when_downloaded_then_raw_archive_is_pinned(self):
        raw = ROOT / "data/raw/current/cbp23co.zip"
        receipt = ROOT / "data/raw/current/cbp23co.zip.source.json"
        pop = ROOT / "data/raw/current/co-est2023-alldata.csv"
        pop_receipt = ROOT / "data/raw/current/co-est2023-alldata.csv.source.json"
        export = ROOT / "data/interim/current/cbp-source.csv"
        densities = ROOT / "data/interim/current/cbp-densities.csv"
        self.assertTrue(raw.is_file(), "download the official 2023 CBP archive first")
        self.assertTrue(receipt.is_file())
        self.assertTrue(pop.is_file())
        self.assertTrue(pop_receipt.is_file())
        self.assertTrue(export.is_file(), "normalize the CBP rows before calculating densities")
        self.assertTrue(densities.is_file(), "join CBP rows to the same-year population denominator")
