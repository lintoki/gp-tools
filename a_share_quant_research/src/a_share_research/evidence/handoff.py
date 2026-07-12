from __future__ import annotations

import json
from pathlib import Path

from a_share_research.evidence.models import Event, EvidenceItem, LlmEvidenceAnalysis


def export_llm_bundle(
    event: Event,
    evidence: list[EvidenceItem] | tuple[EvidenceItem, ...],
    path: Path,
) -> Path:
    payload = {
        "event": event.model_dump(mode="json"),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "grade": item.grade,
                "source_name": item.source_name,
                "source_uri": item.source_uri,
                "title": item.title,
                "text": item.text,
                "published_at": item.published_at.isoformat(),
                "event_time": item.event_time.isoformat(),
                "is_counter_evidence": item.is_counter_evidence,
            }
            for item in evidence
        ],
        "allowed_tasks": [
            "classification",
            "event_extraction",
            "industry_chain",
            "contradictions",
            "natural_language_explanation",
        ],
        "forbidden_tasks": ["numeric_factor_generation", "price_inference", "missing_data_imputation"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_llm_analysis(path: Path, *, allowed_evidence_ids: set[str]) -> LlmEvidenceAnalysis:
    return LlmEvidenceAnalysis.model_validate_json(
        path.read_text(encoding="utf-8"),
        context={"allowed_evidence_ids": allowed_evidence_ids},
    )
