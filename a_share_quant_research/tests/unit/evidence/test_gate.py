from datetime import UTC, datetime, timedelta

from a_share_research.evidence.gate import EvidenceGate
from a_share_research.evidence.models import Event, EvidenceGrade, EvidenceItem, VerificationStatus

NOW = datetime(2026, 7, 12, tzinfo=UTC)
EVENT = Event(
    event_id="event-1",
    entity_id="SH600000",
    title="测试事件",
    event_time=NOW - timedelta(days=1),
    major=True,
)


def evidence(
    item_id: str,
    grade: EvidenceGrade,
    owner: str,
    cluster: str,
    *,
    counter: bool = False,
    published_at: datetime = NOW,
    event_id: str = EVENT.event_id,
    entity_id: str = EVENT.entity_id,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=item_id,
        event_id=event_id,
        entity_id=entity_id,
        grade=grade,
        source_name=owner,
        source_owner=owner,
        source_uri=f"https://example.invalid/{item_id}",
        canonical_uri=f"https://example.invalid/{cluster}",
        title=item_id,
        text=f"TEST_ONLY {item_id}",
        published_at=published_at,
        event_time=EVENT.event_time,
        content_sha256=(item_id[0] * 64)[:64],
        syndication_cluster=cluster,
        is_counter_evidence=counter,
    )


def test_two_reprints_are_one_c_source() -> None:
    items = [
        evidence("a-source", EvidenceGrade.C, "media-a", "same-cluster"),
        evidence("b-reprint", EvidenceGrade.C, "media-b", "same-cluster"),
    ]
    result = EvidenceGate().evaluate(EVENT, items, counter_search_performed=True, as_of=NOW)
    assert result.status == VerificationStatus.UNVERIFIED
    assert result.independent_c_sources == 1


def test_two_independent_c_sources_verify_without_ab() -> None:
    items = [
        evidence("a-source", EvidenceGrade.C, "media-a", "cluster-a"),
        evidence("b-source", EvidenceGrade.C, "media-b", "cluster-b"),
        evidence("c-counter", EvidenceGrade.C, "media-c", "cluster-c", counter=True),
    ]
    result = EvidenceGate().evaluate(EVENT, items, counter_search_performed=True, as_of=NOW)
    assert result.status == VerificationStatus.VERIFIED
    assert result.catalyst_score > 0
    assert result.counter_evidence_ids == ("c-counter",)


def test_d_source_never_scores_and_missing_counter_search_blocks() -> None:
    item = evidence("d-rumor", EvidenceGrade.D, "forum", "rumor")
    result = EvidenceGate().evaluate(EVENT, [item], counter_search_performed=False, as_of=NOW)
    assert result.status == VerificationStatus.UNVERIFIED
    assert result.catalyst_score == 0
    assert "COUNTER_SEARCH_MISSING" in result.failure_codes


def test_a_grade_verifies_major_event() -> None:
    item = evidence("a-filing", EvidenceGrade.A, "exchange", "filing")
    result = EvidenceGate().evaluate(EVENT, [item], counter_search_performed=True, as_of=NOW)
    assert result.status == VerificationStatus.VERIFIED
    assert result.entity_id == "SH600000"
    assert result.core_evidence_ids == ("a-filing",)


def test_future_or_wrong_event_evidence_cannot_verify() -> None:
    items = [
        evidence("a-future", EvidenceGrade.A, "exchange", "future", published_at=NOW + timedelta(days=1)),
        evidence("b-wrong", EvidenceGrade.B, "company", "wrong", event_id="other-event"),
    ]
    result = EvidenceGate().evaluate(EVENT, items, counter_search_performed=True, as_of=NOW)
    assert result.status == VerificationStatus.UNVERIFIED
    assert "EVIDENCE_NOT_YET_AVAILABLE" in result.failure_codes
    assert "EVIDENCE_EVENT_MISMATCH" in result.failure_codes


def test_counter_evidence_reduces_catalyst_score() -> None:
    supportive = evidence("a-filing", EvidenceGrade.A, "exchange", "filing")
    counter = evidence("b-counter", EvidenceGrade.B, "regulator", "counter", counter=True)
    without = EvidenceGate().evaluate(EVENT, [supportive], counter_search_performed=True, as_of=NOW)
    with_counter = EvidenceGate().evaluate(
        EVENT, [supportive, counter], counter_search_performed=True, as_of=NOW
    )
    assert with_counter.catalyst_score < without.catalyst_score
