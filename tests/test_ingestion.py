from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb

from household_payroll.ingestion import (
    SourceConflictError,
    ingest_fixture_submissions,
)


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema_path = Path("sql/001_initial.sql")
        self.fixture_path = Path(
            "examples/fixtures/submissions.csv"
        )

    def test_repeated_ingestion_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.duckdb"

            first_result = ingest_fixture_submissions(
                database_path,
                self.schema_path,
                self.fixture_path,
            )
            second_result = ingest_fixture_submissions(
                database_path,
                self.schema_path,
                self.fixture_path,
            )

        self.assertEqual(first_result["inserted_rows"], 5)
        self.assertEqual(first_result["skipped_rows"], 0)
        self.assertEqual(second_result["inserted_rows"], 0)
        self.assertEqual(second_result["skipped_rows"], 5)
        self.assertEqual(second_result["total_submissions"], 5)

    def test_changed_source_record_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_path = Path(directory)
            database_path = temporary_path / "test.duckdb"
            changed_fixture_path = (
                temporary_path / "changed-submissions.csv"
            )

            original_content = self.fixture_path.read_text(
                encoding="utf-8"
            )
            changed_content = original_content.replace(
                ",09:00,13:00,15,",
                ",08:00,13:00,15,",
                1,
            )
            changed_fixture_path.write_text(
                changed_content,
                encoding="utf-8",
            )

            ingest_fixture_submissions(
                database_path,
                self.schema_path,
                self.fixture_path,
            )

            with self.assertRaises(SourceConflictError):
                ingest_fixture_submissions(
                    database_path,
                    self.schema_path,
                    changed_fixture_path,
                )

            with duckdb.connect(
                str(database_path),
                read_only=True,
            ) as connection:
                submission_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM raw.form_submission
                    """
                ).fetchone()[0]
                run_statuses = connection.execute(
                    """
                    SELECT status
                    FROM raw.ingestion_run
                    ORDER BY started_at
                    """
                ).fetchall()

        self.assertEqual(submission_count, 5)
        self.assertEqual(
            run_statuses,
            [("succeeded",), ("failed",)],
        )


if __name__ == "__main__":
    unittest.main()
