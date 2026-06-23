import contextlib
import io
import json
import math
import subprocess
import time as time_module
import urllib.parse
import urllib.request
import warnings
from datetime import date, datetime, time
from typing import Any, Iterable, List, Optional, Union

from .models import DailyBar, MarketSnapshot, MinuteBar
from .strategy import is_main_board, normalize_code


EASTMONEY_CLIST_URL = "http://82.push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_ULIST_URL = "http://push2.eastmoney.com/api/qt/ulist.np/get"
EASTMONEY_HIST_URL = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_TRENDS_URL = "http://push2his.eastmoney.com/api/qt/stock/trends2/get"
EASTMONEY_FIELDS = (
    "f2,f3,f6,f8,f10,f12,f14,f15,f16,f17,f18,f20"
)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("%", "")
        if value in {"", "-", "--", "None", "nan", "NaN"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _required_float(row: Any, field: str) -> float:
    value = _to_float(_row_get(row, field))
    if value is None:
        raise ValueError(f"字段 {field} 缺失或不是数字")
    return value


def _row_get(row: Any, field: str) -> Any:
    if hasattr(row, "get"):
        return row.get(field)
    return row[field]


def dataframe_to_spot_snapshots(df: Any) -> List[MarketSnapshot]:
    snapshots: List[MarketSnapshot] = []
    for _, row in df.iterrows():
        code = normalize_code(str(_row_get(row, "代码")))
        snapshots.append(
            MarketSnapshot(
                code=code,
                name=str(_row_get(row, "名称") or ""),
                latest_price=_to_float(_row_get(row, "最新价")),
                change_pct=_to_float(_row_get(row, "涨跌幅")),
                volume_ratio=_to_float(_row_get(row, "量比")),
                turnover_pct=_to_float(_row_get(row, "换手率")),
                total_market_value_yuan=_to_float(_row_get(row, "总市值")),
                high_price=_to_float(_row_get(row, "最高")),
                low_price=_to_float(_row_get(row, "最低")),
                open_price=_to_float(_row_get(row, "今开")),
                prev_close=_to_float(_row_get(row, "昨收")),
                amount_yuan=_to_float(_row_get(row, "成交额")),
            )
        )
    return snapshots


def dataframe_to_legacy_spot_snapshots(df: Any) -> List[MarketSnapshot]:
    snapshots: List[MarketSnapshot] = []
    for _, row in df.iterrows():
        raw_code = str(_row_get(row, "代码") or "")
        code = normalize_code(raw_code[-6:])
        snapshots.append(
            MarketSnapshot(
                code=code,
                name=str(_row_get(row, "名称") or ""),
                latest_price=_to_float(_row_get(row, "最新价")),
                change_pct=_to_float(_row_get(row, "涨跌幅")),
                volume_ratio=None,
                turnover_pct=None,
                total_market_value_yuan=None,
                high_price=_to_float(_row_get(row, "最高")),
                low_price=_to_float(_row_get(row, "最低")),
                open_price=_to_float(_row_get(row, "今开")),
                prev_close=_to_float(_row_get(row, "昨收")),
                amount_yuan=_to_float(_row_get(row, "成交额")),
            )
        )
    return snapshots


def eastmoney_diff_to_spot_snapshots(rows: Iterable[Any]) -> List[MarketSnapshot]:
    snapshots: List[MarketSnapshot] = []
    for row in rows:
        code = str(_row_get(row, "f12") or "").strip()
        if not code.isdigit() or len(code) != 6:
            continue
        snapshots.append(
            MarketSnapshot(
                code=normalize_code(code),
                name=str(_row_get(row, "f14") or ""),
                latest_price=_to_float(_row_get(row, "f2")),
                change_pct=_to_float(_row_get(row, "f3")),
                volume_ratio=_to_float(_row_get(row, "f10")),
                turnover_pct=_to_float(_row_get(row, "f8")),
                total_market_value_yuan=_to_float(_row_get(row, "f20")),
                high_price=_to_float(_row_get(row, "f15")),
                low_price=_to_float(_row_get(row, "f16")),
                open_price=_to_float(_row_get(row, "f17")),
                prev_close=_to_float(_row_get(row, "f18")),
                amount_yuan=_to_float(_row_get(row, "f6")),
            )
        )
    return snapshots


def _eastmoney_url(params: dict) -> str:
    return EASTMONEY_CLIST_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _eastmoney_ulist_url(params: dict) -> str:
    return EASTMONEY_ULIST_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def fetch_eastmoney_spot_snapshots(page_size: int = 100, max_pages: int = 4) -> List[MarketSnapshot]:
    snapshots_by_code = {}
    empty_stock_pages = 0
    failed_pages = 0
    for page in range(1, max_pages + 1):
        params = {
            "pn": str(page),
            "pz": str(page_size),
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": EASTMONEY_FIELDS,
        }
        try:
            payload = _fetch_eastmoney_page(params)
        except Exception:
            failed_pages += 1
            if snapshots_by_code and failed_pages >= 3:
                break
            if not snapshots_by_code and failed_pages >= 5:
                raise
            continue
        failed_pages = 0
        if payload.get("rc") != 0:
            raise RuntimeError(f"东方财富实时接口返回异常: {payload}")
        rows = (payload.get("data") or {}).get("diff") or []
        page_snapshots = eastmoney_diff_to_spot_snapshots(rows)
        if not page_snapshots:
            empty_stock_pages += 1
            if empty_stock_pages >= 3:
                break
            continue
        empty_stock_pages = 0
        for snapshot in page_snapshots:
            snapshots_by_code[snapshot.code] = snapshot
        min_change = min(
            (snapshot.change_pct for snapshot in page_snapshots if snapshot.change_pct is not None),
            default=None,
        )
        if min_change is not None and min_change < 2.5:
            break
    snapshots = list(snapshots_by_code.values())
    if not snapshots:
        raise RuntimeError("东方财富实时接口未返回 6 位 A 股代码")
    return snapshots


def _secid(code: str) -> str:
    normalized = normalize_code(code)
    prefix = "1" if normalized.startswith("6") else "0"
    return f"{prefix}.{normalized}"


def fetch_eastmoney_ulist_snapshots(codes: Iterable[str], batch_size: int = 80) -> List[MarketSnapshot]:
    code_list = [normalize_code(code) for code in codes]
    snapshots_by_code = {}
    for start in range(0, len(code_list), batch_size):
        batch = code_list[start : start + batch_size]
        if not batch:
            continue
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": EASTMONEY_FIELDS,
            "secids": ",".join(_secid(code) for code in batch),
        }
        payload = _fetch_json_url(_eastmoney_ulist_url(params))
        if payload.get("rc") != 0:
            raise RuntimeError(f"东方财富 ulist 接口返回异常: {payload}")
        rows = (payload.get("data") or {}).get("diff") or []
        for snapshot in eastmoney_diff_to_spot_snapshots(rows):
            snapshots_by_code[snapshot.code] = snapshot
    return [snapshots_by_code[code] for code in code_list if code in snapshots_by_code]


