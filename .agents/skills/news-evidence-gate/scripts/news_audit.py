#!/usr/bin/env python3
"""
news_audit.py

MVP evidence gate for stock analysis.

Design goals:
- Never fail silently when data sources are unavailable.
- Always produce evidence_pack.json and evidence_pack.md.
- Treat missing official disclosures/news as confidence-cap events.
- Support demo mode for offline validation.

Examples:
  python news_audit.py --query DEMO --market A --demo --out /tmp/news-demo
  python news_audit.py --query 600519 --market A --stock-home "$STOCK_SKILLS_HOME" --out ./.cache/news-evidence-gate/600519
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


MATERIAL_KEYWORDS: dict[str, list[str]] = {
    "earnings_revision": ["业绩预告", "业绩快报", "修正", "预亏", "预增", "预减", "profit warning", "guidance"],
    "fraud_investigation": ["财务造假", "立案调查", "审计", "fraud", "investigation"],
    "regulatory_penalty": ["处罚", "立案", "调查", "监管", "警示函", "问询函", "penalty", "probe"],
    "trading_halt": ["停牌", "复牌", "halt", "suspension"],
    "debt_default": ["违约", "流动性", "评级下调", "default", "downgrade"],
    "major_customer_loss": ["大客户", "客户流失", "订单取消", "customer loss"],
    "export_control_sanction": ["出口管制", "制裁", "实体清单", "关税", "sanction", "tariff", "export control"],
    "safety_accident": ["事故", "火灾", "爆炸", "召回", "安全", "recall", "accident"],
    "delisting_risk": ["退市", "ST", "delisting"],
    "key_person_event": ["实控人", "董事长", "CFO", "核心技术人员", "resign", "resignation"],
    "major_contract": ["重大合同", "中标", "订单", "框架协议", "contract", "order"],
    "shareholder_change": ["减持", "增持", "回购", "质押", "冻结", "buyback", "pledge"],
    "ma_restructuring": ["并购", "重组", "收购", "资产注入", "acquisition", "merger", "restructuring"],
    "litigation": ["诉讼", "仲裁", "判决", "lawsuit", "litigation"],
    "industry_policy": ["政策", "医保", "集采", "价格管制", "补贴", "policy", "regulation"],
    "product_approval": ["获批", "临床", "认证", "approval", "FDA"],
    "capacity_change": ["扩产", "停产", "产能", "供应链", "capacity", "supply chain"],
    "social_sentiment_spike": ["热议", "爆雷", "传闻", "rumor", "viral"],
}

HIGH_IMPACT_CATEGORIES = {
    "earnings_revision",
    "fraud_investigation",
    "regulatory_penalty",
    "trading_halt",
    "debt_default",
    "major_customer_loss",
    "export_control_sanction",
    "safety_accident",
    "delisting_risk",
    "key_person_event",
    "major_contract",
    "shareholder_change",
    "ma_restructuring",
    "litigation",
    "industry_policy",
    "product_approval",
    "capacity_change",
}

MATERIAL_KEYWORDS.update(
    {
        "trading_anomaly": ["股票交易异常波动", "交易异常波动", "异常波动", "异动", "涨幅偏离", "跌幅偏离"],
        "dividend": ["权益分派", "分红", "派息", "除权", "除息"],
        "management_change": ["董事长", "法定代表人", "高管", "任职", "辞职", "补选"],
        "earnings_revision": MATERIAL_KEYWORDS["earnings_revision"] + ["业绩预告", "业绩快报", "修正", "预亏", "预增", "预减"],
        "fraud_investigation": MATERIAL_KEYWORDS["fraud_investigation"] + ["财务造假", "立案调查", "审计"],
        "regulatory_penalty": MATERIAL_KEYWORDS["regulatory_penalty"] + ["处罚", "立案", "调查", "监管", "警示函", "问询函"],
        "trading_halt": MATERIAL_KEYWORDS["trading_halt"] + ["停牌", "复牌"],
        "debt_default": MATERIAL_KEYWORDS["debt_default"] + ["违约", "流动性", "评级下调"],
        "major_customer_loss": MATERIAL_KEYWORDS["major_customer_loss"] + ["大客户", "客户流失", "订单取消"],
        "export_control_sanction": MATERIAL_KEYWORDS["export_control_sanction"] + ["出口管制", "制裁", "实体清单", "关税"],
        "safety_accident": MATERIAL_KEYWORDS["safety_accident"] + ["事故", "火灾", "爆炸", "召回", "安全"],
        "delisting_risk": MATERIAL_KEYWORDS["delisting_risk"] + ["退市"],
        "key_person_event": MATERIAL_KEYWORDS["key_person_event"] + ["实控人", "董事长", "核心技术人员"],
        "major_contract": MATERIAL_KEYWORDS["major_contract"] + ["重大合同", "中标", "订单", "框架协议"],
        "shareholder_change": MATERIAL_KEYWORDS["shareholder_change"] + ["减持", "增持", "回购", "质押", "冻结"],
        "ma_restructuring": MATERIAL_KEYWORDS["ma_restructuring"] + ["并购", "重组", "收购", "资产注入"],
        "litigation": MATERIAL_KEYWORDS["litigation"] + ["诉讼", "仲裁", "判决"],
        "industry_policy": MATERIAL_KEYWORDS["industry_policy"] + ["政策", "医保", "集采", "价格管制", "补贴"],
        "product_approval": MATERIAL_KEYWORDS["product_approval"] + ["获批", "临床", "认证"],
        "capacity_change": MATERIAL_KEYWORDS["capacity_change"] + ["扩产", "停产", "产能", "供应链"],
        "social_sentiment_spike": MATERIAL_KEYWORDS["social_sentiment_spike"] + ["热议", "爆雷", "传闻"],
    }
)
HIGH_IMPACT_CATEGORIES.update({"trading_anomaly"})

EASTMONEY_TOKEN = "D43BF722C8E33D741DCB40B44B70D7B3"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 90) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception as exc:  # noqa: BLE001
        return 999, "", repr(exc)


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def classify_event(text: str) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    for label, keywords in MATERIAL_KEYWORDS.items():
        if any(keyword.lower() in lower for keyword in keywords):
            hits.append(label)
    return sorted(set(hits))


def source_reliability(source: str) -> int:
    s = source.lower()
    if any(x in s for x in ["official", "exchange", "cninfo", "sec", "hkex", "disclosure"]):
        return 5
    if any(x in s for x in ["price_volume", "kline", "quote", "sina"]):
        return 4
    if any(x in s for x in ["market_news", "news", "eastmoney", "headline"]):
        return 4
    if any(x in s for x in ["flash", "7x24"]):
        return 3
    if any(x in s for x in ["social", "forum", "xueqiu", "guba"]):
        return 2
    return 3


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_url_text(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> str:
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    request = Request(url, headers=req_headers)
    try:
        with urlopen(request, timeout=timeout) as resp:  # noqa: S310 - public market-data fetch
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")
    except Exception as primary_exc:  # noqa: BLE001
        cmd = ["curl.exe", "-L", "--silent", "--show-error"]
        for key, value in req_headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
        cmd.append(url)
        code, out, err = run_cmd(cmd, timeout=timeout)
        if code == 0 and out:
            return out
        raise RuntimeError(f"urlopen failed: {primary_exc}; curl fallback failed code={code}: {err[:240]}") from primary_exc


def parse_jsonish(raw: str) -> Any:
    text = raw.strip().lstrip("\ufeff")
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    match = re.search(r"^[\w$]+\((.*)\)\s*;?$", text, re.S)
    if match:
        return json.loads(match.group(1))
    return None


def evidence_item(
    source: str,
    title: str,
    *,
    raw: Any | None = None,
    url: str = "",
    published_at: str = "",
    confirmed: bool | None = None,
    coverage_only: bool = False,
) -> dict[str, Any] | None:
    clean_title = clean_text(title)
    if len(clean_title) < 4:
        return None
    reliability = source_reliability(source)
    item_confirmed = confirmed if confirmed is not None else reliability >= 4
    item = {
        "id": stable_id(source + clean_title + url + published_at),
        "source": source,
        "title": clean_title[:260],
        "raw": raw if raw is not None else clean_title,
        "event_categories": classify_event(clean_title),
        "reliability": reliability,
        "confirmed": bool(item_confirmed and reliability >= 4 and not coverage_only),
        "captured_at": now_iso(),
    }
    if url:
        item["url"] = url
    if published_at:
        item["published_at"] = published_at
    if coverage_only:
        item["coverage_only"] = True
    return item


def append_item(items: list[dict[str, Any]], item: dict[str, Any] | None) -> None:
    if item:
        items.append(item)


def market_id_for_code(code: str) -> str:
    return "1" if code.startswith(("5", "6", "9")) else "0"


def sina_symbol_for_code(code: str) -> str:
    return ("sh" if market_id_for_code(code) == "1" else "sz") + code


def parse_text_items(source_name: str, raw: str, *, confirmed: bool | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in raw.splitlines():
        title = re.sub(r"\s+", " ", line.strip())
        if len(title) < 8:
            continue
        cats = classify_event(title)
        reliability = source_reliability(source_name)
        item_confirmed = confirmed if confirmed is not None else reliability >= 4
        items.append(
            {
                "id": stable_id(source_name + title),
                "source": source_name,
                "title": title[:260],
                "raw": title,
                "event_categories": cats,
                "reliability": reliability,
                "confirmed": bool(item_confirmed and reliability >= 4),
                "captured_at": now_iso(),
            }
        )
    return items


def demo_items(query: str) -> list[dict[str, Any]]:
    raw = f"""
