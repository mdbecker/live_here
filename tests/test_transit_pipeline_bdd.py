"""BDD scenario for selecting EPA transit in the shared pipeline."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class TransitPipelineBDD(unittest.TestCase):
    def test_given_transit_export_when_pipeline_runs_then_transit_is_ranked_and_missing_is_retained(self):
        # Given a source geography with one EPA-covered and one uncovered county
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
            export = root / "transit.csv"
            with export.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["fips", "value", "value_status", "method", "quality_note", "observation_period"])
                writer.writeheader()
                writer.writerow({"fips": "01001", "value": 64, "value_status": "derived_source", "method": "test", "quality_note": "", "observation_period": "EPA 2013"})
            sources = [{"id": "counties", "path": counties.name, "sha256": sha256(counties), "url": "https://example.test/counties", "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                       {"id": "transit", "path": export.name, "sha256": sha256(export), "url": "https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip", "vintage": "EPA 2013", "geography_vintage": "2019", "role": "source_export", "license": "EPA public data"}]
            config = {"mode": "research", "geography_source": "counties", "factors": ["transit"], "missing_policy": "complete_case", "iterations": 10, "seed": 7, "adapters": {"transit": {"sources": ["transit"]}}, "sources": sources}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            # When the shared pipeline runs
            coverage = run(config_path, root / "out")
            # Then the observed county is ranked while the uncovered county remains excluded
            self.assertEqual(coverage["ranked_count"], 1)
            self.assertEqual(coverage["excluded_fips"], ["01003"])


if __name__ == "__main__":
    unittest.main()
