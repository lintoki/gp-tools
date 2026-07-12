from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


class EvidenceGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    event_time: datetime
    major: bool = False


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    grade: EvidenceGrade
    source_name: str = Field(min_length=1)
    source_owner: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    canonical_uri: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    published_at: datetime
    event_time: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    syndication_cluster: str = Field(min_length=1)
    is_counter_evidence: bool = False


class VerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    entity_id: str = Field(min_length=1)
    status: VerificationStatus
    confidence: float = Field(ge=0, le=1)
    catalyst_score: float = Field(ge=0, le=1)
    core_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    independent_c_sources: int = Field(ge=0)
    failure_codes: tuple[str, ...] = ()


class LlmEvidenceAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    classification: str
    industry_chain: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    contradictions: tuple[str, ...]
    explanation: str

    @model_validator(mode="after")
    def references_only_allowed_evidence(self, info: ValidationInfo) -> Self:
        allowed = set((info.context or {}).get("allowed_evidence_ids", ()))
        referenced = set(self.supporting_evidence_ids) | set(self.counter_evidence_ids)
        unknown = sorted(referenced - allowed)
        if unknown:
            raise ValueError(f"unknown evidence ids: {unknown}")
        return self
