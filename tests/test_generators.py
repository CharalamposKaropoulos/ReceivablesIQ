"""Tests for synthetic data generators (Phase 2)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.generators.claims import (
    CLAIM_STATUSES,
    FACT_CLAIM_COLUMNS,
    INSURERS,
    generate_fact_claim,
)
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
from src.generators.credit_decisions import (
    DECISION_TYPES,
    FACT_CREDIT_DECISION_COLUMNS,
    generate_fact_credit_decision,
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
from src.generators.defects import (
    DEFECT_AUDIT_COLUMNS,
    DEFECT_TYPES,
    inject_data_quality_defects,
)
from src.generators.invoices import (
    FACT_INVOICE_COLUMNS,
    INVOICE_STATUSES,
    generate_fact_invoice,
)
from src.generators.payments import (
    FACT_PAYMENT_COLUMNS,
    generate_fact_payment,
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


# --- fact_payment (Phase 2 step 07) ---------------------------------------------


def _sample_invoices(n_customers: int = 40):
    config, customers = _sample_customers(n_customers)
    invoices = generate_fact_invoice(config, customers)
    return config, customers, invoices


def test_generate_fact_payment_columns_and_ids() -> None:
    config, _, invoices = _sample_invoices(30)
    payments = generate_fact_payment(config, invoices)

    assert list(payments.columns) == list(FACT_PAYMENT_COLUMNS)
    assert len(payments) > 0
    assert payments["payment_id"].is_unique
    assert payments["payment_id"].iloc[0] == "PAY-0000001"
    assert (payments["payment_amount"] > 0).all()


def test_generate_fact_payment_invoice_fk_integrity() -> None:
    config, _, invoices = _sample_invoices(50)
    payments = generate_fact_payment(config, invoices)

    invoice_ids = set(invoices["invoice_id"])
    assert set(payments["invoice_id"]).issubset(invoice_ids)

    customer_by_invoice = invoices.set_index("invoice_id")["customer_id"]
    matched = payments["invoice_id"].map(customer_by_invoice)
    assert (payments["customer_id"] == matched).all()


def test_generate_fact_payment_date_on_or_after_invoice() -> None:
    config, _, invoices = _sample_invoices(40)
    payments = generate_fact_payment(config, invoices)

    _, as_of = history_window_bounds(config.pipeline.history_months)
    invoice_date_by_id = pd.to_datetime(
        invoices.set_index("invoice_id")["invoice_date"]
    ).dt.date
    payment_dates = pd.to_datetime(payments["payment_date"]).dt.date
    linked_invoice_dates = payments["invoice_id"].map(invoice_date_by_id)

    assert (payment_dates >= linked_invoice_dates).all()
    assert (payment_dates <= as_of).all()


def test_generate_fact_payment_sums_match_invoice_paid() -> None:
    config, _, invoices = _sample_invoices(45)
    payments = generate_fact_payment(config, invoices)

    paid_by_invoice = (
        payments.groupby("invoice_id", sort=False)["payment_amount"]
        .sum()
        .round(2)
    )
    expected = (
        invoices.assign(
            paid=(invoices["invoice_amount"] - invoices["outstanding_amount"]).round(2)
        )
        .loc[lambda df: df["paid"] > 0]
        .set_index("invoice_id")["paid"]
    )

    assert set(paid_by_invoice.index) == set(expected.index)
    pd.testing.assert_series_equal(
        paid_by_invoice.sort_index(),
        expected.sort_index(),
        check_names=False,
    )

    # Fully open / overdue invoices (nothing paid) produce no payment rows.
    unpaid_ids = set(
        invoices.loc[
            (invoices["invoice_amount"] - invoices["outstanding_amount"]).round(2) <= 0,
            "invoice_id",
        ]
    )
    assert unpaid_ids.isdisjoint(set(payments["invoice_id"]))


def test_generate_fact_payment_is_deterministic() -> None:
    config, _, invoices = _sample_invoices(25)
    first = generate_fact_payment(config, invoices)
    second = generate_fact_payment(config, invoices)
    pd.testing.assert_frame_equal(first, second)


def test_generate_fact_payment_seed_changes_rows() -> None:
    config, _, invoices = _sample_invoices(20)
    other = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"random_seed": 99})}
    )
    a = generate_fact_payment(config, invoices)
    b = generate_fact_payment(other, invoices)

    assert not a.equals(b)


# --- fact_credit_decision (Phase 2 step 08) -------------------------------------


def test_generate_fact_credit_decision_columns_and_ids() -> None:
    config, customers = _sample_customers(80)
    decisions = generate_fact_credit_decision(config, customers)

    assert list(decisions.columns) == list(FACT_CREDIT_DECISION_COLUMNS)
    assert len(decisions) > 0
    assert decisions["decision_id"].is_unique
    assert decisions["decision_id"].iloc[0] == "CRD-0000001"
    assert decisions["previous_limit"].notna().all()
    assert decisions["new_limit"].notna().all()
    assert (decisions["previous_limit"] >= 0).all()
    assert (decisions["new_limit"] >= 0).all()
    assert set(decisions["decision_type"]).issubset(DECISION_TYPES)
    assert decisions["decision_reason"].notna().all()


def test_generate_fact_credit_decision_customer_fk_integrity() -> None:
    config, customers = _sample_customers(100)
    decisions = generate_fact_credit_decision(config, customers)

    customer_ids = set(customers["customer_id"])
    assert set(decisions["customer_id"]).issubset(customer_ids)
    # Sparse: not every customer appears.
    assert len(set(decisions["customer_id"])) < len(customers)


def test_generate_fact_credit_decision_limits_match_type() -> None:
    config, customers = _sample_customers(120)
    decisions = generate_fact_credit_decision(config, customers)

    for decision_type, previous, new in zip(
        decisions["decision_type"],
        decisions["previous_limit"],
        decisions["new_limit"],
        strict=True,
    ):
        if decision_type in ("review", "hold"):
            assert previous == new
        elif decision_type == "increase":
            assert new > previous
        elif decision_type == "decrease":
            assert new < previous
        elif decision_type == "new":
            assert previous == 0.0
            assert new >= 0.0


def test_generate_fact_credit_decision_final_limit_matches_customer() -> None:
    config, customers = _sample_customers(90)
    decisions = generate_fact_credit_decision(config, customers)

    credit_by_customer = customers.set_index("customer_id")["credit_limit"]
    latest = (
        decisions.sort_values(["customer_id", "decision_date", "decision_id"])
        .groupby("customer_id", sort=False)
        .tail(1)
        .set_index("customer_id")
    )
    expected = latest.index.map(credit_by_customer)
    assert (latest["new_limit"].to_numpy() == expected.to_numpy()).all()


def test_generate_fact_credit_decision_dates_in_window() -> None:
    config, customers = _sample_customers(80)
    decisions = generate_fact_credit_decision(config, customers)

    history_start, as_of = history_window_bounds(config.pipeline.history_months)
    created_by_id = pd.to_datetime(
        customers.set_index("customer_id")["created_date"]
    ).dt.date
    decision_dates = pd.to_datetime(decisions["decision_date"]).dt.date
    created = decisions["customer_id"].map(created_by_id)

    assert (decision_dates >= history_start).all()
    assert (decision_dates <= as_of).all()
    assert (decision_dates >= created).all()


def test_generate_fact_credit_decision_is_deterministic() -> None:
    config, customers = _sample_customers(40)
    first = generate_fact_credit_decision(config, customers)
    second = generate_fact_credit_decision(config, customers)
    pd.testing.assert_frame_equal(first, second)


def test_generate_fact_credit_decision_seed_changes_rows() -> None:
    config, customers = _sample_customers(50)
    other = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"random_seed": 99})}
    )
    a = generate_fact_credit_decision(config, customers)
    b = generate_fact_credit_decision(other, customers)

    assert not a.equals(b)


# --- fact_claim (Phase 2 step 09) -----------------------------------------------


def test_generate_fact_claim_columns_and_ids() -> None:
    config, customers, invoices = _sample_invoices(120)
    claims = generate_fact_claim(config, customers, invoices)

    assert list(claims.columns) == list(FACT_CLAIM_COLUMNS)
    assert len(claims) > 0
    assert claims["claim_id"].is_unique
    assert claims["claim_id"].iloc[0] == "CLM-0000001"
    assert (claims["claim_amount"] >= 0).all()
    assert (claims["recovery_amount"] >= 0).all()
    assert set(claims["status"]).issubset(CLAIM_STATUSES)
    assert set(claims["insurer"]).issubset(INSURERS)
    assert claims["insurer"].notna().all()


def test_generate_fact_claim_customer_and_invoice_fk() -> None:
    config, customers, invoices = _sample_invoices(100)
    claims = generate_fact_claim(config, customers, invoices)

    assert set(claims["customer_id"]).issubset(set(customers["customer_id"]))
    # invoice_id is optional in the schema but populated for these generators.
    assert claims["invoice_id"].notna().all()
    assert set(claims["invoice_id"]).issubset(set(invoices["invoice_id"]))
    assert claims["invoice_id"].is_unique


def test_generate_fact_claim_only_insured_overdue_exposure() -> None:
    config, customers, invoices = _sample_invoices(100)
    claims = generate_fact_claim(config, customers, invoices)

    insurance_by_id = customers.set_index("customer_id")["credit_insurance_status"]
    invoice_by_id = invoices.set_index("invoice_id")

    for customer_id, invoice_id in zip(
        claims["customer_id"], claims["invoice_id"], strict=True
    ):
        assert insurance_by_id.loc[customer_id] in ("insured", "partial")
        invoice = invoice_by_id.loc[invoice_id]
        assert invoice["status"] in ("overdue", "written_off")
        assert float(invoice["outstanding_amount"]) > 0


def test_generate_fact_claim_amounts_and_recovery() -> None:
    config, customers, invoices = _sample_invoices(120)
    claims = generate_fact_claim(config, customers, invoices)

    outstanding_by_invoice = invoices.set_index("invoice_id")["outstanding_amount"]
    claimed = claims["invoice_id"].map(outstanding_by_invoice)
    assert (claims["claim_amount"] <= claimed.round(2) + 1e-9).all()

    settled = claims.loc[claims["status"] == "settled"]
    if not settled.empty:
        assert (settled["recovery_amount"] > 0).all()
        assert (settled["recovery_amount"] <= settled["claim_amount"]).all()

    openish = claims.loc[claims["status"] != "settled"]
    if not openish.empty:
        assert (openish["recovery_amount"] == 0).all()


def test_generate_fact_claim_dates_after_due_date() -> None:
    config, customers, invoices = _sample_invoices(100)
    claims = generate_fact_claim(config, customers, invoices)

    _, as_of = history_window_bounds(config.pipeline.history_months)
    due_by_invoice = pd.to_datetime(
        invoices.set_index("invoice_id")["due_date"]
    ).dt.date
    claim_dates = pd.to_datetime(claims["claim_date"]).dt.date
    due_dates = claims["invoice_id"].map(due_by_invoice)

    assert (claim_dates >= due_dates).all()
    assert (claim_dates <= as_of).all()


def test_generate_fact_claim_is_deterministic() -> None:
    config, customers, invoices = _sample_invoices(60)
    first = generate_fact_claim(config, customers, invoices)
    second = generate_fact_claim(config, customers, invoices)
    pd.testing.assert_frame_equal(first, second)


def test_generate_fact_claim_seed_changes_rows() -> None:
    config, customers, invoices = _sample_invoices(80)
    other = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"random_seed": 99})}
    )
    a = generate_fact_claim(config, customers, invoices)
    b = generate_fact_claim(other, customers, invoices)

    assert not a.equals(b)


def test_generate_fact_claim_sparse_subset() -> None:
    config, customers, invoices = _sample_invoices(100)
    claims = generate_fact_claim(config, customers, invoices)

    insurance_by_id = customers.set_index("customer_id")["credit_insurance_status"]
    eligible = invoices.loc[
        invoices["customer_id"].map(insurance_by_id).isin(("insured", "partial"))
        & invoices["status"].isin(("overdue", "written_off"))
        & (invoices["outstanding_amount"] > 0)
    ]
    assert len(claims) < len(eligible)
    assert len(claims) > 0


# --- DQ defect injection (Phase 2 step 10) --------------------------------------


def _sample_payments(n_customers: int = 50):
    config, customers, invoices = _sample_invoices(n_customers)
    payments = generate_fact_payment(config, invoices)
    return config, customers, invoices, payments


def _config_with_defects(
    config,
    *,
    inject: bool = True,
    rate: float = 0.05,
    seed: int | None = None,
):
    updates: dict = {
        "inject_data_quality_defects": inject,
        "defect_rate": rate,
    }
    if seed is not None:
        updates["random_seed"] = seed
    return config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update=updates)}
    )


def test_inject_defects_skip_leaves_tables_unchanged() -> None:
    config, customers, invoices, payments = _sample_payments(40)
    cfg = _config_with_defects(config, inject=True, rate=0.1)

    out_c, out_i, out_p, audit = inject_data_quality_defects(
        cfg, customers, invoices, payments, skip=True
    )

    pd.testing.assert_frame_equal(out_c, customers)
    pd.testing.assert_frame_equal(out_i, invoices)
    pd.testing.assert_frame_equal(out_p, payments)
    assert list(audit.columns) == list(DEFECT_AUDIT_COLUMNS)
    assert audit.empty


def test_inject_defects_rate_zero_unchanged() -> None:
    config, customers, invoices, payments = _sample_payments(40)
    cfg = _config_with_defects(config, inject=True, rate=0.0)

    out_c, out_i, out_p, audit = inject_data_quality_defects(
        cfg, customers, invoices, payments
    )

    pd.testing.assert_frame_equal(out_c, customers)
    pd.testing.assert_frame_equal(out_i, invoices)
    pd.testing.assert_frame_equal(out_p, payments)
    assert audit.empty


def test_inject_defects_disabled_in_config_unchanged() -> None:
    config, customers, invoices, payments = _sample_payments(40)
    cfg = _config_with_defects(config, inject=False, rate=0.1)

    _, out_i, out_p, audit = inject_data_quality_defects(
        cfg, customers, invoices, payments
    )

    pd.testing.assert_frame_equal(out_i, invoices)
    pd.testing.assert_frame_equal(out_p, payments)
    assert audit.empty


def test_inject_defects_rate_positive_produces_measurable_defects() -> None:
    config, customers, invoices, payments = _sample_payments(60)
    cfg = _config_with_defects(config, inject=True, rate=0.08)

    _, out_i, out_p, audit = inject_data_quality_defects(
        cfg, customers, invoices, payments
    )

    assert not audit.empty
    assert set(audit["defect_type"]).issubset(DEFECT_TYPES)
    assert list(audit.columns) == list(DEFECT_AUDIT_COLUMNS)

    # Missing customer identifiers on invoices.
    assert out_i["customer_id"].isna().any()

    # Duplicate invoice_ids.
    assert not out_i["invoice_id"].is_unique
    assert len(out_i) > len(invoices)

    # Payments larger than linked invoice amount.
    amount_by_invoice = out_i.drop_duplicates(subset=["invoice_id"]).set_index(
        "invoice_id"
    )["invoice_amount"]
    linked = out_p["invoice_id"].map(amount_by_invoice)
    assert (out_p["payment_amount"] > linked).any()

    # Invalid dates: due before invoice and/or payment before invoice.
    due_before = pd.to_datetime(out_i["due_date"]).dt.date < pd.to_datetime(
        out_i["invoice_date"]
    ).dt.date
    assert due_before.any()

    inv_date_by_id = out_i.drop_duplicates(subset=["invoice_id"]).set_index(
        "invoice_id"
    )["invoice_date"]
    pay_dates = pd.to_datetime(out_p["payment_date"]).dt.date
    inv_dates = pd.to_datetime(out_p["invoice_id"].map(inv_date_by_id)).dt.date
    assert (pay_dates < inv_dates).any()


def test_inject_defects_does_not_mutate_inputs() -> None:
    config, customers, invoices, payments = _sample_payments(40)
    cfg = _config_with_defects(config, inject=True, rate=0.1)

    invoices_before = invoices.copy()
    payments_before = payments.copy()
    inject_data_quality_defects(cfg, customers, invoices, payments)

    pd.testing.assert_frame_equal(invoices, invoices_before)
    pd.testing.assert_frame_equal(payments, payments_before)


def test_inject_defects_is_deterministic() -> None:
    config, customers, invoices, payments = _sample_payments(45)
    cfg = _config_with_defects(config, inject=True, rate=0.06)

    a = inject_data_quality_defects(cfg, customers, invoices, payments)
    b = inject_data_quality_defects(cfg, customers, invoices, payments)

    for left, right in zip(a, b, strict=True):
        pd.testing.assert_frame_equal(left, right)


def test_inject_defects_seed_changes_audit() -> None:
    config, customers, invoices, payments = _sample_payments(50)
    cfg_a = _config_with_defects(config, inject=True, rate=0.06, seed=42)
    cfg_b = _config_with_defects(config, inject=True, rate=0.06, seed=99)

    _, _, _, audit_a = inject_data_quality_defects(
        cfg_a, customers, invoices, payments
    )
    _, _, _, audit_b = inject_data_quality_defects(
        cfg_b, customers, invoices, payments
    )

    assert not audit_a.equals(audit_b)


def test_inject_defects_audit_covers_all_types() -> None:
    config, customers, invoices, payments = _sample_payments(80)
    cfg = _config_with_defects(config, inject=True, rate=0.1)

    _, _, _, audit = inject_data_quality_defects(cfg, customers, invoices, payments)

    assert set(DEFECT_TYPES).issubset(set(audit["defect_type"]))
    assert audit["defect_id"].is_unique
    assert audit["defect_id"].iloc[0] == "DEF-0000001"
