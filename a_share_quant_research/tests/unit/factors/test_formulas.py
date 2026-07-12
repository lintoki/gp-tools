from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from a_share_research.factors.event import event_catalyst_factor
from a_share_research.factors.fundamental import fundamental_quality_factor, valuation_percentile_factor
from a_share_research.factors.industry import industry_prosperity_factor
from a_share_research.factors.technical import (
    relative_strength_factor,
    trend_factor,
    volatility_drawdown_factor,
    volume_turnover_factor,
)

AS_OF = datetime(2026, 7, 11, tzinfo=UTC)


def test_technical_factor_formulas_are_deterministic() -> None:
    close = pd.Series(np.linspace(10.0, 20.0, 60))
    benchmark = pd.Series(np.linspace(100.0, 110.0, 60))
    volume = pd.Series([100.0] * 20 + [1000.0])
    turnover = pd.Series(np.linspace(0.5, 2.5, 21))

    assert trend_factor(close) > 0
    assert relative_strength_factor(close, benchmark) > 0
    assert volume_turnover_factor(volume, turnover) == pytest.approx(0.5 * np.log(10) + 0.5)
    assert volatility_drawdown_factor(close) <= 0


def test_fundamental_uses_latest_disclosed_row_only() -> None:
    rows = pd.DataFrame(
        [
            {
                "available_at": AS_OF - timedelta(days=1),
                "revenue_yoy": 0.10,
                "net_profit_yoy": 0.20,
                "operating_cashflow": 120.0,
                "net_profit": 100.0,
            },
            {
                "available_at": AS_OF + timedelta(days=1),
                "revenue_yoy": 9.0,
                "net_profit_yoy": 9.0,
                "operating_cashflow": 900.0,
                "net_profit": 1.0,
            },
        ]
    )
    value = fundamental_quality_factor(rows, AS_OF)
    assert value == pytest.approx(0.35 * 0.10 + 0.35 * 0.20 + 0.30 * 1.20)


def test_negative_pe_makes_valuation_factor_missing() -> None:
    pe = pd.Series([-1.0] * 756)
    pb = pd.Series(np.linspace(1.0, 3.0, 756))
    assert valuation_percentile_factor(pe, pb) is None


def test_industry_and_event_formulas() -> None:
    assert industry_prosperity_factor(0.20, 0.50) == pytest.approx(0.32)
    assert event_catalyst_factor("A", True, 1, 0, days_old=0) == pytest.approx(1.0)
    assert event_catalyst_factor("C", True, 1, 0, days_old=0) == 0.0
    assert event_catalyst_factor("C", True, 2, 0.1, days_old=15) == pytest.approx(0.2)
    assert event_catalyst_factor("D", True, 10, 0, days_old=0) == 0.0
