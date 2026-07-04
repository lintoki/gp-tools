import unittest
from unittest import mock

import news_audit


class BuiltinAshareCollectorTests(unittest.TestCase):
    def test_fetch_url_text_falls_back_to_curl_when_urlopen_fails(self):
        with mock.patch.object(news_audit, "urlopen", side_effect=OSError("blocked")):
            with mock.patch.object(news_audit, "run_cmd", return_value=(0, "ok", "")) as fake_run:
                self.assertEqual(news_audit.fetch_url_text("https://example.test/data"), "ok")
        self.assertEqual(fake_run.call_args.args[0][0], "curl.exe")

    def test_builtin_collectors_cover_core_sources_without_stock_home(self):
        def fake_fetch(url, headers=None, timeout=20):
            if "suggest/get" in url:
                return """
                {"QuotationCodeTable":{"Data":[{"Code":"600667","Name":"太极实业","QuoteID":"1.600667","MarketType":"1"}]}}
                """
            if "np-anotice-stock.eastmoney.com" in url:
                return """
                {"data":{"list":[
                  {"title":"太极实业:股票交易异常波动公告","notice_date":"2026-06-26 00:00:00","art_code":"AN1"},
                  {"title":"太极实业:2025年年度权益分派实施公告","notice_date":"2026-06-23 00:00:00","art_code":"AN2"}
                ]},"success":1}
                """
            if "hq.sinajs.cn" in url:
                return 'var hq_str_sh600667="太极实业,28.310,28.890,29.960,31.000,27.180,29.960,29.970,407863159,11894094083.000,1274694,29.960,320400,29.950,138300,29.940,56100,29.930,3200,29.920,22900,29.970,42300,29.980,33700,29.990,509125,30.000,27500,30.010,2026-07-03,15:00:01,00,";'
            if "kline/get" in url:
                return """
                {"data":{"klines":[
                  "2026-06-18,19.00,20.86,20.86,19.00,100000,100000000,10.00,10.02,1.90,5.00",
                  "2026-07-01,29.18,32.10,32.10,29.18,500000,12988000000,10.00,10.01,2.92,20.00",
                  "2026-07-03,28.31,29.96,31.00,27.18,4078631,11894094083,13.22,3.70,1.07,19.50"
                ]}}
                """
            if "market-news" in url:
                return '{"items":[{"title":"太极实业近期股价异动引发市场关注","time":"2026-07-03","url":"https://example.test/news"}]}'
            if "flash-news" in url:
                return '{"items":[{"title":"快讯：太极实业成交额显著放大","time":"2026-07-03","url":"https://example.test/flash"}]}'
            return ""

        items, missing = news_audit.collect_builtin_sources("太极实业", "A", fetch_text=fake_fetch)
        pack = news_audit.compute_pack("太极实业", "A", news_audit.dedupe(items), missing)

        self.assertEqual(pack["source_coverage"]["official_disclosure"], "covered")
        self.assertEqual(pack["source_coverage"]["market_news"], "covered")
        self.assertEqual(pack["source_coverage"]["flash_news"], "covered")
        self.assertEqual(pack["source_coverage"]["price_volume_anomaly"], "covered")
        self.assertNotEqual(pack["evidence_status"], "BLOCK")
        self.assertGreater(pack["coverage_score"], 40)

    def test_builtin_collectors_emit_price_volume_anomaly_from_kline(self):
        def fake_fetch(url, headers=None, timeout=20):
            if "suggest/get" in url:
                return '{"QuotationCodeTable":{"Data":[{"Code":"600667","Name":"太极实业","QuoteID":"1.600667","MarketType":"1"}]}}'
            if "np-anotice-stock.eastmoney.com" in url:
                return '{"data":{"list":[{"title":"太极实业:股票交易异常波动公告","notice_date":"2026-06-26 00:00:00","art_code":"AN1"}]},"success":1}'
            if "hq.sinajs.cn" in url:
                return 'var hq_str_sh600667="太极实业,28.310,28.890,29.960,31.000,27.180,29.960,29.970,407863159,11894094083.000,1274694,29.960,320400,29.950,138300,29.940,56100,29.930,3200,29.920,22900,29.970,42300,29.980,33700,29.990,509125,30.000,27500,30.010,2026-07-03,15:00:01,00,";'
            if "kline/get" in url:
                return '{"data":{"klines":["2026-06-18,19.00,20.86,20.86,19.00,100000,100000000,10.00,10.02,1.90,5.00","2026-07-03,28.31,29.96,31.00,27.18,4078631,11894094083,13.22,3.70,1.07,19.50"]}}'
            return '{"items":[]}'

        items, missing = news_audit.collect_builtin_sources("600667", "A", fetch_text=fake_fetch)
        pack = news_audit.compute_pack("600667", "A", news_audit.dedupe(items), missing)

        self.assertTrue(pack["price_volume_anomalies"])
        self.assertTrue(any("kline" in item["source"] for item in items))

    def test_sina_quote_can_emit_structured_anomaly_when_kline_fails(self):
        def fake_fetch(url, headers=None, timeout=20):
            if "suggest/get" in url:
                return '{"QuotationCodeTable":{"Data":[{"Code":"600667","Name":"太极实业","QuoteID":"1.600667","MarketType":"1"}]}}'
            if "np-anotice-stock.eastmoney.com" in url:
                return '{"data":{"list":[{"title":"太极实业:股票交易异常波动公告","notice_date":"2026-06-26 00:00:00","art_code":"AN1"}]},"success":1}'
            if "hq.sinajs.cn" in url:
                return 'var hq_str_sh600667="太极实业,28.310,28.890,29.960,31.000,27.180,29.960,29.970,407863159,11894094083.000,1274694,29.960,320400,29.950,138300,29.940,56100,29.930,3200,29.920,22900,29.970,42300,29.980,33700,29.990,509125,30.000,27500,30.010,2026-07-03,15:00:01,00,";'
            if "kline/get" in url:
                raise OSError("remote closed")
            return '{"items":[]}'

        items, missing = news_audit.collect_builtin_sources("600667", "A", fetch_text=fake_fetch)
        pack = news_audit.compute_pack("600667", "A", news_audit.dedupe(items), missing)

        self.assertTrue(any("eastmoney_kline failed" in item for item in missing))
        self.assertTrue(
            any(anomaly.get("source") == "price_volume:sina_quote" for anomaly in pack["price_volume_anomalies"])
        )


if __name__ == "__main__":
    unittest.main()
