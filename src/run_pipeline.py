"""Pipeline CLI entrypoint — config, logging, and orchestration stub.

Generation, defect injection, and DuckDB load are wired in later Phase 2 steps.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG_PATH, ProjectConfig, load_config
from src.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the synthetic data pipeline."""
    parser = argparse.ArgumentParser(
        prog="python -m src.run_pipeline",
        description=(
            "Generate synthetic credit-risk data, optionally inject data-quality "
            "defects, and load analytical tables into DuckDB."
        ),
    )
    parser.add_argument(
        "--small",
        action="store_true",
        help="Use pipeline.small_num_customers instead of num_customers",
    )
    parser.add_argument(
        "--skip-defects",
        action="store_true",
        help="Skip data-quality defect injection even if enabled in config",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        metavar="PATH",
        help=f"Path to project_config.yaml (default: {DEFAULT_CONFIG_PATH})",
    )
    return parser.parse_args(argv)


def resolve_customer_count(config: ProjectConfig, *, small: bool) -> int:
    """Return the customer count for this run from config."""
    if small:
        return config.pipeline.small_num_customers
    return config.pipeline.num_customers


def resolve_inject_defects(config: ProjectConfig, *, skip_defects: bool) -> bool:
    """Return whether defect injection should run for this invocation."""
    if skip_defects:
        return False
    return config.pipeline.inject_data_quality_defects


def run(argv: list[str] | None = None) -> int:
    """Load config, configure logging, and run the pipeline (stub until step 11)."""
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        # Logging may not be configured yet; print a clear user-facing message.
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.application.log_level)

    customer_count = resolve_customer_count(config, small=args.small)
    inject_defects = resolve_inject_defects(config, skip_defects=args.skip_defects)

    logger.info(
        "Pipeline starting (seed=%s, customers=%s, history_months=%s, "
        "inject_defects=%s, database=%s)",
        config.pipeline.random_seed,
        customer_count,
        config.pipeline.history_months,
        inject_defects,
        config.database_path,
    )
    logger.info(
        "Synthetic generation is not implemented yet "
        "(Phase 2 steps 03–11). Config and logging OK."
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
