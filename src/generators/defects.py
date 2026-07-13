"""Inject configurable data-quality defects into clean synthetic tables.

Defects are applied after clean generation so Phase 4 validation can detect them.
Controlled by ``pipeline.inject_data_quality_defects``, ``pipeline.defect_rate``,
and the CLI ``--skip-defects`` flag (passed as ``skip=True``).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.config import ProjectConfig
from src.generators.common import make_faker

DEFECT_AUDIT_COLUMNS = (
    "defect_id",
    "defect_type",
    "table_name",
    "record_id",
    "column_name",
    "original_value",
    "injected_value",
    "description",
)

DEFECT_TYPES = (
    "missing_customer_id",
    "duplicate_invoice",
    "payment_exceeds_invoice",
    "invalid_date",
)

# Offset keeps the defect RNG stream independent of entity generators.
_DEFECT_SEED_OFFSET = 17_003


def _empty_audit_log() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DEFECT_AUDIT_COLUMNS))


def _should_inject(config: ProjectConfig, *, skip: bool) -> bool:
    if skip:
        return False
    if not config.pipeline.inject_data_quality_defects:
        return False
    if config.pipeline.defect_rate <= 0:
        return False
    return True


def _defect_count(n_rows: int, rate: float) -> int:
    """How many rows to corrupt for one defect type.

    When ``rate > 0`` and the table is non-empty, inject at least one row so
    small demo / test datasets still show measurable defects.
    """
    if n_rows <= 0 or rate <= 0:
        return 0
    return min(n_rows, max(1, int(round(n_rows * rate))))


def _sample_positions(faker, n_rows: int, rate: float) -> list[int]:
    count = _defect_count(n_rows, rate)
    if count == 0:
        return []
    return sorted(faker.random.sample(range(n_rows), k=count))


def _to_str(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def _append_audit(
    audit_rows: list[dict[str, object]],
    *,
    defect_type: str,
    table_name: str,
    record_id: object,
    column_name: str,
    original_value: object,
    injected_value: object,
    description: str,
) -> None:
    audit_rows.append(
        {
            "defect_id": f"DEF-{len(audit_rows) + 1:07d}",
            "defect_type": defect_type,
            "table_name": table_name,
            "record_id": _to_str(record_id),
            "column_name": column_name,
            "original_value": _to_str(original_value),
            "injected_value": _to_str(injected_value),
            "description": description,
        }
    )


def _inject_missing_customer_ids(
    faker,
    invoices: pd.DataFrame,
    rate: float,
    audit_rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Null ``customer_id`` on a sample of invoice rows."""
    if invoices.empty:
        return invoices

    positions = _sample_positions(faker, len(invoices), rate)
    if not positions:
        return invoices

    out = invoices.copy()
    out["customer_id"] = out["customer_id"].astype(object)
    for pos in positions:
        original = out.iat[pos, out.columns.get_loc("customer_id")]
        record_id = out.iat[pos, out.columns.get_loc("invoice_id")]
        out.iat[pos, out.columns.get_loc("customer_id")] = None
        _append_audit(
            audit_rows,
            defect_type="missing_customer_id",
            table_name="fact_invoice",
            record_id=record_id,
            column_name="customer_id",
            original_value=original,
            injected_value="",
            description="Cleared customer_id on invoice row",
        )
    return out


