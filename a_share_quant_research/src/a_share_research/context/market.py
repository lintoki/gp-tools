from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from a_share_research.context.models import (
    ContextSnapshot,
    ContextStatus,
    FuturesRisk,
    GlobalContext,
    IndustryDevelopment,
    MarketContext,
)


class ContextDataIncomplete(RuntimeError):
    pass


class ContextEngine:
    required_series = ("SP500", "VIXCLS", "DGS10", "BAMLH0A0HYM2")

    def __init__(
        self, market_max_age: timedelta = timedelta(days=4), cot_max_age: timedelta = timedelta(days=10)
    ):
        self.market_max_age = market_max_age
        self.cot_max_age = cot_max_age

    def compute(self, snapshot: ContextSnapshot, as_of: datetime) -> GlobalContext:
        market_frame = self._prepare_market(snapshot.market_series, as_of)
        series = {
            series_id: self._series(market_frame, series_id, as_of) for series_id in self.required_series
        }
        market = MarketContext(
            index_trend=self._trend(series["SP500"]),
            volatility_direction=self._direction(series["VIXCLS"]),
            yield_direction=self._direction(series["DGS10"]),
            credit_direction=self._direction(series["BAMLH0A0HYM2"]),
            latest_observations={
                series_id: frame.iloc[-1]["effective_at"].to_pydatetime()
                for series_id, frame in series.items()
            },
        )
        industries = self._industries(snapshot.industry_evidence, as_of)
        futures = self._futures(snapshot.cot, as_of)
        return GlobalContext(
            status=ContextStatus.READY,
            as_of=as_of,
            market=market,
            industries=industries,
            futures=futures,
        )

    @staticmethod
    def _prepare_market(frame: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
        prepared = frame.copy()
        if prepared.empty:
            return prepared
        if "available_at" not in prepared:
            raise ContextDataIncomplete("market series available_at is missing")
        prepared["effective_at"] = pd.to_datetime(prepared["effective_at"], utc=True)
        prepared["available_at"] = pd.to_datetime(prepared["available_at"], utc=True)
        return prepared[
            (prepared["effective_at"] <= pd.Timestamp(as_of))
            & (prepared["available_at"] <= pd.Timestamp(as_of))
        ].sort_values("effective_at")

    def _series(self, frame: pd.DataFrame, series_id: str, as_of: datetime) -> pd.DataFrame:
        selected = frame[frame["series_id"] == series_id].sort_values("effective_at")
        if len(selected) < 60:
            raise ContextDataIncomplete(f"required series {series_id} has fewer than 60 observations")
        latest = selected.iloc[-1]["effective_at"].to_pydatetime()
        if as_of - latest > self.market_max_age:
            raise ContextDataIncomplete(f"required series {series_id} is stale")
        return selected

    @staticmethod
    def _trend(frame: pd.DataFrame) -> str:
        values = frame["value"].astype(float)
        ma20 = float(values.iloc[-20:].mean())
        ma60 = float(values.iloc[-60:].mean())
        latest = float(values.iloc[-1])
        if latest > ma20 > ma60:
            return "UP"
        if latest < ma20 < ma60:
            return "DOWN"
        return "MIXED"

    @staticmethod
    def _direction(frame: pd.DataFrame) -> str:
        values = frame["value"].astype(float)
        latest = float(values.iloc[-1])
        mean20 = float(values.iloc[-20:].mean())
        if latest > mean20:
            return "UP"
        if latest < mean20:
            return "DOWN"
        return "FLAT"

    @staticmethod
    def _industries(frame: pd.DataFrame, as_of: datetime) -> tuple[IndustryDevelopment, ...]:
        if frame.empty:
            return ()
        prepared = frame.copy()
        if "published_at" not in prepared:
            raise ContextDataIncomplete("industry evidence published_at is missing")
        prepared["event_time"] = pd.to_datetime(prepared["event_time"], utc=True)
        prepared["published_at"] = pd.to_datetime(prepared["published_at"], utc=True)
        prepared = prepared[
            (prepared["event_time"] <= pd.Timestamp(as_of))
            & (prepared["published_at"] <= pd.Timestamp(as_of))
            & prepared["verified"].astype(bool)
        ]
        results = []
        for industry, rows in prepared.groupby("industry"):
            rows = rows.sort_values("event_time")
            results.append(
                IndustryDevelopment(
                    industry=str(industry),
                    direction=str(rows.iloc[-1]["direction"]),
                    evidence_ids=tuple(sorted(set(rows["evidence_id"].astype(str)))),
                    latest_event_time=rows.iloc[-1]["event_time"].to_pydatetime(),
                )
            )
        return tuple(sorted(results, key=lambda item: item.industry))

    def _futures(self, frame: pd.DataFrame, as_of: datetime) -> tuple[FuturesRisk, ...]:
        if frame.empty:
            raise ContextDataIncomplete("CFTC COT data is missing")
        prepared = frame.copy()
        if "available_at" not in prepared:
            raise ContextDataIncomplete("CFTC COT available_at is missing")
        prepared["report_date"] = pd.to_datetime(prepared["report_date"], utc=True)
        prepared["available_at"] = pd.to_datetime(prepared["available_at"], utc=True)
        prepared = prepared[
            (prepared["report_date"] <= pd.Timestamp(as_of))
            & (prepared["available_at"] <= pd.Timestamp(as_of))
        ]
        results = []
        for contract, rows in prepared.groupby("contract_market_name"):
            rows = rows.sort_values("report_date")
            if len(rows) < 2:
                raise ContextDataIncomplete(f"CFTC COT contract {contract} requires two reports")
            latest = rows.iloc[-1]
            previous = rows.iloc[-2]
            report_date = latest["report_date"].to_pydatetime()
            if as_of - report_date > self.cot_max_age:
                raise ContextDataIncomplete(f"CFTC COT contract {contract} is stale")
            latest_net = float(latest["long"]) - float(latest["short"])
            previous_net = float(previous["long"]) - float(previous["short"])
            results.append(
                FuturesRisk(
                    contract_market_name=str(contract),
                    report_date=report_date,
                    net_position=latest_net,
                    net_position_change=latest_net - previous_net,
                )
            )
        return tuple(sorted(results, key=lambda item: item.contract_market_name))
