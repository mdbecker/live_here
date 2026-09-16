"""Given/When/Then behavior for the archived specialty-grocery source."""

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.factors import specialty_grocery
from live_here.io import load_counties, sha256
from live_here.pipeline import run


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/sources/specialty_grocery_density_1020_city_restricted_statewide_expansion.xlsx"


def write_workbook(path, rows):
    headers = ["County", "State", "County FIPS", "Proxy / Lower-Bound Stores"]

    def cell(ref, value):
        if value == "":
            return f'<c r="{ref}" t="inlineStr"><is><t></t></is></c>'
        escaped = (str(value).replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;").replace('"', "&quot;"))
        return f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'

    def row_xml(number, values):
        letters = ["A", "B", "C", "D"]
        return f'<row r="{number}">' + "".join(
            cell(f"{letter}{number}", value) for letter, value in zip(letters, values)
        ) + "</row>"

    sheet_rows = [row_xml(1, headers)]
    sheet_rows.extend(row_xml(number, values) for number, values in enumerate(rows, 2))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + "".join(sheet_rows) + "</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="County Density Ranking" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="/xl/worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def write_counties(path, rows):
    fields = ["fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class SpecialtyGroceryBehaviors(unittest.TestCase):
    def test_given_archived_workbook_when_loaded_then_proxy_store_values_match_all_source_counties(self):
        counties = load_counties(ROOT / "data/interim/current/counties.csv")
        result, audit = specialty_grocery.calculate([SOURCE], counties)
        self.assertEqual(result["06075"]["value"], 8)
        self.assertEqual(result["34003"]["value"], 39)
        self.assertEqual(audit["rows_read"], 319)
        self.assertEqual(audit["matched_by_fips"], 319)
        self.assertEqual(audit["fuzzy_matches"], 0)

    def test_given_missing_and_blank_counties_when_loaded_then_they_are_explicit_zeroes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "specialty.xlsx"
            write_workbook(path, [
                ["Alpha County", "AA", "", "3"],
                ["Gammaa County", "AA", "", ""],
            ])
            counties = {
                "01001": {"fips": "01001", "name": "Alpha County", "state": "AA"},
                "01003": {"fips": "01003", "name": "Beta County", "state": "AA"},
                "01005": {"fips": "01005", "name": "Gamma County", "state": "AA"},
            }
            result, audit = specialty_grocery.calculate([path], counties)
        self.assertEqual(result["01001"]["value"], 3)
        for code in ("01003", "01005"):
            self.assertEqual(result[code]["value"], 0)
            self.assertEqual(result[code]["value_status"], "inferred_zero")
            self.assertTrue(result[code]["is_inferred"])
        self.assertEqual(audit["normalized_matches"], 1)
        self.assertEqual(audit["fuzzy_matches"], 1)
        self.assertEqual(audit["zero_filled_count"], 2)

    def test_given_conflicting_or_ambiguous_county_identity_when_loaded_then_the_build_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "specialty.xlsx"
            write_workbook(path, [["Beta County", "AA", "01001", "3"]])
            counties = {
                "01001": {"fips": "01001", "name": "Alpha County", "state": "AA"},
                "01003": {"fips": "01003", "name": "Beta County", "state": "AA"},
            }
            with self.assertRaisesRegex(ValueError, "onflict"):
                specialty_grocery.calculate([path], counties)

            write_workbook(path, [["Fairfax", "VA", "", "3"]])
            counties = {
                "51059": {"fips": "51059", "name": "Fairfax County", "state": "VA"},
                "51600": {"fips": "51600", "name": "Fairfax city", "state": "VA"},
            }
            with self.assertRaisesRegex(ValueError, "mbiguous"):
                specialty_grocery.calculate([path], counties)

            write_workbook(path, [
                ["Alpha County", "AA", "01001", "3"],
                ["Alpha County", "AA", "01001", "4"],
            ])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                specialty_grocery.calculate([path], {"01001": {"fips": "01001", "name": "Alpha County", "state": "AA"}})

    def test_given_completed_factor_when_pipeline_runs_then_outputs_include_values_ranks_and_zero_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counties_path = root / "counties.csv"
            workbook_path = root / "specialty.xlsx"
            write_counties(counties_path, [
                {"fips": "01001", "name": "Alpha County", "state": "AA", "geography_vintage": "2019", "latitude": "0", "longitude": "0", "coordinate_vintage": "2020"},
                {"fips": "01003", "name": "Beta County", "state": "AA", "geography_vintage": "2019", "latitude": "0", "longitude": "1", "coordinate_vintage": "2020"},
            ])
            write_workbook(workbook_path, [["Alpha County", "AA", "01001", "3"]])
            config = {
                "mode": "research", "geography_source": "counties", "factors": ["specialty_groceries"],
                "iterations": 10, "seed": 42,
                "adapters": {"specialty_groceries": {"sources": ["specialty_groceries"]}},
                "sources": [
                    {"id": "counties", "path": str(counties_path), "sha256": sha256(counties_path), "url": "fixture://counties", "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                    {"id": "specialty_groceries", "path": str(workbook_path), "sha256": sha256(workbook_path), "url": "fixture://specialty", "vintage": "fixture", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
                ],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            output = root / "output"
            coverage = run(config_path, output)

            with (output / "factors.csv").open(newline="", encoding="utf-8") as stream:
                factors = list(csv.DictReader(stream))
            with (output / "rankings.csv").open(newline="", encoding="utf-8") as stream:
                rankings = list(csv.DictReader(stream))
            with (output / "county_rankings.csv").open(newline="", encoding="utf-8") as stream:
                presentation = list(csv.DictReader(stream))
        self.assertEqual(coverage["selected_factors"], ["specialty_groceries"])
        self.assertEqual(next(row for row in factors if row["fips"] == "01003")["value_status"], "inferred_zero")
        self.assertEqual(next(row for row in rankings if row["fips"] == "01003")["inferred_factors"], "specialty_groceries")
        self.assertIn("specialty_groceries_rank", rankings[0])
        zero_row = next(row for row in presentation if row["fips"] == "01003")
        self.assertTrue(zero_row["specialty_groceries"].endswith("*"))
        self.assertIn("specialty_groceries_rank", zero_row)

    def test_given_archived_source_when_repository_is_checked_then_it_is_stable_and_incoming_is_empty(self):
        self.assertTrue(SOURCE.is_file())
        self.assertEqual(sha256(SOURCE), "b9054b2612d6a2a1ca9acf1769585958a7962454d7939f6aa8cc51d7dadb2f61")
        incoming = ROOT / "data/incoming"
        self.assertEqual(list(incoming.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
