"""Given/When/Then scenarios for the Census CBP shared business base."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors import cbp


class CbpBehaviors(unittest.TestCase):
    def test_given_cbp_rows_when_density_is_calculated_then_grocery_and_trade_units_are_explicit(self):
        rows = [{"fips": "01001", "NAICS": "445110", "ESTAB": "20", "EMP": "100", "POP": "50000"},
                {"fips": "01001", "NAICS": "238", "ESTAB": "", "EMP": "250", "POP": "50000"},
                {"fips": "01003", "NAICS": "445110", "ESTAB": "D", "EMP": "100", "POP": "50000"}]
        result, audit = cbp.calculate_rows(rows)
        self.assertEqual(result["01001"]["grocery_establishments_per_10k"], 4.0)
        self.assertEqual(result["01001"]["trade_employment_per_1k"], 5.0)
        self.assertEqual(audit["suppressed_or_missing_rows"], 1)

    def test_given_suppressed_population_or_industry_when_calculated_then_missing_is_not_zero(self):
        result, _ = cbp.calculate_rows([{"fips": "01003", "NAICS": "445110", "ESTAB": "D", "EMP": "100", "POP": "-"}])
        self.assertNotIn("01003", result)

    def test_given_cbp_rows_and_same_year_population_when_joined_then_denominator_is_explicit(self):
        rows = [{"fips": "01001", "NAICS": "445110", "ESTAB": "20", "EMP": "100"}]
        result, audit = cbp.calculate_rows_with_population(rows, {"01001": 50000}, population_vintage="2023")
        self.assertEqual(result["01001"]["grocery_establishments_per_10k"], 4.0)
        self.assertEqual(audit["population_vintage"], "2023")
