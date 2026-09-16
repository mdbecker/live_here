"""Given/When/Then contract for exposing normalized snowfall to the pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class SnowfallPipelineBehaviors(unittest.TestCase):
    def test_given_normalized_snowfall_source_when_pipeline_runs_then_snowfall_is_rankable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counties = root / "counties.csv"
            counties.write_text("fips,name,state,geography_vintage,latitude,longitude,coordinate_vintage\n01001,Alpha,AL,2019,0,0,2020\n01003,Beta,AL,2019,0,1,2020\n")
            snow = root / "snowfall.csv"
            snow.write_text("fips,snowfall_feet,value_status,method,stations_used,max_distance_km,source_vintage\n"
                            "01001,1.2,derived_nearby,idw_inverse_square,2,50,NOAA 2006-2020 normals\n"
                            "01003,4.8,derived_nearby,idw_inverse_square,2,50,NOAA 2006-2020 normals\n")
            config = {"mode": "research", "geography_source": "counties", "factors": ["snowfall"],
                      "iterations": 10, "seed": 42,
                      "adapters": {"snowfall": {"sources": ["snowfall"]}},
                      "sources": [{"id": "counties", "path": str(counties), "sha256": sha256(counties), "url": "fixture://counties",
                                   "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                                  {"id": "snowfall", "path": str(snow), "sha256": sha256(snow), "url": "fixture://snowfall",
                                   "vintage": "2006-2020", "geography_vintage": "2019", "role": "source_export", "license": "fixture"}]}
            config_path = root / "config.json"; config_path.write_text(json.dumps(config))
            self.assertEqual(run(config_path, root / "output")["ranked_count"], 2)
