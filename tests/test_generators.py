"""Tests for shared generator helpers (Phase 2 step 03)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.generators.common import (
    DEFAULT_PROCESSED_DIR,
    DEFAULT_RAW_DIR,
    make_faker,
    processed_dir,
    processed_path,
    raw_dir,
    raw_path,
    write_csv,
    write_parquet,
)


def test_make_faker_is_reproducible() -> None:
    first = make_faker(42)
    second = make_faker(42)
    assert [first.name() for _ in range(5)] == [second.name() for _ in range(5)]


def test_make_faker_different_seeds_diverge() -> None:
    a = make_faker(1)
    b = make_faker(2)
    assert [a.name() for _ in range(5)] != [b.name() for _ in range(5)]


def test_path_helpers_default_layout() -> None:
    assert DEFAULT_RAW_DIR == Path("data/raw")
    assert DEFAULT_PROCESSED_DIR == Path("data/processed")
    assert raw_dir() == Path("data/raw")
    assert processed_dir() == Path("data/processed")
    assert raw_path("customers.csv") == Path("data/raw/customers.csv")
    assert processed_path("dim_customer.parquet") == Path(
        "data/processed/dim_customer.parquet"
    )


def test_path_helpers_respect_root(tmp_path: Path) -> None:
    assert raw_dir(tmp_path) == tmp_path / "data" / "raw"
    assert processed_dir(tmp_path) == tmp_path / "data" / "processed"
    assert raw_path("invoices.csv", root=tmp_path) == (
        tmp_path / "data" / "raw" / "invoices.csv"
    )
    assert processed_path("fact_invoice.parquet", root=tmp_path) == (
        tmp_path / "data" / "processed" / "fact_invoice.parquet"
    )


def test_write_csv_and_parquet_to_temp_dirs(tmp_path: Path) -> None:
    df = pd.DataFrame({"id": [1, 2], "label": ["a", "b"]})

    csv_out = write_csv(df, raw_path("sample.csv", root=tmp_path))
    parquet_out = write_parquet(df, processed_path("sample.parquet", root=tmp_path))

    assert csv_out.is_file()
    assert parquet_out.is_file()
    assert csv_out.parent == tmp_path / "data" / "raw"
    assert parquet_out.parent == tmp_path / "data" / "processed"

    round_trip_csv = pd.read_csv(csv_out)
    round_trip_parquet = pd.read_parquet(parquet_out)
    pd.testing.assert_frame_equal(round_trip_csv, df)
    pd.testing.assert_frame_equal(round_trip_parquet, df)


def test_write_creates_missing_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "out" / "table.csv"
    assert not nested.parent.exists()
    write_csv(pd.DataFrame({"x": [1]}), nested)
    assert nested.is_file()
