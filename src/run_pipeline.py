"""Pipeline CLI — generate synthetic data, optional DQ defects, write files, load DuckDB."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.config import DEFAULT_CONFIG_PATH, ProjectConfig, load_config
from src.generators import (
    generate_dim_customer,
    generate_dim_date,
    generate_fact_claim,
    generate_fact_credit_decision,
    generate_fact_invoice,
    generate_fact_payment,
    inject_data_quality_defects,
    processed_path,
    raw_path,
    write_csv,
    write_parquet,
)
from src.io_duckdb import (
    DEFAULT_SCHEMA_PATH,
    apply_schema,
    load_entity_tables,
    open_writable_database,
    record_pipeline_run,
)
from src.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)

# (table_name, raw csv stem, processed parquet stem)
_OUTPUT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("dim_date", "dim_date.csv", "dim_date.parquet"),
    ("dim_customer", "dim_customer.csv", "dim_customer.parquet"),
    ("fact_invoice", "fact_invoice.csv", "fact_invoice.parquet"),
    ("fact_payment", "fact_payment.csv", "fact_payment.parquet"),
    ("fact_credit_decision", "fact_credit_decision.csv", "fact_credit_decision.parquet"),
    ("fact_claim", "fact_claim.csv", "fact_claim.parquet"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the synthetic data pipeline."""
    parser = argparse.ArgumentParser(
        prog="python -m src.run_pipeline",
        description=(
            "Generate synthetic credit-risk data, optionally inject data-quality "
            "defects, and load analytical tables into DuckDB."
        ),
    )
    parser.add_argument(
        "--small",
        action="store_true",
        help="Use pipeline.small_num_customers instead of num_customers",
    )
    parser.add_argument(
        "--skip-defects",
        action="store_true",
        help="Skip data-quality defect injection even if enabled in config",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        metavar="PATH",
        help=f"Path to project_config.yaml (default: {DEFAULT_CONFIG_PATH})",
    )
    return parser.parse_args(argv)


def resolve_customer_count(config: ProjectConfig, *, small: bool) -> int:
    """Return the customer count for this run from config."""
    if small:
        return config.pipeline.small_num_customers
    return config.pipeline.num_customers


def resolve_inject_defects(config: ProjectConfig, *, skip_defects: bool) -> bool:
    """Return whether defect injection should run for this invocation."""
    if skip_defects:
        return False
    return config.pipeline.inject_data_quality_defects


def _write_outputs(
    tables: dict[str, pd.DataFrame],
    *,
    data_root: Path,
    audit_log: pd.DataFrame | None = None,
) -> None:
    """Write entity tables (and optional defect audit) to CSV and Parquet."""
    for table_name, csv_name, parquet_name in _OUTPUT_SPECS:
        frame = tables[table_name]
        csv_out = write_csv(frame, raw_path(csv_name, root=data_root))
        parquet_out = write_parquet(frame, processed_path(parquet_name, root=data_root))
        logger.info(
            "Wrote %s (%s rows) -> %s, %s",
            table_name,
            len(frame),
            csv_out,
            parquet_out,
        )

    if audit_log is not None and not audit_log.empty:
        audit_csv = write_csv(audit_log, raw_path("defect_audit.csv", root=data_root))
        audit_parquet = write_parquet(
            audit_log, processed_path("defect_audit.parquet", root=data_root)
        )
        logger.info(
            "Wrote defect audit (%s rows) -> %s, %s",
            len(audit_log),
            audit_csv,
            audit_parquet,
        )


def execute_pipeline(
    config: ProjectConfig,
    *,
    customer_count: int,
    skip_defects: bool,
    data_root: Path | None = None,
    schema_path: Path | None = None,
) -> dict[str, int]:
    """Generate, optionally defect-inject, write files, and load DuckDB.

    Returns a mapping of entity table name -> row count loaded.
    """
    root = Path(".") if data_root is None else Path(data_root)
    schema = DEFAULT_SCHEMA_PATH if schema_path is None else Path(schema_path)
    inject = resolve_inject_defects(config, skip_defects=skip_defects)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    db_path = config.database_path
    # When tests point database.path at a temp file, keep absolute; otherwise
    # resolve relative paths against data_root so outputs stay co-located.
    if not db_path.is_absolute() and data_root is not None:
        db_path = root / db_path

    logger.info(
        "Generating synthetic tables (seed=%s, customers=%s, inject_defects=%s)",
        config.pipeline.random_seed,
        customer_count,
        inject,
    )

    dim_date = generate_dim_date(config)
    dim_customer = generate_dim_customer(config, n=customer_count)
    fact_invoice = generate_fact_invoice(config, dim_customer)
    fact_payment = generate_fact_payment(config, fact_invoice)
    fact_credit_decision = generate_fact_credit_decision(config, dim_customer)
    fact_claim = generate_fact_claim(config, dim_customer, fact_invoice)

    dim_customer, fact_invoice, fact_payment, audit_log = inject_data_quality_defects(
        config,
        dim_customer,
        fact_invoice,
        fact_payment,
        skip=skip_defects,
    )

    tables: dict[str, pd.DataFrame] = {
        "dim_date": dim_date,
        "dim_customer": dim_customer,
        "fact_invoice": fact_invoice,
        "fact_payment": fact_payment,
        "fact_credit_decision": fact_credit_decision,
        "fact_claim": fact_claim,
    }

    _write_outputs(tables, data_root=root, audit_log=audit_log)

    conn = open_writable_database(db_path)
    try:
        apply_schema(conn, schema)
        record_pipeline_run(
            conn,
            run_id=run_id,
            started_at=started_at,
            finished_at=None,
            status="running",
            random_seed=config.pipeline.random_seed,
            customer_count=customer_count,
            notes="Pipeline run in progress",
        )

        # Defective rows can violate PK/FK/NOT NULL; keep them for Phase 4.
        relax = bool(inject and len(audit_log) > 0)
        row_counts = load_entity_tables(conn, tables, relax_constraints=relax)

        finished_at = datetime.now(UTC)
        notes = (
            f"defects_injected={len(audit_log)}; relax_constraints={relax}"
            if inject
            else "defects skipped or disabled"
        )
        record_pipeline_run(
            conn,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            random_seed=config.pipeline.random_seed,
            customer_count=customer_count,
            notes=notes,
        )
    except Exception:
        finished_at = datetime.now(UTC)
        try:
            record_pipeline_run(
                conn,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                status="failed",
                random_seed=config.pipeline.random_seed,
                customer_count=customer_count,
                notes="Pipeline failed during schema apply or load",
            )
        except Exception:
            logger.exception("Could not record failed pipeline_runs row")
        raise
    finally:
        conn.close()

    logger.info(
        "Pipeline finished successfully (database=%s, tables=%s)",
        db_path,
        row_counts,
    )
    return row_counts


def run(argv: list[str] | None = None) -> int:
    """Load config, configure logging, and execute the synthetic data pipeline."""
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        # Logging may not be configured yet; print a clear user-facing message.
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.application.log_level)

    customer_count = resolve_customer_count(config, small=args.small)
    inject_defects = resolve_inject_defects(config, skip_defects=args.skip_defects)

    logger.info(
        "Pipeline starting (seed=%s, customers=%s, history_months=%s, "
        "inject_defects=%s, database=%s)",
        config.pipeline.random_seed,
        customer_count,
        config.pipeline.history_months,
        inject_defects,
        config.database_path,
    )

    try:
        execute_pipeline(
            config,
            customer_count=customer_count,
            skip_defects=args.skip_defects,
        )
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
