from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from household_payroll import __version__


def _healthcheck() -> int:
    timezone_name = os.getenv("APP_TIMEZONE", "Europe/Lisbon")
    warnings: list[str] = []
    required_paths = {
        "data": Path(os.getenv("APP_DATA_DIR", "data")),
        "reports": Path(os.getenv("APP_REPORT_DIR", "reports")),
        "logs": Path(os.getenv("APP_LOG_DIR", "logs")),
    }

    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        warnings.append("timezone_database_unavailable")

    for path in required_paths.values():
        path.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "ok",
        "version": __version__,
        "timezone": timezone_name,
        "warnings": warnings,
        "paths": {name: str(path.resolve()) for name, path in required_paths.items()},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="household-payroll")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("healthcheck", help="Validate the local runtime")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "healthcheck":
        raise SystemExit(_healthcheck())
    raise SystemExit(2)


if __name__ == "__main__":
    sys.exit(main())
