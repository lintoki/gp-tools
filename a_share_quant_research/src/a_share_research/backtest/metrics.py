from __future__ import annotations

import math

import pandas as pd

from a_share_research.backtest.models import BacktestMetrics, EquityPoint, Fill


def calculate_metrics(
    equity_curve: list[EquityPoint],
    fills: list[Fill],
    initial_cash: float,
    benchmark_return: float = 0.0,
) -> BacktestMetrics:
    if not equity_curve:
        return BacktestMetrics()
    equity = pd.Series([point.equity for point in equity_curve], dtype=float)
    returns = equity.pct_change().dropna()
    days = max((equity_curve[-1].trade_date - equity_curve[0].trade_date).days, 1)
    annualized = (equity.iloc[-1] / initial_cash) ** (365.25 / days) - 1 if equity.iloc[-1] > 0 else -1.0
    drawdown = equity / equity.cummax() - 1
    sharpe = 0.0
    if not returns.empty and float(returns.std(ddof=0)) > 0:
        sharpe = float(returns.mean() / returns.std(ddof=0) * math.sqrt(252))
    realized = [fill.realized_pnl for fill in fills if fill.realized_pnl is not None]
    wins = [value for value in realized if value > 0]
    losses = [abs(value) for value in realized if value < 0]
    win_rate = len(wins) / len(realized) if realized else 0.0
    profit_loss = (
        (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        if wins and losses
        else (float("inf") if wins else 0.0)
    )
    gross_turnover = sum(fill.quantity * fill.price for fill in fills)
    return BacktestMetrics(
        annualized_return=float(annualized),
        max_drawdown=float(drawdown.min()),
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        profit_loss_ratio=profit_loss,
        turnover=float(gross_turnover / initial_cash),
        trade_count=len(fills),
        excess_return=float(equity.iloc[-1] / initial_cash - 1 - benchmark_return),
    )
