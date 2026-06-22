import contextlib
import io
import math
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from main import Quote, WatchItem


class MarketRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class SectorRisk(str, Enum):
    LOW = "SECTOR_RISK_LOW"
    MEDIUM = "SECTOR_RISK_MEDIUM"
    HIGH = "SECTOR_RISK_HIGH"
    UNKNOWN = "SECTOR_RISK_UNKNOWN"


class StockAcceptance(str, Enum):
    CONFIRMED = "ACCEPTANCE_CONFIRMED"
    WEAK = "PRICE_IN_ZONE_BUT_NO_CONFIRM"
    UNKNOWN = "ACCEPTANCE_UNKNOWN"


class FinalAlert(str, Enum):
    NONE = "NONE"
    BUY_CONFIRMED = "BUY_CONFIRMED"
    WATCH_ONLY = "WATCH_ONLY"
    RISK_BLOCKED = "RISK_BLOCKED"
    BELOW_ZONE_RISK = "BELOW_ZONE_RISK"


AI_CORE_WATCH = [
    "601138.SH",
    "002463.SZ",
    "603228.SH",
    "002130.SZ",
    "300394.SZ",
    "300502.SZ",
    "300308.SZ",
    "300476.SZ",
    "688256.SH",
    "600183.SH",
]

DISPLAY_LABELS = {
    "LOW": "低风险",
    "MEDIUM": "中风险",
    "HIGH": "高风险",
    "UNKNOWN": "未知",
    "SECTOR_RISK_LOW": "板块低风险",
    "SECTOR_RISK_MEDIUM": "板块中风险",
    "SECTOR_RISK_HIGH": "板块高风险",
    "SECTOR_RISK_UNKNOWN": "板块未知",
    "ACCEPTANCE_CONFIRMED": "承接确认",
    "PRICE_IN_ZONE_BUT_NO_CONFIRM": "承接不足",
    "ACCEPTANCE_UNKNOWN": "承接未知",
    "NONE": "无提醒",
    "BUY_CONFIRMED": "买点确认",
    "WATCH_ONLY": "观察提醒",
    "RISK_BLOCKED": "风险拦截",
    "BELOW_ZONE_RISK": "跌破风险",
    "BUY_ZONE": "进入区间",
    "WAIT_PULLBACK": "等待回落",
    "BELOW_ZONE": "跌破区间",
    "NO_PRICE": "无价格",
    "MISSING_QUOTE": "无行情",
    "BLOCKED_BY_POSITION": "持仓阻断",
}


def display_label(value: Any) -> str:
    if value is None:
        return "-"
    text = value.value if hasattr(value, "value") else str(value)
    return DISPLAY_LABELS.get(text, text)


@dataclass(frozen=True)
class FundFlowSnapshot:
    main_net_inflow_yi: Optional[float]
    net_inflow_15m_delta_yi: Optional[float]
    source: str
    error: str = ""


@dataclass(frozen=True)
class MarketRiskSnapshot:
    level: MarketRisk
    main_net_inflow_yi: Optional[float]
    net_inflow_15m_delta_yi: Optional[float]
    source: str
    reason: str


@dataclass(frozen=True)
class SectorRiskSnapshot:
    level: SectorRisk
    up_count: int
    down_count: int
    flat_count: int
    sample_count: int
    avg_change_pct: Optional[float]
    below_vwap_count: int
    back_to_vwap_count: int
    reason: str


