from __future__ import annotations

from pathlib import Path

import duckdb


MANAGED_SCHEMAS = ("raw", "core", "mart")


def initialize_database(
    database_path: Path,
    schema_path: Path,
) -> list[str]:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = schema_path.read_text(encoding="utf-8")

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(schema_sql)
        placeholders = ", ".join("?" for _ in MANAGED_SCHEMAS)
        rows = connection.execute(
            f"""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ({placeholders})
            ORDER BY table_schema, table_name
            """,
            list(MANAGED_SCHEMAS),
        ).fetchall()

    return [
        f"{schema_name}.{table_name}"
        for schema_name, table_name in rows
    ]
