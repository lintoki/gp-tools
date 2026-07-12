from datetime import date

import pandas as pd

from a_share_research.backtest.engine import BacktestEngine
from a_share_research.backtest.models import BacktestConfig, Order, OrderSide


def test_order_after_as_of_is_ignored() -> None:
    config = BacktestConfig(initial_cash=10_000, slippage_bps=0)
    bars = pd.DataFrame(
        [
            {
                "instrument_id": "SH600000",
                "trade_date": "2026-07-10",
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 10,
                "suspended": False,
                "limit_up_locked": False,
                "limit_down_locked": False,
            },
            {
                "instrument_id": "SH600000",
                "trade_date": "2026-07-11",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "suspended": False,
                "limit_up_locked": False,
                "limit_down_locked": False,
            },
        ]
    )
    orders = [
        Order("SH600000", date(2026, 7, 9), OrderSide.BUY, 100),
        Order("SH600000", date(2026, 7, 11), OrderSide.SELL, 100),
    ]
    result = BacktestEngine(config).run(orders, bars, as_of=date(2026, 7, 10))
    assert result.positions["SH600000"] == 100
    assert result.metrics.trade_count == 1
