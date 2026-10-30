from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import duckdb


class DuplicateDailySubmissionError(ValueError):
    """More than one submission exists for an author and day."""


def refresh_reconciliation(
    database_path: Path,
) -> dict[str, Any]:
    with duckdb.connect(str(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                submission_id,
                author_id,
                work_date,
                start_time,
                end_time,
                break_minutes,
                worked_minutes
            FROM core.work_submission
            ORDER BY work_date, author_id, submitted_at
            """
        ).fetchall()

        submissions_by_date: dict[
            date,
            dict[str, tuple[Any, ...]],
        ] = {}

        for row in rows:
            submission_id = row[0]
            author_id = row[1]
            work_date = row[2]

            daily_submissions = submissions_by_date.setdefault(
                work_date,
                {},
            )

            if author_id in daily_submissions:
                raise DuplicateDailySubmissionError(
                    "Multiple submissions for "
                    f"{author_id} on {work_date}"
                )

            daily_submissions[author_id] = (
                submission_id,
                row[3],
                row[4],
                row[5],
                row[6],
            )

        reconciliation_rows: list[list[Any]] = []
        status_counts: Counter[str] = Counter()

        for work_date in sorted(submissions_by_date):
            daily_submissions = submissions_by_date[work_date]
            employer = daily_submissions.get("employer")
            worker = daily_submissions.get("worker")

            if employer is not None and worker is not None:
                start_time_matches = employer[1] == worker[1]
                end_time_matches = employer[2] == worker[2]
                break_matches = employer[3] == worker[3]
                duration_matches = employer[4] == worker[4]

                if (
                    start_time_matches
                    and end_time_matches
                    and break_matches
                ):
                    status = "matched"
                else:
                    status = "divergent"
            elif employer is not None:
                status = "employer_only"
                start_time_matches = None
                end_time_matches = None
                break_matches = None
                duration_matches = None
            else:
                status = "worker_only"
                start_time_matches = None
                end_time_matches = None
                break_matches = None
                duration_matches = None

            status_counts[status] += 1

            reconciliation_rows.append(
                [
                    work_date,
                    employer[0] if employer else None,
                    worker[0] if worker else None,
                    status,
                    start_time_matches,
                    end_time_matches,
                    break_matches,
                    duration_matches,
                ]
            )

        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(
                "DELETE FROM core.reconciliation"
            )
            connection.executemany(
                """
                INSERT INTO core.reconciliation
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                reconciliation_rows,
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    return {
        "status": "ok",
        "total_work_dates": len(reconciliation_rows),
        "status_counts": dict(sorted(status_counts.items())),
    }
