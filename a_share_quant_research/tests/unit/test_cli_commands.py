import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from a_share_research.cli import main
from a_share_research.evidence.models import Event, EvidenceGrade, EvidenceItem
from a_share_research.quality.gate import QualityError
from a_share_research.reporting.models import DailyReport, DataIntegrity, ReportStatus

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def pass_gate(tmp_path: Path, artifacts: dict[str, Path]) -> Path:
    path = tmp_path / "quality.json"
    artifact_hashes = {
        name: hashlib.sha256(value.read_bytes()).hexdigest() for name, value in artifacts.items()
    }
    path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "blocking_errors": [],
                "run_ids": ["TEST_ONLY_run"],
                "dataset_hashes": {"daily_bars": ["a" * 64]},
                "artifact_hashes": artifact_hashes,
                "as_of": NOW.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    return path


def failed_gate(tmp_path: Path) -> tuple[Path, QualityError]:
    error = QualityError(code="STALE_DATA", dataset="daily_bars", message="old")
    path = tmp_path / "quality-failed.json"
    path.write_text(
        '{"status":"FAIL","blocking_errors":[{"code":"STALE_DATA","dataset":"daily_bars","message":"old","affected_keys":[]}],"run_ids":["TEST_ONLY_run"],"dataset_hashes":{"daily_bars":["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]},"artifact_hashes":{"source":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"as_of":"2026-07-12T00:00:00Z"}',
        encoding="utf-8",
    )
    return path, error


def test_daily_report_command_renders_canonical_json(tmp_path: Path) -> None:
    source = tmp_path / "report.json"
    output = tmp_path / "outputs"
    gate_path, error = failed_gate(tmp_path)
    report = DailyReport(
        run_id="TEST_ONLY_run",
        as_of=NOW,
        status=ReportStatus.BLOCKED_DATA,
        conclusion="不推荐",
        data_integrity=DataIntegrity(status="FAIL", errors=(error,)),
        market_environment={},
        industry_ranking=(),
        candidates=(),
        known_issues=("TEST_ONLY",),
    )
    source.write_text(report.model_dump_json(), encoding="utf-8")

    assert (
        main(
            [
                "daily-report",
                "--report-json",
                str(source),
                "--output-dir",
                str(output),
                "--gate-json",
                str(gate_path),
                "--run-id",
                "TEST_ONLY_run",
                "--config-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert len(list(output.glob("daily-research-2026-07-12.*"))) == 3


def test_evidence_gate_command_writes_verified_result(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    evidence_path = tmp_path / "evidence.json"
    output_path = tmp_path / "verification.json"
    event = Event(event_id="event-1", entity_id="SH600000", title="公告", event_time=NOW, major=True)
    item = EvidenceItem(
        evidence_id="evidence-1",
        event_id="event-1",
        entity_id="SH600000",
        grade=EvidenceGrade.A,
        source_name="exchange",
        source_owner="exchange",
        source_uri="https://example.invalid/1",
        canonical_uri="https://example.invalid/1",
        title="公告",
        text="TEST_ONLY",
        published_at=NOW,
        event_time=NOW,
        content_sha256="1" * 64,
        syndication_cluster="filing-1",
    )
    event_path.write_text(event.model_dump_json(), encoding="utf-8")
    evidence_path.write_text(json.dumps([item.model_dump(mode="json")]), encoding="utf-8")

    exit_code = main(
        [
            "run-evidence-gate",
            "--event-json",
            str(event_path),
            "--evidence-json",
            str(evidence_path),
            "--counter-search-performed",
            "--as-of",
            NOW.isoformat(),
            "--output-json",
            str(output_path),
            "--gate-json",
            str(pass_gate(tmp_path, {"event": event_path, "evidence": evidence_path})),
            "--run-id",
            "TEST_ONLY_run",
        ]
    )
    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["payload"][0]["status"] == "VERIFIED"


def test_failed_gate_blocks_downstream_command(tmp_path: Path) -> None:
    gate = tmp_path / "quality.json"
    gate.write_text(
        '{"status":"FAIL","blocking_errors":[{"code":"STALE_DATA","dataset":"daily_bars","message":"old","affected_keys":[]}]}',
        encoding="utf-8",
    )
    assert (
        main(
            [
                "daily-report",
                "--report-json",
                str(tmp_path / "untrusted.json"),
                "--output-dir",
                str(tmp_path / "out"),
                "--gate-json",
                str(gate),
                "--run-id",
                "TEST_ONLY_run",
                "--config-dir",
                str(tmp_path),
            ]
        )
        == 3
    )


def test_gate_rejects_changed_evidence_artifact(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    evidence_path = tmp_path / "evidence.json"
    event_path.write_text("{}", encoding="utf-8")
    evidence_path.write_text("[]", encoding="utf-8")
    gate = pass_gate(tmp_path, {"event": event_path, "evidence": evidence_path})
    evidence_path.write_text('[{"tampered":true}]', encoding="utf-8")
    assert (
        main(
            [
                "run-evidence-gate",
                "--event-json",
                str(event_path),
                "--evidence-json",
                str(evidence_path),
                "--counter-search-performed",
                "--as-of",
                NOW.isoformat(),
                "--output-json",
                str(tmp_path / "out.json"),
                "--gate-json",
                str(gate),
                "--run-id",
                "TEST_ONLY_run",
            ]
        )
        == 3
    )
