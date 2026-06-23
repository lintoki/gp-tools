from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd
import requests

from quant.strategy_config import merge_strategy_config


MAIN_BOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")
DEFAULT_MAX_SYMBOLS: Optional[int] = None


def fetch_a_share_bars(
    start_date: str,
    end_date: str,
    max_symbols: Optional[int] = DEFAULT_MAX_SYMBOLS,
) -> Dict[str, pd.DataFrame]:
    stock_list = ak.stock_info_a_code_name()
    candidates = _normalize_stock_list(stock_list)
    if max_symbols is not None:
        candidates = candidates[:max_symbols]
    fetch_end_date = _extend_end_date(end_date)
    bars_by_symbol: Dict[str, pd.DataFrame] = {}

    for item in candidates:
        code = item["code"]
        name = item["name"]
        try:
            raw = _fetch_daily_history(code, start_date, fetch_end_date)
            normalized = _normalize_daily_history(raw, code, name)
            bars = _to_indexed_bars(normalized)
            if not bars.empty:
                bars_by_symbol[code] = bars
        except Exception:
            continue
    return bars_by_symbol


def fetch_ranked_backtest_bars(
    start_date: str,
    end_date: str,
    max_symbols: Optional[int] = DEFAULT_MAX_SYMBOLS,
    strategy_id: Optional[str] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, pd.DataFrame]:
    config = _ranked_strategy_config(strategy_id, strategy_config)
    signal_rows = _fetch_ranked_signal_rows(start_date, end_date, config)
    if not signal_rows:
        return {}

    limit_up_counts = _fetch_limit_up_counts(start_date, end_date)
    signal_rows = _prefilter_ranked_signal_rows(signal_rows, limit_up_counts, strategy_id, config)
    if max_symbols is not None:
        signal_rows = signal_rows[:max_symbols]
    if not signal_rows:
        return {}

    rows_by_code: Dict[str, List[Dict[str, Any]]] = {}
    for row in signal_rows:
        rows_by_code.setdefault(row["code"], []).append(row)

    fetch_end_date = _extend_end_date(end_date)
    bars_by_symbol: Dict[str, pd.DataFrame] = {}
    for code, rows in rows_by_code.items():
        try:
            first_signal_date = min(row["trade_date"] for row in rows)
            raw = _fetch_daily_history(code, first_signal_date, fetch_end_date)
            normalized = _normalize_daily_history(raw, code, rows[0]["name"])
            enriched = _apply_ranked_signal_fields(normalized, rows, limit_up_counts)
            bars = _to_indexed_bars(enriched)
            if not bars.empty:
                bars_by_symbol[code] = bars
        except Exception:
            continue
    return bars_by_symbol


def fetch_recent_a_share_bars(max_symbols: Optional[int] = DEFAULT_MAX_SYMBOLS) -> Dict[str, pd.DataFrame]:
    end = datetime.now().date()
    start = end - timedelta(days=90)
    return fetch_a_share_bars(
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        max_symbols=max_symbols,
    )


