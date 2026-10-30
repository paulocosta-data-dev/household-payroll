from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import duckdb


CALCULATION_RULE_VERSION = (
    "gross-v1-line-round-half-up"
)


class SettlementRuleError(ValueError):
    """The approved data cannot produce one settlement."""


def calculate_gross_cents(
    approved_minutes: int,
    hourly_rate_cents: int,
) -> int:
    exact_cents = (
        Decimal(approved_minutes)
        * Decimal(hourly_rate_cents)
        / Decimal(60)
    )
    return int(
        exact_cents.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def build_settlement(
    database_path: Path,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    if period_end < period_start:
        raise SettlementRuleError(
            "period_end must not precede period_start"
        )

    with duckdb.connect(str(database_path)) as connection:
        approvals = connection.execute(
            """
            SELECT
                approval.approval_id,
                approval.work_date,
                approval.approved_minutes
            FROM core.work_approval AS approval
            WHERE
                approval.status = 'approved'
                AND approval.work_date BETWEEN ? AND ?
                AND NOT EXISTS (
                    SELECT 1
                    FROM core.work_approval AS replacement
                    WHERE
                        replacement.supersedes_approval_id =
                            approval.approval_id
                )
            ORDER BY approval.work_date, approval.decided_at
            """,
            [period_start, period_end],
        ).fetchall()

        approval_counts = Counter(
            approval[1] for approval in approvals
        )
        duplicate_dates = sorted(
            work_date
            for work_date, count in approval_counts.items()
            if count > 1
        )
        if duplicate_dates:
            raise SettlementRuleError(
                "Multiple current approvals for: "
                + ", ".join(
                    work_date.isoformat()
                    for work_date in duplicate_dates
                )
            )

        payment_lines: list[list[Any]] = []

        for (
            approval_id,
            work_date,
            approved_minutes,
        ) in approvals:
            rates = connection.execute(
                """
                SELECT rate_id, hourly_rate_cents
                FROM core.rate_version
                WHERE
                    valid_from <= ?
                    AND (
                        valid_to IS NULL
                        OR ? < valid_to
                    )
                ORDER BY valid_from
                """,
                [work_date, work_date],
            ).fetchall()

            if len(rates) != 1:
                raise SettlementRuleError(
                    "Expected exactly one rate for "
                    f"{work_date}; found {len(rates)}"
                )

            rate_id, hourly_rate_cents = rates[0]
            gross_amount_cents = calculate_gross_cents(
                approved_minutes,
                hourly_rate_cents,
            )

            payment_lines.append(
                [
                    f"work:{approval_id}",
                    work_date,
                    approval_id,
                    rate_id,
                    approved_minutes,
                    hourly_rate_cents,
                    gross_amount_cents,
                    CALCULATION_RULE_VERSION,
                ]
            )

        approved_minutes_total = sum(
            line[4] for line in payment_lines
        )
        gross_amount_cents_total = sum(
            line[6] for line in payment_lines
        )
        generated_at = datetime.now(timezone.utc)

        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(
                """
                DELETE FROM mart.payment_line
                WHERE work_date BETWEEN ? AND ?
                """,
                [period_start, period_end],
            )
            connection.execute(
                """
                DELETE FROM mart.payment_summary
                WHERE
                    period_start = ?
                    AND period_end = ?
                """,
                [period_start, period_end],
            )

            if payment_lines:
                connection.executemany(
                    """
                    INSERT INTO mart.payment_line
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payment_lines,
                )

            connection.execute(
                """
                INSERT INTO mart.payment_summary
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    period_start,
                    period_end,
                    len(payment_lines),
                    approved_minutes_total,
                    gross_amount_cents_total,
                    generated_at,
                ],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    return {
        "status": "ok",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "approved_visits": len(payment_lines),
        "approved_minutes": approved_minutes_total,
        "gross_amount_cents": gross_amount_cents_total,
        "calculation_rule_version": (
            CALCULATION_RULE_VERSION
        ),
    }
