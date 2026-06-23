from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class StrategyConfig:
    min_change_pct: float = 3.0
    max_change_pct: float = 5.0
    limit_up_lookback_days: int = 20
    min_limit_up_count_20: int = 1
    max_limit_up_count_20: int = 3
    min_volume_ratio: float = 1.0
    min_turnover_pct: float = 5.0
    max_turnover_pct: float = 10.0
    min_total_market_value_yuan: float = 5_000_000_000
    max_total_market_value_yuan: float = 20_000_000_000
    limit_up_pct: float = 9.8
    min_above_avg_ratio: float = 0.8
    vwap_break_tolerance_pct: float = 0.5
    pullback_to_avg_tolerance_pct: float = 1.0
    tail_start: str = "14:30:00"


@dataclass(frozen=True)
class MarketSnapshot:
    code: str
    name: str
    latest_price: Optional[float]
    change_pct: Optional[float]
    volume_ratio: Optional[float]
    turnover_pct: Optional[float]
    total_market_value_yuan: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    open_price: Optional[float]
    prev_close: Optional[float]
    amount_yuan: Optional[float]


@dataclass(frozen=True)
class DailyBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    change_pct: float
    turnover_pct: Optional[float] = None
    volume: Optional[float] = None
    amount_yuan: Optional[float] = None


@dataclass(frozen=True)
class MinuteBar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    avg_price: Optional[float] = None


@dataclass(frozen=True)
class CandidateReport:
    code: str
    name: str
    passed: bool
    score: float
    entry_price: Optional[float]
    pass_reasons: List[str] = field(default_factory=list)
    fail_reasons: List[str] = field(default_factory=list)
    snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperTrade:
    trade_id: str
    code: str
    name: str
    entry_date: str
    entry_time: str
    entry_price: float
    shares: int
    status: str
    strategy: str
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewResult:
    trade: PaperTrade
    exit_date: str
    exit_time: str
    exit_price: float
    exit_reason: str
    return_pct: float
    profit_yuan: float
