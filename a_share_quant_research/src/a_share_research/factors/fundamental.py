from __future__ import annotations

from datetime import datetime

import pandas as pd


def fundamental_quality_factor(rows: pd.DataFrame, as_of: datetime) -> float | None:
    if rows.empty:
        return None
    frame = rows.copy()
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    eligible = frame[frame["available_at"] <= pd.Timestamp(as_of)].sort_values("available_at")
    if eligible.empty:
        return None
    latest = eligible.iloc[-1]
    net_profit = float(latest["net_profit"])
    if abs(net_profit) < 1e-9:
        return None
    cash_quality = float(latest["operating_cashflow"]) / abs(net_profit)
    return 0.35 * float(latest["revenue_yoy"]) + 0.35 * float(latest["net_profit_yoy"]) + 0.30 * cash_quality


def valuation_percentile_factor(
    pe_ttm: pd.Series, pb: pd.Series, minimum_observations: int = 756
) -> float | None:
    pe = pd.to_numeric(pe_ttm, errors="coerce").dropna()
    pb_values = pd.to_numeric(pb, errors="coerce").dropna()
    if len(pe) < minimum_observations or len(pb_values) < minimum_observations:
        return None
    if float(pe.iloc[-1]) <= 0:
        return None
    pe_percentile = float((pe.iloc[-minimum_observations:] <= pe.iloc[-1]).mean())
    pb_percentile = float((pb_values.iloc[-minimum_observations:] <= pb_values.iloc[-1]).mean())
    return 1.0 - (pe_percentile + pb_percentile) / 2.0
