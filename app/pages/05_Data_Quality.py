"""Data Quality — validation and freshness monitoring (Phase 5)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from app.utils.db import db_available

st.set_page_config(page_title="Data Quality", layout="wide")

st.title("Data Quality")
st.caption("Validation results, failure trends, and refresh / freshness status.")

if not db_available():
    st.info(
        "Coming soon — run the data pipeline to populate this page:\n\n"
        "```bash\npython -m src.run_pipeline --small\n```"
    )
else:
    st.info(
        "Database detected. Validation KPIs, failure trends, and failed-record "
        "samples will be wired in Phase 5."
    )
