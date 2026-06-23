import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


LEVEL_LABELS = {
    "A": "A 级严格买入候选",
    "B": "B 级重点观察候选",
    "C": "C 级预备观察池",
}


FIELD_LABELS = {
    "min_pct_chg": "最小涨幅",
    "max_pct_chg": "最大涨幅",
    "min_volume_ratio": "最小量比",
    "min_turnover_rate": "最小换手率",
    "max_turnover_rate": "最大换手率",
    "min_market_cap_billion": "最小总市值（亿）",
    "max_market_cap_billion": "最大总市值（亿）",
    "min_limit_up_count_20d": "近 20 日最少涨停次数",
    "min_above_vwap_ratio": "最小均价线上方比例",
    "min_relative_strength": "最小相对强度",
    "min_score": "最小评分",
    "min_close_near_high": "最低收盘接近日内高位比例",
}


DEFAULT_STRATEGY_CONFIGS: Dict[str, Dict[str, Any]] = {
    "overnight_arbitrage": {
        "levels": {
            "A": {
                "min_pct_chg": 3.0,
                "max_pct_chg": 5.0,
                "min_volume_ratio": 1.01,
                "min_turnover_rate": 5.0,
                "max_turnover_rate": 10.0,
                "min_market_cap_billion": 50.0,
                "max_market_cap_billion": 200.0,
                "min_limit_up_count_20d": 1,
                "min_above_vwap_ratio": 0.70,
                "min_relative_strength": 2.0,
                "min_score": 70.0,
                "min_close_near_high": 0.72,
            },
            "B": {
                "min_pct_chg": 2.8,
                "max_pct_chg": 5.5,
                "min_volume_ratio": 1.0,
                "min_turnover_rate": 4.0,
                "max_turnover_rate": 11.0,
                "min_market_cap_billion": 45.0,
                "max_market_cap_billion": 220.0,
                "min_limit_up_count_20d": 1,
                "min_above_vwap_ratio": 0.60,
                "min_relative_strength": 1.0,
                "min_score": 0.0,
                "min_close_near_high": 0.0,
            },
            "C": {
                "min_pct_chg": 2.0,
                "max_pct_chg": 6.0,
                "min_volume_ratio": 0.8,
                "min_turnover_rate": 3.0,
                "max_turnover_rate": 12.0,
                "min_market_cap_billion": 40.0,
                "max_market_cap_billion": 250.0,
                "min_limit_up_count_20d": 0,
                "min_above_vwap_ratio": 0.0,
                "min_relative_strength": 0.0,
                "min_score": 0.0,
                "min_close_near_high": 0.0,
            },
        }
    },
    "tail_30m_reversal": {
        "levels": {
            "A": {
                "min_pct_chg": 3.0,
                "max_pct_chg": 5.0,
                "min_volume_ratio": 1.01,
                "min_turnover_rate": 5.0,
                "max_turnover_rate": 10.0,
                "min_market_cap_billion": 50.0,
                "max_market_cap_billion": 200.0,
                "min_above_vwap_ratio": 0.0,
                "min_score": 70.0,
                "min_close_near_high": 0.80,
            },
            "B": {
                "min_pct_chg": 2.8,
                "max_pct_chg": 5.5,
                "min_volume_ratio": 1.0,
                "min_turnover_rate": 4.0,
                "max_turnover_rate": 11.0,
                "min_market_cap_billion": 45.0,
                "max_market_cap_billion": 220.0,
                "min_above_vwap_ratio": 0.0,
                "min_score": 0.0,
                "min_close_near_high": 0.65,
            },
            "C": {
                "min_pct_chg": 2.0,
                "max_pct_chg": 6.0,
                "min_volume_ratio": 0.8,
                "min_turnover_rate": 3.0,
                "max_turnover_rate": 12.0,
                "min_market_cap_billion": 40.0,
                "max_market_cap_billion": 250.0,
                "min_above_vwap_ratio": 0.0,
                "min_score": 0.0,
                "min_close_near_high": 0.0,
            },
        }
    },
}


def default_strategy_config(strategy_id: str) -> Dict[str, Any]:
    if strategy_id not in DEFAULT_STRATEGY_CONFIGS:
        raise KeyError(f"unknown strategy config: {strategy_id}")
    return deepcopy(DEFAULT_STRATEGY_CONFIGS[strategy_id])


def merge_strategy_config(strategy_id: str, override: Dict[str, Any] = None) -> Dict[str, Any]:
    config = default_strategy_config(strategy_id)
    _deep_update(config, override or {})
    return config


def strategy_config_payload(strategy_id: str, config: Dict[str, Any], strategy_name: str = "") -> Dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "config": config,
        "defaults": default_strategy_config(strategy_id),
        "field_labels": FIELD_LABELS,
        "level_labels": LEVEL_LABELS,
        "standards": _standards(config),
    }


def _standards(config: Dict[str, Any]) -> Dict[str, str]:
    standards = {}
    for level, values in config.get("levels", {}).items():
        standards[level] = (
            f"涨幅 {_fmt_value(values.get('min_pct_chg'))}%-{_fmt_value(values.get('max_pct_chg'))}%，"
            f"量比不低于 {_fmt_value(values.get('min_volume_ratio'))}，"
            f"换手率 {_fmt_value(values.get('min_turnover_rate'))}%-{_fmt_value(values.get('max_turnover_rate'))}%，"
            f"总市值 {_fmt_value(values.get('min_market_cap_billion'))}-{_fmt_value(values.get('max_market_cap_billion'))} 亿"
        )
    return standards


def _fmt_value(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def _deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


class StrategyConfigStore:
    def __init__(self, path: Path):
        self.path = path

    def get(self, strategy_id: str) -> Dict[str, Any]:
        stored = self._load().get(strategy_id, {})
        return merge_strategy_config(strategy_id, stored)

    def save(self, strategy_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        merged = merge_strategy_config(strategy_id, config)
        all_configs = self._load()
        all_configs[strategy_id] = merged
        self._write(all_configs)
        return merged

    def reset(self, strategy_id: str) -> Dict[str, Any]:
        all_configs = self._load()
        if strategy_id in all_configs:
            del all_configs[strategy_id]
            self._write(all_configs)
        return default_strategy_config(strategy_id)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
