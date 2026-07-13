"""Structured logging setup driven by application.log_level."""

from __future__ import annotations

import logging
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_CONFIGURED = False


def setup_logging(level: LogLevel | str = "INFO", *, force: bool = False) -> None:
    """Configure root logging once for the process.

    Safe to call multiple times; subsequent calls are no-ops unless ``force``.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    numeric_level = getattr(logging, str(level).upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (call ``setup_logging`` first in entrypoints)."""
    return logging.getLogger(name)