官方公告：{query} 发布回购进展公告，当前无停牌或退市风险提示。
市场新闻：{query} 所属板块出现资金流入，行业景气度讨论升温。
7x24快讯：相关产业政策发布，市场关注龙头公司订单弹性。
社媒舆情：投资者讨论热度上升，但未见可确认重大利空。
价格异动：近三日成交量放大，需要与资金流和新闻催化交叉验证。
""".strip()
    items = []
    for source, line in [
        ("official_disclosure_demo", raw.splitlines()[0]),
        ("market_news_demo", raw.splitlines()[1]),
        ("flash_news_demo", raw.splitlines()[2]),
        ("social_sentiment_demo", raw.splitlines()[3]),
        ("price_volume_demo", raw.splitlines()[4]),
    ]:
        items.extend(parse_text_items(source, line, confirmed=True))
    return items


def collect_from_stock_skills(stock_home: Path, query: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Best-effort adapter for tetap/stock-skills CLI."""
    items: list[dict[str, Any]] = []
    missing: list[str] = []

    em = stock_home / "scripts" / "em.py"
    if not em.exists():
        return items, [f"stock-skills CLI not found: {em}"]

    py_candidates = [stock_home / ".venv" / "bin" / "python", Path(sys.executable)]
    py = next((p for p in py_candidates if p.exists()), Path(sys.executable))

    commands: list[tuple[str, list[str]]] = [
        ("stock_skills_list", [str(py), str(em), "list"]),
        ("resolve_symbol", [str(py), str(em), "resolve_symbol", "--query", query]),
        ("market_news_flash", [str(py), str(em), "get_market_news", "--source", "all"]),
        ("news_and_reports", [str(py), str(em), "get_news_and_reports", "--query", query]),
        ("realtime_quote", [str(py), str(em), "get_realtime_quote", "--query", query]),
        ("kline", [str(py), str(em), "get_kline", "--query", query, "--limit", "60"]),
        ("fund_flow", [str(py), str(em), "get_stock_fund_flow", "--query", query]),
    ]

    for name, cmd in commands:
        code, out, err = run_cmd(cmd, cwd=stock_home, timeout=120)
        if code != 0 or not out.strip():
            missing.append(f"{name} failed or empty. code={code}; stderr={err[:240]}")
            continue
        items.extend(parse_text_items(name, out))

    return items, missing


