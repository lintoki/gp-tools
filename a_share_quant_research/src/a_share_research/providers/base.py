from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any, Protocol, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from a_share_research.core.models import DataBatch, FieldProvenance
from a_share_research.core.retry import BoundedRetryPolicy, RetryExhausted


class FetchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset: str = Field(min_length=1)
    symbols: tuple[str, ...] = ()
    series_ids: tuple[str, ...] = ()
    start_date: date | None = None
    end_date: date | None = None
    as_of: datetime
    run_id: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request_time_range(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        if self.end_date and self.end_date > self.as_of.date():
            raise ValueError("end_date must not be after as_of")
        return self


class DataProvider(Protocol):
    name: str
    capabilities: frozenset[str]

    def fetch(self, request: FetchRequest) -> DataBatch: ...


class IncompleteBatchError(RuntimeError):
    pass


class ProviderRegistry:
    def __init__(
        self,
        primary: DataProvider,
        backups: Sequence[DataProvider] = (),
        *,
        policy: BoundedRetryPolicy[DataBatch] | None = None,
        maximum_backups: int = 1,
    ) -> None:
        self.primary = primary
        self.backups = tuple(backups)
        self.policy = policy or BoundedRetryPolicy()
        self.maximum_backups = maximum_backups

    def fetch_with_fallback(self, request: FetchRequest) -> DataBatch:
        providers = (self.primary, *self.backups[: self.maximum_backups])
        failures: list[str] = []
        for provider in providers:
            if request.dataset not in provider.capabilities:
                failures.append(f"{provider.name}: unsupported dataset")
                continue
            try:
                return self.policy.execute(
                    lambda provider=provider: self._fetch_complete(provider, request),
                    self._is_transient,
                )
            except RetryExhausted as exc:
                failures.append(f"{provider.name}: {exc.cause}")
        raise RuntimeError("all allowed providers failed: " + "; ".join(failures))

    @staticmethod
    def _fetch_complete(provider: DataProvider, request: FetchRequest) -> DataBatch:
        batch = provider.fetch(request)
        if not batch.is_complete:
            raise IncompleteBatchError(f"partial batch: {batch.failed_items}")
        return batch

    @staticmethod
    def _is_transient(error: Exception) -> bool:
        if isinstance(
            error, (TimeoutError, IncompleteBatchError, httpx.TimeoutException, httpx.NetworkError)
        ):
            return True
        return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {
            429,
            500,
            502,
            503,
            504,
        }


def build_batch(
    *,
    request: FetchRequest,
    rows: list[dict[str, Any]],
    source_name: str,
    source_uri: str,
    provider_version: str,
    fetched_at: datetime,
    effective_at: datetime,
    failed_items: Sequence[str] = (),
    expected_fields: Sequence[str] = (),
    raw_payload_sha256: str | None = None,
) -> DataBatch:
    serialized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    payload_hash = hashlib.sha256(serialized).hexdigest()
    fields = set(expected_fields) | {key for row in rows for key in row}
    provenance = FieldProvenance(
        source_name=source_name,
        source_uri=source_uri,
        source_record_id=f"{request.dataset}:{request.run_id}",
        fetched_at=fetched_at,
        effective_at=effective_at,
        available_at=fetched_at,
        run_id=request.run_id,
        payload_sha256=payload_hash,
    )
    return DataBatch(
        dataset=request.dataset,
        rows=tuple(rows),
        field_provenance={field: provenance for field in fields},
        failed_items=tuple(failed_items),
        provider_version=provider_version,
        request_parameters=request.model_dump(mode="json"),
        raw_payload_sha256=raw_payload_sha256,
    )


Clock = Callable[[], datetime]
