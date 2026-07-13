"""Integration tests for the synthetic data pipeline (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest
import yaml

from src.config import load_config
from src.db import database_exists
from src.io_duckdb import ENTITY_LOAD_ORDER
from src.run_pipeline import execute_pipeline, run

# Key columns used for cross-run reproducibility checksums (Phase 2 gate).
_CHECKSUM_COLUMNS: dict[str, list[str]] = {
    "dim_date": ["date_key", "full_date"],
    "dim_customer": ["customer_id", "name", "country", "credit_limit"],
    "fact_invoice": [
        "invoice_id",
        "customer_id",
        "invoice_date",
        "invoice_amount",
        "outstanding_amount",
    ],
    "fact_payment": ["payment_id", "invoice_id", "payment_date", "payment_amount"],
    "fact_credit_decision": ["decision_id", "customer_id", "new_limit", "previous_limit"],
    "fact_claim": ["claim_id", "customer_id", "claim_amount", "status"],
}


def _write_temp_config(
    tmp_path: Path,
    *,
    small_num_customers: int = 20,
    inject_defects: bool = False,
    defect_rate: float = 0.03,
) -> Path:
    """Copy project config into ``tmp_path`` with a temp DuckDB path."""
    base = load_config()
    payload = base.model_dump()
    payload["database"]["path"] = str(tmp_path / "credit_risk.duckdb")
    payload["pipeline"]["small_num_customers"] = small_num_customers
    payload["pipeline"]["inject_data_quality_defects"] = inject_defects
    payload["pipeline"]["defect_rate"] = defect_rate
    payload["application"]["log_level"] = "WARNING"

    config_path = tmp_path / "project_config.yaml"
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return config_path


def test_pipeline_small_skip_defects_writes_files_and_duckdb(tmp_path: Path) -> None:
    config_path = _write_temp_config(tmp_path, small_num_customers=15)
    config = load_config(config_path)

    row_counts = execute_pipeline(
        config,
        customer_count=config.pipeline.small_num_customers,
        skip_defects=True,
        data_root=tmp_path,
    )

    assert row_counts["dim_customer"] == 15
    assert row_counts["dim_date"] > 0
    assert row_counts["fact_invoice"] > 0
    assert row_counts["fact_payment"] >= 0
    assert row_counts["fact_credit_decision"] >= 0
    assert row_counts["fact_claim"] >= 0

    db_path = tmp_path / "credit_risk.duckdb"
    assert database_exists(db_path)

    for table_name in ENTITY_LOAD_ORDER:
        csv_path = tmp_path / "data" / "raw" / f"{table_name}.csv"
        parquet_path = tmp_path / "data" / "processed" / f"{table_name}.parquet"
        assert csv_path.is_file(), f"missing {csv_path}"
        assert parquet_path.is_file(), f"missing {parquet_path}"

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        for table_name, expected in row_counts.items():
            actual = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            assert actual == expected

        run_row = conn.execute(
            "SELECT status, customer_count, random_seed, finished_at "
            "FROM pipeline_runs ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        assert run_row is not None
        assert run_row[0] == "success"
        assert run_row[1] == 15
        assert run_row[2] == config.pipeline.random_seed
        assert run_row[3] is not None
    finally:
        conn.close()


def test_pipeline_cli_small_skip_defects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _write_temp_config(tmp_path, small_num_customers=10)
    monkeypatch.chdir(tmp_path)

    exit_code = run(
        ["--small", "--skip-defects", "--config", str(config_path)]
    )
    assert exit_code == 0

    db_path = Path(load_config(config_path).database.path)
    # database.path in temp config is absolute under tmp_path
    assert database_exists(db_path)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        customers = conn.execute("SELECT COUNT(*) FROM dim_customer").fetchone()[0]
        invoices = conn.execute("SELECT COUNT(*) FROM fact_invoice").fetchone()[0]
        assert customers == 10
        assert invoices > 0
    finally:
        conn.close()


def test_pipeline_rerun_skip_defects_replaces_existing_tables(tmp_path: Path) -> None:
    """Second constrained load must clear children before parents (FK-safe)."""
    config_path = _write_temp_config(tmp_path, small_num_customers=12)
    config = load_config(config_path)

    first = execute_pipeline(
        config,
        customer_count=config.pipeline.small_num_customers,
        skip_defects=True,
        data_root=tmp_path,
    )
    second = execute_pipeline(
        config,
        customer_count=config.pipeline.small_num_customers,
        skip_defects=True,
        data_root=tmp_path,
    )

    assert first == second
    assert second["dim_customer"] == 12

    db_path = tmp_path / "credit_risk.duckdb"
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        for table_name, expected in second.items():
            actual = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            assert actual == expected
        success_runs = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'success'"
        ).fetchone()[0]
        assert success_runs >= 2
    finally:
        conn.close()


def _frame_checksum(path: Path, columns: list[str]) -> int:
    """Stable hash of selected columns from a Parquet file."""
    frame = pd.read_parquet(path)
    subset = frame.loc[:, columns].sort_values(columns).reset_index(drop=True)
    return int(pd.util.hash_pandas_object(subset, index=False).sum())


def test_pipeline_same_seed_produces_identical_row_counts_and_checksums(
    tmp_path: Path,
) -> None:
    """Two independent runs with the same seed must match on counts and key columns."""
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()

    config_path_a = _write_temp_config(run_a, small_num_customers=18)
    config_path_b = _write_temp_config(run_b, small_num_customers=18)
    config_a = load_config(config_path_a)
    config_b = load_config(config_path_b)

    assert config_a.pipeline.random_seed == config_b.pipeline.random_seed

    counts_a = execute_pipeline(
        config_a,
        customer_count=18,
        skip_defects=True,
        data_root=run_a,
    )
    counts_b = execute_pipeline(
        config_b,
        customer_count=18,
        skip_defects=True,
        data_root=run_b,
    )

    assert counts_a == counts_b

    for table_name, columns in _CHECKSUM_COLUMNS.items():
        path_a = run_a / "data" / "processed" / f"{table_name}.parquet"
        path_b = run_b / "data" / "processed" / f"{table_name}.parquet"
        assert _frame_checksum(path_a, columns) == _frame_checksum(
            path_b, columns
        ), f"checksum mismatch for {table_name}"


def test_pipeline_with_defects_still_loads_duckdb(tmp_path: Path) -> None:
    config_path = _write_temp_config(
        tmp_path,
        small_num_customers=25,
        inject_defects=True,
        defect_rate=0.05,
    )
    config = load_config(config_path)

    row_counts = execute_pipeline(
        config,
        customer_count=config.pipeline.small_num_customers,
        skip_defects=False,
        data_root=tmp_path,
    )

    assert row_counts["dim_customer"] == 25
    # Defects append duplicate invoice rows → more invoice rows than clean run.
    assert row_counts["fact_invoice"] > 0

    audit_csv = tmp_path / "data" / "raw" / "defect_audit.csv"
    assert audit_csv.is_file()

    db_path = tmp_path / "credit_risk.duckdb"
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        loaded = conn.execute("SELECT COUNT(*) FROM fact_invoice").fetchone()[0]
        assert loaded == row_counts["fact_invoice"]
        status = conn.execute(
            "SELECT status FROM pipeline_runs ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()[0]
        assert status == "success"
    finally:
        conn.close()
