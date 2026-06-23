from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .akshare_source import fetch_eastmoney_ulist_snapshots
from .backtest import BacktestDataProvider
from .models import DailyBar, MarketSnapshot, MinuteBar, StrategyConfig
from .strategy import is_main_board, normalize_code


def _load_baostock() -> Any:
    try:
        import baostock as bs
    except ImportError as exc:
        raise RuntimeError("缺少依赖 baostock，请先执行: python3 -m pip install -r requirements.txt") from exc
    return bs


def _plain_code(baostock_code: str) -> str:
    return normalize_code(str(baostock_code).split(".")[-1])


def _baostock_code(code: str) -> str:
    normalized = normalize_code(code)
    prefix = "sh" if normalized.startswith("6") else "sz"
    return f"{prefix}.{normalized}"


def _rows(result: Any) -> List[Dict[str, str]]:
    fields = list(getattr(result, "fields", []) or [])
    rows: List[Dict[str, str]] = []
    while result.next():
        rows.append(dict(zip(fields, result.get_row_data())))
    return rows


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_baostock_time(value: str) -> str:
    text = str(value)
    if len(text) < 14:
        return text
    return f"{text[:4]}-{text[4:6]}-{text[6:8]} {text[8:10]}:{text[10:12]}:{text[12:14]}"


def _volume_ratio_for_date(bars: List[DailyBar], trading_date: str) -> Optional[float]:
    index = next((idx for idx, bar in enumerate(bars) if bar.date == trading_date), None)
    if index is None:
        return None
    current_volume = bars[index].volume
    previous = [bar.volume for bar in bars[max(0, index - 5) : index] if bar.volume and bar.volume > 0]
    if not current_volume or not previous:
        return None
    return current_volume / (sum(previous) / len(previous))


