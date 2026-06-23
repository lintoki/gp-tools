import html
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol

from .models import CandidateReport, DailyBar, MarketSnapshot, MinuteBar, PaperTrade, StrategyConfig
from .paper import decide_morning_exit
from .retention import prepare_output_file
from .strategy import evaluate_candidate, is_main_board, normalize_code


@dataclass(frozen=True)
class BacktestTradeResult:
    code: str
    name: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_time: str
    exit_price: float
    exit_reason: str
    return_pct: float
    profit_yuan: float
    pass_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BacktestDayResult:
    date: str
    status: str
    candidates_checked: int
    passed_count: int
    unavailable_count: int
    trades: List[BacktestTradeResult] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BacktestReport:
    start_date: str
    end_date: str
    generated_at: str
    summary: Dict[str, Any]
    days: List[BacktestDayResult]
    notes: List[str] = field(default_factory=list)


class BacktestDataProvider(Protocol):
    def trading_dates_between(self, start_date: str, end_date: str) -> List[str]:
        ...

    def snapshots_for_date(self, trading_date: str) -> List[MarketSnapshot]:
        ...

    def daily_bars(self, code: str, start_date: str, end_date: str) -> List[DailyBar]:
        ...

    def minute_bars(self, code: str, trading_date: str) -> List[MinuteBar]:
        ...

    def next_trading_date(self, trading_date: str) -> Optional[str]:
        ...


def _compact_date(value: str) -> str:
    return value.replace("-", "")[:8]


def _lookback_start(trading_date: str, calendar_days: int = 90) -> str:
    return (datetime.strptime(trading_date, "%Y-%m-%d").date() - timedelta(days=calendar_days)).strftime("%Y%m%d")


def _snapshot_prefilter(snapshot: MarketSnapshot, config: StrategyConfig) -> bool:
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


def _trade_result_from_candidate(
    report: CandidateReport,
    entry_date: str,
    next_day_bars: Iterable[MinuteBar],
    shares: int,
    target_profit_pct: float,
    stop_loss_pct: float,
) -> BacktestTradeResult:
    if report.entry_price is None:
        raise ValueError(f"{report.code} 缺少入场价")
    trade = PaperTrade(
        trade_id=f"{entry_date.replace('-', '')}-{report.code}",
        code=report.code,
        name=report.name,
        entry_date=entry_date,
        entry_time="14:55:00",
        entry_price=report.entry_price,
        shares=shares,
        status="OPEN",
        strategy="tail_overnight_backtest",
        notes=list(report.pass_reasons),
    )
    review = decide_morning_exit(
        trade,
        next_day_bars,
        target_profit_pct=target_profit_pct,
        stop_loss_pct=stop_loss_pct,
    )
    return BacktestTradeResult(
        code=report.code,
        name=report.name,
        entry_date=entry_date,
        entry_price=report.entry_price,
        exit_date=review.exit_date,
        exit_time=review.exit_time,
        exit_price=review.exit_price,
        exit_reason=review.exit_reason,
        return_pct=review.return_pct,
        profit_yuan=review.profit_yuan,
        pass_reasons=list(report.pass_reasons),
    )


def _summary(start_date: str, end_date: str, days: List[BacktestDayResult]) -> Dict[str, Any]:
    trades = [trade for day in days for trade in day.trades]
    wins = sum(1 for trade in trades if trade.return_pct > 0)
    losses = sum(1 for trade in trades if trade.return_pct < 0)
    total_return = sum(trade.return_pct for trade in trades)
    total_profit = sum(trade.profit_yuan for trade in trades)
    closed = len(trades)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "trading_days": len(days),
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / closed * 100, 2) if closed else 0.0,
        "avg_return_pct": round(total_return / closed, 4) if closed else 0.0,
        "total_profit_yuan": round(total_profit, 2),
        "candidate_days": sum(1 for day in days if day.candidates_checked > 0),
        "passed_signals": sum(day.passed_count for day in days),
        "unavailable_days": sum(1 for day in days if day.status == "DATA_UNAVAILABLE"),
        "unavailable_items": sum(day.unavailable_count for day in days),
    }


