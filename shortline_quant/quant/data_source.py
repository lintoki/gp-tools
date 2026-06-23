from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd


REQUIRED_COLUMNS = {
    "date",
    "code",
    "name",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
}

OPTIONAL_DEFAULTS = {
    "pct_chg": 0.0,
    "volume_ratio": 1.0,
    "turnover_rate": 6.0,
    "market_cap_billion": 100.0,
    "has_limit_up_20d": 0,
    "relative_strength": 0.0,
    "above_vwap": 1,
    "ma5_gt_ma30": 1,
    "close_near_high": 0.5,
}


def cache_dir(data_dir: Path) -> Path:
    return data_dir / "cache"


def daily_csv_path(data_dir: Path, symbol: str) -> Path:
    return cache_dir(data_dir) / f"{symbol}_daily.csv"


def list_universe_symbols(data_dir: Path) -> List[str]:
    cache = cache_dir(data_dir)
    if not cache.exists():
        return []
    symbols = []
    for path in sorted(cache.glob("*_daily.csv")):
        symbols.append(path.name[: -len("_daily.csv")])
    return symbols


def ensure_sample_data(data_dir: Path) -> None:
    cache = cache_dir(data_dir)
    cache.mkdir(parents=True, exist_ok=True)
    if list(cache.glob("*_daily.csv")):
        return
    for symbol, name, base_price in [
        ("DEMO1", "示例强势股一", 22.0),
        ("DEMO2", "示例强势股二", 36.0),
    ]:
        path = daily_csv_path(data_dir, symbol)
        if not path.exists():
            _build_sample_bars(symbol, name, base_price).to_csv(path, index=False)


def load_daily_bars(
    data_dir: Path,
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    path = daily_csv_path(data_dir, symbol)
    if not path.exists():
        raise FileNotFoundError(f"daily data not found for {symbol}: {path}")

    df = pd.read_csv(path, dtype={"code": str})
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default

    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    df = df.sort_values("date").set_index("date")
    return df


def _build_sample_bars(symbol: str, name: str, base_price: float) -> pd.DataFrame:
    dates = pd.bdate_range(date(2025, 1, 2), periods=90)
    rows = []
    last_close = base_price
    for idx, day in enumerate(dates):
        signal_day = idx % 13 == 8
        tail_day = idx % 17 == 11
        drift = 0.003 if idx % 5 else -0.002
        open_price = last_close * (1 + drift)
        if signal_day:
            close_price = open_price * 1.038
            pct_chg = 3.8
            volume_ratio = 1.45
            turnover = 7.2
            market_cap = 118.0
            has_limit = 1
            rel_strength = 2.5
            above_vwap = 1
            ma5_gt_ma30 = 1
            close_near_high = 0.86
        elif tail_day:
            close_price = open_price * 1.025
            pct_chg = 2.5
            volume_ratio = 1.3
            turnover = 6.6
            market_cap = 132.0
            has_limit = 1
            rel_strength = 1.1
            above_vwap = 1
            ma5_gt_ma30 = 1
            close_near_high = 0.9
        else:
            wave = ((idx % 7) - 3) / 1000
            close_price = open_price * (1 + wave)
            pct_chg = (close_price / last_close - 1) * 100
            volume_ratio = 0.9 + (idx % 4) * 0.08
            turnover = 4.0 + (idx % 5)
            market_cap = 118.0
            has_limit = 1 if idx > 20 else 0
            rel_strength = 0.2
            above_vwap = 1 if close_price >= open_price else 0
            ma5_gt_ma30 = 1
            close_near_high = 0.45

        high_price = max(open_price, close_price) * 1.006
        low_price = min(open_price, close_price) * 0.992
        volume = 900000 + idx * 7000
        rows.append(
            {
                "date": day.date().isoformat(),
                "code": symbol,
                "name": name,
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": int(volume),
                "amount": round(volume * close_price, 2),
                "pct_chg": round(pct_chg, 2),
                "volume_ratio": round(volume_ratio, 2),
                "turnover_rate": round(turnover, 2),
                "market_cap_billion": round(market_cap, 2),
                "has_limit_up_20d": has_limit,
                "relative_strength": round(rel_strength, 2),
                "above_vwap": above_vwap,
                "ma5_gt_ma30": ma5_gt_ma30,
                "close_near_high": round(close_near_high, 2),
            }
        )
        last_close = close_price
    return pd.DataFrame(rows)
