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
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


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
    if any(x in s for x in ["market_news", "news", "eastmoney", "headline"]):
        return 4
    if any(x in s for x in ["flash", "7x24"]):
        return 3
    if any(x in s for x in ["social", "forum", "xueqiu", "guba"]):
        return 2
    return 3


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
    sources = " ".join(sorted(set(str(x.get("source", "")) for x in items))).lower()

    def covered(*needles: str) -> bool:
        return any(n.lower() in sources for n in needles)

    return {
        "official_disclosure": "covered" if covered("official", "exchange", "cninfo", "sec", "hkex", "disclosure") else "missing",
        "market_news": "covered" if covered("market_news", "news", "headline", "eastmoney") else "missing",
        "flash_news": "covered" if covered("flash", "7x24") else "missing",
        "policy_industry": "covered" if any("industry_policy" in x.get("event_categories", []) for x in items) else "partial",
        "social_sentiment": "covered" if covered("social", "forum", "xueqiu", "guba") else "missing",
        "price_volume_anomaly": "covered" if covered("price", "volume", "kline", "quote", "fund_flow") else "not_checked",
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


def compute_pack(query: str, market: str, items: list[dict[str, Any]], missing_sources: list[str]) -> dict[str, Any]:
    source_coverage = infer_source_coverage(items, missing_sources)
    time_coverage = infer_time_coverage(items)
    material_events = [x for x in items if x.get("event_categories")]
    high_material = [
        x for x in material_events
        if any(cat in HIGH_IMPACT_CATEGORIES for cat in x.get("event_categories", []))
    ]
    unconfirmed_events = [x for x in material_events if not x.get("confirmed")]
    price_volume_anomalies = detect_price_volume_anomalies(items)

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
        if args.stock_home:
            got, miss = collect_from_stock_skills(Path(args.stock_home), args.query)
            items.extend(got)
            missing.extend(miss)
        else:
            missing.append("STOCK_SKILLS_HOME not set and --stock-home not provided; skipped stock-skills collectors")

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
