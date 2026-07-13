"""Generate sparse synthetic credit-decision history for the credit-risk pipeline."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.config import ProjectConfig
from src.generators.common import make_faker
from src.generators.dates import DEFAULT_AS_OF_DATE, history_window_bounds

FACT_CREDIT_DECISION_COLUMNS = (
    "decision_id",
    "customer_id",
    "decision_date",
    "previous_limit",
    "new_limit",
    "decision_type",
    "decision_reason",
)

DECISION_TYPES = ("increase", "decrease", "new", "review", "hold")

# Sparse history: most customers have none; those who do usually have a single event.
DECISION_COUNT_CHOICES = (0, 1, 2, 3)
DECISION_COUNT_WEIGHTS = (0.55, 0.28, 0.12, 0.05)

# First decision leans toward onboarding / limit set; later events toward reviews.
FIRST_DECISION_TYPES = ("new", "increase", "decrease", "review", "hold")
FIRST_DECISION_WEIGHTS = (0.45, 0.25, 0.10, 0.12, 0.08)

LATER_DECISION_TYPES = ("increase", "decrease", "review", "hold")
LATER_DECISION_WEIGHTS = (0.35, 0.25, 0.25, 0.15)

DECISION_REASONS: dict[str, tuple[str, ...]] = {
    "new": (
        "New account setup",
        "Initial underwriting",
        "Onboarding credit facility",
    ),
    "increase": (
        "Strong payment history",
        "Revenue growth",
        "Relationship expansion",
        "Improved financials",
    ),
    "decrease": (
        "Deteriorating DSO",
        "Industry risk outlook",
        "Overdue concentration",
        "Weaker trading performance",
    ),
    "review": (
        "Periodic annual review",
        "No change warranted",
        "Limit confirmed after review",
    ),
    "hold": (
        "Pending financials",
        "Awaiting insurance confirmation",
        "Underwriting information incomplete",
    ),
}


def _decision_id(index: int) -> str:
    return f"CRD-{index:07d}"


def _to_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def _weighted_choice(faker, values: tuple[str, ...], weights: tuple[float, ...]) -> str:
    return faker.random.choices(values, weights=weights, k=1)[0]


def _decision_count(faker) -> int:
    return faker.random.choices(
        DECISION_COUNT_CHOICES, weights=DECISION_COUNT_WEIGHTS, k=1
    )[0]


def _pick_decision_type(faker, *, is_first: bool) -> str:
    if is_first:
        return _weighted_choice(faker, FIRST_DECISION_TYPES, FIRST_DECISION_WEIGHTS)
    return _weighted_choice(faker, LATER_DECISION_TYPES, LATER_DECISION_WEIGHTS)


def _decision_dates(
    faker,
    *,
    earliest: date,
    latest: date,
    n: int,
) -> list[date]:
    """Pick ``n`` non-decreasing decision dates within ``[earliest, latest]``."""
    if n <= 0:
        return []
    if earliest > latest:
        return [latest] * n

    dates: list[date] = []
    start = earliest
    for _ in range(n):
        decision_date = faker.date_between(start_date=start, end_date=latest)
        dates.append(decision_date)
        start = decision_date
    return dates


def _prior_limit(faker, *, new_limit: float, decision_type: str) -> float:
    """Infer ``previous_limit`` so the type matches the limit movement."""
    if decision_type in ("review", "hold"):
        return round(new_limit, 2)
    if decision_type == "new":
        return 0.0

    ratio = faker.pyfloat(min_value=0.08, max_value=0.35)
    if decision_type == "increase":
        # previous < new
        previous = new_limit / (1.0 + ratio)
    else:
        # decrease: previous > new
        previous = new_limit * (1.0 + ratio)
    return round(max(previous, 0.0), 2)


def _limit_chain(
    faker,
    *,
    final_limit: float,
    decision_types: list[str],
) -> list[tuple[float, float]]:
    """Build ``(previous_limit, new_limit)`` pairs ending at ``final_limit``.

    Walks backwards from the customer's current limit so the latest decision
    lands on ``dim_customer.credit_limit``.
    """
    if not decision_types:
        return []

    pairs_rev: list[tuple[float, float]] = []
    new_limit = round(float(final_limit), 2)
    for decision_type in reversed(decision_types):
        previous = _prior_limit(faker, new_limit=new_limit, decision_type=decision_type)
        pairs_rev.append((previous, new_limit))
        new_limit = previous

    pairs_rev.reverse()
    return pairs_rev


def generate_fact_credit_decision(
    config: ProjectConfig,
    customers: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build sparse ``fact_credit_decision`` rows linked to ``customers``.

    Many customers have no decisions; others get a short chronological chain
    whose final ``new_limit`` matches ``credit_limit``. Decision dates fall on
    or after ``created_date`` (clamped into the history window) and on or before
    the as-of date. No risk or collections scores are computed here.
    """
    if customers.empty:
        raise ValueError("customers must contain at least one row")
    required = {"customer_id", "credit_limit", "created_date"}
    missing = required - set(customers.columns)
    if missing:
        raise ValueError(f"customers missing required columns: {sorted(missing)}")

    end = as_of if as_of is not None else DEFAULT_AS_OF_DATE
    history_start, history_end = history_window_bounds(
        config.pipeline.history_months, as_of=end
    )

    faker = make_faker(config.pipeline.random_seed)
    rows: list[dict[str, object]] = []
    decision_index = 1

    for record in customers.to_dict(orient="records"):
        n = _decision_count(faker)
        if n == 0:
            continue

        customer_id = str(record["customer_id"])
        created = _to_date(record["created_date"])
        earliest = max(created, history_start)
        if earliest > history_end:
            continue

        types = [_pick_decision_type(faker, is_first=(i == 0)) for i in range(n)]
        dates = _decision_dates(
            faker, earliest=earliest, latest=history_end, n=n
        )
        pairs = _limit_chain(
            faker,
            final_limit=float(record["credit_limit"]),
            decision_types=types,
        )

        for decision_type, decision_date, (previous_limit, new_limit) in zip(
            types, dates, pairs, strict=True
        ):
            rows.append(
                {
                    "decision_id": _decision_id(decision_index),
                    "customer_id": customer_id,
                    "decision_date": decision_date,
                    "previous_limit": previous_limit,
                    "new_limit": new_limit,
                    "decision_type": decision_type,
                    "decision_reason": faker.random_element(
                        DECISION_REASONS[decision_type]
                    ),
                }
            )
            decision_index += 1

    return pd.DataFrame(rows, columns=list(FACT_CREDIT_DECISION_COLUMNS))
