from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Order:
    instrument_id: str
    trade_date: date
    side: OrderSide
    quantity: int


class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_cash: float = Field(gt=0)
    lot_size: int = Field(default=100, ge=1)
    commission_rate: float = Field(default=0.0003, ge=0)
    minimum_commission: float = Field(default=5.0, ge=0)
    sell_stamp_tax_rate: float = Field(default=0.0005, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    signal_time: Literal["close"] = "close"
    execution_time: Literal["next_open"] = "next_open"
    t_plus_one: bool = True


class MarketBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    trade_date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    suspended: bool
    limit_up_locked: bool
    limit_down_locked: bool


class ExecutionQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    order: Order
    quantity: int = 0
    price: float | None = None
    commission: float = 0.0
    stamp_tax: float = 0.0
    rejection_code: str | None = None

    @property
    def gross_value(self) -> float:
        return float(self.quantity * (self.price or 0.0))


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    trade_date: date
    side: OrderSide
    quantity: int
    price: float
    commission: float
    stamp_tax: float
    realized_pnl: float | None = None


class Rejection(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    trade_date: date
    side: OrderSide
    code: str
    message: str


class EquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_date: date
    equity: float


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    turnover: float = 0.0
    trade_count: int = 0
    excess_return: float = 0.0


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    cash: float
    positions: dict[str, int]
    fills: tuple[Fill, ...]
    rejections: tuple[Rejection, ...]
    equity_curve: tuple[EquityPoint, ...]
    metrics: BacktestMetrics
