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
        "paths": {
            name: str(path.resolve())
            for name, path in required_paths.items()
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _database_path() -> Path:
    data_directory = Path(
        os.getenv("APP_DATA_DIR", "data")
    )
    return Path(
        os.getenv(
            "APP_DATABASE_PATH",
            str(data_directory / "household-payroll.duckdb"),
        )
    )


def _schema_path() -> Path:
    return Path(
        os.getenv("APP_SCHEMA_PATH", "sql/001_initial.sql")
    )


def _init_database() -> int:
    from household_payroll.database import initialize_database

    database_path = _database_path()
    schema_path = _schema_path()
    tables = initialize_database(
        database_path,
        schema_path,
    )

    result = {
        "status": "ok",
        "database": str(database_path.resolve()),
        "schema": str(schema_path.resolve()),
        "tables": tables,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _ingest_fixtures() -> int:
    from household_payroll.ingestion import (
        ingest_fixture_submissions,
    )

    fixture_path = Path(
        os.getenv(
            "APP_SUBMISSIONS_FIXTURE",
            "examples/fixtures/submissions.csv",
        )
    )

    result = ingest_fixture_submissions(
        database_path=_database_path(),
        schema_path=_schema_path(),
        fixture_path=fixture_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="household-payroll"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )
    subparsers.add_parser(
        "healthcheck",
        help="Validate the local runtime",
    )
    subparsers.add_parser(
        "init-db",
        help="Create or update the DuckDB schema",
    )
    subparsers.add_parser(
        "ingest-fixtures",
        help="Ingest the fictitious submission fixture",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "healthcheck":
        raise SystemExit(_healthcheck())

    if args.command == "init-db":
        raise SystemExit(_init_database())

    if args.command == "ingest-fixtures":
        raise SystemExit(_ingest_fixtures())

    raise SystemExit(2)


if __name__ == "__main__":
    sys.exit(main())
