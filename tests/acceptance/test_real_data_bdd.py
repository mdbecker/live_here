"""Opt-in acceptance: run explicitly after gathering and running real sources.

python -m unittest discover -s tests/acceptance -v
"""
import csv
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealDataAcceptance(unittest.TestCase):
    def test_given_official_sources_when_gathered_then_all_runtime_inputs_are_pinned(self):
        path = ROOT / "data/interim/current/config.json"
        self.assertTrue(path.is_file(), "Real-source configuration has not been gathered")
        config = json.loads(path.read_text())
        self.assertEqual(config["mode"], "research")
        self.assertEqual(set(config["factors"]), {"aqi", "walkability", "heat", "cold", "snowfall", "tradespeople", "groceries", "hazard_burden", "resilience", "drought", "transit", "housing"})
        for source in config["sources"]:
            local = (path.parent / source["path"]).resolve()
            self.assertTrue(local.is_file())
            self.assertEqual(hashlib.sha256(local.read_bytes()).hexdigest(), source["sha256"])
            self.assertNotEqual(source["role"], "fixture")
            self.assertTrue(source["url"].startswith("https://"))
            if source["role"] == "raw_source":
                self.assertTrue(source.get("raw_parent_sha256"))

    def test_given_real_national_inputs_when_pipeline_runs_then_coverage_and_wins_reconcile(self):
        folder = ROOT / "outputs/current-real-closure-final"
        self.assertTrue((folder / "coverage.json").is_file(), "No real-source pipeline run exists")
        coverage = json.loads((folder / "coverage.json").read_text())
        self.assertEqual(coverage["mode"], "research")
        self.assertGreater(coverage["universe_count"], 3000)
        self.assertGreater(coverage["ranked_count"], 250)
        self.assertEqual(coverage["universe_count"], coverage["ranked_count"] + len(coverage["excluded_fips"]))
        with (folder / "rankings.csv").open() as stream:
            rankings = list(csv.DictReader(stream))
        manifest = json.loads((folder / "run-manifest.json").read_text())
        current_config_hash = hashlib.sha256((ROOT / "data/interim/current/config.json").read_bytes()).hexdigest()
        current_pipeline_hash = hashlib.sha256((ROOT / "src/live_here/pipeline.py").read_bytes()).hexdigest()
        self.assertEqual(manifest["config_sha256"], current_config_hash)
        self.assertEqual(manifest["code_sha256"]["pipeline.py"], current_pipeline_hash)
        self.assertEqual(len(rankings), coverage["ranked_count"])
        self.assertEqual(sum(int(r["wins"]) for r in rankings), manifest["config"]["iterations"])
        self.assertTrue(all(len(r["fips"]) == 5 for r in rankings))
        self.assertIn("tradespeople", coverage["selected_factors"])
        self.assertGreater(coverage["per_factor"]["tradespeople"].get("derived_state_proxy", 0), 2000)
        self.assertGreater(coverage["per_factor"]["groceries"].get("derived_usda_access_adjusted", 0), 2000)
        self.assertGreater(coverage["per_factor"]["hazard_burden"].get("derived_source", 0), 3000)
        self.assertGreater(coverage["per_factor"]["resilience"].get("derived_source", 0), 3000)
        self.assertGreater(coverage["per_factor"]["drought"].get("derived_source", 0), 3000)
        self.assertGreater(coverage["per_factor"]["housing"].get("derived_source", 0), 2500)
        self.assertGreater(coverage["per_factor"]["transit"].get("derived_source", 0), 500)


if __name__ == "__main__":
    unittest.main()
