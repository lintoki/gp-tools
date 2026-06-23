from datetime import datetime, timedelta
from typing import Dict, List, Optional

import akshare as ak
import pandas as pd
import requests


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
        return _fetch_tencent_daily_history(code, start_date, end_date)


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
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
        "换手率": "turnover_rate",
    }
    df = raw.rename(columns=mapping)
    required = ["date", "open", "close", "high", "low", "volume", "amount"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"history missing columns: {missing}")

    df = df[required + [column for column in ["pct_chg", "turnover_rate"] if column in df.columns]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    for column in ["open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover_rate"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
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
