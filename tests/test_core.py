import json
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

from live_here.catalog import FACTORS
from live_here.factors import aqi, walkability
from live_here.io import csv_rows, fips, load_counties, sha256
from live_here.pipeline import read_config, run
from live_here.ranking import average_ranks, runoff

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


class RankingTests(unittest.TestCase):
    def test_average_ties_and_direction(self):
        self.assertEqual(average_ranks([10, 30, 10, 20]), [1.5, 4, 1.5, 3])
        self.assertEqual(average_ranks([10, 30, 10, 20], True), [3.5, 1, 3.5, 2])
        with self.assertRaises(ValueError):
            average_ranks([1, math.nan])

    def test_dominance_and_round_conservation(self):
        wins, rounds = runoff([[1, 1], [2, 2], [3, 3]], 20, 7)
        self.assertEqual(wins, [20, 0, 0])
        self.assertEqual(rounds, [3, 2, 1])
        self.assertEqual(sum(rounds), 3 * 4 / 2)

    def test_seed_reproducibility_and_tie_fairness(self):
        matrix = [[1, 1]] * 3
        first = runoff(matrix, 6000, 123)
        self.assertEqual(first, runoff(matrix, 6000, 123))
        self.assertEqual(sum(first[0]), 6000)
        self.assertTrue(all(1700 < n < 2300 for n in first[0]))
        self.assertAlmostEqual(sum(first[1]), 6)

    def test_single_county_and_invalid_inputs(self):
        self.assertEqual(runoff([[1]], 10), ([10], [1.0]))
        for matrix, iterations in [([], 10), ([[1], [1, 2]], 10), ([[1]], 0), ([[1]], 1.2), ([[math.inf]], 1)]:
            with self.assertRaises(ValueError):
                runoff(matrix, iterations)
        with self.assertRaisesRegex(ValueError, "seed"):
            runoff([[1]], 10, "42")


class GeographyTests(unittest.TestCase):
    def test_leading_zero_and_reject_ambiguous_codes(self):
        self.assertEqual(fips("01001"), "01001")
        for code in (1001, "1001.0", "01000", "00001", "", "123456"):
            with self.assertRaises(ValueError):
                fips(code)

    def test_duplicate_and_mixed_vintage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "counties.csv"
            for rows in ("01001,A,AL,2020\n01001,B,AL,2020\n", "01001,A,AL,2020\n01003,B,AL,2023\n"):
                p.write_text("fips,name,state,geography_vintage\n" + rows)
                with self.assertRaises(ValueError):
                    load_counties(p)


