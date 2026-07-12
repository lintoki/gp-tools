from datetime import date

import pandas as pd
import pytest

from a_share_research.backtest.engine import BacktestEngine
from a_share_research.backtest.models import BacktestConfig, Order, OrderSide

CONFIG = BacktestConfig(
    initial_cash=100_000,
    lot_size=100,
    commission_rate=0.0003,
    minimum_commission=5.0,
    sell_stamp_tax_rate=0.0005,
    slippage_bps=0.0,
)


def market(include_future: bool = False) -> pd.DataFrame:
    rows = [
        {
            "instrument_id": "SH600000",
            "trade_date": "2026-07-10",
            "open": 10,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "suspended": False,
            "limit_up_locked": False,
            "limit_down_locked": False,
        },
        {
            "instrument_id": "SH600000",
            "trade_date": "2026-07-11",
            "open": 10.3,
            "high": 10.8,
            "low": 10.1,
            "close": 10.5,
            "suspended": False,
            "limit_up_locked": False,
            "limit_down_locked": False,
        },
        {
            "instrument_id": "SH600000",
            "trade_date": "2026-07-12",
            "open": 10.6,
            "high": 10.9,
            "low": 10.4,
            "close": 10.8,
            "suspended": False,
            "limit_up_locked": False,
            "limit_down_locked": False,
        },
    ]
    if include_future:
        rows.append(
            {
                "instrument_id": "SH600000",
                "trade_date": "2026-07-13",
                "open": 9999,
                "high": 9999,
                "low": 9999,
                "close": 9999,
                "suspended": False,
                "limit_up_locked": False,
                "limit_down_locked": False,
            }
        )
    return pd.DataFrame(rows)


def test_t_plus_one_prevents_same_day_sale() -> None:
    orders = [
        Order("SH600000", date(2026, 7, 10), OrderSide.BUY, 100),
        Order("SH600000", date(2026, 7, 10), OrderSide.SELL, 100),
    ]
    result = BacktestEngine(CONFIG).run(orders, market(), as_of=date(2026, 7, 11))
    assert result.rejections[-1].code == "T_PLUS_ONE"
    assert result.positions["SH600000"] == 100
    assert result.fills[0].trade_date == date(2026, 7, 11)


def test_future_bars_do_not_change_past_result() -> None:
    orders = [Order("SH600000", date(2026, 7, 10), OrderSide.BUY, 100)]
    engine = BacktestEngine(CONFIG)
    before = engine.run(orders, market(False), as_of=date(2026, 7, 11))
    after = engine.run(orders, market(True), as_of=date(2026, 7, 11))
    assert before == after


def test_next_day_sale_realizes_trade_and_metrics() -> None:
    orders = [
        Order("SH600000", date(2026, 7, 10), OrderSide.BUY, 100),
        Order("SH600000", date(2026, 7, 11), OrderSide.SELL, 100),
    ]
    result = BacktestEngine(CONFIG).run(orders, market(), as_of=date(2026, 7, 12))
    assert result.metrics.trade_count == 2
    assert result.positions.get("SH600000", 0) == 0
    assert result.metrics.win_rate == 1.0


def test_missing_trade_flags_are_rejected_instead_of_defaulting_to_tradeable() -> None:
    bars = market().drop(columns=["suspended"])
    with pytest.raises(ValueError, match="required market columns"):
        BacktestEngine(CONFIG).run([], bars, as_of=date(2026, 7, 11))


def test_held_position_uses_last_close_when_bar_is_missing() -> None:
    bars = market()
    second = bars.iloc[1].copy()
    second["instrument_id"] = "SH600001"
    bars = pd.concat([bars.iloc[[0]], pd.DataFrame([second])], ignore_index=True)
    orders = [Order("SH600000", date(2026, 7, 9), OrderSide.BUY, 100)]
    result = BacktestEngine(CONFIG).run(orders, bars, as_of=date(2026, 7, 11))
    assert result.equity_curve[-1].equity > result.cash


def test_historical_universe_excludes_ineligible_execution_day() -> None:
    orders = [Order("SH600000", date(2026, 7, 10), OrderSide.BUY, 100)]
    universe = pd.DataFrame([{"trade_date": "2026-07-11", "instrument_id": "SH600000", "eligible": False}])
    result = BacktestEngine(CONFIG).run(
        orders,
        market(),
        as_of=date(2026, 7, 11),
        historical_universe=universe,
    )
    assert result.rejections[-1].code == "UNIVERSE_EXCLUDED"
    assert result.metrics.trade_count == 0
