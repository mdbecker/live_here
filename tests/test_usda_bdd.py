"""Given/When/Then scenarios for USDA Food Environment adjustment."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors import usda


class UsdaBehaviors(unittest.TestCase):
    def test_given_low_access_percentiles_when_multiplier_is_calculated_then_penalty_is_bounded(self):
        self.assertEqual(usda.access_multiplier(0.0), 1.0)
        self.assertEqual(usda.access_multiplier(1.0), 0.65)
        self.assertGreaterEqual(usda.access_multiplier(2.0), 0.65)

    def test_given_usda_sentinels_when_parsed_then_values_remain_missing(self):
        self.assertIsNone(usda.safe_number("-9999"))
        self.assertIsNone(usda.safe_number("-8888"))
        self.assertEqual(usda.safe_number("12.5"), 12.5)

    def test_given_tied_access_values_when_percentiles_are_calculated_then_ties_receive_their_average_position(self):
        self.assertEqual(
            usda.percentile_scores([5.0, 5.0, 10.0, 20.0, 20.0]),
            [0.125, 0.125, 0.5, 0.875, 0.875],
        )

    def test_given_permuted_tied_access_values_when_percentiles_are_calculated_then_each_value_keeps_its_score(self):
        original = [5.0, 5.0, 10.0, 20.0, 20.0]
        permuted = [20.0, 5.0, 20.0, 5.0, 10.0]
        expected_by_value = {5.0: 0.125, 10.0: 0.5, 20.0: 0.875}
        self.assertEqual(
            [expected_by_value[value] for value in permuted],
            usda.percentile_scores(permuted),
        )

    def test_given_complete_usda_access_rows_when_grocery_is_calculated_then_the_national_cohort_and_indicator_period_are_audited(self):
        cbp = {
            "01001": {"grocery_establishments_per_10k": "2.0"},
            "01003": {"grocery_establishments_per_10k": "3.0"},
        }
        atlas = {
            "01001": {"PCT_LACCESS_POP19": 10.0, "PCT_LACCESS_LOWI19": 20.0, "PCT_LACCESS_HHNV19": 30.0},
            "01003": {"PCT_LACCESS_POP19": 20.0, "PCT_LACCESS_LOWI19": 30.0, "PCT_LACCESS_HHNV19": 40.0},
        }
        _, audit = usda.calculate_grocery(cbp, atlas)
        self.assertEqual(audit["percentile_cohort"], "national_usda_fea_rows_with_all_three_2019_access_indicators")
        self.assertEqual(audit["access_indicator_observation_period"], "2019")
        self.assertEqual(audit["access_indicator_codes"], ["PCT_LACCESS_POP19", "PCT_LACCESS_LOWI19", "PCT_LACCESS_HHNV19"])

    def test_given_state_and_county_data_csv_when_read_then_fips_and_variables_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "atlas.zip"
            text = "FIPS,Variable_Code,Value\n01001,PCT_LACCESS_POP19,12.5\n01001,GROC20,-9999\n"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("StateAndCountyData.csv", text)
            rows = usda.read_atlas_zip(path)
            self.assertEqual(rows["01001"]["PCT_LACCESS_POP19"], 12.5)
            self.assertNotIn("GROC20", rows["01001"])
