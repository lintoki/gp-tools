from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from quant.quality import build_operation_advice


class SignalRunner:
    def __init__(self, registry):
        self.registry = registry

    def scan(
        self,
        strategy_id: str,
        bars_by_symbol: Dict[str, pd.DataFrame],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        spec = self.registry.get(strategy_id)
        merged_params = _merge_params(spec, params)
        lookback_days = int(merged_params.get("lookback_days", 20))
        signals = []

        for symbol, bars in bars_by_symbol.items():
            if bars.empty:
                continue
            signal = self._scan_symbol(strategy_id, spec.name, symbol, bars, merged_params, lookback_days)
            if signal:
                signals.append(signal)

        return {
            "strategy_id": strategy_id,
            "strategy_name": spec.name,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scanned_symbols": sorted(bars_by_symbol),
            "signals": signals,
            "empty_advice": "最近窗口没有触发信号，策略建议空仓等待。" if not signals else "",
        }

    def _scan_symbol(
        self,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        bars: pd.DataFrame,
        params: Dict[str, Any],
        lookback_days: int,
    ) -> Dict[str, Any]:
        recent = bars.tail(lookback_days)
        for date_value, row in reversed(list(recent.iterrows())):
            matched, reason = _match_strategy(strategy_id, row, params)
            if not matched:
                continue

            quality_hint = {
                "grade": "观察",
                "conclusion": "这是策略筛出的候选信号，需要结合盘面人工确认。",
            }
            return {
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "symbol": symbol,
                "name": str(row.get("name", symbol)),
                "signal_date": date_value.date().isoformat(),
                "action": "buy_watch",
                "latest_price": round(float(row["close"]), 3),
                "pct_chg": round(float(row.get("pct_chg", 0.0)), 2),
                "trigger_reason": reason,
                "risk_notes": _risk_notes(strategy_id),
                "operation_advice": build_operation_advice(strategy_id, quality_hint),
            }
        return {}


def _merge_params(spec, user_params: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(spec.default_params)
    for key, meta in spec.params_schema.items():
        if "default" in meta:
            merged[key] = meta["default"]
    merged.setdefault("lookback_days", 20)
    merged.update(user_params or {})
    return merged


def _match_strategy(strategy_id: str, row: pd.Series, params: Dict[str, Any]) -> Tuple[bool, str]:
    if strategy_id == "overnight_arbitrage":
        matched = all(
            [
                _between(row.get("pct_chg", 0), params["min_pct_chg"], params["max_pct_chg"]),
                float(row.get("has_limit_up_20d", 0)) >= 1,
                float(row.get("volume_ratio", 0)) >= float(params.get("min_volume_ratio", 1.0)),
                _between(row.get("turnover_rate", 0), params["min_turnover"], params["max_turnover"]),
                _between(
                    row.get("market_cap_billion", 0),
                    params.get("min_market_cap_billion", 50.0),
                    params.get("max_market_cap_billion", 200.0),
                ),
                float(row.get("relative_strength", 0)) >= 2,
                float(row.get("above_vwap", 0)) >= 1,
                float(row.get("close_near_high", 0)) >= float(params.get("min_close_near_high", 0.72)),
            ]
        )
        return matched, "涨幅3-5%、涨停基因、量比/换手/市值合规、尾盘承接强"

    if strategy_id == "tail_30m_reversal":
        matched = all(
            [
                _between(row.get("pct_chg", 0), params["min_pct_chg"], params["max_pct_chg"]),
                float(row.get("volume_ratio", 0)) >= float(params.get("min_volume_ratio", 1.0)),
                _between(row.get("turnover_rate", 0), params.get("min_turnover", 5.0), params.get("max_turnover", 10.0)),
                _between(
                    row.get("market_cap_billion", 0),
                    params.get("min_market_cap_billion", 50.0),
                    params.get("max_market_cap_billion", 200.0),
                ),
                float(row.get("ma5_gt_ma30", 0)) >= 1,
                float(row.get("above_vwap", 0)) >= 1,
                float(row.get("close_near_high", 0)) >= float(params.get("min_close_near_high", 0.8)),
                float(row.get("close", 0)) > float(row.get("open", 0)),
            ]
        )
        return matched, "尾盘站稳均线、成交放大、收盘接近日内高位、均线趋势向上"

    raise KeyError(f"unknown strategy: {strategy_id}")


def _between(value: Any, low: Any, high: Any) -> bool:
    return float(low) <= float(value) <= float(high)


def _risk_notes(strategy_id: str) -> str:
    if strategy_id == "overnight_arbitrage":
        return "若 14:30 后跌破分时均价线、量能突然萎缩、或次日不冲高，应放弃或及时止损。"
    if strategy_id == "tail_30m_reversal":
        return "若尾盘先涨后跌破开盘价、反弹不过开盘价、或只是无量震荡，信号应剔除。"
    return "信号只代表进入观察范围，不能替代人工决策。"
