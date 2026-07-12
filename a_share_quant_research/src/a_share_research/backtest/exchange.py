from __future__ import annotations

from a_share_research.backtest.models import (
    BacktestConfig,
    ExecutionQuote,
    MarketBar,
    Order,
    OrderSide,
)


class ExchangeSimulator:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def quote(self, order: Order, bar: MarketBar) -> ExecutionQuote:
        if bar.suspended:
            return ExecutionQuote(order=order, rejection_code="SUSPENDED")
        if order.side == OrderSide.BUY and bar.limit_up_locked:
            return ExecutionQuote(order=order, rejection_code="LIMIT_UP_LOCKED")
        if order.side == OrderSide.SELL and bar.limit_down_locked:
            return ExecutionQuote(order=order, rejection_code="LIMIT_DOWN_LOCKED")
        quantity = order.quantity // self.config.lot_size * self.config.lot_size
        if quantity <= 0:
            return ExecutionQuote(order=order, rejection_code="BELOW_LOT_SIZE")
        slip = self.config.slippage_bps / 10_000.0
        price = bar.open * (1 + slip if order.side == OrderSide.BUY else 1 - slip)
        gross = quantity * price
        commission = max(self.config.minimum_commission, gross * self.config.commission_rate)
        stamp_tax = gross * self.config.sell_stamp_tax_rate if order.side == OrderSide.SELL else 0.0
        return ExecutionQuote(
            order=order,
            quantity=quantity,
            price=price,
            commission=commission,
            stamp_tax=stamp_tax,
        )
