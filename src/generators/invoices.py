"""Generate the synthetic invoice fact table for the credit-risk pipeline."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.config import ProjectConfig
from src.generators.common import make_faker
from src.generators.dates import DEFAULT_AS_OF_DATE, history_window_bounds

FACT_INVOICE_COLUMNS = (
    "invoice_id",
    "customer_id",
    "invoice_date",
    "due_date",
    "invoice_amount",
    "outstanding_amount",
    "currency",
    "dispute_flag",
    "status",
)

INVOICE_STATUSES = ("open", "overdue", "partial", "paid", "written_off")

# Payment terms in days (net terms common in trade credit).
PAYMENT_TERMS_DAYS = (30, 45, 60, 90)
PAYMENT_TERMS_WEIGHTS = (0.45, 0.25, 0.20, 0.10)

# Target mix for clean rows (before DQ defect injection in a later step).
STATUS_WEIGHTS = (0.18, 0.22, 0.25, 0.30, 0.05)

# Typical invoices per customer by account status.
INVOICE_COUNT_BY_STATUS: dict[str, tuple[int, int]] = {
    "active": (4, 14),
    "watchlist": (2, 10),
    "inactive": (0, 4),
}


def _invoice_id(index: int) -> str:
    return f"INV-{index:07d}"


def _weighted_choice(faker, values: tuple[str, ...], weights: tuple[float, ...]) -> str:
    return faker.random.choices(values, weights=weights, k=1)[0]


def _invoice_count_for_customer(faker, customer_status: str) -> int:
    low, high = INVOICE_COUNT_BY_STATUS.get(customer_status, (1, 8))
    if high < low:
        raise ValueError(f"invalid invoice count range for status {customer_status!r}")
    return faker.random_int(min=low, max=high)


def _choose_amounts(
    faker,
    *,
    status: str,
    credit_limit: float,
) -> tuple[float, float]:
    """Return ``(invoice_amount, outstanding_amount)`` consistent with ``status``."""
    # Scale invoice size to credit limit so utilisation looks plausible.
    base = max(float(credit_limit), 1_000.0)
    ratio = faker.pyfloat(min_value=0.01, max_value=0.18)
    invoice_amount = round(base * ratio, 2)
    invoice_amount = max(invoice_amount, 50.0)

    if status == "paid":
        return invoice_amount, 0.0
    if status == "open" or status == "overdue":
        return invoice_amount, invoice_amount
    if status == "partial":
        paid_ratio = faker.pyfloat(min_value=0.15, max_value=0.85)
        outstanding = round(invoice_amount * (1.0 - paid_ratio), 2)
        outstanding = min(max(outstanding, 0.01), invoice_amount - 0.01)
        return invoice_amount, round(outstanding, 2)
    # written_off — residual balance after write-off / recovery demo.
    residual_ratio = faker.pyfloat(min_value=0.0, max_value=0.40)
    outstanding = round(invoice_amount * residual_ratio, 2)
    return invoice_amount, outstanding


def _dates_for_status(
    faker,
    *,
    status: str,
    earliest: date,
    as_of: date,
    terms_days: int,
) -> tuple[date, date]:
    """Pick ``(invoice_date, due_date)`` coherent with ``status`` and the window."""
    if earliest > as_of:
        raise ValueError("earliest invoice date cannot be after as_of")

    if status == "open":
        # Still within terms: due on or after as_of.
        min_invoice = max(earliest, as_of - timedelta(days=terms_days))
        invoice_date = faker.date_between(start_date=min_invoice, end_date=as_of)
        due_date = invoice_date + timedelta(days=terms_days)
        if due_date < as_of:
            due_date = as_of
        return invoice_date, due_date

    if status == "overdue":
        # Past due with full balance still open.
        latest_due = as_of - timedelta(days=1)
        earliest_due = earliest + timedelta(days=terms_days)
        if earliest_due > latest_due:
            # Window too tight for true overdue — fall back to open-like dates.
            invoice_date = earliest
            return invoice_date, invoice_date + timedelta(days=terms_days)
        due_date = faker.date_between(start_date=earliest_due, end_date=latest_due)
        invoice_date = due_date - timedelta(days=terms_days)
        if invoice_date < earliest:
            invoice_date = earliest
            due_date = invoice_date + timedelta(days=terms_days)
        return invoice_date, due_date

    # paid / partial / written_off — any date in window is fine.
    invoice_date = faker.date_between(start_date=earliest, end_date=as_of)
    due_date = invoice_date + timedelta(days=terms_days)
    return invoice_date, due_date


def generate_fact_invoice(
    config: ProjectConfig,
    customers: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build ``fact_invoice`` rows linked to ``customers`` over the history window.

    Every ``customer_id`` references ``customers``. Invoice dates fall inside the
    pipeline history window (and on/after the customer's ``created_date`` when
    that overlaps the window). Outstanding balances never exceed invoice amounts
    on these clean rows. No risk scores are computed here.
    """
    if customers.empty:
        raise ValueError("customers must contain at least one row")
    if "customer_id" not in customers.columns:
        raise ValueError("customers must include a customer_id column")

    end = as_of if as_of is not None else DEFAULT_AS_OF_DATE
    history_start, history_end = history_window_bounds(
        config.pipeline.history_months, as_of=end
    )

    faker = make_faker(config.pipeline.random_seed)
    rows: list[dict[str, object]] = []
    invoice_index = 1

    for record in customers.to_dict(orient="records"):
        customer_id = str(record["customer_id"])
        currency = str(record.get("currency") or "GBP")
        customer_status = str(record.get("status") or "active")
        credit_limit = float(record.get("credit_limit") or 10_000.0)

        created = record.get("created_date")
        if created is None:
            created_date = history_start
        elif isinstance(created, date) and not isinstance(created, pd.Timestamp):
            created_date = created
        else:
            created_date = pd.Timestamp(created).date()

        earliest = max(history_start, created_date)
        if earliest > history_end:
            # Customer onboarded after the window — skip invoices.
            continue

        for _ in range(_invoice_count_for_customer(faker, customer_status)):
            status = _weighted_choice(faker, INVOICE_STATUSES, STATUS_WEIGHTS)
            terms_days = int(
                faker.random.choices(
                    PAYMENT_TERMS_DAYS, weights=PAYMENT_TERMS_WEIGHTS, k=1
                )[0]
            )
            invoice_date, due_date = _dates_for_status(
                faker,
                status=status,
                earliest=earliest,
                as_of=history_end,
                terms_days=terms_days,
            )
            # Reconcile status with due date when the window forced a fallback.
            if status == "overdue" and due_date >= history_end:
                status = "open"
            if status == "open" and due_date < history_end:
                status = "overdue"

            invoice_amount, outstanding_amount = _choose_amounts(
                faker, status=status, credit_limit=credit_limit
            )
            dispute_flag = bool(
                faker.random.random() < (0.18 if status in {"overdue", "partial"} else 0.05)
            )

            rows.append(
                {
                    "invoice_id": _invoice_id(invoice_index),
                    "customer_id": customer_id,
                    "invoice_date": invoice_date,
                    "due_date": due_date,
                    "invoice_amount": invoice_amount,
                    "outstanding_amount": outstanding_amount,
                    "currency": currency,
                    "dispute_flag": dispute_flag,
                    "status": status,
                }
            )
            invoice_index += 1

    return pd.DataFrame(rows, columns=list(FACT_INVOICE_COLUMNS))
