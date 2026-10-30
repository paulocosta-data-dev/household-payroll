from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from household_payroll.admin_ingestion import (
    ingest_admin_fixtures,
)
from household_payroll.ingestion import (
    ingest_fixture_submissions,
)
from household_payroll.reconciliation import (
    refresh_reconciliation,
)
from household_payroll.reporting import generate_report
from household_payroll.settlement import build_settlement


class ReportingTests(unittest.TestCase):
    def test_generates_expected_static_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_path = Path(directory)
            database_path = temporary_path / "test.duckdb"
            output_path = temporary_path / "index.html"
            schema_path = Path("sql/001_initial.sql")
            period_start = date(2026, 9, 28)
            period_end = date(2026, 10, 27)

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
            build_settlement(
                database_path,
                period_start,
                period_end,
            )

            result = generate_report(
                database_path=database_path,
                template_path=Path(
                    "templates/report.html.j2"
                ),
                output_path=output_path,
                period_start=period_start,
                period_end=period_end,
            )

            rendered_html = output_path.read_text(
                encoding="utf-8"
            )

        self.assertEqual(result["payment_lines"], 3)
        self.assertEqual(
            result["gross_amount_cents"],
            13500,
        )
        self.assertIn("135,00 EUR", rendered_html)
        self.assertIn("11,25", rendered_html)
        self.assertIn("Divergências", rendered_html)
        self.assertNotIn("<button", rendered_html)
        self.assertIn("click-cleaner", rendered_html)
        self.assertIn("PRONTO", rendered_html)
        self.assertIn("broomSvg", rendered_html)


if __name__ == "__main__":
    unittest.main()
