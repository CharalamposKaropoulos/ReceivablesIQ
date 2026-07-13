"""Foundation tests — config loading and DuckDB helpers (Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import load_config
from src.db import connect, create_database, database_exists
from src.logging_setup import get_logger, setup_logging


def test_load_default_config() -> None:
    config = load_config()
    assert config.dashboard.title
    assert config.database.engine == "duckdb"
    assert config.database.path.endswith(".duckdb")
    assert config.application.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert config.pipeline.random_seed == 42


def test_load_config_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("dashboard: [\n  invalid\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(bad)


def test_logging_setup() -> None:
    setup_logging("INFO", force=True)
    logger = get_logger("tests.foundation")
    logger.info("foundation logging ok")
    assert logger.name == "tests.foundation"


def test_database_helpers(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    assert database_exists(db_path) is False

    with pytest.raises(FileNotFoundError):
        connect(db_path, read_only=True)

    conn = create_database(db_path)
    try:
        conn.execute("CREATE TABLE smoke (id INTEGER)")
        conn.execute("INSERT INTO smoke VALUES (1)")
        assert conn.execute("SELECT id FROM smoke").fetchone()[0] == 1
    finally:
        conn.close()

    assert database_exists(db_path) is True
    read_conn = connect(db_path, read_only=True)
    try:
        assert read_conn.execute("SELECT COUNT(*) FROM smoke").fetchone()[0] == 1
    finally:
        read_conn.close()
