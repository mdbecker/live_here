"""BDD scenario for selecting both FEMA composites in the ranking pipeline."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class FEMAPipelineBDD(unittest.TestCase):
    def test_given_fema_exports_when_pipeline_runs_then_both_factors_are_ranked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            counties = root / "counties.csv"
            with counties.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["fips", "name", "state", "geography_vintage"])
                writer.writeheader()
                writer.writerows([
                    {"fips": "01001", "name": "Autauga County", "state": "AL", "geography_vintage": "2019"},
                    {"fips": "01003", "name": "Baldwin County", "state": "AL", "geography_vintage": "2019"},
                ])
            exports = {}
            for factor, vals in {"hazard_burden": [20, 80], "resilience": [80, 20]}.items():
                path = root / f"{factor}.csv"
                with path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["fips", "value", "value_status", "method", "quality_note", "observation_period"])
                    writer.writeheader()
                    for fips, value in zip(("01001", "01003"), vals):
                        writer.writerow({"fips": fips, "value": value, "value_status": "derived_source", "method": "test", "quality_note": "", "observation_period": "FEMA NRI v1.20"})
                exports[factor] = path
            sources = [{"id": "counties", "path": "counties.csv", "sha256": sha256(counties), "url": "https://example.test/counties", "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"}]
            for factor, path in exports.items():
                sources.append({"id": factor, "path": path.name, "sha256": sha256(path), "url": "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0", "vintage": "FEMA NRI v1.20", "geography_vintage": "2019", "role": "source_export", "license": "FEMA public data"})
            config = {"mode": "research", "geography_source": "counties", "factors": ["hazard_burden", "resilience"], "missing_policy": "complete_case", "iterations": 20, "seed": 7, "adapters": {"hazard_burden": {"sources": ["hazard_burden"]}, "resilience": {"sources": ["resilience"]}}, "sources": sources}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            coverage = run(config_path, root / "out")
            self.assertEqual(coverage["ranked_count"], 2)
            self.assertEqual(coverage["selected_factors"], ["hazard_burden", "resilience"])


if __name__ == "__main__":
    unittest.main()
