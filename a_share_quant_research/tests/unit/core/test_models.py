from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from a_share_research.core.models import (
    DataBatch,
    FieldProvenance,
    RunManifest,
    RunStatus,
)

NOW = datetime(2026, 7, 12, 8, 0, tzinfo=UTC)


def provenance() -> FieldProvenance:
    return FieldProvenance(
        source_name="official-test-source",
        source_uri="https://example.invalid/record/1",
        source_record_id="1",
        fetched_at=NOW,
        effective_at=NOW,
        available_at=NOW,
        run_id="run-1",
        payload_sha256="a" * 64,
    )


def test_data_batch_rejects_rows_without_field_provenance() -> None:
    with pytest.raises(ValidationError, match="field_provenance"):
        DataBatch(dataset="daily_bars", rows=({"instrument_id": "SH600000", "close": 10.0},))


def test_data_batch_requires_provenance_for_every_business_field() -> None:
    with pytest.raises(ValidationError, match="missing field provenance"):
        DataBatch(
            dataset="daily_bars",
            rows=({"instrument_id": "SH600000", "close": 10.0},),
            field_provenance={"instrument_id": provenance()},
        )


def test_manifest_rejects_skipping_ready_gate() -> None:
    manifest = RunManifest(run_id="run-1", as_of=NOW)
    manifest = manifest.transition(RunStatus.FETCHING)
    with pytest.raises(ValueError, match="invalid run transition"):
        manifest.transition(RunStatus.COMPUTING)