def fetch_legacy_enriched_spot_snapshots() -> List[MarketSnapshot]:
    ak = _load_akshare()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        df = ak.stock_zh_a_spot()
    base_snapshots = dataframe_to_legacy_spot_snapshots(df)
    candidate_codes = [
        snapshot.code
        for snapshot in base_snapshots
        if is_main_board(snapshot.code)
        and snapshot.change_pct is not None
        and 3.0 <= snapshot.change_pct <= 5.2
    ]
    enriched = fetch_eastmoney_ulist_snapshots(candidate_codes)
    if not enriched:
        raise RuntimeError("旧实时接口候选未能通过 ulist 补充字段")
    return enriched


def _fetch_eastmoney_page(params: dict) -> dict:
    url = _eastmoney_url(params)
    return _fetch_json_url(url)


def _fetch_json_url(url: str) -> dict:
    last_error: Optional[Exception] = None
    for attempt in range(3):
        if attempt:
            time_module.sleep(0.5 * attempt)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://quote.eastmoney.com/center/gridlist.html",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
    try:
        completed = subprocess.run(
            [
                "curl",
                "-sS",
                "--max-time",
                "15",
                "-A",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "-e",
                "https://quote.eastmoney.com/center/gridlist.html",
                url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)
    except Exception as exc:
        raise RuntimeError(f"东方财富实时接口连续失败: {last_error}; curl 兜底失败: {exc}") from exc


def dataframe_to_daily_bars(df: Any) -> List[DailyBar]:
    bars: List[DailyBar] = []
    for _, row in df.iterrows():
        bars.append(
            DailyBar(
                date=str(_row_get(row, "日期")),
                open=_required_float(row, "开盘"),
                high=_required_float(row, "最高"),
                low=_required_float(row, "最低"),
                close=_required_float(row, "收盘"),
                change_pct=_required_float(row, "涨跌幅"),
                turnover_pct=_to_float(_row_get(row, "换手率")),
                volume=_to_float(_row_get(row, "成交量")),
                amount_yuan=_to_float(_row_get(row, "成交额")),
            )
        )
    return bars


def eastmoney_klines_to_daily_bars(klines: Iterable[str]) -> List[DailyBar]:
    bars: List[DailyBar] = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 11:
            continue
        bars.append(
            DailyBar(
                date=parts[0],
                open=float(parts[1]),
                close=float(parts[2]),
                high=float(parts[3]),
                low=float(parts[4]),
                change_pct=float(parts[8]),
                turnover_pct=_to_float(parts[10]),
                volume=_to_float(parts[5]),
                amount_yuan=_to_float(parts[6]),
            )
        )
    return bars


def dataframe_to_minute_bars(df: Any) -> List[MinuteBar]:
    bars: List[MinuteBar] = []
    for _, row in df.iterrows():
        bars.append(
            MinuteBar(
                time=str(_row_get(row, "时间")),
                open=_required_float(row, "开盘"),
                high=_required_float(row, "最高"),
                low=_required_float(row, "最低"),
                close=_required_float(row, "收盘"),
                volume=_required_float(row, "成交量"),
                amount=_required_float(row, "成交额"),
                avg_price=_to_float(_row_get(row, "均价")),
            )
        )
    return bars


def eastmoney_trends_to_minute_bars(trends: Iterable[str], trading_date: str) -> List[MinuteBar]:
    bars: List[MinuteBar] = []
    prefix = dashed_date(trading_date)
    for item in trends:
        parts = str(item).split(",")
        if len(parts) < 8:
            continue
        timestamp = parts[0]
        if not timestamp.startswith(prefix):
            continue
        if len(timestamp) == 16:
            timestamp = f"{timestamp}:00"
        bars.append(
            MinuteBar(
                time=timestamp,
                open=float(parts[1]),
                close=float(parts[2]),
                high=float(parts[3]),
                low=float(parts[4]),
                volume=float(parts[5]),
                amount=float(parts[6]),
                avg_price=_to_float(parts[7]),
            )
        )
    return bars


def _load_akshare() -> Any:
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("缺少依赖 akshare，请先执行: pip install -r requirements.txt") from exc
    return ak


def fetch_spot_snapshots() -> List[MarketSnapshot]:
    errors: List[str] = []
    try:
        return fetch_legacy_enriched_spot_snapshots()
    except Exception as exc:
        errors.append(f"AKShare 旧实时接口 + 东方财富 ulist 失败: {exc}")

    try:
        return fetch_eastmoney_spot_snapshots()
    except Exception as exc:
        errors.append(f"东方财富直连接口失败: {exc}")

    try:
        ak = _load_akshare()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            df = ak.stock_zh_a_spot_em()
        snapshots = [snapshot for snapshot in dataframe_to_spot_snapshots(df) if snapshot.code.isdigit()]
        if snapshots:
            return snapshots
        errors.append("AKShare 全市场接口没有返回 6 位 A 股代码")
    except Exception as exc:
        errors.append(f"AKShare 全市场接口失败: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_daily_bars(code: str, start_date: str, end_date: str, adjust: str = "") -> List[DailyBar]:
    errors: List[str] = []
    try:
        return fetch_eastmoney_daily_bars(code, start_date, end_date, adjust)
    except Exception as exc:
        errors.append(f"东方财富日线直连失败: {exc}")
    try:
        ak = _load_akshare()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            df = ak.stock_zh_a_hist(
                symbol=normalize_code(code),
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
        return dataframe_to_daily_bars(df)
    except Exception as exc:
        errors.append(f"AKShare 日线失败: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_eastmoney_daily_bars(code: str, start_date: str, end_date: str, adjust: str = "") -> List[DailyBar]:
    normalized = normalize_code(code)
    adjust_dict = {"qfq": "1", "hfq": "2", "": "0"}
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101",
        "fqt": adjust_dict.get(adjust, "0"),
        "secid": _secid(normalized),
        "beg": compact_date(start_date),
        "end": compact_date(end_date),
    }
    payload = _fetch_json_url(EASTMONEY_HIST_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))
    klines = (payload.get("data") or {}).get("klines") or []
    return eastmoney_klines_to_daily_bars(klines)


def fetch_minute_bars(code: str, trading_date: str, period: str = "1") -> List[MinuteBar]:
    errors: List[str] = []
    if period == "1":
        try:
            return fetch_eastmoney_minute_bars(code, trading_date)
        except Exception as exc:
            errors.append(f"东方财富分时直连失败: {exc}")
    try:
        ak = _load_akshare()
        start_date = f"{trading_date} 09:30:00"
        end_date = f"{trading_date} 15:00:00"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            df = ak.stock_zh_a_hist_min_em(
                symbol=normalize_code(code),
                start_date=start_date,
                end_date=end_date,
                period=period,
                adjust="",
            )
        return dataframe_to_minute_bars(df)
    except Exception as exc:
        errors.append(f"AKShare 分时失败: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_eastmoney_minute_bars(code: str, trading_date: str) -> List[MinuteBar]:
    normalized = normalize_code(code)
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "ndays": "5",
        "iscr": "0",
        "secid": _secid(normalized),
    }
    payload = _fetch_json_url(EASTMONEY_TRENDS_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))
    trends = (payload.get("data") or {}).get("trends") or []
    return eastmoney_trends_to_minute_bars(trends, dashed_date(trading_date))


def compact_date(value: Union[date, datetime, str]) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value).replace("-", "")[:8]


def dashed_date(value: Union[date, datetime, str]) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    if "-" in text:
        return text[:10]
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def is_after_tail_start(now: datetime, tail_start: str = "14:30:00") -> bool:
    hour, minute, second = [int(part) for part in tail_start.split(":")]
    return now.time() >= time(hour, minute, second)
