"""Customer Details — per-customer drill-down (Phase 5)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from app.utils.db import db_available

st.set_page_config(page_title="Customer Details", layout="wide")

st.title("Customer Details")
st.caption("Single-customer view across invoices, payments, risk, and claims.")

st.warning(
    "This application uses a fictional dataset and a demonstration risk "
    "methodology. It is not a production credit-rating model, regulatory "
    "model, or substitute for professional underwriting judgement."
)

if not db_available():
    st.info(
        "Coming soon — run the data pipeline to populate this page:\n\n"
        "```bash\npython -m src.run_pipeline --small\n```"
    )
else:
    st.info(
        "Database detected. Customer search, tabs, and history downloads "
        "will be wired in Phase 5."
    )
