"""Given/When/Then contract for selecting housing in the source-only pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class HousingPipelineBehaviors(unittest.TestCase):
    def test_given_normalized_housing_source_when_pipeline_runs_then_zhvi_is_rankable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counties = root / "counties.csv"
            counties.write_text("fips,name,state,geography_vintage\n01001,Alpha,AL,2019\n01003,Beta,AL,2019\n")
            source = root / "housing.csv"
            source.write_text("fips,value,value_status,method,observation_period,unit\n01001,100000,derived_source,Zillow county three-bedroom ZHVI,2025-02-28,USD\n01003,200000,derived_source,Zillow county three-bedroom ZHVI,2025-02-28,USD\n")
            config = {"mode": "research", "geography_source": "counties", "factors": ["housing"], "missing_policy": "complete_case", "iterations": 10, "seed": 42,
                      "adapters": {"housing": {"sources": ["housing"]}}, "sources": [
                          {"id": "counties", "path": str(counties), "sha256": sha256(counties), "url": "fixture://counties", "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                          {"id": "housing", "path": str(source), "sha256": sha256(source), "url": "fixture://housing", "vintage": "2025-02-28", "geography_vintage": "2019", "role": "source_export", "license": "fixture"}]}
            path = root / "config.json"
            path.write_text(json.dumps(config))
            self.assertEqual(run(path, root / "output")["ranked_count"], 2)
