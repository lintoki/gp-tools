from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, ConfigDict


class ContextStatus(StrEnum):
    READY = "READY"


@dataclass(frozen=True)
class ContextSnapshot:
    market_series: pd.DataFrame
    industry_evidence: pd.DataFrame
    cot: pd.DataFrame


class MarketContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    index_trend: str
    volatility_direction: str
    yield_direction: str
    credit_direction: str
    latest_observations: dict[str, datetime]


class IndustryDevelopment(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry: str
    direction: str
    evidence_ids: tuple[str, ...]
    latest_event_time: datetime


class FuturesRisk(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_market_name: str
    report_date: datetime
    net_position: float
    net_position_change: float


class GlobalContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ContextStatus
    as_of: datetime
    market: MarketContext
    industries: tuple[IndustryDevelopment, ...]
    futures: tuple[FuturesRisk, ...]
