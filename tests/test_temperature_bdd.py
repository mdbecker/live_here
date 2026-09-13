"""Given/When/Then scenarios for the NOAA temperature incoming file."""

import csv
import io
import math
import tarfile
import tempfile
import unittest
from pathlib import Path

from live_here.factors import temperature


class TemperatureBehaviors(unittest.TestCase):
    def station_rows(self, n=366, normal=90.0, sd=10.0):
        return [{"GHCN_ID": "TEST", "month": str((i // 31) + 1), "day": str((i % 31) + 1),
                 "DLY-TMAX-NORMAL": str(normal), "DLY-TMAX-STDDEV": str(sd)} for i in range(n)]

    def test_given_normal_at_threshold_when_expected_days_then_annualizes_to_365_25(self):
        result = temperature.expected_threshold_days(self.station_rows(), 90.0, "gte")
        self.assertAlmostEqual(result, 182.625, places=6)

    def test_given_cold_threshold_when_expected_days_then_uses_tmax_below_50(self):
        result = temperature.expected_threshold_days(self.station_rows(normal=50.0), 50.0, "lt")
        self.assertAlmostEqual(result, 182.625, places=6)

    def test_given_fewer_than_350_valid_days_when_expected_then_remain_missing(self):
        self.assertIsNone(temperature.expected_threshold_days(self.station_rows(349), 90.0, "gte"))

    def test_given_negative_noaa_sentinel_when_expected_then_exclude_it(self):
        rows = self.station_rows()
        rows[0]["DLY-TMAX-NORMAL"] = "-9999"
        self.assertIsNone(temperature.expected_threshold_days(rows[:349], 90.0, "gte"))
        self.assertAlmostEqual(temperature.expected_threshold_days(rows[1:], 90.0, "gte"), 182.625, places=3)

    def test_given_two_stations_at_one_and_two_km_when_blended_then_weights_are_inverse_square(self):
        stations = [{"station_id": "a", "x": 0.0, "y": 0.0, "hot_days": 10.0, "cold_days": 20.0},
                    {"station_id": "b", "x": 0.0, "y": 1.0, "hot_days": 20.0, "cold_days": 10.0}]
        result = temperature.blend_stations(stations, 0.0, 0.0, distance_unit="km", radius_km=125)
        self.assertAlmostEqual(result["hot_days"], 10.0)
        result = temperature.blend_stations(stations, 0.0, 0.001, distance_unit="km", radius_km=125)
        self.assertGreater(result["hot_days"], 10.0)

    def test_given_no_station_match_when_blended_then_missing_is_not_an_old_estimate(self):
        self.assertIsNone(temperature.blend_stations([], 0, 0, distance_unit="km", radius_km=125))

    def test_given_tar_with_required_noaa_members_when_parsed_then_station_metrics_are_source_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "normals.tar.gz"
            normal = "GHCN_ID,month,day,DLY-TMAX-NORMAL,DLY-TAVG-NORMAL\nTEST,1,1,90,80\n"
            std = "GHCN_ID,month,day,DLY-TMAX-STDDEV,DLY-TAVG-STDDEV\nTEST,1,1,10,10\n"
            inventory = "TEST| 40.0000| -75.0000| 10| PA| Test Station\n"
            with tarfile.open(tar_path, "w:gz") as archive:
                for name, data in (("dly-temp-normal.csv", normal), ("dly-temp-stddev.csv", std),
                                   ("dly_inventory.txt", inventory)):
                    info = tarfile.TarInfo(name); info.size = len(data.encode()); archive.addfile(info, io.BytesIO(data.encode()))
            stations, audit = temperature.parse_noaa_tar(tar_path)
            self.assertEqual(stations[0]["station_id"], "TEST")
            self.assertEqual(audit["stations_with_temperature_metrics"], 0)
