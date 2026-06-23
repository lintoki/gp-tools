from typing import Dict, Iterable, List

from quant.models import StrategySpec
from quant.strategies.overnight_arbitrage import get_spec as overnight_spec
from quant.strategies.tail_30m_reversal import get_spec as tail_30m_spec


class StrategyRegistry:
    def __init__(self, specs: Iterable[StrategySpec]):
        self._specs: Dict[str, StrategySpec] = {spec.strategy_id: spec for spec in specs}

    @classmethod
    def load_builtin(cls) -> "StrategyRegistry":
        return cls([overnight_spec(), tail_30m_spec()])

    def list_specs(self) -> List[Dict]:
        return [self._specs[key].to_dict() for key in sorted(self._specs)]

    def get(self, strategy_id: str) -> StrategySpec:
        try:
            return self._specs[strategy_id]
        except KeyError as exc:
            raise KeyError(f"unknown strategy: {strategy_id}") from exc
