from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import duckdb

from household_payroll.admin_ingestion import (
    ingest_admin_fixtures,
)
from household_payroll.ingestion import (
    ingest_fixture_submissions,
)
from household_payroll.reconciliation import (
    refresh_reconciliation,
)
from household_payroll.settlement import (
    build_settlement,
    calculate_gross_cents,
)


class SettlementTests(unittest.TestCase):
    def test_builds_expected_fixture_settlement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.duckdb"
            schema_path = Path("sql/001_initial.sql")

            ingest_fixture_submissions(
                database_path,
                schema_path,
                Path("examples/fixtures/submissions.csv"),
            )
            ingest_admin_fixtures(
                database_path,
                schema_path,
                Path("examples/fixtures/rate_versions.csv"),
                Path("examples/fixtures/approvals.csv"),
            )
            refresh_reconciliation(database_path)

            first_result = build_settlement(
                database_path,
                date(2026, 9, 28),
                date(2026, 10, 27),
            )
            second_result = build_settlement(
                database_path,
                date(2026, 9, 28),
                date(2026, 10, 27),
            )

            with duckdb.connect(
                str(database_path),
                read_only=True,
            ) as connection:
                payment_lines = connection.execute(
                    """
                    SELECT
                        work_date,
                        approved_minutes,
                        gross_amount_cents
                    FROM mart.payment_line
                    ORDER BY work_date
                    """
                ).fetchall()
                summary_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM mart.payment_summary
                    """
                ).fetchone()[0]

        self.assertEqual(first_result["approved_visits"], 3)
        self.assertEqual(
            first_result["approved_minutes"],
            675,
        )
        self.assertEqual(
            first_result["gross_amount_cents"],
            13500,
        )
        self.assertEqual(first_result, second_result)
        self.assertEqual(len(payment_lines), 3)
        self.assertEqual(summary_count, 1)

    def test_rounds_each_line_half_up(self) -> None:
        self.assertEqual(
            calculate_gross_cents(
                approved_minutes=1,
                hourly_rate_cents=1000,
            ),
            17,
        )


if __name__ == "__main__":
    unittest.main()
