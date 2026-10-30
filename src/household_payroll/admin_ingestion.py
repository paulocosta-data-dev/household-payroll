from __future__ import annotations

import csv
import hashlib
import json
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import duckdb

from household_payroll.database import initialize_database


class AdminSourceConflictError(ValueError):
    """An admin record ID was reused with different content."""


def _required(
    row: dict[str, str],
    field_name: str,
) -> str:
    value = row.get(field_name, "").strip()
    if not value:
        raise ValueError(
            f"Missing required field: {field_name}"
        )
    return value


def _canonical_payload(row: dict[str, str]) -> str:
    return json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _content_hash(payload: str) -> str:
    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _observe_admin_record(
    connection: duckdb.DuckDBPyConnection,
    source_table: str,
    source_record_key: str,
    row: dict[str, str],
    observed_at: datetime,
    run_id: str,
) -> bool:
    payload = _canonical_payload(row)
    content_hash = _content_hash(payload)

    existing_hashes = connection.execute(
        """
        SELECT content_hash
        FROM raw.admin_record_observation
        WHERE
            source_table = ?
            AND source_record_key = ?
        """,
        [source_table, source_record_key],
    ).fetchall()

    if existing_hashes:
        if (content_hash,) in existing_hashes:
            return False
        raise AdminSourceConflictError(
            "Admin record changed without a new ID: "
            f"{source_table}/{source_record_key}"
        )

    connection.execute(
        """
        INSERT INTO raw.admin_record_observation
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            source_table,
            source_record_key,
            content_hash,
            payload,
            observed_at,
            run_id,
        ],
    )
    return True


def _approved_minutes(
    work_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
) -> int:
    start_datetime = datetime.combine(
        work_date,
        start_time,
    )
    end_datetime = datetime.combine(
        work_date,
        end_time,
    )
    elapsed_minutes = int(
        (end_datetime - start_datetime).total_seconds()
        // 60
    )
    approved_minutes = elapsed_minutes - break_minutes

    if break_minutes < 0 or approved_minutes <= 0:
        raise ValueError(
            f"Invalid approved duration for {work_date}"
        )

    return approved_minutes


def _read_csv_rows(
    fixture_path: Path,
) -> list[dict[str, str]]:
    with fixture_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as fixture_file:
        return list(csv.DictReader(fixture_file))


def ingest_admin_fixtures(
    database_path: Path,
    schema_path: Path,
    rates_path: Path,
    approvals_path: Path,
) -> dict[str, Any]:
    initialize_database(database_path, schema_path)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    observed_at = started_at

    inserted_rates = 0
    skipped_rates = 0
    inserted_approvals = 0
    skipped_approvals = 0

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO raw.ingestion_run (
                run_id,
                source_name,
                started_at,
                status
            )
            VALUES (?, ?, ?, 'running')
            """,
            [run_id, "admin-fixtures", started_at],
        )

        try:
            connection.execute("BEGIN TRANSACTION")

            for row in _read_csv_rows(rates_path):
                rate_id = _required(row, "rate_id")
                valid_from = date.fromisoformat(
                    _required(row, "valid_from")
                )
                valid_to_text = row.get(
                    "valid_to",
                    "",
                ).strip()
                valid_to = (
                    date.fromisoformat(valid_to_text)
                    if valid_to_text
                    else None
                )
                hourly_rate_cents = int(
                    _required(row, "hourly_rate_cents")
                )

                if hourly_rate_cents <= 0:
                    raise ValueError(
                        f"Invalid rate: {rate_id}"
                    )
                if (
                    valid_to is not None
                    and valid_to <= valid_from
                ):
                    raise ValueError(
                        f"Invalid rate period: {rate_id}"
                    )

                is_new = _observe_admin_record(
                    connection,
                    "rate_versions",
                    rate_id,
                    row,
                    observed_at,
                    run_id,
                )

                if not is_new:
                    skipped_rates += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO core.rate_version
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        rate_id,
                        valid_from,
                        valid_to,
                        hourly_rate_cents,
                    ],
                )
                inserted_rates += 1

            for row in _read_csv_rows(approvals_path):
                approval_id = _required(
                    row,
                    "approval_id",
                )
                work_date = date.fromisoformat(
                    _required(row, "work_date")
                )
                start_time = time.fromisoformat(
                    _required(row, "start_time")
                )
                end_time = time.fromisoformat(
                    _required(row, "end_time")
                )
                break_minutes = int(
                    _required(row, "break_minutes")
                )
                status = _required(row, "status")
                decided_at = datetime.fromisoformat(
                    _required(row, "decided_at")
                )
                reason = _required(row, "reason")
                supersedes_approval_id = (
                    row.get(
                        "supersedes_approval_id",
                        "",
                    ).strip()
                    or None
                )

                if status not in {
                    "approved",
                    "rejected",
                    "superseded",
                }:
                    raise ValueError(
                        f"Invalid approval status: {status}"
                    )
                if decided_at.tzinfo is None:
                    raise ValueError(
                        "decided_at must include a timezone: "
                        f"{approval_id}"
                    )

                approved_minutes = _approved_minutes(
                    work_date,
                    start_time,
                    end_time,
                    break_minutes,
                )

                is_new = _observe_admin_record(
                    connection,
                    "work_approvals",
                    approval_id,
                    row,
                    observed_at,
                    run_id,
                )

                if not is_new:
                    skipped_approvals += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO core.work_approval
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        approval_id,
                        work_date,
                        start_time,
                        end_time,
                        break_minutes,
                        approved_minutes,
                        status,
                        decided_at,
                        reason,
                        supersedes_approval_id,
                    ],
                )
                inserted_approvals += 1

            inserted_total = (
                inserted_rates + inserted_approvals
            )
            connection.execute(
                """
                UPDATE raw.ingestion_run
                SET
                    completed_at = ?,
                    status = 'succeeded',
                    row_count = ?
                WHERE run_id = ?
                """,
                [
                    datetime.now(timezone.utc),
                    inserted_total,
                    run_id,
                ],
            )
            connection.execute("COMMIT")
        except Exception as error:
            connection.execute("ROLLBACK")
            connection.execute(
                """
                UPDATE raw.ingestion_run
                SET
                    completed_at = ?,
                    status = 'failed',
                    error_message = ?
                WHERE run_id = ?
                """,
                [
                    datetime.now(timezone.utc),
                    str(error)[:1000],
                    run_id,
                ],
            )
            raise

    return {
        "status": "ok",
        "run_id": run_id,
        "inserted_rates": inserted_rates,
        "skipped_rates": skipped_rates,
        "inserted_approvals": inserted_approvals,
        "skipped_approvals": skipped_approvals,
    }
