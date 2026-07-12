from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class FactorStatus(StrEnum):
    READY = "READY"
    MISSING = "MISSING"


class FactorResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    factor_name: str
    raw_value: float | None
    z_value: float | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    as_of: datetime
    dependencies: tuple[str, ...]
    status: FactorStatus
    reason: str | None = None


@dataclass(frozen=True)
class FactorSnapshot:
    bars: pd.DataFrame
    benchmark: pd.DataFrame
    financials: pd.DataFrame
    valuations: pd.DataFrame
    industry: pd.DataFrame
    events: pd.DataFrame
