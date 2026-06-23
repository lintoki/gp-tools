import unittest
from unittest.mock import Mock, patch

import pandas as pd

from quant.real_data import fetch_a_share_bars


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


if __name__ == "__main__":
    unittest.main()
