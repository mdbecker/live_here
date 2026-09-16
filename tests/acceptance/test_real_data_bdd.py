"""Opt-in acceptance: run explicitly after gathering and running real sources.

python -m unittest discover -s tests/acceptance -v
"""
import csv
import hashlib
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealDataAcceptance(unittest.TestCase):
    def test_given_official_sources_when_gathered_then_all_runtime_inputs_are_pinned(self):
        path = ROOT / "data/interim/current/config.json"
        self.assertTrue(path.is_file(), "Real-source configuration has not been gathered")
        config = json.loads(path.read_text())
        self.assertEqual(config["mode"], "research")
        self.assertEqual(set(config["factors"]), {"aqi", "walkability", "heat", "cold", "snowfall", "tradespeople", "groceries", "specialty_groceries", "hazard_burden", "resilience", "drought", "transit", "housing"})
        for source in config["sources"]:
            local = (path.parent / source["path"]).resolve()
            self.assertTrue(local.is_file())
            self.assertEqual(hashlib.sha256(local.read_bytes()).hexdigest(), source["sha256"])
            self.assertNotEqual(source["role"], "fixture")
            self.assertTrue(source["url"].startswith(("https://", "project://")))
            if source["role"] == "raw_source":
                self.assertTrue(source.get("raw_parent_sha256"))
        county_source = next(source for source in config["sources"] if source["id"] == "counties")
        self.assertIn("centers", county_source["raw_parent_sha256"])
        for factor_source_id in ("temperature", "snowfall"):
            factor_source = next(source for source in config["sources"] if source["id"] == factor_source_id)
            self.assertTrue({"counties", "centers"} <= set(factor_source["raw_parent_sha256"]))
        with (ROOT / "data/interim/current/counties.csv").open(newline="") as stream:
            self.assertEqual(next(csv.reader(stream)), [
                "fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage",
            ])

    def test_given_real_national_inputs_when_pipeline_runs_then_coverage_and_wins_reconcile(self):
        folder = ROOT / "outputs"
        self.assertTrue((folder / "coverage.json").is_file(), "No real-source pipeline run exists")
        coverage = json.loads((folder / "coverage.json").read_text())
        self.assertEqual(coverage["mode"], "research")
        self.assertGreater(coverage["universe_count"], 3000)
        self.assertEqual(coverage["universe_count"], 3220)
        self.assertEqual(coverage["ranked_count"], 3220)
        self.assertEqual(coverage["inference"]["counties_with_inference"] + coverage["inference"]["counties_without_inference"], 3220)
        with (folder / "rankings.csv").open() as stream:
            rankings = list(csv.DictReader(stream))
        with (folder / "factors.csv").open() as stream:
            factors = list(csv.DictReader(stream))
        with (folder / "county_rankings.csv").open() as stream:
            county_rankings = list(csv.DictReader(stream))
        manifest = json.loads((folder / "run-manifest.json").read_text())
        current_config_hash = hashlib.sha256((ROOT / "data/interim/current/config.json").read_bytes()).hexdigest()
        current_pipeline_hash = hashlib.sha256((ROOT / "src/live_here/pipeline.py").read_bytes()).hexdigest()
        self.assertEqual(manifest["config_sha256"], current_config_hash)
        self.assertEqual(manifest["code_sha256"]["pipeline.py"], current_pipeline_hash)
        self.assertEqual(len(rankings), coverage["ranked_count"])
        self.assertEqual(len(county_rankings), 3220)
        self.assertEqual(len(factors), 3220 * len(coverage["selected_factors"]))
        self.assertTrue(all(row["value_status"] != "missing" for row in factors))
        inferred_codes_by_factor = {}
        for factor in coverage["selected_factors"]:
            rows = [row for row in factors if row["factor"] == factor]
            inferred_codes = {row["fips"] for row in rows if row["is_inferred"] == "true"}
            inferred_codes_by_factor[factor] = inferred_codes
            self.assertEqual(len(rows), 3220)
            for row in rows:
                if row["is_inferred"] == "true":
                    self.assertTrue(math.isfinite(float(row["value"])))
                    if factor == "specialty_groceries":
                        self.assertEqual(row["value_status"], "inferred_zero")
                        self.assertEqual(row["method"], "workbook_proxy_lower_bound_zero_fill")
                    else:
                        self.assertEqual(row["value_status"], "inferred_geographic_idw")
                        self.assertEqual(row["method"], "geographic_idw_k5_p2")
                        donors = row["inference_donor_fips"].split(";")
                        self.assertTrue(2 <= len(donors) <= 5)
                        self.assertTrue(all(donor not in inferred_codes for donor in donors))
                        self.assertTrue(row["nearest_donor_km"] and row["farthest_donor_km"])
        presentation_by_fips = {row["fips"]: row for row in county_rankings}
        composite_fields = {"runoff_rank", "average_factor_rank", "average_based_rank", "mean_elimination_round", "wins", "win_rate"}
        for ranking in rankings:
            row = presentation_by_fips[ranking["fips"]]
            inferred = set(ranking["inferred_factors"].split(";")) if ranking["inferred_factors"] else set()
            self.assertEqual(bool(inferred), row["name"].endswith("*"))
            self.assertFalse(row["fips"].endswith("*"))
            self.assertFalse(row["state"].endswith("*"))
            self.assertFalse(row["inferred_factors"].endswith("*"))
            for field in composite_fields:
                self.assertEqual(bool(inferred), row[field].endswith("*"))
            for factor in coverage["selected_factors"]:
                self.assertEqual(factor in inferred, row[factor].endswith("*"))
                self.assertEqual(factor in inferred, row[f"{factor}_rank"].endswith("*"))
        self.assertEqual(sum(int(r["wins"]) for r in rankings), manifest["config"]["iterations"])
        self.assertTrue(all(len(r["fips"]) == 5 for r in rankings))
        self.assertIn("tradespeople", coverage["selected_factors"])
        self.assertIn("specialty_groceries", coverage["selected_factors"])
        self.assertEqual(coverage["per_factor"]["specialty_groceries"].get("derived_workbook_proxy"), 319)
        self.assertEqual(coverage["per_factor"]["specialty_groceries"].get("inferred_zero"), 2901)
        self.assertGreater(coverage["per_factor"]["tradespeople"].get("derived_state_proxy", 0), 2000)
        self.assertGreater(coverage["per_factor"]["groceries"].get("derived_usda_access_adjusted", 0), 2000)
        self.assertGreater(coverage["per_factor"]["hazard_burden"].get("derived_source", 0), 3000)
        self.assertGreater(coverage["per_factor"]["resilience"].get("derived_source", 0), 3000)
        self.assertGreater(coverage["per_factor"]["drought"].get("derived_source", 0), 3000)
        self.assertGreater(coverage["per_factor"]["housing"].get("derived_source", 0), 2500)
        self.assertGreater(coverage["per_factor"]["transit"].get("derived_source", 0), 500)


if __name__ == "__main__":
    unittest.main()
