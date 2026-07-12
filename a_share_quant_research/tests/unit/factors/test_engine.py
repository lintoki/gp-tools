from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from a_share_research.factors.base import FactorSnapshot, FactorStatus
from a_share_research.factors.scoring import CandidateStatus, CompositeScorer, FactorEngine

AS_OF = datetime(2026, 7, 11, tzinfo=UTC)


def snapshot(include_future: bool = False) -> FactorSnapshot:
    dates = pd.bdate_range(end=AS_OF.date(), periods=800, tz="UTC")
    bars = pd.DataFrame(
        {
            "instrument_id": "SH600000",
            "effective_at": dates,
            "available_at": dates,
            "close": np.linspace(10.0, 20.0, len(dates)),
            "volume": np.linspace(1000.0, 1500.0, len(dates)),
            "turnover_rate": np.linspace(0.5, 2.0, len(dates)),
        }
    )
    benchmark = pd.DataFrame(
        {
            "effective_at": dates,
            "available_at": dates,
            "close": np.linspace(100.0, 120.0, len(dates)),
        }
    )
    valuations = pd.DataFrame(
        {
            "instrument_id": "SH600000",
            "effective_at": dates,
            "available_at": dates,
            "pe_ttm": np.linspace(8.0, 16.0, len(dates)),
            "pb": np.linspace(0.8, 1.6, len(dates)),
        }
    )
    if include_future:
        future = pd.Timestamp(AS_OF + timedelta(days=3))
        bars.loc[len(bars)] = ["SH600000", future, future, 9999.0, 999999.0, 99.0]
        valuations.loc[len(valuations)] = ["SH600000", future, future, 9999.0, 9999.0]
    return FactorSnapshot(
        bars=bars,
        benchmark=benchmark,
        financials=pd.DataFrame(
            [
                {
                    "instrument_id": "SH600000",
                    "available_at": AS_OF - timedelta(days=2),
                    "revenue_yoy": 0.10,
                    "net_profit_yoy": 0.15,
                    "operating_cashflow": 120.0,
                    "net_profit": 100.0,
                }
            ]
        ),
        valuations=valuations,
        industry=pd.DataFrame(
            [
                {
                    "instrument_id": "SH600000",
                    "effective_at": AS_OF - timedelta(days=1),
                    "available_at": AS_OF - timedelta(days=1),
                    "industry_relative_return_60d": 0.12,
                    "industry_fundamental_breadth": 0.60,
                }
            ]
        ),
        events=pd.DataFrame(
            [
                {
                    "instrument_id": "SH600000",
                    "event_time": AS_OF - timedelta(days=3),
                    "published_at": AS_OF - timedelta(days=2),
                    "grade": "A",
                    "verified": True,
                    "independent_sources": 1,
                    "contradiction_penalty": 0.0,
                }
            ]
        ),
    )


def test_factor_engine_computes_all_eight_factors() -> None:
    results = FactorEngine().compute(snapshot(), AS_OF)
    assert len(results) == 8
    assert {result.status for result in results} == {FactorStatus.READY}


def test_future_rows_do_not_change_past_factors() -> None:
    engine = FactorEngine()
    assert engine.compute(snapshot(False), AS_OF) == engine.compute(snapshot(True), AS_OF)


def test_missing_required_factor_excludes_candidate() -> None:
    results = list(FactorEngine().compute(snapshot(), AS_OF))
    results[-1] = results[-1].model_copy(
        update={"status": FactorStatus.MISSING, "raw_value": None, "score": None}
    )
    weights = {result.factor_name: 1 / 8 for result in results}
    candidate = CompositeScorer(tuple(weights)).score(results, weights)[0]
    assert candidate.status == CandidateStatus.EXCLUDED_MISSING_FACTOR


def test_unpublished_event_does_not_change_past_factor() -> None:
    baseline = snapshot()
    future = snapshot()
    future.events.loc[0, "grade"] = "A"
    future.events.loc[0, "published_at"] = AS_OF + timedelta(days=1)
    future.events.loc[0, "contradiction_penalty"] = 0.0
    baseline = replace(baseline, events=baseline.events.iloc[0:0].copy())
    engine = FactorEngine()
    baseline_event = next(
        item for item in engine.compute(baseline, AS_OF) if item.factor_name == "event_catalyst"
    )
    future_event = next(
        item for item in engine.compute(future, AS_OF) if item.factor_name == "event_catalyst"
    )
    assert future_event.raw_value == baseline_event.raw_value == 0.0