def run_backtest(
    provider: BacktestDataProvider,
    start_date: str,
    end_date: str,
    *,
    market_change_pct: float = 0.0,
    shares: int = 100,
    max_candidates: int = 80,
    target_profit_pct: float = 2.0,
    stop_loss_pct: float = 2.0,
    config: Optional[StrategyConfig] = None,
    notes: Optional[List[str]] = None,
) -> BacktestReport:
    strategy_config = config or StrategyConfig()
    days: List[BacktestDayResult] = []
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        trading_dates = provider.trading_dates_between(start_date, end_date)
    except Exception as exc:
        trading_dates = []
        days.append(
            BacktestDayResult(
                date=f"{start_date}~{end_date}",
                status="DATA_UNAVAILABLE",
                candidates_checked=0,
                passed_count=0,
                unavailable_count=1,
                messages=[f"交易日历获取失败: {exc}"],
            )
        )

    for trading_date in trading_dates:
        messages: List[str] = []
        try:
            snapshots = provider.snapshots_for_date(trading_date)
        except Exception as exc:
            days.append(
                BacktestDayResult(
                    date=trading_date,
                    status="DATA_UNAVAILABLE",
                    candidates_checked=0,
                    passed_count=0,
                    unavailable_count=1,
                    messages=[f"历史候选快照获取失败: {exc}"],
                )
            )
            continue

        cheap_candidates = [snapshot for snapshot in snapshots if _snapshot_prefilter(snapshot, strategy_config)]
        cheap_candidates = cheap_candidates[:max_candidates]
        trades: List[BacktestTradeResult] = []
        unavailable_count = 0
        passed_count = 0
        for snapshot in cheap_candidates:
            code = normalize_code(snapshot.code)
            try:
                daily_bars = provider.daily_bars(code, _lookback_start(trading_date), _compact_date(trading_date))
                minute_bars = provider.minute_bars(code, trading_date)
                report = evaluate_candidate(snapshot, daily_bars, minute_bars, market_change_pct, strategy_config)
            except Exception as exc:
                unavailable_count += 1
                messages.append(f"{code} 明细数据不可用: {exc}")
                continue
            if not report.passed:
                continue
            passed_count += 1
            try:
                next_date = provider.next_trading_date(trading_date)
                if not next_date:
                    raise ValueError("缺少下一交易日")
                next_day_bars = provider.minute_bars(code, next_date)
                trades.append(
                    _trade_result_from_candidate(
                        report,
                        trading_date,
                        next_day_bars,
                        shares,
                        target_profit_pct,
                        stop_loss_pct,
                    )
                )
            except Exception as exc:
                unavailable_count += 1
                messages.append(f"{code} 次日退出数据不可用: {exc}")

        if trades:
            status = "TRADED"
        elif unavailable_count and (cheap_candidates or messages):
            status = "DATA_UNAVAILABLE"
        elif cheap_candidates:
            status = "NO_SIGNAL"
        else:
            status = "NO_CANDIDATE"
        days.append(
            BacktestDayResult(
                date=trading_date,
                status=status,
                candidates_checked=len(cheap_candidates),
                passed_count=passed_count,
                unavailable_count=unavailable_count,
                trades=trades,
                messages=messages,
            )
        )

    return BacktestReport(
        start_date=start_date,
        end_date=end_date,
        generated_at=generated_at,
        summary=_summary(start_date, end_date, days),
        days=days,
        notes=list(notes or []),
    )


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _status_text(status: str) -> str:
    return {
        "TRADED": "有交易",
        "NO_SIGNAL": "无完整信号",
        "NO_CANDIDATE": "无候选",
        "DATA_UNAVAILABLE": "数据不可验证",
    }.get(status, status)


def _trade_rows(day: BacktestDayResult) -> str:
    if not day.trades:
        return '<tr><td colspan="8" class="muted">无已完成交易</td></tr>'
    rows = []
    for trade in day.trades:
        rows.append(
            f"""
            <tr>
              <td><strong>{_esc(trade.code)}</strong><span>{_esc(trade.name)}</span></td>
              <td>{_esc(trade.entry_date)}</td>
              <td class="num">{trade.entry_price:.3f}</td>
              <td>{_esc(trade.exit_date)} {_esc(trade.exit_time)}</td>
              <td class="num">{trade.exit_price:.3f}</td>
              <td>{_esc(trade.exit_reason)}</td>
              <td class="num {'pos' if trade.return_pct > 0 else 'neg' if trade.return_pct < 0 else ''}">{trade.return_pct:+.2f}%</td>
              <td class="num">{trade.profit_yuan:+.2f}</td>
            </tr>
            """
        )
    return "".join(rows)


