"""Foundation tests — config loading and DuckDB helpers (Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import RECOMMENDED_ACTIONS, load_config
from src.db import connect, create_database, database_exists
from src.logging_setup import get_logger, setup_logging


def _write_config(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "project_config.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_load_default_config() -> None:
    config = load_config()
    assert config.dashboard.title
    assert config.database.engine == "duckdb"
    assert config.database.path.endswith(".duckdb")
    assert config.application.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert config.pipeline.random_seed == 42
    assert abs(sum(config.risk_model.weights.model_dump().values()) - 1.0) < 1e-6
    assert abs(sum(config.collections_model.weights.model_dump().values()) - 1.0) < 1e-6
    assert config.risk_model.category_thresholds.medium == 25.0
    assert config.collections_model.priority_thresholds.critical == 75.0
    assert set(config.collections_model.recommended_actions) == set(RECOMMENDED_ACTIONS)


def test_load_config_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("dashboard: [\n  invalid\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(bad)


def test_load_config_missing_risk_model_section(tmp_path: Path) -> None:
    payload = load_config().model_dump()
    del payload["risk_model"]
    path = _write_config(tmp_path, payload)
    with pytest.raises(ValueError, match="risk_model|validation"):
        load_config(path)


def test_load_config_missing_collections_model_section(tmp_path: Path) -> None:
    payload = load_config().model_dump()
    del payload["collections_model"]
    path = _write_config(tmp_path, payload)
    with pytest.raises(ValueError, match="collections_model|validation"):
        load_config(path)


def test_load_config_rejects_risk_weights_not_summing_to_one(tmp_path: Path) -> None:
    payload = load_config().model_dump()
    payload["risk_model"]["weights"]["ageing"] = 0.99
    path = _write_config(tmp_path, payload)
    with pytest.raises(ValueError, match="sum to 1.0"):
        load_config(path)


def test_load_config_rejects_collections_weights_not_summing_to_one(
    tmp_path: Path,
) -> None:
    payload = load_config().model_dump()
    payload["collections_model"]["weights"]["risk"] = 0.99
    path = _write_config(tmp_path, payload)
    with pytest.raises(ValueError, match="sum to 1.0"):
        load_config(path)


def test_load_config_rejects_non_increasing_category_thresholds(tmp_path: Path) -> None:
    payload = load_config().model_dump()
    payload["risk_model"]["category_thresholds"] = {
        "medium": 50.0,
        "high": 40.0,
        "critical": 75.0,
    }
    path = _write_config(tmp_path, payload)
    with pytest.raises(ValueError, match="medium < high < critical"):
        load_config(path)


def test_load_config_rejects_unknown_recommended_action(tmp_path: Path) -> None:
    payload = load_config().model_dump()
    payload["collections_model"]["recommended_actions"] = [
        *RECOMMENDED_ACTIONS[:-1],
        "not a real action",
    ]
    path = _write_config(tmp_path, payload)
    with pytest.raises(ValueError, match="outside the locked BRD"):
        load_config(path)


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
