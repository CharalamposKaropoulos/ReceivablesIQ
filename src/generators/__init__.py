"""Synthetic data generators for the credit-risk pipeline."""

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
    DIM_CUSTOMER_COLUMNS,
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
    generate_fact_invoice,
)
from src.generators.payments import (
    FACT_PAYMENT_COLUMNS,
    generate_fact_payment,
)

__all__ = [
    "CLAIM_STATUSES",
    "DEFAULT_AS_OF_DATE",
    "DEFAULT_PROCESSED_DIR",
    "DEFAULT_RAW_DIR",
    "DECISION_TYPES",
    "DIM_CUSTOMER_COLUMNS",
    "DIM_DATE_COLUMNS",
    "FACT_CLAIM_COLUMNS",
    "FACT_CREDIT_DECISION_COLUMNS",
    "FACT_INVOICE_COLUMNS",
    "FACT_PAYMENT_COLUMNS",
    "INSURERS",
    "generate_dim_customer",
    "generate_dim_date",
    "generate_fact_claim",
    "generate_fact_credit_decision",
    "generate_fact_invoice",
    "generate_fact_payment",
    "history_window_bounds",
    "make_faker",
    "processed_dir",
    "processed_path",
    "raw_dir",
    "raw_path",
    "write_csv",
    "write_parquet",
]
