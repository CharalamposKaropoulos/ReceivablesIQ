"""Shared helpers for synthetic data generators (Faker seeding and file I/O)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from faker import Faker

DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_PROCESSED_DIR = Path("data/processed")


def make_faker(seed: int) -> Faker:
    """Return a Faker instance seeded for reproducible generation.

    Both the class-level seed and the instance seed are set so that calls
    across modules remain deterministic for a given ``seed``.
    """
    faker = Faker()
    Faker.seed(seed)
    faker.seed_instance(seed)
    return faker


def raw_dir(root: Path | None = None) -> Path:
    """Return the raw data directory (``data/raw`` under ``root`` or cwd)."""
    base = Path(".") if root is None else Path(root)
    return base / "data" / "raw"


def processed_dir(root: Path | None = None) -> Path:
    """Return the processed data directory (``data/processed`` under ``root`` or cwd)."""
    base = Path(".") if root is None else Path(root)
    return base / "data" / "processed"


def raw_path(filename: str, *, root: Path | None = None) -> Path:
    """Build a path under ``data/raw`` for ``filename``."""
    return raw_dir(root) / filename


def processed_path(filename: str, *, root: Path | None = None) -> Path:
    """Build a path under ``data/processed`` for ``filename``."""
    return processed_dir(root) / filename


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write ``df`` to CSV at ``path``, creating parent directories as needed."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destination, index=False)
    return destination


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    """Write ``df`` to Parquet at ``path``, creating parent directories as needed."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destination, index=False)
    return destination
