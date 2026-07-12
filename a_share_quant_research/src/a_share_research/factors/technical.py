from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _require(series: pd.Series, observations: int, name: str) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < observations:
        raise ValueError(f"{name} requires {observations} observations")
    return clean


def trend_factor(close: pd.Series) -> float:
    close = _require(close, 60, "trend")
    ma20 = float(close.iloc[-20:].mean())
    ma60 = float(close.iloc[-60:].mean())
    return 0.5 * (float(close.iloc[-1]) / ma20 - 1) + 0.5 * (ma20 / ma60 - 1)


def relative_strength_factor(close: pd.Series, benchmark_close: pd.Series) -> float:
    close = _require(close, 60, "relative strength")
    benchmark_close = _require(benchmark_close, 60, "benchmark relative strength")
    stock_return = float(close.iloc[-1] / close.iloc[-60] - 1)
    benchmark_return = float(benchmark_close.iloc[-1] / benchmark_close.iloc[-60] - 1)
    return stock_return - benchmark_return


def volume_turnover_factor(volume: pd.Series, turnover_rate: pd.Series) -> float:
    volume = _require(volume, 21, "volume turnover")
    turnover_rate = _require(turnover_rate, 21, "volume turnover")
    baseline = float(volume.iloc[-21:-1].mean())
    if baseline <= 0 or float(volume.iloc[-1]) <= 0:
        raise ValueError("volume baseline and current volume must be positive")
    turnover_percentile = float((turnover_rate.iloc[-21:] <= turnover_rate.iloc[-1]).mean())
    return 0.5 * math.log(float(volume.iloc[-1]) / baseline) + 0.5 * turnover_percentile


def volatility_drawdown_factor(close: pd.Series) -> float:
    close = _require(close, 60, "volatility drawdown")
    returns = close.pct_change().dropna()
    annualized_volatility = float(returns.iloc[-20:].std(ddof=0) * np.sqrt(252))
    recent = close.iloc[-60:]
    drawdown = recent / recent.cummax() - 1
    maximum_drawdown = abs(float(drawdown.min()))
    return -0.5 * annualized_volatility - 0.5 * maximum_drawdown
