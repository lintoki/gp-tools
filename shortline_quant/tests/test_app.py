from datetime import datetime
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from quant.data_source import ensure_sample_data, load_daily_bars
from tests.test_realtime_screener import FailingRankedQuoteProvider, StubRealtimeProvider, intraday, quote


def sample_history_provider(start_date, end_date, max_symbols):
    data_dir = Path("/tmp/shortline_quant_app_test_data")
    ensure_sample_data(data_dir)
    return {
        "DEMO1": load_daily_bars(data_dir, "DEMO1"),
        "DEMO2": load_daily_bars(data_dir, "DEMO2"),
    }


def sample_recent_provider(max_symbols):
    return sample_history_provider("2025-01-02", "2025-05-15", max_symbols)


def sample_realtime_provider():
    return StubRealtimeProvider(
        quotes=[
            quote("605305", "中际联合", 4.1, price=42.76, volume_ratio=2.4, turnover_rate=5.41, cap=8_979_000_000),
            quote("000029", "深深房A", -0.65, price=29.05),
        ],
        intraday_by_code={
            "605305": intraday(
                [
                    ("2026-06-23 09:30", 41.0, 40.8, 1000, 10),
                    ("2026-06-23 14:20", 42.0, 41.4, 1300, 20),
                    ("2026-06-23 14:35", 42.8, 41.8, 1500, 30),
                    ("2026-06-23 14:45", 42.4, 41.9, 1500, 25),
                    ("2026-06-23 14:55", 42.7, 42.0, 1500, 28),
                ]
            )
        },
        limit_up_counts={"605305": 1},
        index_pct_chg=0.3,
    )


