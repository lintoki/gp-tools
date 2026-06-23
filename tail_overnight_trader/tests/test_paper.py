import tempfile
import unittest
from pathlib import Path

from tail_trader.models import MinuteBar, PaperTrade
from tail_trader.paper import (
    append_trade,
    build_review_markdown,
    decide_morning_exit,
    load_trades,
)


class PaperTradeTest(unittest.TestCase):
    def test_decide_morning_exit_hits_profit_target_before_timeout(self):
        trade = PaperTrade(
            trade_id="20260623-002123",
            code="002123",
            name="测试股份",
            entry_date="2026-06-23",
            entry_time="14:55:00",
            entry_price=10.0,
            shares=100,
            status="OPEN",
            strategy="tail_overnight",
            notes=["测试入选"],
        )
        next_day_bars = [
            MinuteBar("2026-06-24 09:31:00", 10.08, 10.10, 10.02, 10.05, 1000, 10_050_000, 10.05),
            MinuteBar("2026-06-24 09:38:00", 10.12, 10.25, 10.10, 10.21, 1500, 15_300_000, 10.12),
        ]

        result = decide_morning_exit(trade, next_day_bars, target_profit_pct=2.0, stop_loss_pct=2.0)

        self.assertEqual(result.exit_reason, "TARGET_HIT")
        self.assertAlmostEqual(result.exit_price, 10.2)
        self.assertAlmostEqual(result.return_pct, 2.0)

    def test_decide_morning_exit_times_out_at_last_morning_price(self):
        trade = PaperTrade(
            trade_id="20260623-002123",
            code="002123",
            name="测试股份",
            entry_date="2026-06-23",
            entry_time="14:55:00",
            entry_price=10.0,
            shares=100,
            status="OPEN",
            strategy="tail_overnight",
            notes=[],
        )
        next_day_bars = [
            MinuteBar("2026-06-24 09:31:00", 10.01, 10.05, 9.99, 10.03, 1000, 10_030_000, 10.02),
            MinuteBar("2026-06-24 10:30:00", 10.05, 10.08, 10.00, 10.06, 1000, 10_060_000, 10.04),
        ]

        result = decide_morning_exit(trade, next_day_bars, target_profit_pct=2.0, stop_loss_pct=2.0)

        self.assertEqual(result.exit_reason, "MORNING_TIMEOUT")
        self.assertAlmostEqual(result.exit_price, 10.06)
        self.assertAlmostEqual(result.return_pct, 0.6)

    def test_trade_store_appends_jsonl_and_review_markdown_summarizes_result(self):
        trade = PaperTrade(
            trade_id="20260623-002123",
            code="002123",
            name="测试股份",
            entry_date="2026-06-23",
            entry_time="14:55:00",
            entry_price=10.0,
            shares=100,
            status="OPEN",
            strategy="tail_overnight",
            notes=["涨幅达标"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trades.jsonl"
            append_trade(path, trade)
            trades = load_trades(path)

        self.assertEqual(trades, [trade])
        markdown = build_review_markdown(
            review_date="2026-06-24",
            results=[
                decide_morning_exit(
                    trade,
                    [
                        MinuteBar(
                            "2026-06-24 09:35:00",
                            10.10,
                            10.22,
                            10.09,
                            10.20,
                            1000,
                            10_200_000,
                            10.10,
                        )
                    ],
                    target_profit_pct=2.0,
                    stop_loss_pct=2.0,
                )
            ],
        )

        self.assertIn("# 尾盘隔夜策略复盘 2026-06-24", markdown)
        self.assertIn("| 002123 | 测试股份 | 10.000 | 10.200 | +2.00% | TARGET_HIT |", markdown)

    def test_append_trade_keeps_latest_ten_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trades.jsonl"
            for index in range(12):
                append_trade(
                    path,
                    PaperTrade(
                        trade_id=f"20260623-00{index:04d}",
                        code=f"{index:06d}",
                        name=f"测试{index}",
                        entry_date="2026-06-23",
                        entry_time="14:55:00",
                        entry_price=10.0 + index,
                        shares=100,
                        status="OPEN",
                        strategy="tail_overnight",
                        notes=[],
                    ),
                )
            trades = load_trades(path)

        self.assertEqual(len(trades), 10)
        self.assertEqual(trades[0].code, "000002")
        self.assertEqual(trades[-1].code, "000011")


if __name__ == "__main__":
    unittest.main()
