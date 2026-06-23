import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from .akshare_source import (
    compact_date,
    dashed_date,
    fetch_daily_bars,
    fetch_minute_bars,
    fetch_spot_snapshots,
)
from .html_report import write_scan_html
from .models import CandidateReport, DailyBar, MarketSnapshot, MinuteBar, PaperTrade, StrategyConfig
from .paper import append_trade, build_review_markdown, decide_morning_exit, load_trades
from .retention import prepare_output_file
from .strategy import evaluate_candidate, is_main_board, normalize_code
from .workflow import (
    build_scan_markdown,
    paper_trade_from_report,
    scan_html_output_path,
    review_output_path,
    scan_output_path,
    write_scan_payload,
)


TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def default_scan_args() -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=str(DEFAULT_DATA_DIR),
        market_change_pct=0.0,
        top=20,
        max_prefilter=80,
        history_days=60,
        ignore_time=True,
        record=False,
        record_top=1,
        shares=100,
    )


def _prefilter(snapshot: MarketSnapshot, config: StrategyConfig) -> bool:
    code = normalize_code(snapshot.code)
    if not is_main_board(code):
        return False
    if "ST" in snapshot.name.upper() or "退" in snapshot.name:
        return False
    if snapshot.change_pct is None or not (config.min_change_pct <= snapshot.change_pct <= config.max_change_pct):
        return False
    if snapshot.volume_ratio is None or snapshot.volume_ratio < config.min_volume_ratio:
        return False
    if snapshot.turnover_pct is None or not (config.min_turnover_pct <= snapshot.turnover_pct <= config.max_turnover_pct):
        return False
    if snapshot.total_market_value_yuan is None:
        return False
    return config.min_total_market_value_yuan <= snapshot.total_market_value_yuan <= config.max_total_market_value_yuan


def _scan_live(args: argparse.Namespace) -> List[CandidateReport]:
    now = datetime.now(TZ)
    config = StrategyConfig()
    snapshots = fetch_spot_snapshots()
    cheap_candidates = [snapshot for snapshot in snapshots if _prefilter(snapshot, config)]
    cheap_candidates = cheap_candidates[: args.max_prefilter]

    end = now.date()
    start = end - timedelta(days=args.history_days)
    start_date = compact_date(start)
    end_date = compact_date(end)
    trading_date = dashed_date(end)

    reports: List[CandidateReport] = []
    for snapshot in cheap_candidates:
        code = normalize_code(snapshot.code)
        try:
            daily_bars = fetch_daily_bars(code, start_date=start_date, end_date=end_date)
            minute_bars = fetch_minute_bars(code, trading_date=trading_date)
        except Exception as exc:
            reports.append(
                CandidateReport(
                    code=code,
                    name=snapshot.name,
                    passed=False,
                    score=0.0,
                    entry_price=snapshot.latest_price,
                    pass_reasons=[],
                    fail_reasons=[f"行情明细获取失败: {exc}"],
                    snapshot={},
                )
            )
            continue
        reports.append(evaluate_candidate(snapshot, daily_bars, minute_bars, args.market_change_pct, config))

    return sorted(reports, key=lambda report: report.score, reverse=True)


def _write_scan_and_optionally_record(args: argparse.Namespace, reports: List[CandidateReport]) -> None:
    scan_time = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    data_dir = Path(args.data_dir)
    output = scan_output_path(data_dir, scan_time)
    html_output = scan_html_output_path(data_dir, scan_time)
    write_scan_payload(output, scan_time, reports)
    write_scan_html(html_output, scan_time, reports)

    markdown = build_scan_markdown(scan_time, reports[: args.top])
    print(markdown)
    print(f"扫描快照: {output}")
    print(f"HTML报告: {html_output}")

    if not args.record:
        return
    trade_path = data_dir / "trades.jsonl"
    recorded = 0
    for report in [report for report in reports if report.passed][: args.record_top]:
        trade = paper_trade_from_report(report, scan_time, args.shares)
        append_trade(trade_path, trade)
        recorded += 1
    print(f"已记录纸面交易 {recorded} 笔: {trade_path}")


def command_scan(args: argparse.Namespace) -> None:
    try:
        reports = _scan_live(args)
    except Exception as exc:
        reports = [
            CandidateReport(
                code="DATA_SOURCE",
                name="行情源不可用",
                passed=False,
                score=0.0,
                entry_price=None,
                pass_reasons=[],
                fail_reasons=[f"实时行情获取失败: {exc}"],
                snapshot={},
            )
        ]
    _write_scan_and_optionally_record(args, reports)


def command_default_report() -> None:
    command_scan(default_scan_args())


def _open_trades_for_review(trades: List[PaperTrade], review_date: str) -> List[PaperTrade]:
    return [
        trade
        for trade in trades
        if trade.status == "OPEN" and trade.strategy == "tail_overnight" and trade.entry_date < review_date
    ]


def command_review(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    review_date = args.date or datetime.now(TZ).strftime("%Y-%m-%d")
    trade_path = data_dir / "trades.jsonl"
    trades = _open_trades_for_review(load_trades(trade_path), review_date)
    results = []
    for trade in trades:
        minute_bars = fetch_minute_bars(trade.code, review_date)
        results.append(
            decide_morning_exit(
                trade,
                minute_bars,
                target_profit_pct=args.target_profit_pct,
                stop_loss_pct=args.stop_loss_pct,
            )
        )

    markdown = build_review_markdown(review_date, results)
    output = review_output_path(data_dir, review_date)
    prepare_output_file(output, "*.md")
    output.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"复盘报告: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="尾盘隔夜套利筛选、纸面交易和复盘工具；不连接券商账户。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="按当前时间扫描尾盘隔夜候选")
    scan.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="扫描快照、纸面交易和复盘输出目录")
    scan.add_argument("--market-change-pct", type=float, default=0.0, help="大盘涨跌幅，用于判断个股是否强于大盘")
    scan.add_argument("--top", type=int, default=20, help="打印前 N 个结果")
    scan.add_argument("--max-prefilter", type=int, default=80, help="最多拉取分时明细的预筛股票数")
    scan.add_argument("--history-days", type=int, default=60, help="拉取历史日线的自然日长度")
    scan.add_argument("--ignore-time", action="store_true", help=argparse.SUPPRESS)
    scan.add_argument("--record", action="store_true", help="把入选候选记录为纸面交易")
    scan.add_argument("--record-top", type=int, default=1, help="记录前 N 个入选候选")
    scan.add_argument("--shares", type=int, default=100, help="纸面交易股数")
    scan.set_defaults(func=command_scan)

    review = subparsers.add_parser("review", help="复盘上一交易日纸面交易")
    review.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="扫描快照、纸面交易和复盘输出目录")
    review.add_argument("--date", default="", help="复盘日期，默认今天，格式 YYYY-MM-DD")
    review.add_argument("--target-profit-pct", type=float, default=2.0, help="次日早盘止盈线")
    review.add_argument("--stop-loss-pct", type=float, default=2.0, help="次日早盘止损线")
    review.set_defaults(func=command_review)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
