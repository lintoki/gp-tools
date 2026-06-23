#!/usr/bin/env python3
from pathlib import Path

from tail_trader.backtest import (
    backtest_output_path,
    run_backtest,
    write_backtest_html,
    write_backtest_payload,
)
from tail_trader.baostock_provider import BaostockBacktestProvider
from tail_trader.cli import DEFAULT_DATA_DIR


START_DATE = "2026-01-01"
END_DATE = "2026-01-07"
SHARES = 100
MAX_UNIVERSE = 80


def _print_summary(summary: dict, html_path: Path, json_path: Path) -> None:
    print("# 尾盘隔夜策略回测")
    print(f"- 区间：{summary['start_date']} 至 {summary['end_date']}")
    print(f"- 交易日：{summary['trading_days']}")
    print(f"- 已完成交易：{summary['closed_trades']}")
    print(f"- 胜率：{summary['win_rate_pct']:.2f}%")
    print(f"- 平均收益：{summary['avg_return_pct']:+.2f}%")
    print(f"- 纸面盈亏：{summary['total_profit_yuan']:+.2f} 元")
    print(f"- 数据不可验证交易日：{summary['unavailable_days']}")
    print(f"HTML报告: {html_path}")
    print(f"JSON数据: {json_path}")


def main() -> None:
    notes = [
        "2026-01-01 至 2026-01-04 为休市日或周末，Baostock 交易日历只回测实际交易日。",
        "历史尾盘形态使用 Baostock 5 分钟 K 线近似验证；如果需要 1 分钟逐笔级严格验证，需要更完整的历史分时源。",
        "历史量比使用当日成交量 / 前 5 个交易日日均成交量近似；不是盘中实时量比字段。",
        "历史总市值使用东方财富当前总市值按历史收盘价缩放估算，用于执行 50 亿到 200 亿过滤。",
        f"为保证本地一键脚本可快速完成，每个交易日最多检查 {MAX_UNIVERSE} 只主板股票；这是快速抽样验证，不等同全市场回测。",
        "程序只做报告和纸面测算，不连接券商账户，不自动下单。",
    ]
    provider = BaostockBacktestProvider(max_universe=MAX_UNIVERSE)
    try:
        report = run_backtest(provider, START_DATE, END_DATE, shares=SHARES, notes=notes)
    finally:
        provider.close()

    json_path = backtest_output_path(DEFAULT_DATA_DIR, START_DATE, END_DATE, "json")
    html_path = backtest_output_path(DEFAULT_DATA_DIR, START_DATE, END_DATE, "html")
    write_backtest_payload(json_path, report)
    write_backtest_html(html_path, report)
    _print_summary(report.summary, html_path, json_path)


if __name__ == "__main__":
    main()
