from quant.models import StrategySpec
from quant.strategies.common import BASE_PARAMS, TailBaseStrategy, between


class Tail30mReversalStrategy(TailBaseStrategy):
    params = BASE_PARAMS + (
        ("min_pct_chg", 3.0),
        ("max_pct_chg", 5.0),
        ("min_turnover", 5.0),
        ("max_turnover", 10.0),
        ("min_market_cap_billion", 50.0),
        ("max_market_cap_billion", 200.0),
        ("min_volume_ratio", 1.0),
        ("min_close_near_high", 0.8),
    )

    def should_enter(self):
        checks = [
            between(self.data.pct_chg[0], self.p.min_pct_chg, self.p.max_pct_chg),
            self.data.volume_ratio[0] >= self.p.min_volume_ratio,
            between(self.data.turnover_rate[0], self.p.min_turnover, self.p.max_turnover),
            between(
                self.data.market_cap_billion[0],
                self.p.min_market_cap_billion,
                self.p.max_market_cap_billion,
            ),
            self.data.ma5_gt_ma30[0] >= 1,
            self.data.above_vwap[0] >= 1,
            self.data.close_near_high[0] >= self.p.min_close_near_high,
            self.data.close[0] > self.data.open[0],
        ]
        if all(checks):
            return True, "尾盘站稳均线、成交放大、收盘接近日内高位、均线趋势向上"
        return False, ""


def get_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="tail_30m_reversal",
        name="尾盘30分钟强承接策略",
        description="请求时分析主板 3%-5% 股票的分时强弱，尾盘阶段重点识别次日早盘冲高套利机会。",
        source_note="/Users/zhihu/Desktop/尾盘交易",
        supported_timeframes=["day", "30m-later", "5m-later"],
        default_params={
            "max_hold_days": 1,
            "stop_loss_pct": 3.0,
            "take_profit_pct": 5.0,
            "stake_pct": 0.9,
        },
        params_schema={
            "min_pct_chg": {"label": "最小涨幅", "default": 3.0},
            "max_pct_chg": {"label": "最大涨幅", "default": 5.0},
            "min_turnover": {"label": "最小换手率", "default": 5.0},
            "max_turnover": {"label": "最大换手率", "default": 10.0},
            "min_volume_ratio": {"label": "最小量比", "default": 1.0},
            "min_close_near_high": {"label": "收盘接近日内高位", "default": 0.8},
            "stop_loss_pct": {"label": "止损百分比", "default": 3.0},
            "take_profit_pct": {"label": "止盈百分比", "default": 5.0},
        },
        limitations=[
            "页面实时信号会分类尾盘形态；历史回测只能用日线字段近似。",
            "次日早盘或上午必须处理，不把短线票变成长线持有。",
        ],
        bt_strategy_class=Tail30mReversalStrategy,
    )
