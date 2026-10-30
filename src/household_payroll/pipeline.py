from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

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


class PipelineAlreadyRunningError(RuntimeError):
    """Another pipeline process holds the execution lock."""


@contextmanager
def exclusive_pipeline_lock(
    lock_path: Path,
) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    acquired = False

    try:
        try:
            file_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as error:
            raise PipelineAlreadyRunningError(
                f"Pipeline lock already exists: {lock_path}"
            ) from error

        acquired = True
        lock_content = {
            "pid": os.getpid(),
            "acquired_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as lock_file:
            json.dump(lock_content, lock_file)

        yield
    finally:
        if acquired:
            lock_path.unlink(missing_ok=True)


def run_fixture_pipeline(
    database_path: Path,
    schema_path: Path,
    submissions_path: Path,
    rates_path: Path,
    approvals_path: Path,
    template_path: Path,
    report_path: Path,
    lock_path: Path,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    with exclusive_pipeline_lock(lock_path):
        submissions_result = ingest_fixture_submissions(
            database_path=database_path,
            schema_path=schema_path,
            fixture_path=submissions_path,
        )
        admin_result = ingest_admin_fixtures(
            database_path=database_path,
            schema_path=schema_path,
            rates_path=rates_path,
            approvals_path=approvals_path,
        )
        reconciliation_result = refresh_reconciliation(
            database_path
        )
        settlement_result = build_settlement(
            database_path=database_path,
            period_start=period_start,
            period_end=period_end,
        )
        report_result = generate_report(
            database_path=database_path,
            template_path=template_path,
            output_path=report_path,
            period_start=period_start,
            period_end=period_end,
        )

    return {
        "status": "ok",
        "submissions": submissions_result,
        "admin": admin_result,
        "reconciliation": reconciliation_result,
        "settlement": settlement_result,
        "report": report_result,
    }
