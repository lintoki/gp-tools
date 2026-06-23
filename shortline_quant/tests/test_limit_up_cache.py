import tempfile
import unittest
from pathlib import Path

from quant.realtime_screener import LimitUpCache


class LimitUpCacheTest(unittest.TestCase):
    def test_count_recent_uses_latest_20_trade_dates_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = LimitUpCache(Path(tmp) / "limit_up_cache.csv")
            for day in range(1, 23):
                trade_date = f"2026-05-{day:02d}"
                rows = [
                    {
                        "code": "000001",
                        "name": "示例一",
                        "trade_date": trade_date,
                        "close_price": 10.0,
                        "limit_up_price": 11.0,
                        "limit_up_reason": "",
                    }
                ]
                if day >= 5:
                    rows.append(
                        {
                            "code": "000002",
                            "name": "示例二",
                            "trade_date": trade_date,
                            "close_price": 20.0,
                            "limit_up_price": 22.0,
                            "limit_up_reason": "",
                        }
                    )
                cache.replace_trade_date(trade_date, rows)

            result = cache.count_recent(["000001", "000002", "000003"], "2026-05-22", lookback=20)

            self.assertEqual(20, result["000001"])
            self.assertEqual(18, result["000002"])
            self.assertEqual(0, result["000003"])


if __name__ == "__main__":
    unittest.main()
