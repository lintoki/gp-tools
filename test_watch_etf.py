import unittest
from unittest.mock import patch

from watch_etf import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_WECHAT_WEBHOOK_URL,
    build_log_line,
    build_wechat_message,
    should_send_wechat,
    send_wechat_text,
)


class WatchEtfTest(unittest.TestCase):
    def test_default_interval_is_half_hour(self):
        self.assertEqual(DEFAULT_INTERVAL_SECONDS, 1800)

    def test_default_wechat_webhook_is_not_hard_coded(self):
        self.assertIsNone(DEFAULT_WECHAT_WEBHOOK_URL)

    def test_build_log_line_formats_expected_fields(self):
        row = {
            "代码": "159659",
            "名称": "纳指100ETF",
            "最新价": 1.234,
            "涨跌幅": 0.56,
            "成交额": 12345678.9,
            "IOPV实时估值": 1.22,
        }

        line = build_log_line(row)

        self.assertEqual(
            line,
            "159659 纳指100ETF | 现价 1.2340 | 涨跌 +0.56% | "
            "成交 1,234.57 万 | IOPV 1.2200 | 溢价 +1.15%",
        )

    def test_build_log_line_handles_missing_iopv(self):
        row = {
            "代码": "513650",
            "名称": "标普ETF",
            "最新价": 0.987,
            "涨跌幅": -1.23,
            "成交额": 0,
            "IOPV实时估值": "-",
        }

        line = build_log_line(row)

        self.assertIn("IOPV -", line)
        self.assertIn("溢价 -", line)

    def test_build_wechat_message_joins_lines(self):
        message = build_wechat_message(
            "2026-06-18 14:30:00",
            [
                "159659 纳斯达克100ETF招商 | 现价 2.3830",
                "513650 标普500ETF南方 | 现价 1.9110",
            ],
        )

        self.assertEqual(
            message,
            "ETF 实时行情\n"
            "时间：2026-06-18 14:30:00\n\n"
            "159659 纳斯达克100ETF招商 | 现价 2.3830\n"
            "513650 标普500ETF南方 | 现价 1.9110",
        )

    def test_send_wechat_text_posts_text_payload(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"errcode":0,"errmsg":"ok"}'

        with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            send_wechat_text("https://example.test/webhook", "hello")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/webhook")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertIn(b'"msgtype": "text"', request.data)
        self.assertIn(b'"content": "hello"', request.data)

    def test_should_send_wechat_respects_interval(self):
        self.assertTrue(should_send_wechat(None, 100.0, 1800))
        self.assertFalse(should_send_wechat(100.0, 1899.9, 1800))
        self.assertTrue(should_send_wechat(100.0, 1900.0, 1800))


if __name__ == "__main__":
    unittest.main()
