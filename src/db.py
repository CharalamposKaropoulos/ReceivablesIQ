"""DuckDB connection helpers around ``database.path``."""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.logging_setup import get_logger

logger = get_logger(__name__)


def database_exists(path: Path | str) -> bool:
    """Return True if a DuckDB file exists at ``path``."""
    return Path(path).is_file()


def ensure_parent_dir(path: Path | str) -> Path:
    """Create the parent directory for the database file if needed."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def connect(
    path: Path | str,
    *,
    read_only: bool = False,
    create_if_missing: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection.

    Args:
        path: Filesystem path to the ``.duckdb`` file.
        read_only: Open in read-only mode (typical for Streamlit).
        create_if_missing: Create parent dirs and allow DuckDB to create the file.

    Raises:
        FileNotFoundError: if the file is missing and ``create_if_missing`` is False.
    """
    db_path = Path(path)

    if create_if_missing:
        ensure_parent_dir(db_path)
    elif not db_path.is_file():
        raise FileNotFoundError(
            f"Analytical database not found at {db_path}. "
            "Run: python -m src.run_pipeline --small"
        )

    logger.debug("Connecting to DuckDB at %s (read_only=%s)", db_path, read_only)
    return duckdb.connect(str(db_path), read_only=read_only)


def create_database(path: Path | str) -> duckdb.DuckDBPyConnection:
    """Create (or open) a writable DuckDB database, ensuring parent directories exist."""
    return connect(path, read_only=False, create_if_missing=True)
