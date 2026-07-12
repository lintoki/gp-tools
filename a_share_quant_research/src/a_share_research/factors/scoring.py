from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from a_share_research.factors.base import FactorResult, FactorSnapshot, FactorStatus
from a_share_research.factors.event import event_catalyst_factor
from a_share_research.factors.fundamental import fundamental_quality_factor, valuation_percentile_factor
from a_share_research.factors.industry import industry_prosperity_factor
from a_share_research.factors.technical import (
    relative_strength_factor,
    trend_factor,
    volatility_drawdown_factor,
    volume_turnover_factor,
)

FACTOR_DEPENDENCIES = {
    "trend": ("daily_bars.close",),
    "relative_strength": ("daily_bars.close", "benchmark.close"),
    "volume_turnover": ("daily_bars.volume", "daily_bars.turnover_rate"),
    "volatility_drawdown": ("daily_bars.close",),
    "fundamental_quality": ("financials.available_at", "financials.cashflow"),
    "valuation_percentile": ("valuations.pe_ttm", "valuations.pb"),
    "industry_prosperity": ("industry.relative_return", "industry.fundamental_breadth"),
    "event_catalyst": ("events.verification", "events.event_time"),
}


class CandidateStatus(StrEnum):
    READY = "READY"
    EXCLUDED_MISSING_FACTOR = "EXCLUDED_MISSING_FACTOR"


class CandidateScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    composite_score: float | None = Field(default=None, ge=0, le=100)
    status: CandidateStatus
    missing_factors: tuple[str, ...] = ()