def _inject_duplicate_invoices(
    faker,
    invoices: pd.DataFrame,
    rate: float,
    audit_rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Append duplicate copies of sampled invoice rows (same ``invoice_id``)."""
    if invoices.empty:
        return invoices

    positions = _sample_positions(faker, len(invoices), rate)
    if not positions:
        return invoices

    duplicates = invoices.iloc[positions].copy()
    for _, row in duplicates.iterrows():
        _append_audit(
            audit_rows,
            defect_type="duplicate_invoice",
            table_name="fact_invoice",
            record_id=row["invoice_id"],
            column_name="invoice_id",
            original_value=row["invoice_id"],
            injected_value=row["invoice_id"],
            description="Appended duplicate invoice row with the same invoice_id",
        )
    return pd.concat([invoices, duplicates], ignore_index=True)


def _inject_oversized_payments(
    faker,
    payments: pd.DataFrame,
    invoices: pd.DataFrame,
    rate: float,
    audit_rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Inflate ``payment_amount`` so it exceeds the linked invoice amount."""
    if payments.empty or invoices.empty:
        return payments

    amount_by_invoice = invoices.drop_duplicates(subset=["invoice_id"]).set_index(
        "invoice_id"
    )["invoice_amount"]

    eligible = [
        i
        for i in range(len(payments))
        if payments.iloc[i]["invoice_id"] in amount_by_invoice.index
    ]
    if not eligible:
        return payments

    count = _defect_count(len(eligible), rate)
    if count == 0:
        return payments

    chosen = sorted(faker.random.sample(eligible, k=count))
    out = payments.copy()
    amount_col = out.columns.get_loc("payment_amount")

    for pos in chosen:
        invoice_id = out.iat[pos, out.columns.get_loc("invoice_id")]
        payment_id = out.iat[pos, out.columns.get_loc("payment_id")]
        invoice_amount = float(amount_by_invoice.loc[invoice_id])
        original = float(out.iat[pos, amount_col])
        multiplier = faker.pyfloat(min_value=1.25, max_value=2.75)
        injected = round(max(invoice_amount * multiplier, invoice_amount + 1.0), 2)
        out.iat[pos, amount_col] = injected
        _append_audit(
            audit_rows,
            defect_type="payment_exceeds_invoice",
            table_name="fact_payment",
            record_id=payment_id,
            column_name="payment_amount",
            original_value=original,
            injected_value=injected,
            description=(
                f"Raised payment_amount above invoice_amount ({invoice_amount}) "
                f"for invoice_id={invoice_id}"
            ),
        )
    return out


def _inject_invalid_dates(
    faker,
    invoices: pd.DataFrame,
    payments: pd.DataFrame,
    rate: float,
    audit_rows: list[dict[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Corrupt dates: due_date before invoice_date; payment_date before invoice_date."""
    out_invoices = invoices
    out_payments = payments

    if not invoices.empty:
        positions = _sample_positions(faker, len(invoices), rate)
        if positions:
            out_invoices = invoices.copy()
            due_col = out_invoices.columns.get_loc("due_date")
            inv_date_col = out_invoices.columns.get_loc("invoice_date")
            id_col = out_invoices.columns.get_loc("invoice_id")
            for pos in positions:
                invoice_id = out_invoices.iat[pos, id_col]
                invoice_date = pd.Timestamp(out_invoices.iat[pos, inv_date_col]).date()
                original = out_invoices.iat[pos, due_col]
                # Due date clearly before the invoice date.
                injected: date = invoice_date - timedelta(
                    days=int(faker.random.randint(1, 45))
                )
                out_invoices.iat[pos, due_col] = injected
                _append_audit(
                    audit_rows,
                    defect_type="invalid_date",
                    table_name="fact_invoice",
                    record_id=invoice_id,
                    column_name="due_date",
                    original_value=original,
                    injected_value=injected,
                    description="Set due_date before invoice_date",
                )

    if not payments.empty and not invoices.empty:
        invoice_date_by_id = invoices.drop_duplicates(subset=["invoice_id"]).set_index(
            "invoice_id"
        )["invoice_date"]
        eligible = [
            i
            for i in range(len(payments))
            if payments.iloc[i]["invoice_id"] in invoice_date_by_id.index
        ]
        count = _defect_count(len(eligible), rate) if eligible else 0
        if count > 0:
            chosen = sorted(faker.random.sample(eligible, k=count))
            out_payments = payments.copy()
            pay_date_col = out_payments.columns.get_loc("payment_date")
            pay_id_col = out_payments.columns.get_loc("payment_id")
            inv_id_col = out_payments.columns.get_loc("invoice_id")
            for pos in chosen:
                payment_id = out_payments.iat[pos, pay_id_col]
                invoice_id = out_payments.iat[pos, inv_id_col]
                invoice_date = pd.Timestamp(invoice_date_by_id.loc[invoice_id]).date()
                original = out_payments.iat[pos, pay_date_col]
                injected = invoice_date - timedelta(
                    days=int(faker.random.randint(1, 30))
                )
                out_payments.iat[pos, pay_date_col] = injected
                _append_audit(
                    audit_rows,
                    defect_type="invalid_date",
                    table_name="fact_payment",
                    record_id=payment_id,
                    column_name="payment_date",
                    original_value=original,
                    injected_value=injected,
                    description="Set payment_date before invoice_date",
                )

    return out_invoices, out_payments


def inject_data_quality_defects(
    config: ProjectConfig,
    customers: pd.DataFrame,
    invoices: pd.DataFrame,
    payments: pd.DataFrame,
    *,
    skip: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Inject Page-5-aligned DQ defects into clean synthetic frames.

    Returns ``(customers, invoices, payments, audit_log)``. ``customers`` is
    returned as an unchanged copy (missing identifiers are injected on invoice
    rows). When ``skip`` is true, injection is disabled in config, or
    ``defect_rate`` is 0, returns deep copies of the inputs and an empty audit
    log.

    Defect types:
    - ``missing_customer_id`` — null ``fact_invoice.customer_id``
    - ``duplicate_invoice`` — duplicate ``fact_invoice`` rows
    - ``payment_exceeds_invoice`` — ``payment_amount`` > linked ``invoice_amount``
    - ``invalid_date`` — ``due_date`` / ``payment_date`` before invoice date
    """
    customers_out = customers.copy()
    invoices_out = invoices.copy()
    payments_out = payments.copy()

    if not _should_inject(config, skip=skip):
        return customers_out, invoices_out, payments_out, _empty_audit_log()

    rate = float(config.pipeline.defect_rate)
    faker = make_faker(config.pipeline.random_seed + _DEFECT_SEED_OFFSET)
    audit_rows: list[dict[str, object]] = []

    # Duplicates first so later defects can also land on duplicated keys.
    invoices_out = _inject_duplicate_invoices(faker, invoices_out, rate, audit_rows)
    invoices_out = _inject_missing_customer_ids(faker, invoices_out, rate, audit_rows)
    payments_out = _inject_oversized_payments(
        faker, payments_out, invoices_out, rate, audit_rows
    )
    invoices_out, payments_out = _inject_invalid_dates(
        faker, invoices_out, payments_out, rate, audit_rows
    )

    audit_log = pd.DataFrame(audit_rows, columns=list(DEFECT_AUDIT_COLUMNS))
    return customers_out, invoices_out, payments_out, audit_log
