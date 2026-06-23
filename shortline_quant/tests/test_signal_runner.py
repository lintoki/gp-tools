import tempfile
import unittest
from pathlib import Path

from quant.data_source import ensure_sample_data, load_daily_bars
from quant.registry import StrategyRegistry
from quant.signal_runner import SignalRunner


class SignalRunnerTest(unittest.TestCase):
    def test_scan_latest_outputs_strategy_signals_with_advice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_sample_data(root / "data")
            bars = load_daily_bars(root / "data", "DEMO1")
            runner = SignalRunner(StrategyRegistry.load_builtin())

            result = runner.scan(
                strategy_id="overnight_arbitrage",
                bars_by_symbol={"DEMO1": bars},
                params={},
            )

            self.assertEqual("overnight_arbitrage", result["strategy_id"])
            self.assertGreater(len(result["signals"]), 0)
            signal = result["signals"][0]
            self.assertEqual("DEMO1", signal["symbol"])
            self.assertEqual("buy_watch", signal["action"])
            self.assertIn("trigger_reason", signal)
            self.assertIn("具体操作", signal["operation_advice"])
            self.assertIn("只做提醒", signal["operation_advice"])


if __name__ == "__main__":
    unittest.main()
