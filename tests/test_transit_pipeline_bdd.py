"""BDD scenario for selecting EPA transit in the shared pipeline."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class TransitPipelineBDD(unittest.TestCase):
    def test_given_transit_export_when_pipeline_runs_then_source_gap_is_inferred_and_retained(self):
        # Given a source geography with one EPA-covered and one uncovered county
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            counties = root / "counties.csv"
            counties.write_text(
                "fips,name,state,geography_vintage,latitude,longitude,coordinate_vintage\n"
                "01001,Autauga County,AL,2019,0,0,2020\n"
                "01003,Baldwin County,AL,2019,0,1,2020\n"
                "01005,Barbour County,AL,2019,0,2,2020\n"
            )
            export = root / "transit.csv"
            with export.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["fips", "value", "value_status", "method", "quality_note", "observation_period"])
                writer.writeheader()
                writer.writerow({"fips": "01001", "value": 64, "value_status": "derived_source", "method": "test", "quality_note": "", "observation_period": "EPA 2013"})
                writer.writerow({"fips": "01003", "value": 32, "value_status": "derived_source", "method": "test", "quality_note": "", "observation_period": "EPA 2013"})
            sources = [{"id": "counties", "path": counties.name, "sha256": sha256(counties), "url": "https://example.test/counties", "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                       {"id": "transit", "path": export.name, "sha256": sha256(export), "url": "https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip", "vintage": "EPA 2013", "geography_vintage": "2019", "role": "source_export", "license": "EPA public data"}]
            config = {"mode": "research", "geography_source": "counties", "factors": ["transit"], "iterations": 10, "seed": 7, "adapters": {"transit": {"sources": ["transit"]}}, "sources": sources}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            # When the shared pipeline runs
            coverage = run(config_path, root / "out")
            # Then the uncovered county is inferred and the complete universe is ranked
            self.assertEqual(coverage["ranked_count"], 3)
            self.assertEqual(coverage["inference"]["per_factor"]["transit"]["inferred_count"], 1)


if __name__ == "__main__":
    unittest.main()
