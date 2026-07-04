import unittest
from pathlib import Path


class StaticOutputUiTest(unittest.TestCase):
    def setUp(self):
        self.html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")

    def test_signal_output_uses_abc_modules_with_observation_lists(self):
        self.assertIn("function renderCandidateModules", self.html)
        self.assertIn("abc-grid", self.html)
        self.assertIn("abc-module", self.html)
        self.assertIn("function renderNearMisses", self.html)
        self.assertIn("function renderRejections", self.html)
        self.assertIn("接近标准观察池", self.html)
        self.assertIn("剔除原因", self.html)
        self.assertIn("data.rejected", self.html)
        self.assertIn("data.rejections", self.html)

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
