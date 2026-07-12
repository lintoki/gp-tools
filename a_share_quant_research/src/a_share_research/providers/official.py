from __future__ import annotations

import time as time_module
from datetime import UTC, datetime, time, timedelta
from io import StringIO

import httpx
import pandas as pd

from a_share_research.providers.base import Clock, FetchRequest, build_batch


class _OfficialHttpProvider:
    name = "official"
    capabilities: frozenset[str] = frozenset()

    def __init__(
        self,
        client: httpx.Client | None = None,
        clock: Clock | None = None,
        minimum_interval_seconds: float = 0.2,
        sleeper=time_module.sleep,
    ) -> None:
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
        self.clock = clock or (lambda: datetime.now(UTC))
        self.minimum_interval_seconds = minimum_interval_seconds
        self.sleeper = sleeper

    def _wait(self, index: int) -> None:
        if index:
            self.sleeper(self.minimum_interval_seconds)


class FredCsvProvider(_OfficialHttpProvider):
    name = "fred_csv"
    capabilities = frozenset({"us_market", "us_macro"})
    base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def fetch(self, request: FetchRequest):
        if not request.series_ids:
            raise ValueError("FRED request requires series_ids")
        rows: list[dict] = []
        failed: list[str] = []
        latest_date = request.as_of
        for index, series_id in enumerate(request.series_ids):
            self._wait(index)
            try:
                response = self.client.get(self.base_url, params={"id": series_id})
                response.raise_for_status()
                frame = pd.read_csv(StringIO(response.text))
                value_column = next(column for column in frame.columns if column != "observation_date")
                for item in frame.to_dict(orient="records"):
                    if str(item[value_column]) == ".":
                        continue
                    rows.append(
                        {
                            "series_id": series_id,
                            "effective_at": str(item["observation_date"]),
                            "available_at": datetime.combine(
                                pd.Timestamp(item["observation_date"]).date() + timedelta(days=1),
                                time(23, 59),
                                tzinfo=UTC,
                            ).isoformat(),
                            "value": float(item[value_column]),
                        }
                    )
                if rows:
                    latest_date = pd.Timestamp(rows[-1]["effective_at"]).to_pydatetime().replace(tzinfo=UTC)
            except Exception:
                failed.append(series_id)
        now = self.clock()
        return build_batch(
            request=request,
            rows=rows,
            source_name=self.name,
            source_uri=self.base_url,
            provider_version="fred-csv-v1",
            fetched_at=now,
            effective_at=latest_date,
            failed_items=failed,
            expected_fields=("series_id", "effective_at", "available_at", "value"),
        )


class CftcCotProvider(_OfficialHttpProvider):
    name = "cftc_cot"
    capabilities = frozenset({"cftc_cot"})
    base_url = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"

    def fetch(self, request: FetchRequest):
        response = self.client.get(
            self.base_url, params={"$limit": 5000, "$order": "report_date_as_yyyy_mm_dd DESC"}
        )
        response.raise_for_status()
        rows = []
        for item in response.json():
            report_date = pd.Timestamp(item["report_date_as_yyyy_mm_dd"]).date()
            rows.append(
                {
                    "report_date": report_date.isoformat(),
                    "available_at": datetime.combine(
                        report_date + timedelta(days=3), time(22, 0), tzinfo=UTC
                    ).isoformat(),
                    "contract_market_name": str(item["contract_market_name"]),
                    "long": float(item["noncomm_positions_long_all"]),
                    "short": float(item["noncomm_positions_short_all"]),
                }
            )
        now = self.clock()
        return build_batch(
            request=request,
            rows=rows,
            source_name=self.name,
            source_uri=self.base_url,
            provider_version="cftc-pre-v1",
            fetched_at=now,
            effective_at=now,
            expected_fields=("report_date", "available_at", "contract_market_name", "long", "short"),
        )


class SecEdgarProvider(_OfficialHttpProvider):
    name = "sec_edgar"
    capabilities = frozenset({"sec_submissions"})
    base_url = "https://data.sec.gov/submissions"

    def fetch(self, request: FetchRequest):
        if not request.symbols:
            raise ValueError("SEC submissions request requires CIK values in symbols")
        rows: list[dict] = []
        failed: list[str] = []
        headers = {
            "User-Agent": request.parameters.get("user_agent", "a-share-research contact@example.invalid")
        }
        for index, cik in enumerate(request.symbols):
            self._wait(index)
            try:
                response = self.client.get(f"{self.base_url}/CIK{str(cik).zfill(10)}.json", headers=headers)
                response.raise_for_status()
                rows.append(dict(response.json()))
            except Exception:
                failed.append(cik)
        now = self.clock()
        return build_batch(
            request=request,
            rows=rows,
            source_name=self.name,
            source_uri=self.base_url,
            provider_version="sec-submissions-v1",
            fetched_at=now,
            effective_at=now,
            failed_items=failed,
            expected_fields=("cik", "name", "filings"),
        )
