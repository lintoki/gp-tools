from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from a_share_research.providers.base import Clock, FetchRequest, build_batch

DAILY_FIELDS = (
    "instrument_id",
    "effective_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover_rate",
)


class AkshareProvider:
    name = "akshare"
    capabilities = frozenset({"daily_bars"})

    def __init__(
        self,
        api: Any | None = None,
        clock: Clock | None = None,
        minimum_interval_seconds: float = 0.2,
        sleeper=time.sleep,
    ) -> None:
        self.api = api
        self.clock = clock or (lambda: datetime.now(UTC))
        self.minimum_interval_seconds = minimum_interval_seconds
        self.sleeper = sleeper
        self._last_raw_payload: bytes | None = None

    @property
    def last_raw_payload(self) -> bytes:
        if self._last_raw_payload is None:
            raise RuntimeError("no raw AkShare response has been captured")
        return self._last_raw_payload

    def _api(self):
        if self.api is not None:
            return self.api
        import akshare

        return akshare

    def fetch(self, request: FetchRequest):
        if request.dataset != "daily_bars":
            raise ValueError(f"unsupported dataset: {request.dataset}")
        if not request.symbols or request.start_date is None or request.end_date is None:
            raise ValueError("daily_bars requires symbols, start_date and end_date")
        rows: list[dict] = []
        failed: list[str] = []
        raw_responses: list[dict] = []
        for index, symbol in enumerate(request.symbols):
            if index:
                self.sleeper(self.minimum_interval_seconds)
            try:
                raw = self._api().stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=request.start_date.strftime("%Y%m%d"),
                    end_date=request.end_date.strftime("%Y%m%d"),
                    adjust="",
                )
                raw_responses.append(
                    {
                        "symbol": symbol,
                        "frame": raw.to_json(orient="split", force_ascii=False, date_format="iso"),
                    }
                )
                normalized = self._normalize_daily(raw, symbol)
                if not normalized:
                    failed.append(symbol)
                    continue
                rows.extend(normalized)
            except Exception:
                failed.append(symbol)
        fetched_at = self.clock()
        self._last_raw_payload = json.dumps(raw_responses, ensure_ascii=False, sort_keys=True).encode("utf-8")
        effective_at = (
            pd.to_datetime(max(row["effective_at"] for row in rows), utc=True).to_pydatetime()
            if rows
            else datetime.combine(request.end_date, datetime.min.time(), tzinfo=UTC)
        )
        return build_batch(
            request=request,
            rows=rows,
            source_name=self.name,
            source_uri="https://akshare.akfamily.xyz/data/stock/stock.html",
            provider_version=self._provider_version(),
            fetched_at=fetched_at,
            effective_at=effective_at,
            failed_items=failed,
            expected_fields=DAILY_FIELDS,
            raw_payload_sha256=hashlib.sha256(self._last_raw_payload).hexdigest(),
        )

    @staticmethod
    def _normalize_daily(raw: pd.DataFrame, symbol: str) -> list[dict]:
        if raw is None or raw.empty:
            return []
        mapping = {
            "日期": "effective_at",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
            "换手率": "turnover_rate",
        }
        normalized = raw.rename(columns=mapping)
        missing = [
            field for field in DAILY_FIELDS if field not in {"instrument_id"} and field not in normalized
        ]
        if missing:
            raise ValueError(f"AkShare daily schema missing: {missing}")
        instrument_id = f"SH{symbol}" if symbol.startswith("6") else f"SZ{symbol}"
        rows = []
        for item in normalized.to_dict(orient="records"):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "effective_at": str(item["effective_at"]),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                    "amount": float(item["amount"]),
                    "turnover_rate": float(item["turnover_rate"]),
                }
            )
        return rows

    def _provider_version(self) -> str:
        return str(getattr(self._api(), "__version__", "injected"))
