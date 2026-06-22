#!/usr/bin/env python3
import argparse
import contextlib
import copy
import io
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
TZ = ZoneInfo("Asia/Shanghai")

FETCH_INTERVAL_SECONDS = 60
SUMMARY_INTERVAL_SECONDS = 300

ALERT_TYPE_BUY_ZONE = "BUY_ZONE"
ALERT_TYPE_BELOW_ZONE = "BELOW_ZONE"

STATUS_BUY_ZONE = "BUY_ZONE"
STATUS_WAIT_PULLBACK = "WAIT_PULLBACK"
STATUS_BELOW_ZONE = "BELOW_ZONE"
STATUS_NO_PRICE = "NO_PRICE"

STATUS_DISPLAY_LABELS = {
    "BUY_ZONE": "进入区间",
    "WAIT_PULLBACK": "等待回落",
    "BELOW_ZONE": "跌破区间",
    "NO_PRICE": "无价格",
    "MISSING_QUOTE": "无行情",
    "BLOCKED_BY_POSITION": "持仓阻断",
    "NONE": "无提醒",
    "BUY_CONFIRMED": "买点确认",
    "WATCH_ONLY": "观察提醒",
    "RISK_BLOCKED": "风险拦截",
    "BELOW_ZONE_RISK": "跌破风险",
}

REQUIRED_AKSHARE_COLUMNS = ("代码", "名称", "最新价", "涨跌幅", "成交额")
EASTMONEY_ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"

DEFAULT_POSITION_STATE = {
    "002463.SZ": {
        "name": "沪电股份",
        "bought": False,
    },
    "601138.SH": {
        "name": "工业富联",
        "bought": True,
        "current_holding": 100,
        "target_add": 100,
    },
    "603228.SH": {
        "name": "景旺电子",
        "bought": False,
    },
    "002130.SZ": {
        "name": "沃尔核材",
        "bought": False,
    },
    "600900.SH": {
        "name": "长江电力",
        "bought": False,
    },
}


@dataclass(frozen=True)
class WatchItem:
    name: str
    code: str
    market: str
    buy_low: float
    buy_high: float
    shares: int
    type: str
    priority: int
    enabled: bool
    note: str = ""
    depends_on_not_bought: Optional[str] = None

    @property
    def symbol(self) -> str:
        return self.code.split(".", 1)[0].zfill(6)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WatchItem":
        return cls(
            name=str(data["name"]),
            code=str(data["code"]),
            market=str(data.get("market", "")),
            buy_low=float(data["buy_low"]),
            buy_high=float(data["buy_high"]),
            shares=int(data["shares"]),
            type=str(data.get("type", "")),
            priority=int(data.get("priority", 999)),
            enabled=bool(data.get("enabled", True)),
            note=str(data.get("note", "")),
            depends_on_not_bought=data.get("depends_on_not_bought"),
        )


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    latest_price: Optional[float]
    change_pct: Optional[float]
    amount: Optional[float]


def load_dotenv_if_available(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(path)


def load_config(path: Path) -> List[WatchItem]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少依赖 PyYAML，请先执行: pip install -r requirements.txt") from exc

    if not path.exists():
        raise RuntimeError(f"配置文件不存在: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    raw_watchlist = data.get("watchlist")
    if not isinstance(raw_watchlist, list):
        raise RuntimeError("config.yaml 必须包含 watchlist 列表")

    items = [WatchItem.from_dict(item) for item in raw_watchlist]
    return sorted((item for item in items if item.enabled), key=lambda item: item.priority)


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON 文件格式错误: {path}: {exc}") from exc


def save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)


def ensure_position_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        state = copy.deepcopy(DEFAULT_POSITION_STATE)
        save_json_file(path, state)
        return state

    return load_json_file(path, DEFAULT_POSITION_STATE)


def ensure_alert_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        save_json_file(path, {})
        return {}

    return load_json_file(path, {})


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("%", "")
        if value in ("", "-", "--", "None", "nan", "NaN"):
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _format_price(value: Any) -> str:
    number = _to_float(value)
    return "-" if number is None else f"{number:.2f}"


def _format_pct(value: Any) -> str:
    number = _to_float(value)
    return "-" if number is None else f"{number:+.2f}%"


def _format_amount(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿"
    return f"{number / 10000:.2f}万"


def _normalize_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=TZ)
    return now.astimezone(TZ)


def is_trading_time(now: datetime) -> bool:
    now = _normalize_now(now)
    if now.weekday() >= 5:
        return False

    current = now.time()
    morning = dtime(9, 30) <= current <= dtime(11, 30)
    afternoon = dtime(13, 0) <= current <= dtime(15, 0)
    return morning or afternoon


def determine_status(item: WatchItem, latest_price: Optional[float]) -> str:
    if latest_price is None:
        return STATUS_NO_PRICE
    if item.buy_low <= latest_price <= item.buy_high:
        return STATUS_BUY_ZONE
    if latest_price > item.buy_high:
        return STATUS_WAIT_PULLBACK
    return STATUS_BELOW_ZONE


def display_status(status: Any) -> str:
    if status is None:
        return "-"
    text = str(status)
    return STATUS_DISPLAY_LABELS.get(text, text)


def should_allow_alert(item: WatchItem, positions: Dict[str, Any]) -> bool:
    if not item.depends_on_not_bought:
        return True

    dependency = positions.get(item.depends_on_not_bought, {})
    return not bool(dependency.get("bought", False))


def should_alert(state: Dict[str, Any], code: str, alert_type: str, now: datetime) -> bool:
    today = _normalize_now(now).strftime("%Y-%m-%d")
    return alert_type not in state.get(today, {}).get(code, {})


def record_alert(
    path: Path,
    state: Dict[str, Any],
    code: str,
    alert_type: str,
    now: datetime,
    latest_price: Optional[float] = None,
) -> None:
    now = _normalize_now(now)
    today = now.strftime("%Y-%m-%d")
    state.setdefault(today, {}).setdefault(code, {})[alert_type] = {
        "sent_at": now.isoformat(),
        "latest_price": latest_price,
    }
    save_json_file(path, state)


def build_wechat_markdown(item: WatchItem, latest_price: float, status: str) -> str:
    amount = latest_price * item.shares

    if status == STATUS_BUY_ZONE:
        title = "【A股买点提醒】"
        status_text = "进入买入区间"
        reminders = [
            "1. 这只是价格提醒，不是自动买入指令。",
            "2. 下单前再看上证指数、创业板指、AI算力板块、成交量和分时承接。",
            "3. 如果板块集体放量杀跌，不要机械买入。",
        ]
    elif status == STATUS_BELOW_ZONE:
        title = "【A股风险提醒】"
        status_text = "跌破计划区间"
        reminders = [
            "1. 跌破计划区间，可能是下跌中继，不能机械买入，需要人工复盘，避免接飞刀。",
            "2. 先确认大盘、板块、成交量和个股分时承接，再决定是否调整计划。",
            "3. 这只是价格提醒，不是自动买入指令。",
        ]
    else:
        title = "【A股行情提醒】"
        status_text = display_status(status)
        reminders = ["1. 这只是价格提醒，不是自动买入指令。"]

    note_line = f"\n备注：{item.note}" if item.note else ""

    return "\n".join(
        [
            title,
            "",
            f"股票：{item.name} {item.code}",
            f"现价：{latest_price:.2f}",
            f"买入区间：{item.buy_low:.2f} - {item.buy_high:.2f}",
            f"计划股数：{item.shares}股",
            f"预计金额：{amount:.0f}元",
            f"状态：{status_text}",
            note_line,
            "提醒：",
            *reminders,
        ]
    ).replace("\n\n备注：", "\n备注：")


def send_wechat_markdown(webhook_url: str, content: str, timeout: int = 10) -> None:
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"企业微信推送失败: {exc}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"企业微信返回非 JSON: {body}") from exc

    if result.get("errcode") != 0:
        raise RuntimeError(f"企业微信推送失败: {result}") from None


def _eastmoney_secid(item: WatchItem) -> str:
    market = item.market.upper() or item.code.split(".", 1)[-1].upper()
    if market == "SH":
        prefix = "1"
    elif market in {"SZ", "BJ"}:
        prefix = "0"
    else:
        raise RuntimeError(f"无法识别交易所: {item.code}")
    return f"{prefix}.{item.symbol}"


def fetch_eastmoney_ulist_quotes(items: Iterable[WatchItem], timeout: int = 10) -> Dict[str, Quote]:
    unique_items = {item.symbol: item for item in items}
    if not unique_items:
        return {}

    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("缺少依赖 requests，请先执行: pip install -r requirements.txt") from exc

    secids = ",".join(_eastmoney_secid(item) for item in unique_items.values())
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f12,f14,f2,f3,f6",
        "secids": secids,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }

    try:
        response = requests.get(EASTMONEY_ULIST_URL, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"东方财富小范围行情接口失败: {exc}") from exc

    if payload.get("rc") != 0:
        raise RuntimeError(f"东方财富小范围行情接口返回异常: {payload}")

    rows = (payload.get("data") or {}).get("diff") or []
    quotes: Dict[str, Quote] = {}
    for row in rows:
        symbol = str(row.get("f12", "")).strip().zfill(6)
        if symbol not in unique_items:
            continue
        quotes[symbol] = Quote(
            code=symbol,
            name=str(row.get("f14") or unique_items[symbol].name),
            latest_price=_to_float(row.get("f2")),
            change_pct=_to_float(row.get("f3")),
            amount=_to_float(row.get("f6")),
        )

    if not quotes:
        raise RuntimeError(f"东方财富小范围行情接口未返回监控股票: {secids}")
    return quotes


def fetch_akshare_realtime_quotes(items: Iterable[WatchItem]) -> Dict[str, Quote]:
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("缺少依赖 akshare，请先执行: pip install -r requirements.txt") from exc

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        df = ak.stock_zh_a_spot_em()

    missing_columns = [column for column in REQUIRED_AKSHARE_COLUMNS if column not in df.columns]
    if missing_columns:
        actual_columns = ", ".join(str(column) for column in df.columns)
        raise RuntimeError(
            "akshare 东方财富 A 股实时行情字段缺失: "
            f"缺少 {missing_columns}; 实际字段名: [{actual_columns}]"
        )

    wanted_symbols = {item.symbol for item in items}
    quotes: Dict[str, Quote] = {}
    for _, row in df.iterrows():
        symbol = str(row["代码"]).strip().zfill(6)
        if symbol not in wanted_symbols:
            continue
        quotes[symbol] = Quote(
            code=symbol,
            name=str(row["名称"]),
            latest_price=_to_float(row["最新价"]),
            change_pct=_to_float(row["涨跌幅"]),
            amount=_to_float(row["成交额"]),
        )
    return quotes


def fetch_realtime_quotes(items: Iterable[WatchItem]) -> Dict[str, Quote]:
    items = list(items)
    try:
        return fetch_eastmoney_ulist_quotes(items)
    except Exception as primary_exc:
        try:
            return fetch_akshare_realtime_quotes(items)
        except Exception as fallback_exc:
            raise RuntimeError(
                f"行情获取失败；东方财富小范围接口: {primary_exc}; AKShare 全市场接口: {fallback_exc}"
            ) from fallback_exc


def format_summary_line(now: datetime, item: WatchItem, quote: Optional[Quote], status: str) -> str:
    timestamp = _normalize_now(now).strftime("%Y-%m-%d %H:%M:%S")
    if quote is None:
        return (
            f"{timestamp} | {item.code} | {item.name} | 最新价 - | 涨跌幅 - | 成交额 - | "
            f"买入区间 {item.buy_low:.2f}-{item.buy_high:.2f} | 状态 {display_status('MISSING_QUOTE')}"
        )

    return (
        f"{timestamp} | {item.code} | {quote.name} | 最新价 {_format_price(quote.latest_price)} | "
        f"涨跌幅 {_format_pct(quote.change_pct)} | 成交额 {_format_amount(quote.amount)} | "
        f"买入区间 {item.buy_low:.2f}-{item.buy_high:.2f} | 状态 {display_status(status)}"
    )


def print_summary(now: datetime, items: Iterable[WatchItem], quotes: Dict[str, Quote]) -> None:
    logging.info("========== A股监控行情汇总 ==========")
    for item in items:
        quote = quotes.get(item.symbol)
        status = determine_status(item, quote.latest_price if quote else None)
        if quote and status in (STATUS_BUY_ZONE, STATUS_BELOW_ZONE) and not should_allow_alert(item, {}):
            status = "BLOCKED_BY_POSITION"
        logging.info("%s", format_summary_line(now, item, quote, status))


def process_alerts(
    now: datetime,
    items: Iterable[WatchItem],
    quotes: Dict[str, Quote],
    positions: Dict[str, Any],
    alert_state: Dict[str, Any],
    alert_state_path: Path,
    webhook_url: Optional[str],
    market_risk_snapshot: Optional[Any] = None,
    sector_risk_snapshot: Optional[Any] = None,
    stock_acceptance_by_symbol: Optional[Dict[str, Any]] = None,
) -> None:
    from fund_risk import (
        FinalAlert,
        MarketRisk,
        MarketRiskSnapshot,
        SectorRisk,
        SectorRiskSnapshot,
        StockAcceptanceSnapshot,
        StockAcceptance,
        build_fund_risk_message,
        decide_final_alert,
    )

    if market_risk_snapshot is None:
        market_risk_snapshot = MarketRiskSnapshot(
            MarketRisk.UNKNOWN,
            None,
            None,
            "none",
            "资金数据未提供，降级观察，不发送买入提醒",
        )
    if sector_risk_snapshot is None:
        sector_risk_snapshot = SectorRiskSnapshot(
            SectorRisk.UNKNOWN,
            0,
            0,
            0,
            0,
            None,
            0,
            0,
            "板块数据未提供，降级观察",
        )
    stock_acceptance_by_symbol = stock_acceptance_by_symbol or {}

    for item in items:
        quote = quotes.get(item.symbol)
        if quote is None:
            logging.warning("未找到行情: %s %s", item.code, item.name)
            continue

        status = determine_status(item, quote.latest_price)
        if status not in (STATUS_BUY_ZONE, STATUS_BELOW_ZONE):
            continue

        if quote.latest_price is None:
            continue

        if not should_allow_alert(item, positions):
            logging.info(
                "%s %s 触发 %s，但 %s 已标记 bought=true，跳过提醒",
                item.code,
                item.name,
                display_status(status),
                item.depends_on_not_bought,
            )
            continue

        stock_acceptance = stock_acceptance_by_symbol.get(item.symbol) or StockAcceptanceSnapshot(
            StockAcceptance.WEAK,
            "缺少个股承接数据，降级观察",
        )
        final_alert = decide_final_alert(
            item=item,
            price_status=status,
            latest_price=quote.latest_price,
            market_risk=market_risk_snapshot.level,
            sector_risk=sector_risk_snapshot.level,
            stock_acceptance=stock_acceptance.level,
        )
        if final_alert == FinalAlert.NONE:
            continue

        alert_type = final_alert.value
        if not should_alert(alert_state, item.code, alert_type, now):
            continue

        if not webhook_url:
            logging.warning(
                "%s %s 触发 %s，但未设置 WECHAT_WEBHOOK_URL，无法发送企业微信群提醒",
                item.code,
                item.name,
                display_status(final_alert.value),
            )
            continue

        message = build_fund_risk_message(
            item,
            quote.latest_price,
            final_alert,
            market_risk_snapshot,
            sector_risk_snapshot,
            stock_acceptance,
        )
        send_wechat_markdown(webhook_url, message)
        record_alert(alert_state_path, alert_state, item.code, alert_type, now, quote.latest_price)
        logging.info("%s %s 已发送企业微信提醒: %s", item.code, item.name, display_status(final_alert.value))


def run_monitor(
    config_path: Path,
    alert_state_path: Path,
    position_state_path: Path,
    fetch_interval: int = FETCH_INTERVAL_SECONDS,
    summary_interval: int = SUMMARY_INTERVAL_SECONDS,
    once: bool = False,
) -> None:
    items = load_config(config_path)
    positions = ensure_position_state(position_state_path)
    alert_state = ensure_alert_state(alert_state_path)
    webhook_url = os.getenv("WECHAT_WEBHOOK_URL")

    logging.info(
        "A股买点监控启动 | 股票数 %s | 拉取间隔 %s 秒 | 汇总间隔 %s 秒 | Ctrl-C 退出",
        len(items),
        fetch_interval,
        summary_interval,
    )
    if not webhook_url:
        logging.warning("未设置 WECHAT_WEBHOOK_URL，触发提醒时只会打印本地警告，不会推送企业微信")

    last_summary_at: Optional[float] = None
    last_waiting_log_at: Optional[float] = None

    while True:
        started_at = time.monotonic()
        now = datetime.now(TZ)

        try:
            if not is_trading_time(now):
                if last_waiting_log_at is None or started_at - last_waiting_log_at >= summary_interval:
                    logging.info("%s 当前不在 A 股交易时段，等待下一轮检查", now.strftime("%Y-%m-%d %H:%M:%S"))
                    last_waiting_log_at = started_at
                if once:
                    return
            else:
                quotes = fetch_realtime_quotes(items)
                process_alerts(now, items, quotes, positions, alert_state, alert_state_path, webhook_url)

                if last_summary_at is None or started_at - last_summary_at >= summary_interval:
                    print_summary(now, items, quotes)
                    last_summary_at = started_at

                if once:
                    return
        except Exception:
            logging.exception("本轮监控失败")
            if once:
                raise

        elapsed = time.monotonic() - started_at
        time.sleep(max(0, fetch_interval - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A 股买点监控：只提醒人工确认，不自动交易。")
    parser.add_argument("--config", default=str(BASE_DIR / "config.yaml"), help="配置文件路径")
    parser.add_argument("--alert-state", default=str(BASE_DIR / "alert_state.json"), help="提醒状态文件路径")
    parser.add_argument("--position-state", default=str(BASE_DIR / "position_state.json"), help="持仓状态文件路径")
    parser.add_argument("--fetch-interval", type=int, default=FETCH_INTERVAL_SECONDS, help="行情拉取间隔秒数")
    parser.add_argument("--summary-interval", type=int, default=SUMMARY_INTERVAL_SECONDS, help="汇总打印间隔秒数")
    parser.add_argument("--once", action="store_true", help="只执行一轮，便于排查配置")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv_if_available(BASE_DIR / ".env")
    args = parse_args()

    try:
        run_monitor(
            config_path=Path(args.config),
            alert_state_path=Path(args.alert_state),
            position_state_path=Path(args.position_state),
            fetch_interval=args.fetch_interval,
            summary_interval=args.summary_interval,
            once=args.once,
        )
    except KeyboardInterrupt:
        logging.info("已退出 A 股买点监控")
    except RuntimeError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
