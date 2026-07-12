from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    """Validated subset of project-wide settings used by core services."""

    model_config = ConfigDict(frozen=True)

    factor_weights: dict[str, float]
    required_factors: tuple[str, ...] = ()
    main_board_only: bool = True
    max_attempts: int = Field(ge=1, le=10)
    retry_delays_seconds: tuple[float, ...] = ()
    maximum_backup_sources: int = Field(ge=0, le=3)
    dataset_deadline_seconds: int = Field(ge=1, le=600)
    minimum_request_interval_seconds: float = Field(ge=0, le=60)
    lot_size: int = Field(ge=1)


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required configuration file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return payload


def load_settings(config_dir: Path) -> Settings:
    factors = _read_yaml(config_dir / "factors.yaml")
    universe = _read_yaml(config_dir / "universe.yaml")
    quality = _read_yaml(config_dir / "quality.yaml")
    providers = _read_yaml(config_dir / "providers.yaml")
    backtest = _read_yaml(config_dir / "backtest.yaml")

    weights = {str(name): float(value) for name, value in factors.get("weights", {}).items()}
    if not weights or abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("factor weights must sum to 1")

    return Settings(
        factor_weights=weights,
        required_factors=tuple(factors.get("required", ())),
        main_board_only=bool(universe.get("main_board_only", True)),
        max_attempts=int(quality["max_attempts"]),
        retry_delays_seconds=tuple(float(item) for item in quality.get("retry_delays_seconds", ())),
        maximum_backup_sources=int(quality.get("maximum_backup_sources", 1)),
        dataset_deadline_seconds=int(providers["dataset_deadline_seconds"]),
        minimum_request_interval_seconds=float(providers.get("minimum_request_interval_seconds", 0.2)),
        lot_size=int(backtest["lot_size"]),
    )
