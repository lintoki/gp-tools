from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from quant.realtime_screener import AkshareRealtimeProvider, RealtimeStrategyScreener, _normalize_quote


def quote(code, name, pct_chg, price=10.0, volume_ratio=2.0, turnover_rate=6.0, cap=10_000_000_000):
    return {
        "code": code,
        "name": name,
        "price": price,
        "pct_chg": pct_chg,
        "volume_ratio": volume_ratio,
        "turnover_rate": turnover_rate,
        "total_market_cap": cap,
        "open": price / (1 + pct_chg / 100),
        "is_st": False,
        "is_suspended": False,
    }


def intraday(points):
    return pd.DataFrame(
        [
            {
                "datetime": dt,
                "price": price,
                "vwap": vwap,
                "volume": volume,
                "fund_flow": fund_flow,
            }
            for dt, price, vwap, volume, fund_flow in points
        ]
    )


class StubRealtimeProvider:
    def __init__(self, quotes, intraday_by_code, limit_up_counts=None, daily_features=None, index_pct_chg=0.2):
        self.quotes = quotes
        self.intraday_by_code = intraday_by_code
        self.limit_up_counts = limit_up_counts or {}
        self.daily_features = daily_features or {}
        self.index_pct_chg = index_pct_chg
        self.ranked_quote_calls = 0
        self.intraday_codes = []

    def get_ranked_quotes(self):
        self.ranked_quote_calls += 1
        return self.quotes

    def get_index_pct_chg(self):
        return self.index_pct_chg

    def get_limit_up_counts(self, codes, trade_date, lookback=20):
        return {code: self.limit_up_counts.get(code, 0) for code in codes}

    def get_intraday_bars(self, code, trade_date):
        self.intraday_codes.append(code)
        return self.intraday_by_code.get(code, pd.DataFrame())

    def get_daily_features(self, code, trade_date):
        return self.daily_features.get(
            code,
            {
                "ma5": 18.2,
                "ma30": 17.6,
                "ma5_slope": 0.2,
                "ma30_slope": 0.1,
                "ma_structure": "ma5_above_ma30_and_up",
            },
        )


class FailingRankedQuoteProvider(StubRealtimeProvider):
    def get_ranked_quotes(self):
        raise RuntimeError("RemoteDisconnected('Remote end closed connection without response')")


