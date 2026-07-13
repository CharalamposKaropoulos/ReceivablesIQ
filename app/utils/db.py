"""Streamlit-facing DuckDB helpers with connection caching."""

from __future__ import annotations

from pathlib import Path

import duckdb
import streamlit as st

from app.utils.config import get_config
from src.db import connect, database_exists


def get_database_path() -> Path:
    """Resolve the configured DuckDB path."""
    return get_config().database_path


def db_available() -> bool:
    """Return True when the analytical database file exists."""
    return database_exists(get_database_path())


@st.cache_resource
def get_connection(db_path: str) -> duckdb.DuckDBPyConnection:
    """Cached read-only DuckDB connection for Streamlit.

    ``db_path`` is part of the cache key so a path change opens a new connection.
    """
    return connect(db_path, read_only=True, create_if_missing=False)


def get_cached_connection() -> duckdb.DuckDBPyConnection | None:
    """Return a cached connection, or None if the database is missing."""
    path = get_database_path()
    if not database_exists(path):
        return None
    return get_connection(str(path))
