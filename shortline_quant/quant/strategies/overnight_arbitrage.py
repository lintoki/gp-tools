from quant.models import StrategySpec
from quant.strategies.common import BASE_PARAMS, TailBaseStrategy, between


class OvernightArbitrageStrategy(TailBaseStrategy):
    params = BASE_PARAMS + (
        ("min_pct_chg", 3.0),
        ("max_pct_chg", 5.0),
        ("min_turnover", 5.0),
        ("max_turnover", 10.0),
        ("min_market_cap_billion", 50.0),
        ("max_market_cap_billion", 200.0),
        ("min_volume_ratio", 1.0),
        ("min_close_near_high", 0.72),
    )

    def should_enter(self):
        checks = [
            between(self.data.pct_chg[0], self.p.min_pct_chg, self.p.max_pct_chg),
            self.data.has_limit_up_20d[0] >= 1,
            self.data.volume_ratio[0] >= self.p.min_volume_ratio,
            between(self.data.turnover_rate[0], self.p.min_turnover, self.p.max_turnover),
            between(
                self.data.market_cap_billion[0],
                self.p.min_market_cap_billion,
                self.p.max_market_cap_billion,
            ),
            self.data.relative_strength[0] >= 2,
            self.data.above_vwap[0] >= 1,
            self.data.close_near_high[0] >= self.p.min_close_near_high,
        ]
        if all(checks):
            return True, "涨幅3-5%、涨停基因、量比/换手/市值合规、尾盘承接强"
        return False, ""


def get_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="overnight_arbitrage",
        name="杨永兴隔夜套利法",
        description="14:30 后从实时涨幅榜筛选主板 3%-5% 强势股，隔夜持有，次日早盘只卖不加仓。",
        source_note="/Users/zhihu/Desktop/短线.txt",
        supported_timeframes=["day", "5m-later"],
        default_params={
            "max_hold_days": 1,
            "stop_loss_pct": 3.0,
            "take_profit_pct": 6.0,
            "stake_pct": 0.9,
        },
        params_schema={
            "min_pct_chg": {"label": "最小涨幅", "default": 3.0},
            "max_pct_chg": {"label": "最大涨幅", "default": 5.0},
            "min_turnover": {"label": "最小换手率", "default": 5.0},
            "max_turnover": {"label": "最大换手率", "default": 10.0},
            "min_volume_ratio": {"label": "最小量比", "default": 1.0},
            "stop_loss_pct": {"label": "止损百分比", "default": 3.0},
            "take_profit_pct": {"label": "止盈百分比", "default": 6.0},
        },
        limitations=[
            "页面实时信号使用涨幅榜和分时数据；历史回测仍用日线字段近似尾盘形态。",
            "策略只输出候选和建议，不允许自动下单。",
        ],
        bt_strategy_class=OvernightArbitrageStrategy,
    )
