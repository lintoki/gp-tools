from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb


class ExperimentLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id VARCHAR PRIMARY KEY,
                    status VARCHAR NOT NULL,
                    config_hash VARCHAR NOT NULL,
                    data_manifest_hash VARCHAR NOT NULL,
                    metrics_json VARCHAR,
                    error_type VARCHAR,
                    error_message VARCHAR,
                    recorded_at TIMESTAMP NOT NULL
                )
                """
            )

    def record_failure(
        self,
        experiment_id: str,
        config_hash: str,
        data_manifest_hash: str,
        error: Exception,
    ) -> None:
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO experiments VALUES (?, 'FAILED', ?, ?, NULL, ?, ?, ?)
                """,
                [
                    experiment_id,
                    config_hash,
                    data_manifest_hash,
                    type(error).__name__,
                    str(error),
                    datetime.now(UTC),
                ],
            )

    def get(self, experiment_id: str) -> dict:
        with duckdb.connect(str(self.path), read_only=True) as connection:
            cursor = connection.execute("SELECT * FROM experiments WHERE experiment_id = ?", [experiment_id])
            row = cursor.fetchone()
            if row is None:
                raise KeyError(experiment_id)
            return dict(zip([column[0] for column in cursor.description], row, strict=True))
