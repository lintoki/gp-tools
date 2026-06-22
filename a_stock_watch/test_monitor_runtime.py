import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from main import Quote, WatchItem
from monitor_runtime import build_quote_rows


class MonitorRuntimeTest(unittest.TestCase):
    def test_build_quote_rows_marks_position_blocked_alert(self):
        tz = ZoneInfo("Asia/Shanghai")
        item = WatchItem(
            name="景旺电子",
            code="603228.SH",
            market="SH",
            buy_low=74.5,
            buy_high=76.0,
            shares=100,
            type="PCB备选",
            priority=3,
            enabled=True,
            note="只有没买沪电股份时才提醒",
            depends_on_not_bought="002463.SZ",
        )
        quote = Quote(
            code="603228",
            name="景旺电子",
            latest_price=75.2,
            change_pct=1.23,
            amount=123456789,
        )
        positions = {
            "002463.SZ": {"name": "沪电股份", "bought": True},
            "603228.SH": {"name": "景旺电子", "bought": False},
        }

        rows = build_quote_rows(
            datetime(2026, 6, 22, 10, 0, tzinfo=tz),
            [item],
            {"603228": quote},
            positions,
        )

        self.assertEqual(rows[0]["status"], "BLOCKED_BY_POSITION")
        self.assertEqual(rows[0]["latest_price_text"], "75.20")
        self.assertEqual(rows[0]["amount_text"], "1.23亿")


if __name__ == "__main__":
    unittest.main()
