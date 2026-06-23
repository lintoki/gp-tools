import unittest
from datetime import date
from unittest.mock import Mock, patch

import pandas as pd

from quant.real_data import fetch_a_share_bars, fetch_ranked_backtest_bars


class RealDataTest(unittest.TestCase):
    def test_fetch_a_share_bars_can_fetch_all_main_board_candidates_when_limit_is_none(self):
        stock_list = pd.DataFrame(
            [{"code": f"000{i:03d}", "name": f"主板{i:03d}"} for i in range(1, 83)]
            + [{"code": "300001", "name": "创业板示例"}]
        )
        hist = pd.DataFrame(
            [
                {
                    "日期": "2025-01-02",
                    "开盘": 10.0,
                    "收盘": 10.4,
                    "最高": 10.5,
                    "最低": 9.9,
                    "成交量": 100000,
                    "成交额": 100000000,
                    "涨跌幅": 4.0,
                    "换手率": 6.5,
                }
            ]
        )

        with patch("quant.real_data.ak.stock_info_a_code_name", return_value=stock_list), patch(
            "quant.real_data.ak.stock_zh_a_hist", return_value=hist
        ) as history_fetch:
            result = fetch_a_share_bars("2025-01-02", "2025-01-03", max_symbols=None)

            self.assertEqual(82, len(result))
            self.assertEqual(82, history_fetch.call_count)

    def test_fetch_a_share_bars_returns_normalized_in_memory_frames_with_limit(self):
        stock_list = pd.DataFrame(
            [
                {"code": "000001", "name": "平安银行"},
                {"code": "600000", "name": "浦发银行"},
                {"code": "300001", "name": "非主板示例"},
            ]
        )
        hist = pd.DataFrame(
            [
                {
                    "日期": "2025-01-02",
                    "开盘": 10.0,
                    "收盘": 10.4,
                    "最高": 10.5,
                    "最低": 9.9,
                    "成交量": 100000,
                    "成交额": 100000000,
                    "涨跌幅": 4.0,
                    "换手率": 6.5,
                },
                {
                    "日期": "2025-01-03",
                    "开盘": 10.5,
                    "收盘": 10.7,
                    "最高": 10.9,
                    "最低": 10.3,
                    "成交量": 120000,
                    "成交额": 120000000,
                    "涨跌幅": 1.92,
                    "换手率": 7.1,
                },
            ]
        )

        with patch("quant.real_data.ak.stock_info_a_code_name", return_value=stock_list), patch(
            "quant.real_data.ak.stock_zh_a_hist", return_value=hist
        ):
            result = fetch_a_share_bars("2025-01-02", "2025-01-03", max_symbols=1)

            self.assertEqual(["000001"], sorted(result))
            bars = result["000001"]
            self.assertEqual(["000001"], bars["code"].unique().tolist())
            self.assertIn("volume_ratio", bars.columns)
            self.assertIn("has_limit_up_20d", bars.columns)

    def test_fetch_a_share_bars_falls_back_to_tencent_history_when_akshare_history_fails(self):
        stock_list = pd.DataFrame([{"code": "000001", "name": "平安银行"}])
        tencent_payload = {
            "data": {
                "sz000001": {
                    "qfqday": [
                        ["2025-01-02", "10.00", "10.40", "10.50", "9.90", "100000"],
                        ["2025-01-03", "10.50", "10.70", "10.90", "10.30", "120000"],
                    ]
                }
            }
        }
        response = Mock()
        response.json.return_value = tencent_payload
        response.raise_for_status.return_value = None

        with patch("quant.real_data.ak.stock_info_a_code_name", return_value=stock_list), patch(
            "quant.real_data.ak.stock_zh_a_hist", side_effect=RuntimeError("akshare down")
        ), patch("quant.real_data.requests.get", return_value=response):
            result = fetch_a_share_bars("2025-01-02", "2025-01-03", max_symbols=1)

            self.assertEqual(["000001"], sorted(result))
            self.assertEqual(2, len(result["000001"]))

    def test_fetch_ranked_backtest_bars_uses_daily_ranked_pool_not_full_market_scan(self):
        strong_pool = pd.DataFrame(
            [
                {
                    "代码": "605305",
                    "名称": "中际联合",
                    "涨跌幅": 4.1,
                    "最新价": 42.76,
                    "成交额": 800000000,
                    "总市值": 8979000000,
                    "换手率": 5.41,
                    "量比": 2.4,
                    "是否新高": "是",
                },
                {
                    "代码": "300001",
                    "名称": "创业板示例",
                    "涨跌幅": 4.2,
                    "最新价": 11.0,
                    "成交额": 100000000,
                    "总市值": 8000000000,
                    "换手率": 6.0,
                    "量比": 2.0,
                    "是否新高": "是",
                },
                {
                    "代码": "600000",
                    "名称": "涨幅过高",
                    "涨跌幅": 6.0,
                    "最新价": 10.0,
                    "成交额": 100000000,
                    "总市值": 8000000000,
                    "换手率": 6.0,
                    "量比": 2.0,
                    "是否新高": "是",
                },
            ]
        )
        limit_up_pool = pd.DataFrame([{"代码": "605305", "名称": "中际联合"}])
        history = pd.DataFrame(
            [
                {
                    "日期": "2026-06-22",
                    "开盘": 41.0,
                    "收盘": 42.76,
                    "最高": 43.0,
                    "最低": 40.8,
                    "成交量": 1000000,
                    "成交额": 800000000,
                    "涨跌幅": 4.1,
                    "换手率": 5.41,
                },
                {
                    "日期": "2026-06-23",
                    "开盘": 43.0,
                    "收盘": 43.4,
                    "最高": 44.0,
                    "最低": 42.5,
                    "成交量": 900000,
                    "成交额": 780000000,
                    "涨跌幅": 1.5,
                    "换手率": 4.2,
                },
            ]
        )

        with patch(
            "quant.real_data.ak.stock_info_a_code_name",
            side_effect=AssertionError("回测不应该全市场逐股扫描"),
        ), patch("quant.real_data.ak.stock_zt_pool_strong_em", return_value=strong_pool) as ranked_pool, patch(
            "quant.real_data.ak.stock_zt_pool_em", return_value=limit_up_pool
        ), patch(
            "quant.real_data._fetch_daily_history", return_value=history
        ) as history_fetch:
            result = fetch_ranked_backtest_bars("2026-06-22", "2026-06-22", strategy_id="overnight_arbitrage")

            self.assertEqual(["600000", "605305"], sorted(result))
            self.assertEqual(1, ranked_pool.call_count)
            self.assertEqual(["605305", "600000"], [call.args[0] for call in history_fetch.call_args_list])
            signal_row = result["605305"].loc[pd.Timestamp(date(2026, 6, 22))]
            self.assertEqual(4.1, signal_row["pct_chg"])
            self.assertEqual(2.4, signal_row["volume_ratio"])
            self.assertGreaterEqual(signal_row["has_limit_up_20d"], 1)

    def test_fetch_ranked_backtest_bars_keeps_relaxed_pool_before_history_for_level_backtest(self):
        strong_pool = pd.DataFrame(
            [
                {
                    "代码": "605305",
                    "名称": "中际联合",
                    "涨跌幅": 4.1,
                    "最新价": 42.76,
                    "成交额": 800000000,
                    "总市值": 8979000000,
                    "换手率": 5.41,
                    "量比": 2.4,
                    "是否新高": "是",
                },
                {
                    "代码": "603000",
                    "名称": "无涨停基因",
                    "涨跌幅": 4.0,
                    "最新价": 18.0,
                    "成交额": 500000000,
                    "总市值": 9000000000,
                    "换手率": 6.0,
                    "量比": 2.0,
                    "是否新高": "是",
                },
                {
                    "代码": "603001",
                    "名称": "超过观察池",
                    "涨跌幅": 4.0,
                    "最新价": 18.0,
                    "成交额": 500000000,
                    "总市值": 9000000000,
                    "换手率": 13.0,
                    "量比": 2.0,
                    "是否新高": "是",
                },
            ]
        )
        limit_up_pool = pd.DataFrame([{"代码": "605305", "名称": "中际联合"}])
        history = pd.DataFrame(
            [
                {
                    "日期": "2026-06-22",
                    "开盘": 41.0,
                    "收盘": 42.76,
                    "最高": 43.0,
                    "最低": 40.8,
                    "成交量": 1000000,
                    "成交额": 800000000,
                    "涨跌幅": 4.1,
                    "换手率": 5.41,
                },
                {
                    "日期": "2026-06-23",
                    "开盘": 43.0,
                    "收盘": 43.4,
                    "最高": 44.0,
                    "最低": 42.5,
                    "成交量": 900000,
                    "成交额": 780000000,
                    "涨跌幅": 1.5,
                    "换手率": 4.2,
                },
            ]
        )

        with patch("quant.real_data.ak.stock_zt_pool_strong_em", return_value=strong_pool), patch(
            "quant.real_data.ak.stock_zt_pool_em", return_value=limit_up_pool
        ), patch("quant.real_data._fetch_daily_history", return_value=history) as history_fetch:
            result = fetch_ranked_backtest_bars("2026-06-22", "2026-06-22", strategy_id="overnight_arbitrage")

            self.assertEqual(["603000", "605305"], sorted(result))
            self.assertEqual(["605305", "603000"], [call.args[0] for call in history_fetch.call_args_list])

    def test_fetch_ranked_backtest_bars_uses_configured_c_level_range_before_history(self):
        strong_pool = pd.DataFrame(
            [
                {
                    "代码": "605305",
                    "名称": "中际联合",
                    "涨跌幅": 4.1,
                    "最新价": 42.76,
                    "成交额": 800000000,
                    "总市值": 8979000000,
                    "换手率": 5.41,
                    "量比": 2.4,
                    "是否新高": "是",
                },
                {
                    "代码": "603000",
                    "名称": "低于配置",
                    "涨跌幅": 2.5,
                    "最新价": 18.0,
                    "成交额": 500000000,
                    "总市值": 9000000000,
                    "换手率": 6.0,
                    "量比": 2.0,
                    "是否新高": "否",
                },
            ]
        )
        history = pd.DataFrame(
            [
                {
                    "日期": "2026-06-22",
                    "开盘": 41.0,
                    "收盘": 42.76,
                    "最高": 43.0,
                    "最低": 40.8,
                    "成交量": 1000000,
                    "成交额": 800000000,
                    "涨跌幅": 4.1,
                    "换手率": 5.41,
                },
                {
                    "日期": "2026-06-23",
                    "开盘": 43.0,
                    "收盘": 43.4,
                    "最高": 44.0,
                    "最低": 42.5,
                    "成交量": 900000,
                    "成交额": 780000000,
                    "涨跌幅": 1.5,
                    "换手率": 4.2,
                },
            ]
        )

        with patch("quant.real_data.ak.stock_zt_pool_strong_em", return_value=strong_pool), patch(
            "quant.real_data.ak.stock_zt_pool_em", return_value=pd.DataFrame()
        ), patch("quant.real_data._fetch_daily_history", return_value=history) as history_fetch:
            result = fetch_ranked_backtest_bars(
                "2026-06-22",
                "2026-06-22",
                strategy_id="overnight_arbitrage",
                strategy_config={"levels": {"C": {"min_pct_chg": 3.5}}},
            )

            self.assertEqual(["605305"], sorted(result))
            self.assertEqual(["605305"], [call.args[0] for call in history_fetch.call_args_list])


if __name__ == "__main__":
    unittest.main()
