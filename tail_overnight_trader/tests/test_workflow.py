import json
import tempfile
import unittest
from pathlib import Path

from tail_trader.models import CandidateReport
from tail_trader.workflow import (
    build_scan_advice,
    build_scan_markdown,
    paper_trade_from_report,
    scan_html_output_path,
    write_scan_payload,
)
from tail_trader.html_report import build_scan_html


class WorkflowTest(unittest.TestCase):
    def test_build_scan_markdown_includes_passed_and_failed_reasons(self):
        report = CandidateReport(
            code="002123",
            name="测试股份",
            passed=True,
            score=6.2,
            entry_price=12.45,
            pass_reasons=["涨幅达标", "尾盘形态达标"],
            fail_reasons=[],
            snapshot={},
        )

        markdown = build_scan_markdown("2026-06-23 14:55:00", [report])

        self.assertIn("# 尾盘隔夜候选 2026-06-23 14:55:00", markdown)
        self.assertIn("| 002123 | 测试股份 | 12.450 | 6.20 |", markdown)
        self.assertIn("- 002123 测试股份：涨幅达标；尾盘形态达标", markdown)

    def test_build_scan_advice_recommends_top_passed_candidate(self):
        passed = CandidateReport(
            code="002123",
            name="测试股份",
            passed=True,
            score=6.2,
            entry_price=12.45,
            pass_reasons=["尾盘形态达标"],
            fail_reasons=[],
            snapshot={},
        )
        failed = CandidateReport(
            code="002456",
            name="失败股份",
            passed=False,
            score=7.0,
            entry_price=9.87,
            pass_reasons=["涨幅达标"],
            fail_reasons=["尾盘未创日内新高"],
            snapshot={},
        )

        advice = build_scan_advice([failed, passed])

        self.assertEqual(advice["level"], "BUY_CANDIDATE")
        self.assertIn("002123 测试股份", advice["summary"])
        self.assertIn("纸面或小仓候选", advice["action"])

    def test_build_scan_advice_recommends_cash_when_no_candidate_passes(self):
        failed = CandidateReport(
            code="002456",
            name="失败股份",
            passed=False,
            score=7.0,
            entry_price=9.87,
            pass_reasons=["涨幅达标"],
            fail_reasons=["尾盘未创日内新高"],
            snapshot={},
        )

        advice = build_scan_advice([failed])

        self.assertEqual(advice["level"], "NO_BUY")
        self.assertIn("空仓", advice["action"])
        self.assertIn("002456 失败股份", advice["watchlist"])

    def test_build_scan_advice_marks_data_source_failure_as_no_data(self):
        failed = CandidateReport(
            code="DATA_SOURCE",
            name="行情源不可用",
            passed=False,
            score=0.0,
            entry_price=None,
            pass_reasons=[],
            fail_reasons=["实时行情接口失败"],
            snapshot={},
        )

        advice = build_scan_advice([failed])

        self.assertEqual(advice["level"], "NO_DATA")
        self.assertIn("行情源不可用", advice["summary"])
        self.assertIn("稍后重新执行", advice["action"])

    def test_build_scan_html_is_standalone_and_contains_advice(self):
        report = CandidateReport(
            code="002123",
            name="测试股份",
            passed=True,
            score=6.2,
            entry_price=12.45,
            pass_reasons=["涨幅达标", "尾盘形态达标"],
            fail_reasons=[],
            snapshot={"change_pct": 4.2, "volume_ratio": 1.6, "turnover_pct": 6.5},
        )

        html = build_scan_html("2026-06-23 14:55:00", [report])

        self.assertIn("<!doctype html>", html)
        self.assertIn("尾盘隔夜策略扫描", html)
        self.assertIn("BUY_CANDIDATE", html)
        self.assertIn("002123", html)
        self.assertIn("涨幅达标", html)

    def test_write_scan_payload_saves_candidate_json(self):
        report = CandidateReport(
            code="002123",
            name="测试股份",
            passed=True,
            score=6.2,
            entry_price=12.45,
            pass_reasons=["涨幅达标"],
            fail_reasons=[],
            snapshot={"code": "002123"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "scan.json"
            write_scan_payload(output, "2026-06-23 14:55:00", [report])
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["scan_time"], "2026-06-23 14:55:00")
        self.assertEqual(payload["reports"][0]["code"], "002123")
        self.assertTrue(payload["reports"][0]["passed"])

    def test_scan_html_output_path_uses_html_suffix(self):
        output = scan_html_output_path(Path("/tmp/out"), "2026-06-23 14:55:00")

        self.assertEqual(output, Path("/tmp/out/reports/20260623-145500.html"))

    def test_paper_trade_from_report_uses_scan_time_and_notes(self):
        report = CandidateReport(
            code="002123",
            name="测试股份",
            passed=True,
            score=6.2,
            entry_price=12.45,
            pass_reasons=["涨幅达标"],
            fail_reasons=[],
            snapshot={},
        )

        trade = paper_trade_from_report(report, "2026-06-23 14:55:00", shares=100)

        self.assertEqual(trade.trade_id, "20260623-002123")
        self.assertEqual(trade.entry_date, "2026-06-23")
        self.assertEqual(trade.entry_time, "14:55:00")
        self.assertEqual(trade.entry_price, 12.45)
        self.assertEqual(trade.notes, ["涨幅达标"])


if __name__ == "__main__":
    unittest.main()
