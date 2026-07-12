from datetime import UTC, date, datetime

import pandas as pd

from a_share_research.providers.akshare import AkshareProvider
from a_share_research.providers.base import FetchRequest


class FakeAkshare:
    @staticmethod
    def stock_zh_a_hist(**kwargs):
        if kwargs["symbol"] == "600001":
            raise TimeoutError("TEST_ONLY timeout")
        return pd.DataFrame(
            [
                {
                    "日期": "2026-07-11",
                    "开盘": 10.0,
                    "最高": 10.5,
                    "最低": 9.8,
                    "收盘": 10.2,
                    "成交量": 1000,
                    "成交额": 10200,
                    "换手率": 1.2,
                }
            ]
        )


def test_partial_symbol_failure_is_explicit() -> None:
    provider = AkshareProvider(api=FakeAkshare(), clock=lambda: datetime(2026, 7, 12, tzinfo=UTC))
    request = FetchRequest(
        dataset="daily_bars",
        symbols=("600000", "600001"),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 11),
        as_of=datetime(2026, 7, 12, tzinfo=UTC),
        run_id="TEST_ONLY_run",
    )

    batch = provider.fetch(request)

    assert batch.is_complete is False
    assert batch.failed_items == ("600001",)
    assert batch.rows[0]["instrument_id"] == "SH600000"
    assert batch.rows[0]["close"] == 10.2
