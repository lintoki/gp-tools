try:
    import backtrader as bt
except ImportError:  # pragma: no cover - import is checked by BacktestEngine
    bt = None


BASE_PARAMS = (
    ("symbol", ""),
    ("stake_pct", 0.9),
    ("lot_size", 100),
    ("max_hold_days", 1),
    ("stop_loss_pct", 3.0),
    ("take_profit_pct", 6.0),
)


class TailBaseStrategy(bt.Strategy if bt else object):
    params = BASE_PARAMS

    def __init__(self):
        self.order = None
        self.entry_bar = None
        self.entry_price = None
        self.entry_reason = ""
        self.entry_date = None
        self.entry_size = 0
        self.completed_trades = []
        self.equity_curve = []

    def next(self):
        self.equity_curve.append(
            {
                "date": self.data.datetime.date(0).isoformat(),
                "symbol": self.p.symbol,
                "equity": round(self.broker.getvalue(), 2),
            }
        )
        if self.order:
            return

        if self.position:
            hold_days = len(self) - self.entry_bar
            pnl_pct = (self.data.close[0] / self.entry_price - 1) * 100
            if pnl_pct <= -self.p.stop_loss_pct:
                self.entry_reason = f"{self.entry_reason}; 跌破止损线"
                self.order = self.close()
            elif pnl_pct >= self.p.take_profit_pct:
                self.entry_reason = f"{self.entry_reason}; 达到止盈线"
                self.order = self.close()
            elif hold_days >= self.p.max_hold_days:
                self.entry_reason = f"{self.entry_reason}; 隔夜策略到期"
                self.order = self.close()
            return

        signal, reason = self.should_enter()
        if signal:
            cash = self.broker.getcash() * self.p.stake_pct
            size = int(cash / max(self.data.close[0], 0.01) / self.p.lot_size) * self.p.lot_size
            if size > 0:
                self.entry_reason = reason
                self.order = self.buy(size=size)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            executed_date = bt.num2date(order.executed.dt).date().isoformat()
            if order.isbuy():
                self.entry_bar = max(0, len(self) - 1)
                self.entry_price = float(order.executed.price)
                self.entry_date = executed_date
                self.entry_size = int(order.executed.size)
            elif order.issell() and self.entry_price:
                exit_price = float(order.executed.price)
                pnl = (exit_price - self.entry_price) * self.entry_size - float(order.executed.comm)
                return_pct = (exit_price / self.entry_price - 1) * 100
                hold_days = max(1, max(0, len(self) - 1) - self.entry_bar)
                self.completed_trades.append(
                    {
                        "symbol": self.p.symbol,
                        "entry_date": self.entry_date,
                        "entry_price": round(self.entry_price, 3),
                        "exit_date": executed_date,
                        "exit_price": round(exit_price, 3),
                        "shares": self.entry_size,
                        "pnl": round(pnl, 2),
                        "return_pct": round(return_pct, 2),
                        "hold_days": hold_days,
                        "reason": self.entry_reason,
                    }
                )
                self.entry_bar = None
                self.entry_price = None
                self.entry_date = None
                self.entry_size = 0
        self.order = None

    def should_enter(self):
        raise NotImplementedError


def between(value, low, high):
    return low <= float(value) <= high
