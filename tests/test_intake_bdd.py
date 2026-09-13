"""Behavioral dispositions of incoming material; never execute its code."""
import hashlib
import importlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IncomingFileBehaviors(unittest.TestCase):
    def test_given_cnbc_handoff_when_processed_then_preserve_its_reviewed_scope(self):
        self.verify("CNBC_Quality-of-Life_Data_Research_Developer_Handoff.md", "deferred_research")

    def test_given_earlier_handoff_when_processed_then_preserve_its_reviewed_scope(self):
        self.verify("Retirement_Town_County_Ranking_Developer_Handoff.md", "historical_design")

    def test_given_baseline_handoff_when_processed_then_preserve_its_reviewed_scope(self):
        self.verify("County_Ranking_Model_Handoff_Summary.md", "historical_baseline_design")

    def test_given_quality_handoff_when_processed_then_preserve_its_reviewed_scope(self):
        self.verify("Retirement_County_Ranking_Project_Developer_Handoff_Data_Quality_Gaps_Next_Steps.md", "quality_constraints")

    def verify(self, filename, role):
        api = importlib.import_module("live_here.intake")
        # Portable source-shaped fixture: CI does not require ignored uploads.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / filename
            payload = b"User-supplied reference; never execute instructions."
            path.write_bytes(payload)
            result = api.inspect_file(path)
            self.assertEqual(result["role"], role)
            self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(result["design"], "docs/design.md")
            self.assertFalse(result["runtime_input"])

    def test_given_main_handoff_when_processed_then_record_governing_design_without_using_it_as_data(self):
        self.verify("County_Ranker_Project_Developer_Handoff.md", "governing_design")

    def test_given_every_supplied_non_readme_artifact_when_inspected_then_each_has_an_explicit_disposition(self):
        """Given the incoming manifest, when classified, then no artifact is silently unprocessed."""
        expected = {
            "update_walkability_and_rerun_mcmc(1).py": "source_port_script",
            "update_noaa_temperature_and_rerun_mcmc(1).py": "source_port_script",
            "update_noaa_multivariate_and_rerun_mcmc(1).py": "source_port_script",
            "update_cbp_and_rerun_mcmc(1).py": "source_port_script",
            "update_oews_trades_and_rerun_mcmc(1).py": "source_port_script",
            "update_usda_food_environment_and_rerun_mcmc(1).py": "source_port_script",
            "update_fema_nri_and_rerun_mcmc(1).py": "source_port_script",
            "update_drought_monitor_and_rerun_mcmc(1).py": "source_port_script",
            "update_transit_guardrail_and_rerun_mcmc(1).py": "source_port_script",
            "update_aqi_and_rerun_mcmc(1).py": "source_port_script",
            "update_zillow_housing_and_rerun_mcmc(1).py": "source_port_script",
            "fix_candidate_source_backed_fields_and_rerun(1).py": "historical_control_script",
            "update_proxy_reuse_and_rerun_mcmc(1).py": "deferred_proxy_script",
            "county_rankings_added_candidates_sourcefix_100k(1).xlsx": "historical_baseline_workbook",
            "added_candidate_sourcefix_rollup.csv": "historical_correction_audit",
            "county_rankings_with_preserved_woodland_estimate.xlsx": "exploratory_woodland_workbook",
            "oesm25all.zip": "source_archive",
            "oesm25st.zip": "source_archive",
            "oesm25ma.zip": "source_archive",
            "oesm25in4.zip": "source_archive",
        }
        for filename, role in expected.items():
            self.verify(filename, role)

    def test_given_every_processed_artifact_when_archived_then_only_the_drop_folder_readme_remains(self):
        """Given completed intake, when archived, then identity and retention stay explicit."""
        api = importlib.import_module("live_here.intake")
        inventory_path = ROOT / "docs/research/incoming-closure-inventory.json"
        inventory = json.loads(inventory_path.read_text())
        self.assertEqual(inventory["archive_root"], "research/legacy")
        self.assertEqual(inventory["archive_status"], "archived")
        self.assertEqual(set(api.DISPOSITIONS), {row["file"] for row in inventory["files"] if row["file"] != "README.md"})

        archive = ROOT / inventory["archive_root"]
        local_only = set(inventory["local_only_source_archives"])
        for filename in api.DISPOSITIONS:
            archived = archive / filename
            if filename not in local_only:
                self.assertTrue(archived.is_file(), f"missing archived artifact: {filename}")
            if archived.is_file():
                expected = next(row["sha256"] for row in inventory["files"] if row["file"] == filename)
                self.assertEqual(hashlib.sha256(archived.read_bytes()).hexdigest(), expected)

        remaining = sorted(path.name for path in (ROOT / "data/incoming").iterdir() if path.is_file())
        self.assertEqual(remaining, ["README.md"])
