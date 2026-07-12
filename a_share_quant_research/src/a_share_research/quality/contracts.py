from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset: str = Field(min_length=1)
    required_columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    minimum_rows: int = Field(default=1, ge=0)
    max_age: timedelta
    required: bool = True
    check_ohlc: bool = False
    non_negative_columns: tuple[str, ...] = ("volume", "amount", "turnover_rate")
    column_types: dict[str, Literal["string", "number", "boolean", "datetime"]] = Field(default_factory=dict)
    row_available_at_column: str | None = None
