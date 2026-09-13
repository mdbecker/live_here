"""Given/When/Then specifications written before acquisition implementation."""

import importlib
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace


class SourceAcquisitionBehaviors(unittest.TestCase):
    def api(self):
        return importlib.import_module("live_here.acquire")

    def test_given_remote_bytes_when_downloaded_then_hash_and_origin_are_saved(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "source.csv"
            record = api.download("https://example.test/source.csv", target,
                                  fetch=lambda url: b"id,value\n01,2\n")
            self.assertEqual(target.read_bytes(), b"id,value\n01,2\n")
            self.assertEqual(record["url"], "https://example.test/source.csv")
            self.assertEqual(len(record["sha256"]), 64)
            self.assertTrue(record["retrieved_at"])
            self.assertTrue(target.with_suffix(".csv.source.json").is_file())

    def test_given_cached_download_when_repeated_then_network_is_not_used(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "source.csv"
            api.download("https://example.test/a", target, fetch=lambda url: b"original")
            def offline(url):
                self.fail("A verified cached source must not be downloaded again")
            result = api.download("https://example.test/a", target, fetch=offline)
            self.assertEqual(result["sha256"], api.sha256(target))
            target.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                api.download("https://example.test/a", target, fetch=offline)

    def test_given_failed_download_when_fetch_raises_then_no_source_is_registered(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "source.csv"
            def failure(url):
                raise OSError("network unavailable")
            with self.assertRaises(OSError):
                api.download("https://example.test/a", target, fetch=failure)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".csv.source.json").exists())

    def test_given_system_http_transport_when_requested_then_http_failures_are_not_saved_as_data(self):
        api = self.api()
        with patch("subprocess.run", return_value=SimpleNamespace(stdout=b"official bytes")) as call:
            self.assertEqual(api.curl_fetch("https://example.test/a"), b"official bytes")
            self.assertIn("--fail", call.call_args.args[0])
            self.assertTrue(call.call_args.kwargs["check"])

    def test_given_numeric_epa_ids_when_normalized_then_leading_zeros_survive(self):
        api = self.api()
        row = api.normalize_walkability_row({"GEOID10": 10010001001,
              "STATEFP": 1, "COUNTYFP": 1, "TotPop": 100, "NatWalkInd": 8})
        self.assertEqual(row["GEOID10"], "010010001001")
        self.assertEqual(row["STATEFP"], "01")
        self.assertEqual(row["COUNTYFP"], "001")

    def test_given_county_and_independent_city_when_names_match_then_never_conflate(self):
        api = self.api()
        counties = [{"fips": "51059", "name": "Fairfax County", "state": "VA", "geography_vintage": "2010"},
                    {"fips": "51600", "name": "Fairfax city", "state": "VA", "geography_vintage": "2010"}]
        rows, audit = api.aqi_crosswalk(counties, [{"State": "Virginia", "County": "Fairfax"},
                                                {"State": "Virginia", "County": "Fairfax City"}])
        self.assertEqual({r["County"]: r["fips"] for r in rows}, {"Fairfax": "51059", "Fairfax City": "51600"})
        self.assertEqual(audit["unmatched"], [])

    def test_given_unknown_aqi_name_when_mapping_then_report_it_without_guessing(self):
        api = self.api()
        rows, audit = api.aqi_crosswalk([], [{"State": "Virginia", "County": "Unknown"}])
        self.assertEqual(rows, [])
        self.assertEqual(audit["unmatched"], [["Virginia", "Unknown"]])

    def test_given_updated_epa_geoid_when_exported_then_use_generic_identifier_without_claiming_2010(self):
        api = self.api()
        row = api.normalize_walkability_row({"GEOID10": "461130001001", "GEOID20": "461020001001",
              "STATEFP": "46", "COUNTYFP": "102", "TotPop": "100", "NatWalkInd": "8"})
        self.assertEqual(row["GEOID"], "461020001001")
        self.assertNotIn("GEOID10", row)

    def test_given_rounded_epa_scientific_identifier_when_components_exist_then_reconstruct_exact_code(self):
        api = self.api()
        row = api.normalize_walkability_row({"GEOID20": "4.8113E+11", "STATEFP": "48",
              "COUNTYFP": "113", "TRACTCE": "980100", "BLKGRPCE": "1", "TotPop": "100", "NatWalkInd": "8"})
        self.assertEqual(row["GEOID"], "481139801001")
        with self.assertRaises(ValueError):
            api.normalize_walkability_row({"GEOID20": "4.8113E+11", "STATEFP": "48",
                "COUNTYFP": "113", "TotPop": "100", "NatWalkInd": "8"})

    def test_given_census_gazetteer_when_normalized_then_all_source_counties_are_preserved(self):
        api = self.api()
        rows = api.normalize_counties("USPS\tGEOID\tNAME\nAL\t01001\tAutauga County\nPR\t72001\tAdjuntas Municipio\n", "2019")
        self.assertEqual([r["fips"] for r in rows], ["01001", "72001"])
        self.assertTrue(all(r["geography_vintage"] == "2019" for r in rows))

    def test_given_generic_geoid_export_when_adapter_runs_then_source_vintage_is_not_relabelled(self):
        from live_here.factors.walkability import calculate
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "walk.csv"
            p.write_text("GEOID,STATEFP,COUNTYFP,TotPop,NatWalkInd\n461020001001,46,102,100,8\n")
            values, _ = calculate([p], {"46102": {"geography_vintage": "2019"}})
            self.assertEqual(values["46102"]["value"], 8)

    def test_given_downloaded_source_files_when_prepared_then_pipeline_reads_only_hashed_source_exports(self):
        api = self.api()
        from live_here.pipeline import run
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "data/raw/current"
            raw.mkdir(parents=True)
            files = {"counties": ("counties.zip", "https://example.test/counties"),
                     "walkability": ("walk.csv", "https://example.test/walk"),
                     "aqi2023": ("aqi.csv", "https://example.test/aqi")}
            with zipfile.ZipFile(raw / "counties.zip", "w") as archive:
                archive.writestr("counties.txt", "USPS\tGEOID\tNAME\nAL\t01001\tAutauga County\nAL\t01003\tBaldwin County\n")
            (raw / "walk.csv").write_text("GEOID20,STATEFP,COUNTYFP,TotPop,NatWalkInd\n010010001001,01,001,100,8\n")
            (raw / "aqi.csv").write_text("State,County,Year,Days with AQI,Unhealthy for Sensitive Groups Days,Unhealthy Days,Very Unhealthy Days,Hazardous Days\nAlabama,Autauga,2023,365,10,0,0,0\n")
            receipts = {key: {"url": url, "sha256": api.sha256(raw / name), "retrieved_at": "2026-09-12T00:00:00Z"}
                        for key, (name, url) in files.items()}
            api.prepare_current(root, files, receipts)
            config_path = root / "data/interim/current/config.json"
            config = json.loads(config_path.read_text())
            self.assertEqual(config["mode"], "research")
            self.assertTrue(all(s["raw_parent_sha256"] for s in config["sources"]))
            report = run(config_path, root / "result")
            self.assertEqual(report["ranked_count"], 1)
            self.assertEqual(report["excluded_fips"], ["01003"])

    def test_given_epa_release_listing_when_discovered_then_latest_two_complete_years_are_selected(self):
        """Given a listing with an in-progress year, when discovered, then only complete years are selected."""
        api = self.api()
        html = """<a href='annual_aqi_by_county_2026.zip'>2026</a>
        <a href='annual_aqi_by_county_2025.zip'>2025</a>
        <a href='annual_aqi_by_county_2024.zip'>2024</a>"""
        releases = api.discover_aqi_releases(html, today=date(2026, 9, 13))
        self.assertEqual([release["year"] for release in releases], [2025, 2024])
        self.assertEqual(releases[0]["url"], "https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_2025.zip")

    def test_given_cached_aqi_discovery_when_sources_are_discovered_then_network_listing_is_not_required(self):
        """Given cached AQI discovery, when preparing sources, then offline reruns reuse it."""
        gather = importlib.import_module("scripts.gather_current_data")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "data/raw/current"
            raw.mkdir(parents=True)
            cached = {
                "url": gather.AQI_LISTING_URL,
                "retrieved_at": "2026-09-13T00:00:00+00:00",
                "selected_releases": [
                    {"id": "aqi2025", "year": 2025, "filename": "annual_aqi_by_county_2025.zip", "url": "https://example.test/2025.zip"},
                    {"id": "aqi2024", "year": 2024, "filename": "annual_aqi_by_county_2024.zip", "url": "https://example.test/2024.zip"},
                ],
            }
            (raw / "aqi-release-discovery.json").write_text(json.dumps(cached), encoding="utf-8")
            original_root, original_listing = gather.ROOT, gather.listing_bytes
            try:
                gather.ROOT = root
                gather.listing_bytes = lambda transport: (_ for _ in ()).throw(AssertionError("network listing used"))
                sources = gather.discover_sources("python")
            finally:
                gather.ROOT = original_root
                gather.listing_bytes = original_listing
        self.assertEqual(sources["aqi2025"], ("annual_aqi_by_county_2025.zip", "https://example.test/2025.zip"))


if __name__ == "__main__":
    unittest.main()
