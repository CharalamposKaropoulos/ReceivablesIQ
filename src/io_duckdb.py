"""DuckDB schema application and DataFrame load helpers for the pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from src.db import create_database
from src.logging_setup import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_PATH = _PROJECT_ROOT / "sql" / "create_schema.sql"

# FK-safe create order (parents before children). Drop uses the reverse.
ENTITY_LOAD_ORDER: tuple[str, ...] = (
    "dim_date",
    "dim_customer",
    "fact_invoice",
    "fact_payment",
    "fact_credit_decision",
    "fact_claim",
)


def apply_schema(
    conn: duckdb.DuckDBPyConnection,
    schema_path: Path | str | None = None,
) -> Path:
    """Execute Phase 2 DDL from ``sql/create_schema.sql`` (or ``schema_path``)."""
    path = Path(schema_path) if schema_path is not None else DEFAULT_SCHEMA_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Schema SQL not found: {path}")

    sql = path.read_text(encoding="utf-8")
    conn.execute(sql)
    logger.info("Applied schema from %s", path)
    return path


def _insert_dataframe(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    df: pd.DataFrame,
) -> int:
    """Insert all rows from ``df`` into an existing ``table_name``."""
    if df.empty:
        return 0

    view_name = f"_load_{table_name}"
    conn.register(view_name, df)
    try:
        conn.execute(f"INSERT INTO {table_name} BY NAME SELECT * FROM {view_name}")
    finally:
        conn.unregister(view_name)
    return len(df)


def _replace_table_as_select(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    df: pd.DataFrame,
) -> int:
    """Drop ``table_name`` and recreate it from ``df`` (no PK/FK constraints).

    Used when injected DQ defects would violate the constrained DDL (duplicate
    keys, null identifiers). Phase 4 validation still needs those rows in DuckDB.
    """
    conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    view_name = f"_load_{table_name}"
    conn.register(view_name, df)
    try:
        if df.empty:
            # Preserve column names even when there are no rows.
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {view_name} WHERE 1=0")
        else:
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {view_name}")
    finally:
        conn.unregister(view_name)
    return len(df)


def load_entity_tables(
    conn: duckdb.DuckDBPyConnection,
    tables: dict[str, pd.DataFrame],
    *,
    relax_constraints: bool = False,
) -> dict[str, int]:
    """Load entity DataFrames into DuckDB.

    When ``relax_constraints`` is False, rows are inserted into the tables
    created by ``apply_schema`` (PK/FK enforced). When True — typical after DQ
    defect injection — tables are replaced from the DataFrames so defective
    rows are retained for later validation.
    """
    missing = [name for name in ENTITY_LOAD_ORDER if name not in tables]
    if missing:
        raise ValueError(f"Missing tables for DuckDB load: {missing}")

    row_counts: dict[str, int] = {}

    if relax_constraints:
        for name in reversed(ENTITY_LOAD_ORDER):
            conn.execute(f"DROP TABLE IF EXISTS {name} CASCADE")
        for name in ENTITY_LOAD_ORDER:
            count = _replace_table_as_select(conn, name, tables[name])
            row_counts[name] = count
            logger.info("Loaded %s (%s rows, unconstrained)", name, count)
        return row_counts

    # Children first so FK references do not block truncate on re-runs.
    for name in reversed(ENTITY_LOAD_ORDER):
        conn.execute(f"DELETE FROM {name}")

    for name in ENTITY_LOAD_ORDER:
        count = _insert_dataframe(conn, name, tables[name])
        row_counts[name] = count
        logger.info("Loaded %s (%s rows)", name, count)

    return row_counts


def record_pipeline_run(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime | None,
    status: str,
    random_seed: int,
    customer_count: int,
    notes: str | None = None,
) -> None:
    """Insert or replace a ``pipeline_runs`` metadata row."""
    conn.execute(
        """
        INSERT OR REPLACE INTO pipeline_runs (
            run_id, started_at, finished_at, status,
            random_seed, customer_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            started_at,
            finished_at,
            status,
            random_seed,
            customer_count,
            notes,
        ],
    )
    logger.info(
        "Recorded pipeline_runs row run_id=%s status=%s customers=%s",
        run_id,
        status,
        customer_count,
    )


def open_writable_database(path: Path | str) -> duckdb.DuckDBPyConnection:
    """Create parent dirs and open a writable DuckDB connection."""
    return create_database(path)
