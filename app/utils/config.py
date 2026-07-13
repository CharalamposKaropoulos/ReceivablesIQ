"""Streamlit-facing config helpers."""

from __future__ import annotations

from pathlib import Path

from src.config import DEFAULT_CONFIG_PATH, ProjectConfig, load_config


def get_config(path: Path | str | None = None) -> ProjectConfig:
    """Load validated project config for the Streamlit app."""
    return load_config(path or DEFAULT_CONFIG_PATH)


def get_cache_ttl_seconds(config: ProjectConfig | None = None) -> int:
    """Return cache TTL from config (used with ``st.cache_data``)."""
    cfg = config if config is not None else get_config()
    return cfg.dashboard.cache_ttl_seconds
