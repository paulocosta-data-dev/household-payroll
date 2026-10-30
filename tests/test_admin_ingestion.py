from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb

from household_payroll.admin_ingestion import (
    AdminSourceConflictError,
    ingest_admin_fixtures,
)


class AdminIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema_path = Path("sql/001_initial.sql")
        self.rates_path = Path(
            "examples/fixtures/rate_versions.csv"
        )
        self.approvals_path = Path(
            "examples/fixtures/approvals.csv"
        )

    def test_repeated_admin_ingestion_is_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.duckdb"

            first_result = ingest_admin_fixtures(
                database_path,
                self.schema_path,
                self.rates_path,
                self.approvals_path,
            )
            second_result = ingest_admin_fixtures(
                database_path,
                self.schema_path,
                self.rates_path,
                self.approvals_path,
            )

            with duckdb.connect(
                str(database_path),
                read_only=True,
            ) as connection:
                observation_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM raw.admin_record_observation
                    """
                ).fetchone()[0]
                rate_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM core.rate_version
                    """
                ).fetchone()[0]
                approval_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM core.work_approval
                    """
                ).fetchone()[0]

        self.assertEqual(first_result["inserted_rates"], 1)
        self.assertEqual(first_result["inserted_approvals"], 3)
        self.assertEqual(second_result["skipped_rates"], 1)
        self.assertEqual(
            second_result["skipped_approvals"],
            3,
        )
        self.assertEqual(observation_count, 4)
        self.assertEqual(rate_count, 1)
        self.assertEqual(approval_count, 3)

    def test_changed_admin_record_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_path = Path(directory)
            database_path = temporary_path / "test.duckdb"
            changed_rates_path = (
                temporary_path / "changed-rates.csv"
            )

            changed_rates_path.write_text(
                self.rates_path.read_text(
                    encoding="utf-8"
                ).replace(",1200", ",1300"),
                encoding="utf-8",
            )

            ingest_admin_fixtures(
                database_path,
                self.schema_path,
                self.rates_path,
                self.approvals_path,
            )

            with self.assertRaises(
                AdminSourceConflictError
            ):
                ingest_admin_fixtures(
                    database_path,
                    self.schema_path,
                    changed_rates_path,
                    self.approvals_path,
                )

            with duckdb.connect(
                str(database_path),
                read_only=True,
            ) as connection:
                stored_rate = connection.execute(
                    """
                    SELECT hourly_rate_cents
                    FROM core.rate_version
                    WHERE rate_id = 'rate-001'
                    """
                ).fetchone()[0]
                statuses = connection.execute(
                    """
                    SELECT status
                    FROM raw.ingestion_run
                    ORDER BY started_at
                    """
                ).fetchall()

        self.assertEqual(stored_rate, 1200)
        self.assertEqual(
            statuses,
            [("succeeded",), ("failed",)],
        )


if __name__ == "__main__":
    unittest.main()
