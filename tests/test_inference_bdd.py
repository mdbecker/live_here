"""Given/When/Then scenarios for PRD-2 geographic inference and outputs."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from live_here.inference import EARTH_RADIUS_KM, haversine_km, infer_missing
from live_here.io import sha256
from live_here.pipeline import run


def county(code, lat, lon, name=None):
    return {
        "fips": code,
        "name": name or f"County {code}",
        "state": "AL",
        "geography_vintage": "2019",
        "latitude": str(lat),
        "longitude": str(lon),
        "coordinate_vintage": "2020",
    }


class GeographicInferenceBDD(unittest.TestCase):
    def test_given_known_donors_when_interpolated_then_hand_calculable_idw_is_used(self):
        counties = {
            "00001": county("00001", 0, 0),
            "00002": county("00002", 0, 1),
            "00003": county("00003", 0, 2),
        }
        observations = {
            "00002": {"value": 10, "value_status": "derived_source"},
            "00003": {"value": 30, "value_status": "derived_source"},
        }
        result = infer_missing(counties, observations)
        self.assertEqual(result["00001"]["value"], 14.0)
        self.assertEqual(EARTH_RADIUS_KM, 6371.0088)

    def test_given_one_equatorial_degree_when_distance_is_calculated_then_haversine_is_about_111_19508_km(self):
        self.assertAlmostEqual(haversine_km(0, 0, 0, 1), 111.19508, places=4)

    def test_given_more_than_five_donors_when_inferred_then_only_five_nearest_are_used(self):
        counties = {"00001": county("00001", 0, 0)}
        observations = {}
        for index in range(2, 9):
            code = f"{index:05d}"
            counties[code] = county(code, 0, index)
            observations[code] = {"value": float(index), "value_status": "derived_source"}
        result = infer_missing(counties, observations)
        self.assertEqual(result["00001"]["inference_donor_fips"], "00002;00003;00004;00005;00006")
        self.assertEqual(result["00001"]["farthest_donor_km"], haversine_km(0, 0, 0, 6))

    def test_given_equal_distance_donors_when_inferred_then_lower_fips_breaks_ties(self):
        counties = {
            "00001": county("00001", 0, 0),
            "00002": county("00002", 0, -1),
            "00003": county("00003", 0, 1),
            "00004": county("00004", 0, 2),
        }
        observations = {
            "00002": {"value": 2, "value_status": "derived_source"},
            "00003": {"value": 3, "value_status": "derived_source"},
            "00004": {"value": 4, "value_status": "derived_source"},
        }
        result = infer_missing(counties, observations)
        self.assertEqual(result["00001"]["inference_donor_fips"], "00002;00003;00004")

    def test_given_three_donors_when_inferred_then_all_three_are_used(self):
        counties = {"00001": county("00001", 0, 0)}
        observations = {}
        for index in range(2, 5):
            code = f"{index:05d}"
            counties[code] = county(code, 0, index)
            observations[code] = {"value": float(index), "value_status": "derived_source"}
        result = infer_missing(counties, observations)
        self.assertEqual(result["00001"]["inference_donor_fips"], "00002;00003;00004")

    def test_given_fewer_than_two_donors_when_inference_runs_then_it_fails(self):
        counties = {"00001": county("00001", 0, 0), "00002": county("00002", 0, 1)}
        observations = {"00002": {"value": 2, "value_status": "derived_source"}}
        with self.assertRaisesRegex(ValueError, "two pre-inference donors"):
            infer_missing(counties, observations)

    def test_given_two_missing_counties_when_inference_runs_then_synthetic_values_never_donate(self):
        counties = {f"{index:05d}": county(f"{index:05d}", 0, index) for index in range(1, 5)}
        observations = {
            "00001": {"value": 1, "value_status": "derived_source"},
            "00002": {"value": 2, "value_status": "derived_source"},
        }
        result = infer_missing(counties, observations)
        self.assertEqual(result["00003"]["inference_donor_fips"], "00002;00001")
        self.assertEqual(result["00004"]["inference_donor_fips"], "00002;00001")
        self.assertNotIn("00003", result["00004"]["inference_donor_fips"])

    def test_given_existing_value_when_inference_runs_then_source_observation_is_preserved(self):
        counties = {"00001": county("00001", 0, 0), "00002": county("00002", 0, 1), "00003": county("00003", 0, 2)}
        observations = {
            "00001": {"value": 10, "value_status": "derived_state_proxy", "method": "proxy"},
            "00002": {"value": 20, "value_status": "derived_source"},
        }
        result = infer_missing(counties, observations)
        self.assertEqual(result["00001"], observations["00001"])


class PipelineInferenceOutputBDD(unittest.TestCase):
    def make_fixture(self, root):
        counties = root / "counties.csv"
        with counties.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage",
            ])
            writer.writeheader()
            writer.writerows([
                county("01001", 0, 0, "Alpha"),
                county("01003", 0, 1, "Beta"),
                county("01005", 0, 2, "Gamma"),
            ])
        factor = root / "factor.csv"
        factor.write_text(
            "fips,value,value_status,method,quality_note,observation_period\n"
            "01001,10,derived_source,fixture,,2020\n"
            "01003,20,derived_state_proxy,proxy,,2021\n"
        )
        config = {
            "mode": "research", "geography_source": "counties", "factors": ["housing"],
            "iterations": 10, "seed": 42,
            "adapters": {"housing": {"sources": ["housing"]}},
            "sources": [
                {"id": "counties", "path": str(counties), "sha256": sha256(counties), "url": "fixture://counties",
                 "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                {"id": "housing", "path": str(factor), "sha256": sha256(factor), "url": "fixture://housing",
                 "vintage": "2021", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
            ],
        }
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config))
        return config_path

    def test_given_missing_source_observation_when_pipeline_runs_then_all_counties_are_ranked_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            coverage = run(self.make_fixture(Path(tmp)), output)
            self.assertEqual(coverage["ranked_count"], coverage["universe_count"])
            with (output / "factors.csv").open(newline="") as stream:
                factors = list(csv.DictReader(stream))
            inferred = next(row for row in factors if row["fips"] == "01005")
            self.assertEqual(inferred["value_status"], "inferred_geographic_idw")
            self.assertEqual(inferred["is_inferred"], "true")
            self.assertEqual(inferred["inference_donor_fips"], "01003;01001")
            self.assertEqual(inferred["observation_period"], "2020;2021")
            self.assertEqual(inferred["source_ids"], "housing;counties")
            self.assertNotIn("*", inferred["value"])
            self.assertEqual(coverage["inference"]["per_factor"]["housing"]["inferred_count"], 1)
            source_backed = next(row for row in factors if row["fips"] == "01001")
            self.assertEqual(source_backed["is_inferred"], "false")
            self.assertEqual(source_backed["inference_donor_fips"], "")
            self.assertEqual(source_backed["nearest_donor_km"], "")
            self.assertEqual(source_backed["farthest_donor_km"], "")

    def test_given_inferred_factor_when_outputs_are_written_then_machine_and_presentation_contracts_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            run(self.make_fixture(Path(tmp)), output)
            with (output / "rankings.csv").open(newline="") as stream:
                rankings = list(csv.DictReader(stream))
            self.assertEqual(len(rankings), 3)
            self.assertTrue(all("*" not in value for row in rankings for value in row.values()))
            self.assertEqual(next(row for row in rankings if row["fips"] == "01005")["inferred_factors"], "housing")
            with (output / "county_rankings.csv").open(newline="") as stream:
                presentation = list(csv.DictReader(stream))
            inferred = next(row for row in presentation if row["fips"] == "01005")
            sourced = next(row for row in presentation if row["fips"] == "01001")
            self.assertTrue(inferred["name"].endswith("*"))
            self.assertTrue(inferred["housing"].endswith("*"))
            self.assertTrue(inferred["housing_rank"].endswith("*"))
            self.assertTrue(inferred["runoff_rank"].endswith("*"))
            self.assertFalse(any("*" in value for value in sourced.values()))

    def test_given_successful_pipeline_when_outputs_are_listed_then_exactly_six_canonical_files_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            run(self.make_fixture(Path(tmp)), output)
            self.assertEqual({path.name for path in output.iterdir()}, {
                "counties.csv", "factors.csv", "rankings.csv", "county_rankings.csv",
                "coverage.json", "run-manifest.json",
            })


if __name__ == "__main__":
    unittest.main()