class BaostockBacktestProvider(BacktestDataProvider):
    def __init__(
        self,
        *,
        max_universe: Optional[int] = None,
        config: Optional[StrategyConfig] = None,
        cap_slack: float = 0.4,
    ):
        self.bs = _load_baostock()
        login = self.bs.login()
        if getattr(login, "error_code", "0") not in {"0", 0}:
            raise RuntimeError(f"Baostock 登录失败: {getattr(login, 'error_msg', '')}")
        self.max_universe = max_universe
        self.config = config or StrategyConfig()
        self.cap_slack = cap_slack
        self._daily_cache: Dict[str, List[DailyBar]] = {}
        self._daily_cache_ranges: Dict[str, tuple[str, str]] = {}
        self._spot_cache: Dict[str, MarketSnapshot] = {}

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.bs.logout()

    def trading_dates_between(self, start_date: str, end_date: str) -> List[str]:
        result = self.bs.query_trade_dates(start_date=start_date, end_date=end_date)
        if result.error_code != "0":
            raise RuntimeError(result.error_msg)
        return [row["calendar_date"] for row in _rows(result) if row.get("is_trading_day") == "1"]

    def next_trading_date(self, trading_date: str) -> Optional[str]:
        start = (datetime.strptime(trading_date, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
        end = (datetime.strptime(trading_date, "%Y-%m-%d").date() + timedelta(days=15)).strftime("%Y-%m-%d")
        dates = self.trading_dates_between(start, end)
        return dates[0] if dates else None

    def snapshots_for_date(self, trading_date: str) -> List[MarketSnapshot]:
        stock_rows = self._stock_rows_for_date(trading_date)
        partials: List[Dict[str, Any]] = []
        checked = 0
        for row in stock_rows:
            code = row["code"]
            checked += 1
            if self.max_universe and checked > self.max_universe:
                break
            try:
                daily_bars = self.daily_bars(code, self._lookback_start(trading_date), trading_date.replace("-", ""))
            except Exception:
                continue
            day_bar = next((bar for bar in daily_bars if bar.date == trading_date), None)
            if day_bar is None:
                continue
            volume_ratio = _volume_ratio_for_date(daily_bars, trading_date)
            if not self._passes_daily_prefilter(day_bar, volume_ratio, daily_bars):
                continue
            partials.append({"row": row, "day_bar": day_bar, "volume_ratio": volume_ratio})

        current_spots = self._current_spots(partial["row"]["code"] for partial in partials)
        snapshots: List[MarketSnapshot] = []
        for partial in partials:
            row = partial["row"]
            code = row["code"]
            day_bar = partial["day_bar"]
            current = current_spots.get(code)
            if current is None or current.latest_price in {None, 0} or current.total_market_value_yuan is None:
                continue
            historical_market_value = current.total_market_value_yuan / float(current.latest_price) * day_bar.close
            if not (
                self.config.min_total_market_value_yuan
                <= historical_market_value
                <= self.config.max_total_market_value_yuan
            ):
                continue
            snapshots.append(
                MarketSnapshot(
                    code=code,
                    name=row["name"],
                    latest_price=day_bar.close,
                    change_pct=day_bar.change_pct,
                    volume_ratio=partial["volume_ratio"],
                    turnover_pct=day_bar.turnover_pct,
                    total_market_value_yuan=historical_market_value,
                    high_price=day_bar.high,
                    low_price=day_bar.low,
                    open_price=day_bar.open,
                    prev_close=day_bar.close / (1 + day_bar.change_pct / 100) if day_bar.change_pct != -100 else None,
                    amount_yuan=day_bar.amount_yuan,
                )
            )
        return snapshots

    def _passes_daily_prefilter(
        self,
        day_bar: DailyBar,
        volume_ratio: Optional[float],
        daily_bars: List[DailyBar],
    ) -> bool:
        if not (self.config.min_change_pct <= day_bar.change_pct <= self.config.max_change_pct):
            return False
        if volume_ratio is None or volume_ratio < self.config.min_volume_ratio:
            return False
        if day_bar.turnover_pct is None:
            return False
        if not (self.config.min_turnover_pct <= day_bar.turnover_pct <= self.config.max_turnover_pct):
            return False
        recent = daily_bars[-self.config.limit_up_lookback_days :]
        limit_up_count = sum(1 for bar in recent if bar.change_pct >= self.config.limit_up_pct)
        return self.config.min_limit_up_count_20 <= limit_up_count <= self.config.max_limit_up_count_20

    def daily_bars(self, code: str, start_date: str, end_date: str) -> List[DailyBar]:
        normalized = normalize_code(code)
        start_text = self._dash_date(start_date)
        end_text = self._dash_date(end_date)
        cached = self._daily_cache.get(normalized)
        cached_range = self._daily_cache_ranges.get(normalized)
        if cached is None or cached_range is None or start_text < cached_range[0] or end_text > cached_range[1]:
            fetch_start = min(start_text, cached_range[0]) if cached_range else start_text
            fetch_end = max(end_text, cached_range[1]) if cached_range else end_text
            cached = self._fetch_daily_bars(normalized, fetch_start, fetch_end)
            self._daily_cache[normalized] = cached
            self._daily_cache_ranges[normalized] = (fetch_start, fetch_end)
        return [bar for bar in cached if start_text <= bar.date <= end_text]

    def minute_bars(self, code: str, trading_date: str) -> List[MinuteBar]:
        result = self.bs.query_history_k_data_plus(
            _baostock_code(code),
            "date,time,code,open,high,low,close,volume,amount",
            start_date=trading_date,
            end_date=trading_date,
            frequency="5",
            adjustflag="3",
        )
        if result.error_code != "0":
            raise RuntimeError(result.error_msg)
        bars: List[MinuteBar] = []
        cumulative_volume = 0.0
        cumulative_amount = 0.0
        for row in _rows(result):
            volume = _float_or_none(row.get("volume")) or 0.0
            amount = _float_or_none(row.get("amount")) or 0.0
            cumulative_volume += volume
            cumulative_amount += amount
            avg_price = cumulative_amount / cumulative_volume if cumulative_volume > 0 else None
            bars.append(
                MinuteBar(
                    time=_format_baostock_time(row["time"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=volume,
                    amount=amount,
                    avg_price=avg_price,
                )
            )
        if not bars:
            raise RuntimeError(f"{code} {trading_date} 缺少 5 分钟历史数据")
        return bars

    def _stock_rows_for_date(self, trading_date: str) -> List[Dict[str, str]]:
        result = self.bs.query_all_stock(day=trading_date)
        if result.error_code != "0":
            raise RuntimeError(result.error_msg)
        rows = []
        for row in _rows(result):
            code = _plain_code(row.get("code", ""))
            name = row.get("code_name") or row.get("name") or code
            if not code.isdigit() or not is_main_board(code):
                continue
            if row.get("tradeStatus") not in {"1", 1, None, ""}:
                continue
            if "ST" in name.upper() or "退" in name:
                continue
            rows.append({"code": code, "name": name})
        return rows

    def _current_spots(self, codes: Iterable[str]) -> Dict[str, MarketSnapshot]:
        missing = [normalize_code(code) for code in codes if normalize_code(code) not in self._spot_cache]
        for start in range(0, len(missing), 80):
            batch = missing[start : start + 80]
            if not batch:
                continue
            self._fetch_current_spot_batch(batch)
        return {normalize_code(code): self._spot_cache[normalize_code(code)] for code in codes if normalize_code(code) in self._spot_cache}

    def _fetch_current_spot_batch(self, batch: List[str]) -> None:
        try:
            for snapshot in fetch_eastmoney_ulist_snapshots(batch):
                self._spot_cache[normalize_code(snapshot.code)] = snapshot
            return
        except Exception:
            if len(batch) <= 1:
                return
        midpoint = len(batch) // 2
        self._fetch_current_spot_batch(batch[:midpoint])
        self._fetch_current_spot_batch(batch[midpoint:])

    def _fetch_daily_bars(self, code: str, start_date: str, end_date: str) -> List[DailyBar]:
        result = self.bs.query_history_k_data_plus(
            _baostock_code(code),
            "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,isST",
            start_date=self._dash_date(start_date),
            end_date=self._dash_date(end_date),
            frequency="d",
            adjustflag="3",
        )
        if result.error_code != "0":
            raise RuntimeError(result.error_msg)
        bars: List[DailyBar] = []
        for row in _rows(result):
            open_price = _float_or_none(row.get("open"))
            high_price = _float_or_none(row.get("high"))
            low_price = _float_or_none(row.get("low"))
            close_price = _float_or_none(row.get("close"))
            change_pct = _float_or_none(row.get("pctChg"))
            if None in {open_price, high_price, low_price, close_price, change_pct}:
                continue
            bars.append(
                DailyBar(
                    date=row["date"],
                    open=float(open_price),
                    high=float(high_price),
                    low=float(low_price),
                    close=float(close_price),
                    change_pct=float(change_pct),
                    turnover_pct=_float_or_none(row.get("turn")),
                    volume=_float_or_none(row.get("volume")),
                    amount_yuan=_float_or_none(row.get("amount")),
                )
            )
        return bars

    @staticmethod
    def _dash_date(value: str) -> str:
        text = str(value)
        if "-" in text:
            return text[:10]
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"

    @staticmethod
    def _lookback_start(trading_date: str) -> str:
        return (datetime.strptime(trading_date, "%Y-%m-%d").date() - timedelta(days=100)).strftime("%Y%m%d")