def _fetch_daily_history(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        return ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
            timeout=10,
        )
    except Exception:
        pass
    try:
        return ak.stock_zh_a_hist_tx(
            symbol=_tencent_market_code(code),
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
            timeout=10,
        )
    except Exception:
        pass
    try:
        return ak.stock_zh_a_daily(
            symbol=_tencent_market_code(code),
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
    except Exception:
        return _fetch_tencent_daily_history(code, start_date, end_date)


def _fetch_ranked_signal_rows(start_date: str, end_date: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for trade_date in _iter_weekdays(start_date, end_date):
        try:
            raw = ak.stock_zt_pool_strong_em(date=trade_date.replace("-", ""))
        except Exception:
            continue
        rows.extend(_normalize_ranked_pool(raw, trade_date, config))
    return rows


def _normalize_ranked_pool(raw: pd.DataFrame, trade_date: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    if raw is None or raw.empty or "代码" not in raw.columns:
        return []

    rows: List[Dict[str, Any]] = []
    for _, item in raw.iterrows():
        code = str(item.get("代码", "")).zfill(6)
        name = str(item.get("名称", ""))
        pct_chg = _safe_float(item.get("涨跌幅"), 0.0)
        if not _is_ranked_backtest_candidate(code, name, pct_chg, config):
            continue
        rows.append(
            {
                "code": code,
                "name": name,
                "trade_date": trade_date,
                "close": _safe_float(item.get("最新价"), 0.0),
                "pct_chg": pct_chg,
                "volume_ratio": _safe_float(item.get("量比"), 1.0),
                "turnover_rate": _safe_float(item.get("换手率"), 0.0),
                "market_cap_billion": _safe_float(item.get("总市值"), 0.0) / 100000000,
                "amount": _safe_float(item.get("成交额"), 0.0),
                "is_intraday_high": str(item.get("是否新高", "")) == "是",
            }
        )
    return rows


def _is_ranked_backtest_candidate(code: str, name: str, pct_chg: float, config: Dict[str, Any]) -> bool:
    if not code.startswith(MAIN_BOARD_PREFIXES):
        return False
    if _is_st_or_delist_name(name):
        return False
    c_cfg = _level_config(config, "C")
    return _between_cfg(pct_chg, c_cfg, "pct_chg")


def _prefilter_ranked_signal_rows(
    signal_rows: List[Dict[str, Any]],
    limit_up_counts: Dict[str, Dict[str, int]],
    strategy_id: Optional[str],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    c_cfg = _level_config(config, "C")
    filtered = []
    for row in signal_rows:
        if row["volume_ratio"] < c_cfg.get("min_volume_ratio", 0.8):
            continue
        if not _between_cfg(row["turnover_rate"], c_cfg, "turnover_rate"):
            continue
        if not _between_cfg(row["market_cap_billion"], c_cfg, "market_cap_billion"):
            continue
        filtered.append(row)
    return filtered


def _ranked_strategy_config(strategy_id: Optional[str], strategy_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if strategy_id:
        try:
            return merge_strategy_config(strategy_id, strategy_config or {})
        except KeyError:
            pass
    return strategy_config or {
        "levels": {
            "C": {
                "min_pct_chg": 2.0,
                "max_pct_chg": 6.0,
                "min_volume_ratio": 0.8,
                "min_turnover_rate": 3.0,
                "max_turnover_rate": 12.0,
                "min_market_cap_billion": 40.0,
                "max_market_cap_billion": 250.0,
            }
        }
    }


def _level_config(config: Dict[str, Any], level: str) -> Dict[str, Any]:
    return config.get("levels", {}).get(level, {})


def _between_cfg(value: float, cfg: Dict[str, Any], key: str) -> bool:
    return float(cfg.get(f"min_{key}", float("-inf"))) <= float(value) <= float(cfg.get(f"max_{key}", float("inf")))


def _fetch_limit_up_counts(start_date: str, end_date: str) -> Dict[str, Dict[str, int]]:
    limit_up_dates_by_code: Dict[str, set] = {}
    lookback_start = (datetime.strptime(start_date, "%Y-%m-%d").date() - timedelta(days=45)).strftime("%Y-%m-%d")
    for trade_date in _iter_weekdays(lookback_start, end_date):
        try:
            raw = ak.stock_zt_pool_em(date=trade_date.replace("-", ""))
        except Exception:
            continue
        if raw is None or raw.empty or "代码" not in raw.columns:
            continue
        for value in raw["代码"]:
            code = str(value).zfill(6)
            limit_up_dates_by_code.setdefault(code, set()).add(trade_date)

    counts_by_signal_date: Dict[str, Dict[str, int]] = {}
    for signal_date in _iter_weekdays(start_date, end_date):
        current = datetime.strptime(signal_date, "%Y-%m-%d").date()
        lookback_floor = current - timedelta(days=35)
        counts_by_signal_date[signal_date] = {
            code: sum(
                1
                for item in dates
                if lookback_floor <= datetime.strptime(item, "%Y-%m-%d").date() < current
            )
            for code, dates in limit_up_dates_by_code.items()
        }
    return counts_by_signal_date


def _apply_ranked_signal_fields(
    df: pd.DataFrame,
    signal_rows: List[Dict[str, Any]],
    limit_up_counts: Dict[str, Dict[str, int]],
) -> pd.DataFrame:
    if df.empty:
        return df
    enriched = df.copy()
    for row in signal_rows:
        mask = enriched["date"] == row["trade_date"]
        if not mask.any():
            continue
        enriched.loc[mask, "name"] = row["name"]
        if row["close"] > 0:
            enriched.loc[mask, "close"] = row["close"]
        enriched.loc[mask, "pct_chg"] = row["pct_chg"]
        enriched.loc[mask, "volume_ratio"] = row["volume_ratio"]
        enriched.loc[mask, "turnover_rate"] = row["turnover_rate"]
        enriched.loc[mask, "market_cap_billion"] = row["market_cap_billion"]
        enriched.loc[mask, "relative_strength"] = row["pct_chg"]
        close_price = float(enriched.loc[mask, "close"].iloc[0])
        open_price = float(enriched.loc[mask, "open"].iloc[0])
        enriched.loc[mask, "above_vwap"] = 1 if close_price >= open_price else 0
        if row["is_intraday_high"]:
            enriched.loc[mask, "close_near_high"] = 0.9
        enriched.loc[mask, "has_limit_up_20d"] = limit_up_counts.get(row["trade_date"], {}).get(row["code"], 0)
    return enriched


def _iter_weekdays(start_date: str, end_date: str) -> List[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _safe_float(value: Any, default: float) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_st_or_delist_name(name: str) -> bool:
    normalized = name.upper()
    return "ST" in normalized or "退" in name or "退市" in name


def _fetch_tencent_daily_history(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    market_code = _tencent_market_code(code)
    response = requests.get(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": f"{market_code},day,{start_date},{end_date},640,qfq"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", {}).get(market_code, {})
    rows = data.get("qfqday") or data.get("day") or []
    normalized_rows = []
    for row in rows:
        trade_date, open_price, close_price, high_price, low_price, volume = row[:6]
        close_float = float(close_price)
        normalized_rows.append(
            {
                "日期": trade_date,
                "开盘": float(open_price),
                "收盘": close_float,
                "最高": float(high_price),
                "最低": float(low_price),
                "成交量": float(volume),
                "成交额": float(volume) * close_float,
            }
        )
    return pd.DataFrame(normalized_rows)


def _tencent_market_code(code: str) -> str:
    return f"sh{code}" if code.startswith("6") else f"sz{code}"


def _normalize_stock_list(stock_list: pd.DataFrame) -> List[Dict[str, str]]:
    code_col = "code" if "code" in stock_list.columns else "代码"
    name_col = "name" if "name" in stock_list.columns else "名称"
    rows = []
    for _, row in stock_list.iterrows():
        code = str(row[code_col]).zfill(6)
        if not code.startswith(MAIN_BOARD_PREFIXES):
            continue
        rows.append({"code": code, "name": str(row[name_col])})
    return rows


def _normalize_daily_history(raw: pd.DataFrame, code: str, name: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()

    mapping = {
        "date": "date",
        "日期": "date",
        "open": "open",
        "开盘": "open",
        "close": "close",
        "收盘": "close",
        "high": "high",
        "最高": "high",
        "low": "low",
        "最低": "low",
        "volume": "volume",
        "成交量": "volume",
        "amount": "amount",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
        "换手率": "turnover_rate",
        "turnover": "turnover_rate",
    }
    df = raw.rename(columns=mapping)
    if "volume" not in df.columns and "amount" in df.columns:
        df["volume"] = df["amount"]
    if "amount" not in df.columns and "volume" in df.columns and "close" in df.columns:
        df["amount"] = df["volume"] * df["close"]
    required = ["date", "open", "close", "high", "low", "volume", "amount"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"history missing columns: {missing}")

    df = df[required + [column for column in ["pct_chg", "turnover_rate"] if column in df.columns]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    for column in ["open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover_rate"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "turnover_rate" in df.columns and df["turnover_rate"].max(skipna=True) <= 1:
        df["turnover_rate"] = df["turnover_rate"] * 100
    df = df.dropna(subset=["open", "close", "high", "low"]).sort_values("date")
    df["code"] = code
    df["name"] = name
    if "pct_chg" not in df.columns:
        df["pct_chg"] = df["close"].pct_change().fillna(0) * 100
    if "turnover_rate" not in df.columns:
        df["turnover_rate"] = 6.0

    prev_avg_volume = df["volume"].shift(1).rolling(5, min_periods=1).mean()
    df["volume_ratio"] = (df["volume"] / prev_avg_volume).replace([float("inf"), -float("inf")], 1.0).fillna(1.0)
    df["has_limit_up_20d"] = (
        (df["pct_chg"] >= 9.5).shift(1).rolling(20, min_periods=1).max().fillna(0).astype(int)
    )
    df["relative_strength"] = df["pct_chg"].fillna(0)
    df["above_vwap"] = (df["close"] >= df["open"]).astype(int)
    ma5 = df["close"].rolling(5, min_periods=1).mean()
    ma30 = df["close"].rolling(30, min_periods=1).mean()
    df["ma5_gt_ma30"] = (ma5 >= ma30).astype(int)
    spread = (df["high"] - df["low"]).replace(0, float("nan"))
    df["close_near_high"] = ((df["close"] - df["low"]) / spread).fillna(0.5).clip(0, 1)
    df["market_cap_billion"] = 100.0

    output_columns = [
        "date",
        "code",
        "name",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
        "volume_ratio",
        "turnover_rate",
        "market_cap_billion",
        "has_limit_up_20d",
        "relative_strength",
        "above_vwap",
        "ma5_gt_ma30",
        "close_near_high",
    ]
    return df[output_columns].round(4)


def _to_indexed_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    bars = df.copy()
    bars["date"] = pd.to_datetime(bars["date"])
    return bars.sort_values("date").set_index("date")


def _extend_end_date(end_date: str) -> str:
    parsed = datetime.strptime(end_date, "%Y-%m-%d").date()
    return (parsed + timedelta(days=10)).strftime("%Y-%m-%d")
