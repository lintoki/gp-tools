from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from a_share_research.quality.gate import QualityError


class ReportStatus(StrEnum):
    BLOCKED_DATA = "BLOCKED_DATA"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


class CandidateConclusion(StrEnum):
    OBSERVE = "观察"
    WAIT_CONFIRMATION = "等待确认"
    ENTER_POOL = "进入候选池"
    NOT_RECOMMENDED = "不推荐"


class DataIntegrity(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["PASS", "FAIL"]
    snapshot_id: str | None = None
    errors: tuple[QualityError, ...] = ()


class FactorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    raw_value: float | None
    z_value: float | None
    score: float | None = Field(default=None, ge=0, le=100)
    as_of: datetime
    dependencies: tuple[str, ...] = Field(min_length=1)


class CandidateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    composite_score: float = Field(ge=0, le=100)
    conclusion: CandidateConclusion
    factor_details: tuple[FactorDetail, ...] = Field(min_length=1)
    key_evidence_ids: tuple[str, ...] = Field(min_length=1)
    counter_evidence_ids: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    historical_signal_summary: str
    risk_notes: tuple[str, ...]
    explanation: str


class IndustryRank(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    industry: str
    score: float = Field(ge=0, le=100)
    direction: str
    evidence_ids: tuple[str, ...]


class DailyReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    as_of: datetime
    status: ReportStatus
    conclusion: str
    data_integrity: DataIntegrity
    market_environment: dict[str, Any]
    industry_ranking: tuple[IndustryRank, ...]
    candidates: tuple[CandidateReport, ...] = Field(max_length=5)
    known_issues: tuple[str, ...]
    required_factors: tuple[str, ...] = ()
    factor_weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def blocked_report_has_no_candidates(self) -> Self:
        if self.status == ReportStatus.BLOCKED_DATA and self.candidates:
            raise ValueError("blocked report cannot contain candidates")
        if self.status == ReportStatus.BLOCKED_DATA and self.data_integrity.status != "FAIL":
            raise ValueError("blocked report requires failed data integrity")
        if self.data_integrity.status == "PASS" and self.data_integrity.errors:
            raise ValueError("PASS data integrity cannot contain errors")
        if self.status == ReportStatus.SUCCEEDED:
            if self.data_integrity.status != "PASS" or not self.data_integrity.snapshot_id:
                raise ValueError("successful report requires a traceable PASS snapshot")
            if any(
                candidate.conclusion == CandidateConclusion.NOT_RECOMMENDED for candidate in self.candidates
            ):
                raise ValueError("successful candidate list cannot contain NOT_RECOMMENDED entries")
            if not self.required_factors or set(self.factor_weights) != set(self.required_factors):
                raise ValueError("successful report requires all configured factor weights")
            if abs(sum(self.factor_weights.values()) - 1.0) > 1e-9:
                raise ValueError("report factor weights must sum to 1")
            for candidate in self.candidates:
                details = {detail.name: detail for detail in candidate.factor_details}
                if set(details) != set(self.required_factors):
                    raise ValueError("candidate factor details do not match required factors")
                if any(detail.score is None for detail in details.values()):
                    raise ValueError("candidate required factor score is missing")
                calculated = sum(
                    float(details[name].score) * self.factor_weights[name] for name in self.required_factors
                )
                if abs(calculated - candidate.composite_score) > 1e-6:
                    raise ValueError("candidate composite score is inconsistent with factors")
        return self

    @classmethod
    def blocked(
        cls,
        *,
        run_id: str,
        as_of: datetime,
        errors: tuple[QualityError, ...],
    ) -> DailyReport:
        return cls(
            run_id=run_id,
            as_of=as_of,
            status=ReportStatus.BLOCKED_DATA,
            conclusion="不推荐：必需数据未通过完整性门禁",
            data_integrity=DataIntegrity(status="FAIL", errors=errors),
            market_environment={},
            industry_ranking=(),
            candidates=(),
            known_issues=("数据门禁失败，未执行因子、证据推理和候选生成。",),
        )
