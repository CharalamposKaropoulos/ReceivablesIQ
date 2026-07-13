"""Generate synthetic insurance claims / recoveries for the credit-risk pipeline."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.config import ProjectConfig
from src.generators.common import make_faker
from src.generators.dates import DEFAULT_AS_OF_DATE, history_window_bounds

FACT_CLAIM_COLUMNS = (
    "claim_id",
    "customer_id",
    "invoice_id",
    "claim_date",
    "claim_amount",
    "status",
    "insurer",
    "recovery_amount",
)

CLAIM_STATUSES = ("submitted", "approved", "rejected", "settled")
CLAIM_STATUS_WEIGHTS = (0.25, 0.20, 0.15, 0.40)

# Trade-credit style insurers (demo names; not endorsements).
INSURERS = (
    "Allianz Trade",
    "Atradius",
    "Coface",
    "QBE Trade Credit",
    "Zurich Trade Credit",
    "Nexus Trade Credit",
)

# Only overdue / written-off exposure is claim-eligible in clean data.
CLAIMABLE_INVOICE_STATUSES = ("overdue", "written_off")

# Customers must have some insurance cover to file.
INSURED_CUSTOMER_STATUSES = ("insured", "partial")

# Sparse: only a subset of eligible invoices become claims.
CLAIM_PROBABILITY_BY_STATUS: dict[str, float] = {
    "overdue": 0.18,
    "written_off": 0.55,
}


def _claim_id(index: int) -> str:
    return f"CLM-{index:07d}"


def _to_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def _weighted_choice(faker, values: tuple[str, ...], weights: tuple[float, ...]) -> str:
    return faker.random.choices(values, weights=weights, k=1)[0]


def _claim_amount(
    faker,
    *,
    outstanding_amount: float,
    insurance_status: str,
) -> float:
    """Size the claim from outstanding exposure and cover type."""
    outstanding = max(float(outstanding_amount), 0.0)
    if outstanding <= 0:
        return 0.0

    if insurance_status == "partial":
        cover_ratio = faker.pyfloat(min_value=0.35, max_value=0.70)
    else:
        # Fully insured: claim most or all of the outstanding balance.
        cover_ratio = faker.pyfloat(min_value=0.85, max_value=1.0)

    return round(max(outstanding * cover_ratio, 0.0), 2)


def _recovery_amount(faker, *, claim_amount: float, status: str) -> float:
    """Recovery is zero until settled; settled recoveries stay ≤ claim_amount."""
    if status != "settled" or claim_amount <= 0:
        return 0.0
    recovery_ratio = faker.pyfloat(min_value=0.40, max_value=1.0)
    return round(min(claim_amount * recovery_ratio, claim_amount), 2)


def _should_file_claim(faker, invoice_status: str) -> bool:
    probability = CLAIM_PROBABILITY_BY_STATUS.get(invoice_status, 0.0)
    if probability <= 0:
        return False
    return faker.random.random() < probability


def generate_fact_claim(
    config: ProjectConfig,
    customers: pd.DataFrame,
    invoices: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build sparse ``fact_claim`` rows for insured overdue / written-off exposure.

    Claims are filed against a subset of invoices whose customer has
    ``credit_insurance_status`` of ``insured`` or ``partial``. Each selected
    invoice yields at most one claim (``invoice_id`` populated). Claim dates
    fall on or after the invoice ``due_date`` and on or before the as-of date.
    Amounts are non-negative; settled recoveries do not exceed ``claim_amount``.
    No risk or collections scores are computed here.
    """
    if customers.empty:
        raise ValueError("customers must contain at least one row")
    if invoices.empty:
        raise ValueError("invoices must contain at least one row")

    customer_required = {"customer_id", "credit_insurance_status"}
    customer_missing = customer_required - set(customers.columns)
    if customer_missing:
        raise ValueError(
            f"customers missing required columns: {sorted(customer_missing)}"
        )

    invoice_required = {
        "invoice_id",
        "customer_id",
        "due_date",
        "outstanding_amount",
        "status",
    }
    invoice_missing = invoice_required - set(invoices.columns)
    if invoice_missing:
        raise ValueError(
            f"invoices missing required columns: {sorted(invoice_missing)}"
        )

    end = as_of if as_of is not None else DEFAULT_AS_OF_DATE
    _, history_end = history_window_bounds(config.pipeline.history_months, as_of=end)

    insurance_by_customer = customers.set_index("customer_id")[
        "credit_insurance_status"
    ].astype(str)

    faker = make_faker(config.pipeline.random_seed)
    rows: list[dict[str, object]] = []
    claim_index = 1

    for record in invoices.to_dict(orient="records"):
        customer_id = str(record["customer_id"])
        if customer_id not in insurance_by_customer.index:
            continue

        insurance_status = str(insurance_by_customer.loc[customer_id])
        if insurance_status not in INSURED_CUSTOMER_STATUSES:
            continue

        invoice_status = str(record["status"])
        if invoice_status not in CLAIMABLE_INVOICE_STATUSES:
            continue

        outstanding = float(record["outstanding_amount"])
        if outstanding <= 0:
            continue

        due_date = _to_date(record["due_date"])
        if due_date > history_end:
            continue

        if not _should_file_claim(faker, invoice_status):
            continue

        claim_amount = _claim_amount(
            faker,
            outstanding_amount=outstanding,
            insurance_status=insurance_status,
        )
        if claim_amount <= 0:
            continue

        status = _weighted_choice(faker, CLAIM_STATUSES, CLAIM_STATUS_WEIGHTS)
        claim_date = faker.date_between(start_date=due_date, end_date=history_end)

        rows.append(
            {
                "claim_id": _claim_id(claim_index),
                "customer_id": customer_id,
                "invoice_id": str(record["invoice_id"]),
                "claim_date": claim_date,
                "claim_amount": claim_amount,
                "status": status,
                "insurer": faker.random_element(INSURERS),
                "recovery_amount": _recovery_amount(
                    faker, claim_amount=claim_amount, status=status
                ),
            }
        )
        claim_index += 1

    return pd.DataFrame(rows, columns=list(FACT_CLAIM_COLUMNS))
