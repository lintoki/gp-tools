from datetime import date

import pytest

from a_share_research.backtest.exchange import ExchangeSimulator
from a_share_research.backtest.models import BacktestConfig, MarketBar, Order, OrderSide

CONFIG = BacktestConfig(
    initial_cash=100_000,
    lot_size=100,
    commission_rate=0.0003,
    minimum_commission=5.0,
    sell_stamp_tax_rate=0.0005,
    slippage_bps=5.0,
)


def bar(**updates) -> MarketBar:
    payload = {
        "instrument_id": "SH600000",
        "trade_date": date(2026, 7, 10),
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "suspended": False,
        "limit_up_locked": False,
        "limit_down_locked": False,
    }
    payload.update(updates)
    return MarketBar(**payload)


def test_locked_limit_up_buy_does_not_fill() -> None:
    order = Order("SH600000", date(2026, 7, 10), OrderSide.BUY, 100)
    result = ExchangeSimulator(CONFIG).quote(order, bar(limit_up_locked=True))
    assert result.rejection_code == "LIMIT_UP_LOCKED"


def test_buy_and_sell_costs_include_directional_slippage_and_stamp_tax() -> None:
    exchange = ExchangeSimulator(CONFIG)
    buy = exchange.quote(Order("SH600000", date(2026, 7, 10), OrderSide.BUY, 100), bar())
    sell = exchange.quote(Order("SH600000", date(2026, 7, 10), OrderSide.SELL, 100), bar())

    assert buy.price == pytest.approx(10.005)
    assert buy.commission == 5.0
    assert buy.stamp_tax == 0.0
    assert sell.price == pytest.approx(9.995)
    assert sell.commission == 5.0
    assert sell.stamp_tax == pytest.approx(999.5 * 0.0005)
