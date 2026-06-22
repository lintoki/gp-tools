import tempfile
import unittest
from pathlib import Path

from web_config import (
    build_watch_item_payload,
    import_watchlist_csv,
    import_watchlist_json,
    mask_webhook_url,
    normalize_stock_code,
    save_settings,
    load_settings,
)


class WebConfigTest(unittest.TestCase):
    def test_normalize_stock_code_infers_exchange_suffix(self):
        self.assertEqual(normalize_stock_code("2463"), "002463.SZ")
        self.assertEqual(normalize_stock_code("601138"), "601138.SH")
        self.assertEqual(normalize_stock_code("603228.sh"), "603228.SH")

    def test_build_watch_item_payload_accepts_single_price(self):
        payload = build_watch_item_payload(
            {
                "name": "测试股票",
                "code": "600900",
                "price": "21.8",
                "shares": "200",
                "type": "防守仓",
                "note": "本地测试",
            },
            priority=3,
        )

        self.assertEqual(payload["code"], "600900.SH")
        self.assertEqual(payload["market"], "SH")
        self.assertEqual(payload["buy_low"], 21.8)
        self.assertEqual(payload["buy_high"], 21.8)
        self.assertEqual(payload["shares"], 200)
        self.assertTrue(payload["enabled"])

    def test_build_watch_item_payload_accepts_price_range(self):
        payload = build_watch_item_payload(
            {
                "name": "沪电股份",
                "code": "002463.SZ",
                "buy_low": "142",
                "buy_high": "144",
                "shares": "100",
            },
            priority=1,
        )

        self.assertEqual(payload["buy_low"], 142.0)
        self.assertEqual(payload["buy_high"], 144.0)

    def test_import_watchlist_csv_parses_header_rows(self):
        content = (
            "name,code,buy_low,buy_high,shares,type,note\n"
            "沪电股份,002463.SZ,142,144,100,AI_PCB核心,优先买入\n"
            "长江电力,600900,21.5,21.8,200,防守仓,防守配置\n"
        )

        items = import_watchlist_csv(content, start_priority=10)

        self.assertEqual([item["code"] for item in items], ["002463.SZ", "600900.SH"])
        self.assertEqual(items[0]["priority"], 10)
        self.assertEqual(items[1]["priority"], 11)

    def test_import_watchlist_json_parses_watchlist_object(self):
        content = """
        {
          "watchlist": [
            {"name": "沪电股份", "code": "002463.SZ", "buy_low": 142, "buy_high": 144, "shares": 100},
            {"name": "长江电力", "code": "600900", "price": 21.8, "shares": 200}
          ]
        }
        """

        items = import_watchlist_json(content, start_priority=20)

        self.assertEqual([item["code"] for item in items], ["002463.SZ", "600900.SH"])
        self.assertEqual(items[0]["priority"], 20)
        self.assertEqual(items[1]["buy_low"], 21.8)

    def test_settings_round_trip_and_webhook_mask(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            save_settings(path, {"wechat_webhook_url": "https://example.test/send?key=abcdef123456"})

            settings = load_settings(path)

            self.assertEqual(settings["wechat_webhook_url"], "https://example.test/send?key=abcdef123456")
            self.assertEqual(mask_webhook_url(settings["wechat_webhook_url"]), "https://example.test/send?key=abcd...3456")


if __name__ == "__main__":
    unittest.main()
