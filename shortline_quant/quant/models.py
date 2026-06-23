from dataclasses import dataclass
from typing import Any, Dict, List, Type


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    description: str
    source_note: str
    supported_timeframes: List[str]
    default_params: Dict[str, Any]
    params_schema: Dict[str, Dict[str, Any]]
    limitations: List[str]
    bt_strategy_class: Type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "source_note": self.source_note,
            "supported_timeframes": self.supported_timeframes,
            "default_params": self.default_params,
            "params_schema": self.params_schema,
            "limitations": self.limitations,
        }


@dataclass
class BacktestResult:
    summary: Dict[str, Any]
    trades: List[Dict[str, Any]]
    equity_curve: List[Dict[str, Any]]
