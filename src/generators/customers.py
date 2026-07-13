"""Generate the synthetic customer dimension for the credit-risk pipeline."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.config import ProjectConfig
from src.generators.common import make_faker
from src.generators.dates import DEFAULT_AS_OF_DATE, history_window_bounds

DIM_CUSTOMER_COLUMNS = (
    "customer_id",
    "name",
    "country",
    "region",
    "industry",
    "annual_revenue",
    "account_manager",
    "collections_owner",
    "status",
    "credit_insurance_status",
    "credit_limit",
    "currency",
    "business_unit",
    "created_date",
)

# Country → regions kept coherent so filter drill-downs look realistic.
COUNTRY_REGIONS: dict[str, tuple[str, ...]] = {
    "United Kingdom": (
        "London & South East",
        "Midlands",
        "North of England",
        "Scotland",
        "Wales",
    ),
    "Ireland": ("Dublin & East", "Munster", "Connacht & Ulster"),
    "Germany": ("North Germany", "South Germany", "West Germany"),
    "France": ("Île-de-France", "Hauts-de-France", "Auvergne-Rhône-Alpes"),
    "Netherlands": ("Randstad", "North Netherlands", "South Netherlands"),
    "United States": ("Northeast", "Midwest", "South", "West"),
    "Spain": ("Madrid", "Catalonia", "Andalusia"),
}

INDUSTRIES = (
    "Manufacturing",
    "Wholesale & Distribution",
    "Retail",
    "Construction",
    "Technology",
    "Healthcare",
    "Professional Services",
    "Transportation & Logistics",
    "Energy & Utilities",
    "Hospitality",
)

STATUSES = ("active", "inactive", "watchlist")
STATUS_WEIGHTS = (0.82, 0.08, 0.10)

CREDIT_INSURANCE_STATUSES = ("insured", "uninsured", "partial")
CREDIT_INSURANCE_WEIGHTS = (0.55, 0.30, 0.15)

CURRENCIES = ("GBP", "EUR", "USD")
CURRENCY_WEIGHTS = (0.70, 0.20, 0.10)

BUSINESS_UNITS = (
    "Commercial Credit",
    "Trade Finance",
    "SME Lending",
    "Corporate Banking",
)

# Prefer UK-centric portfolio for a GBP demo dashboard.
COUNTRY_WEIGHTS = (0.45, 0.08, 0.12, 0.10, 0.08, 0.12, 0.05)

# Account / collections owners drawn from a fixed pool so filters stay usable.
ACCOUNT_MANAGER_POOL = (
    "Amelia Hughes",
    "James Okonkwo",
    "Sophie Müller",
    "Liam O'Brien",
    "Priya Shah",
    "Noah Bennett",
    "Elena Rossi",
    "Marcus Webb",
)

COLLECTIONS_OWNER_POOL = (
    "Hannah Cole",
    "Diego Alvarez",
    "Fatima Khan",
    "Oliver Grant",
    "Chloe Martin",
    "Ethan Brooks",
)


def _customer_id(index: int) -> str:
    return f"CUST-{index:06d}"


def _weighted_choice(faker, values: tuple[str, ...], weights: tuple[float, ...]) -> str:
    return faker.random.choices(values, weights=weights, k=1)[0]


def generate_dim_customer(
    config: ProjectConfig,
    *,
    n: int | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build ``dim_customer`` with ``n`` synthetic rows (default: ``num_customers``).

    Filter dimensions (country, region, industry, managers, insurance, status,
    currency, business unit) are always populated. ``created_date`` falls on or
    before the pipeline as-of date and may precede the history window start.
    """
    count = config.pipeline.num_customers if n is None else n
    if count < 1:
        raise ValueError(f"customer count must be >= 1, got {count}")

    end = as_of if as_of is not None else DEFAULT_AS_OF_DATE
    history_start, _ = history_window_bounds(config.pipeline.history_months, as_of=end)
    # Allow onboarding before the analytical history window.
    earliest_created = history_start - timedelta(days=365 * 5)

    faker = make_faker(config.pipeline.random_seed)
    countries = tuple(COUNTRY_REGIONS.keys())

    rows: list[dict[str, object]] = []
    for index in range(1, count + 1):
        country = _weighted_choice(faker, countries, COUNTRY_WEIGHTS)
        region = faker.random_element(COUNTRY_REGIONS[country])
        annual_revenue = float(faker.random_int(min=250_000, max=85_000_000))
        # Credit limit roughly scales with revenue (demo heuristic, not a model).
        limit_ratio = faker.pyfloat(min_value=0.05, max_value=0.25)
        credit_limit = round(annual_revenue * limit_ratio, 2)

        rows.append(
            {
                "customer_id": _customer_id(index),
                "name": faker.company(),
                "country": country,
                "region": region,
                "industry": faker.random_element(INDUSTRIES),
                "annual_revenue": annual_revenue,
                "account_manager": faker.random_element(ACCOUNT_MANAGER_POOL),
                "collections_owner": faker.random_element(COLLECTIONS_OWNER_POOL),
                "status": _weighted_choice(faker, STATUSES, STATUS_WEIGHTS),
                "credit_insurance_status": _weighted_choice(
                    faker, CREDIT_INSURANCE_STATUSES, CREDIT_INSURANCE_WEIGHTS
                ),
                "credit_limit": credit_limit,
                "currency": _weighted_choice(faker, CURRENCIES, CURRENCY_WEIGHTS),
                "business_unit": faker.random_element(BUSINESS_UNITS),
                "created_date": faker.date_between(
                    start_date=earliest_created, end_date=end
                ),
            }
        )

    return pd.DataFrame(rows, columns=list(DIM_CUSTOMER_COLUMNS))
