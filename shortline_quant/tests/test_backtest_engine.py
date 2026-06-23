import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.backtest_engine import BacktestEngine
from quant.data_source import ensure_sample_data, load_daily_bars
from quant.registry import StrategyRegistry
from quant.result_store import ResultStore


def as_main_board_bars(bars, code, name):
    main_board = bars.copy()
    main_board["code"] = code
    main_board["name"] = name
    return main_board


class BacktestEngineTest(unittest.TestCase):
    def test_backtest_uses_daily_ranked_quote_universe_before_strategy_match(self):
        def bars(code, name, pct_chg):
            return pd.DataFrame(
                [
                    {
                        "date": "2026-06-22",
                        "code": code,
                        "name": name,
                        "open": 10.0,
                        "high": 10.7,
                        "low": 9.9,
                        "close": 10.4,
                        "volume": 1000000,
                        "amount": 10400000,
                        "pct_chg": pct_chg,
                        "volume_ratio": 2.0,
                        "turnover_rate": 6.0,
                        "market_cap_billion": 100.0,
                        "has_limit_up_20d": 1,
                        "relative_strength": 3.0,
                        "above_vwap": 1,
                        "ma5_gt_ma30": 1,
                        "close_near_high": 0.9,
                    },
                    {
                        "date": "2026-06-23",
                        "code": code,
                        "name": name,
                        "open": 10.5,
                        "high": 10.8,
                        "low": 10.2,
                        "close": 10.6,
                        "volume": 900000,
                        "amount": 9540000,
                        "pct_chg": 1.9,
                        "volume_ratio": 1.0,
                        "turnover_rate": 4.0,
                        "market_cap_billion": 100.0,
                        "has_limit_up_20d": 1,
                        "relative_strength": 0.5,
                        "above_vwap": 1,
                        "ma5_gt_ma30": 1,
                        "close_near_high": 0.5,
                    },
                ]
            ).assign(date=lambda df: pd.to_datetime(df["date"])).set_index("date")

        engine = BacktestEngine(StrategyRegistry.load_builtin())

        result = engine.run(
            strategy_id="overnight_arbitrage",
            bars_by_symbol={
                "605305": bars("605305", "中际联合", 4.1),
                "000029": bars("000029", "深深房A", -0.65),
                "300001": bars("300001", "创业板示例", 4.1),
            },
            initial_cash=100000,
            commission=0.0003,
            slippage=0.001,
            params={"start_date": "2026-06-22", "end_date": "2026-06-22"},
        )

        self.assertEqual(["605305"], [trade["symbol"] for trade in result.trades])
        self.assertEqual("historical_daily_ranked_quotes", result.summary["universe_mode"])
        self.assertIn("涨幅榜", result.summary["stock_pool_rule"])

    def test_backtest_generates_quality_score_trades_and_operation_advice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_sample_data(root / "data")
            bars = as_main_board_bars(load_daily_bars(root / "data", "DEMO1"), "605305", "中际联合")
            registry = StrategyRegistry.load_builtin()
            engine = BacktestEngine(registry)

            result = engine.run(
                strategy_id="overnight_arbitrage",
                bars_by_symbol={"605305": bars},
                initial_cash=100000,
                commission=0.0003,
                slippage=0.001,
                params={},
            )

            self.assertEqual("overnight_arbitrage", result.summary["strategy_id"])
            self.assertGreater(result.summary["total_trades"], 0)
            self.assertIn(result.summary["quality"]["grade"], {"A", "B", "C", "D"})
            self.assertGreater(len(result.trades), 0)
            self.assertGreater(len(result.equity_curve), 0)
            self.assertIn("具体操作", result.summary["operation_advice"])
            self.assertIn("只做提醒", result.summary["operation_advice"])

    def test_backtest_is_daily_cross_section_and_evaluates_next_trading_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_sample_data(root / "data")
            bars_by_symbol = {
                "605305": as_main_board_bars(load_daily_bars(root / "data", "DEMO1"), "605305", "中际联合"),
                "603000": as_main_board_bars(load_daily_bars(root / "data", "DEMO2"), "603000", "示例股票"),
            }
            engine = BacktestEngine(StrategyRegistry.load_builtin())

            result = engine.run(
                strategy_id="tail_30m_reversal",
                bars_by_symbol=bars_by_symbol,
                initial_cash=100000,
                commission=0.0003,
                slippage=0.001,
                params={"start_date": "2025-02-01", "end_date": "2025-03-31"},
            )

            self.assertEqual("daily_cross_section", result.summary["backtest_mode"])
            self.assertEqual("2025-02-01", result.summary["start_date"])
            self.assertEqual("2025-03-31", result.summary["end_date"])
            self.assertIn("signal_accuracy_pct", result.summary)
            self.assertGreater(result.summary["evaluated_signals"], 0)
            first_trade = result.trades[0]
            self.assertGreaterEqual(first_trade["signal_date"], "2025-02-01")
            self.assertLessEqual(first_trade["signal_date"], "2025-03-31")
            self.assertIn("signal_date", first_trade)
            self.assertIn("evaluation_date", first_trade)
            self.assertNotEqual(first_trade["signal_date"], first_trade["evaluation_date"])
            self.assertIn("next_day_high_return_pct", first_trade)
            self.assertIn("is_correct", first_trade)
            self.assertIn(first_trade["evaluation_basis"], {"next_day_high", "next_day_close"})

    def test_result_store_saves_run_files_and_prunes_old_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ResultStore(Path(tmp), keep_last=2)

            for idx in range(4):
                store.save(
                    {
                        "run_id": f"run_{idx}",
                        "strategy_id": "overnight_arbitrage",
                        "quality": {"grade": "B"},
                    },
                    [{"symbol": "DEMO1", "pnl": idx}],
                    [{"date": "2026-01-01", "equity": 100000 + idx}],
                )

            runs = store.list_runs()
            self.assertEqual(["run_3", "run_2"], [item["run_id"] for item in runs])
            self.assertFalse((Path(tmp) / "run_0").exists())
            self.assertTrue((Path(tmp) / "run_3" / "summary.json").exists())
            self.assertTrue((Path(tmp) / "run_3" / "trades.csv").exists())
            self.assertTrue((Path(tmp) / "run_3" / "equity_curve.csv").exists())


if __name__ == "__main__":
    unittest.main()
