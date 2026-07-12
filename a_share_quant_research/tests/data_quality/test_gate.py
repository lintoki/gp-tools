from datetime import UTC, datetime, timedelta

import pytest

from a_share_research.core.models import DataBatch, FieldProvenance
from a_share_research.quality.contracts import DataContract
from a_share_research.quality.gate import QualityGate, QualityStatus

AS_OF = datetime(2026, 7, 12, 8, 0, tzinfo=UTC)


def make_batch(
    rows: tuple[dict, ...] | None = None,
    *,
    available_at: datetime = AS_OF - timedelta(hours=1),
    effective_at: datetime = AS_OF - timedelta(days=1),
    failed_items: tuple[str, ...] = (),
) -> DataBatch:
    rows = rows or (
        {
            "instrument_id": "SH600000",
            "effective_at": "2026-07-11",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 1000.0,
        },
    )
    fields = {key for row in rows for key in row}
    provenance = FieldProvenance(
        source_name="TEST_ONLY_source",
        source_uri="https://example.invalid/test-only",
        source_record_id="TEST_ONLY_1",
        fetched_at=AS_OF,
        effective_at=effective_at,
        available_at=available_at,
        run_id="TEST_ONLY_run",
        payload_sha256="b" * 64,
    )
    return DataBatch(
        dataset="daily_bars",
        rows=rows,
        field_provenance={field: provenance for field in fields},
        failed_items=failed_items,
        provider_version="TEST_ONLY_1",
    )


def contract() -> DataContract:
    return DataContract(
        dataset="daily_bars",
        required_columns=("instrument_id", "effective_at", "open", "high", "low", "close", "volume"),
        primary_key=("instrument_id", "effective_at"),
        minimum_rows=1,
        max_age=timedelta(days=2),
        check_ohlc=True,
    )


def test_valid_batch_passes() -> None:
    report = QualityGate().validate([make_batch()], [contract()], AS_OF)
    assert report.status == QualityStatus.PASS
    assert report.blocking_errors == ()


@pytest.mark.parametrize(
    ("batch", "error_code"),
    [
        (make_batch(rows=({"instrument_id": "SH600000", "effective_at": "2026-07-11"},)), "MISSING_COLUMN"),
        (
            make_batch(
                rows=(
                    {
                        "instrument_id": "SH600000",
                        "effective_at": "2026-07-11",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10,
                        "volume": 1,
                    },
                    {
                        "instrument_id": "SH600000",
                        "effective_at": "2026-07-11",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10,
                        "volume": 1,
                    },
                )
            ),
            "DUPLICATE_KEY",
        ),
        (make_batch(available_at=AS_OF - timedelta(days=3)), "STALE_DATA"),
        (make_batch(failed_items=("SH600001",)), "PARTIAL_FETCH"),
        (
            make_batch(
                rows=(
                    {
                        "instrument_id": "SH600000",
                        "effective_at": "2026-07-11",
                        "open": 10,
                        "high": 9,
                        "low": 8,
                        "close": 10,
                        "volume": 1,
                    },
                )
            ),
            "INVALID_OHLC",
        ),
    ],
)
def test_required_dataset_failure_blocks_run(batch: DataBatch, error_code: str) -> None:
    report = QualityGate().validate([batch], [contract()], AS_OF)
    assert report.status == QualityStatus.FAIL
    assert error_code in {error.code for error in report.blocking_errors}


def test_missing_required_dataset_fails() -> None:
    report = QualityGate().validate([], [contract()], AS_OF)
    assert report.status == QualityStatus.FAIL
    assert report.blocking_errors[0].code == "DATASET_MISSING"


def test_refetching_old_effective_data_does_not_refresh_it() -> None:
    batch = make_batch(available_at=AS_OF, effective_at=AS_OF - timedelta(days=10))
    report = QualityGate().validate([batch], [contract()], AS_OF)
    assert "STALE_DATA" in {error.code for error in report.blocking_errors}


def test_future_row_date_and_partial_required_values_fail_closed() -> None:
    future = make_batch(
        rows=(
            {
                "instrument_id": "SH600000",
                "effective_at": "2026-07-13",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": None,
                "volume": 1,
            },
        )
    )
    report = QualityGate().validate([future], [contract()], AS_OF)
    codes = {error.code for error in report.blocking_errors}
    assert {"FUTURE_DATA", "MISSING_VALUE"} <= codes


def test_duplicate_batches_for_dataset_are_not_silently_overwritten() -> None:
    report = QualityGate().validate([make_batch(), make_batch()], [contract()], AS_OF)
    assert "MULTIPLE_BATCHES" in {error.code for error in report.blocking_errors}


def test_declared_types_and_row_available_time_are_enforced() -> None:
    batch = make_batch(
        rows=(
            {
                "instrument_id": "SH600000",
                "effective_at": "2026-07-11",
                "available_at": "2026-07-13T00:00:00+00:00",
                "open": "bad",
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 1,
            },
        )
    )
    strict = contract().model_copy(
        update={
            "column_types": {"open": "number", "available_at": "datetime"},
            "row_available_at_column": "available_at",
        }
    )
    report = QualityGate().validate([batch], [strict], AS_OF)
    codes = {error.code for error in report.blocking_errors}
    assert {"TYPE_ERROR", "FUTURE_DATA"} <= codes
