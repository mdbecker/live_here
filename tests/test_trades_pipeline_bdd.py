"""Given/When/Then contract for the source-only trades factor."""

import json
import tempfile
import unittest
from pathlib import Path

from live_here.io import sha256
from live_here.pipeline import run


class TradesPipelineBehaviors(unittest.TestCase):
    def test_given_normalized_trades_source_when_pipeline_runs_then_factor_is_rankable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counties = root / "counties.csv"; counties.write_text("fips,name,state,geography_vintage,latitude,longitude,coordinate_vintage\n01001,Alpha,AL,2019,0,0,2020\n01003,Beta,AL,2019,0,1,2020\n")
            source = root / "trades.csv"; source.write_text("fips,value,value_status,method,observation_period\n01001,6.75,derived_state_proxy,oews_state_adjusted,2023\n01003,4.0,derived_state_proxy,oews_state_adjusted,2023\n")
            config = {"mode":"research","geography_source":"counties","factors":["tradespeople"],"iterations":10,"seed":42,
                      "adapters":{"tradespeople":{"sources":["trades"]}},"sources":[
                          {"id":"counties","path":str(counties),"sha256":sha256(counties),"url":"fixture://counties","vintage":"2019","geography_vintage":"2019","role":"source_export","license":"fixture"},
                          {"id":"trades","path":str(source),"sha256":sha256(source),"url":"fixture://trades","vintage":"2023","geography_vintage":"2019","role":"source_export","license":"fixture"}]}
            path = root / "config.json"; path.write_text(json.dumps(config)); self.assertEqual(run(path, root / "output")["ranked_count"], 2)
