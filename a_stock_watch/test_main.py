import json
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from main import (
    ALERT_TYPE_BELOW_ZONE,
    ALERT_TYPE_BUY_ZONE,
    DEFAULT_POSITION_STATE,
    WatchItem,
    build_wechat_markdown,
    determine_status,
    display_status,
    ensure_position_state,
    fetch_akshare_realtime_quotes,
    fetch_eastmoney_ulist_quotes,
    fetch_realtime_quotes,
    format_summary_line,
    is_trading_time,
    load_json_file,
    record_alert,
    should_alert,
    should_allow_alert,
    send_wechat_markdown,
)


class AStockWatchTest(unittest.TestCase):
    def test_trading_time_only_allows_a_share_sessions(self):
        tz = ZoneInfo("Asia/Shanghai")

        self.assertFalse(is_trading_time(datetime(2026, 6, 22, 9, 29, tzinfo=tz)))
        self.assertTrue(is_trading_time(datetime(2026, 6, 22, 9, 30, tzinfo=tz)))
        self.assertTrue(is_trading_time(datetime(2026, 6, 22, 11, 30, tzinfo=tz)))
        self.assertFalse(is_trading_time(datetime(2026, 6, 22, 11, 31, tzinfo=tz)))
        self.assertFalse(is_trading_time(datetime(2026, 6, 22, 12, 59, tzinfo=tz)))
        self.assertTrue(is_trading_time(datetime(2026, 6, 22, 13, 0, tzinfo=tz)))
        self.assertTrue(is_trading_time(datetime(2026, 6, 22, 15, 0, tzinfo=tz)))
        self.assertFalse(is_trading_time(datetime(2026, 6, 22, 15, 1, tzinfo=tz)))

    def test_determine_status_uses_buy_zone_bounds(self):
        item = WatchItem(
            name="沪电股份",
            code="002463.SZ",
            market="SZ",
            buy_low=142.0,
            buy_high=144.0,
            shares=100,
            type="AI_PCB核心",
            priority=1,
            enabled=True,
            note="",
        )

        self.assertEqual(determine_status(item, 143.2), "BUY_ZONE")
        self.assertEqual(determine_status(item, 144.1), "WAIT_PULLBACK")
        self.assertEqual(determine_status(item, 141.9), "BELOW_ZONE")

    def test_display_status_uses_chinese_labels(self):
        self.assertEqual(display_status("WAIT_PULLBACK"), "等待回落")
        self.assertEqual(display_status("RISK_BLOCKED"), "风险拦截")
        self.assertEqual(display_status("UNKNOWN_CUSTOM_STATUS"), "UNKNOWN_CUSTOM_STATUS")

    def test_summary_line_displays_chinese_status(self):
        item = WatchItem(
            name="沪电股份",
            code="002463.SZ",
            market="SZ",
            buy_low=142.0,
            buy_high=144.0,
            shares=100,
            type="AI_PCB核心",
            priority=1,
            enabled=True,
            note="",
        )
        quote = types.SimpleNamespace(
            name="沪电股份",
            latest_price=145.0,
            change_pct=1.23,
            amount=123456789,
        )
        now = datetime(2026, 6, 22, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        line = format_summary_line(now, item, quote, "WAIT_PULLBACK")
        missing_line = format_summary_line(now, item, None, "MISSING_QUOTE")

        self.assertIn("状态 等待回落", line)
        self.assertNotIn("WAIT_PULLBACK", line)
        self.assertIn("状态 无行情", missing_line)

    def test_alert_dependency_blocks_jingwang_when_hudian_bought(self):
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
            note="",
            depends_on_not_bought="002463.SZ",
        )
        positions = {
            "002463.SZ": {"name": "沪电股份", "bought": True},
            "603228.SH": {"name": "景旺电子", "bought": False},
        }

        self.assertFalse(should_allow_alert(item, positions))
        positions["002463.SZ"]["bought"] = False
        self.assertTrue(should_allow_alert(item, positions))

    def test_alert_state_dedupes_same_stock_type_and_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "alert_state.json"
            now = datetime(2026, 6, 22, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

            self.assertTrue(should_alert({}, "002463.SZ", ALERT_TYPE_BUY_ZONE, now))
            state = {}
            record_alert(path, state, "002463.SZ", ALERT_TYPE_BUY_ZONE, now)

            saved = load_json_file(path, {})
            self.assertFalse(should_alert(saved, "002463.SZ", ALERT_TYPE_BUY_ZONE, now))
            self.assertTrue(should_alert(saved, "002463.SZ", ALERT_TYPE_BELOW_ZONE, now))

    def test_ensure_position_state_creates_default_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "position_state.json"

            positions = ensure_position_state(path)

            self.assertEqual(positions, DEFAULT_POSITION_STATE)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), DEFAULT_POSITION_STATE)

    def test_wechat_markdown_contains_manual_confirmation_warning(self):
        item = WatchItem(
            name="沪电股份",
            code="002463.SZ",
            market="SZ",
            buy_low=142.0,
            buy_high=144.0,
            shares=100,
            type="AI_PCB核心",
            priority=1,
            enabled=True,
            note="优先买入",
        )

        message = build_wechat_markdown(item, 143.2, "BUY_ZONE")

        self.assertIn("【A股买点提醒】", message)
        self.assertIn("股票：沪电股份 002463.SZ", message)
        self.assertIn("预计金额：14320元", message)
        self.assertIn("这只是价格提醒，不是自动买入指令", message)

    def test_below_zone_markdown_warns_against_mechanical_buying(self):
        item = WatchItem(
            name="沪电股份",
            code="002463.SZ",
            market="SZ",
            buy_low=142.0,
            buy_high=144.0,
            shares=100,
            type="AI_PCB核心",
            priority=1,
            enabled=True,
            note="",
        )

        message = build_wechat_markdown(item, 141.0, "BELOW_ZONE")

        self.assertIn("跌破计划区间", message)
        self.assertIn("不能机械买入", message)
        self.assertIn("避免接飞刀", message)

    def test_send_wechat_markdown_posts_markdown_payload(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"errcode":0,"errmsg":"ok"}'

        with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            send_wechat_markdown("https://example.test/webhook", "**hello**")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/webhook")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertIn(b'"msgtype": "markdown"', request.data)
        self.assertIn(b'"content": "**hello**"', request.data)

    def test_akshare_field_error_includes_actual_columns(self):
        class FakeDataFrame:
            columns = ["代码", "名称", "现价"]

        fake_akshare = types.SimpleNamespace(stock_zh_a_spot_em=lambda: FakeDataFrame())

        with patch.dict(sys.modules, {"akshare": fake_akshare}):
            with self.assertRaisesRegex(RuntimeError, "实际字段名: \\[代码, 名称, 现价\\]"):
                fetch_akshare_realtime_quotes([])

    def test_eastmoney_ulist_quotes_parse_selected_symbols(self):
        item = WatchItem("沪电股份", "002463.SZ", "SZ", 142.0, 144.0, 100, "AI_PCB核心", 1, True)

        class FakeResponse:
            def json(self):
                return {
                    "rc": 0,
                    "data": {
                        "diff": [
                            {"f12": "002463", "f14": "沪电股份", "f2": 143.9, "f3": -2.7, "f6": 9906032525.2}
                        ]
                    },
                }

            def raise_for_status(self):
                return None

        with patch("requests.get", return_value=FakeResponse()) as get:
            quotes = fetch_eastmoney_ulist_quotes([item])

        self.assertEqual(quotes["002463"].name, "沪电股份")
        self.assertEqual(quotes["002463"].latest_price, 143.9)
        self.assertIn("secids", get.call_args.kwargs["params"])

    def test_realtime_quotes_falls_back_to_akshare_when_ulist_fails(self):
        item = WatchItem("沪电股份", "002463.SZ", "SZ", 142.0, 144.0, 100, "AI_PCB核心", 1, True)

        class FakeDataFrame:
            columns = ["代码", "名称", "最新价", "涨跌幅", "成交额"]

            def iterrows(self):
                yield 0, {"代码": "002463", "名称": "沪电股份", "最新价": 143.2, "涨跌幅": 1.2, "成交额": 123456}

        fake_akshare = types.SimpleNamespace(stock_zh_a_spot_em=lambda: FakeDataFrame())

        with patch("main.fetch_eastmoney_ulist_quotes", side_effect=RuntimeError("ulist failed")):
            with patch.dict(sys.modules, {"akshare": fake_akshare}):
                quotes = fetch_realtime_quotes([item])

        self.assertEqual(quotes["002463"].latest_price, 143.2)


if __name__ == "__main__":
    unittest.main()
