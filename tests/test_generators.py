"""Tests for synthetic data generators (Phase 2)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.config import load_config
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
from src.generators.customers import (
    COUNTRY_REGIONS,
    CREDIT_INSURANCE_STATUSES,
    DIM_CUSTOMER_COLUMNS,
    STATUSES,
    generate_dim_customer,
)
from src.generators.dates import (
    DEFAULT_AS_OF_DATE,
    DIM_DATE_COLUMNS,
    generate_dim_date,
    history_window_bounds,
)
from src.generators.invoices import (
    FACT_INVOICE_COLUMNS,
    INVOICE_STATUSES,
    generate_fact_invoice,
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


# --- dim_date (Phase 2 step 04) -------------------------------------------------


def test_date_history_window_bounds_for_default_as_of() -> None:
    start, end = history_window_bounds(24)
    assert end == DEFAULT_AS_OF_DATE
    assert start == date(2024, 7, 1)
    assert (end - start).days + 1 == 730


def test_generate_dim_date_row_count_and_columns() -> None:
    config = load_config()
    dim_date = generate_dim_date(config)

    start, end = history_window_bounds(config.pipeline.history_months)
    expected_rows = (end - start).days + 1

    assert list(dim_date.columns) == list(DIM_DATE_COLUMNS)
    assert len(dim_date) == expected_rows
    assert dim_date["full_date"].iloc[0] == start
    assert dim_date["full_date"].iloc[-1] == end


def test_generate_dim_date_unique_keys_and_no_gaps() -> None:
    config = load_config()
    dim_date = generate_dim_date(config)

    assert dim_date["date_key"].is_unique
    assert dim_date["full_date"].is_unique

    dates = pd.to_datetime(dim_date["full_date"]).dt.date
    diffs = dates.diff().iloc[1:]
    assert (diffs == timedelta(days=1)).all()


def test_generate_dim_date_attributes_and_month_ends() -> None:
    config = load_config()
    dim_date = generate_dim_date(config)

    june_end = dim_date.loc[dim_date["date_key"] == 20260630].iloc[0]
    assert june_end["year"] == 2026
    assert june_end["month"] == 6
    assert june_end["month_name"] == "June"
    assert june_end["quarter"] == 2
    assert bool(june_end["is_month_end"]) is True

    mid_month = dim_date.loc[dim_date["date_key"] == 20260615].iloc[0]
    assert bool(mid_month["is_month_end"]) is False

    assert dim_date["is_month_end"].dtype == bool


def test_generate_dim_date_is_deterministic() -> None:
    config = load_config()
    first = generate_dim_date(config)
    second = generate_dim_date(config)
    pd.testing.assert_frame_equal(first, second)


def test_generate_dim_date_respects_history_months() -> None:
    config = load_config()
    short = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"history_months": 1})}
    )
    dim_date = generate_dim_date(short)
    start, end = history_window_bounds(1)
    assert len(dim_date) == (end - start).days + 1
    assert dim_date["full_date"].iloc[0] == start


# --- dim_customer (Phase 2 step 05) ---------------------------------------------


def test_generate_dim_customer_row_count_and_columns() -> None:
    config = load_config()
    customers = generate_dim_customer(config, n=config.pipeline.small_num_customers)

    assert list(customers.columns) == list(DIM_CUSTOMER_COLUMNS)
    assert len(customers) == config.pipeline.small_num_customers


def test_generate_dim_customer_unique_ids_and_no_null_pks() -> None:
    config = load_config()
    customers = generate_dim_customer(config, n=50)

    assert customers["customer_id"].is_unique
    assert customers["customer_id"].notna().all()
    assert (customers["customer_id"].astype(str).str.len() > 0).all()
    assert customers["customer_id"].iloc[0] == "CUST-000001"
    assert customers["customer_id"].iloc[-1] == "CUST-000050"


def test_generate_dim_customer_filter_dimensions_populated() -> None:
    config = load_config()
    customers = generate_dim_customer(config, n=80)

    required = [
        "country",
        "region",
        "industry",
        "account_manager",
        "collections_owner",
        "status",
        "credit_insurance_status",
        "currency",
        "business_unit",
        "name",
        "credit_limit",
        "created_date",
    ]
    for column in required:
        assert customers[column].notna().all(), f"{column} has nulls"
        assert (customers[column].astype(str).str.len() > 0).all()

    assert set(customers["status"]).issubset(STATUSES)
    assert set(customers["credit_insurance_status"]).issubset(CREDIT_INSURANCE_STATUSES)
    assert set(customers["country"]).issubset(COUNTRY_REGIONS.keys())
    assert (customers["credit_limit"] > 0).all()

    history_start, as_of = history_window_bounds(config.pipeline.history_months)
    earliest_created = history_start - timedelta(days=365 * 5)
    created = pd.to_datetime(customers["created_date"]).dt.date
    assert (created <= as_of).all()
    assert (created >= earliest_created).all()


def test_generate_dim_customer_region_matches_country() -> None:
    config = load_config()
    customers = generate_dim_customer(config, n=60)

    for country, region in zip(
        customers["country"], customers["region"], strict=True
    ):
        assert region in COUNTRY_REGIONS[country]


def test_generate_dim_customer_is_deterministic() -> None:
    config = load_config()
    first = generate_dim_customer(config, n=25)
    second = generate_dim_customer(config, n=25)
    pd.testing.assert_frame_equal(first, second)


def test_generate_dim_customer_seed_changes_names_and_ids_stable() -> None:
    config = load_config()
    other = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"random_seed": 99})}
    )
    a = generate_dim_customer(config, n=10)
    b = generate_dim_customer(other, n=10)

    assert list(a["customer_id"]) == list(b["customer_id"])
    assert list(a["name"]) != list(b["name"])


def test_generate_dim_customer_defaults_to_num_customers() -> None:
    config = load_config()
    tiny = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"num_customers": 7})}
    )
    customers = generate_dim_customer(tiny)
    assert len(customers) == 7


# --- fact_invoice (Phase 2 step 06) ---------------------------------------------


def _sample_customers(n: int = 40):
    config = load_config()
    customers = generate_dim_customer(config, n=n)
    return config, customers


def test_generate_fact_invoice_columns_and_non_empty() -> None:
    config, customers = _sample_customers(30)
    invoices = generate_fact_invoice(config, customers)

    assert list(invoices.columns) == list(FACT_INVOICE_COLUMNS)
    assert len(invoices) > 0
    assert invoices["invoice_id"].is_unique
    assert invoices["invoice_id"].iloc[0] == "INV-0000001"


def test_generate_fact_invoice_customer_fk_integrity() -> None:
    config, customers = _sample_customers(50)
    invoices = generate_fact_invoice(config, customers)

    customer_ids = set(customers["customer_id"])
    assert set(invoices["customer_id"]).issubset(customer_ids)


def test_generate_fact_invoice_dates_within_history() -> None:
    config, customers = _sample_customers(40)
    invoices = generate_fact_invoice(config, customers)

    history_start, as_of = history_window_bounds(config.pipeline.history_months)
    invoice_dates = pd.to_datetime(invoices["invoice_date"]).dt.date
    due_dates = pd.to_datetime(invoices["due_date"]).dt.date

    assert (invoice_dates >= history_start).all()
    assert (invoice_dates <= as_of).all()
    assert (due_dates >= invoice_dates).all()


def test_generate_fact_invoice_amounts_and_status_clean() -> None:
    config, customers = _sample_customers(45)
    invoices = generate_fact_invoice(config, customers)

    assert (invoices["invoice_amount"] >= 0).all()
    assert (invoices["outstanding_amount"] >= 0).all()
    assert (
        invoices["outstanding_amount"] <= invoices["invoice_amount"]
    ).all()
    assert set(invoices["status"]).issubset(INVOICE_STATUSES)
    assert invoices["dispute_flag"].dtype == bool
    assert invoices["currency"].notna().all()

    paid = invoices.loc[invoices["status"] == "paid"]
    if not paid.empty:
        assert (paid["outstanding_amount"] == 0).all()


def test_generate_fact_invoice_currency_matches_customer() -> None:
    config, customers = _sample_customers(35)
    invoices = generate_fact_invoice(config, customers)

    currency_by_customer = customers.set_index("customer_id")["currency"]
    matched = invoices["customer_id"].map(currency_by_customer)
    assert (invoices["currency"] == matched).all()


def test_generate_fact_invoice_is_deterministic() -> None:
    config, customers = _sample_customers(25)
    first = generate_fact_invoice(config, customers)
    second = generate_fact_invoice(config, customers)
    pd.testing.assert_frame_equal(first, second)


def test_generate_fact_invoice_seed_changes_amounts() -> None:
    config, customers = _sample_customers(20)
    other = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"random_seed": 99})}
    )
    a = generate_fact_invoice(config, customers)
    b = generate_fact_invoice(other, customers)

    assert not a.equals(b)
