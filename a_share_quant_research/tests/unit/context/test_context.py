from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from a_share_research.context.market import ContextDataIncomplete, ContextEngine
from a_share_research.context.models import ContextSnapshot, ContextStatus

AS_OF = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def snapshot(*, drop_series: str | None = None, include_future: bool = False) -> ContextSnapshot:
    dates = pd.bdate_range(end="2026-07-10", periods=60, tz="UTC")
    series = []
    payloads = {
        "SP500": np.linspace(5500.0, 6250.0, 60),
        "VIXCLS": np.linspace(25.0, 15.0, 60),
        "DGS10": np.linspace(4.5, 4.0, 60),
        "BAMLH0A0HYM2": np.linspace(4.0, 3.0, 60),
    }
    for series_id, values in payloads.items():
        if series_id == drop_series:
            continue
        series.extend(
            {
                "series_id": series_id,
                "effective_at": day,
                "available_at": day + timedelta(hours=12),
                "value": float(value),
            }
            for day, value in zip(dates, values, strict=True)
        )
    if include_future:
        series.append(
            {
                "series_id": "SP500",
                "effective_at": AS_OF + timedelta(days=1),
                "available_at": AS_OF + timedelta(days=1),
                "value": 1.0,
            }
        )
    return ContextSnapshot(
        market_series=pd.DataFrame(series),
        industry_evidence=pd.DataFrame(
            [
                {
                    "industry": "AI基础设施",
                    "event_time": AS_OF - timedelta(days=2),
                    "published_at": AS_OF - timedelta(days=1),
                    "verified": True,
                    "evidence_id": "sec-filing-1",
                    "direction": "POSITIVE",
                },
                {
                    "industry": "未验证行业",
                    "event_time": AS_OF - timedelta(days=1),
                    "published_at": AS_OF - timedelta(hours=12),
                    "verified": False,
                    "evidence_id": "rumor-1",
                    "direction": "POSITIVE",
                },
            ]
        ),
        cot=pd.DataFrame(
            [
                {
                    "report_date": "2026-06-30",
                    "available_at": "2026-07-03T19:30:00Z",
                    "contract_market_name": "S&P 500",
                    "long": 100,
                    "short": 80,
                },
                {
                    "report_date": "2026-07-07",
                    "available_at": "2026-07-10T19:30:00Z",
                    "contract_market_name": "S&P 500",
                    "long": 120,
                    "short": 90,
                },
            ]
        ),
    )


def test_weekly_cot_is_fresh_inside_release_window() -> None:
    result = ContextEngine().compute(snapshot(), AS_OF)
    assert result.status == ContextStatus.READY
    assert result.market.index_trend == "UP"
    assert result.market.volatility_direction == "DOWN"
    assert result.futures[0].net_position_change == 10.0
    assert tuple(item.industry for item in result.industries) == ("AI基础设施",)


def test_missing_required_us_series_blocks_context() -> None:
    with pytest.raises(ContextDataIncomplete, match="SP500"):
        ContextEngine().compute(snapshot(drop_series="SP500"), AS_OF)


def test_future_us_observation_does_not_change_context() -> None:
    engine = ContextEngine()
    assert engine.compute(snapshot(include_future=False), AS_OF) == engine.compute(
        snapshot(include_future=True), AS_OF
    )


def test_context_model_has_no_trade_instruction_fields() -> None:
    payload = ContextEngine().compute(snapshot(), AS_OF).model_dump()
    serialized_keys = str(payload).lower()
    assert "order" not in serialized_keys
    assert "target_position" not in serialized_keys


def test_unreleased_cot_report_is_not_visible() -> None:
    data = snapshot()
    data.cot.loc[data.cot.index[-1], "available_at"] = (AS_OF + timedelta(days=1)).isoformat()
    with pytest.raises(ContextDataIncomplete, match="requires two reports"):
        ContextEngine().compute(data, AS_OF)
