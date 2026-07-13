"""Generate the synthetic payment fact table for the credit-risk pipeline."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.config import ProjectConfig
from src.generators.common import make_faker
from src.generators.dates import DEFAULT_AS_OF_DATE, history_window_bounds

FACT_PAYMENT_COLUMNS = (
    "payment_id",
    "invoice_id",
    "customer_id",
    "payment_date",
    "payment_amount",
)


def _payment_id(index: int) -> str:
    return f"PAY-{index:07d}"


def _to_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def _paid_amount(invoice_amount: float, outstanding_amount: float) -> float:
    """Cash applied so far on a clean invoice row."""
    paid = round(float(invoice_amount) - float(outstanding_amount), 2)
    return max(paid, 0.0)


def _split_payment_amounts(faker, total: float) -> list[float]:
    """Split ``total`` into one or a few positive payment events."""
    if total <= 0:
        return []

    # Prefer a single settlement; occasionally split into instalments.
    n_payments = faker.random.choices([1, 2, 3], weights=[0.70, 0.22, 0.08], k=1)[0]
    if n_payments == 1 or total < 1.0:
        return [round(total, 2)]

    amounts: list[float] = []
    remaining = total
    for i in range(n_payments - 1):
        # Leave at least 0.01 for each remaining payment.
        slots_left = n_payments - i
        max_share = remaining - 0.01 * (slots_left - 1)
        if max_share <= 0.01:
            break
        share = round(faker.pyfloat(min_value=0.01, max_value=float(max_share)), 2)
        amounts.append(share)
        remaining = round(remaining - share, 2)

    if remaining > 0:
        amounts.append(round(remaining, 2))
    return amounts


def _payment_dates(
    faker,
    *,
    invoice_date: date,
    as_of: date,
    n: int,
) -> list[date]:
    """Pick ``n`` non-decreasing payment dates on/after the invoice date."""
    if n <= 0:
        return []
    if invoice_date > as_of:
        return [invoice_date] * n

    dates: list[date] = []
    earliest = invoice_date
    for _ in range(n):
        payment_date = faker.date_between(start_date=earliest, end_date=as_of)
        dates.append(payment_date)
        # Keep later instalments on or after earlier ones.
        earliest = payment_date
    return dates


def generate_fact_payment(
    config: ProjectConfig,
    invoices: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build ``fact_payment`` rows from clean invoice outstanding balances.

    Every ``invoice_id`` / ``customer_id`` references ``invoices``. Payment dates
    fall on or after the linked ``invoice_date`` and on or before the as-of date.
    Paid / partial / written-off invoices get one or more events summing to
    ``invoice_amount - outstanding_amount``; open / overdue (full outstanding)
    produce no payments. No risk or collections scores are computed here.
    """
    if invoices.empty:
        raise ValueError("invoices must contain at least one row")
    required = {"invoice_id", "customer_id", "invoice_date", "invoice_amount", "outstanding_amount"}
    missing = required - set(invoices.columns)
    if missing:
        raise ValueError(f"invoices missing required columns: {sorted(missing)}")

    end = as_of if as_of is not None else DEFAULT_AS_OF_DATE
    _, history_end = history_window_bounds(config.pipeline.history_months, as_of=end)

    faker = make_faker(config.pipeline.random_seed)
    rows: list[dict[str, object]] = []
    payment_index = 1

    for record in invoices.to_dict(orient="records"):
        invoice_id = str(record["invoice_id"])
        customer_id = str(record["customer_id"])
        invoice_date = _to_date(record["invoice_date"])
        paid = _paid_amount(record["invoice_amount"], record["outstanding_amount"])
        if paid <= 0:
            continue

        amounts = _split_payment_amounts(faker, paid)
        dates = _payment_dates(
            faker,
            invoice_date=invoice_date,
            as_of=history_end,
            n=len(amounts),
        )

        for amount, payment_date in zip(amounts, dates, strict=True):
            rows.append(
                {
                    "payment_id": _payment_id(payment_index),
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "payment_date": payment_date,
                    "payment_amount": amount,
                }
            )
            payment_index += 1

    return pd.DataFrame(rows, columns=list(FACT_PAYMENT_COLUMNS))
