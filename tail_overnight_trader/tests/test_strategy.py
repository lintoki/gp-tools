import unittest

from tail_trader.models import DailyBar, MarketSnapshot, MinuteBar, StrategyConfig
from tail_trader.strategy import evaluate_candidate, screen_market


def passing_snapshot(code: str = "002123") -> MarketSnapshot:
    return MarketSnapshot(
        code=code,
        name="测试股份",
        latest_price=12.45,
        change_pct=4.2,
        volume_ratio=1.6,
        turnover_pct=6.5,
        total_market_value_yuan=12_000_000_000,
        high_price=12.8,
        low_price=11.9,
        open_price=12.0,
        prev_close=11.95,
        amount_yuan=880_000_000,
    )


def passing_daily_bars() -> list[DailyBar]:
    bars: list[DailyBar] = []
    close = 10.0
    for index in range(30):
        change_pct = 1.0
        if index == 16:
            change_pct = 10.02
        close = close * (1 + change_pct / 100)
        bars.append(
            DailyBar(
                date=f"2026-05-{index + 1:02d}",
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                change_pct=change_pct,
                turnover_pct=6.0,
            )
        )
    return bars


def passing_minute_bars() -> list[MinuteBar]:
    bars = [
        MinuteBar("2026-06-23 14:20:00", 12.08, 12.12, 12.06, 12.10, 1000, 12_100_000, 12.00),
        MinuteBar("2026-06-23 14:30:00", 12.18, 12.30, 12.16, 12.28, 1200, 14_700_000, 12.04),
        MinuteBar("2026-06-23 14:38:00", 12.28, 12.55, 12.26, 12.50, 1400, 17_500_000, 12.08),
        MinuteBar("2026-06-23 14:46:00", 12.50, 12.52, 12.11, 12.18, 1500, 18_200_000, 12.10),
        MinuteBar("2026-06-23 14:55:00", 12.18, 12.46, 12.16, 12.44, 1800, 22_300_000, 12.12),
    ]
    return bars


class StrategyTest(unittest.TestCase):
    def test_candidate_passes_when_all_tail_overnight_rules_match(self):
        report = evaluate_candidate(
            passing_snapshot(),
            passing_daily_bars(),
            passing_minute_bars(),
            market_change_pct=0.8,
            config=StrategyConfig(),
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.code, "002123")
        self.assertAlmostEqual(report.entry_price, 12.45)
        self.assertGreater(report.score, 0)
        self.assertIn("涨幅 4.20% 在 3.00%-5.00%", report.pass_reasons)
        self.assertIn("近 20 日涨停次数 1", report.pass_reasons)
        self.assertIn("尾盘创日内新高后回踩均价线不破", report.pass_reasons)
        self.assertEqual(report.fail_reasons, [])

    def test_candidate_rejects_non_main_board_and_bad_turnover(self):
        snapshot = passing_snapshot(code="300123")
        snapshot = MarketSnapshot(
            **{
                **snapshot.__dict__,
                "turnover_pct": 12.0,
            }
        )

        report = evaluate_candidate(
            snapshot,
            passing_daily_bars(),
            passing_minute_bars(),
            market_change_pct=0.8,
            config=StrategyConfig(),
        )

        self.assertFalse(report.passed)
        self.assertIn("非主板股票", report.fail_reasons)
        self.assertIn("换手率 12.00% 不在 5.00%-10.00%", report.fail_reasons)

    def test_candidate_rejects_missing_intraday_pullback(self):
        minute_bars = [
            MinuteBar("2026-06-23 14:20:00", 12.08, 12.12, 12.06, 12.10, 1000, 12_100_000, 12.00),
            MinuteBar("2026-06-23 14:35:00", 12.18, 12.70, 12.18, 12.68, 1200, 15_200_000, 12.03),
            MinuteBar("2026-06-23 14:55:00", 12.68, 12.80, 12.62, 12.78, 1500, 19_000_000, 12.05),
        ]

        report = evaluate_candidate(
            passing_snapshot(),
            passing_daily_bars(),
            minute_bars,
            market_change_pct=0.8,
            config=StrategyConfig(),
        )

        self.assertFalse(report.passed)
        self.assertIn("尾盘未出现贴近均价线的回踩", report.fail_reasons)

    def test_screen_market_returns_passed_reports_sorted_by_score(self):
        first = passing_snapshot("002111")
        second = MarketSnapshot(
            **{
                **passing_snapshot("600222").__dict__,
                "change_pct": 4.9,
                "volume_ratio": 2.4,
            }
        )

        reports = screen_market(
            snapshots=[first, second, passing_snapshot("688333")],
            daily_bars_by_code={
                "002111": passing_daily_bars(),
                "600222": passing_daily_bars(),
                "688333": passing_daily_bars(),
            },
            minute_bars_by_code={
                "002111": passing_minute_bars(),
                "600222": passing_minute_bars(),
                "688333": passing_minute_bars(),
            },
            market_change_pct=0.8,
            config=StrategyConfig(),
            passed_only=True,
        )

        self.assertEqual([report.code for report in reports], ["600222", "002111"])


if __name__ == "__main__":
    unittest.main()
