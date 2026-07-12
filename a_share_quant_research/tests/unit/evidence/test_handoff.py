from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from a_share_research.evidence.handoff import export_llm_bundle, import_llm_analysis
from a_share_research.evidence.models import Event, EvidenceGrade, EvidenceItem

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def test_llm_handoff_round_trip_requires_citations(tmp_path: Path) -> None:
    event = Event(event_id="event-1", entity_id="SH600000", title="事件", event_time=NOW, major=True)
    item = EvidenceItem(
        evidence_id="evidence-1",
        event_id="event-1",
        entity_id="SH600000",
        grade=EvidenceGrade.A,
        source_name="exchange",
        source_owner="exchange",
        source_uri="https://example.invalid/evidence-1",
        canonical_uri="https://example.invalid/evidence-1",
        title="公告",
        text="TEST_ONLY 公告正文",
        published_at=NOW,
        event_time=NOW,
        content_sha256="e" * 64,
        syndication_cluster="filing-1",
    )
    bundle = export_llm_bundle(event, [item], tmp_path / "bundle.json")
    assert bundle.is_file()
    assert "factor_score" not in bundle.read_text(encoding="utf-8")

    analysis = tmp_path / "analysis.json"
    analysis.write_text(
        '{"event_id":"event-1","classification":"earnings","industry_chain":["bank"],'
        '"supporting_evidence_ids":["evidence-1"],"counter_evidence_ids":[],'
        '"contradictions":[],"explanation":"TEST_ONLY explanation"}',
        encoding="utf-8",
    )
    parsed = import_llm_analysis(analysis, allowed_evidence_ids={"evidence-1"})
    assert parsed.supporting_evidence_ids == ("evidence-1",)


def test_llm_analysis_rejects_unknown_evidence_id(tmp_path: Path) -> None:
    analysis = tmp_path / "invalid.json"
    analysis.write_text(
        '{"event_id":"event-1","classification":"other","industry_chain":[],'
        '"supporting_evidence_ids":["invented"],"counter_evidence_ids":[],'
        '"contradictions":[],"explanation":"invalid"}',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="unknown evidence ids"):
        import_llm_analysis(analysis, allowed_evidence_ids={"evidence-1"})
