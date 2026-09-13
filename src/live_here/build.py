"""Thin clean-build orchestration for the public CLI."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .pipeline import run as run_pipeline

GATHER_SCRIPTS = [
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
    "coverage.json",
    "run-manifest.json",
}


def _require_repo_root(root):
    required = [root / "pyproject.toml", root / "src/live_here", root / "scripts"]
    if not all(path.exists() for path in required):
        raise ValueError("Run build from the repository root")
    missing = [script for script in GATHER_SCRIPTS if not (root / "scripts" / script).is_file()]
    if missing:
        raise ValueError(f"Missing gather scripts: {', '.join(missing)}")


def _remove_tree(path):
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Expected directory: {path}")
        shutil.rmtree(path)


def _clean_stale_scratch(root):
    for path in root.glob(".outputs-staging-*"):
        if path.is_dir():
            shutil.rmtree(path)
    outputs = root / "outputs"
    backups = sorted(path for path in root.glob(".outputs-backup-*") if path.is_dir())
    if outputs.exists():
        for path in backups:
            shutil.rmtree(path)
    elif len(backups) == 1:
        backups[0].rename(outputs)
    elif len(backups) > 1:
        raise OSError("Multiple prior output backups found; preserved all backups for manual recovery")


def _validate_canonical_outputs(path):
    if not path.is_dir():
        raise ValueError("Pipeline did not create an output directory")
    found = {entry.name for entry in path.iterdir()}
    if found != CANONICAL_OUTPUTS or any(not (path / name).is_file() for name in found):
        raise ValueError(f"Output directory must contain exactly: {sorted(CANONICAL_OUTPUTS)}")


def _promote_outputs(root, staging):
    outputs = root / "outputs"
    backup = root / f".outputs-backup-{os.getpid()}"
    if backup.exists():
        if not outputs.exists():
            raise OSError(f"Refusing to remove the only prior output backup: {backup}")
        shutil.rmtree(backup)
    moved_outputs = False
    if outputs.exists():
        outputs.rename(backup)
        moved_outputs = True
    try:
        staging.rename(outputs)
    except OSError as promote_error:
        if moved_outputs:
            try:
                backup.rename(outputs)
            except OSError as restore_error:
                raise RuntimeError(
                    f"Failed to promote outputs and could not restore previous outputs; preserved backup at {backup}"
                ) from restore_error
        raise promote_error

    if backup.exists():
        try:
            shutil.rmtree(backup)
        except OSError as cleanup_error:
            print(f"Warning: committed outputs but could not remove backup {backup}: {cleanup_error}", file=sys.stderr)


def run_build(root=None, transport="python"):
    root = Path.cwd() if root is None else Path(root)
    root = root.resolve()
    if transport not in {"python", "curl"}:
        raise ValueError("transport must be python or curl")
    _require_repo_root(root)
    _clean_stale_scratch(root)

    current = root / "data/interim/current"
    _remove_tree(current)
    current.mkdir(parents=True)

    total = len(GATHER_SCRIPTS) + 1
    for index, script in enumerate(GATHER_SCRIPTS, 1):
        print(f"[{index}/{total}] {script}", file=sys.stderr)
        subprocess.run(
            [sys.executable, str(root / "scripts" / script), "--transport", transport],
            check=True,
            cwd=root,
        )

    staging = root / f".outputs-staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    print(f"[{total}/{total}] final ranking pipeline", file=sys.stderr)
    try:
        run_pipeline(current / "config.json", staging)
        _validate_canonical_outputs(staging)
        _promote_outputs(root, staging)
    except Exception:
        if staging.exists():
            try:
                shutil.rmtree(staging)
            except OSError as cleanup_error:
                print(
                    f"Warning: build failed and staging cleanup also failed for {staging}: {cleanup_error}",
                    file=sys.stderr,
                )
        raise
    print("Build complete: outputs/")
