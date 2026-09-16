"""Given/When/Then contract for the source-only grocery factor."""

import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import _normalized_factor, run


class GroceryPipelineBehaviors(unittest.TestCase):
    def test_given_normalized_grocery_source_when_pipeline_runs_then_factor_is_rankable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counties = root / "counties.csv"; counties.write_text("fips,name,state,geography_vintage,latitude,longitude,coordinate_vintage\n01001,Alpha,AL,2019,0,0,2020\n01003,Beta,AL,2019,0,1,2020\n")
            source = root / "grocery.csv"; source.write_text("fips,value,value_status,method,observation_period\n01001,3.2,derived_usda_access_adjusted,usda_bounded,2023\n01003,4.1,derived_usda_access_adjusted,usda_bounded,2023\n")
            config = {"mode":"research","geography_source":"counties","factors":["groceries"],"iterations":10,"seed":42,
                      "adapters":{"groceries":{"sources":["groceries"]}},"sources":[
                          {"id":"counties","path":str(counties),"sha256":sha256(counties),"url":"fixture://counties","vintage":"2019","geography_vintage":"2019","role":"source_export","license":"fixture"},
                          {"id":"groceries","path":str(source),"sha256":sha256(source),"url":"fixture://groceries","vintage":"2023","geography_vintage":"2019","role":"source_export","license":"fixture"}]}
            path = root / "config.json"; path.write_text(json.dumps(config)); self.assertEqual(run(path, root / "output")["ranked_count"], 2)

    def test_given_normalized_rows_outside_target_geography_when_read_then_their_fips_are_audited(self):
        """Given an unharmonized source row, when normalized, then its identifier is retained in the audit."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "grocery.csv"
            source.write_text("fips,value\n01001,3.2\n99999,4.1\n")
            _, audit = _normalized_factor(source, {"01001": {}})
        self.assertEqual(audit["outside_universe_fips"], ["99999"])
