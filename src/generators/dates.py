"""Generate the calendar date dimension for the synthetic pipeline."""

from __future__ import annotations

from calendar import month_name, monthrange
from datetime import date, timedelta

import pandas as pd

from src.config import ProjectConfig

# Fixed as-of anchor so dim_date is reproducible across machines and calendar days.
# Later fact generators should use the same window (step 05+).
DEFAULT_AS_OF_DATE = date(2026, 6, 30)

DIM_DATE_COLUMNS = (
    "date_key",
    "full_date",
    "year",
    "month",
    "month_name",
    "quarter",
    "is_month_end",
)


def history_window_bounds(
    history_months: int,
    *,
    as_of: date | None = None,
) -> tuple[date, date]:
    """Return inclusive ``(start, end)`` dates for ``history_months`` ending on ``as_of``.

    The window is ``history_months`` calendar months long: from the day after
    ``as_of - history_months`` through ``as_of`` inclusive.
    """
    if history_months < 1:
        raise ValueError(f"history_months must be >= 1, got {history_months}")

    end = as_of if as_of is not None else DEFAULT_AS_OF_DATE
    start_ts = pd.Timestamp(end) - pd.DateOffset(months=history_months) + pd.Timedelta(days=1)
    start = start_ts.date()
    return start, end


def _date_key(day: date) -> int:
    return day.year * 10_000 + day.month * 100 + day.day


def _is_month_end(day: date) -> bool:
    return day.day == monthrange(day.year, day.month)[1]


def generate_dim_date(
    config: ProjectConfig,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build ``dim_date`` covering the pipeline history window.

    Rows are contiguous calendar days with unique ``date_key`` values
    (``YYYYMMDD``). The end of the window defaults to ``DEFAULT_AS_OF_DATE``.
    """
    start, end = history_window_bounds(config.pipeline.history_months, as_of=as_of)

    rows: list[dict[str, object]] = []
    current = start
    one_day = timedelta(days=1)
    while current <= end:
        rows.append(
            {
                "date_key": _date_key(current),
                "full_date": current,
                "year": current.year,
                "month": current.month,
                "month_name": month_name[current.month],
                "quarter": (current.month - 1) // 3 + 1,
                "is_month_end": _is_month_end(current),
            }
        )
        current += one_day

    return pd.DataFrame(rows, columns=list(DIM_DATE_COLUMNS))