class FactorEngine:
    def compute(self, snapshot: FactorSnapshot, as_of: datetime) -> list[FactorResult]:
        bars = self._filter_time(snapshot.bars, "effective_at", as_of)
        benchmark = self._filter_time(snapshot.benchmark, "effective_at", as_of).sort_values("effective_at")
        raw_results: list[FactorResult] = []
        for instrument in sorted(bars["instrument_id"].unique()):
            instrument_bars = bars[bars["instrument_id"] == instrument].sort_values("effective_at")
            values = self._raw_values(snapshot, instrument, instrument_bars, benchmark, as_of)
            for factor_name, value in values.items():
                raw_results.append(
                    FactorResult(
                        instrument_id=instrument,
                        factor_name=factor_name,
                        raw_value=value,
                        as_of=as_of,
                        dependencies=FACTOR_DEPENDENCIES[factor_name],
                        status=FactorStatus.READY if value is not None else FactorStatus.MISSING,
                        reason=None if value is not None else "required data is unavailable or invalid",
                    )
                )
        return self._standardize(raw_results)

    def _raw_values(self, snapshot, instrument, bars, benchmark, as_of):
        try:
            technical = {
                "trend": trend_factor(bars["close"]),
                "relative_strength": relative_strength_factor(bars["close"], benchmark["close"]),
                "volume_turnover": volume_turnover_factor(bars["volume"], bars["turnover_rate"]),
                "volatility_drawdown": volatility_drawdown_factor(bars["close"]),
            }
        except (KeyError, ValueError, ZeroDivisionError):
            technical = {
                "trend": None,
                "relative_strength": None,
                "volume_turnover": None,
                "volatility_drawdown": None,
            }
        financials = snapshot.financials[snapshot.financials["instrument_id"] == instrument]
        fundamentals = fundamental_quality_factor(financials, as_of)
        valuations = self._filter_time(
            snapshot.valuations[snapshot.valuations["instrument_id"] == instrument], "effective_at", as_of
        ).sort_values("effective_at")
        valuation = valuation_percentile_factor(
            valuations.get("pe_ttm", pd.Series(dtype=float)), valuations.get("pb", pd.Series(dtype=float))
        )
        industry = self._filter_time(
            snapshot.industry[snapshot.industry["instrument_id"] == instrument], "effective_at", as_of
        ).sort_values("effective_at")
        industry_value = None
        if not industry.empty:
            latest = industry.iloc[-1]
            industry_value = industry_prosperity_factor(
                latest["industry_relative_return_60d"], latest["industry_fundamental_breadth"]
            )
        event_value = self._event_value(snapshot.events, instrument, as_of)
        return {
            **technical,
            "fundamental_quality": fundamentals,
            "valuation_percentile": valuation,
            "industry_prosperity": industry_value,
            "event_catalyst": event_value,
        }

    @staticmethod
    def _event_value(events: pd.DataFrame, instrument: str, as_of: datetime) -> float:
        if events.empty:
            return 0.0
        required = {"instrument_id", "event_time", "published_at"}
        missing = sorted(required - set(events.columns))
        if missing:
            raise ValueError(f"event factor input missing available-time columns: {missing}")
        frame = events[events["instrument_id"] == instrument].copy()
        frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True)
        frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True)
        frame = frame[
            (frame["event_time"] <= pd.Timestamp(as_of)) & (frame["published_at"] <= pd.Timestamp(as_of))
        ]
        values = [
            event_catalyst_factor(
                row["grade"],
                bool(row["verified"]),
                int(row["independent_sources"]),
                float(row["contradiction_penalty"]),
                days_old=(as_of.date() - row["event_time"].date()).days,
            )
            for _, row in frame.iterrows()
        ]
        return max(values, default=0.0)

    @staticmethod
    def _filter_time(frame: pd.DataFrame, column: str, as_of: datetime) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        if "available_at" not in frame:
            raise ValueError(f"factor input with {column} is missing available_at")
        result = frame.copy()
        result[column] = pd.to_datetime(result[column], utc=True)
        result["available_at"] = pd.to_datetime(result["available_at"], utc=True)
        return result[
            (result[column] <= pd.Timestamp(as_of)) & (result["available_at"] <= pd.Timestamp(as_of))
        ]

    @staticmethod
    def _standardize(results: list[FactorResult]) -> list[FactorResult]:
        by_factor: dict[str, list[FactorResult]] = defaultdict(list)
        for result in results:
            by_factor[result.factor_name].append(result)
        standardized: list[FactorResult] = []
        for factor_results in by_factor.values():
            ready = [result for result in factor_results if result.raw_value is not None]
            values = pd.Series([result.raw_value for result in ready], dtype=float)
            if values.empty:
                standardized.extend(factor_results)
                continue
            lower, upper = values.quantile(0.01), values.quantile(0.99)
            clipped = values.clip(lower, upper)
            std = float(clipped.std(ddof=0))
            z_values = (clipped - clipped.mean()) / std if std > 0 else pd.Series([0.0] * len(clipped))
            scores = clipped.rank(pct=True) * 100 if len(clipped) > 1 else pd.Series([50.0])
            replacements = {
                result.instrument_id: result.model_copy(
                    update={"z_value": float(z_values.iloc[index]), "score": float(scores.iloc[index])}
                )
                for index, result in enumerate(ready)
            }
            standardized.extend(replacements.get(result.instrument_id, result) for result in factor_results)
        return sorted(standardized, key=lambda item: (item.instrument_id, item.factor_name))


class CompositeScorer:
    def __init__(self, required_factors: tuple[str, ...]) -> None:
        self.required_factors = required_factors

    def score(self, results: list[FactorResult], weights: dict[str, float]) -> list[CandidateScore]:
        by_instrument: dict[str, list[FactorResult]] = defaultdict(list)
        for result in results:
            by_instrument[result.instrument_id].append(result)
        candidates = []
        for instrument, factor_results in sorted(by_instrument.items()):
            by_name = {result.factor_name: result for result in factor_results}
            missing = tuple(
                name
                for name in self.required_factors
                if name not in by_name
                or by_name[name].status != FactorStatus.READY
                or by_name[name].score is None
            )
            if missing:
                candidates.append(
                    CandidateScore(
                        instrument_id=instrument,
                        status=CandidateStatus.EXCLUDED_MISSING_FACTOR,
                        missing_factors=missing,
                    )
                )
                continue
            composite = sum(
                float(by_name[name].score) * float(weights[name]) for name in self.required_factors
            )
            candidates.append(
                CandidateScore(
                    instrument_id=instrument, composite_score=composite, status=CandidateStatus.READY
                )
            )
        return candidates
