import unittest

from main import Quote, WatchItem
from fund_risk import (
    FinalAlert,
    FundFlowSnapshot,
    MarketRisk,
    SectorRisk,
    StockAcceptance,
    decide_final_alert,
    evaluate_market_risk,
    evaluate_sector_risk,
    extract_main_net_inflow_yi,
    display_label,
)


class FundRiskTest(unittest.TestCase):
    def test_market_risk_high_when_large_outflow_keeps_expanding(self):
        snapshot = FundFlowSnapshot(main_net_inflow_yi=-738.13, net_inflow_15m_delta_yi=-42.0, source="test")

        self.assertEqual(evaluate_market_risk(snapshot).level, MarketRisk.HIGH)

    def test_market_risk_unknown_when_fund_flow_missing(self):
        self.assertEqual(evaluate_market_risk(None).level, MarketRisk.UNKNOWN)

    def test_extract_market_fund_flow_uses_akshare_net_amount_field(self):
        class FakeILoc:
            def __getitem__(self, index):
                return {"主力净流入-净额": -73813000000}

        class FakeDataFrame:
            columns = ["日期", "主力净流入-净额"]
            iloc = FakeILoc()

        self.assertEqual(extract_main_net_inflow_yi(FakeDataFrame()), -738.13)

    def test_display_label_returns_chinese_for_internal_status(self):
        self.assertEqual(display_label("SECTOR_RISK_HIGH"), "板块高风险")
        self.assertEqual(display_label("RISK_BLOCKED"), "风险拦截")
        self.assertEqual(display_label("BUY_ZONE"), "进入区间")

    def test_sector_risk_high_when_ai_core_broadly_falls(self):
        quotes = {
            "601138": Quote("601138", "工业富联", 76.62, -3.1, 1),
            "002463": Quote("002463", "沪电股份", 142.49, -2.7, 1),
            "603228": Quote("603228", "景旺电子", 75.2, -2.8, 1),
            "002130": Quote("002130", "沃尔核材", 19.3, -3.3, 1),
            "300394": Quote("300394", "天孚通信", 90.0, -2.6, 1),
            "300502": Quote("300502", "新易盛", 100.0, -2.9, 1),
            "300308": Quote("300308", "中际旭创", 120.0, -3.0, 1),
            "300476": Quote("300476", "胜宏科技", 80.0, -2.7, 1),
            "688256": Quote("688256", "寒武纪", 500.0, 0.2, 1),
            "600183": Quote("600183", "生益科技", 30.0, -2.5, 1),
        }

        risk = evaluate_sector_risk(quotes)

        self.assertEqual(risk.level, SectorRisk.HIGH)
        self.assertEqual(risk.down_count, 9)

    def test_buy_zone_is_risk_blocked_under_high_market_or_sector_risk(self):
        item = WatchItem("沪电股份", "002463.SZ", "SZ", 142.0, 144.0, 100, "AI_PCB核心", 1, True)

        decision = decide_final_alert(
            item=item,
            price_status="BUY_ZONE",
            latest_price=142.49,
            market_risk=MarketRisk.HIGH,
            sector_risk=SectorRisk.HIGH,
            stock_acceptance=StockAcceptance.CONFIRMED,
        )

        self.assertEqual(decision, FinalAlert.RISK_BLOCKED)

    def test_buy_zone_is_watch_only_when_fund_flow_unknown(self):
        item = WatchItem("沪电股份", "002463.SZ", "SZ", 142.0, 144.0, 100, "AI_PCB核心", 1, True)

        decision = decide_final_alert(
            item=item,
            price_status="BUY_ZONE",
            latest_price=142.49,
            market_risk=MarketRisk.UNKNOWN,
            sector_risk=SectorRisk.LOW,
            stock_acceptance=StockAcceptance.CONFIRMED,
        )

        self.assertEqual(decision, FinalAlert.WATCH_ONLY)

    def test_buy_zone_confirmed_only_when_all_filters_pass(self):
        item = WatchItem("沪电股份", "002463.SZ", "SZ", 142.0, 144.0, 100, "AI_PCB核心", 1, True)

        decision = decide_final_alert(
            item=item,
            price_status="BUY_ZONE",
            latest_price=143.2,
            market_risk=MarketRisk.LOW,
            sector_risk=SectorRisk.LOW,
            stock_acceptance=StockAcceptance.CONFIRMED,
        )

        self.assertEqual(decision, FinalAlert.BUY_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
