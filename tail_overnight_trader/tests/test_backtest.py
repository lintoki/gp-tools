import unittest

from tail_trader.backtest import build_backtest_html, run_backtest
from tail_trader.models import DailyBar, MarketSnapshot, MinuteBar


def passing_snapshot(code: str = "002123") -> MarketSnapshot:
    return MarketSnapshot(
        code=code,
        name="测试股份",
        latest_price=10.0,
        change_pct=4.0,
        volume_ratio=1.4,
        turnover_pct=6.2,
        total_market_value_yuan=8_000_000_000,
        high_price=10.3,
        low_price=9.7,
        open_price=9.8,
        prev_close=9.62,
        amount_yuan=500_000_000,
    )


def passing_daily_bars() -> list[DailyBar]:
    bars: list[DailyBar] = []
    close = 8.0
    for index in range(30):
        change_pct = 1.0
        if index == 15:
            change_pct = 10.0
        close = close * (1 + change_pct / 100)
        bars.append(
            DailyBar(
                date=f"2025-12-{index + 1:02d}",
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                change_pct=change_pct,
                turnover_pct=6.0,
            )
        )
    return bars


def passing_entry_minutes(trading_date: str) -> list[MinuteBar]:
    return [
        MinuteBar(f"{trading_date} 14:20:00", 9.86, 9.93, 9.85, 9.91, 1000, 9_910_000, 9.80),
        MinuteBar(f"{trading_date} 14:30:00", 9.92, 10.08, 9.94, 10.05, 1200, 12_060_000, 9.86),
        MinuteBar(f"{trading_date} 14:38:00", 10.05, 10.30, 10.04, 10.25, 1400, 14_350_000, 9.90),
        MinuteBar(f"{trading_date} 14:46:00", 10.25, 10.26, 9.95, 9.98, 1500, 14_970_000, 9.95),
        MinuteBar(f"{trading_date} 14:55:00", 9.98, 10.18, 9.96, 10.00, 1800, 18_000_000, 9.98),
    ]


def target_hit_minutes(trading_date: str) -> list[MinuteBar]:
    return [
        MinuteBar(f"{trading_date} 09:31:00", 10.02, 10.08, 9.99, 10.05, 1000, 10_050_000, 10.03),
        MinuteBar(f"{trading_date} 09:40:00", 10.08, 10.25, 10.06, 10.20, 1200, 12_240_000, 10.12),
    ]


class FakeProvider:
    def __init__(self, minute_error: bool = False):
        self.minute_error = minute_error

    def trading_dates_between(self, start_date: str, end_date: str) -> list[str]:
        return ["2026-01-05"]

    def snapshots_for_date(self, trading_date: str) -> list[MarketSnapshot]:
        return [passing_snapshot()]

    def daily_bars(self, code: str, start_date: str, end_date: str) -> list[DailyBar]:
        return passing_daily_bars()

    def minute_bars(self, code: str, trading_date: str) -> list[MinuteBar]:
        if self.minute_error and trading_date == "2026-01-05":
            raise RuntimeError("历史 1 分钟分时不可用")
        if trading_date == "2026-01-06":
            return target_hit_minutes(trading_date)
        return passing_entry_minutes(trading_date)

    def next_trading_date(self, trading_date: str) -> str:
        return "2026-01-06"


class BacktestTest(unittest.TestCase):
    def test_run_backtest_closes_passed_candidate_next_morning(self):
        report = run_backtest(FakeProvider(), "2026-01-01", "2026-01-07", shares=100)

        self.assertEqual(report.summary["trading_days"], 1)
        self.assertEqual(report.summary["closed_trades"], 1)
        self.assertEqual(report.summary["win_rate_pct"], 100.0)
        self.assertEqual(report.days[0].status, "TRADED")
        self.assertEqual(report.days[0].trades[0].exit_reason, "TARGET_HIT")
        self.assertEqual(report.days[0].trades[0].return_pct, 2.0)

    def test_run_backtest_marks_day_unavailable_when_strict_intraday_data_is_missing(self):
        report = run_backtest(FakeProvider(minute_error=True), "2026-01-01", "2026-01-07")

        self.assertEqual(report.summary["closed_trades"], 0)
        self.assertEqual(report.summary["unavailable_days"], 1)
        self.assertEqual(report.days[0].status, "DATA_UNAVAILABLE")
        self.assertIn("历史 1 分钟分时不可用", report.days[0].messages[0])

    def test_build_backtest_html_contains_summary_and_day_status(self):
        report = run_backtest(FakeProvider(), "2026-01-01", "2026-01-07", shares=100)

        html = build_backtest_html(report)

        self.assertIn("<!doctype html>", html)
        self.assertIn("策略回测", html)
        self.assertIn("2026-01-01 至 2026-01-07", html)
        self.assertIn("TARGET_HIT", html)


if __name__ == "__main__":
    unittest.main()