def build_backtest_html(report: BacktestReport) -> str:
    summary = report.summary
    note_items = "".join(f"<li>{_esc(note)}</li>" for note in report.notes) or '<li class="muted">无</li>'
    day_cards = []
    for day in report.days:
        messages = "".join(f"<li>{_esc(message)}</li>" for message in day.messages) or '<li class="muted">无</li>'
        day_cards.append(
            f"""
            <section class="panel day">
              <div class="panel-head">
                <div>
                  <h2>{_esc(day.date)} · {_esc(_status_text(day.status))}</h2>
                  <p>候选 {day.candidates_checked}，完整信号 {day.passed_count}，不可验证 {day.unavailable_count}</p>
                </div>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>股票</th><th>买入日</th><th class="num">买入价</th><th>卖出时间</th>
                      <th class="num">卖出价</th><th>退出</th><th class="num">收益率</th><th class="num">盈亏</th>
                    </tr>
                  </thead>
                  <tbody>{_trade_rows(day)}</tbody>
                </table>
              </div>
              <details>
                <summary>数据与过滤说明</summary>
                <ul>{messages}</ul>
              </details>
            </section>
            """
        )
    payload_json = json.dumps(asdict(report), ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>尾盘隔夜策略回测 {report.start_date} 至 {report.end_date}</title>
  <style>
    :root {{
      --bg: #f5f6f8;
      --panel: #fff;
      --text: #182230;
      --muted: #667085;
      --line: #d6dce5;
      --green: #0f7a45;
      --red: #b42318;
      --blue: #175cd3;
      --amber: #9a6700;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 44px; }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    .sub {{ color: var(--muted); margin-top: 6px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }}
    .metric, .panel, .notes {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
    .metric {{ padding: 14px 16px; }}
    .metric .label {{ color: var(--muted); font-size: 13px; }}
    .metric .value {{ font-size: 24px; font-weight: 750; margin-top: 4px; }}
    .notes {{ padding: 14px 16px; border-left: 5px solid var(--amber); }}
    .notes h2 {{ margin: 0 0 8px; font-size: 18px; }}
    .panel {{ margin-top: 16px; overflow: hidden; }}
    .panel-head {{ padding: 14px 16px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 12px; }}
    .panel-head h2 {{ margin: 0; font-size: 18px; }}
    .panel-head p {{ margin: 4px 0 0; color: var(--muted); }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 11px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #eef1f5; color: #384250; font-size: 13px; }}
    td:first-child span {{ display: block; color: var(--muted); margin-top: 2px; }}
    .num {{ text-align: right; white-space: nowrap; }}
    .pos {{ color: var(--green); font-weight: 700; }}
    .neg {{ color: var(--red); font-weight: 700; }}
    .muted {{ color: var(--muted); }}
    details {{ padding: 12px 16px 14px; }}
    summary {{ cursor: pointer; color: var(--blue); font-weight: 650; }}
    ul {{ margin: 8px 0 0; padding-left: 20px; }}
    li {{ overflow-wrap: anywhere; }}
    .raw {{ display: none; }}
    @media (max-width: 820px) {{
      main {{ padding: 18px 12px 32px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table {{ min-width: 820px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>尾盘隔夜策略回测</h1>
    <div class="sub">区间：{_esc(report.start_date)} 至 {_esc(report.end_date)} · 生成：{_esc(report.generated_at)}</div>
    <section class="metrics">
      <div class="metric"><div class="label">交易日</div><div class="value">{summary['trading_days']}</div></div>
      <div class="metric"><div class="label">已完成交易</div><div class="value">{summary['closed_trades']}</div></div>
      <div class="metric"><div class="label">胜率</div><div class="value">{summary['win_rate_pct']:.2f}%</div></div>
      <div class="metric"><div class="label">平均收益</div><div class="value">{summary['avg_return_pct']:+.2f}%</div></div>
    </section>
    <section class="notes">
      <h2>结论口径</h2>
      <ul>{note_items}</ul>
    </section>
    {''.join(day_cards) or '<section class="panel"><div class="panel-head"><h2>没有可回测交易日</h2></div></section>'}
    <script type="application/json" class="raw">{_esc(payload_json)}</script>
  </main>
</body>
</html>
"""


def backtest_output_path(data_dir: Path, start_date: str, end_date: str, suffix: str) -> Path:
    stamp = f"{start_date.replace('-', '')}-{end_date.replace('-', '')}"
    return data_dir / "backtests" / f"{stamp}.{suffix}"


def write_backtest_payload(path: Path, report: BacktestReport) -> None:
    prepare_output_file(path, "*.json")
    path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_backtest_html(path: Path, report: BacktestReport) -> None:
    prepare_output_file(path, "*.html")
    path.write_text(build_backtest_html(report), encoding="utf-8")
