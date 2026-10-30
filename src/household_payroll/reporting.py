from __future__ import annotations

import os
from datetime import date, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)


class ReportDataError(ValueError):
    """The requested settlement is not available."""


def _format_eur(cents: int) -> str:
    absolute_cents = abs(cents)
    euros = absolute_cents // 100
    remainder = absolute_cents % 100
    grouped_euros = f"{euros:,}".replace(",", ".")
    sign = "-" if cents < 0 else ""
    return f"{sign}{grouped_euros},{remainder:02d} EUR"


def _format_hours(minutes: int) -> str:
    hours = (
        Decimal(minutes) / Decimal(60)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return f"{hours}".replace(".", ",")


def generate_report(
    database_path: Path,
    template_path: Path,
    output_path: Path,
    period_start: date,
    period_end: date,
    timezone_name: str = "Europe/Lisbon",
) -> dict[str, Any]:
    with duckdb.connect(
        str(database_path),
        read_only=True,
    ) as connection:
        summary = connection.execute(
            """
            SELECT
                approved_visits,
                approved_minutes,
                gross_amount_cents,
                generated_at
            FROM mart.payment_summary
            WHERE
                period_start = ?
                AND period_end = ?
            """,
            [period_start, period_end],
        ).fetchone()

        if summary is None:
            raise ReportDataError(
                "No settlement summary for "
                f"{period_start} to {period_end}"
            )

        lines = connection.execute(
            """
            SELECT
                work_date,
                approval_id,
                approved_minutes,
                hourly_rate_cents,
                gross_amount_cents
            FROM mart.payment_line
            WHERE work_date BETWEEN ? AND ?
            ORDER BY work_date
            """,
            [period_start, period_end],
        ).fetchall()

        reconciliation_counts = dict(
            connection.execute(
                """
                SELECT status, COUNT(*)
                FROM core.reconciliation
                WHERE work_date BETWEEN ? AND ?
                GROUP BY status
                """,
                [period_start, period_end],
            ).fetchall()
        )

    generated_at = summary[3]
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(
            tzinfo=timezone.utc
        )
    generated_at = generated_at.astimezone(
        ZoneInfo(timezone_name)
    )

    payment_lines = [
        {
            "work_date": work_date.isoformat(),
            "approval_id": approval_id,
            "approved_minutes": approved_minutes,
            "approved_hours": _format_hours(
                approved_minutes
            ),
            "hourly_rate": (
                _format_eur(hourly_rate_cents)
                + "/h"
            ),
            "gross_amount": _format_eur(
                gross_amount_cents
            ),
        }
        for (
            work_date,
            approval_id,
            approved_minutes,
            hourly_rate_cents,
            gross_amount_cents,
        ) in lines
    ]

    environment = Environment(
        loader=FileSystemLoader(
            str(template_path.parent)
        ),
        autoescape=select_autoescape(
            enabled_extensions=("html", "xml")
        ),
        undefined=StrictUndefined,
    )
    template = environment.get_template(
        template_path.name
    )

    rendered_html = template.render(
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        gross_amount=_format_eur(summary[2]),
        approved_visits=summary[0],
        approved_hours=_format_hours(summary[1]),
        divergent_count=reconciliation_counts.get(
            "divergent",
            0,
        ),
        matched_count=reconciliation_counts.get(
            "matched",
            0,
        ),
        employer_only_count=reconciliation_counts.get(
            "employer_only",
            0,
        ),
        worker_only_count=reconciliation_counts.get(
            "worker_only",
            0,
        ),
        payment_lines=payment_lines,
        generated_at=generated_at.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
        calculation_rule_version=(
            "gross-v1-line-round-half-up"
        ),
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary_path = output_path.with_name(
        f".{output_path.name}.tmp"
    )
    temporary_path.write_text(
        rendered_html,
        encoding="utf-8",
    )
    os.replace(temporary_path, output_path)

    return {
        "status": "ok",
        "report_path": str(output_path.resolve()),
        "payment_lines": len(payment_lines),
        "gross_amount_cents": summary[2],
    }
