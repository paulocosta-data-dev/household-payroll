from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from household_payroll.pipeline import (
    PipelineAlreadyRunningError,
    run_fixture_pipeline,
)


class PipelineTests(unittest.TestCase):
    def _run_pipeline(
        self,
        temporary_path: Path,
    ) -> dict:
        return run_fixture_pipeline(
            database_path=temporary_path / "test.duckdb",
            schema_path=Path("sql/001_initial.sql"),
            submissions_path=Path(
                "examples/fixtures/submissions.csv"
            ),
            rates_path=Path(
                "examples/fixtures/rate_versions.csv"
            ),
            approvals_path=Path(
                "examples/fixtures/approvals.csv"
            ),
            template_path=Path(
                "templates/report.html.j2"
            ),
            report_path=temporary_path / "index.html",
            lock_path=temporary_path / "pipeline.lock",
            period_start=date(2026, 9, 28),
            period_end=date(2026, 10, 27),
        )

    def test_pipeline_runs_end_to_end_idempotently(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_path = Path(directory)

            first_result = self._run_pipeline(
                temporary_path
            )
            second_result = self._run_pipeline(
                temporary_path
            )

            report_path = temporary_path / "index.html"
            report_content = report_path.read_text(
                encoding="utf-8"
            )
            lock_exists = (
                temporary_path / "pipeline.lock"
            ).exists()

        self.assertEqual(first_result["status"], "ok")
        self.assertEqual(
            first_result["settlement"][
                "gross_amount_cents"
            ],
            13500,
        )
        self.assertEqual(
            first_result["submissions"]["inserted_rows"],
            5,
        )
        self.assertEqual(
            second_result["submissions"]["skipped_rows"],
            5,
        )
        self.assertIn("135,00 EUR", report_content)
        self.assertFalse(lock_exists)

    def test_existing_lock_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_path = Path(directory)
            lock_path = temporary_path / "pipeline.lock"
            lock_path.write_text(
                "existing lock",
                encoding="utf-8",
            )

            with self.assertRaises(
                PipelineAlreadyRunningError
            ):
                self._run_pipeline(temporary_path)

            self.assertTrue(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
