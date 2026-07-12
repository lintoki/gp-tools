from __future__ import annotations

from datetime import date
from typing import Self

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class UniverseConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed_prefixes: tuple[str, ...]
    minimum_listing_trading_days: int = Field(ge=0)
    minimum_20d_average_amount: float = Field(ge=0)
    minimum_20d_valid_days: int = Field(ge=1, le=20)


class TradeFlags(BaseModel):
    model_config = ConfigDict(frozen=True)

    suspended: bool = False
    limit_up_locked: bool = False
    limit_down_locked: bool = False


class UniverseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    eligible: tuple[str, ...]
    excluded: dict[str, tuple[str, ...]]
    trade_flags: dict[str, TradeFlags]

    @model_validator(mode="after")
    def require_flags_for_eligible_instruments(self) -> Self:
        missing = sorted(set(self.eligible) - set(self.trade_flags))
        if missing:
            raise ValueError(f"eligible instruments missing trade flags: {missing}")
        overlap = sorted(set(self.eligible) & set(self.excluded))
        if overlap:
            raise ValueError(f"eligible instruments also excluded: {overlap}")
        return self


class UniverseBuilder:
    def __init__(self, config: UniverseConfig) -> None:
        self.config = config

    def build(self, as_of: date, securities: pd.DataFrame, bars: pd.DataFrame) -> UniverseResult:
        eligible: list[str] = []
        excluded: dict[str, tuple[str, ...]] = {}
        flags: dict[str, TradeFlags] = {}
        prepared_bars = bars.copy()
        if not prepared_bars.empty:
            required = {
                "instrument_id",
                "effective_at",
                "amount",
                "suspended",
                "limit_up_locked",
                "limit_down_locked",
            }
            missing = sorted(required - set(prepared_bars.columns))
            if missing:
                raise ValueError(f"required trade status columns are missing: {missing}")
            prepared_bars["effective_at"] = pd.to_datetime(prepared_bars["effective_at"]).dt.date
            prepared_bars = prepared_bars[prepared_bars["effective_at"] <= as_of]

        for security in securities.to_dict(orient="records"):
            instrument = str(security["instrument_id"])
            reasons: list[str] = []
            code = instrument[2:] if instrument[:2] in {"SH", "SZ", "BJ"} else instrument
            if not code.startswith(self.config.allowed_prefixes):
                reasons.append("BOARD_EXCLUDED")
            name = str(security.get("name", ""))
            if bool(security.get("is_st", False)) or "ST" in name.upper():
                reasons.append("ST_EXCLUDED")
            if "退" in name or self._delisted_by_as_of(security.get("delist_date"), as_of):
                reasons.append("DELISTING_EXCLUDED")
            list_date = pd.Timestamp(security["list_date"]).date()
            listing_trading_days = len(pd.bdate_range(start=list_date, end=as_of, inclusive="left"))
            if listing_trading_days < self.config.minimum_listing_trading_days:
                reasons.append("TOO_NEW")

            history = prepared_bars[prepared_bars["instrument_id"] == instrument].sort_values("effective_at")
            if history.empty:
                reasons.append("NO_BARS")
                flags[instrument] = TradeFlags(suspended=True)
            else:
                recent = history.tail(20)
                valid = recent[~recent["suspended"].astype(bool)]
                average_amount = float(valid["amount"].mean()) if not valid.empty else 0.0
                if (
                    len(valid) < self.config.minimum_20d_valid_days
                    or average_amount < self.config.minimum_20d_average_amount
                ):
                    reasons.append("ILLIQUID")
                last = history.iloc[-1]
                flags[instrument] = TradeFlags(
                    suspended=bool(last.get("suspended", False)),
                    limit_up_locked=bool(last.get("limit_up_locked", False)),
                    limit_down_locked=bool(last.get("limit_down_locked", False)),
                )

            if reasons:
                excluded[instrument] = tuple(dict.fromkeys(reasons))
            else:
                eligible.append(instrument)

        return UniverseResult(
            as_of=as_of,
            eligible=tuple(sorted(eligible)),
            excluded=excluded,
            trade_flags=flags,
        )

    @staticmethod
    def _delisted_by_as_of(value, as_of: date) -> bool:
        if value is None or pd.isna(value):
            return False
        return pd.Timestamp(value).date() <= as_of
