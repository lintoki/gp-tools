from __future__ import annotations

from datetime import datetime

from a_share_research.evidence.dedupe import independent_c_representatives
from a_share_research.evidence.models import (
    Event,
    EvidenceGrade,
    EvidenceItem,
    VerificationResult,
    VerificationStatus,
)
from a_share_research.factors.event import event_catalyst_factor


class EvidenceGate:
    def evaluate(
        self,
        event: Event,
        evidence: list[EvidenceItem] | tuple[EvidenceItem, ...],
        *,
        counter_search_performed: bool,
        as_of: datetime,
    ) -> VerificationResult:
        failure_codes: list[str] = []
        mismatched = [
            item for item in evidence if item.event_id != event.event_id or item.entity_id != event.entity_id
        ]
        if mismatched:
            failure_codes.append("EVIDENCE_EVENT_MISMATCH")
        scoped = [
            item for item in evidence if item.event_id == event.event_id and item.entity_id == event.entity_id
        ]
        if any(item.published_at > as_of for item in scoped):
            failure_codes.append("EVIDENCE_NOT_YET_AVAILABLE")
        visible = [item for item in scoped if item.published_at <= as_of]
        supportive = [item for item in visible if not item.is_counter_evidence]
        counter = [item for item in visible if item.is_counter_evidence]
        counter_ids = tuple(sorted(item.evidence_id for item in counter))
        ab = sorted(
            (item for item in supportive if item.grade in {EvidenceGrade.A, EvidenceGrade.B}),
            key=lambda item: (item.grade, item.published_at, item.evidence_id),
        )
        independent_c = independent_c_representatives(
            item for item in supportive if item.grade == EvidenceGrade.C
        )
        if not counter_search_performed:
            failure_codes.append("COUNTER_SEARCH_MISSING")
        verified_by_source = bool(ab) or len(independent_c) >= 2
        if not verified_by_source:
            failure_codes.append("CORE_EVIDENCE_INSUFFICIENT")
        verified = verified_by_source and counter_search_performed

        if ab:
            chosen_grade = ab[0].grade
            core_ids = tuple(item.evidence_id for item in ab)
            confidence = 1.0 if chosen_grade == EvidenceGrade.A else 0.8
            independent_count = len(independent_c)
        elif len(independent_c) >= 2:
            chosen_grade = EvidenceGrade.C
            core_ids = tuple(item.evidence_id for item in independent_c)
            confidence = 0.6
            independent_count = len(independent_c)
        else:
            chosen_grade = EvidenceGrade.D
            core_ids = ()
            confidence = 0.0
            independent_count = len(independent_c)

        evaluation_time = as_of
        days_old = max((evaluation_time.date() - event.event_time.date()).days, 0)
        score = event_catalyst_factor(
            chosen_grade,
            verified,
            independent_count,
            min(
                0.5,
                0.1
                * len(
                    independent_c_representatives(item for item in counter if item.grade != EvidenceGrade.D)
                ),
            ),
            days_old=days_old,
        )
        return VerificationResult(
            event_id=event.event_id,
            entity_id=event.entity_id,
            status=VerificationStatus.VERIFIED if verified else VerificationStatus.UNVERIFIED,
            confidence=confidence if verified else 0.0,
            catalyst_score=score if verified else 0.0,
            core_evidence_ids=core_ids if verified else (),
            counter_evidence_ids=counter_ids,
            independent_c_sources=independent_count,
            failure_codes=tuple(failure_codes),
        )
