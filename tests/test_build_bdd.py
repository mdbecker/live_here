"""Given/When/Then behavior for the public clean build command."""

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from live_here.build import run_build


EXPECTED_GATHER_SCRIPTS = [
    "gather_current_data.py",
    "gather_temperature_data.py",
    "gather_snowfall_data.py",
    "gather_drought_data.py",
    "gather_cbp_data.py",
    "gather_oews_data.py",
    "gather_usda_data.py",
    "gather_fema_data.py",
    "gather_housing_data.py",
    "gather_transit_data.py",
]


CANONICAL_OUTPUTS = {
    "counties.csv",
    "factors.csv",
    "rankings.csv",
    "county_rankings.csv",
    "coverage.json",
    "run-manifest.json",
}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_pipeline_files(staging, names=CANONICAL_OUTPUTS):
    staging.mkdir(parents=True, exist_ok=True)
    for name in names:
        (staging / name).write_text(f"new {name}\n", encoding="utf-8")


class BuildBehaviorTests(unittest.TestCase):
    @contextmanager
    def make_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname = \"fixture\"\n", encoding="utf-8")
            (root / "src/live_here").mkdir(parents=True)
            (root / "scripts").mkdir()
            yield root

    def install_ordered_gather_scripts(self, root, *, fail_at=None, transport_file=True):
        for index, script in enumerate(EXPECTED_GATHER_SCRIPTS, 1):
            previous = "" if index == 1 else EXPECTED_GATHER_SCRIPTS[index - 2]
            body = f"""
import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--transport", choices=["python", "curl"], default="python")
args = parser.parse_args()
root = Path.cwd()
current = root / "data/interim/current"
current.mkdir(parents=True, exist_ok=True)
order = current / "order.txt"
if {index} > 1 and {previous!r} not in order.read_text(encoding="utf-8").splitlines():
    raise SystemExit("previous stage missing")
if args.transport != "curl":
    raise SystemExit("transport was not passed through")
if {script!r} == {fail_at!r}:
    raise SystemExit("intentional gather failure")
with order.open("a", encoding="utf-8") as stream:
    stream.write({script!r} + "\\n")
if {transport_file!r}:
    (current / "transport.txt").write_text(args.transport, encoding="utf-8")
"""
            if index == len(EXPECTED_GATHER_SCRIPTS):
                body += self.config_writer_source()
            path = root / "scripts" / script
            path.write_text(textwrap.dedent(body), encoding="utf-8")

    def config_writer_source(self):
        return r'''
def write_csv(path, rows, fields):
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

counties = current / "counties.csv"
transit = current / "transit.csv"
write_csv(counties, [
    {"fips": "01001", "name": "Alpha County", "state": "AA", "geography_vintage": "2019", "latitude": "0", "longitude": "0", "coordinate_vintage": "2020"},
    {"fips": "01003", "name": "Beta County", "state": "AA", "geography_vintage": "2019", "latitude": "0", "longitude": "1", "coordinate_vintage": "2020"},
], ["fips", "name", "state", "geography_vintage", "latitude", "longitude", "coordinate_vintage"])
write_csv(transit, [
    {"fips": "01001", "value": "10", "value_status": "derived_source", "observation_period": "fixture", "method": "fixture", "quality_note": ""},
    {"fips": "01003", "value": "20", "value_status": "derived_source", "observation_period": "fixture", "method": "fixture", "quality_note": ""},
], ["fips", "value", "value_status", "observation_period", "method", "quality_note"])
config = {
    "mode": "research",
    "geography_source": "counties",
    "factors": ["transit"],
    "iterations": 5,
    "seed": 1,
    "adapters": {"transit": {"sources": ["transit"]}},
    "sources": [
        {"id": "counties", "path": "counties.csv", "sha256": "", "url": "fixture://counties", "vintage": "2019", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
        {"id": "transit", "path": "transit.csv", "sha256": "", "url": "fixture://transit", "vintage": "fixture", "geography_vintage": "2019", "role": "source_export", "license": "fixture"},
    ],
}
import hashlib
config["sources"][0]["sha256"] = hashlib.sha256(counties.read_bytes()).hexdigest()
config["sources"][1]["sha256"] = hashlib.sha256(transit.read_bytes()).hexdigest()
(current / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
'''

    def test_given_fake_gather_chain_when_build_runs_then_order_and_outputs_are_observable(self):
        """Given ordered gather stages, when build runs, then artifacts prove stage order and canonical outputs."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            run_build(root=root, transport="curl")
            order = (root / "data/interim/current/order.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(order, EXPECTED_GATHER_SCRIPTS)
            self.assertEqual({p.name for p in (root / "outputs").iterdir()}, CANONICAL_OUTPUTS)
            manifest = json.loads((root / "outputs/run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(manifest["config"]["sources"][0]["path"]).name, "counties.csv")

    def test_given_stale_interim_when_build_runs_then_clean_config_from_same_build_is_used(self):
        """Given a stale config, when build runs, then interim is cleared before the generated config is used."""
        with self.make_repo() as root:
            stale = root / "data/interim/current"
            stale.mkdir(parents=True)
            (stale / "config.json").write_text('{"mode": "demo"}', encoding="utf-8")
            (stale / "stale.txt").write_text("old", encoding="utf-8")
            self.install_ordered_gather_scripts(root)
            run_build(root=root, transport="curl")
            self.assertFalse((root / "data/interim/current/stale.txt").exists())
            self.assertEqual((root / "data/interim/current/transport.txt").read_text(encoding="utf-8"), "curl")

    def test_given_prior_outputs_when_gather_fails_then_prior_outputs_are_preserved(self):
        """Given prior outputs, when a gather stage fails, then later stages stop and outputs stay unchanged."""
        with self.make_repo() as root:
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            before = _sha256(outputs / "run-manifest.json")
            self.install_ordered_gather_scripts(root, fail_at=EXPECTED_GATHER_SCRIPTS[3])
            with self.assertRaises(subprocess.CalledProcessError):
                run_build(root=root, transport="curl")
            self.assertEqual(_sha256(outputs / "run-manifest.json"), before)
            order = (root / "data/interim/current/order.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(order, EXPECTED_GATHER_SCRIPTS[:3])

    def test_given_wrong_directory_when_build_runs_then_nothing_is_deleted(self):
        """Given a non-root directory, when build starts, then validation fails before mutation."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "data/interim/current"
            current.mkdir(parents=True)
            (current / "keep.txt").write_text("do not delete", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repository root"):
                run_build(root=root, transport="curl")
            self.assertTrue((current / "keep.txt").is_file())
            self.assertFalse((root / ".outputs-staging-1").exists())

    def test_given_stale_scratch_when_build_runs_then_safe_scratch_is_cleaned(self):
        """Given interrupted scratch dirs, when build runs, then safe stale scratch is removed and outputs promote."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            (root / ".outputs-staging-old").mkdir()
            (root / ".outputs-staging-old/temp.txt").write_text("old", encoding="utf-8")
            (root / "outputs").mkdir()
            (root / "outputs/run-manifest.json").write_text("previous", encoding="utf-8")
            (root / ".outputs-backup-old").mkdir()
            (root / ".outputs-backup-old/run-manifest.json").write_text("backup", encoding="utf-8")
            run_build(root=root, transport="curl")
            self.assertFalse((root / ".outputs-staging-old").exists())
            self.assertFalse((root / ".outputs-backup-old").exists())
            self.assertEqual({p.name for p in (root / "outputs").iterdir()}, CANONICAL_OUTPUTS)

    def test_given_prior_outputs_when_pipeline_fails_then_prior_outputs_are_preserved(self):
        """Given prior outputs, when ranking fails before promotion, then the prior output stays intact."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            with patch("live_here.build.run_pipeline", side_effect=RuntimeError("intentional pipeline failure")):
                with self.assertRaisesRegex(RuntimeError, "intentional pipeline failure"):
                    run_build(root=root, transport="curl")
            self.assertEqual((outputs / "run-manifest.json").read_text(encoding="utf-8"), "previous")

    def test_given_pipeline_and_staging_cleanup_failures_then_pipeline_failure_is_reported(self):
        """Given prior outputs, when ranking and cleanup fail, then the ranking failure remains visible."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            import live_here.build as build
            original_rmtree = build.shutil.rmtree

            def reject_staging_cleanup(path, *args, **kwargs):
                if Path(path).name.startswith(".outputs-staging-"):
                    raise OSError("intentional staging cleanup failure")
                return original_rmtree(path, *args, **kwargs)

            def pipeline_fails_after_creating_staging(_config, staging):
                staging.mkdir()
                raise RuntimeError("intentional pipeline failure")

            with patch("live_here.build.run_pipeline", side_effect=pipeline_fails_after_creating_staging):
                with patch("live_here.build.shutil.rmtree", side_effect=reject_staging_cleanup):
                    with self.assertRaisesRegex(RuntimeError, "intentional pipeline failure"):
                        run_build(root=root, transport="curl")
            self.assertEqual((outputs / "run-manifest.json").read_text(encoding="utf-8"), "previous")

    def test_given_prior_outputs_when_pipeline_omits_a_canonical_file_then_prior_outputs_are_preserved(self):
        """Given prior outputs, when generated output is incomplete, then no incomplete result is promoted."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            with patch(
                "live_here.build.run_pipeline",
                side_effect=lambda _config, staging: _write_pipeline_files(staging, CANONICAL_OUTPUTS - {"coverage.json"}),
            ):
                with self.assertRaisesRegex(ValueError, "exactly"):
                    run_build(root=root, transport="curl")
            self.assertEqual((outputs / "run-manifest.json").read_text(encoding="utf-8"), "previous")

    def test_given_prior_outputs_when_pipeline_creates_an_extra_file_then_prior_outputs_are_preserved(self):
        """Given prior outputs, when generated output has an accidental file, then it is not promoted."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            with patch(
                "live_here.build.run_pipeline",
                side_effect=lambda _config, staging: _write_pipeline_files(staging, CANONICAL_OUTPUTS | {"debug.txt"}),
            ):
                with self.assertRaisesRegex(ValueError, "exactly"):
                    run_build(root=root, transport="curl")
            self.assertEqual((outputs / "run-manifest.json").read_text(encoding="utf-8"), "previous")

    def test_given_prior_outputs_when_promotion_cannot_commit_then_prior_outputs_are_restored(self):
        """Given prior outputs, when staging cannot replace them, then the previous output is restored."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            original_rename = Path.rename

            def reject_staging_commit(path, target):
                if path.name.startswith(".outputs-staging-") and Path(target).name == "outputs":
                    raise OSError("intentional promotion failure")
                return original_rename(path, target)

            with patch.object(Path, "rename", autospec=True, side_effect=reject_staging_commit):
                with self.assertRaisesRegex(OSError, "intentional promotion failure"):
                    run_build(root=root, transport="curl")
            self.assertEqual((outputs / "run-manifest.json").read_text(encoding="utf-8"), "previous")

    def test_given_prior_outputs_when_backup_cleanup_fails_after_commit_then_new_output_is_successful(self):
        """Given a successful commit, when backup deletion fails, then the new canonical output remains successful."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            outputs = root / "outputs"
            outputs.mkdir()
            (outputs / "run-manifest.json").write_text("previous", encoding="utf-8")
            import live_here.build as build
            original_rmtree = build.shutil.rmtree

            def reject_committed_backup(path, *args, **kwargs):
                if Path(path).name.startswith(".outputs-backup-"):
                    raise OSError("intentional backup cleanup failure")
                return original_rmtree(path, *args, **kwargs)

            with patch("live_here.build.shutil.rmtree", side_effect=reject_committed_backup):
                run_build(root=root, transport="curl")
            self.assertEqual({p.name for p in outputs.iterdir()}, CANONICAL_OUTPUTS)
            self.assertTrue(any(root.glob(".outputs-backup-*")))

    def test_given_previous_output_when_build_repeats_then_it_is_replaced_without_extra_files(self):
        """Given a completed build, when it runs again, then the second canonical set replaces the first."""
        with self.make_repo() as root:
            self.install_ordered_gather_scripts(root)
            run_build(root=root, transport="curl")
            (root / "outputs/accidental-old-file.txt").write_text("old", encoding="utf-8")
            run_build(root=root, transport="curl")
            self.assertEqual({p.name for p in (root / "outputs").iterdir()}, CANONICAL_OUTPUTS)

    def test_given_only_an_interrupted_backup_when_promotion_fails_then_prior_output_survives_for_retry(self):
        """Given only a prior backup, when promotion fails, then that sole prior result is restored for retry."""
        with self.make_repo() as root:
            backup = root / ".outputs-backup-interrupted"
            backup.mkdir()
            (backup / "run-manifest.json").write_text("previous", encoding="utf-8")
            self.install_ordered_gather_scripts(root)
            original_rename = Path.rename

            def reject_staging_commit(path, target):
                if path.name.startswith(".outputs-staging-") and Path(target).name == "outputs":
                    raise OSError("intentional promotion failure")
                return original_rename(path, target)

            with patch.object(Path, "rename", autospec=True, side_effect=reject_staging_commit):
                with self.assertRaisesRegex(OSError, "intentional promotion failure"):
                    run_build(root=root, transport="curl")
            self.assertEqual((root / "outputs/run-manifest.json").read_text(encoding="utf-8"), "previous")
            run_build(root=root, transport="curl")
            self.assertEqual({p.name for p in (root / "outputs").iterdir()}, CANONICAL_OUTPUTS)

    def test_given_cli_help_when_displayed_then_only_build_and_catalog_are_public_commands(self):
        """Given the public CLI, when help is displayed, then removed commands are absent."""
        result = subprocess.run(
            [sys.executable, "-m", "live_here", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONPATH": "src"},
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("build", result.stdout)
        self.assertIn("catalog", result.stdout)
        self.assertNotIn("inventory", result.stdout)
        self.assertNotIn("run", result.stdout)


if __name__ == "__main__":
    unittest.main()
