from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from household_payroll.database import initialize_database


EXPECTED_TABLES = [
    "core.rate_version",
    "core.reconciliation",
    "core.work_approval",
    "core.work_submission",
    "mart.payment_line",
    "mart.payment_summary",
    "raw.form_submission",
    "raw.ingestion_run",
]


class DatabaseTests(unittest.TestCase):
    def test_initialization_is_idempotent(self) -> None:
        schema_path = Path("sql/001_initial.sql")

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = (
                Path(temporary_directory)
                / "test.duckdb"
            )

            first_result = initialize_database(
                database_path,
                schema_path,
            )
            second_result = initialize_database(
                database_path,
                schema_path,
            )

        self.assertEqual(first_result, EXPECTED_TABLES)
        self.assertEqual(second_result, EXPECTED_TABLES)


if __name__ == "__main__":
    unittest.main()
