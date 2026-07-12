from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunStatus(StrEnum):
    CREATED = "CREATED"
    FETCHING = "FETCHING"
    NORMALIZING = "NORMALIZING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    COMPUTING = "COMPUTING"
    EVIDENCE = "EVIDENCE"
    BACKTEST_LOOKUP = "BACKTEST_LOOKUP"
    REPORTING = "REPORTING"
    BLOCKED_DATA = "BLOCKED_DATA"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.FETCHING}),
    RunStatus.FETCHING: frozenset({RunStatus.NORMALIZING, RunStatus.BLOCKED_DATA}),
    RunStatus.NORMALIZING: frozenset({RunStatus.VALIDATING, RunStatus.BLOCKED_DATA}),
    RunStatus.VALIDATING: frozenset({RunStatus.READY, RunStatus.BLOCKED_DATA}),
    RunStatus.READY: frozenset({RunStatus.COMPUTING}),
    RunStatus.COMPUTING: frozenset({RunStatus.EVIDENCE, RunStatus.FAILED}),
    RunStatus.EVIDENCE: frozenset({RunStatus.BACKTEST_LOOKUP, RunStatus.FAILED}),
    RunStatus.BACKTEST_LOOKUP: frozenset({RunStatus.REPORTING, RunStatus.FAILED}),
    RunStatus.REPORTING: frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED}),
    RunStatus.BLOCKED_DATA: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.SUCCEEDED: frozenset(),
}


class FieldProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_name: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    fetched_at: datetime
    effective_at: datetime
    available_at: datetime
    run_id: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DataBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset: str = Field(min_length=1)
    rows: tuple[dict[str, Any], ...]
    field_provenance: dict[str, FieldProvenance]
    failed_items: tuple[str, ...] = ()
    provider_version: str = "unknown"
    request_parameters: dict[str, Any] = Field(default_factory=dict)
    raw_payload_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_provenance_for_all_fields(self) -> Self:
        fields = {key for row in self.rows for key in row}
        missing = sorted(fields - set(self.field_provenance))
        if missing:
            raise ValueError(f"missing field provenance: {missing}")
        return self

    @property
    def is_complete(self) -> bool:
        return not self.failed_items


class FailureRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    dataset: str | None = None
    item_ids: tuple[str, ...] = ()
    occurred_at: datetime


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    as_of: datetime
    status: RunStatus = RunStatus.CREATED
    failures: tuple[FailureRecord, ...] = ()
    dataset_hashes: dict[str, str] = Field(default_factory=dict)

    def transition(self, target: RunStatus) -> RunManifest:
        if target not in ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid run transition: {self.status} -> {target}")
        return self.model_copy(update={"status": target})
