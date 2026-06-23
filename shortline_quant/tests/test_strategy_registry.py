import unittest

from quant.registry import StrategyRegistry


class StrategyRegistryTest(unittest.TestCase):
    def test_builtin_registry_exposes_two_tail_trading_strategies(self):
        registry = StrategyRegistry.load_builtin()

        strategies = registry.list_specs()
        strategy_ids = {item["strategy_id"] for item in strategies}

        self.assertIn("overnight_arbitrage", strategy_ids)
        self.assertIn("tail_30m_reversal", strategy_ids)
        self.assertEqual("杨永兴隔夜套利法", registry.get("overnight_arbitrage").name)
        self.assertEqual("尾盘30分钟强承接策略", registry.get("tail_30m_reversal").name)

    def test_unknown_strategy_raises_clear_error(self):
        registry = StrategyRegistry.load_builtin()

        with self.assertRaisesRegex(KeyError, "unknown strategy"):
            registry.get("missing_strategy")


if __name__ == "__main__":
    unittest.main()