class AppTest(unittest.TestCase):
    def test_api_lists_strategies_and_runs_backtest(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=sample_realtime_provider(),
                now_func=lambda: datetime(2026, 6, 23, 14, 40),
            )
            client = TestClient(app)

            strategies = client.get("/api/strategies")
            self.assertEqual(200, strategies.status_code)
            self.assertGreaterEqual(len(strategies.json()["strategies"]), 2)

            response = client.post(
                "/api/backtests",
                json={
                    "strategy_id": "tail_30m_reversal",
                    "start_date": "2025-02-01",
                    "end_date": "2025-03-31",
                    "initial_cash": 100000,
                    "commission": 0.0003,
                    "slippage": 0.001,
                    "params": {},
                },
            )
            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual("tail_30m_reversal", payload["summary"]["strategy_id"])
            self.assertIn("operation_advice", payload["summary"])
            self.assertIn("quality", payload["summary"])

    def test_api_triggers_strategy_signal_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=sample_realtime_provider(),
                now_func=lambda: datetime(2026, 6, 23, 14, 40),
            )
            client = TestClient(app)

            response = client.post(
                "/api/signals",
                json={
                    "strategy_id": "overnight_arbitrage",
                    "params": {},
                },
            )

            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual("yang_yongxing_overnight_arbitrage_8_steps", payload["strategy"])
            self.assertGreater(len(payload["candidates"]), 0)
            self.assertEqual("605305", payload["candidates"][0]["code"])
            self.assertEqual("buy_candidate", payload["candidates"][0]["action"])
            self.assertIn("rejections", payload)

    def test_api_saves_strategy_config_and_signals_use_saved_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=sample_realtime_provider(),
                now_func=lambda: datetime(2026, 6, 23, 14, 40),
            )
            client = TestClient(app)

            saved = client.put(
                "/api/strategy-configs/overnight_arbitrage",
                json={"levels": {"A": {"max_pct_chg": 4.0}}},
            )
            self.assertEqual(200, saved.status_code)
            self.assertEqual(4.0, saved.json()["config"]["levels"]["A"]["max_pct_chg"])

            response = client.post(
                "/api/signals",
                json={"strategy_id": "overnight_arbitrage", "params": {}},
            )

            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual([], payload["A_buy_candidates"])
            self.assertEqual(["605305"], [item["code"] for item in payload["B_watch_candidates"]])
            stored_file = Path(tmp) / "data" / "strategy_configs.json"
            self.assertTrue(stored_file.exists())

    def test_api_resets_strategy_config_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=sample_realtime_provider(),
                now_func=lambda: datetime(2026, 6, 23, 14, 40),
            )
            client = TestClient(app)

            client.put(
                "/api/strategy-configs/overnight_arbitrage",
                json={"levels": {"A": {"max_pct_chg": 4.0}}},
            )
            reset = client.delete("/api/strategy-configs/overnight_arbitrage")

            self.assertEqual(200, reset.status_code)
            self.assertEqual(5.0, reset.json()["config"]["levels"]["A"]["max_pct_chg"])
            response = client.post("/api/signals", json={"strategy_id": "overnight_arbitrage", "params": {}})
            self.assertEqual(["605305"], [item["code"] for item in response.json()["A_buy_candidates"]])

    def test_api_backtest_uses_ranked_quote_universe_without_fixed_symbol_limit(self):
        seen_limits = []

        def history_provider(start_date, end_date, max_symbols):
            seen_limits.append(max_symbols)
            return sample_history_provider(start_date, end_date, max_symbols)

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=history_provider,
                recent_provider=sample_recent_provider,
            )
            client = TestClient(app)

            response = client.post(
                "/api/backtests",
                json={
                    "strategy_id": "tail_30m_reversal",
                    "start_date": "2025-02-01",
                    "end_date": "2025-03-31",
                    "initial_cash": 100000,
                    "commission": 0.0003,
                    "slippage": 0.001,
                    "params": {},
                },
            )

            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual(["DEMO1", "DEMO2"], payload["summary"]["symbols"])
            self.assertEqual("daily_cross_section", payload["summary"]["backtest_mode"])
            self.assertEqual("historical_daily_ranked_quotes", payload["summary"]["universe_mode"])
            self.assertEqual([None], seen_limits)

    def test_api_backtest_default_provider_uses_ranked_backtest_pool(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch(
            "app.fetch_ranked_backtest_bars",
            return_value=sample_history_provider("2025-02-01", "2025-03-31", None),
        ) as ranked_provider, unittest.mock.patch(
            "app.fetch_a_share_bars",
            side_effect=AssertionError("默认回测不应该调用全市场逐股历史 provider"),
        ):
            app = create_app(base_dir=Path(tmp), recent_provider=sample_recent_provider)
            client = TestClient(app)

            response = client.post(
                "/api/backtests",
                json={
                    "strategy_id": "tail_30m_reversal",
                    "start_date": "2025-02-01",
                    "end_date": "2025-03-31",
                    "initial_cash": 100000,
                    "commission": 0.0003,
                    "slippage": 0.001,
                    "params": {},
                },
            )

            self.assertEqual(200, response.status_code)
            called_args = ranked_provider.call_args.args
            self.assertEqual(("2025-02-01", "2025-03-31", None, "tail_30m_reversal"), called_args[:4])
            self.assertEqual(2.0, called_args[4]["levels"]["C"]["min_pct_chg"])

    def test_api_backtest_accepts_history_date_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
            )
            client = TestClient(app)

            response = client.post(
                "/api/backtests",
                json={
                    "strategy_id": "tail_30m_reversal",
                    "start_date": "2025-02-01",
                    "end_date": "2025-03-31",
                    "initial_cash": 100000,
                    "commission": 0.0003,
                    "slippage": 0.001,
                    "params": {},
                },
            )

            self.assertEqual(200, response.status_code)
            summary = response.json()["summary"]
            self.assertEqual("2025-02-01", summary["start_date"])
            self.assertEqual("2025-03-31", summary["end_date"])

    def test_api_signal_scan_rejects_current_down_stock_without_symbol_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=sample_realtime_provider(),
                now_func=lambda: datetime(2026, 6, 23, 14, 40),
            )
            client = TestClient(app)

            response = client.post(
                "/api/signals",
                json={
                    "strategy_id": "overnight_arbitrage",
                    "params": {},
                },
            )

            self.assertEqual(200, response.status_code)
            payload = response.json()
            rejected = {item["code"]: item["reasons"] for item in payload["rejections"]}
            self.assertIn("当前涨幅不在 2%-6% 观察池范围", rejected["000029"])
            self.assertNotIn("stock_code", payload)

    def test_api_signal_scan_returns_chinese_warning_when_market_source_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=FailingRankedQuoteProvider([], {}),
                now_func=lambda: datetime(2026, 6, 23, 14, 40),
            )
            client = TestClient(app)

            response = client.post(
                "/api/signals",
                json={
                    "strategy_id": "tail_30m_reversal",
                    "params": {},
                },
            )

            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertIn("行情榜数据源暂时不可用", payload["data_warning"])
            self.assertEqual([], payload["candidates"])
            self.assertEqual([], payload["near_misses"])
            self.assertNotIn("RemoteDisconnected", str(payload))

    def test_limit_up_cache_refresh_endpoint(self):
        class RefreshProvider(StubRealtimeProvider):
            def __init__(self):
                super().__init__([], {})
                self.refreshed_trade_date = None

            def refresh_limit_up_cache(self, trade_date=None):
                self.refreshed_trade_date = trade_date
                return 2

        with tempfile.TemporaryDirectory() as tmp:
            provider = RefreshProvider()
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
                realtime_provider=provider,
                now_func=lambda: datetime(2026, 6, 23, 16, 0),
            )
            client = TestClient(app)

            response = client.post("/api/limit-up-cache/refresh", json={"trade_date": "2026-06-23"})

            self.assertEqual(200, response.status_code)
            self.assertEqual(2, response.json()["cached_limit_up_count"])
            self.assertEqual("2026-06-23", provider.refreshed_trade_date.isoformat())

    def test_backtest_requires_history_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
            )
            client = TestClient(app)

            response = client.post(
                "/api/backtests",
                json={"strategy_id": "tail_30m_reversal", "params": {}},
            )

            self.assertEqual(422, response.status_code)

    def test_page_presents_strategy_workspace_without_cache_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                base_dir=Path(tmp),
                history_provider=sample_history_provider,
                recent_provider=sample_recent_provider,
            )
            client = TestClient(app)

            response = client.get("/")
            html = response.text

            self.assertIn("策略说明", html)
            self.assertIn("触发策略信号", html)
            self.assertIn("运行回测", html)
            self.assertIn("涨跌幅", html)
            self.assertIn("尾盘形态", html)
            self.assertIn("时间筛选", html)
            self.assertIn("接近标准观察池", html)
            self.assertIn("剔除原因", html)
            self.assertIn("涨幅榜", html)
            self.assertIn("主板", html)
            self.assertIn("ABC 标准", html)
            self.assertIn("修改配置", html)
            self.assertIn("恢复默认", html)
            self.assertIn("ABC 候选明细", html)
            self.assertIn("renderCandidateModules", html)
            self.assertIn("abc-module", html)
            self.assertIn("initDefaultBacktestDates", html)
            self.assertIn("applyQuickRange(7)", html)
            self.assertIn("setDate(end.getDate() - days)", html)
            self.assertNotIn('value="2025-01-02"', html)
            self.assertNotIn('value="2025-05-15"', html)
            self.assertNotIn("刷新真实A股数据", html)
            self.assertNotIn("最多缓存股票数", html)
            self.assertNotIn("股票代码", html)


if __name__ == "__main__":
    unittest.main()
