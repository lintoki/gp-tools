from typing import Any, Dict, List


def build_quality(summary: Dict[str, Any], trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_return = summary.get("total_return_pct", 0.0)
    drawdown = abs(summary.get("max_drawdown_pct", 0.0))
    win_rate = summary.get("win_rate_pct", 0.0)
    trade_count = summary.get("total_trades", 0)
    profit_factor = summary.get("profit_factor", 0.0)

    score = 0
    score += 25 if total_return > 8 else 15 if total_return > 0 else 0
    score += 25 if drawdown < 8 else 15 if drawdown < 15 else 5
    score += 20 if win_rate >= 55 else 10 if win_rate >= 45 else 0
    score += 15 if profit_factor >= 1.5 else 8 if profit_factor >= 1.0 else 0
    score += 15 if trade_count >= 5 else 8 if trade_count >= 2 else 0

    if score >= 80:
        grade = "A"
        conclusion = "历史表现较健康，可进入小仓位观察池。"
    elif score >= 60:
        grade = "B"
        conclusion = "有一定可用性，需要结合盘面人工筛选。"
    elif score >= 40:
        grade = "C"
        conclusion = "表现不稳定，只适合继续观察和调参。"
    else:
        grade = "D"
        conclusion = "暂不建议用于实盘提醒。"

    return {
        "score": score,
        "grade": grade,
        "conclusion": conclusion,
        "sample_size_warning": "交易次数偏少，结论可信度有限。" if trade_count < 10 else "",
    }


def build_operation_advice(strategy_id: str, quality: Dict[str, Any]) -> str:
    prefix = "具体操作：只做提醒，不自动下单。"
    if strategy_id == "overnight_arbitrage":
        detail = (
            "请求时筛选主板涨幅 3%-5%、量比大于 1、换手 5%-10%、市值 50-200 亿、"
            "近 20 日有涨停基因的股票；尾盘决策前再人工确认分时全天在均价线上方、尾盘回踩均线不破、"
            "走势强于大盘至少 2 个点。符合时才加入隔夜观察，次日 9:30-10:00 只卖不买，"
            "高开冲高优先了结，弱势反抽不过开盘价立即卖出，不补仓。"
        )
    elif strategy_id == "tail_30m_reversal":
        detail = (
            "请求时先看涨幅 3%-5% 主板股，尾盘决策前重点复核尾盘 30 分钟形态，优先选择尾盘创新高、回踩分时均价线不破、"
            "成交量温和放大、5 日线强于 30 日线的股票；形态 A、B、E 直接跳过。"
            "次日早盘或上午必须处理，只卖不加仓，不把隔夜套利做成长线持仓。"
        )
    else:
        detail = "按策略输出的候选股逐只人工复核，确认成交量、分时承接和自身仓位后再行动。"

    return f"{prefix}{detail}策略质量：{quality['grade']}，{quality['conclusion']}"
