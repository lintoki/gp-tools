import unittest
from pathlib import Path


class StaticOutputUiTest(unittest.TestCase):
    def setUp(self):
        self.html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")

    def test_signal_output_uses_abc_modules_without_unmatched_lists(self):
        self.assertIn("function renderCandidateModules", self.html)
        self.assertIn("abc-grid", self.html)
        self.assertIn("abc-module", self.html)
        self.assertNotIn("renderNearMisses", self.html)
        self.assertNotIn("renderRejections", self.html)
        self.assertNotIn("data.rejected", self.html)
        self.assertNotIn("data.rejections", self.html)

    def test_backtest_time_filter_defaults_to_recent_week(self):
        self.assertIn('id="quickRange"', self.html)
        self.assertIn('value="7"', self.html)
        self.assertIn("applyQuickRange(7)", self.html)
        self.assertIn("setDate(end.getDate() - days)", self.html)
        self.assertNotIn("setMonth(end.getMonth() - 1)", self.html)

    def test_backtest_candidates_open_trade_detail_overlay_and_modal(self):
        self.assertIn("let lastBacktestTrades = []", self.html)
        self.assertIn("class=\"trade-trigger\"", self.html)
        self.assertIn("data-trade-index", self.html)
        self.assertIn("class=\"trade-popover\"", self.html)
        self.assertIn("function renderTradeHover", self.html)
        self.assertIn("function renderTradeDetailModal", self.html)
        self.assertIn("function openTradeDetail", self.html)
        self.assertIn("result.addEventListener('click'", self.html)
        self.assertIn("result.addEventListener('keydown'", self.html)


if __name__ == "__main__":
    unittest.main()
