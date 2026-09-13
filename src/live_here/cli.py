"""Local public commands for Live Here."""

import argparse
import json
import subprocess

from .build import run_build
from .catalog import catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description="Source-only county comparison starter")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build current source outputs")
    build.add_argument("--transport", choices=["python", "curl"], default="python")
    commands.add_parser("catalog", help="Show V1 factor scope and implementation status")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            print(json.dumps(catalog(), indent=2))
        else:
            run_build(transport=args.transport)
        return 0
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Error: {exc}\n")