def resolve_a_share(query: str, fetch_text=fetch_url_text) -> tuple[dict[str, str] | None, list[str]]:
    missing: list[str] = []
    code_match = re.search(r"\b(\d{6})\b", query)
    if code_match:
        code = code_match.group(1)
        return {
            "code": code,
            "name": query,
            "quote_id": f"{market_id_for_code(code)}.{code}",
            "market_id": market_id_for_code(code),
        }, missing

    url = (
        "https://searchapi.eastmoney.com/api/suggest/get"
        f"?input={quote(query)}&type=14&token={EASTMONEY_TOKEN}"
    )
    try:
        data = parse_jsonish(fetch_text(url))
        rows = (((data or {}).get("QuotationCodeTable") or {}).get("Data") or [])
        astock = next((row for row in rows if str(row.get("Classify", "")).lower() == "astock"), None)
        row = astock or (rows[0] if rows else None)
        if not row:
            return None, [f"builtin_resolve failed: no A-share match for {query}"]
        code = str(row.get("Code") or row.get("UnifiedCode") or "")
        market_id = str(row.get("MarketType") or market_id_for_code(code))
        return {
            "code": code,
            "name": str(row.get("Name") or query),
            "quote_id": str(row.get("QuoteID") or f"{market_id}.{code}"),
            "market_id": market_id,
        }, missing
    except Exception as exc:  # noqa: BLE001
        return None, [f"builtin_resolve failed: {exc}"]


