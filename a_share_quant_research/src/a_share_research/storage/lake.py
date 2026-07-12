from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from a_share_research.core.models import DataBatch
from a_share_research.quality.gate import QualityReport, QualityStatus


class DataGateBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedArtifact:
    dataset: str
    path: Path
    run_id: str


class DataLake:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.db_path = root / "curated" / "research.duckdb"

    def write_raw(self, batch: DataBatch, payload: bytes) -> Path:
        provenance = next(iter(batch.field_provenance.values()))
        digest = hashlib.sha256(payload).hexdigest()
        if batch.raw_payload_sha256 is not None and digest != batch.raw_payload_sha256:
            raise ValueError("raw payload hash does not match data batch")
        directory = (
            self.root
            / "raw"
            / batch.dataset
            / provenance.source_name
            / provenance.fetched_at.date().isoformat()
            / provenance.run_id
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.bin"
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"raw hash collision at {path}")
        if not path.exists():
            path.write_bytes(payload)
        return path

    def write_normalized(self, batch: DataBatch) -> NormalizedArtifact:
        provenance = next(iter(batch.field_provenance.values()))
        provenance_json = json.dumps(
            {name: value.model_dump(mode="json") for name, value in batch.field_provenance.items()},
            ensure_ascii=False,
            sort_keys=True,
        )
        rows = [dict(row, __field_provenance_json=provenance_json) for row in batch.rows]
        table = pa.Table.from_pylist(rows)
        directory = (
            self.root / "normalized" / batch.dataset / f"effective_date={provenance.effective_at.date()}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(provenance_json.encode("utf-8")).hexdigest()[:16]
        path = directory / f"part-{provenance.run_id}-{digest}.parquet"
        pq.write_table(table, path)
        return NormalizedArtifact(dataset=batch.dataset, path=path, run_id=provenance.run_id)

    def publish_curated(
        self,
        artifacts: list[NormalizedArtifact] | tuple[NormalizedArtifact, ...],
        quality_report: QualityReport,
    ) -> Path:
        if quality_report.status != QualityStatus.PASS:
            raise DataGateBlocked("curated snapshot requires PASS quality report")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        grouped: dict[str, list[str]] = defaultdict(list)
        for artifact in artifacts:
            grouped[artifact.dataset].append(str(artifact.path))
        with duckdb.connect(str(self.db_path)) as connection:
            for dataset, paths in grouped.items():
                table_name = self._safe_name(dataset)
                connection.execute(
                    f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_parquet(?)",
                    [paths],
                )
        return self.db_path

    @staticmethod
    def _safe_name(name: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"unsafe dataset name: {name}")
        return name
