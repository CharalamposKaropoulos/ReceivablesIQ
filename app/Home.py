"""Landing page — Credit Risk & Receivables Dashboard."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

# Streamlit adds ``app/`` to sys.path; ensure the repo root is importable too.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from app.utils.config import get_config
from app.utils.db import db_available, get_cached_connection
from src.logging_setup import setup_logging

DEMO_DISCLAIMER = (
    "This application uses a fictional dataset and a demonstration risk "
    "methodology. It is not a production credit-rating model, regulatory "
    "model, or substitute for professional underwriting judgement."
)

PAGE_GUIDE = [
    (
        "Executive Overview",
        "Portfolio KPIs, exposure trends, risk mix, concentration, and "
        "rule-based executive commentary.",
    ),
    (
        "Collections Priorities",
        "Collections worklist with priority scores, recommended actions, "
        "and score explainability.",
    ),
    (
        "Portfolio Risk",
        "Exposure and concentration by country, industry, and customer, "
        "plus ageing and utilisation views.",
    ),
    (
        "Customer Details",
        "Single-customer drill-down across invoices, payments, risk history, "
        "credit decisions, and claims.",
    ),
    (
        "Data Quality",
        "Validation results, failure trends, refresh status, and stale-data "
        "monitoring.",
    ),
]


def _format_currency(value: float, currency: str = "GBP") -> str:
    symbol = "£" if currency.upper() == "GBP" else f"{currency} "
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{symbol}{value / 1_000_000:,.1f}M"
    if abs_value >= 1_000:
        return f"{symbol}{value / 1_000:,.0f}K"
    return f"{symbol}{value:,.0f}"


def _portfolio_summary(conn) -> dict[str, float | int | str | None]:
    """Best-effort portfolio summary when analytical tables exist."""
    summary: dict[str, float | int | str | None] = {
        "customers": None,
        "invoices": None,
        "exposure": None,
        "reporting_date": None,
        "refresh_status": "unknown",
    }

    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
    except Exception:
        logging.getLogger(__name__).exception("Failed to list DuckDB tables")
        summary["refresh_status"] = "error"
        return summary

    if "dim_customer" in tables:
        try:
            summary["customers"] = int(
                conn.execute("SELECT COUNT(*) FROM dim_customer").fetchone()[0]
            )
        except Exception:
            logging.getLogger(__name__).exception("Failed to count customers")

    if "fact_invoice" in tables:
        try:
            summary["invoices"] = int(
                conn.execute("SELECT COUNT(*) FROM fact_invoice").fetchone()[0]
            )
        except Exception:
            logging.getLogger(__name__).exception("Failed to count invoices")

    exposure_queries = (
        (
            "executive_metrics",
            "SELECT total_exposure, reporting_date FROM executive_metrics "
            "ORDER BY reporting_date DESC LIMIT 1",
        ),
        (
            "customer_snapshot",
            "SELECT SUM(outstanding_amount), MAX(as_of_date) FROM customer_snapshot",
        ),
        (
            "fact_invoice",
            "SELECT SUM(outstanding_amount), MAX(invoice_date) FROM fact_invoice "
            "WHERE status IN ('open', 'overdue', 'partial')",
        ),
    )
    for table_name, sql in exposure_queries:
        if table_name not in tables:
            continue
        try:
            row = conn.execute(sql).fetchone()
            if row and row[0] is not None:
                summary["exposure"] = float(row[0])
                if len(row) > 1 and row[1] is not None:
                    summary["reporting_date"] = str(row[1])
                break
        except Exception:
            logging.getLogger(__name__).debug(
                "Portfolio exposure query skipped or failed: %s", sql, exc_info=True
            )

    if "pipeline_runs" in tables:
        try:
            row = conn.execute(
                "SELECT status, finished_at FROM pipeline_runs "
                "ORDER BY finished_at DESC NULLS LAST LIMIT 1"
            ).fetchone()
            if row:
                summary["refresh_status"] = str(row[0] or "unknown")
                if row[1] is not None and summary["reporting_date"] is None:
                    summary["reporting_date"] = str(row[1])
        except Exception:
            logging.getLogger(__name__).debug(
                "pipeline_runs lookup failed", exc_info=True
            )

    if summary["customers"] is not None or summary["exposure"] is not None:
        if summary["refresh_status"] == "unknown":
            summary["refresh_status"] = "ready"

    return summary


def main() -> None:
    try:
        config = get_config()
    except (FileNotFoundError, ValueError) as exc:
        st.set_page_config(page_title="Credit Risk Dashboard", layout="wide")
        st.error(f"Invalid or missing configuration: {exc}")
        return

    setup_logging(config.application.log_level)
    logger = logging.getLogger(__name__)

    st.set_page_config(
        page_title=config.dashboard.title,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title(config.dashboard.title)
    st.caption(
        "Open-source Streamlit demo — synthetic data and a demonstration risk methodology."
    )

    if config.dashboard.show_demo_disclaimer:
        st.warning(DEMO_DISCLAIMER)

    st.markdown(
        """
### Business scenario
Finance and credit teams need a single view of receivables exposure, overdue risk,
collections priorities, and data quality — without proprietary BI tooling. This
dashboard walks that story end-to-end on a fully synthetic portfolio.

### Dashboard objectives
- Surface portfolio exposure, overdue trends, and concentration risk
- Prioritise collections work with transparent scoring and recommended actions
- Support customer-level drill-down across invoices, payments, and claims
- Monitor validation health and data freshness after each pipeline run
"""
    )

    st.subheader("Data status")
    if not db_available():
        st.error(
            "No analytical database found yet.\n\n"
            "Run the data pipeline first, then refresh this page:\n\n"
            "```bash\n"
            "python -m src.run_pipeline --small\n"
            "```"
        )
        st.info(
            f"Expected database path: `{config.database.path}` "
            f"(environment: {config.application.environment})."
        )
        logger.info("Home page loaded without database at %s", config.database.path)
    else:
        conn = get_cached_connection()
        if conn is None:
            st.error(
                "Database file exists but could not be opened. "
                "Check permissions and re-run the pipeline if needed."
            )
        else:
            summary = _portfolio_summary(conn)
            reporting = summary.get("reporting_date") or datetime.now().strftime("%Y-%m-%d")
            status = str(summary.get("refresh_status") or "ready")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Reporting date", str(reporting)[:10])
            c2.metric("Refresh status", status.replace("_", " ").title())
            customers = summary.get("customers")
            c3.metric(
                "Customers",
                f"{customers:,}" if isinstance(customers, int) else "—",
            )
            invoices = summary.get("invoices")
            c4.metric(
                "Invoices",
                f"{invoices:,}" if isinstance(invoices, int) else "—",
            )

            exposure = summary.get("exposure")
            st.metric(
                "Total portfolio exposure",
                (
                    _format_currency(float(exposure), config.dashboard.default_currency)
                    if exposure is not None
                    else "Available after pipeline tables load"
                ),
            )
            st.success(
                f"Analytical database detected at `{config.database.path}`. "
                "Use the sidebar to open dashboard pages."
            )
            logger.info("Home page loaded with database at %s", config.database.path)

    st.subheader("Page guide")
    st.markdown("Use the **sidebar** to navigate. Pages will populate once the pipeline has run.")
    for name, blurb in PAGE_GUIDE:
        st.markdown(f"**{name}** — {blurb}")

    st.caption(f"Config: `{Path('config/project_config.yaml').as_posix()}`")


if __name__ == "__main__":
    main()
else:
    # Streamlit executes the script as a module; still run main on import.
    main()