class FactorTests(unittest.TestCase):
    def setUp(self):
        self.counties = load_counties(DEMO / "counties.csv")

    def test_aqi_annualization(self):
        results, audit = aqi.calculate([DEMO / "aqi.csv"], self.counties, DEMO / "aqi-crosswalk.csv")
        self.assertAlmostEqual(results["01001"]["value"], (10 / 365 * 365.25 + 4 / 366 * 365.25) / 2)
        self.assertAlmostEqual(results["01003"]["value"], 15 / 200 * 365.25)
        self.assertNotIn("01005", results)
        self.assertEqual(audit["unmatched_source_names"], [])

    def test_aqi_rejects_duplicate_years(self):
        with self.assertRaisesRegex(ValueError, "Duplicate county/year"):
            aqi.calculate([DEMO / "aqi.csv"] * 2, self.counties, DEMO / "aqi-crosswalk.csv")

    def test_aqi_invalid_counts_and_zero_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "aqi.csv"
            header = (DEMO / "aqi.csv").read_text().splitlines()[0] + "\n"
            p.write_text(header + "Example State,North,2023,0,0,0,0,0\n")
            result, audit = aqi.calculate([p], self.counties, DEMO / "aqi-crosswalk.csv")
            self.assertEqual(result, {})
            self.assertEqual(audit["zero_monitoring_county_years"], 1)
            p.write_text(header + "Example State,North,2023,10,11,0,0,0\n")
            with self.assertRaisesRegex(ValueError, "exceed"):
                aqi.calculate([p], self.counties, DEMO / "aqi-crosswalk.csv")

    def test_walkability_weights_and_zero_population(self):
        result, audit = walkability.calculate([DEMO / "walkability.csv"], self.counties)
        self.assertEqual(result["01001"]["value"], 10)
        self.assertEqual(result["01003"]["value"], 6)
        self.assertNotIn("01005", result)
        self.assertEqual(audit["zero_valid_population_counties"], 1)
        with self.assertRaisesRegex(ValueError, "Duplicate block group"):
            walkability.calculate([DEMO / "walkability.csv"] * 2, self.counties)

    def test_zip_parsing_and_ambiguous_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "source.zip"
            with zipfile.ZipFile(p, "w") as archive:
                archive.write(DEMO / "aqi.csv", "aqi.csv")
            self.assertEqual(csv_rows(p), csv_rows(DEMO / "aqi.csv"))
            with zipfile.ZipFile(p, "a") as archive:
                archive.writestr("another.csv", "a,b\n1,2\n")
            with self.assertRaisesRegex(ValueError, "exactly one CSV"):
                csv_rows(p)

    def test_walkability_missing_score_is_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "walk.csv"
            p.write_text("GEOID10,STATEFP,COUNTYFP,TotPop,NatWalkInd\n"
                         "010010001001,01,001,100,4\n"
                         "010010001002,01,001,300,\n")
            result, _ = walkability.calculate([p], self.counties)
            self.assertEqual(result["01001"]["value"], 4)
            self.assertIn("missing_score_groups=1", result["01001"]["quality_note"])


class PipelineTests(unittest.TestCase):
    def changed_config(self, directory, **overrides):
        config = json.loads((DEMO / "config.json").read_text())
        for source in config["sources"]:
            source["path"] = str(DEMO / source["path"])
        config.update(overrides)
        p = Path(directory) / "config.json"
        p.write_text(json.dumps(config))
        return p

    def test_end_to_end_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            result = run(DEMO / "config.json", a)
            run(DEMO / "config.json", b)
            self.assertEqual(result["universe_count"], 3)
            self.assertEqual(result["ranked_count"], 2)
            self.assertEqual(result["excluded_fips"], ["01005"])
            for file in a.iterdir():
                self.assertEqual(file.read_bytes(), (b / file.name).read_bytes())
            manifest = json.loads((a / "run-manifest.json").read_text())
            for name, checksum in manifest["output_sha256"].items():
                self.assertEqual(sha256(a / name), checksum)
            with self.assertRaisesRegex(ValueError, "new or empty"):
                run(DEMO / "config.json", a)

    def test_strict_missingness_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.changed_config(tmp, missing_policy="error")
            out = Path(tmp) / "out"
            with self.assertRaisesRegex(ValueError, "lack selected factors"):
                run(config, out)
            self.assertFalse(out.exists())

    def test_rejects_checksum_tampering_and_unimplemented_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.changed_config(tmp, factors=[*FACTORS, "future_factor"])
            with self.assertRaisesRegex(ValueError, "awaiting implementation"):
                read_config(p)
            p = self.changed_config(tmp)
            data = json.loads(p.read_text())
            data["sources"][0]["sha256"] = "0" * 64
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                read_config(p)

    def test_rejects_production_and_mismatched_geography(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.changed_config(tmp, mode="production")
            with self.assertRaisesRegex(ValueError, "not implemented"):
                read_config(p)
            p = self.changed_config(tmp)
            data = json.loads(p.read_text())
            data["sources"][-1]["geography_vintage"] = "other"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "geography differs"):
                run(p, Path(tmp) / "out")

    def test_rejects_legacy_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.changed_config(tmp)
            data = json.loads(p.read_text())
            data["sources"][0]["path"] = str(DEMO.parents[1] / "research" / "legacy" / "added_candidate_sourcefix_rollup.csv")
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Historical research"):
                read_config(p)


if __name__ == "__main__":
    unittest.main()