class RealtimeScreenerTest(unittest.TestCase):
    def test_signal_scan_returns_chinese_warning_when_ranked_quote_source_fails(self):
        provider = FailingRankedQuoteProvider([], {})
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 40))

        result = screener.run("tail_30m_reversal")

        self.assertTrue(result["run_time_valid"])
        self.assertEqual([], result["candidates"])
        self.assertEqual([], result["near_misses"])
        self.assertIn("行情榜数据源暂时不可用", result["data_warning"])
        self.assertNotIn("RemoteDisconnected", str(result))

    def test_yang_strategy_does_not_run_before_1430(self):
        provider = StubRealtimeProvider([], {})
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 20))

        result = screener.run("overnight_arbitrage")

        self.assertFalse(result["run_time_valid"])
        self.assertEqual([], result["candidates"])
        self.assertEqual("今日无符合策略标的，建议空仓", result["decision"]["note"])
        self.assertEqual(0, provider.ranked_quote_calls)

    def test_yang_strategy_uses_ranked_quotes_filters_scores_and_reports_rejections(self):
        provider = StubRealtimeProvider(
            quotes=[
                quote("605305", "中际联合", 4.1, price=42.76, volume_ratio=2.4, turnover_rate=5.41, cap=8_979_000_000),
                quote("000029", "深深房A", -0.65, price=29.05),
                quote("300001", "创业板示例", 4.0),
                quote("600666", "无涨停示例", 4.2),
            ],
            intraday_by_code={
                "605305": intraday(
                    [
                        ("2026-06-23 09:30", 41.0, 40.8, 1000, 10),
                        ("2026-06-23 14:20", 42.0, 41.4, 1300, 20),
                        ("2026-06-23 14:35", 42.8, 41.8, 1500, 30),
                        ("2026-06-23 14:45", 42.4, 41.9, 1500, 25),
                        ("2026-06-23 14:55", 42.7, 42.0, 1500, 28),
                    ]
                )
            },
            limit_up_counts={"605305": 1, "600666": 0},
            index_pct_chg=0.3,
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 40))

        result = screener.run("overnight_arbitrage")

        self.assertEqual("yang_yongxing_overnight_arbitrage_8_steps", result["strategy"])
        self.assertTrue(result["run_time_valid"])
        self.assertEqual(1, provider.ranked_quote_calls)
        self.assertEqual(1, len(result["candidates"]))
        candidate = result["candidates"][0]
        self.assertEqual("605305", candidate["code"])
        self.assertGreaterEqual(candidate["score"], 70)
        self.assertEqual("buy_candidate", candidate["action"])
        self.assertEqual("次日 9:30-10:00 只卖不加仓", candidate["sell_rule_next_day"])
        rejected = {item["code"]: item["reasons"] for item in result["rejections"]}
        self.assertIn("当前涨幅不在 2%-6% 观察池范围", rejected["000029"])
        self.assertIn("非沪深主板", rejected["300001"])
        self.assertIn("近20个交易日无涨停记录", rejected["600666"])
        stages = {item["stage"] for item in result["rejections"]}
        self.assertIn("涨幅榜粗筛", stages)
        self.assertIn("硬性条件过滤", stages)
        self.assertNotIn("rough_filter", stages)
        self.assertNotIn("hard_filter", stages)

    def test_yang_strategy_outputs_three_candidate_levels(self):
        provider = StubRealtimeProvider(
            quotes=[
                quote("605305", "A级", 4.1, price=42.76, volume_ratio=2.4, turnover_rate=5.41, cap=8_979_000_000),
                quote("603111", "B级", 4.0, price=20.0, volume_ratio=1.2, turnover_rate=4.5, cap=4_800_000_000),
                quote("002222", "C级", 2.2, price=12.0, volume_ratio=0.9, turnover_rate=3.5, cap=4_200_000_000),
                quote("300001", "创业板示例", 4.0),
            ],
            intraday_by_code={
                "605305": intraday(
                    [
                        ("2026-06-23 09:30", 41.0, 40.8, 1000, 10),
                        ("2026-06-23 14:20", 42.0, 41.4, 1200, 12),
                        ("2026-06-23 14:35", 42.8, 41.8, 1400, 18),
                        ("2026-06-23 14:55", 42.7, 42.0, 1400, 20),
                    ]
                ),
                "603111": intraday(
                    [
                        ("2026-06-23 09:30", 19.3, 19.2, 1000, 10),
                        ("2026-06-23 13:50", 20.3, 19.8, 1000, 12),
                        ("2026-06-23 14:35", 20.0, 19.8, 1100, 13),
                        ("2026-06-23 14:55", 20.1, 19.9, 1100, 13),
                    ]
                ),
                "002222": intraday(
                    [
                        ("2026-06-23 09:30", 11.7, 11.7, 1000, 1),
                        ("2026-06-23 14:35", 12.0, 11.9, 900, 1),
                        ("2026-06-23 14:55", 12.0, 11.9, 900, 1),
                    ]
                ),
            },
            limit_up_counts={"605305": 1, "603111": 1, "002222": 0},
            index_pct_chg=0.3,
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 45))

        result = screener.run("overnight_arbitrage")

        self.assertEqual("strict_buy_relaxed_watch", result["strategy_mode"])
        self.assertEqual(["605305"], [item["code"] for item in result["A_buy_candidates"]])
        self.assertEqual(["603111"], [item["code"] for item in result["B_watch_candidates"]])
        self.assertEqual(["002222"], [item["code"] for item in result["C_pool_candidates"]])
        self.assertEqual("buy_candidate", result["A_buy_candidates"][0]["action"])
        self.assertEqual("watch", result["B_watch_candidates"][0]["action"])
        self.assertIn("需要 14:30 后放量突破当日新高", result["B_watch_candidates"][0]["upgrade_requirements"])
        self.assertTrue(result["trade_decision"]["can_buy"])
        self.assertEqual(1, result["trade_decision"]["max_buy_count"])
        self.assertEqual(1, result["stats"]["A_buy_count"])
        self.assertEqual(1, result["stats"]["B_watch_count"])
        self.assertEqual(1, result["stats"]["C_pool_count"])

    def test_yang_strategy_returns_near_misses_when_no_candidates_match(self):
        provider = StubRealtimeProvider(
            quotes=[
                quote("600666", "接近标准", 4.2, price=18.8, volume_ratio=2.2, turnover_rate=6.3, cap=9_000_000_000),
                quote("000029", "深深房A", 2.9, price=29.05, volume_ratio=2.0, turnover_rate=6.0, cap=9_000_000_000),
                quote("300001", "创业板示例", 4.1),
            ],
            intraday_by_code={},
            limit_up_counts={"600666": 0},
            index_pct_chg=0.3,
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 40))

        result = screener.run("overnight_arbitrage")

        self.assertEqual([], result["candidates"])
        self.assertGreater(len(result["near_misses"]), 0)
        self.assertLessEqual(len(result["near_misses"]), 5)
        self.assertEqual("600666", result["near_misses"][0]["code"])
        self.assertEqual("观察，不买入", result["near_misses"][0]["action"])
        self.assertIn("缺少分时数据", result["near_misses"][0]["reasons"])

    def test_yang_strategy_outputs_watch_when_candidate_has_no_tail_breakout(self):
        provider = StubRealtimeProvider(
            quotes=[quote("605305", "中际联合", 4.1, price=42.2)],
            intraday_by_code={
                "605305": intraday(
                    [
                        ("2026-06-23 09:30", 41.0, 40.8, 1000, 10),
                        ("2026-06-23 13:50", 42.8, 41.6, 1000, 12),
                        ("2026-06-23 14:35", 42.4, 41.8, 1200, 14),
                        ("2026-06-23 14:55", 42.5, 41.9, 1200, 15),
                    ]
                )
            },
            limit_up_counts={"605305": 2},
            index_pct_chg=0.1,
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 45))

        result = screener.run("overnight_arbitrage")

        self.assertEqual([], result["A_buy_candidates"])
        self.assertEqual(1, len(result["B_watch_candidates"]))
        self.assertEqual("watch", result["B_watch_candidates"][0]["action"])
        self.assertFalse(result["trade_decision"]["can_buy"])

    def test_three_level_decision_cannot_buy_without_a_candidates(self):
        provider = StubRealtimeProvider(
            quotes=[quote("603111", "B级", 4.0, price=20.0, volume_ratio=1.2, turnover_rate=4.5, cap=4_800_000_000)],
            intraday_by_code={
                "603111": intraday(
                    [
                        ("2026-06-23 09:30", 19.3, 19.2, 1000, 10),
                        ("2026-06-23 13:50", 20.3, 19.8, 1000, 12),
                        ("2026-06-23 14:35", 20.0, 19.8, 1100, 13),
                        ("2026-06-23 14:55", 20.1, 19.9, 1100, 13),
                    ]
                )
            },
            limit_up_counts={"603111": 1},
            index_pct_chg=0.3,
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 45))

        result = screener.run("overnight_arbitrage")

        self.assertEqual([], result["A_buy_candidates"])
        self.assertEqual(1, len(result["B_watch_candidates"]))
        self.assertFalse(result["trade_decision"]["can_buy"])
        self.assertEqual("没有 A 级严格买入候选，今日空仓", result["trade_decision"]["reason"])

    def test_signal_scan_skips_intraday_fetch_when_quote_misses_c_pool_basics(self):
        provider = StubRealtimeProvider(
            quotes=[quote("603999", "基础不合格", 4.0, price=10.0, volume_ratio=0.4, turnover_rate=1.0, cap=2_000_000_000)],
            intraday_by_code={},
            limit_up_counts={"603999": 1},
            index_pct_chg=0.2,
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 45))

        result = screener.run("overnight_arbitrage")

        self.assertEqual([], provider.intraday_codes)
        self.assertIn("603999", {item["code"] for item in result["rejected"]})

    def test_tail_30m_strategy_outputs_pattern_and_rejection_reasons(self):
        provider = StubRealtimeProvider(
            quotes=[
                quote("603000", "示例股票", 4.2, price=18.88, volume_ratio=1.8, turnover_rate=6.2, cap=9_800_000_000),
                quote("603001", "逃跑形态", 4.0, price=18.1, volume_ratio=2.0, turnover_rate=6.0, cap=9_000_000_000),
            ],
            intraday_by_code={
                "603000": intraday(
                    [
                        ("2026-06-23 09:30", 18.0, 17.9, 1000, 10),
                        ("2026-06-23 14:20", 18.4, 18.0, 1000, 12),
                        ("2026-06-23 14:35", 18.9, 18.3, 1400, 18),
                        ("2026-06-23 14:45", 18.6, 18.4, 1300, 18),
                        ("2026-06-23 14:55", 18.8, 18.5, 1400, 20),
                    ]
                ),
                "603001": intraday(
                    [
                        ("2026-06-23 09:30", 18.0, 17.9, 1000, 5),
                        ("2026-06-23 14:31", 18.6, 18.1, 1600, 6),
                        ("2026-06-23 14:45", 17.8, 18.0, 2200, -20),
                        ("2026-06-23 14:55", 17.7, 18.0, 2300, -30),
                    ]
                ),
            },
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 50))

        result = screener.run("tail_30m_reversal")

        self.assertEqual("chen_xiaoqun_last_30min_method", result["strategy"])
        self.assertEqual(1, len(result["candidates"]))
        candidate = result["candidates"][0]
        self.assertEqual("qualified_break_intraday_high", candidate["tail_pattern"])
        self.assertEqual("buy_candidate", candidate["action"])
        self.assertGreaterEqual(candidate["score"], 70)
        rejected = {item["code"]: item["reasons"] for item in result["rejections"]}
        self.assertIn("尾盘先涨后落并跌破开盘价", rejected["603001"])

    def test_tail_strategy_rejects_pattern_a_and_keeps_weaker_pattern_in_c_pool(self):
        provider = StubRealtimeProvider(
            quotes=[
                quote("603001", "逃跑形态", 4.0, price=18.1, volume_ratio=2.0, turnover_rate=6.0, cap=9_000_000_000),
                quote("603002", "震荡形态", 2.5, price=18.1, volume_ratio=0.9, turnover_rate=3.5, cap=4_500_000_000),
            ],
            intraday_by_code={
                "603001": intraday(
                    [
                        ("2026-06-23 09:30", 18.0, 17.9, 1000, 5),
                        ("2026-06-23 14:31", 18.6, 18.1, 1600, 6),
                        ("2026-06-23 14:45", 17.8, 18.0, 2200, -20),
                        ("2026-06-23 14:55", 17.7, 18.0, 2300, -30),
                    ]
                ),
                "603002": intraday(
                    [
                        ("2026-06-23 09:30", 18.0, 18.0, 1000, 1),
                        ("2026-06-23 14:20", 18.2, 18.0, 1000, 1),
                        ("2026-06-23 14:31", 18.1, 18.15, 900, 1),
                        ("2026-06-23 14:45", 18.1, 18.15, 900, 1),
                        ("2026-06-23 14:55", 18.1, 18.15, 900, 1),
                    ]
                ),
            },
            daily_features={
                "603001": {"ma5": 18.2, "ma30": 17.6, "ma_structure": "ma5_above_ma30_and_up"},
                "603002": {"ma5": 18.0, "ma30": 17.9, "ma_structure": "ma5_above_ma30"},
            },
        )
        screener = RealtimeStrategyScreener(provider, now_func=lambda: datetime(2026, 6, 23, 14, 50))

        result = screener.run("tail_30m_reversal")

        self.assertEqual(["603002"], [item["code"] for item in result["C_pool_candidates"]])
        self.assertEqual("sideways_no_signal", result["C_pool_candidates"][0]["tail_pattern"])
        self.assertIn("603001", {item["code"] for item in result["rejected"]})

    def test_quote_normalization_handles_percent_and_market_cap_units(self):
        normalized = _normalize_quote(
            {
                "code": "605305",
                "name": "中际联合",
                "price": 42.76,
                "pct_chg": 0.041,
                "volume_ratio": 2.4,
                "turnover_rate": 0.0541,
                "total_market_cap": 89.79,
            }
        )

        self.assertAlmostEqual(4.1, normalized["pct_chg"])
        self.assertAlmostEqual(5.41, normalized["turnover_rate"])
        self.assertEqual(8_979_000_000, normalized["total_market_cap"])

    def test_eastmoney_ranked_quote_fetch_stops_after_page_drops_below_three_pct(self):
        first = Mock()
        first.json.return_value = {
            "data": {
                "diff": [
                    {"f12": "605305", "f14": "中际联合", "f2": 42.76, "f3": 4.1, "f10": 2.4, "f8": 5.41, "f20": 8979000000, "f17": 41.0},
                    {"f12": "600001", "f14": "示例A", "f2": 10.0, "f3": 3.2, "f10": 1.2, "f8": 5.1, "f20": 8000000000, "f17": 9.7},
                ]
            }
        }
        first.raise_for_status.return_value = None
        second = Mock()
        second.json.return_value = {
            "data": {
                "diff": [
                    {"f12": "000029", "f14": "深深房A", "f2": 29.05, "f3": 2.9, "f10": 1.3, "f8": 6.0, "f20": 9000000000, "f17": 28.9}
                ]
            }
        }
        second.raise_for_status.return_value = None

        with patch("quant.realtime_screener.requests.get", side_effect=[first, second]) as request_get:
            provider = AkshareRealtimeProvider(cache_dir=Path("/tmp/shortline_quote_test"))
            quotes = provider.get_ranked_quotes()

        self.assertEqual(2, request_get.call_count)
        self.assertEqual(["605305", "600001"], [item["code"] for item in quotes])

    def test_sina_ranked_quote_fallback_enriches_with_tencent_details(self):
        sina = Mock()
        sina.json.return_value = [
            {
                "symbol": "sh605305",
                "code": "605305",
                "name": "中际联合",
                "trade": "42.76",
                "changepercent": 4.1,
                "open": "41.0",
                "turnoverratio": 5.41,
                "mktcap": 897900,
            },
            {
                "symbol": "sz000029",
                "code": "000029",
                "name": "深深房A",
                "trade": "29.05",
                "changepercent": 2.9,
                "open": "28.9",
                "turnoverratio": 6.0,
                "mktcap": 900000,
            },
        ]
        sina.raise_for_status.return_value = None
        fields = [""] * 55
        fields[1] = "中际联合"
        fields[2] = "605305"
        fields[3] = "42.76"
        fields[5] = "41.00"
        fields[32] = "4.10"
        fields[38] = "5.41"
        fields[44] = "89.79"
        fields[49] = "1.80"
        tencent = Mock()
        tencent.text = f'v_sh605305="{"~".join(fields)}";'
        tencent.raise_for_status.return_value = None

        with patch("quant.realtime_screener._fetch_eastmoney_ranked_quotes", side_effect=RuntimeError("em down")), patch(
            "quant.realtime_screener.requests.get", side_effect=[sina, tencent]
        ):
            provider = AkshareRealtimeProvider(cache_dir=Path("/tmp/shortline_quote_test"))
            quotes = provider.get_ranked_quotes()

        self.assertEqual(["605305"], [item["code"] for item in quotes])
        self.assertEqual(1.8, quotes[0]["volume_ratio"])
        self.assertEqual(5.41, quotes[0]["turnover_rate"])
        self.assertEqual(8_979_000_000, quotes[0]["total_market_cap"])


if __name__ == "__main__":
    unittest.main()
