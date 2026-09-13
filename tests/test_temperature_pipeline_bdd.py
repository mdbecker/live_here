"""Given/When/Then contract for exposing normalized heat/cold to the pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class TemperaturePipelineBehaviors(unittest.TestCase):
    def test_given_normalized_temperature_source_when_pipeline_runs_then_heat_is_a_rankable_factor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counties = root / "counties.csv"
            counties.write_text("fips,name,state,geography_vintage\n01001,Alpha,AL,2019\n01003,Beta,AL,2019\n")
            temperature = root / "temperature.csv"
            temperature.write_text("fips,hot_days,cold_days,value_status,method,stations_used,max_distance_km,source_vintage\n"
                                   "01001,40,120,derived_nearby,idw_inverse_square,2,50,NOAA 2006-2020 normals\n"
                                   "01003,80,100,derived_nearby,idw_inverse_square,2,50,NOAA 2006-2020 normals\n")
            config = {
                "mode": "research", "geography_source": "counties", "factors": ["heat"],
                "missing_policy": "complete_case", "iterations": 10, "seed": 42,
                "adapters": {"heat": {"sources": ["temperature"], "field": "hot_days"}},
                "sources": [
                    {"id": "counties", "path": str(counties), "sha256": sha256(counties), "url": "fixture://counties",
                     "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                    {"id": "temperature", "path": str(temperature), "sha256": sha256(temperature), "url": "fixture://temperature",
                     "vintage": "2006-2020", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                ],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            coverage = run(config_path, root / "output")
            self.assertEqual(coverage["ranked_count"], 2)