def collect_eastmoney_announcements(
    resolved: dict[str, str],
    fetch_text=fetch_url_text,
) -> tuple[list[dict[str, Any]], list[str]]:
    code = resolved["code"]
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?sr=-1&page_size=20&page_index=1&ann_type=A&client_source=web&stock_list={code}"
    )
    try:
        data = parse_jsonish(fetch_text(url, headers={"Referer": "https://data.eastmoney.com/"}))
        rows = (((data or {}).get("data") or {}).get("list") or [])
    except Exception as exc:  # noqa: BLE001
        return [], [f"official_disclosure:eastmoney_announcements failed: {exc}"]

    items: list[dict[str, Any]] = []
    for row in rows:
        title = row.get("title_ch") or row.get("title") or ""
        art_code = str(row.get("art_code") or "")
        notice_date = str(row.get("notice_date") or row.get("display_time") or "")
        detail_url = f"https://data.eastmoney.com/notices/detail/{code}/{art_code}.html" if art_code else ""
        append_item(
            items,
            evidence_item(
                "official_disclosure:eastmoney_announcements",
                f"{notice_date[:10]} {title}",
                raw=row,
                url=detail_url,
                published_at=notice_date,
                confirmed=True,
            ),
        )
    if not items:
        return [], ["official_disclosure:eastmoney_announcements empty"]
    return items, []


def collect_sina_quote(
    resolved: dict[str, str],
    fetch_text=fetch_url_text,
) -> tuple[list[dict[str, Any]], list[str]]:
    code = resolved["code"]
    symbol = sina_symbol_for_code(code)
    url = f"https://hq.sinajs.cn/list={symbol}"
    try:
        raw = fetch_text(url, headers={"Referer": "https://finance.sina.com.cn/"})
    except Exception as exc:  # noqa: BLE001
        return [], [f"price_volume:sina_quote failed: {exc}"]

    match = re.search(r'="(.*)";', raw)
    if not match:
        return [], ["price_volume:sina_quote empty"]
    parts = match.group(1).split(",")
    if len(parts) < 32 or not parts[0]:
        return [], ["price_volume:sina_quote malformed"]

    try:
        prev_close = float(parts[2])
        last = float(parts[3])
        high = float(parts[4])
        low = float(parts[5])
        pct = ((last / prev_close) - 1) * 100 if prev_close else 0.0
        amount = float(parts[9])
        amplitude = ((high - low) / prev_close) * 100 if prev_close else 0.0
        anomaly = abs(pct) >= 7 or amplitude >= 10 or amount >= 5_000_000_000
        title = (
            f"行情: {parts[0]} {code} 最新{last:.2f} 涨跌幅{pct:.2f}% "
            f"最高{high:.2f} 最低{low:.2f} 振幅{amplitude:.2f}% "
            f"成交额{amount / 100000000:.2f}亿 时间{parts[30]} {parts[31]}"
        )
    except Exception:
        anomaly = False
        amount = None
        amplitude = None
        pct = None
        title = f"行情: {parts[0]} {code} " + ",".join(parts[:10])

    item = evidence_item(
        "price_volume:sina_quote",
        title,
        raw={
            "url": url,
            "fields": parts,
            "pct": pct,
            "amplitude": amplitude,
            "amount": amount,
            "anomaly": anomaly,
        },
        url=url,
        published_at=f"{parts[30]} {parts[31]}" if len(parts) > 31 else "",
        confirmed=True,
    )
    return ([item] if item else []), []


def collect_eastmoney_kline(
    resolved: dict[str, str],
    fetch_text=fetch_url_text,
) -> tuple[list[dict[str, Any]], list[str]]:
    quote_id = resolved["quote_id"]
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={quote_id}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=1&beg=20250101&end=20500101"
    )
    try:
        data = parse_jsonish(fetch_text(url))
        rows = (((data or {}).get("data") or {}).get("klines") or [])
    except Exception as exc:  # noqa: BLE001
        return [], [f"price_volume:eastmoney_kline failed: {exc}"]

    parsed: list[dict[str, Any]] = []
    for row in rows:
        parts = str(row).split(",")
        if len(parts) < 11:
            continue
        try:
            parsed.append(
                {
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]),
                    "amplitude": float(parts[7]),
                    "pct": float(parts[8]),
                    "change": float(parts[9]),
                    "turnover": float(parts[10]),
                }
            )
        except ValueError:
            continue

    if not parsed:
        return [], ["price_volume:eastmoney_kline empty"]

    first = parsed[0]
    last = parsed[-1]
    max_row = max(parsed, key=lambda row: row["high"])
    period_return = ((last["close"] / first["close"]) - 1) * 100 if first["close"] else 0.0
    has_limit_like_move = any(abs(row["pct"]) >= 9.5 for row in parsed[-20:])
    has_turnover_spike = last["turnover"] >= 10 or last["amount"] >= 5_000_000_000
    anomaly = abs(period_return) >= 20 or has_limit_like_move or has_turnover_spike
    title_prefix = "K线异常" if anomaly else "K线检查"
    title = (
        f"{title_prefix}: {resolved.get('name') or resolved['code']} {first['date']}至{last['date']} "
        f"收盘涨幅{period_return:.2f}% 最高{max_row['high']:.2f} "
        f"最新收盘{last['close']:.2f} 最新换手{last['turnover']:.2f}% "
        f"最新成交额{last['amount'] / 100000000:.2f}亿"
    )
    item = evidence_item(
        "price_volume:eastmoney_kline",
        title,
        raw={
            "url": url,
            "first": first,
            "last": last,
            "max": max_row,
            "period_return_pct": period_return,
            "anomaly": anomaly,
            "has_limit_like_move": has_limit_like_move,
            "has_turnover_spike": has_turnover_spike,
        },
        url=url,
        published_at=last["date"],
        confirmed=True,
    )
    return ([item] if item else []), []


def collect_market_news(query: str, fetch_text=fetch_url_text) -> tuple[list[dict[str, Any]], list[str]]:
    url = f"https://so.eastmoney.com/news/s?keyword={quote(query)}&collector=market-news"
    try:
        raw = fetch_text(url, headers={"Referer": "https://so.eastmoney.com/"})
    except Exception as exc:  # noqa: BLE001
        return [], [f"market_news:eastmoney_search failed: {exc}"]

    try:
        data = parse_jsonish(raw)
    except Exception:
        data = None
    rows = data.get("items", []) if isinstance(data, dict) else []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        append_item(
            items,
            evidence_item(
                "market_news:eastmoney_search",
                row.get("title") or row.get("Title") or row.get("headline") or "",
                raw=row,
                url=str(row.get("url") or row.get("Url") or ""),
                published_at=str(row.get("time") or row.get("date") or row.get("ShowTime") or ""),
            ),
        )
    if items:
        return items, []
    if "<title>" in raw.lower() or "搜索结果" in raw:
        item = evidence_item(
            "market_news:eastmoney_search",
            f"市场新闻源已检查: 东方财富新闻搜索页可达，关键词 {query}，未捕获结构化新闻条目",
            raw={"url": url, "captured_chars": min(len(raw), 5000)},
            url=url,
            coverage_only=True,
        )
        return ([item] if item else []), ["market_news:eastmoney_search structured results empty"]
    return [], ["market_news:eastmoney_search empty"]


def collect_flash_news(query: str, fetch_text=fetch_url_text) -> tuple[list[dict[str, Any]], list[str]]:
    url = f"https://kuaixun.eastmoney.com/?collector=flash-news&keyword={quote(query)}"
    try:
        raw = fetch_text(url, headers={"Referer": "https://kuaixun.eastmoney.com/"})
    except Exception as exc:  # noqa: BLE001
        return [], [f"flash_news:eastmoney_kuaixun failed: {exc}"]

    try:
        data = parse_jsonish(raw)
    except Exception:
        data = None
    rows = data.get("items", []) if isinstance(data, dict) else []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        append_item(
            items,
            evidence_item(
                "flash_news:eastmoney_kuaixun",
                row.get("title") or row.get("Title") or row.get("headline") or "",
                raw=row,
                url=str(row.get("url") or row.get("Url") or ""),
                published_at=str(row.get("time") or row.get("date") or row.get("ShowTime") or ""),
            ),
        )
    if items:
        return items, []
    if "全球财经快讯" in raw or "7*24" in raw or "7x24" in raw:
        item = evidence_item(
            "flash_news:eastmoney_kuaixun",
            f"7x24快讯源已检查: 东方财富全球财经快讯页面可达，关键词 {query}，未捕获结构化快讯条目",
            raw={"url": url, "captured_chars": min(len(raw), 5000)},
            url=url,
            coverage_only=True,
        )
        return ([item] if item else []), ["flash_news:eastmoney_kuaixun structured results empty"]
    return [], ["flash_news:eastmoney_kuaixun empty"]


