import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import CandidateReport, PaperTrade
from .retention import prepare_output_file


def build_scan_advice(reports: Iterable[CandidateReport]) -> Dict[str, Any]:
    rows = list(reports)
    if rows and all(report.code == "DATA_SOURCE" for report in rows):
        return {
            "level": "NO_DATA",
            "summary": "行情源不可用，无法完成本轮扫描。",
            "action": "严格策略建议空仓；稍后重新执行报告命令。",
            "watchlist": [],
        }
    passed = [report for report in rows if report.passed]
    if passed:
        best = sorted(passed, key=lambda report: report.score, reverse=True)[0]
        return {
            "level": "BUY_CANDIDATE",
            "summary": f"严格策略出现候选：{best.code} {best.name}",
            "action": "可作为纸面或小仓候选；不自动下单，实盘前仍需确认盘口和仓位。",
            "watchlist": [f"{report.code} {report.name}" for report in passed[:5]],
        }

    if rows:
        watch = sorted(rows, key=lambda report: report.score, reverse=True)[:3]
        return {
            "level": "NO_BUY",
            "summary": "没有股票通过全部尾盘隔夜规则。",
            "action": "严格策略建议空仓或不新增仓位；只观察最接近条件的股票。",
            "watchlist": [f"{report.code} {report.name}" for report in watch],
        }

    return {
        "level": "NO_DATA",
        "summary": "本轮没有进入明细评估的候选。",
        "action": "严格策略建议空仓；可稍后重新执行扫描。",
        "watchlist": [],
    }


def build_scan_markdown(scan_time: str, reports: Iterable[CandidateReport]) -> str:
    rows = list(reports)
    passed_count = sum(1 for report in rows if report.passed)
    lines = [
        f"# 尾盘隔夜候选 {scan_time}",
        "",
        f"- 入选：{passed_count}",
        f"- 总检查：{len(rows)}",
        "",
        "| 代码 | 名称 | 参考入场价 | 评分 |",
        "| --- | --- | ---: | ---: |",
    ]
    for report in rows:
        if not report.passed:
            continue
        price = "-" if report.entry_price is None else f"{report.entry_price:.3f}"
        lines.append(f"| {report.code} | {report.name} | {price} | {report.score:.2f} |")

    lines.extend(["", "## 入选理由"])
    for report in rows:
        if report.passed:
            lines.append(f"- {report.code} {report.name}：{'；'.join(report.pass_reasons)}")

    failed = [report for report in rows if not report.passed]
    if failed:
        lines.extend(["", "## 主要过滤原因"])
        for report in failed[:20]:
            lines.append(f"- {report.code} {report.name}：{'；'.join(report.fail_reasons)}")

    lines.append("")
    return "\n".join(lines)


def write_scan_payload(path: Path, scan_time: str, reports: Iterable[CandidateReport]) -> None:
    prepare_output_file(path, "*.json")
    payload = {
        "scan_time": scan_time,
        "reports": [asdict(report) for report in reports],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def paper_trade_from_report(report: CandidateReport, scan_time: str, shares: int) -> PaperTrade:
    if report.entry_price is None:
        raise ValueError(f"{report.code} 缺少参考入场价，不能记录纸面交易")
    entry_date, entry_time = scan_time.split()
    return PaperTrade(
        trade_id=f"{entry_date.replace('-', '')}-{report.code}",
        code=report.code,
        name=report.name,
        entry_date=entry_date,
        entry_time=entry_time,
        entry_price=report.entry_price,
        shares=shares,
        status="OPEN",
        strategy="tail_overnight",
        notes=list(report.pass_reasons),
    )


def scan_output_path(data_dir: Path, scan_time: str) -> Path:
    stamp = scan_time.replace("-", "").replace(":", "").replace(" ", "-")
    return data_dir / "scans" / f"{stamp}.json"


def scan_html_output_path(data_dir: Path, scan_time: str) -> Path:
    stamp = scan_time.replace("-", "").replace(":", "").replace(" ", "-")
    return data_dir / "reports" / f"{stamp}.html"


def review_output_path(data_dir: Path, review_date: str) -> Path:
    return data_dir / "reviews" / f"{review_date}.md"
