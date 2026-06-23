from dataclasses import asdict
from typing import Dict, Iterable, List, Optional

from .models import CandidateReport, DailyBar, MarketSnapshot, MinuteBar, StrategyConfig


MAIN_BOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")


def normalize_code(code: str) -> str:
    return str(code).split(".", 1)[0].zfill(6)


def is_main_board(code: str) -> bool:
    return normalize_code(code).startswith(MAIN_BOARD_PREFIXES)


def _is_st_or_delist_name(name: str) -> bool:
    upper_name = str(name).upper()
    return "ST" in upper_name or "退" in str(name)


def _fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def _check_range(
    label: str,
    value: Optional[float],
    minimum: float,
    maximum: float,
    unit: str = "",
) -> tuple[bool, str]:
    if value is None:
        return False, f"{label}缺失"
    if minimum <= value <= maximum:
        return True, f"{label} {value:.2f}{unit} 在 {minimum:.2f}{unit}-{maximum:.2f}{unit}"
    return False, f"{label} {value:.2f}{unit} 不在 {minimum:.2f}{unit}-{maximum:.2f}{unit}"


def _recent_limit_up_count(daily_bars: Iterable[DailyBar], config: StrategyConfig) -> int:
    recent = list(daily_bars)[-config.limit_up_lookback_days :]
    return sum(1 for bar in recent if bar.change_pct >= config.limit_up_pct)


def _above_avg_ratio(minute_bars: List[MinuteBar]) -> float:
    usable = [bar for bar in minute_bars if bar.avg_price is not None]
    if not usable:
        return 0.0
    above = [bar for bar in usable if bar.close >= float(bar.avg_price)]
    return len(above) / len(usable)


def _time_part(value: str) -> str:
    return str(value).split()[-1]


def _is_tail_bar(bar: MinuteBar, config: StrategyConfig) -> bool:
    return _time_part(bar.time) >= config.tail_start


def _intraday_tail_signal(minute_bars: List[MinuteBar], config: StrategyConfig) -> tuple[bool, List[str], List[str]]:
    pass_reasons: List[str] = []
    fail_reasons: List[str] = []
    if len(minute_bars) < 3:
        return False, pass_reasons, ["分时数据不足，无法确认尾盘形态"]

    latest = minute_bars[-1]
    if latest.avg_price is None:
        fail_reasons.append("最新分时均价缺失")
        return False, pass_reasons, fail_reasons

    latest_avg = float(latest.avg_price)
    if latest.close >= latest_avg:
        pass_reasons.append("最新价站在分时均价线上方")
    else:
        fail_reasons.append("最新价跌破分时均价线")

    ratio = _above_avg_ratio(minute_bars)
    if ratio >= config.min_above_avg_ratio:
        pass_reasons.append(f"全天 {ratio:.0%} 分时收盘价在均价线上方")
    else:
        fail_reasons.append(f"全天仅 {ratio:.0%} 分时收盘价在均价线上方")

    tail_indices = [index for index, bar in enumerate(minute_bars) if _is_tail_bar(bar, config)]
    if not tail_indices:
        fail_reasons.append("缺少 14:30 后分时数据")
        return False, pass_reasons, fail_reasons

    first_tail_index = tail_indices[0]
    pre_tail_high = max((bar.high for bar in minute_bars[:first_tail_index]), default=minute_bars[0].high)
    new_high_index: Optional[int] = None
    for index in tail_indices:
        if minute_bars[index].high >= pre_tail_high:
            new_high_index = index
            break
    if new_high_index is None:
        fail_reasons.append("尾盘未创日内新高")
        return False, pass_reasons, fail_reasons

    after_high = minute_bars[new_high_index:]
    min_low_after_high = min(bar.low for bar in after_high)
    touched_avg = min_low_after_high <= latest_avg * (1 + config.pullback_to_avg_tolerance_pct / 100)
    not_broken_avg = min_low_after_high >= latest_avg * (1 - config.vwap_break_tolerance_pct / 100)
    if touched_avg and not_broken_avg:
        pass_reasons.append("尾盘创日内新高后回踩均价线不破")
    elif not touched_avg:
        fail_reasons.append("尾盘未出现贴近均价线的回踩")
    else:
        fail_reasons.append("尾盘回踩跌破分时均价线")

    return not fail_reasons, pass_reasons, fail_reasons


