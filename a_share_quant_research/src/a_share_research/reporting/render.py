from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from a_share_research.reporting.models import DailyReport


@dataclass(frozen=True)
class ReportPaths:
    json: Path
    markdown: Path
    csv: Path


def write_report(report: DailyReport, output_dir: Path) -> ReportPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"daily-research-{report.as_of.date().isoformat()}"
    paths = ReportPaths(
        json=output_dir / f"{stem}.json",
        markdown=output_dir / f"{stem}.md",
        csv=output_dir / f"{stem}.csv",
    )
    paths.json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    paths.markdown.write_text(render_markdown(report), encoding="utf-8")
    _write_csv(report, paths.csv)
    return paths


def render_markdown(report: DailyReport) -> str:
    lines = [
        f"# A股每日量化投研报告 {report.as_of.date().isoformat()}",
        "",
        f"结论：{report.conclusion}",
        f"运行状态：{report.status}",
        f"运行ID：{report.run_id}",
        "",
        "## 数据完整性和更新时间",
        "",
        f"状态：{report.data_integrity.status}",
        f"快照：{report.data_integrity.snapshot_id or '未生成'}",
    ]
    for error in report.data_integrity.errors:
        lines.append(f"- {error.code}: {error.message}")
    lines.extend(
        [
            "",
            "## 市场环境",
            "",
            f"```json\n{json.dumps(report.market_environment, ensure_ascii=False, indent=2)}\n```",
        ]
    )
    lines.extend(["", "## 行业评分和排名", ""])
    for item in report.industry_ranking:
        lines.append(f"{item.rank}. {item.industry} — {item.score:.2f} — {item.direction}")
    if not report.industry_ranking:
        lines.append("无可用行业排名。")
    lines.extend(["", "## 候选股票", ""])
    if not report.candidates:
        lines.append("不推荐：没有通过全部门禁的股票。")
    for candidate in report.candidates:
        lines.extend(
            [
                f"### {candidate.instrument_id} — {candidate.conclusion}",
                "",
                f"综合分：{candidate.composite_score:.2f}",
                f"解释：{candidate.explanation}",
                f"关键证据：{', '.join(candidate.key_evidence_ids) or '无'}",
                f"反方证据：{', '.join(candidate.counter_evidence_ids) or '无'}",
                f"历史同类信号：{candidate.historical_signal_summary}",
                "因子明细：",
            ]
        )
        for factor in candidate.factor_details:
            lines.append(f"- {factor.name}: raw={factor.raw_value}, z={factor.z_value}, score={factor.score}")
        lines.append("逻辑失效条件：" + "；".join(candidate.invalidation_conditions))
        lines.append("风险提示：" + "；".join(candidate.risk_notes))
        lines.append("")
    lines.extend(["## 已知问题", ""])
    lines.extend(f"- {issue}" for issue in report.known_issues)
    return "\n".join(lines) + "\n"


def _write_csv(report: DailyReport, path: Path) -> None:
    fieldnames = [
        "record_type",
        "instrument_id",
        "composite_score",
        "conclusion",
        "factor_scores_json",
        "key_evidence_ids",
        "counter_evidence_ids",
        "error_code",
        "error_message",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in report.candidates:
            writer.writerow(
                {
                    "record_type": "candidate",
                    "instrument_id": candidate.instrument_id,
                    "composite_score": candidate.composite_score,
                    "conclusion": candidate.conclusion,
                    "factor_scores_json": json.dumps(
                        [item.model_dump(mode="json") for item in candidate.factor_details],
                        ensure_ascii=False,
                    ),
                    "key_evidence_ids": "|".join(candidate.key_evidence_ids),
                    "counter_evidence_ids": "|".join(candidate.counter_evidence_ids),
                }
            )
        for error in report.data_integrity.errors:
            writer.writerow(
                {
                    "record_type": "error",
                    "error_code": error.code,
                    "error_message": error.message,
                }
            )
