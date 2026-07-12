from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from a_share_research.core.models import DataBatch, FieldProvenance
from a_share_research.quality.gate import QualityError, QualityReport, QualityStatus
from a_share_research.storage.lake import DataGateBlocked, DataLake

NOW = datetime(2026, 7, 12, 8, 0, tzinfo=UTC)


def batch() -> DataBatch:
    provenance = FieldProvenance(
        source_name="TEST_ONLY_source",
        source_uri="https://example.invalid/test-only",
        source_record_id="TEST_ONLY_1",
        fetched_at=NOW,
        effective_at=NOW - timedelta(days=1),
        available_at=NOW - timedelta(hours=1),
        run_id="TEST_ONLY_run",
        payload_sha256="c" * 64,
    )
    row = {"instrument_id": "SH600000", "effective_at": "2026-07-11", "close": 10.0}
    return DataBatch(
        dataset="daily_bars",
        rows=(row,),
        field_provenance={field: provenance for field in row},
        provider_version="TEST_ONLY_1",
    )


def test_write_normalized_preserves_provenance(tmp_path: Path) -> None:
    artifact = DataLake(tmp_path).write_normalized(batch())
    table = pq.read_table(artifact.path)
    assert artifact.path.is_file()
    assert "__field_provenance_json" in table.column_names
    assert table.num_rows == 1


def test_publish_curated_refuses_failed_quality(tmp_path: Path) -> None:
    report = QualityReport(
        status=QualityStatus.FAIL,
        blocking_errors=(QualityError(code="STALE_DATA", dataset="daily_bars", message="stale"),),
    )
    lake = DataLake(tmp_path)
    with pytest.raises(DataGateBlocked):
        lake.publish_curated([], report)
    assert not lake.db_path.exists()


def test_publish_curated_creates_queryable_table(tmp_path: Path) -> None:
    lake = DataLake(tmp_path)
    artifact = lake.write_normalized(batch())
    report = QualityReport(status=QualityStatus.PASS)

    path = lake.publish_curated([artifact], report)

    with duckdb.connect(str(path), read_only=True) as connection:
        count = connection.execute("select count(*) from daily_bars").fetchone()[0]
    assert count == 1
