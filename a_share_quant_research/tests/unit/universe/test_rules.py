from datetime import date

import pandas as pd
import pytest

from a_share_research.universe.rules import UniverseBuilder, UniverseConfig


def test_universe_filters_board_st_new_and_illiquid_stocks() -> None:
    as_of = date(2026, 7, 11)
    securities = pd.DataFrame(
        [
            {"instrument_id": "SH600000", "name": "浦发银行", "list_date": "2000-01-01", "is_st": False},
            {"instrument_id": "SZ300001", "name": "创业板股", "list_date": "2010-01-01", "is_st": False},
            {"instrument_id": "SH600001", "name": "ST测试", "list_date": "2000-01-01", "is_st": True},
            {"instrument_id": "SH600002", "name": "新股", "list_date": "2026-06-01", "is_st": False},
            {"instrument_id": "SH600003", "name": "低流动性", "list_date": "2000-01-01", "is_st": False},
        ]
    )
    dates = pd.bdate_range(end=as_of, periods=20)
    bars = pd.DataFrame(
        [
            {
                "instrument_id": instrument,
                "effective_at": day,
                "amount": 200.0 if instrument == "SH600000" else 10.0,
                "suspended": False,
                "limit_up_locked": instrument == "SH600000" and day == dates[-1],
                "limit_down_locked": False,
            }
            for instrument in ("SH600000", "SH600003")
            for day in dates
        ]
    )
    config = UniverseConfig(
        allowed_prefixes=("000", "001", "002", "003", "600", "601", "603", "605"),
        minimum_listing_trading_days=250,
        minimum_20d_average_amount=100.0,
        minimum_20d_valid_days=18,
    )

    result = UniverseBuilder(config).build(as_of, securities, bars)

    assert result.eligible == ("SH600000",)
    assert result.trade_flags["SH600000"].limit_up_locked is True
    assert "BOARD_EXCLUDED" in result.excluded["SZ300001"]
    assert "ST_EXCLUDED" in result.excluded["SH600001"]
    assert "TOO_NEW" in result.excluded["SH600002"]
    assert "ILLIQUID" in result.excluded["SH600003"]


def test_missing_trade_status_columns_fail_closed() -> None:
    securities = pd.DataFrame(
        [{"instrument_id": "SH600000", "name": "A", "list_date": "2000-01-01", "is_st": False}]
    )
    bars = pd.DataFrame([{"instrument_id": "SH600000", "effective_at": "2026-07-10", "amount": 1000.0}])
    config = UniverseConfig(
        allowed_prefixes=("600",),
        minimum_listing_trading_days=250,
        minimum_20d_average_amount=1.0,
        minimum_20d_valid_days=1,
    )
    with pytest.raises(ValueError, match="trade status"):
        UniverseBuilder(config).build(date(2026, 7, 11), securities, bars)
