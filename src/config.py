"""Load and validate project configuration from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

DEFAULT_CONFIG_PATH = Path("config/project_config.yaml")


class DashboardConfig(BaseModel):
    title: str
    default_currency: str = "GBP"
    default_page_size: int = Field(default=50, ge=1)
    maximum_table_rows: int = Field(default=5000, ge=1)
    enable_excel_exports: bool = True
    enable_chart_exports: bool = True
    show_demo_disclaimer: bool = True
    cache_ttl_seconds: int = Field(default=3600, ge=0)


class DatabaseConfig(BaseModel):
    engine: Literal["duckdb"] = "duckdb"
    path: str

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("database.path must not be blank")
        return value


class ApplicationConfig(BaseModel):
    environment: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    show_debug_information: bool = False


class PipelineConfig(BaseModel):
    random_seed: int = 42
    num_customers: int = Field(default=2000, ge=1)
    small_num_customers: int = Field(default=100, ge=1)
    history_months: int = Field(default=24, ge=1)
    inject_data_quality_defects: bool = True
    defect_rate: float = Field(default=0.03, ge=0.0, le=1.0)


class ProjectConfig(BaseModel):
    dashboard: DashboardConfig
    database: DatabaseConfig
    application: ApplicationConfig
    pipeline: PipelineConfig

    @property
    def database_path(self) -> Path:
        return Path(self.database.path)


def load_config(path: Path | str | None = None) -> ProjectConfig:
    """Load and validate ``project_config.yaml``.

    Raises:
        FileNotFoundError: if the config file does not exist.
        ValueError: if YAML is invalid or fails Pydantic validation.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration root must be a mapping: {config_path}")

    try:
        return ProjectConfig.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Configuration validation failed for {config_path}: {exc}") from exc
