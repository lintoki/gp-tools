import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from a_share_research.reporting.models import (
    CandidateConclusion,
    CandidateReport,
    DailyReport,
    DataIntegrity,
    FactorDetail,
    ReportStatus,
)
from a_share_research.reporting.render import write_report


def report() -> DailyReport:
    as_of = datetime(2026, 7, 12, tzinfo=UTC)
    candidates = tuple(
        CandidateReport(
            instrument_id=f"SH60000{index}",
            composite_score=90.0 - index,
            conclusion=CandidateConclusion.ENTER_POOL,
            factor_details=(
                FactorDetail(
                    name="trend",
                    raw_value=0.1,
                    z_value=1.0,
                    score=90.0 - index,
                    as_of=as_of,
                    dependencies=("daily_bars.close",),
                ),
            ),
            key_evidence_ids=(f"evidence-{index}",),
            counter_evidence_ids=(),
            invalidation_conditions=("数据门禁失败",),
            historical_signal_summary="TEST_ONLY 10次",
            risk_notes=("仅供研究",),
            explanation="TEST_ONLY explanation",
        )
        for index in range(2)
    )
    return DailyReport(
        run_id="TEST_ONLY_run",
        as_of=as_of,
        status=ReportStatus.SUCCEEDED,
        conclusion="进入候选池",
        data_integrity=DataIntegrity(status="PASS", snapshot_id="TEST_ONLY_snapshot"),
        market_environment={"us_index_trend": "UP"},
        industry_ranking=(),
        candidates=candidates,
        required_factors=("trend",),
        factor_weights={"trend": 1.0},
        known_issues=(),
    )


def test_all_formats_contain_same_candidate_ids(tmp_path: Path) -> None:
    paths = write_report(report(), tmp_path)
    json_ids = {
        item["instrument_id"] for item in json.loads(paths.json.read_text(encoding="utf-8"))["candidates"]
    }
    markdown = paths.markdown.read_text(encoding="utf-8")
    with paths.csv.open(encoding="utf-8-sig", newline="") as handle:
        csv_ids = {row["instrument_id"] for row in csv.DictReader(handle)}
    assert json_ids == csv_ids == {"SH600000", "SH600001"}
    assert all(instrument in markdown for instrument in json_ids)
