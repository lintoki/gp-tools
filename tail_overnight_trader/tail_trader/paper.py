import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List

from .models import MinuteBar, PaperTrade, ReviewResult
from .retention import trim_jsonl_file


def _time_part(value: str) -> str:
    return str(value).split()[-1]


def append_trade(path: Path, trade: PaperTrade) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(asdict(trade), ensure_ascii=False) + "\n")
    trim_jsonl_file(path)


def load_trades(path: Path) -> List[PaperTrade]:
    if not path.exists():
        return []
    trades: List[PaperTrade] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            trades.append(PaperTrade(**json.loads(line)))
    return trades


def decide_morning_exit(
    trade: PaperTrade,
    minute_bars: Iterable[MinuteBar],
    target_profit_pct: float,
    stop_loss_pct: float,
    exit_deadline: str = "10:30:00",
) -> ReviewResult:
    morning_bars = [bar for bar in minute_bars if _time_part(bar.time) <= exit_deadline]
    if not morning_bars:
        raise ValueError(f"{trade.code} 缺少次日早盘分时数据")

    target_price = trade.entry_price * (1 + target_profit_pct / 100)
    stop_price = trade.entry_price * (1 - stop_loss_pct / 100)
    exit_bar = morning_bars[-1]
    exit_price = exit_bar.close
    exit_reason = "MORNING_TIMEOUT"

    for bar in morning_bars:
        if bar.low <= stop_price:
            exit_bar = bar
            exit_price = stop_price
            exit_reason = "STOP_LOSS"
            break
        if bar.high >= target_price:
            exit_bar = bar
            exit_price = target_price
            exit_reason = "TARGET_HIT"
            break

    return_pct = (exit_price / trade.entry_price - 1) * 100
    profit_yuan = (exit_price - trade.entry_price) * trade.shares
    return ReviewResult(
        trade=trade,
        exit_date=str(exit_bar.time).split()[0],
        exit_time=_time_part(exit_bar.time),
        exit_price=round(exit_price, 4),
        exit_reason=exit_reason,
        return_pct=round(return_pct, 4),
        profit_yuan=round(profit_yuan, 2),
    )


def build_review_markdown(review_date: str, results: Iterable[ReviewResult]) -> str:
    rows = list(results)
    total_profit = sum(result.profit_yuan for result in rows)
    avg_return = sum(result.return_pct for result in rows) / len(rows) if rows else 0.0
    lines = [
        f"# 尾盘隔夜策略复盘 {review_date}",
        "",
        f"- 交易数：{len(rows)}",
        f"- 平均收益率：{avg_return:+.2f}%",
        f"- 纸面盈亏：{total_profit:+.2f} 元",
        "",
        "| 代码 | 名称 | 买入价 | 卖出价 | 收益率 | 退出原因 |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for result in rows:
        trade = result.trade
        lines.append(
            f"| {trade.code} | {trade.name} | {trade.entry_price:.3f} | "
            f"{result.exit_price:.3f} | {result.return_pct:+.2f}% | {result.exit_reason} |"
        )
    lines.append("")
    return "\n".join(lines)
