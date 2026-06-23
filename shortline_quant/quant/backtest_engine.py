from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from quant.models import BacktestResult
from quant.quality import build_operation_advice, build_quality
from quant.realtime_screener import _is_main_board, _is_st_or_delist
from quant.signal_runner import _merge_params
from quant.strategy_config import merge_strategy_config


class BacktestEngine:
    def __init__(self, registry):
        self.registry = registry

    def run(
        self,
        strategy_id: str,
        bars_by_symbol: Dict[str, pd.DataFrame],
        initial_cash: float,
        commission: float,
        slippage: float,
        params: Dict[str, Any],
    ) -> BacktestResult:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not bars_by_symbol:
            raise ValueError("bars_by_symbol cannot be empty")

        spec = self.registry.get(strategy_id)
        merged_params = _merge_params(spec, params)
        start_date = merged_params.get("start_date")
        end_date = merged_params.get("end_date")
        success_return_pct = float(merged_params.get("success_return_pct", 1.0))
        stake_pct_per_signal = float(merged_params.get("stake_pct_per_signal", 0.1))

        trades: List[Dict[str, Any]] = []
        for symbol, bars in bars_by_symbol.items():
            if bars.empty:
                continue
            trades.extend(
                _evaluate_symbol_by_next_day(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    bars=bars.sort_index(),
                    params=merged_params,
                    initial_cash=initial_cash,
                    stake_pct_per_signal=stake_pct_per_signal,
                    commission=commission,
                    slippage=slippage,
                    success_return_pct=success_return_pct,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

        trades = sorted(trades, key=lambda item: (item["signal_date"], item["symbol"]))
        equity_curve = _build_equity_curve(initial_cash, trades)
        summary = _build_summary(strategy_id, initial_cash, trades, equity_curve)
        quality = build_quality(summary, trades)
        summary.update(
            {
                "backtest_mode": "daily_cross_section",
                "universe_mode": "historical_daily_ranked_quotes",
                "stock_pool_rule": "每个T日先按历史日线涨幅榜口径筛沪深主板、非ST、涨幅3%-5%，再执行策略硬条件并做T+1验证。",
                "evaluation_rule": f"T日生成候选，T+1最高涨幅达到 {success_return_pct:.2f}% 记为正确；收益按T+1收盘模拟兑现。",
                "start_date": start_date,
                "end_date": end_date,
                "quality": quality,
                "operation_advice": build_operation_advice(strategy_id, quality),
                "strategy_name": spec.name,
                "symbols": sorted(bars_by_symbol),
                "run_id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{strategy_id}",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return BacktestResult(summary=summary, trades=trades, equity_curve=equity_curve)


def _evaluate_symbol_by_next_day(
    strategy_id: str,
    symbol: str,
    bars: pd.DataFrame,
    params: Dict[str, Any],
    initial_cash: float,
    stake_pct_per_signal: float,
    commission: float,
    slippage: float,
    success_return_pct: float,
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    trades = []
    rows = list(bars.iterrows())
    for idx in range(len(rows) - 1):
        signal_date, signal_row = rows[idx]
        evaluation_date, next_row = rows[idx + 1]
        signal_date_str = signal_date.date().isoformat()
        if start_date and signal_date_str < start_date:
            continue
        if end_date and signal_date_str > end_date:
            continue
        if not _passes_historical_daily_ranked_universe(strategy_id, symbol, signal_row, params):
            continue
        classification = _classify_backtest_candidate(strategy_id, signal_row, params)
        if classification["level"] == "rejected":
            continue

        entry_price = float(signal_row["close"]) * (1 + slippage)
        exit_price = float(next_row["close"]) * (1 - slippage)
        next_high = float(next_row["high"])
        next_close = float(next_row["close"])
        next_open = float(next_row["open"])
        stake_cash = initial_cash * stake_pct_per_signal
        shares = int(stake_cash / max(entry_price, 0.01) / 100) * 100
        gross_pnl = (exit_price - entry_price) * shares
        fees = (entry_price * shares + exit_price * shares) * commission
        pnl = gross_pnl - fees
        next_day_high_return_pct = (next_high / entry_price - 1) * 100
        next_day_close_return_pct = (next_close / entry_price - 1) * 100
        next_day_open_return_pct = (next_open / entry_price - 1) * 100
        is_correct = next_day_high_return_pct >= success_return_pct

        trades.append(
            {
                "symbol": symbol,
                "name": str(signal_row.get("name", symbol)),
                "signal_date": signal_date_str,
                "evaluation_date": evaluation_date.date().isoformat(),
                "entry_date": signal_date.date().isoformat(),
                "exit_date": evaluation_date.date().isoformat(),
                "entry_price": round(entry_price, 3),
                "exit_price": round(exit_price, 3),
                "shares": shares,
                "pnl": round(pnl, 2),
                "return_pct": round(next_day_close_return_pct, 2),
                "next_day_open_return_pct": round(next_day_open_return_pct, 2),
                "next_day_high_return_pct": round(next_day_high_return_pct, 2),
                "next_day_close_return_pct": round(next_day_close_return_pct, 2),
                "is_correct": is_correct,
                "evaluation_basis": "next_day_high",
                "candidate_level": classification["level"],
                "action": classification["action"],
                "reject_reasons": classification["reject_reasons"],
                "upgrade_requirements": classification["upgrade_requirements"],
                "evaluation_only": False,
                "hold_days": 1,
                "reason": classification["reason"],
            }
        )
    return trades


def _passes_historical_daily_ranked_universe(strategy_id: str, symbol: str, row: pd.Series, params: Dict[str, Any]) -> bool:
    config = merge_strategy_config(strategy_id, params)
    c_cfg = _level_cfg(config, "C")
    code = str(row.get("code", symbol)).zfill(6)
    name = str(row.get("name", ""))
    pct_chg = float(row.get("pct_chg", 0))
    close_price = float(row.get("close", 0))
    if not _is_main_board(code):
        return False
    if _is_st_or_delist(name):
        return False
    if close_price <= 0:
        return False
    return _between_cfg(pct_chg, c_cfg, "pct_chg")


def _classify_backtest_candidate(strategy_id: str, row: pd.Series, params: Dict[str, Any]) -> Dict[str, Any]:
    config = merge_strategy_config(strategy_id, params)
    a_reasons = _backtest_a_reject_reasons(strategy_id, row, config)
    if not a_reasons:
        return {
            "level": "A",
            "action": "buy_candidate",
            "reason": "A级严格买入候选，T+1 纳入模拟买入验证",
            "reject_reasons": [],
            "upgrade_requirements": [],
        }

    b_reasons = _backtest_b_reject_reasons(strategy_id, row, config)
    if not b_reasons:
        return {
            "level": "B",
            "action": "watch",
            "reason": "B级重点观察候选，T+1 纳入模拟买入验证；实盘仍只观察不自动下单",
            "reject_reasons": a_reasons,
            "upgrade_requirements": _backtest_upgrade_requirements(strategy_id, row, config),
        }

    c_reasons = _backtest_c_reject_reasons(row, config)
    if not c_reasons:
        return {
            "level": "C",
            "action": "watch",
            "reason": "C级预备观察池，T+1 纳入模拟买入验证；实盘只用于复盘观察",
            "reject_reasons": list(dict.fromkeys(a_reasons + b_reasons)),
            "upgrade_requirements": _backtest_upgrade_requirements(strategy_id, row, config),
        }

    return {
        "level": "rejected",
        "action": "reject",
        "reason": "不满足 A/B/C 候选池条件",
        "reject_reasons": c_reasons,
        "upgrade_requirements": _backtest_upgrade_requirements(strategy_id, row, config),
    }


def _backtest_a_reject_reasons(strategy_id: str, row: pd.Series, config: Dict[str, Any]) -> List[str]:
    cfg = _level_cfg(config, "A")
    reasons = []
    if not _between_cfg(_row_float(row, "pct_chg"), cfg, "pct_chg"):
        reasons.append(_range_reason("涨幅", "A", cfg, "pct_chg"))
    if _row_float(row, "volume_ratio") < cfg.get("min_volume_ratio", 1):
        reasons.append(f"量比低于 A 级 {cfg.get('min_volume_ratio', 1)}")
    if not _between_cfg(_row_float(row, "turnover_rate"), cfg, "turnover_rate"):
        reasons.append(_range_reason("换手率", "A", cfg, "turnover_rate"))
    if not _between_cfg(_row_float(row, "market_cap_billion"), cfg, "market_cap_billion"):
        reasons.append(_range_reason("总市值", "A", cfg, "market_cap_billion", " 亿"))
    if _above_vwap_value(row) < cfg.get("min_above_vwap_ratio", 0):
        reasons.append("日线近似分时均价线承接不足")
    if strategy_id == "overnight_arbitrage":
        if _row_float(row, "has_limit_up_20d") < cfg.get("min_limit_up_count_20d", 1):
            reasons.append(f"近20个交易日涨停次数低于 A 级 {cfg.get('min_limit_up_count_20d', 1)}")
        if _row_float(row, "relative_strength") < cfg.get("min_relative_strength", 0):
            reasons.append(f"相对强度低于 A 级 {cfg.get('min_relative_strength', 0)}")
        if _row_float(row, "close_near_high") < cfg.get("min_close_near_high", 0):
            reasons.append("收盘位置未接近日内高位")
    if strategy_id == "tail_30m_reversal":
        if _row_float(row, "ma5_gt_ma30") < 1:
            reasons.append("均线结构未达到 A 级")
        if _row_float(row, "close_near_high") < cfg.get("min_close_near_high", 0):
            reasons.append("收盘位置未接近日内高位")
        if _row_float(row, "close") <= _row_float(row, "open"):
            reasons.append("收盘没有强于开盘")
    if _has_row_value(row, "score") and _row_float(row, "score") < cfg.get("min_score", 0):
        reasons.append(f"评分低于 A 级 {cfg.get('min_score', 0)}")
    return reasons


def _backtest_b_reject_reasons(strategy_id: str, row: pd.Series, config: Dict[str, Any]) -> List[str]:
    cfg = _level_cfg(config, "B")
    reasons = []
    if not _between_cfg(_row_float(row, "pct_chg"), cfg, "pct_chg"):
        reasons.append(_range_reason("涨幅", "B", cfg, "pct_chg"))
    if _row_float(row, "volume_ratio") < cfg.get("min_volume_ratio", 0):
        reasons.append(f"量比低于 B 级 {cfg.get('min_volume_ratio', 0)}")
    if not _between_cfg(_row_float(row, "turnover_rate"), cfg, "turnover_rate"):
        reasons.append(_range_reason("换手率", "B", cfg, "turnover_rate"))
    if not _between_cfg(_row_float(row, "market_cap_billion"), cfg, "market_cap_billion"):
        reasons.append(_range_reason("总市值", "B", cfg, "market_cap_billion", " 亿"))
    if _above_vwap_value(row) < cfg.get("min_above_vwap_ratio", 0):
        reasons.append("均价承接未达到 B 级")
    if strategy_id == "overnight_arbitrage":
        if _row_float(row, "has_limit_up_20d") < cfg.get("min_limit_up_count_20d", 0):
            reasons.append(f"近20个交易日涨停次数低于 B 级 {cfg.get('min_limit_up_count_20d', 0)}")
        if _row_float(row, "relative_strength") < cfg.get("min_relative_strength", 0):
            reasons.append(f"相对强度低于 B 级 {cfg.get('min_relative_strength', 0)}")
    if strategy_id == "tail_30m_reversal" and _row_float(row, "ma5_gt_ma30") < 1:
        reasons.append("均线结构未达到 B 级")
    if _row_float(row, "close_near_high") < cfg.get("min_close_near_high", 0):
        reasons.append("收盘位置未达到 B 级")
    return reasons


def _backtest_c_reject_reasons(row: pd.Series, config: Dict[str, Any]) -> List[str]:
    cfg = _level_cfg(config, "C")
    reasons = []
    if not _between_cfg(_row_float(row, "pct_chg"), cfg, "pct_chg"):
        reasons.append(_range_reason("涨幅", "C", cfg, "pct_chg"))
    if _row_float(row, "volume_ratio") < cfg.get("min_volume_ratio", 0):
        reasons.append(f"量比低于 C 级 {cfg.get('min_volume_ratio', 0)}")
    if not _between_cfg(_row_float(row, "turnover_rate"), cfg, "turnover_rate"):
        reasons.append(_range_reason("换手率", "C", cfg, "turnover_rate"))
    if not _between_cfg(_row_float(row, "market_cap_billion"), cfg, "market_cap_billion"):
        reasons.append(_range_reason("总市值", "C", cfg, "market_cap_billion", " 亿"))
    return reasons


def _backtest_upgrade_requirements(strategy_id: str, row: pd.Series, config: Dict[str, Any]) -> List[str]:
    requirements = []
    for reason in _backtest_a_reject_reasons(strategy_id, row, config):
        if "涨幅" in reason:
            requirements.append("涨幅进入 3%-5% 区间")
        elif "量比" in reason:
            requirements.append("量比提升到 1 以上")
        elif "换手率" in reason:
            requirements.append("换手率进入 5%-10%")
        elif "总市值" in reason:
            requirements.append("总市值进入 50 亿-200 亿")
        elif "涨停" in reason:
            requirements.append("近20个交易日至少有 1 次涨停")
        elif "相对强度" in reason:
            requirements.append("相对强度提升到 2 以上")
        elif "均线" in reason:
            requirements.append("均线结构转为 5 日线上穿或站上 30 日线")
        elif "高位" in reason:
            requirements.append("尾盘收盘位置接近日内高位")
    if not requirements:
        requirements.append("补齐 A 级硬条件后才允许买入")
    return list(dict.fromkeys(requirements))


def _level_cfg(config: Dict[str, Any], level: str) -> Dict[str, Any]:
    return config.get("levels", {}).get(level, {})


def _between_cfg(value: float, cfg: Dict[str, Any], key: str) -> bool:
    return float(cfg.get(f"min_{key}", float("-inf"))) <= float(value) <= float(cfg.get(f"max_{key}", float("inf")))


def _range_reason(label: str, level: str, cfg: Dict[str, Any], key: str, unit: str = "%") -> str:
    return f"{label}未达到 {level} 级 {cfg.get(f'min_{key}')}{unit}-{cfg.get(f'max_{key}')}{unit}"


def _row_float(row: pd.Series, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _above_vwap_value(row: pd.Series) -> float:
    if _has_row_value(row, "above_vwap_ratio"):
        return _row_float(row, "above_vwap_ratio")
    return _row_float(row, "above_vwap")


def _has_row_value(row: pd.Series, key: str) -> bool:
    return key in row.index and pd.notna(row.get(key))


def _build_summary(
    strategy_id: str,
    initial_cash: float,
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_pnl = sum(trade["pnl"] for trade in trades)
    end_value = initial_cash + total_pnl
    total_return = (total_pnl / initial_cash) * 100 if initial_cash else 0.0
    evaluated_signals = len(trades)
    correct_signals = sum(1 for trade in trades if trade["is_correct"])
    signal_accuracy = correct_signals / evaluated_signals * 100 if evaluated_signals else 0.0
    daily_results = _build_daily_results(trades)
    level_stats = _build_level_stats(trades)
    correct_days = sum(1 for item in daily_results if item["is_correct_day"])
    day_accuracy = correct_days / len(daily_results) * 100 if daily_results else 0.0
    wins = [trade for trade in trades if trade["pnl"] > 0]
    losses = [trade for trade in trades if trade["pnl"] < 0]
    gross_profit = sum(trade["pnl"] for trade in wins)
    gross_loss = abs(sum(trade["pnl"] for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit else 0.0)

    return {
        "strategy_id": strategy_id,
        "start_value": round(initial_cash, 2),
        "end_value": round(end_value, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(_max_drawdown_pct(equity_curve), 2),
        "win_rate_pct": round(signal_accuracy, 2),
        "signal_accuracy_pct": round(signal_accuracy, 2),
        "day_accuracy_pct": round(day_accuracy, 2),
        "evaluated_signals": evaluated_signals,
        "correct_signals": correct_signals,
        "days_with_signals": len(daily_results),
        "correct_days": correct_days,
        "profit_factor": round(profit_factor, 2),
        "total_trades": evaluated_signals,
        "avg_trade_return_pct": round(
            sum(trade["return_pct"] for trade in trades) / evaluated_signals, 2
        )
        if evaluated_signals
        else 0.0,
        "daily_results": daily_results[-30:],
        "level_stats": level_stats,
    }


def _build_daily_results(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade["signal_date"]].append(trade)

    results = []
    for signal_date in sorted(grouped):
        day_trades = grouped[signal_date]
        correct_count = sum(1 for trade in day_trades if trade["is_correct"])
        avg_high = sum(trade["next_day_high_return_pct"] for trade in day_trades) / len(day_trades)
        avg_close = sum(trade["next_day_close_return_pct"] for trade in day_trades) / len(day_trades)
        results.append(
            {
                "signal_date": signal_date,
                "candidate_count": len(day_trades),
                "correct_count": correct_count,
                "is_correct_day": correct_count > 0,
                "avg_next_day_high_return_pct": round(avg_high, 2),
                "avg_next_day_close_return_pct": round(avg_close, 2),
            }
        )
    return results


def _build_level_stats(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {}
    for level in ["A", "B", "C"]:
        level_trades = [trade for trade in trades if trade.get("candidate_level") == level]
        evaluated = len(level_trades)
        correct = sum(1 for trade in level_trades if trade["is_correct"])
        result[level] = {
            "evaluated_signals": evaluated,
            "correct_signals": correct,
            "accuracy_pct": round(correct / evaluated * 100, 2) if evaluated else 0.0,
            "avg_next_day_high_return_pct": round(
                sum(trade["next_day_high_return_pct"] for trade in level_trades) / evaluated, 2
            )
            if evaluated
            else 0.0,
            "simulated_buy": True,
        }
    return result


def _build_equity_curve(initial_cash: float, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pnl_by_date = defaultdict(float)
    for trade in trades:
        pnl_by_date[trade["evaluation_date"]] += trade["pnl"]

    equity = initial_cash
    curve = []
    for evaluation_date in sorted(pnl_by_date):
        equity += pnl_by_date[evaluation_date]
        curve.append({"date": evaluation_date, "symbol": "ALL", "equity": round(equity, 2)})
    if not curve:
        curve.append({"date": datetime.now().date().isoformat(), "symbol": "ALL", "equity": round(initial_cash, 2)})
    return curve


def _max_drawdown_pct(equity_curve: List[Dict[str, Any]]) -> float:
    peak = None
    max_drawdown = 0.0
    for point in sorted(equity_curve, key=lambda item: item["date"]):
        equity = point["equity"]
        peak = equity if peak is None else max(peak, equity)
        if peak:
            drawdown = (equity / peak - 1) * 100
            max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown
