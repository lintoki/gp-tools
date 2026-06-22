import copy
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from main import (
    FETCH_INTERVAL_SECONDS,
    STATUS_BELOW_ZONE,
    STATUS_BUY_ZONE,
    SUMMARY_INTERVAL_SECONDS,
    TZ,
    WatchItem,
    Quote,
    _format_amount,
    _format_pct,
    _format_price,
    determine_status,
    ensure_alert_state,
    ensure_position_state,
    fetch_realtime_quotes,
    is_trading_time,
    load_config,
    process_alerts,
    save_json_file,
    should_allow_alert,
)
from fund_risk import (
    AI_CORE_WATCH,
    FinalAlert,
    FundFlowSnapshot,
    MarketRisk,
    SectorRisk,
    SectorRiskSnapshot,
    StockAcceptanceSnapshot,
    build_fund_risk_message,
    decide_final_alert,
    evaluate_market_risk,
    evaluate_sector_risk,
    evaluate_stock_acceptance,
    fetch_market_fund_flow,
    display_label,
)
from web_config import load_config_document, load_settings


MAX_EVENT_LOGS = 200
MAX_SUMMARY_HISTORY = 120


def build_quote_rows(
    now: datetime,
    items: Iterable[WatchItem],
    quotes: Dict[str, Quote],
    positions: Dict[str, Any],
    market_risk: Optional[Any] = None,
    sector_risk: Optional[SectorRiskSnapshot] = None,
    stock_acceptance_by_symbol: Optional[Dict[str, StockAcceptanceSnapshot]] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    timestamp = now.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")
    stock_acceptance_by_symbol = stock_acceptance_by_symbol or {}
    for item in items:
        quote = quotes.get(item.symbol)
        status = determine_status(item, quote.latest_price if quote else None)
        if quote and status in (STATUS_BUY_ZONE, STATUS_BELOW_ZONE) and not should_allow_alert(item, positions):
            status = "BLOCKED_BY_POSITION"
        acceptance = stock_acceptance_by_symbol.get(item.symbol)
        if quote and status != "BLOCKED_BY_POSITION":
            final_alert = decide_final_alert(
                item=item,
                price_status=status,
                latest_price=quote.latest_price,
                market_risk=market_risk.level if market_risk else MarketRisk.UNKNOWN,
                sector_risk=sector_risk.level if sector_risk else SectorRisk.UNKNOWN,
                stock_acceptance=acceptance.level if acceptance else evaluate_stock_acceptance(item, quote).level,
            )
        else:
            final_alert = FinalAlert.NONE

        rows.append(
            {
                "time": timestamp,
                "code": item.code,
                "symbol": item.symbol,
                "name": quote.name if quote else item.name,
                "latest_price": quote.latest_price if quote else None,
                "latest_price_text": _format_price(quote.latest_price if quote else None),
                "change_pct": quote.change_pct if quote else None,
                "change_pct_text": _format_pct(quote.change_pct if quote else None),
                "amount": quote.amount if quote else None,
                "amount_text": _format_amount(quote.amount if quote else None),
                "buy_low": item.buy_low,
                "buy_high": item.buy_high,
                "buy_range_text": f"{item.buy_low:.2f}-{item.buy_high:.2f}",
                "shares": item.shares,
                "type": item.type,
                "priority": item.priority,
                "enabled": item.enabled,
                "note": item.note,
                "status": status if quote else "MISSING_QUOTE",
                "price_status": status if quote else "MISSING_QUOTE",
                "price_status_text": display_label(status if quote else "MISSING_QUOTE"),
                "market_risk_level": market_risk.level.value if market_risk else MarketRisk.UNKNOWN.value,
                "market_risk_level_text": display_label(market_risk.level.value if market_risk else MarketRisk.UNKNOWN.value),
                "market_main_net_inflow_yi": market_risk.main_net_inflow_yi if market_risk else None,
                "market_risk_reason": market_risk.reason if market_risk else "资金数据未提供",
                "sector_risk_level": sector_risk.level.value if sector_risk else SectorRisk.UNKNOWN.value,
                "sector_risk_level_text": display_label(sector_risk.level.value if sector_risk else SectorRisk.UNKNOWN.value),
                "sector_avg_change_pct": sector_risk.avg_change_pct if sector_risk else None,
                "sector_up_count": sector_risk.up_count if sector_risk else 0,
                "sector_down_count": sector_risk.down_count if sector_risk else 0,
                "sector_risk_reason": sector_risk.reason if sector_risk else "板块数据未提供",
                "stock_acceptance": acceptance.level.value if acceptance else "ACCEPTANCE_UNKNOWN",
                "stock_acceptance_text": display_label(acceptance.level.value if acceptance else "ACCEPTANCE_UNKNOWN"),
                "stock_acceptance_reason": acceptance.reason if acceptance else "个股承接数据未提供",
                "final_alert": final_alert.value,
                "final_alert_text": display_label(final_alert.value),
                "position": copy.deepcopy(positions.get(item.code, {})),
                "depends_on_not_bought": item.depends_on_not_bought,
            }
        )
    return rows


def _ai_core_codes_from_config(config_path: Path) -> List[str]:
    document = load_config_document(config_path)
    raw_codes = document.get("ai_core_watch") or AI_CORE_WATCH
    return [str(code) for code in raw_codes]


def _quote_fetch_items(items: List[WatchItem], ai_core_codes: List[str]) -> List[WatchItem]:
    result_by_code = {item.code: item for item in items}
    for index, code in enumerate(ai_core_codes, start=10000):
        normalized = code.upper()
        if normalized in result_by_code:
            continue
        market = normalized.split(".", 1)[1] if "." in normalized else ""
        result_by_code[normalized] = WatchItem(
            name=normalized,
            code=normalized,
            market=market,
            buy_low=0.0,
            buy_high=0.0,
            shares=0,
            type="AI_CORE_WATCH",
            priority=index,
            enabled=True,
        )
    return list(result_by_code.values())


class MonitorRuntime:
    def __init__(
        self,
        base_dir: Path,
        config_path: Path,
        alert_state_path: Path,
        position_state_path: Path,
        settings_path: Path,
        snapshots_path: Path,
        fetch_interval: int = FETCH_INTERVAL_SECONDS,
        summary_interval: int = SUMMARY_INTERVAL_SECONDS,
    ) -> None:
        self.base_dir = base_dir
        self.config_path = config_path
        self.alert_state_path = alert_state_path
        self.position_state_path = position_state_path
        self.settings_path = settings_path
        self.snapshots_path = snapshots_path
        self.fetch_interval = fetch_interval
        self.summary_interval = summary_interval
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_summary_monotonic: Optional[float] = None
        self._state: Dict[str, Any] = {
            "running": False,
            "trading_time": False,
            "last_fetch_at": "",
            "last_summary_at": "",
            "last_error": "",
            "latest_rows": [],
            "summary_history": [],
            "event_logs": [],
            "market_risk": {},
            "sector_risk": {},
        }

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._state["running"] = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, name="a-stock-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._state["running"] = False

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def add_event(self, level: str, message: str) -> None:
        event = {
            "time": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message,
        }
        with self._lock:
            self._state["event_logs"].insert(0, event)
            self._state["event_logs"] = self._state["event_logs"][:MAX_EVENT_LOGS]

    def refresh_once(self, force: bool = True) -> Dict[str, Any]:
        try:
            self._run_once(force=force)
        except Exception as exc:
            self.add_event("ERROR", f"手动刷新失败: {exc}")
            with self._lock:
                self._state["last_error"] = str(exc)
        return self.snapshot()

    def _loop(self) -> None:
        self.add_event("INFO", "监控后台已启动")
        while not self._stop_event.is_set():
            started_at = time.monotonic()
            try:
                self._run_once(force=False)
            except Exception as exc:
                logging.exception("本轮监控失败")
                self.add_event("ERROR", f"本轮监控失败: {exc}")
                with self._lock:
                    self._state["last_error"] = str(exc)

            elapsed = time.monotonic() - started_at
            self._stop_event.wait(max(1, self.fetch_interval - elapsed))

        self.add_event("INFO", "监控后台已停止")

    def _run_once(self, force: bool = False) -> None:
        now = datetime.now(TZ)
        trading = is_trading_time(now)
        with self._lock:
            self._state["trading_time"] = trading

        if not trading and not force:
            return

        items = load_config(self.config_path)
        positions = ensure_position_state(self.position_state_path)
        alert_state = ensure_alert_state(self.alert_state_path)
        settings = load_settings(self.settings_path)
        webhook_url = settings.get("wechat_webhook_url") or None

        fund_flow = fetch_market_fund_flow()
        market_risk = evaluate_market_risk(fund_flow)
        if market_risk.level == MarketRisk.UNKNOWN:
            self.add_event("WARN", f"资金数据获取失败，买点降级观察: {market_risk.reason}")

        ai_core_codes = _ai_core_codes_from_config(self.config_path)
        fetch_items = _quote_fetch_items(items, ai_core_codes)
        try:
            quotes = fetch_realtime_quotes(fetch_items)
        except Exception as exc:
            self.add_event("ERROR", f"行情源获取失败，保留上一轮页面数据: {exc}")
            with self._lock:
                self._state["last_error"] = str(exc)
                self._state["market_risk"] = _market_risk_to_dict(market_risk)
            return

        sector_risk = evaluate_sector_risk(quotes, ai_core_codes)
        acceptance_by_symbol = {
            item.symbol: evaluate_stock_acceptance(item, quotes.get(item.symbol))
            for item in items
        }
        process_alerts(
            now,
            items,
            quotes,
            positions,
            alert_state,
            self.alert_state_path,
            webhook_url,
            market_risk_snapshot=market_risk,
            sector_risk_snapshot=sector_risk,
            stock_acceptance_by_symbol=acceptance_by_symbol,
        )
        rows = build_quote_rows(now, items, quotes, positions, market_risk, sector_risk, acceptance_by_symbol)
        summary_due = self._last_summary_monotonic is None or time.monotonic() - self._last_summary_monotonic >= self.summary_interval

        with self._lock:
            self._state["last_fetch_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
            self._state["last_error"] = ""
            self._state["latest_rows"] = rows
            self._state["market_risk"] = _market_risk_to_dict(market_risk)
            self._state["sector_risk"] = _sector_risk_to_dict(sector_risk)

        if summary_due or force:
            self._append_summary(now, rows, market_risk, sector_risk, forced=force)
            self._last_summary_monotonic = time.monotonic()

    def _append_summary(
        self,
        now: datetime,
        rows: List[Dict[str, Any]],
        market_risk: Any,
        sector_risk: SectorRiskSnapshot,
        forced: bool = False,
    ) -> None:
        snapshot = {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "forced": forced,
            "market_risk": _market_risk_to_dict(market_risk),
            "sector_risk": _sector_risk_to_dict(sector_risk),
            "rows": copy.deepcopy(rows),
        }
        self.snapshots_path.parent.mkdir(parents=True, exist_ok=True)
        with self.snapshots_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

        with self._lock:
            self._state["last_summary_at"] = snapshot["time"]
            self._state["summary_history"].insert(0, snapshot)
            self._state["summary_history"] = self._state["summary_history"][:MAX_SUMMARY_HISTORY]
        self.add_event("INFO", f"已生成行情快照: {snapshot['time']}")


def write_runtime_state(path: Path, runtime: MonitorRuntime) -> None:
    save_json_file(path, runtime.snapshot())


def _market_risk_to_dict(market_risk: Any) -> Dict[str, Any]:
    return {
        "level": market_risk.level.value,
        "level_text": display_label(market_risk.level.value),
        "main_net_inflow_yi": market_risk.main_net_inflow_yi,
        "net_inflow_15m_delta_yi": market_risk.net_inflow_15m_delta_yi,
        "source": market_risk.source,
        "reason": market_risk.reason,
    }


def _sector_risk_to_dict(sector_risk: SectorRiskSnapshot) -> Dict[str, Any]:
    return {
        "level": sector_risk.level.value,
        "level_text": display_label(sector_risk.level.value),
        "up_count": sector_risk.up_count,
        "down_count": sector_risk.down_count,
        "flat_count": sector_risk.flat_count,
        "sample_count": sector_risk.sample_count,
        "avg_change_pct": sector_risk.avg_change_pct,
        "below_vwap_count": sector_risk.below_vwap_count,
        "back_to_vwap_count": sector_risk.back_to_vwap_count,
        "reason": sector_risk.reason,
    }
