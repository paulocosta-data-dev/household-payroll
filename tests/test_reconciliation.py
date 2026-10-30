from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb

from household_payroll.ingestion import (
    ingest_fixture_submissions,
)
from household_payroll.reconciliation import (
    refresh_reconciliation,
)


class ReconciliationTests(unittest.TestCase):
    def test_reconciles_each_work_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.duckdb"

            ingest_fixture_submissions(
                database_path=database_path,
                schema_path=Path("sql/001_initial.sql"),
                fixture_path=Path(
                    "examples/fixtures/submissions.csv"
                ),
            )

            result = refresh_reconciliation(database_path)

            with duckdb.connect(
                str(database_path),
                read_only=True,
            ) as connection:
                rows = connection.execute(
                    """
                    SELECT
                        work_date,
                        status,
                        start_time_matches,
                        end_time_matches,
                        break_matches,
                        duration_matches
                    FROM core.reconciliation
                    ORDER BY work_date
                    """
                ).fetchall()

        self.assertEqual(result["total_work_dates"], 3)
        self.assertEqual(
            result["status_counts"],
            {
                "divergent": 1,
                "employer_only": 1,
                "matched": 1,
            },
        )

        self.assertEqual(rows[0][1], "matched")

        self.assertEqual(rows[1][1], "divergent")
        self.assertFalse(rows[1][2])
        self.assertFalse(rows[1][3])
        self.assertTrue(rows[1][4])
        self.assertTrue(rows[1][5])

        self.assertEqual(rows[2][1], "employer_only")
        self.assertIsNone(rows[2][2])


if __name__ == "__main__":
    unittest.main()
