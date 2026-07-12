from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from a_share_research.core.models import DataBatch
from a_share_research.quality.contracts import DataContract


class QualityStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class QualityError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    message: str = Field(min_length=1)
    affected_keys: tuple[str, ...] = ()


class QualityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: QualityStatus
    blocking_errors: tuple[QualityError, ...] = ()
    run_ids: tuple[str, ...] = ()
    dataset_hashes: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    as_of: datetime | None = None

    def snapshot_id(self) -> str:
        payload = {
            "run_ids": self.run_ids,
            "dataset_hashes": self.dataset_hashes,
            "artifact_hashes": self.artifact_hashes,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "status": self.status,
            "blocking_errors": [error.model_dump(mode="json") for error in self.blocking_errors],
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()


class QualityGate:
    def validate(
        self,
        batches: list[DataBatch] | tuple[DataBatch, ...],
        contracts: list[DataContract] | tuple[DataContract, ...],
        as_of: datetime,
        artifact_hashes: dict[str, str] | None = None,
    ) -> QualityReport:
        counts = Counter(batch.dataset for batch in batches)
        by_dataset = {batch.dataset: batch for batch in batches}
        errors: list[QualityError] = []
        for contract in contracts:
            if counts[contract.dataset] > 1:
                errors.append(
                    self._error(
                        "MULTIPLE_BATCHES",
                        contract,
                        "multiple batches for one dataset require explicit reconciliation",
                    )
                )
                continue
            batch = by_dataset.get(contract.dataset)
            if batch is None:
                if contract.required:
                    errors.append(self._error("DATASET_MISSING", contract, "required dataset is missing"))
                continue
            errors.extend(self._validate_batch(batch, contract, as_of))
        status = QualityStatus.FAIL if errors else QualityStatus.PASS
        run_ids = tuple(
            sorted({item.run_id for batch in batches for item in batch.field_provenance.values()})
        )
        dataset_hashes = {
            batch.dataset: tuple(sorted({item.payload_sha256 for item in batch.field_provenance.values()}))
            for batch in batches
            if counts[batch.dataset] == 1
        }
        return QualityReport(
            status=status,
            blocking_errors=tuple(errors),
            run_ids=run_ids,
            dataset_hashes=dataset_hashes,
            artifact_hashes=artifact_hashes or {},
            as_of=as_of,
        )

    def _validate_batch(
        self,
        batch: DataBatch,
        contract: DataContract,
        as_of: datetime,
    ) -> list[QualityError]:
        errors: list[QualityError] = []
        if batch.failed_items:
            errors.append(
                self._error(
                    "PARTIAL_FETCH",
                    contract,
                    "provider returned failed items",
                    batch.failed_items,
                )
            )
        if len(batch.rows) < contract.minimum_rows:
            errors.append(self._error("INSUFFICIENT_ROWS", contract, "dataset has fewer rows than required"))
        columns = {key for row in batch.rows for key in row}
        missing = tuple(sorted(set(contract.required_columns) - columns))
        if missing:
            errors.append(
                self._error("MISSING_COLUMN", contract, f"missing required columns: {missing}", missing)
            )
        missing_values = tuple(
            f"row={index},column={column}"
            for index, row in enumerate(batch.rows)
            for column in contract.required_columns
            if column not in row or row[column] is None
        )
        if missing_values:
            errors.append(
                self._error(
                    "MISSING_VALUE",
                    contract,
                    "required values are missing",
                    missing_values,
                )
            )
        errors.extend(self._validate_column_types(batch, contract))
        if contract.primary_key and not missing:
            duplicates = self._duplicate_keys(batch.rows, contract.primary_key)
            if duplicates:
                errors.append(self._error("DUPLICATE_KEY", contract, "duplicate primary keys", duplicates))
        if any(
            item.available_at > as_of or item.effective_at > as_of for item in batch.field_provenance.values()
        ):
            errors.append(self._error("FUTURE_DATA", contract, "field is not available at as_of"))
        if any(
            as_of - item.available_at > contract.max_age or as_of - item.effective_at > contract.max_age
            for item in batch.field_provenance.values()
        ):
            errors.append(self._error("STALE_DATA", contract, "one or more required fields are stale"))
        errors.extend(self._validate_row_times(batch, contract, as_of))
        errors.extend(self._validate_non_negative(batch, contract))
        if contract.check_ohlc:
            errors.extend(self._validate_ohlc(batch, contract))
        return errors

    def _validate_column_types(self, batch: DataBatch, contract: DataContract) -> list[QualityError]:
        affected: list[str] = []
        for index, row in enumerate(batch.rows):
            for column, expected in contract.column_types.items():
                value = row.get(column)
                if value is None:
                    continue
                valid = True
                if expected == "string":
                    valid = isinstance(value, str)
                elif expected == "number":
                    try:
                        float(value)
                    except (TypeError, ValueError):
                        valid = False
                elif expected == "boolean":
                    valid = isinstance(value, bool)
                elif expected == "datetime":
                    try:
                        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    except ValueError:
                        valid = False
                if not valid:
                    affected.append(f"row={index},column={column},expected={expected}")
        if affected:
            return [self._error("TYPE_ERROR", contract, "column type validation failed", affected)]
        return []

    @staticmethod
    def _duplicate_keys(rows: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[tuple[Any, ...]] = set()
        duplicates: list[str] = []
        for row in rows:
            key = tuple(row.get(column) for column in keys)
            if key in seen:
                duplicates.append("|".join(str(value) for value in key))
            seen.add(key)
        return tuple(duplicates)

    def _validate_non_negative(self, batch: DataBatch, contract: DataContract) -> list[QualityError]:
        affected: list[str] = []
        for index, row in enumerate(batch.rows):
            for column in contract.non_negative_columns:
                value = row.get(column)
                if value is None:
                    continue
                try:
                    if float(value) < 0:
                        affected.append(f"row={index},column={column}")
                except (TypeError, ValueError):
                    return [
                        self._error(
                            "TYPE_ERROR",
                            contract,
                            "non-numeric value in numeric column",
                            (f"row={index},column={column}",),
                        )
                    ]
        if affected:
            return [
                self._error("NEGATIVE_VALUE", contract, "negative value in non-negative column", affected)
            ]
        return []

    def _validate_ohlc(self, batch: DataBatch, contract: DataContract) -> list[QualityError]:
        affected: list[str] = []
        for index, row in enumerate(batch.rows):
            if not {"open", "high", "low", "close"}.issubset(row):
                continue
            if any(row[column] is None for column in ("open", "high", "low", "close")):
                continue
            try:
                open_price = float(row["open"])
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
            except (TypeError, ValueError):
                return [self._error("TYPE_ERROR", contract, "non-numeric OHLC value", (f"row={index}",))]
            if low > min(open_price, close) or high < max(open_price, close) or high < low:
                affected.append(str(index))
        if affected:
            return [self._error("INVALID_OHLC", contract, "OHLC relationship is invalid", affected)]
        return []

    def _validate_row_times(
        self, batch: DataBatch, contract: DataContract, as_of: datetime
    ) -> list[QualityError]:
        affected: list[str] = []
        invalid: list[str] = []
        stale: list[str] = []
        for index, row in enumerate(batch.rows):
            value = row.get("effective_at")
            if value is None:
                continue
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                observed_date = parsed.date()
            except ValueError:
                try:
                    observed_date = datetime.strptime(str(value), "%Y-%m-%d").date()
                except ValueError:
                    invalid.append(str(index))
                    continue
            if observed_date > as_of.date():
                affected.append(str(index))
        if contract.row_available_at_column:
            column = contract.row_available_at_column
            for index, row in enumerate(batch.rows):
                value = row.get(column)
                if value is None:
                    invalid.append(f"row={index},column={column}")
                    continue
                try:
                    available_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    if available_at.tzinfo is None:
                        raise ValueError
                except ValueError:
                    invalid.append(f"row={index},column={column}")
                    continue
                if available_at > as_of:
                    affected.append(f"row={index},column={column}")
                elif as_of - available_at > contract.max_age:
                    stale.append(f"row={index},column={column}")
        errors = []
        if affected:
            errors.append(self._error("FUTURE_DATA", contract, "row effective_at is in the future", affected))
        if invalid:
            errors.append(self._error("TYPE_ERROR", contract, "invalid effective_at", invalid))
        if stale:
            errors.append(self._error("STALE_DATA", contract, "row available_at is stale", stale))
        return errors

    @staticmethod
    def _error(
        code: str,
        contract: DataContract,
        message: str,
        affected: tuple[str, ...] | list[str] = (),
    ) -> QualityError:
        return QualityError(
            code=code, dataset=contract.dataset, message=message, affected_keys=tuple(affected)
        )
