"""Local commands; never execute files found during inventory."""

import argparse
import json
from pathlib import Path

from .catalog import catalog
from .io import sha256
from .pipeline import run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Source-only county comparison starter")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="Show V1 factor scope and implementation status")
    inv = commands.add_parser("inventory", help="List local files with sizes and SHA-256 hashes")
    inv.add_argument("directory", type=Path)
    execute = commands.add_parser("run", help="Run an explicit demo or research configuration")
    execute.add_argument("--config", required=True, type=Path)
    execute.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = catalog()
        elif args.command == "inventory":
            if not args.directory.is_dir():
                raise ValueError(f"Directory not found: {args.directory}")
            result = [{"path": str(p.relative_to(args.directory)), "bytes": p.stat().st_size,
                       "sha256": sha256(p)} for p in sorted(args.directory.rglob("*"))
                      if p.is_file() and not p.is_symlink() and ".git" not in p.parts]
        else:
            result = run(args.config, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Error: {exc}\n")
