"""Load and validate project configuration from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path("config/project_config.yaml")

_WEIGHT_TOLERANCE = 1e-6

# Locked BRD §10 recommended-action vocabulary (demonstration model).
RECOMMENDED_ACTIONS: tuple[str, ...] = (
    "immediate escalation",
    "senior collections review",
    "contact within 24 hours",
    "standard collection contact",
    "monitor",
    "resolve dispute",
    "consider credit hold",
    "prepare insurance claim",
)


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


class RiskWeightsConfig(BaseModel):
    ageing: float = Field(ge=0.0, le=1.0)
    utilisation: float = Field(ge=0.0, le=1.0)
    payment: float = Field(ge=0.0, le=1.0)
    overdue_ratio: float = Field(ge=0.0, le=1.0)
    dispute: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> RiskWeightsConfig:
        total = (
            self.ageing
            + self.utilisation
            + self.payment
            + self.overdue_ratio
            + self.dispute
        )
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                f"risk_model.weights must sum to 1.0 (within {_WEIGHT_TOLERANCE}), got {total}"
            )
        return self


class ScoreBandThresholds(BaseModel):
    """Upper bounds for low / medium / high bands; critical is at or above ``critical``."""

    medium: float = Field(ge=0.0, le=100.0)
    high: float = Field(ge=0.0, le=100.0)
    critical: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def thresholds_must_be_strictly_increasing(self) -> ScoreBandThresholds:
        if not (0.0 <= self.medium < self.high < self.critical <= 100.0):
            raise ValueError(
                "category/priority thresholds must satisfy "
                "0 <= medium < high < critical <= 100 "
                f"(got medium={self.medium}, high={self.high}, critical={self.critical})"
            )
        return self


class RiskModelConfig(BaseModel):
    """Demonstration risk model weights and category bands (not a production model)."""

    weights: RiskWeightsConfig
    category_thresholds: ScoreBandThresholds


class CollectionsWeightsConfig(BaseModel):
    risk: float = Field(ge=0.0, le=1.0)
    overdue: float = Field(ge=0.0, le=1.0)
    dpd: float = Field(ge=0.0, le=1.0)
    dispute: float = Field(ge=0.0, le=1.0)
    limit_breach: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> CollectionsWeightsConfig:
        total = (
            self.risk + self.overdue + self.dpd + self.dispute + self.limit_breach
        )
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                "collections_model.weights must sum to 1.0 "
                f"(within {_WEIGHT_TOLERANCE}), got {total}"
            )
        return self


class CollectionsModelConfig(BaseModel):
    """Demonstration collections priority weights, bands, and allowed actions."""

    weights: CollectionsWeightsConfig
    priority_thresholds: ScoreBandThresholds
    recommended_actions: list[str]

    @field_validator("recommended_actions")
    @classmethod
    def actions_must_match_locked_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("collections_model.recommended_actions must not be empty")
        normalised = [action.strip() for action in value]
        if any(not action for action in normalised):
            raise ValueError(
                "collections_model.recommended_actions entries must not be blank"
            )
        locked = set(RECOMMENDED_ACTIONS)
        unknown = sorted(set(normalised) - locked)
        if unknown:
            raise ValueError(
                "collections_model.recommended_actions contains values outside the "
                f"locked BRD §10 list: {unknown}"
            )
        missing = sorted(locked - set(normalised))
        if missing:
            raise ValueError(
                "collections_model.recommended_actions is missing locked BRD §10 "
                f"actions: {missing}"
            )
        return normalised


class ProjectConfig(BaseModel):
    dashboard: DashboardConfig
    database: DatabaseConfig
    application: ApplicationConfig
    pipeline: PipelineConfig
    risk_model: RiskModelConfig
    collections_model: CollectionsModelConfig

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