def evaluate_candidate(
    snapshot: MarketSnapshot,
    daily_bars: Iterable[DailyBar],
    minute_bars: Iterable[MinuteBar],
    market_change_pct: float,
    config: StrategyConfig,
) -> CandidateReport:
    code = normalize_code(snapshot.code)
    pass_reasons: List[str] = []
    fail_reasons: List[str] = []
    score = 0.0

    if is_main_board(code):
        pass_reasons.append("主板股票")
        score += 1.0
    else:
        fail_reasons.append("非主板股票")

    if _is_st_or_delist_name(snapshot.name):
        fail_reasons.append("ST 或退市风险股票")

    ok, reason = _check_range("涨幅", snapshot.change_pct, config.min_change_pct, config.max_change_pct, "%")
    (pass_reasons if ok else fail_reasons).append(reason)
    if ok:
        score += float(snapshot.change_pct or 0) - config.min_change_pct

    limit_up_count = _recent_limit_up_count(daily_bars, config)
    if config.min_limit_up_count_20 <= limit_up_count <= config.max_limit_up_count_20:
        pass_reasons.append(f"近 20 日涨停次数 {limit_up_count}")
        score += limit_up_count
    elif limit_up_count < config.min_limit_up_count_20:
        fail_reasons.append("近 20 日没有涨停记录")
    else:
        fail_reasons.append(f"近 20 日涨停次数 {limit_up_count} 过多")

    if snapshot.volume_ratio is not None and snapshot.volume_ratio >= config.min_volume_ratio:
        pass_reasons.append(f"量比 {snapshot.volume_ratio:.2f} >= {config.min_volume_ratio:.2f}")
        score += min(snapshot.volume_ratio, 3.0) / 2
    else:
        fail_reasons.append(f"量比 {snapshot.volume_ratio if snapshot.volume_ratio is not None else '-'} 小于 1.00")

    ok, reason = _check_range("换手率", snapshot.turnover_pct, config.min_turnover_pct, config.max_turnover_pct, "%")
    (pass_reasons if ok else fail_reasons).append(reason)
    if ok:
        score += 1.0

    ok, reason = _check_range(
        "总市值",
        snapshot.total_market_value_yuan,
        config.min_total_market_value_yuan,
        config.max_total_market_value_yuan,
        "",
    )
    if ok:
        pass_reasons.append(
            f"总市值 {snapshot.total_market_value_yuan / 100_000_000:.2f} 亿在 "
            f"{config.min_total_market_value_yuan / 100_000_000:.0f}-{config.max_total_market_value_yuan / 100_000_000:.0f} 亿"
        )
        score += 1.0
    else:
        if snapshot.total_market_value_yuan is None:
            fail_reasons.append("总市值缺失")
        else:
            fail_reasons.append(
                f"总市值 {snapshot.total_market_value_yuan / 100_000_000:.2f} 亿不在 "
                f"{config.min_total_market_value_yuan / 100_000_000:.0f}-{config.max_total_market_value_yuan / 100_000_000:.0f} 亿"
            )

    if snapshot.change_pct is not None and snapshot.change_pct > market_change_pct:
        pass_reasons.append(f"强于大盘：个股 {_fmt_pct(snapshot.change_pct)} > 大盘 {_fmt_pct(market_change_pct)}")
        score += 1.0
    else:
        fail_reasons.append(f"未强于大盘：个股 {_fmt_pct(snapshot.change_pct or 0)} <= 大盘 {_fmt_pct(market_change_pct)}")

    intraday_ok, intraday_pass, intraday_fail = _intraday_tail_signal(list(minute_bars), config)
    pass_reasons.extend(intraday_pass)
    fail_reasons.extend(intraday_fail)
    if intraday_ok:
        score += 2.0

    return CandidateReport(
        code=code,
        name=snapshot.name,
        passed=not fail_reasons,
        score=round(score, 4),
        entry_price=snapshot.latest_price,
        pass_reasons=pass_reasons,
        fail_reasons=fail_reasons,
        snapshot=asdict(snapshot),
    )


def screen_market(
    snapshots: Iterable[MarketSnapshot],
    daily_bars_by_code: Dict[str, List[DailyBar]],
    minute_bars_by_code: Dict[str, List[MinuteBar]],
    market_change_pct: float,
    config: StrategyConfig,
    passed_only: bool = True,
) -> List[CandidateReport]:
    reports = [
        evaluate_candidate(
            snapshot,
            daily_bars_by_code.get(normalize_code(snapshot.code), []),
            minute_bars_by_code.get(normalize_code(snapshot.code), []),
            market_change_pct,
            config,
        )
        for snapshot in snapshots
    ]
    if passed_only:
        reports = [report for report in reports if report.passed]
    return sorted(reports, key=lambda report: report.score, reverse=True)

