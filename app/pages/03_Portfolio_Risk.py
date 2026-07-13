"""Portfolio Risk — concentration and risk mix (Phase 5)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from app.utils.db import db_available

st.set_page_config(page_title="Portfolio Risk", layout="wide")

st.title("Portfolio Risk")
st.caption("Exposure and concentration by country, industry, and customer.")

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
        "Database detected. Portfolio risk charts and concentration panels "
        "will be wired in Phase 5."
    )