@dataclass(frozen=True)
class StockAcceptanceSnapshot:
    level: StockAcceptance
    reason: str
    below_intraday_avg: Optional[bool] = None
    making_new_low: Optional[bool] = None
    five_min_drop_expanding: Optional[bool] = None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("%", "")
        if value in {"", "-", "--", "None", "nan", "NaN"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def normalize_symbol(code: str) -> str:
    return str(code).split(".", 1)[0].zfill(6)


def evaluate_market_risk(snapshot: Optional[FundFlowSnapshot]) -> MarketRiskSnapshot:
    if snapshot is None or snapshot.main_net_inflow_yi is None:
        return MarketRiskSnapshot(
            level=MarketRisk.UNKNOWN,
            main_net_inflow_yi=None,
            net_inflow_15m_delta_yi=None,
            source=snapshot.source if snapshot else "none",
            reason="资金数据获取失败，降级观察，不发送买入提醒",
        )

    amount = snapshot.main_net_inflow_yi
    delta = snapshot.net_inflow_15m_delta_yi

    if amount <= -700 and (delta is None or delta < 0):
        return MarketRiskSnapshot(MarketRisk.HIGH, amount, delta, snapshot.source, "大盘主力净流出超过 700 亿且继续扩大")
    if amount <= -500:
        return MarketRiskSnapshot(MarketRisk.MEDIUM, amount, delta, snapshot.source, "大盘主力净流出超过 500 亿")
    if amount >= 0 or amount > -200:
        return MarketRiskSnapshot(MarketRisk.LOW, amount, delta, snapshot.source, "大盘主力净流入转正或净流出小于 200 亿")
    if amount < 0 and delta is not None and delta > 0:
        return MarketRiskSnapshot(MarketRisk.MEDIUM, amount, delta, snapshot.source, "净流出仍为负，但最近 15 分钟收窄")
    return MarketRiskSnapshot(MarketRisk.MEDIUM, amount, delta, snapshot.source, "大盘资金仍有分歧")


def evaluate_sector_risk(
    quotes: Dict[str, Quote],
    ai_core_watch: Optional[Iterable[str]] = None,
    intraday_metrics: Optional[Dict[str, Dict[str, Any]]] = None,
) -> SectorRiskSnapshot:
    symbols = [normalize_symbol(code) for code in (ai_core_watch or AI_CORE_WATCH)]
    intraday_metrics = intraday_metrics or {}
    changes: List[float] = []
    up_count = down_count = flat_count = 0
    below_vwap_count = back_to_vwap_count = 0

    for symbol in symbols:
        quote = quotes.get(symbol)
        if quote is None or quote.change_pct is None:
            continue
        change = quote.change_pct
        changes.append(change)
        if change > 0:
            up_count += 1
        elif change < 0:
            down_count += 1
        else:
            flat_count += 1

        metrics = intraday_metrics.get(symbol) or {}
        if metrics.get("below_intraday_avg") is True:
            below_vwap_count += 1
        if metrics.get("back_to_intraday_avg") is True:
            back_to_vwap_count += 1

    sample_count = len(changes)
    if sample_count == 0:
        return SectorRiskSnapshot(SectorRisk.UNKNOWN, 0, 0, 0, 0, None, 0, 0, "AI 核心票行情不足")

    avg_change = sum(changes) / sample_count
    down_ratio = down_count / sample_count
    below_vwap_ratio = below_vwap_count / sample_count
    up_ratio = up_count / sample_count

    if down_ratio > 0.7 and avg_change <= -2.5:
        return SectorRiskSnapshot(
            SectorRisk.HIGH,
            up_count,
            down_count,
            flat_count,
            sample_count,
            avg_change,
            below_vwap_count,
            back_to_vwap_count,
            "AI 核心票超过 70% 下跌且平均跌幅超过 2.5%",
        )
    if below_vwap_ratio > 0.7:
        return SectorRiskSnapshot(
            SectorRisk.HIGH,
            up_count,
            down_count,
            flat_count,
            sample_count,
            avg_change,
            below_vwap_count,
            back_to_vwap_count,
            "AI 核心票超过 70% 低于分时均价线",
        )
    if back_to_vwap_count >= 3:
        return SectorRiskSnapshot(
            SectorRisk.MEDIUM,
            up_count,
            down_count,
            flat_count,
            sample_count,
            avg_change,
            below_vwap_count,
            back_to_vwap_count,
            "核心票跌幅有收窄迹象，至少 3 只站回分时均价线",
        )
    if up_ratio >= 0.5:
        return SectorRiskSnapshot(
            SectorRisk.LOW,
            up_count,
            down_count,
            flat_count,
            sample_count,
            avg_change,
            below_vwap_count,
            back_to_vwap_count,
            "AI 核心票至少 50% 红盘",
        )
    return SectorRiskSnapshot(
        SectorRisk.MEDIUM,
        up_count,
        down_count,
        flat_count,
        sample_count,
        avg_change,
        below_vwap_count,
        back_to_vwap_count,
        "AI 核心票有分歧，保持观察",
    )


def evaluate_stock_acceptance(
    item: WatchItem,
    quote: Optional[Quote],
    intraday_metric: Optional[Dict[str, Any]] = None,
) -> StockAcceptanceSnapshot:
    if quote is None or quote.latest_price is None:
        return StockAcceptanceSnapshot(StockAcceptance.UNKNOWN, "个股行情缺失，不能确认承接")

    intraday_metric = intraday_metric or {}
    making_new_low = intraday_metric.get("making_new_low")
    below_avg = intraday_metric.get("below_intraday_avg")
    five_min_drop_expanding = intraday_metric.get("five_min_drop_expanding")
    main_outflow_expanding = intraday_metric.get("main_outflow_expanding")

    if making_new_low is True or below_avg is True or five_min_drop_expanding is True or main_outflow_expanding is True:
        return StockAcceptanceSnapshot(
            StockAcceptance.WEAK,
            "买入区间内承接不足，仍低于均价线或继续走弱",
            below_intraday_avg=below_avg,
            making_new_low=making_new_low,
            five_min_drop_expanding=five_min_drop_expanding,
        )

    if not intraday_metric:
        return StockAcceptanceSnapshot(
            StockAcceptance.WEAK,
            "缺少分时均价/5分钟承接数据，降级观察",
            below_intraday_avg=None,
            making_new_low=None,
            five_min_drop_expanding=None,
        )

    return StockAcceptanceSnapshot(
        StockAcceptance.CONFIRMED,
        "价格进入区间且未继续创新低，个股出现承接",
        below_intraday_avg=below_avg,
        making_new_low=making_new_low,
        five_min_drop_expanding=five_min_drop_expanding,
    )


def decide_final_alert(
    item: WatchItem,
    price_status: str,
    latest_price: Optional[float],
    market_risk: MarketRisk,
    sector_risk: SectorRisk,
    stock_acceptance: StockAcceptance,
) -> FinalAlert:
    if price_status == "BELOW_ZONE":
        return FinalAlert.BELOW_ZONE_RISK
    if price_status != "BUY_ZONE" or latest_price is None:
        return FinalAlert.NONE
    if market_risk == MarketRisk.HIGH or sector_risk == SectorRisk.HIGH:
        return FinalAlert.RISK_BLOCKED
    if market_risk == MarketRisk.UNKNOWN:
        return FinalAlert.WATCH_ONLY
    if market_risk == MarketRisk.MEDIUM or sector_risk in {SectorRisk.MEDIUM, SectorRisk.UNKNOWN}:
        return FinalAlert.WATCH_ONLY
    if stock_acceptance != StockAcceptance.CONFIRMED:
        return FinalAlert.WATCH_ONLY
    return FinalAlert.BUY_CONFIRMED


def build_fund_risk_message(
    item: WatchItem,
    latest_price: float,
    final_alert: FinalAlert,
    market_risk: MarketRiskSnapshot,
    sector_risk: SectorRiskSnapshot,
    stock_acceptance: StockAcceptanceSnapshot,
) -> str:
    amount = latest_price * item.shares
    base_lines = [
        f"股票：{item.name} {item.code}",
        f"现价：{latest_price:.2f}",
        f"买入区间：{item.buy_low:.2f} - {item.buy_high:.2f}",
    ]

    if final_alert == FinalAlert.BUY_CONFIRMED:
        return "\n".join(
            [
                "【A股买点确认】",
                "",
                *base_lines,
                f"计划股数：{item.shares}股",
                f"预计金额：{amount:.0f}元",
                "",
                "状态：价格进入买入区间，市场风险未继续恶化，个股出现承接。",
                f"市场风险：{market_risk.level.value}；板块风险：{sector_risk.level.value}",
                "",
                "注意：",
                "这不是自动交易指令，下单前仍需人工确认。",
            ]
        )

    if final_alert == FinalAlert.RISK_BLOCKED:
        return "\n".join(
            [
                "【A股风险拦截】",
                "",
                *base_lines,
                "",
                "状态：价格虽然进入买入区间，但大盘主力资金大幅净流出，AI科技链集体下跌。",
                f"市场风险：{market_risk.level.value}，{market_risk.reason}",
                f"板块风险：{sector_risk.level.value}，{sector_risk.reason}",
                "",
                "结论：",
                "禁止机械买入。",
                "这可能不是低吸，而是下跌中继。",
                "等尾盘 14:30 后重新判断。",
            ]
        )

    if final_alert == FinalAlert.BELOW_ZONE_RISK:
        return "\n".join(
            [
                "【A股风险提醒】",
                "",
                *base_lines,
                "",
                "状态：价格跌破计划区间下沿，可能是下跌中继，需要人工复盘。",
                "结论：不能因为低于买入区间就机械买入，避免接飞刀。",
            ]
        )

    return "\n".join(
        [
            "【A股观察提醒】",
            "",
            *base_lines,
            "",
            "状态：价格已经进入计划区间，但市场资金仍有分歧，暂不建议机械买入。",
            f"市场风险：{market_risk.level.value}，{market_risk.reason}",
            f"板块风险：{sector_risk.level.value}，{sector_risk.reason}",
            f"个股承接：{stock_acceptance.level.value}，{stock_acceptance.reason}",
            "",
            "处理建议：",
            "等 14:30 后确认是否止跌。",
            "如果大盘主力净流出继续扩大，放弃本次买点。",
            "如果个股站回分时均价线、板块跌幅收窄，再人工确认。",
        ]
    )


def fetch_market_fund_flow() -> FundFlowSnapshot:
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
    try:
        import akshare as ak
    except ImportError as exc:
        return FundFlowSnapshot(None, None, "akshare", f"缺少 akshare: {exc}")

    candidates = [
        ("stock_market_fund_flow", getattr(ak, "stock_market_fund_flow", None)),
        ("stock_fund_flow_individual", getattr(ak, "stock_fund_flow_individual", None)),
    ]
    errors: List[str] = []
    for name, func in candidates:
        if func is None:
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                data = func()
            amount = extract_main_net_inflow_yi(data)
            if amount is not None:
                return FundFlowSnapshot(amount, None, name)
            errors.append(f"{name}: 未找到主力净流入字段")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    return FundFlowSnapshot(None, None, "akshare", "; ".join(errors) or "没有可用资金接口")


def extract_main_net_inflow_yi(data: Any) -> Optional[float]:
    columns = getattr(data, "columns", [])
    if len(columns) == 0:
        return None

    field_candidates = [
        "主力净流入",
        "主力净流入-净额",
        "今日主力净流入-净额",
        "净额",
        "主力净额",
        "主力净流入净额",
    ]
    for field in field_candidates:
        if field not in columns:
            continue
        try:
            value = data.iloc[-1][field]
        except Exception:
            continue
        amount = _to_float(value)
        if amount is None:
            continue
        if abs(amount) > 10000:
            return amount / 100000000
        return amount
    return None
