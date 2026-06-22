import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fund_risk import MarketRisk, MarketRiskSnapshot, SectorRisk, SectorRiskSnapshot
from main import Quote, WatchItem
from monitor_runtime import MAX_SUMMARY_HISTORY, MonitorRuntime, build_quote_rows


class MonitorRuntimeTest(unittest.TestCase):
    def test_build_quote_rows_marks_position_blocked_alert(self):
        tz = ZoneInfo("Asia/Shanghai")
        item = WatchItem(
            name="景旺电子",
            code="603228.SH",
            market="SH",
            buy_low=74.5,
            buy_high=76.0,
            shares=100,
            type="PCB备选",
            priority=3,
            enabled=True,
            note="只有没买沪电股份时才提醒",
            depends_on_not_bought="002463.SZ",
        )
        quote = Quote(
            code="603228",
            name="景旺电子",
            latest_price=75.2,
            change_pct=1.23,
            amount=123456789,
        )
        positions = {
            "002463.SZ": {"name": "沪电股份", "bought": True},
            "603228.SH": {"name": "景旺电子", "bought": False},
        }

        rows = build_quote_rows(
            datetime(2026, 6, 22, 10, 0, tzinfo=tz),
            [item],
            {"603228": quote},
            positions,
        )

        self.assertEqual(rows[0]["status"], "BLOCKED_BY_POSITION")
        self.assertEqual(rows[0]["latest_price_text"], "75.20")
        self.assertEqual(rows[0]["amount_text"], "1.23亿")

    def test_summary_snapshots_keep_only_latest_ten_on_disk_and_state(self):
        tz = ZoneInfo("Asia/Shanghai")
        market_risk = MarketRiskSnapshot(
            level=MarketRisk.LOW,
            main_net_inflow_yi=12.3,
            net_inflow_15m_delta_yi=1.2,
            source="test",
            reason="测试",
        )
        sector_risk = SectorRiskSnapshot(
            level=SectorRisk.LOW,
            up_count=6,
            down_count=4,
            flat_count=0,
            sample_count=10,
            avg_change_pct=1.1,
            below_vwap_count=0,
            back_to_vwap_count=3,
            reason="测试",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            runtime = MonitorRuntime(
                base_dir=base,
                config_path=base / "config.yaml",
                alert_state_path=base / "alert_state.json",
                position_state_path=base / "position_state.json",
                settings_path=base / "settings.json",
                snapshots_path=base / "market_snapshots.jsonl",
            )
            start = datetime(2026, 6, 22, 10, 0, tzinfo=tz)

            for index in range(MAX_SUMMARY_HISTORY + 3):
                runtime._append_summary(
                    start + timedelta(minutes=index),
                    [{"code": f"{index:06d}", "name": "测试"}],
                    market_risk,
                    sector_risk,
                )

            lines = (base / "market_snapshots.jsonl").read_text(encoding="utf-8").splitlines()
            snapshots = [json.loads(line) for line in lines]

        self.assertEqual(len(lines), MAX_SUMMARY_HISTORY)
        self.assertEqual(len(runtime.snapshot()["summary_history"]), MAX_SUMMARY_HISTORY)
        self.assertEqual(snapshots[0]["rows"][0]["code"], "000003")
        self.assertEqual(snapshots[-1]["rows"][0]["code"], "000012")


if __name__ == "__main__":
    unittest.main()
