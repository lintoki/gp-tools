from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import akshare as ak
import pandas as pd
import requests

from quant.strategy_config import merge_strategy_config


MAIN_BOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")
EXCLUDED_PREFIXES = ("300", "301", "688", "689", "8", "4")
AFTER_1430 = time(14, 30)
TAIL_START = "14:30:00"
TAIL_END = "15:00:00"
MAX_CANDIDATES = 10
MAX_REJECTIONS = 10
MAX_NEAR_MISSES = 5
LEVEL_ORDER = {"A": 0, "B": 1, "C": 2, "rejected": 3}
LIMIT_UP_CACHE_COLUMNS = ["code", "name", "trade_date", "close_price", "limit_up_price", "limit_up_reason"]
REJECTION_STAGE_LABELS = {
    "rough_filter": "涨幅榜粗筛",
    "hard_filter": "硬性条件过滤",
    "intraday": "分时强度过滤",
    "score": "评分过滤",
    "ma_structure": "均线结构过滤",
    "tail_pattern": "尾盘形态过滤",
    "tail_volume": "尾盘成交量过滤",
    "fund_flow": "资金流过滤",
}


STRATEGY_META = {
    "overnight_arbitrage": {
        "strategy": "yang_yongxing_overnight_arbitrage_8_steps",
        "empty_note": "今日无符合策略标的，建议空仓",
        "filters": {
            "time": "after_14_30",
            "board": "main_board_only",
            "pct_chg": "3%-5%",
            "limit_up_20d": ">=1",
            "volume_ratio": ">1",
            "turnover_rate": "5%-10%",
            "market_cap": "50e8-200e8",
            "intraday": "price_above_vwap",
            "entry": "break_intraday_high_and_pullback_not_below_vwap",
        },
    },
    "tail_30m_reversal": {
        "strategy": "chen_xiaoqun_last_30min_method",
        "empty_note": "今日尾盘形态不符合，建议空仓",
        "filters": {
            "pct_chg": "3%-5%",
            "volume_ratio": ">1",
            "turnover_rate": "5%-10%",
            "market_cap": "50e8-200e8",
            "ma_structure": "ma5_golden_cross_ma30_or_ma5_above_ma30",
            "tail_pattern": "C_or_D_or_F",
        },
    },
}


