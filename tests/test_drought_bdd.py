import csv
import tempfile
import unittest
from pathlib import Path

from live_here.factors.drought import (
    days_per_year_from_weeks,
    normalize_drought_row,
    read_drought_csv,
)


class DroughtFactorBDD(unittest.TestCase):
    def test_given_observed_d1_plus_weeks_and_a_ten_year_window_when_converted_then_days_are_annualized(self):
        self.assertEqual(days_per_year_from_weeks("20", 10), 14.0)

    def test_given_a_censored_or_missing_drought_value_when_converted_then_it_remains_missing(self):
        self.assertIsNone(days_per_year_from_weeks("-9999", 10))
        self.assertIsNone(days_per_year_from_weeks("", 10))

    def test_given_a_source_row_when_normalized_then_fips_stays_a_five_digit_string(self):
        row = normalize_drought_row(
            {"FIPS": "123", "State": "AA", "County": "Example County", "NonConsecutiveWeeks": "15"},
            window_years=10,
        )
        self.assertEqual(row["fips"], "00123")
        self.assertEqual(row["value"], 10.5)
        self.assertEqual(row["value_status"], "derived_source")

    def test_given_a_small_official_style_csv_when_read_then_rows_and_audit_are_returned(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "drought.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["FIPS", "State", "County", "NonConsecutiveWeeks"])
                writer.writeheader()
                writer.writerow({"FIPS": "1", "State": "AA", "County": "One County", "NonConsecutiveWeeks": "10"})
                writer.writerow({"FIPS": "2", "State": "AA", "County": "Two County", "NonConsecutiveWeeks": "-9999"})
            rows, audit = read_drought_csv(path, window_years=10)
        self.assertEqual(rows["00001"]["value"], 7.0)
        self.assertNotIn("00002", rows)
        self.assertEqual(audit["rows_read"], 2)
        self.assertEqual(audit["usable_rows"], 1)


if __name__ == "__main__":
    unittest.main()
