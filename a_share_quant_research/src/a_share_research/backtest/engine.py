from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from a_share_research.backtest.exchange import ExchangeSimulator
from a_share_research.backtest.metrics import calculate_metrics
from a_share_research.backtest.models import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    Fill,
    MarketBar,
    Order,
    OrderSide,
    Rejection,
)


@dataclass
class _Lot:
    quantity: int
    purchase_date: date
    unit_cost: float


class BacktestEngine:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.exchange = ExchangeSimulator(config)

    def run(
        self,
        orders: list[Order] | tuple[Order, ...],
        bars: pd.DataFrame,
        *,
        as_of: date,
        benchmark_return: float = 0.0,
        historical_universe: pd.DataFrame | None = None,
    ) -> BacktestResult:
        market = self._prepare_market(bars, as_of)
        eligible_orders = [order for order in orders if order.trade_date <= as_of]
        cash = float(self.config.initial_cash)
        lots: dict[str, list[_Lot]] = {}
        fills: list[Fill] = []
        rejections: list[Rejection] = []
        curve: list[EquityPoint] = []
        last_close: dict[str, float] = {}
        trade_dates = [pd.Timestamp(value).date() for value in sorted(market["trade_date"].unique())]
        scheduled: dict[date, list[Order]] = {}
        eligible_pairs = self._prepare_historical_universe(historical_universe, as_of)
        for order in eligible_orders:
            execution_day = next((day for day in trade_dates if day > order.trade_date), None)
            if execution_day is None:
                rejections.append(self._reject(order, "NO_NEXT_OPEN"))
                continue
            scheduled.setdefault(execution_day, []).append(
                Order(order.instrument_id, execution_day, order.side, order.quantity)
            )

        for trade_date in sorted(market["trade_date"].unique()):
            day = pd.Timestamp(trade_date).date()
            day_market = market[market["trade_date"] == day]
            by_instrument = {
                str(row["instrument_id"]): MarketBar.model_validate(row.to_dict())
                for _, row in day_market.iterrows()
            }
            last_close.update({instrument: float(bar.close) for instrument, bar in by_instrument.items()})
            for order in scheduled.get(day, []):
                if eligible_pairs is not None and (day, order.instrument_id) not in eligible_pairs:
                    rejections.append(self._reject(order, "UNIVERSE_EXCLUDED"))
                    continue
                bar = by_instrument.get(order.instrument_id)
                if bar is None:
                    rejections.append(self._reject(order, "NO_MARKET_BAR"))
                    continue
                quote = self.exchange.quote(order, bar)
                if quote.rejection_code:
                    rejections.append(self._reject(order, quote.rejection_code))
                    continue
                if order.side == OrderSide.BUY:
                    total_cost = quote.gross_value + quote.commission
                    if total_cost > cash:
                        rejections.append(self._reject(order, "INSUFFICIENT_CASH"))
                        continue
                    cash -= total_cost
                    lots.setdefault(order.instrument_id, []).append(
                        _Lot(quote.quantity, day, total_cost / quote.quantity)
                    )
                    fills.append(self._fill(quote))
                else:
                    available = sum(
                        lot.quantity
                        for lot in lots.get(order.instrument_id, [])
                        if not self.config.t_plus_one or lot.purchase_date < day
                    )
                    total_position = sum(lot.quantity for lot in lots.get(order.instrument_id, []))
                    if available < quote.quantity:
                        code = "T_PLUS_ONE" if total_position >= quote.quantity else "INSUFFICIENT_POSITION"
                        rejections.append(self._reject(order, code))
                        continue
                    realized = self._consume_lots(lots[order.instrument_id], quote.quantity, day, quote)
                    cash += quote.gross_value - quote.commission - quote.stamp_tax
                    fills.append(self._fill(quote, realized))
            equity = cash + sum(
                sum(lot.quantity for lot in position_lots) * last_close[instrument]
                for instrument, position_lots in lots.items()
                if position_lots and instrument in last_close
            )
            curve.append(EquityPoint(trade_date=day, equity=equity))

        positions = {
            instrument: sum(lot.quantity for lot in position_lots)
            for instrument, position_lots in lots.items()
        }
        positions = {instrument: quantity for instrument, quantity in positions.items() if quantity}
        metrics = calculate_metrics(curve, fills, self.config.initial_cash, benchmark_return)
        return BacktestResult(
            cash=cash,
            positions=positions,
            fills=tuple(fills),
            rejections=tuple(rejections),
            equity_curve=tuple(curve),
            metrics=metrics,
        )

    @staticmethod
    def _prepare_market(bars: pd.DataFrame, as_of: date) -> pd.DataFrame:
        market = bars.copy()
        required = {
            "instrument_id",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "suspended",
            "limit_up_locked",
            "limit_down_locked",
        }
        missing = sorted(required - set(market.columns))
        if missing:
            raise ValueError(f"required market columns are missing: {missing}")
        market["trade_date"] = pd.to_datetime(market["trade_date"]).dt.date
        market = market[market["trade_date"] <= as_of].copy()
        return market.sort_values(["trade_date", "instrument_id"])

    @staticmethod
    def _prepare_historical_universe(frame: pd.DataFrame | None, as_of: date) -> set[tuple[date, str]] | None:
        if frame is None:
            return None
        required = {"trade_date", "instrument_id", "eligible"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"historical universe columns are missing: {missing}")
        prepared = frame.copy()
        prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
        prepared = prepared[(prepared["trade_date"] <= as_of) & prepared["eligible"].astype(bool)]
        return {(row.trade_date, str(row.instrument_id)) for row in prepared.itertuples(index=False)}

    def _consume_lots(self, lots: list[_Lot], quantity: int, day: date, quote) -> float:
        remaining = quantity
        cost = 0.0
        for lot in lots:
            if (self.config.t_plus_one and lot.purchase_date >= day) or remaining <= 0:
                continue
            consumed = min(lot.quantity, remaining)
            cost += consumed * lot.unit_cost
            lot.quantity -= consumed
            remaining -= consumed
        lots[:] = [lot for lot in lots if lot.quantity > 0]
        proceeds = quote.gross_value - quote.commission - quote.stamp_tax
        return proceeds - cost

    @staticmethod
    def _fill(quote, realized_pnl=None) -> Fill:
        return Fill(
            instrument_id=quote.order.instrument_id,
            trade_date=quote.order.trade_date,
            side=quote.order.side,
            quantity=quote.quantity,
            price=quote.price,
            commission=quote.commission,
            stamp_tax=quote.stamp_tax,
            realized_pnl=realized_pnl,
        )

    @staticmethod
    def _reject(order: Order, code: str) -> Rejection:
        return Rejection(
            instrument_id=order.instrument_id,
            trade_date=order.trade_date,
            side=order.side,
            code=code,
            message=code.replace("_", " ").lower(),
        )