class RealtimeStrategyScreener:
    def __init__(
        self,
        provider,
        now_func: Callable[[], datetime] = datetime.now,
    ):
        self.provider = provider
        self.now_func = now_func

    def run(self, strategy_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if strategy_id not in STRATEGY_META:
            raise KeyError(f"unknown realtime strategy: {strategy_id}")

        now = self.now_func()
        meta = STRATEGY_META[strategy_id]
        config = merge_strategy_config(strategy_id, params or {})
        run_time_valid = now.time() >= AFTER_1430
        base = self._base_result(strategy_id, now, run_time_valid)
        if not run_time_valid:
            return base

        try:
            quotes = self.provider.get_ranked_quotes()
        except Exception:
            base["data_warning"] = "行情榜数据源暂时不可用，已停止本次筛选。"
            base["decision"] = {
                "can_buy": False,
                "max_buy_count": 1,
                "note": "行情榜数据源暂时不可用，建议空仓等待，稍后重试。",
            }
            return base
        pool_quotes, rejections, raw_rank_count, main_board_count = _three_level_pool_filter(quotes, config)
        try:
            index_pct_chg = float(self.provider.get_index_pct_chg())
        except Exception:
            index_pct_chg = 0.0
            base["data_warning"] = "大盘指数数据暂时不可用，已按 0% 近似计算相对强度。"
        trade_date = now.date().isoformat()
        codes = [item["code"] for item in pool_quotes]
        try:
            limit_up_counts = self.provider.get_limit_up_counts(codes, trade_date, lookback=20)
        except Exception:
            limit_up_counts = {}
            base["data_warning"] = "涨停缓存读取失败，已按无涨停记录处理。"

        level_buckets = {"A": [], "B": [], "C": []}
        for quote in pool_quotes:
            if strategy_id == "overnight_arbitrage":
                candidate, reject = self._evaluate_yang_layered(quote, trade_date, index_pct_chg, limit_up_counts, config)
            else:
                candidate, reject = self._evaluate_tail_30m_layered(quote, trade_date, config)
            if candidate:
                level_buckets[candidate["level"]].append(candidate)
            if reject:
                rejections.append(reject)

        a_candidates = sorted(level_buckets["A"], key=lambda item: item["score"], reverse=True)[:MAX_CANDIDATES]
        b_candidates = sorted(level_buckets["B"], key=lambda item: item["score"], reverse=True)[:MAX_CANDIDATES]
        c_candidates = sorted(level_buckets["C"], key=lambda item: item["score"], reverse=True)[:MAX_CANDIDATES]
        rejected = rejections[:MAX_REJECTIONS]
        trade_decision = _trade_decision(a_candidates)
        base["A_buy_candidates"] = a_candidates
        base["B_watch_candidates"] = b_candidates
        base["C_pool_candidates"] = c_candidates
        base["rejected"] = rejected
        base["candidates"] = a_candidates
        base["near_misses"] = [] if a_candidates or b_candidates or c_candidates else _build_near_misses(rejections)
        base["rejections"] = rejected
        base["trade_decision"] = trade_decision
        base["decision"] = {"can_buy": trade_decision["can_buy"], "max_buy_count": 1, "note": trade_decision["reason"]}
        base["stats"] = {
            "raw_rank_count": raw_rank_count,
            "main_board_count": main_board_count,
            "C_pool_count": len(c_candidates),
            "B_watch_count": len(b_candidates),
            "A_buy_count": len(a_candidates),
            "rejected_count": len(rejections),
        }
        return base

    def _base_result(self, strategy_id: str, now: datetime, run_time_valid: bool) -> Dict[str, Any]:
        meta = STRATEGY_META[strategy_id]
        result = {
            "strategy": meta["strategy"],
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "strategy_mode": "strict_buy_relaxed_watch",
            "filters": meta["filters"],
            "A_buy_candidates": [],
            "B_watch_candidates": [],
            "C_pool_candidates": [],
            "rejected": [],
            "candidates": [],
            "near_misses": [],
            "rejections": [],
            "data_warning": "",
            "trade_decision": {
                "can_buy": False,
                "reason": "没有 A 级严格买入候选，今日空仓",
                "max_buy_count": 1,
                "allow_auto_trade": False,
            },
            "stats": {
                "raw_rank_count": 0,
                "main_board_count": 0,
                "C_pool_count": 0,
                "B_watch_count": 0,
                "A_buy_count": 0,
                "rejected_count": 0,
            },
            "decision": {
                "can_buy": False,
                "max_buy_count": 1,
                "note": meta["empty_note"],
            },
        }
        if strategy_id == "overnight_arbitrage":
            result["run_time_valid"] = run_time_valid
        else:
            result["window"] = "14:30-15:00"
            result["run_time_valid"] = run_time_valid
        return result

    def _evaluate_yang_layered(
        self,
        quote: Dict[str, Any],
        trade_date: str,
        index_pct_chg: float,
        limit_up_counts: Dict[str, int],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        limit_count = int(limit_up_counts.get(quote["code"], 0))
        known_reasons = ["近20个交易日无涨停记录"] if limit_count <= 0 else []
        c_basic_reasons = _yang_c_reject_reasons(quote, "", config)
        if c_basic_reasons:
            return {}, _rejection(quote, "hard_filter", c_basic_reasons, _yang_upgrade_requirements(c_basic_reasons))
        missing_intraday_stage = "hard_filter" if known_reasons else "intraday"
        try:
            intraday = _prepare_intraday(self.provider.get_intraday_bars(quote["code"], trade_date))
        except Exception:
            return {}, _rejection(quote, missing_intraday_stage, known_reasons + ["分时数据源暂时不可用"], ["补充分时数据后重新评估"])
        if intraday.empty:
            return {}, _rejection(quote, missing_intraday_stage, known_reasons + ["缺少分时数据"], ["补充 14:30-15:00 分时数据"])

        metrics = _intraday_metrics(intraday, quote)
        volume_status, _, volume_reject = _tail_volume_status(intraday)
        relative_strength = float(quote["pct_chg"]) - index_pct_chg
        score, risk_flags = _score_yang(quote, max(limit_count, 1), metrics, relative_strength)

        a_reasons = _yang_a_reject_reasons(quote, limit_count, metrics, relative_strength, volume_reject, score, config)
        if not a_reasons:
            return _candidate(
                quote,
                level="A",
                action="buy_candidate",
                score=score,
                reject_reasons=[],
                upgrade_requirements=[],
                extra=_yang_extra(quote, limit_count, metrics, relative_strength, risk_flags),
            ), None

        b_reasons = _yang_b_reject_reasons(quote, limit_count, metrics, relative_strength, volume_reject, config)
        if not b_reasons:
            return _candidate(
                quote,
                level="B",
                action="watch",
                score=min(score, 69.9),
                reject_reasons=a_reasons,
                upgrade_requirements=_yang_upgrade_requirements(a_reasons, metrics),
                extra=_yang_extra(quote, limit_count, metrics, relative_strength, risk_flags),
            ), None

        c_reasons = _yang_c_reject_reasons(quote, volume_reject, config)
        if not c_reasons:
            return _candidate(
                quote,
                level="C",
                action="watch",
                score=min(max(score, 45), 59.9),
                reject_reasons=a_reasons + b_reasons,
                upgrade_requirements=_yang_upgrade_requirements(a_reasons + b_reasons, metrics),
                extra=_yang_extra(quote, limit_count, metrics, relative_strength, risk_flags),
            ), None

        return {}, _rejection(quote, "hard_filter", c_reasons, _yang_upgrade_requirements(a_reasons + b_reasons + c_reasons, metrics))

    def _evaluate_tail_30m_layered(self, quote: Dict[str, Any], trade_date: str, config: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        c_basic_reasons = _tail_c_reject_reasons(quote, "", config)
        if c_basic_reasons:
            return {}, _rejection(quote, "hard_filter", c_basic_reasons, _tail_upgrade_requirements(c_basic_reasons, TailPattern("", "", "reject", 0)))

        try:
            intraday = _prepare_intraday(self.provider.get_intraday_bars(quote["code"], trade_date))
        except Exception:
            return {}, _rejection(quote, "intraday", ["分时数据源暂时不可用"], ["补充分时数据后重新评估"])
        if intraday.empty:
            return {}, _rejection(quote, "intraday", ["缺少分时数据"], ["补充 14:30-15:00 分时数据"])

        try:
            daily = self.provider.get_daily_features(quote["code"], trade_date)
        except Exception:
            daily = {"ma5": 0, "ma30": 0, "ma_structure": "unknown"}

        metrics = _intraday_metrics(intraday, quote)
        pattern = _classify_tail_pattern(intraday, quote, metrics)
        volume_status, volume_score, volume_reject = _tail_volume_status(intraday)
        fund_status, fund_score, fund_reject = _fund_flow_status(intraday)
        ma_reasons, ma_score = _ma_score(daily)
        breakout_score = 10 if metrics.breakout_after_1430 else 0
        score = round(30 + max(pattern.score, 0) + volume_score + fund_score + ma_score + breakout_score, 1)
        extra = _tail_extra(quote, pattern, volume_status, fund_status, daily, metrics)

        if pattern.key in {"up_then_down_break_open", "down_then_weak_rebound"}:
            return {}, _rejection(quote, "tail_pattern", [pattern.reason], ["尾盘形态修复为 C、D 或 F 后再观察"])

        a_reasons = _tail_a_reject_reasons(quote, metrics, pattern, volume_reject, fund_reject, ma_reasons, score, config)
        if not a_reasons:
            return _candidate(quote, "A", "buy_candidate", score, [], [], extra), None

        b_reasons = _tail_b_reject_reasons(quote, metrics, pattern, volume_reject, daily, config)
        if not b_reasons:
            return _candidate(quote, "B", "watch", min(score, 69.9), a_reasons, _tail_upgrade_requirements(a_reasons, pattern), extra), None

        c_reasons = _tail_c_reject_reasons(quote, volume_reject, config)
        if not c_reasons:
            return _candidate(
                quote,
                "C",
                "watch",
                min(max(score, 45), 59.9),
                a_reasons + b_reasons,
                _tail_upgrade_requirements(a_reasons + b_reasons, pattern),
                extra,
            ), None

        return {}, _rejection(quote, "hard_filter", c_reasons, _tail_upgrade_requirements(a_reasons + b_reasons + c_reasons, pattern))

    def _evaluate_yang(
        self,
        quote: Dict[str, Any],
        trade_date: str,
        index_pct_chg: float,
        limit_up_counts: Dict[str, int],
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        reasons = _base_hard_filter_reasons(quote)
        limit_count = int(limit_up_counts.get(quote["code"], 0))
        if limit_count <= 0:
            reasons.append("近20个交易日无涨停记录")
        if reasons:
            return {}, _rejection(quote, "hard_filter", reasons)

        try:
            intraday = _prepare_intraday(self.provider.get_intraday_bars(quote["code"], trade_date))
        except Exception:
            return {}, _rejection(quote, "intraday", ["分时数据源暂时不可用"])
        if intraday.empty:
            return {}, _rejection(quote, "intraday", ["缺少分时数据"])

        metrics = _intraday_metrics(intraday, quote)
        intraday_reasons = []
        if metrics.above_vwap_ratio < 0.70:
            intraday_reasons.append("全天在分时均价线上方比例低于 0.70")
        if not metrics.current_above_vwap:
            intraday_reasons.append("当前价格跌破分时均价线")
        relative_strength = float(quote["pct_chg"]) - index_pct_chg
        if relative_strength < 2:
            intraday_reasons.append("相对强度低于 2")
        if metrics.breakout_after_1430 and not metrics.pullback_above_vwap:
            intraday_reasons.append("尾盘创高后跌破分时均价线")
        if intraday_reasons:
            return {}, _rejection(quote, "intraday", intraday_reasons)

        score, risk_flags = _score_yang(quote, limit_count, metrics, relative_strength)
        if score < 70:
            return {}, _rejection(quote, "score", [f"评分低于 70: {score}"] + risk_flags)

        action = "buy_or_watch" if metrics.breakout_after_1430 and metrics.pullback_above_vwap else "watch"
        return {
            "code": quote["code"],
            "name": quote["name"],
            "price": _round(quote["price"], 2),
            "pct_chg": _round(quote["pct_chg"], 2),
            "volume_ratio": _round(quote["volume_ratio"], 2),
            "turnover_rate": _round(quote["turnover_rate"], 2),
            "total_market_cap": _round(quote["total_market_cap"], 0),
            "limit_up_count_20d": limit_count,
            "above_vwap_ratio": _round(metrics.above_vwap_ratio, 2),
            "relative_strength": _round(relative_strength, 2),
            "is_intraday_high_breakout_after_1430": metrics.breakout_after_1430,
            "is_pullback_above_vwap": metrics.pullback_above_vwap,
            "score": score,
            "action": action,
            "risk_flags": risk_flags,
            "buy_condition": "14:30 后创当日新高，回踩分时均价线不破才允许买入",
            "sell_rule_next_day": "次日 9:30-10:00 只卖不加仓",
        }, None

    def _evaluate_tail_30m(self, quote: Dict[str, Any], trade_date: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        reasons = _base_hard_filter_reasons(quote)
        if reasons:
            return {}, _rejection(quote, "hard_filter", reasons)

        try:
            intraday = _prepare_intraday(self.provider.get_intraday_bars(quote["code"], trade_date))
        except Exception:
            return {}, _rejection(quote, "intraday", ["分时数据源暂时不可用"])
        if intraday.empty:
            return {}, _rejection(quote, "intraday", ["缺少分时数据"])

        try:
            daily = self.provider.get_daily_features(quote["code"], trade_date)
        except Exception:
            return {}, _rejection(quote, "ma_structure", ["日线均线数据源暂时不可用"])
        ma_reasons, ma_score = _ma_score(daily)
        if ma_reasons:
            return {}, _rejection(quote, "ma_structure", ma_reasons)

        metrics = _intraday_metrics(intraday, quote)
        pattern = _classify_tail_pattern(intraday, quote, metrics)
        if pattern.action == "reject":
            return {}, _rejection(quote, "tail_pattern", [pattern.reason])

        volume_status, volume_score, volume_reject = _tail_volume_status(intraday)
        if volume_reject:
            return {}, _rejection(quote, "tail_volume", [volume_reject])

        fund_status, fund_score, fund_reject = _fund_flow_status(intraday)
        if fund_reject:
            return {}, _rejection(quote, "fund_flow", [fund_reject])

        breakout_score = 10 if metrics.breakout_after_1430 else 0
        score = round(30 + pattern.score + volume_score + fund_score + ma_score + breakout_score, 1)
        if score < 70:
            return {}, _rejection(quote, "score", [f"评分低于 70: {score}"])

        action = "buy_candidate" if pattern.key == "qualified_break_intraday_high" else "watch"
        return {
            "code": quote["code"],
            "name": quote["name"],
            "price": _round(quote["price"], 2),
            "pct_chg": _round(quote["pct_chg"], 2),
            "volume_ratio": _round(quote["volume_ratio"], 2),
            "turnover_rate": _round(quote["turnover_rate"], 2),
            "total_market_cap": _round(quote["total_market_cap"], 0),
            "tail_pattern": pattern.key,
            "tail_pattern_name": pattern.name,
            "tail_volume_status": volume_status,
            "fund_flow_status": fund_status,
            "ma5": _round(daily.get("ma5", 0), 2),
            "ma30": _round(daily.get("ma30", 0), 2),
            "ma_structure": daily.get("ma_structure", "ma5_above_ma30_and_up"),
            "is_intraday_high_breakout_after_1430": metrics.breakout_after_1430,
            "score": score,
            "action": action,
            "buy_condition": "尾盘创新高后不跌破分时均价线才允许买入",
            "sell_rule_next_day": "次日早盘或上午获利了结，弱势则止损离场",
        }, None


class AkshareRealtimeProvider:
    def __init__(self, cache_dir: Path):
        self.limit_up_cache = LimitUpCache(cache_dir / "limit_up_cache.csv")

    def get_ranked_quotes(self) -> List[Dict[str, Any]]:
        try:
            return _fetch_eastmoney_ranked_quotes()
        except Exception:
            try:
                return _fetch_sina_ranked_quotes()
            except Exception:
                return self._fetch_akshare_spot_quotes()

    def _fetch_akshare_spot_quotes(self) -> List[Dict[str, Any]]:
        raw = ak.stock_zh_a_spot_em()
        rows = []
        for _, row in raw.iterrows():
            code = str(row.get("代码", "")).zfill(6)
            name = str(row.get("名称", ""))
            price = _num(row.get("最新价"))
            pct_chg = _num(row.get("涨跌幅"))
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "price": price,
                    "pct_chg": pct_chg,
                    "volume_ratio": _num(row.get("量比"), 0),
                    "turnover_rate": _num(row.get("换手率"), 0),
                    "total_market_cap": _num(row.get("总市值"), 0),
                    "open": _num(row.get("今开"), price),
                    "is_st": _is_st_or_delist(name),
                    "is_suspended": price <= 0,
                }
            )
        return sorted(rows, key=lambda item: item["pct_chg"], reverse=True)

    def get_index_pct_chg(self) -> float:
        try:
            raw = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
            for _, row in raw.iterrows():
                name = str(row.get("名称", ""))
                if name in {"上证指数", "沪深300", "深证成指"}:
                    return _num(row.get("涨跌幅"), 0)
        except Exception:
            return 0.0
        return 0.0

    def get_limit_up_counts(self, codes: Iterable[str], trade_date: str, lookback: int = 20) -> Dict[str, int]:
        return self.limit_up_cache.count_recent(codes, trade_date, lookback)

    def get_intraday_bars(self, code: str, trade_date: str) -> pd.DataFrame:
        start = f"{trade_date} 09:30:00"
        end = f"{trade_date} 15:00:00"
        raw = ak.stock_zh_a_hist_min_em(symbol=code, start_date=start, end_date=end, period="1", adjust="")
        return _normalize_minute_bars(raw)

    def get_daily_features(self, code: str, trade_date: str) -> Dict[str, Any]:
        end = datetime.strptime(trade_date, "%Y-%m-%d").date()
        start = end - timedelta(days=90)
        raw = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
            timeout=10,
        )
        close_col = "收盘" if "收盘" in raw.columns else "close"
        close = pd.to_numeric(raw[close_col], errors="coerce").dropna()
        ma5 = float(close.tail(5).mean()) if len(close) >= 5 else float(close.mean() or 0)
        ma30 = float(close.tail(30).mean()) if len(close) >= 30 else float(close.mean() or 0)
        ma5_prev = float(close.iloc[-6:-1].mean()) if len(close) >= 6 else ma5
        ma30_prev = float(close.iloc[-31:-1].mean()) if len(close) >= 31 else ma30
        if ma5 >= ma30 and ma5_prev < ma30_prev:
            structure = "ma5_golden_cross_ma30"
        elif ma5 >= ma30 and ma5 >= ma5_prev and ma30 >= ma30_prev:
            structure = "ma5_above_ma30_and_up"
        else:
            structure = "weak_ma_structure"
        return {
            "ma5": ma5,
            "ma30": ma30,
            "ma5_slope": ma5 - ma5_prev,
            "ma30_slope": ma30 - ma30_prev,
            "ma_structure": structure,
        }

    def refresh_limit_up_cache(self, trade_date: Optional[date] = None) -> int:
        trade_date = trade_date or datetime.now().date()
        raw = ak.stock_zt_pool_em(date=trade_date.strftime("%Y%m%d"))
        rows = _normalize_limit_up_pool(raw, trade_date.isoformat())
        self.limit_up_cache.replace_trade_date(trade_date.isoformat(), rows)
        return len(rows)


class LimitUpCache:
    def __init__(self, path: Path):
        self.path = path

    def replace_trade_date(self, trade_date: str, rows: List[Dict[str, Any]]) -> None:
        existing = self._load()
        if not existing.empty:
            existing = existing[existing["trade_date"] != trade_date]
        new_rows = pd.DataFrame(rows, columns=LIMIT_UP_CACHE_COLUMNS)
        updated = new_rows if existing.empty else pd.concat([existing, new_rows], ignore_index=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        updated.to_csv(self.path, index=False)

    def count_recent(self, codes: Iterable[str], trade_date: str, lookback: int = 20) -> Dict[str, int]:
        code_set = {str(code).zfill(6) for code in codes}
        result = {code: 0 for code in code_set}
        data = self._load()
        if data.empty:
            return result
        data["trade_date"] = pd.to_datetime(data["trade_date"])
        target = pd.to_datetime(trade_date)
        recent_dates = sorted(data[data["trade_date"] <= target]["trade_date"].drop_duplicates())[-lookback:]
        recent = data[data["trade_date"].isin(recent_dates)]
        recent = recent[recent["code"].astype(str).str.zfill(6).isin(code_set)]
        counts = recent.groupby(recent["code"].astype(str).str.zfill(6)).size().to_dict()
        for code, count in counts.items():
            result[code] = int(count)
        return result

    def _load(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame(columns=LIMIT_UP_CACHE_COLUMNS)
        return pd.read_csv(self.path, dtype={"code": str})


def _fetch_eastmoney_ranked_quotes() -> List[Dict[str, Any]]:
    rows = []
    for page in range(1, 80):
        response = requests.get(
            "https://82.push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": page,
                "pz": 100,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14,f2,f3,f10,f8,f20,f17",
            },
            timeout=10,
        )
        response.raise_for_status()
        diff = response.json().get("data", {}).get("diff") or []
        if not diff:
            break

        page_quotes = [_eastmoney_quote(row) for row in diff]
        rows.extend([item for item in page_quotes if item["pct_chg"] >= 3])
        if min(item["pct_chg"] for item in page_quotes) < 3:
            break
    return sorted(rows, key=lambda item: item["pct_chg"], reverse=True)


def _eastmoney_quote(row: Dict[str, Any]) -> Dict[str, Any]:
    price = _num(row.get("f2"), 0)
    name = str(row.get("f14", ""))
    return {
        "code": str(row.get("f12", "")).zfill(6),
        "name": name,
        "price": price,
        "pct_chg": _num(row.get("f3"), 0),
        "volume_ratio": _num(row.get("f10"), 0),
        "turnover_rate": _num(row.get("f8"), 0),
        "total_market_cap": _num(row.get("f20"), 0),
        "open": _num(row.get("f17"), price),
        "is_st": _is_st_or_delist(name),
        "is_suspended": price <= 0,
    }


def _fetch_sina_ranked_quotes() -> List[Dict[str, Any]]:
    rows = []
    for page in range(1, 80):
        response = requests.get(
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
            params={
                "page": page,
                "num": 100,
                "sort": "changepercent",
                "asc": 0,
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        page_rows = response.json() or []
        if not page_rows:
            break
        page_quotes = [_sina_quote(row) for row in page_rows]
        rows.extend([item for item in page_quotes if item["pct_chg"] >= 3])
        if min(item["pct_chg"] for item in page_quotes) < 3:
            break
    return _enrich_with_tencent_details(sorted(rows, key=lambda item: item["pct_chg"], reverse=True))


def _sina_quote(row: Dict[str, Any]) -> Dict[str, Any]:
    price = _num(row.get("trade"), 0)
    name = str(row.get("name", ""))
    return {
        "code": str(row.get("code", "")).zfill(6),
        "name": name,
        "price": price,
        "pct_chg": _num(row.get("changepercent"), 0),
        "volume_ratio": 0.0,
        "turnover_rate": _num(row.get("turnoverratio"), 0),
        "total_market_cap": _num(row.get("mktcap"), 0) * 10000,
        "open": _num(row.get("open"), price),
        "is_st": _is_st_or_delist(name),
        "is_suspended": price <= 0,
    }


def _enrich_with_tencent_details(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not quotes:
        return quotes
    details = {}
    for start in range(0, len(quotes), 60):
        chunk = quotes[start : start + 60]
        query = ",".join(_tencent_symbol(item["code"]) for item in chunk)
        response = requests.get(
            "https://qt.gtimg.cn/q=" + query,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        details.update(_parse_tencent_detail_response(response.text))

    enriched = []
    for quote in quotes:
        detail = details.get(quote["code"], {})
        merged = {**quote, **{key: value for key, value in detail.items() if value not in ("", 0, 0.0)}}
        enriched.append(merged)
    return enriched


def _parse_tencent_detail_response(text: str) -> Dict[str, Dict[str, Any]]:
    details = {}
    for item in text.split(";"):
        if '="' not in item:
            continue
        payload = item.split('="', 1)[1].rstrip('"')
        fields = payload.split("~")
        if len(fields) < 50:
            continue
        code = str(fields[2]).zfill(6)
        price = _num(_field(fields, 3), 0)
        details[code] = {
            "name": _field(fields, 1),
            "code": code,
            "price": price,
            "open": _num(_field(fields, 5), price),
            "pct_chg": _num(_field(fields, 32), 0),
            "turnover_rate": _num(_field(fields, 38), 0),
            "total_market_cap": _num(_field(fields, 44), 0) * 100_000_000,
            "volume_ratio": _num(_field(fields, 49), 0),
            "is_suspended": price <= 0,
        }
    return details


def _field(fields: List[str], index: int) -> str:
    return fields[index] if index < len(fields) else ""


def _tencent_symbol(code: str) -> str:
    code = str(code).zfill(6)
    return ("sh" if code.startswith("6") else "sz") + code


@dataclass
class IntradayMetrics:
    above_vwap_ratio: float
    current_above_vwap: bool
    breakout_after_1430: bool
    pullback_above_vwap: bool
    tail: pd.DataFrame


@dataclass
class TailPattern:
    key: str
    name: str
    action: str
    score: float
    reason: str = ""


def _three_level_pool_filter(quotes: Iterable[Dict[str, Any]], config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int]:
    c_cfg = _level_config(config, "C")
    selected = []
    rejections = []
    raw_count = 0
    main_board_count = 0
    for raw in quotes:
        raw_count += 1
        quote = _normalize_quote(raw)
        reasons = []
        if not _is_main_board(quote["code"]):
            reasons.append("非沪深主板")
        if _is_st_or_delist(quote["name"]) or quote.get("is_st"):
            reasons.append("ST、退市或风险警示")
        if quote.get("is_suspended"):
            reasons.append("停牌")
        if not reasons:
            main_board_count += 1
        if not c_cfg["min_pct_chg"] <= float(quote["pct_chg"]) <= c_cfg["max_pct_chg"]:
            reasons.append(f"当前涨幅不在 {_fmt_threshold(c_cfg['min_pct_chg'])}%-{_fmt_threshold(c_cfg['max_pct_chg'])}% 观察池范围")
        if reasons:
            rejections.append(_rejection(quote, "rough_filter", reasons, ["进入主板非 ST 且涨幅回到 2%-6% 后再观察"]))
        else:
            selected.append(quote)
    return selected, rejections, raw_count, main_board_count


def _level_config(config: Dict[str, Any], level: str) -> Dict[str, Any]:
    return config.get("levels", {}).get(level, {})


def _rough_filter(quotes: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = []
    rejections = []
    for raw in quotes:
        quote = _normalize_quote(raw)
        reasons = []
        if not _is_main_board(quote["code"]):
            reasons.append("非沪深主板")
        if _is_st_or_delist(quote["name"]) or quote.get("is_st"):
            reasons.append("ST、退市或风险警示")
        if quote.get("is_suspended"):
            reasons.append("停牌")
        if not 3 <= float(quote["pct_chg"]) <= 5:
            reasons.append("当前涨幅不在 3%-5%")
        if reasons:
            rejections.append(_rejection(quote, "rough_filter", reasons))
        else:
            selected.append(quote)
    return selected, rejections


def _normalize_quote(raw: Dict[str, Any]) -> Dict[str, Any]:
    code = str(raw.get("code", "")).zfill(6)
    return {
        "code": code,
        "name": str(raw.get("name", "")),
        "price": _num(raw.get("price"), 0),
        "pct_chg": _normalize_percent(raw.get("pct_chg")),
        "volume_ratio": _num(raw.get("volume_ratio"), 0),
        "turnover_rate": _normalize_percent(raw.get("turnover_rate")),
        "total_market_cap": _normalize_market_cap(raw.get("total_market_cap")),
        "open": _num(raw.get("open"), _num(raw.get("price"), 0)),
        "is_st": bool(raw.get("is_st", False)),
        "is_suspended": bool(raw.get("is_suspended", False)),
    }


def _candidate(
    quote: Dict[str, Any],
    level: str,
    action: str,
    score: float,
    reject_reasons: List[str],
    upgrade_requirements: List[str],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = {
        "code": quote["code"],
        "name": quote["name"],
        "level": level,
        "action": action,
        "price": _round(quote["price"], 2),
        "pct_chg": _round(quote["pct_chg"], 2),
        "volume_ratio": _round(quote["volume_ratio"], 2),
        "turnover_rate": _round(quote["turnover_rate"], 2),
        "total_market_cap": _round(quote["total_market_cap"], 0),
        "score": round(float(score), 1),
        "reject_reasons": reject_reasons,
        "upgrade_requirements": upgrade_requirements,
    }
    if extra:
        item.update(extra)
    return item


def _yang_extra(
    quote: Dict[str, Any],
    limit_count: int,
    metrics: IntradayMetrics,
    relative_strength: float,
    risk_flags: List[str],
) -> Dict[str, Any]:
    return {
        "limit_up_count_20d": limit_count,
        "above_vwap_ratio": _round(metrics.above_vwap_ratio, 2),
        "relative_strength": _round(relative_strength, 2),
        "is_intraday_high_breakout_after_1430": metrics.breakout_after_1430,
        "is_pullback_above_vwap": metrics.pullback_above_vwap,
        "risk_flags": risk_flags,
        "buy_condition": "14:30 后创当日新高，回踩分时均价线不破才允许买入",
        "sell_rule_next_day": "次日 9:30-10:00 只卖不加仓",
    }


def _tail_extra(
    quote: Dict[str, Any],
    pattern: TailPattern,
    volume_status: str,
    fund_status: str,
    daily: Dict[str, Any],
    metrics: IntradayMetrics,
) -> Dict[str, Any]:
    return {
        "tail_pattern": pattern.key,
        "tail_pattern_name": pattern.name,
        "tail_volume_status": volume_status,
        "fund_flow_status": fund_status,
        "ma5": _round(daily.get("ma5", 0), 2),
        "ma30": _round(daily.get("ma30", 0), 2),
        "ma_structure": daily.get("ma_structure", "unknown"),
        "is_intraday_high_breakout_after_1430": metrics.breakout_after_1430,
        "buy_condition": "尾盘创新高后不跌破分时均价线才允许买入",
        "sell_rule_next_day": "次日早盘或上午获利了结，弱势则止损离场",
    }


def _yang_a_reject_reasons(
    quote: Dict[str, Any],
    limit_count: int,
    metrics: IntradayMetrics,
    relative_strength: float,
    volume_reject: str,
    score: float,
    config: Dict[str, Any],
) -> List[str]:
    cfg = _level_config(config, "A")
    reasons = []
    pct = float(quote["pct_chg"])
    if not cfg["min_pct_chg"] <= pct <= cfg["max_pct_chg"]:
        reasons.append(f"当前涨幅未达到 A 级 {cfg['min_pct_chg']}%-{cfg['max_pct_chg']}%")
    if limit_count < cfg.get("min_limit_up_count_20d", 1):
        reasons.append("近20个交易日无涨停记录")
    if float(quote["volume_ratio"]) < cfg["min_volume_ratio"]:
        reasons.append(f"量比低于 A 级 {cfg['min_volume_ratio']}")
    if not cfg["min_turnover_rate"] <= float(quote["turnover_rate"]) <= cfg["max_turnover_rate"]:
        reasons.append(f"换手率未达到 A 级 {cfg['min_turnover_rate']}%-{cfg['max_turnover_rate']}%")
    cap_billion = float(quote["total_market_cap"]) / 100_000_000
    if not cfg["min_market_cap_billion"] <= cap_billion <= cfg["max_market_cap_billion"]:
        reasons.append(f"总市值未达到 A 级 {cfg['min_market_cap_billion']} 亿-{cfg['max_market_cap_billion']} 亿")
    if metrics.above_vwap_ratio < cfg["min_above_vwap_ratio"]:
        reasons.append(f"均价线上方比例只有 {metrics.above_vwap_ratio:.2f}，未达到 A 级 {cfg['min_above_vwap_ratio']:.2f}")
    if not metrics.current_above_vwap:
        reasons.append("当前价格跌破分时均价线")
    if relative_strength < cfg.get("min_relative_strength", 0):
        reasons.append(f"相对强度低于 A 级 {cfg.get('min_relative_strength', 0)}")
    if not (metrics.breakout_after_1430 and metrics.pullback_above_vwap):
        reasons.append("未在 14:30 后创当日新高")
    if volume_reject:
        reasons.append(volume_reject)
    if score < cfg.get("min_score", 70):
        reasons.append(f"评分低于 A 级 {cfg.get('min_score', 70)}: {score}")
    return reasons


def _yang_b_reject_reasons(
    quote: Dict[str, Any],
    limit_count: int,
    metrics: IntradayMetrics,
    relative_strength: float,
    volume_reject: str,
    config: Dict[str, Any],
) -> List[str]:
    cfg = _level_config(config, "B")
    reasons = []
    if not cfg["min_pct_chg"] <= float(quote["pct_chg"]) <= cfg["max_pct_chg"]:
        reasons.append(f"当前涨幅未达到 B 级 {cfg['min_pct_chg']}%-{cfg['max_pct_chg']}%")
    if float(quote["volume_ratio"]) < cfg["min_volume_ratio"]:
        reasons.append(f"量比低于 B 级 {cfg['min_volume_ratio']}")
    if not cfg["min_turnover_rate"] <= float(quote["turnover_rate"]) <= cfg["max_turnover_rate"]:
        reasons.append(f"换手率不在 B 级 {cfg['min_turnover_rate']}%-{cfg['max_turnover_rate']}%")
    cap_billion = float(quote["total_market_cap"]) / 100_000_000
    if not cfg["min_market_cap_billion"] <= cap_billion <= cfg["max_market_cap_billion"]:
        reasons.append(f"总市值不在 B 级 {cfg['min_market_cap_billion']} 亿-{cfg['max_market_cap_billion']} 亿")
    if limit_count < cfg.get("min_limit_up_count_20d", 1):
        reasons.append("近20个交易日无涨停记录")
    if metrics.above_vwap_ratio < cfg.get("min_above_vwap_ratio", 0):
        reasons.append(f"均价线上方比例只有 {metrics.above_vwap_ratio:.2f}，未达到 B 级 {cfg.get('min_above_vwap_ratio', 0):.2f}")
    if not metrics.current_above_vwap:
        reasons.append("当前价格明显跌破分时均价线")
    if relative_strength < cfg.get("min_relative_strength", 0):
        reasons.append(f"相对强度低于 B 级 {cfg.get('min_relative_strength', 0)}")
    if volume_reject:
        reasons.append(volume_reject)
    return reasons


def _yang_c_reject_reasons(quote: Dict[str, Any], volume_reject: str, config: Dict[str, Any]) -> List[str]:
    cfg = _level_config(config, "C")
    reasons = []
    if not cfg["min_pct_chg"] <= float(quote["pct_chg"]) <= cfg["max_pct_chg"]:
        reasons.append(f"当前涨幅未达到 C 级 {cfg['min_pct_chg']}%-{cfg['max_pct_chg']}%")
    if float(quote["volume_ratio"]) < cfg["min_volume_ratio"]:
        reasons.append(f"量比低于 C 级 {cfg['min_volume_ratio']}")
    if not cfg["min_turnover_rate"] <= float(quote["turnover_rate"]) <= cfg["max_turnover_rate"]:
        reasons.append(f"换手率不在 C 级 {cfg['min_turnover_rate']}%-{cfg['max_turnover_rate']}%")
    cap_billion = float(quote["total_market_cap"]) / 100_000_000
    if not cfg["min_market_cap_billion"] <= cap_billion <= cfg["max_market_cap_billion"]:
        reasons.append(f"总市值不在 C 级 {cfg['min_market_cap_billion']} 亿-{cfg['max_market_cap_billion']} 亿")
    if volume_reject:
        reasons.append(volume_reject)
    return reasons


def _yang_upgrade_requirements(reasons: List[str], metrics: Optional[IntradayMetrics] = None) -> List[str]:
    requirements = []
    joined = "；".join(reasons)
    if "未在 14:30 后创当日新高" in joined:
        requirements.append("需要 14:30 后放量突破当日新高")
    if "分时均价线" in joined:
        requirements.append("当前价格保持在分时均价线上方")
    if "均价线上方比例" in joined:
        requirements.append("均价线上方比例提升到 0.70 以上")
    if "涨停" in joined:
        requirements.append("近 20 个交易日至少出现 1 次涨停")
    if "相对强度" in joined:
        requirements.append("相对强度提升到 2 以上")
    if not requirements:
        requirements.append("补齐 A 级硬条件后再考虑买入")
    return list(dict.fromkeys(requirements))


def _tail_a_reject_reasons(
    quote: Dict[str, Any],
    metrics: IntradayMetrics,
    pattern: TailPattern,
    volume_reject: str,
    fund_reject: str,
    ma_reasons: List[str],
    score: float,
    config: Dict[str, Any],
) -> List[str]:
    cfg = _level_config(config, "A")
    reasons = []
    if not cfg["min_pct_chg"] <= float(quote["pct_chg"]) <= cfg["max_pct_chg"]:
        reasons.append(f"涨幅未达到 A 级 {cfg['min_pct_chg']}%-{cfg['max_pct_chg']}%")
    if float(quote["volume_ratio"]) < cfg["min_volume_ratio"]:
        reasons.append(f"量比低于 A 级 {cfg['min_volume_ratio']}")
    if not cfg["min_turnover_rate"] <= float(quote["turnover_rate"]) <= cfg["max_turnover_rate"]:
        reasons.append(f"换手率未达到 A 级 {cfg['min_turnover_rate']}%-{cfg['max_turnover_rate']}%")
    cap_billion = float(quote["total_market_cap"]) / 100_000_000
    if not cfg["min_market_cap_billion"] <= cap_billion <= cfg["max_market_cap_billion"]:
        reasons.append(f"总市值未达到 A 级 {cfg['min_market_cap_billion']} 亿-{cfg['max_market_cap_billion']} 亿")
    if pattern.key not in {"mild_rise_above_vwap_volume_up", "rise_pullback_hold_vwap", "qualified_break_intraday_high"}:
        reasons.append("尾盘形态未达到 A 级 C、D、F")
    if not metrics.breakout_after_1430:
        reasons.append("未在 14:30 后创当日新高")
    if not metrics.current_above_vwap:
        reasons.append("当前价格跌破分时均价线")
    reasons.extend(ma_reasons)
    if volume_reject:
        reasons.append(volume_reject)
    if fund_reject:
        reasons.append(fund_reject)
    if score < cfg.get("min_score", 70):
        reasons.append(f"评分低于 A 级 {cfg.get('min_score', 70)}: {score}")
    return reasons


def _tail_b_reject_reasons(
    quote: Dict[str, Any],
    metrics: IntradayMetrics,
    pattern: TailPattern,
    volume_reject: str,
    daily: Dict[str, Any],
    config: Dict[str, Any],
) -> List[str]:
    cfg = _level_config(config, "B")
    reasons = []
    if not cfg["min_pct_chg"] <= float(quote["pct_chg"]) <= cfg["max_pct_chg"]:
        reasons.append(f"当前涨幅未达到 B 级 {cfg['min_pct_chg']}%-{cfg['max_pct_chg']}%")
    if float(quote["volume_ratio"]) < cfg["min_volume_ratio"]:
        reasons.append(f"量比低于 B 级 {cfg['min_volume_ratio']}")
    if not cfg["min_turnover_rate"] <= float(quote["turnover_rate"]) <= cfg["max_turnover_rate"]:
        reasons.append(f"换手率不在 B 级 {cfg['min_turnover_rate']}%-{cfg['max_turnover_rate']}%")
    cap_billion = float(quote["total_market_cap"]) / 100_000_000
    if not cfg["min_market_cap_billion"] <= cap_billion <= cfg["max_market_cap_billion"]:
        reasons.append(f"总市值不在 B 级 {cfg['min_market_cap_billion']} 亿-{cfg['max_market_cap_billion']} 亿")
    if pattern.key not in {"mild_rise_above_vwap_volume_up", "rise_pullback_hold_vwap", "qualified_break_intraday_high"}:
        reasons.append("尾盘形态不是 B 级可观察形态")
    ma5 = _num(daily.get("ma5"), 0)
    ma30 = _num(daily.get("ma30"), 0)
    if ma30 and ma5 < ma30 * 0.98:
        reasons.append("5 日线距离 30 日线过远")
    if not metrics.current_above_vwap:
        reasons.append("当前价格明显跌破分时均价线")
    if volume_reject:
        reasons.append(volume_reject)
    return reasons


def _tail_c_reject_reasons(quote: Dict[str, Any], volume_reject: str, config: Dict[str, Any]) -> List[str]:
    return _yang_c_reject_reasons(quote, volume_reject, config)


def _tail_upgrade_requirements(reasons: List[str], pattern: TailPattern) -> List[str]:
    requirements = []
    joined = "；".join(reasons)
    if "创当日新高" in joined or pattern.key != "qualified_break_intraday_high":
        requirements.append("14:30 后放量突破或接近突破当日新高")
    if "均线" in joined or "5 日线" in joined:
        requirements.append("5 日线重新站上 30 日线并保持向上")
    if "分时均价线" in joined:
        requirements.append("当前价格重新站回分时均价线上方")
    if "评分" in joined:
        requirements.append("评分提升到 70 以上")
    if not requirements:
        requirements.append("补齐 A 级尾盘形态和硬条件后再考虑买入")
    return list(dict.fromkeys(requirements))



def _base_hard_filter_reasons(quote: Dict[str, Any]) -> List[str]:
    reasons = []
    if float(quote["volume_ratio"]) <= 1:
        reasons.append("量比小于等于 1")
    if not 5 <= float(quote["turnover_rate"]) <= 10:
        reasons.append("换手率不在 5%-10%")
    if not 5_000_000_000 <= float(quote["total_market_cap"]) <= 20_000_000_000:
        reasons.append("总市值不在 50 亿-200 亿")
    return reasons


def _score_yang(
    quote: Dict[str, Any],
    limit_count: int,
    metrics: IntradayMetrics,
    relative_strength: float,
) -> Tuple[float, List[str]]:
    risk_flags = []
    pct = float(quote["pct_chg"])
    pct_score = 15 if 3.5 <= pct <= 4.8 else 9

    if 1 <= limit_count <= 3:
        limit_score = 15
    elif limit_count == 4:
        limit_score = 8
        risk_flags.append("近20日涨停次数偏多")
    else:
        limit_score = 5
        risk_flags.append("高风险妖股")

    volume_ratio = float(quote["volume_ratio"])
    if 1.5 <= volume_ratio <= 3.5:
        volume_score = 10
    elif 1 < volume_ratio < 1.5:
        volume_score = 6
    elif volume_ratio <= 5:
        volume_score = 5
    else:
        volume_score = 3
        risk_flags.append("异常放量")

    turnover = float(quote["turnover_rate"])
    turnover_score = 15 if 5 <= turnover <= 8 else 9

    cap = float(quote["total_market_cap"])
    cap_score = 10 if 7_000_000_000 <= cap <= 15_000_000_000 else 6

    intraday_score = 12 if metrics.above_vwap_ratio >= 0.8 else 8
    intraday_score += 8 if metrics.current_above_vwap else 0

    breakout_score = 10 if metrics.breakout_after_1430 and metrics.pullback_above_vwap else 0
    strength_bonus = 3 if relative_strength >= 3 else 0
    risk_penalty = min(5, len(risk_flags) * 2)
    score = pct_score + limit_score + volume_score + turnover_score + cap_score + intraday_score + breakout_score
    return round(score + strength_bonus - risk_penalty, 1), risk_flags


def _classify_tail_pattern(intraday: pd.DataFrame, quote: Dict[str, Any], metrics: IntradayMetrics) -> TailPattern:
    tail = metrics.tail
    if tail.empty:
        return TailPattern("sideways_no_signal", "尾盘无有效分时数据", "reject", 0, "缺少 14:30-15:00 分时数据")

    open_price = _day_open(intraday, quote)
    max_pos = tail["price"].idxmax()
    after_max = tail.loc[max_pos:]
    if not after_max.empty and float(after_max["price"].min()) < open_price:
        return TailPattern(
            "up_then_down_break_open",
            "先涨后落并跌破当天开盘价",
            "reject",
            0,
            "尾盘先涨后落并跌破开盘价",
        )

    min_pos = tail["price"].idxmin()
    after_min = tail.loc[min_pos:]
    if not after_min.empty:
        rebound_high = float(after_min["price"].max())
        last_price = float(tail["price"].iloc[-1])
        if rebound_high <= open_price or (rebound_high > open_price and last_price < open_price):
            return TailPattern(
                "down_then_weak_rebound",
                "先跌后弱反弹",
                "reject",
                0,
                "尾盘先跌后反弹不过开盘价或快速回落",
            )

    if metrics.breakout_after_1430 and metrics.pullback_above_vwap:
        return TailPattern("qualified_break_intraday_high", "基础条件满足后尾盘创新高", "buy_candidate", 30)

    if not after_max.empty and (after_max["price"] >= after_max["vwap"]).all():
        return TailPattern("rise_pullback_hold_vwap", "尾盘先涨后回落但不破分时均价线", "watch", 28)

    tail_rise = (float(tail["price"].max()) / float(tail["price"].iloc[0]) - 1) * 100
    tail_above_ratio = float((tail["price"] >= tail["vwap"]).mean())
    volume_status, _, _ = _tail_volume_status(intraday)
    if 0 < tail_rise <= 3 and tail_above_ratio >= 0.70 and volume_status == "mild_volume_up":
        return TailPattern("mild_rise_above_vwap_volume_up", "尾盘小幅拉升并在均线上方温和放量", "watch", 23)

    return TailPattern("sideways_no_signal", "尾盘震荡无有效信号", "reject", 0, "尾盘震荡无明显拉升或成交量亮点")


def _intraday_metrics(intraday: pd.DataFrame, quote: Dict[str, Any]) -> IntradayMetrics:
    tail = _tail_slice(intraday)
    above_vwap_ratio = float((intraday["price"] >= intraday["vwap"]).mean()) if not intraday.empty else 0.0
    current_above_vwap = bool(float(intraday["price"].iloc[-1]) >= float(intraday["vwap"].iloc[-1])) if not intraday.empty else False
    before_tail = intraday[pd.to_datetime(intraday["datetime"]).dt.time < AFTER_1430]
    pre_high = float(before_tail["price"].max()) if not before_tail.empty else float(intraday["price"].max())
    breakout_after_1430 = bool(not tail.empty and float(tail["price"].max()) > pre_high)
    pullback_above_vwap = False
    if breakout_after_1430:
        breakout_rows = tail[tail["price"] > pre_high]
        first_breakout_index = breakout_rows.index[0]
        after_breakout = tail.loc[first_breakout_index:]
        pullback_above_vwap = bool((after_breakout["price"] >= after_breakout["vwap"]).all())
    return IntradayMetrics(
        above_vwap_ratio=above_vwap_ratio,
        current_above_vwap=current_above_vwap,
        breakout_after_1430=breakout_after_1430,
        pullback_above_vwap=pullback_above_vwap,
        tail=tail,
    )


def _tail_volume_status(intraday: pd.DataFrame) -> Tuple[str, float, str]:
    tail = _tail_slice(intraday)
    before = intraday[pd.to_datetime(intraday["datetime"]).dt.time < AFTER_1430]
    if tail.empty:
        return "no_tail_volume", 0, "缺少尾盘成交量"
    tail_avg = float(tail["volume"].mean()) if "volume" in tail else 0
    before_avg = float(before["volume"].mean()) if not before.empty and "volume" in before else tail_avg
    ratio = tail_avg / before_avg if before_avg else 1
    tail_return_pct = (float(tail["price"].iloc[-1]) / float(tail["price"].iloc[0]) - 1) * 100
    latest_below_vwap = float(tail["price"].iloc[-1]) < float(tail["vwap"].iloc[-1])
    if ratio >= 1.2 and (tail_return_pct <= -1.0 or latest_below_vwap):
        return "volume_down", 0, "尾盘放量下跌"
    if 1.0 <= ratio <= 2.5:
        return "mild_volume_up", 10, ""
    if ratio < 1.0:
        return "weak_volume", 4, ""
    return "abnormal_volume_up", 5, ""


def _fund_flow_status(intraday: pd.DataFrame) -> Tuple[str, float, str]:
    if "fund_flow" not in intraday.columns:
        return "unknown", 6, ""
    tail = _tail_slice(intraday)
    if tail.empty:
        return "unknown", 6, ""
    delta = float(tail["fund_flow"].iloc[-1]) - float(tail["fund_flow"].iloc[0])
    if delta < -10:
        return "fast_outflow", 0, "尾盘资金流快速转负"
    if delta >= 0:
        return "stable", 10, ""
    return "unstable", 5, ""


def _ma_score(daily: Dict[str, Any]) -> Tuple[List[str], float]:
    ma5 = _num(daily.get("ma5"), 0)
    ma30 = _num(daily.get("ma30"), 0)
    structure = str(daily.get("ma_structure", ""))
    if structure in {"ma5_golden_cross_ma30", "golden_cross"}:
        return [], 10
    if ma5 >= ma30 and structure in {"ma5_above_ma30_and_up", "ma5_above_ma30"}:
        return [], 8
    return ["5 日线下穿 30 日线或均线结构偏弱"], 0


def _prepare_intraday(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if "datetime" not in df.columns:
        if "时间" in df.columns:
            df["datetime"] = df["时间"]
        elif "日期" in df.columns:
            df["datetime"] = df["日期"]
    if "price" not in df.columns:
        for column in ["收盘", "最新价", "成交价", "close"]:
            if column in df.columns:
                df["price"] = df[column]
                break
    if "volume" not in df.columns:
        for column in ["成交量", "volume"]:
            if column in df.columns:
                df["volume"] = df[column]
                break
    if "amount" not in df.columns:
        for column in ["成交额", "amount"]:
            if column in df.columns:
                df["amount"] = df[column]
                break
    required = {"datetime", "price"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0) if "volume" in df.columns else 1.0
    if "vwap" in df.columns:
        df["vwap"] = pd.to_numeric(df["vwap"], errors="coerce")
    elif "amount" in df.columns and df["volume"].sum() > 0:
        amount = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        cumulative_volume = df["volume"].replace(0, pd.NA).cumsum()
        df["vwap"] = (amount.cumsum() / cumulative_volume).fillna(method="ffill")
    else:
        df["vwap"] = (df["price"] * df["volume"].replace(0, 1)).cumsum() / df["volume"].replace(0, 1).cumsum()
    if "fund_flow" in df.columns:
        df["fund_flow"] = pd.to_numeric(df["fund_flow"], errors="coerce").fillna(0)
    df = df.dropna(subset=["datetime", "price", "vwap"]).sort_values("datetime").reset_index(drop=True)
    return df


def _normalize_minute_bars(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    return _prepare_intraday(raw)


def _normalize_limit_up_pool(raw: pd.DataFrame, trade_date: str) -> List[Dict[str, Any]]:
    rows = []
    for _, row in raw.iterrows():
        code = str(row.get("代码", row.get("code", ""))).zfill(6)
        name = str(row.get("名称", row.get("name", "")))
        rows.append(
            {
                "code": code,
                "name": name,
                "trade_date": trade_date,
                "close_price": _num(row.get("最新价", row.get("close_price")), 0),
                "limit_up_price": _num(row.get("涨停价", row.get("limit_up_price")), 0),
                "limit_up_reason": str(row.get("涨停原因类别", row.get("limit_up_reason", ""))),
            }
        )
    return rows


def _tail_slice(intraday: pd.DataFrame) -> pd.DataFrame:
    if intraday.empty:
        return intraday
    times = pd.to_datetime(intraday["datetime"]).dt.time
    return intraday[(times >= time(14, 30)) & (times <= time(15, 0))].copy()


def _day_open(intraday: pd.DataFrame, quote: Dict[str, Any]) -> float:
    if not intraday.empty:
        return float(intraday["price"].iloc[0])
    return float(quote.get("open", quote.get("price", 0)))


def _decision(strategy_id: str, candidates: List[Dict[str, Any]], empty_note: str) -> Dict[str, Any]:
    buy_actions = {"buy_or_watch", "buy_candidate"}
    can_buy = any(item["action"] in buy_actions for item in candidates)
    if not candidates:
        note = empty_note
    elif can_buy:
        note = "只输出建议，不自动下单；如果没有完全符合条件的股票，建议空仓"
    elif strategy_id == "tail_30m_reversal":
        note = "只输出建议，不自动下单；形态 A、B、E 一律不买"
    else:
        note = "候选仅可观察，未出现尾盘创新高买点，不建议买入"
    return {"can_buy": can_buy, "max_buy_count": 1, "note": note}


def _trade_decision(a_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not a_candidates:
        return {
            "can_buy": False,
            "reason": "没有 A 级严格买入候选，今日空仓",
            "max_buy_count": 1,
            "allow_auto_trade": False,
        }
    top = max(a_candidates, key=lambda item: item["score"])
    return {
        "can_buy": True,
        "reason": "存在 A 级严格买入候选，只允许选择 score 最高的 1 只",
        "max_buy_count": 1,
        "allow_auto_trade": False,
        "selected_code": top["code"],
        "selected_name": top["name"],
        "selected_score": top["score"],
    }


def _rejection(
    quote: Dict[str, Any],
    stage: str,
    reasons: List[str],
    upgrade_requirements: Optional[List[str]] = None,
) -> Dict[str, Any]:
    upgrade_requirements = upgrade_requirements or ["补齐 A 级硬条件后再观察"]
    return {
        "code": quote.get("code", ""),
        "name": quote.get("name", ""),
        "level": "rejected",
        "action": "reject",
        "price": _round(quote.get("price", 0), 2),
        "pct_chg": _round(quote.get("pct_chg", 0), 2),
        "volume_ratio": _round(quote.get("volume_ratio", 0), 2),
        "turnover_rate": _round(quote.get("turnover_rate", 0), 2),
        "total_market_cap": _round(quote.get("total_market_cap", 0), 0),
        "score": 0,
        "stage": REJECTION_STAGE_LABELS.get(stage, stage),
        "reasons": reasons,
        "reject_reasons": reasons,
        "upgrade_requirements": upgrade_requirements,
    }


def _build_near_misses(rejections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scored = []
    for item in rejections:
        reasons = item.get("reasons", [])
        if any(reason in reasons for reason in ["非沪深主板", "ST、退市或风险警示", "停牌"]):
            continue

        pct_chg = float(item.get("pct_chg", 0))
        stage = str(item.get("stage", ""))
        close_to_pct_band = 2.5 <= pct_chg <= 5.5
        if stage == "涨幅榜粗筛" and not close_to_pct_band:
            continue

        score = 100.0
        score -= len(reasons) * 15
        score -= abs(pct_chg - 4.0) * 3
        if stage != "涨幅榜粗筛":
            score += 8

        near = {
            "code": item.get("code", ""),
            "name": item.get("name", ""),
            "price": item.get("price", 0),
            "pct_chg": item.get("pct_chg", 0),
            "volume_ratio": item.get("volume_ratio", 0),
            "turnover_rate": item.get("turnover_rate", 0),
            "total_market_cap": item.get("total_market_cap", 0),
            "stage": stage,
            "reasons": reasons,
            "action": "观察，不买入",
            "observe_note": "接近策略标准但仍有硬条件不满足，只能观察，不能作为买入建议。",
        }
        scored.append((score, near))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:MAX_NEAR_MISSES]]


def _is_main_board(code: str) -> bool:
    code = str(code).zfill(6)
    if code.startswith(EXCLUDED_PREFIXES):
        return False
    return code.startswith(MAIN_BOARD_PREFIXES)


def _is_st_or_delist(name: str) -> bool:
    name = str(name).upper()
    return "ST" in name or "退" in name or "退市" in name


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _normalize_percent(value: Any, default: float = 0.0) -> float:
    number = _num(value, default)
    if number != 0 and abs(number) <= 1:
        return number * 100
    return number


def _normalize_market_cap(value: Any, default: float = 0.0) -> float:
    number = _num(value, default)
    if number <= 0:
        return default
    if number < 10_000:
        return number * 100_000_000
    if number < 1_000_000_000:
        return number * 10_000
    return number


def _round(value: Any, digits: int) -> float:
    return round(_num(value), digits)


def _fmt_threshold(value: Any) -> str:
    number = _num(value)
    return str(int(number)) if number.is_integer() else str(number)
