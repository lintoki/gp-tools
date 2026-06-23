import unittest

from tail_trader.akshare_source import (
    dataframe_to_legacy_spot_snapshots,
    dataframe_to_daily_bars,
    dataframe_to_minute_bars,
    dataframe_to_spot_snapshots,
    eastmoney_diff_to_spot_snapshots,
    eastmoney_klines_to_daily_bars,
    eastmoney_trends_to_minute_bars,
)


class FakeDataFrame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        for index, row in enumerate(self.rows):
            yield index, row


class AkshareSourceTest(unittest.TestCase):
    def test_dataframe_to_spot_snapshots_maps_eastmoney_columns(self):
        df = FakeDataFrame(
            [
                {
                    "代码": "2123",
                    "名称": "测试股份",
                    "最新价": "12.45",
                    "涨跌幅": "4.2",
                    "量比": "1.6",
                    "换手率": "6.5",
                    "总市值": "12000000000",
                    "最高": "12.80",
                    "最低": "11.90",
                    "今开": "12.00",
                    "昨收": "11.95",
                    "成交额": "880000000",
                }
            ]
        )

        snapshots = dataframe_to_spot_snapshots(df)

        self.assertEqual(snapshots[0].code, "002123")
        self.assertEqual(snapshots[0].name, "测试股份")
        self.assertAlmostEqual(snapshots[0].change_pct, 4.2)
        self.assertAlmostEqual(snapshots[0].total_market_value_yuan, 12_000_000_000)

    def test_dataframe_to_legacy_spot_snapshots_maps_sina_columns(self):
        df = FakeDataFrame(
            [
                {
                    "代码": "sh600060",
                    "名称": "海信视像",
                    "最新价": "25.36",
                    "涨跌幅": "3.555",
                    "最高": "25.68",
                    "最低": "24.44",
                    "今开": "24.59",
                    "昨收": "24.47",
                    "成交额": "441587794",
                }
            ]
        )

        snapshots = dataframe_to_legacy_spot_snapshots(df)

        self.assertEqual(snapshots[0].code, "600060")
        self.assertEqual(snapshots[0].name, "海信视像")
        self.assertAlmostEqual(snapshots[0].change_pct, 3.555)
        self.assertIsNone(snapshots[0].volume_ratio)

    def test_eastmoney_diff_to_spot_snapshots_maps_raw_fields(self):
        snapshots = eastmoney_diff_to_spot_snapshots(
            [
                {
                    "f2": 12.45,
                    "f3": 4.2,
                    "f6": 880000000,
                    "f8": 6.5,
                    "f10": 1.6,
                    "f12": "002123",
                    "f14": "测试股份",
                    "f15": 12.80,
                    "f16": 11.90,
                    "f17": 12.00,
                    "f18": 11.95,
                    "f20": 12000000000,
                }
            ]
        )

        self.assertEqual(snapshots[0].code, "002123")
        self.assertEqual(snapshots[0].name, "测试股份")
        self.assertAlmostEqual(snapshots[0].volume_ratio, 1.6)
        self.assertAlmostEqual(snapshots[0].turnover_pct, 6.5)

    def test_dataframe_to_daily_bars_maps_history_columns(self):
        df = FakeDataFrame(
            [
                {
                    "日期": "2026-06-20",
                    "开盘": "10.00",
                    "最高": "11.00",
                    "最低": "9.90",
                    "收盘": "10.80",
                    "涨跌幅": "9.98",
                    "换手率": "6.20",
                }
            ]
        )

        bars = dataframe_to_daily_bars(df)

        self.assertEqual(bars[0].date, "2026-06-20")
        self.assertAlmostEqual(bars[0].change_pct, 9.98)
        self.assertAlmostEqual(bars[0].turnover_pct, 6.2)

    def test_eastmoney_klines_to_daily_bars_maps_raw_klines(self):
        bars = eastmoney_klines_to_daily_bars(
            ["2026-06-20,10.00,10.80,11.00,9.90,1000,1080000,11.00,9.98,0.98,6.20"]
        )

        self.assertEqual(bars[0].date, "2026-06-20")
        self.assertAlmostEqual(bars[0].open, 10.0)
        self.assertAlmostEqual(bars[0].close, 10.8)
        self.assertAlmostEqual(bars[0].change_pct, 9.98)
        self.assertAlmostEqual(bars[0].turnover_pct, 6.2)

    def test_dataframe_to_minute_bars_maps_intraday_columns(self):
        df = FakeDataFrame(
            [
                {
                    "时间": "2026-06-23 14:55:00",
                    "开盘": "12.18",
                    "最高": "12.46",
                    "最低": "12.16",
                    "收盘": "12.44",
                    "成交量": "1800",
                    "成交额": "22300000",
                    "均价": "12.12",
                }
            ]
        )

        bars = dataframe_to_minute_bars(df)

        self.assertEqual(bars[0].time, "2026-06-23 14:55:00")
        self.assertAlmostEqual(bars[0].close, 12.44)
        self.assertAlmostEqual(bars[0].avg_price, 12.12)

    def test_eastmoney_trends_to_minute_bars_filters_by_date(self):
        bars = eastmoney_trends_to_minute_bars(
            [
                "2026-06-22 14:55,12.00,12.10,12.20,11.90,100,121000,12.05",
                "2026-06-23 14:55,12.18,12.44,12.46,12.16,1800,22300000,12.12",
            ],
            trading_date="2026-06-23",
        )

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].time, "2026-06-23 14:55:00")
        self.assertAlmostEqual(bars[0].close, 12.44)
        self.assertAlmostEqual(bars[0].avg_price, 12.12)


if __name__ == "__main__":
    unittest.main()