def collect_builtin_sources(query: str, market: str, fetch_text=fetch_url_text) -> tuple[list[dict[str, Any]], list[str]]:
    market_upper = market.upper()
    if market_upper not in {"A", "AUTO"}:
        return [], [f"builtin collectors currently support A-share only; market={market}"]

    resolved, missing = resolve_a_share(query, fetch_text=fetch_text)
    if not resolved:
        return [], missing

    items: list[dict[str, Any]] = []
    for collector in [
        collect_eastmoney_announcements,
        collect_sina_quote,
        collect_eastmoney_kline,
    ]:
        got, miss = collector(resolved, fetch_text=fetch_text)
        items.extend(got)
        missing.extend(miss)

    for collector in [collect_market_news, collect_flash_news]:
        got, miss = collector(resolved.get("name") or query, fetch_text=fetch_text)
        items.extend(got)
        missing.extend(miss)

    return items, missing


def load_extra_json_files(paths: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    missing: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            missing.append(f"extra JSON file not found: {p}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            missing.append(f"extra JSON parse failed: {p}: {exc}")
            continue
        rows = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("headline") or row.get("text") or "").strip()
            source = str(row.get("source") or "extra_json")
            if not title:
                continue
            cats = classify_event(title)
            items.append(
                {
                    "id": stable_id(source + title),
                    "source": source,
                    "title": title[:260],
                    "raw": row,
                    "event_categories": cats,
                    "reliability": int(row.get("reliability") or source_reliability(source)),
                    "confirmed": bool(row.get("confirmed", False)),
                    "captured_at": now_iso(),
                }
            )
    return items, missing


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title", ""))
        key = re.sub(r"\W+", "", title.lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def infer_source_coverage(items: list[dict[str, Any]], missing_sources: list[str]) -> dict[str, str]:
    def coverage_for(*needles: str) -> str:
        matched = [
            item
            for item in items
            if any(needle.lower() in str(item.get("source", "")).lower() for needle in needles)
        ]
        if any(not item.get("coverage_only") for item in matched):
            return "covered"
        if matched:
            return "partial"
        return "missing"

    price_volume_status = coverage_for("price_volume", "kline", "quote", "fund_flow")

    return {
        "official_disclosure": coverage_for("official", "exchange", "cninfo", "sec", "hkex", "disclosure"),
        "market_news": coverage_for("market_news", "headline"),
        "flash_news": coverage_for("flash", "7x24"),
        "policy_industry": "covered" if any("industry_policy" in x.get("event_categories", []) for x in items) else "partial",
        "social_sentiment": coverage_for("social", "forum", "xueqiu", "guba"),
        "price_volume_anomaly": "not_checked" if price_volume_status == "missing" else price_volume_status,
        "collector_errors": "present" if missing_sources else "none",
    }


def infer_time_coverage(items: list[dict[str, Any]]) -> dict[str, str]:
    # MVP cannot reliably parse every source timestamp. Mark windows as partial
    # when at least one item exists; downstream must still inspect source dates.
    if not items:
        return {"24h": "missing", "72h": "missing", "7d": "missing", "30d": "missing", "90d": "missing"}
    return {"24h": "partial", "72h": "partial", "7d": "partial", "30d": "partial", "90d": "partial"}


def detect_price_volume_anomalies(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    joined = "\n".join(str(x.get("title", "")) for x in items)
    anomaly_terms = ["异动", "放量", "成交量", "涨停", "跌停", "大涨", "大跌", "资金流", "volume", "spike"]
    if any(term.lower() in joined.lower() for term in anomaly_terms):
        news_terms = ["公告", "新闻", "快讯", "政策", "中标", "订单", "回购", "减持", "增持"]
        matched_news = any(term in joined for term in news_terms)
        anomalies.append(
            {
                "type": "text_detected_possible_anomaly",
                "detail": "Captured text contains price/volume/fund-flow anomaly terms.",
                "matched_news": matched_news,
                "risk": "medium" if matched_news else "high",
            }
        )
    return anomalies


def detect_price_volume_anomalies_v2(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    has_explanatory_source = any(
        "official" in str(item.get("source", "")).lower()
        or "market_news" in str(item.get("source", "")).lower()
        or "flash_news" in str(item.get("source", "")).lower()
        for item in items
    )

    for item in items:
        raw = item.get("raw")
        source = str(item.get("source", ""))
        if "price_volume" in source and isinstance(raw, dict) and raw.get("anomaly"):
            anomalies.append(
                {
                    "type": "structured_price_volume_anomaly",
                    "source": source,
                    "detail": item.get("title", ""),
                    "matched_news": has_explanatory_source,
                    "risk": "medium" if has_explanatory_source else "high",
                    "raw": raw,
                }
            )

    joined = "\n".join(str(x.get("title", "")) for x in items)
    anomaly_terms = [
        "异常",
        "异动",
        "放量",
        "成交额",
        "换手",
        "涨停",
        "跌停",
        "大涨",
        "大跌",
        "资金流",
        "volume",
        "spike",
    ]
    if any(term.lower() in joined.lower() for term in anomaly_terms):
        news_terms = ["公告", "新闻", "快讯", "政策", "中标", "订单", "回购", "减持", "增持"]
        matched_news = any(term in joined for term in news_terms)
        if not anomalies:
            anomalies.append(
                {
                    "type": "text_detected_possible_anomaly",
                    "detail": "Captured text contains price/volume/fund-flow anomaly terms.",
                    "matched_news": matched_news,
                    "risk": "medium" if matched_news else "high",
                }
            )
    return anomalies


def compute_pack(query: str, market: str, items: list[dict[str, Any]], missing_sources: list[str]) -> dict[str, Any]:
    source_coverage = infer_source_coverage(items, missing_sources)
    time_coverage = infer_time_coverage(items)
    material_events = [x for x in items if x.get("event_categories")]
    high_material = [
        x for x in material_events
        if any(cat in HIGH_IMPACT_CATEGORIES for cat in x.get("event_categories", []))
    ]
    unconfirmed_events = [x for x in material_events if not x.get("confirmed")]
    price_volume_anomalies = detect_price_volume_anomalies_v2(items)

    score = 100
    cap = 8
    status = "PASS"

    if source_coverage["official_disclosure"] != "covered":
        score -= 25
        cap = min(cap, 5)
        status = "WARN"
    if source_coverage["market_news"] != "covered":
        score -= 20
        cap = min(cap, 6)
        status = "WARN"
    if source_coverage["flash_news"] != "covered":
        score -= 15
        cap = min(cap, 6)
        status = "WARN"
    if source_coverage["social_sentiment"] != "covered":
        score -= 10
        cap = min(cap, 7)
    if source_coverage["price_volume_anomaly"] == "not_checked":
        score -= 10
        cap = min(cap, 7)
    if missing_sources:
        score -= min(20, 2 * len(missing_sources))
    if any(a.get("risk") == "high" for a in price_volume_anomalies):
        cap = min(cap, 4)
        status = "WARN"
    if high_material and unconfirmed_events:
        cap = min(cap, 5)
        status = "WARN"
    if not items:
        score = 0
        cap = 2
        status = "BLOCK"
    if score < 40:
        status = "BLOCK"

    score = max(0, min(100, score))

    return {
        "ticker_or_query": query,
        "market": market,
        "audit_time": now_iso(),
        "windows": ["24h", "72h", "7d", "30d", "90d"],
        "evidence_status": status,
        "coverage_score": score,
        "confidence_cap": cap,
        "source_coverage": source_coverage,
        "time_coverage": time_coverage,
        "material_events": material_events[:80],
        "unconfirmed_events": unconfirmed_events[:80],
        "conflicts": [],
        "price_volume_anomalies": price_volume_anomalies,
        "missing_sources": missing_sources,
        "downstream_instructions": [
            "Start final report with evidence_status, coverage_score, and confidence_cap.",
            "Do not exceed confidence_cap.",
            "Discuss material_events before technical or valuation conclusions.",
            "Do not say no major news unless official_disclosure, market_news, and flash_news are covered.",
            "If official_disclosure is missing, avoid strong BUY/SELL language.",
            "If price/volume anomaly is unexplained, mark information-gap risk.",
            "Include a section: 哪些新增信息会推翻当前结论.",
        ],
        "items": items[:300],
    }


def md_table(mapping: dict[str, Any]) -> list[str]:
    lines = ["| Key | Value |", "|---|---|"]
    for key, value in mapping.items():
        lines.append(f"| {key} | {value} |")
    return lines


def write_markdown(pack: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# News Evidence Gate · {pack['ticker_or_query']}")
    lines.append("")
    lines.append("## 0. Audit Summary")
    lines.append("")
    lines.extend(md_table({
        "Audit Time": pack["audit_time"],
        "Evidence Status": pack["evidence_status"],
        "Coverage Score": f"{pack['coverage_score']} / 100",
        "Confidence Cap": f"{pack['confidence_cap']} / 10",
        "Market": pack["market"],
    }))
    lines.append("")
    lines.append("## 1. Source Coverage")
    lines.append("")
    lines.extend(md_table(pack["source_coverage"]))
    lines.append("")
    lines.append("## 2. Time Coverage")
    lines.append("")
    lines.extend(md_table(pack["time_coverage"]))
    lines.append("")
    lines.append("## 3. Material Events")
    lines.append("")
    if pack["material_events"]:
        for event in pack["material_events"][:30]:
            cats = ", ".join(event.get("event_categories", []))
            lines.append(f"- [{event.get('source')}] {event.get('title')} ({cats})")
    else:
        lines.append("- No material event captured by available sources.")
    lines.append("")
    lines.append("## 4. Unconfirmed Events")
    lines.append("")
    if pack["unconfirmed_events"]:
        for event in pack["unconfirmed_events"][:30]:
            cats = ", ".join(event.get("event_categories", []))
            lines.append(f"- [{event.get('source')}] {event.get('title')} ({cats})")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## 5. Conflicts")
    lines.append("")
    if pack["conflicts"]:
        for conflict in pack["conflicts"]:
            lines.append(f"- {conflict}")
    else:
        lines.append("- None detected by MVP logic.")
    lines.append("")
    lines.append("## 6. Price / Volume Anomalies")
    lines.append("")
    if pack["price_volume_anomalies"]:
        for anomaly in pack["price_volume_anomalies"]:
            lines.append(f"- {json.dumps(anomaly, ensure_ascii=False)}")
    else:
        lines.append("- No anomaly detected by MVP text logic, or anomaly check not available.")
    lines.append("")
    lines.append("## 7. Missing Sources")
    lines.append("")
    if pack["missing_sources"]:
        for source in pack["missing_sources"]:
            lines.append(f"- {source}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## 8. Downstream Instructions")
    lines.append("")
    for inst in pack["downstream_instructions"]:
        lines.append(f"- {inst}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Ticker or company name")
    parser.add_argument("--market", default="auto", help="A/HK/US/auto")
    parser.add_argument("--stock-home", default=os.environ.get("STOCK_SKILLS_HOME", ""), help="Path to tetap/stock-skills")
    parser.add_argument("--out", default="./.cache/news-evidence-gate/default", help="Output directory")
    parser.add_argument("--extra-json", action="append", default=[], help="Extra JSON evidence file")
    parser.add_argument("--demo", action="store_true", help="Generate demo evidence without external sources")
    parser.add_argument("--fail-on-block", action="store_true", help="Exit with code 2 when evidence_status=BLOCK")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    missing: list[str] = []

    if args.demo:
        items.extend(demo_items(args.query))
    else:
        got, miss = collect_builtin_sources(args.query, args.market)
        items.extend(got)
        missing.extend(miss)

        if args.stock_home:
            got, miss = collect_from_stock_skills(Path(args.stock_home), args.query)
            items.extend(got)
            missing.extend(miss)
        elif not items:
            missing.append("STOCK_SKILLS_HOME not set and no builtin collectors succeeded")

    extra_items, extra_missing = load_extra_json_files(args.extra_json)
    items.extend(extra_items)
    missing.extend(extra_missing)

    items = dedupe(items)
    pack = compute_pack(args.query, args.market, items, missing)

    json_path = out_dir / "evidence_pack.json"
    md_path = out_dir / "evidence_pack.md"
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(pack, md_path)

    print(json.dumps({
        "evidence_status": pack["evidence_status"],
        "coverage_score": pack["coverage_score"],
        "confidence_cap": pack["confidence_cap"],
        "json": str(json_path),
        "markdown": str(md_path),
    }, ensure_ascii=False, indent=2))

    if args.fail_on_block and pack["evidence_status"] == "BLOCK":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
