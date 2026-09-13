"""Given/When/Then scenarios for the NOAA multivariate snowfall source."""

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from live_here.factors import snowfall


class SnowfallBehaviors(unittest.TestCase):
    def test_given_annual_normal_in_inches_when_converted_then_value_is_feet(self):
        self.assertEqual(snowfall.annual_snowfall_feet("60", "15"), 5.0)

    def test_given_noaa_sentinel_or_short_support_when_converted_then_value_is_missing(self):
        self.assertIsNone(snowfall.annual_snowfall_feet("-9999", "15"))
        self.assertIsNone(snowfall.annual_snowfall_feet("60", "9"))

    def test_given_multivariate_member_when_parsed_then_station_metric_is_source_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "snow.tar.gz"
            data = ("STATION,LATITUDE,LONGITUDE,ELEVATION,ANN-SNOW-NORMAL,years_ANN-SNOW-NORMAL\n"
                    "TEST,40,-75,10,60,15\n")
            with tarfile.open(archive_path, "w:gz") as archive:
                info = tarfile.TarInfo("station.csv"); info.size = len(data.encode()); archive.addfile(info, io.BytesIO(data.encode()))
            rows, audit = snowfall.parse_noaa_multivariate_tar(archive_path)
            self.assertEqual(rows[0]["station_id"], "TEST")
            self.assertEqual(rows[0]["snowfall_feet"], 5.0)
            self.assertEqual(audit["stations_with_snowfall"], 1)
