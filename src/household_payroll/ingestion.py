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


class SourceConflictError(ValueError):
    """A source key was reused with different content."""


def _content_hash(row: dict[str, str]) -> str:
    canonical_content = json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        canonical_content.encode("utf-8")
    ).hexdigest()


def _required_value(
    row: dict[str, str],
    field_name: str,
) -> str:
    value = row.get(field_name, "").strip()
    if not value:
        raise ValueError(
            f"Missing required field: {field_name}"
        )
    return value


def _parse_submission(
    row: dict[str, str],
) -> dict[str, Any]:
    source_record_key = _required_value(
        row,
        "source_record_key",
    )
    author_id = _required_value(row, "author_id")

    if author_id not in {"employer", "worker"}:
        raise ValueError(
            f"Invalid author_id for {source_record_key}"
        )

    submitted_at_text = _required_value(
        row,
        "submitted_at",
    )
    work_date_text = _required_value(row, "work_date")
    start_time_text = _required_value(row, "start_time")
    end_time_text = _required_value(row, "end_time")
    break_minutes_text = _required_value(
        row,
        "break_minutes",
    )

    submitted_at = datetime.fromisoformat(
        submitted_at_text
    )
    if submitted_at.tzinfo is None:
        raise ValueError(
            f"submitted_at must include a timezone: "
            f"{source_record_key}"
        )

    work_date = date.fromisoformat(work_date_text)
    start_time = time.fromisoformat(start_time_text)
    end_time = time.fromisoformat(end_time_text)
    break_minutes = int(break_minutes_text)

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

    if break_minutes < 0:
        raise ValueError(
            f"Negative break for {source_record_key}"
        )

    worked_minutes = elapsed_minutes - break_minutes
    if worked_minutes <= 0:
        raise ValueError(
            f"Non-positive duration for {source_record_key}"
        )

    return {
        "source_record_key": source_record_key,
        "author_id": author_id,
        "submitted_at_text": submitted_at_text,
        "submitted_at": submitted_at,
        "work_date_text": work_date_text,
        "work_date": work_date,
        "start_time_text": start_time_text,
        "start_time": start_time,
        "end_time_text": end_time_text,
        "end_time": end_time,
        "break_minutes_text": break_minutes_text,
        "break_minutes": break_minutes,
        "worked_minutes": worked_minutes,
        "notes": row.get("notes", "").strip() or None,
        "content_hash": _content_hash(row),
    }


def ingest_fixture_submissions(
    database_path: Path,
    schema_path: Path,
    fixture_path: Path,
) -> dict[str, Any]:
    initialize_database(database_path, schema_path)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    inserted_rows = 0
    skipped_rows = 0

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
            [run_id, fixture_path.name, started_at],
        )

        try:
            connection.execute("BEGIN TRANSACTION")

            with fixture_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as fixture_file:
                reader = csv.DictReader(fixture_file)

                for source_row in reader:
                    parsed = _parse_submission(source_row)
                    source_record_key = parsed[
                        "source_record_key"
                    ]

                    existing = connection.execute(
                        """
                        SELECT content_hash
                        FROM raw.form_submission
                        WHERE source_record_key = ?
                        """,
                        [source_record_key],
                    ).fetchone()

                    if existing is not None:
                        if existing[0] != parsed["content_hash"]:
                            raise SourceConflictError(
                                "Source record changed: "
                                f"{source_record_key}"
                            )
                        skipped_rows += 1
                        continue

                    ingested_at = datetime.now(timezone.utc)

                    connection.execute(
                        """
                        INSERT INTO raw.form_submission
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        [
                            source_record_key,
                            parsed["author_id"],
                            parsed["submitted_at_text"],
                            parsed["work_date_text"],
                            parsed["start_time_text"],
                            parsed["end_time_text"],
                            parsed["break_minutes_text"],
                            parsed["notes"],
                            parsed["content_hash"],
                            ingested_at,
                            run_id,
                        ],
                    )

                    connection.execute(
                        """
                        INSERT INTO core.work_submission
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        [
                            source_record_key,
                            source_record_key,
                            parsed["author_id"],
                            parsed["submitted_at"],
                            parsed["work_date"],
                            parsed["start_time"],
                            parsed["end_time"],
                            parsed["break_minutes"],
                            parsed["worked_minutes"],
                            parsed["notes"],
                            ingested_at,
                        ],
                    )
                    inserted_rows += 1

            completed_at = datetime.now(timezone.utc)
            connection.execute(
                """
                UPDATE raw.ingestion_run
                SET
                    completed_at = ?,
                    status = 'succeeded',
                    row_count = ?
                WHERE run_id = ?
                """,
                [completed_at, inserted_rows, run_id],
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

        total_submissions = connection.execute(
            """
            SELECT COUNT(*)
            FROM core.work_submission
            """
        ).fetchone()[0]

    return {
        "status": "ok",
        "run_id": run_id,
        "inserted_rows": inserted_rows,
        "skipped_rows": skipped_rows,
        "total_submissions": total_submissions,
    }
