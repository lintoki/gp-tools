---
name: news-evidence-gate
description: >-
  Use before any stock analysis, stock recommendation, BUY/SELL/HOLD diagnosis,
  sector selection, theme research, or event-driven market judgment. Audits
  recent company announcements, exchange filings, regulator disclosures, market
  news, flash news, policy events, social sentiment, and price/volume anomalies.
  Produces an evidence pack, missing-source warnings, material-event list,
  conflicts, and confidence cap. This skill does not make final investment
  judgments.
---

# News Evidence Gate

## Purpose

This skill is a mandatory pre-analysis gate for stock research. It does not decide
whether to buy, sell, hold, or avoid. It audits whether the information base is
complete enough for another stock-analysis skill to produce a reliable report.

## Required Inputs

- Ticker or company name
- Market: A / HK / US / auto
- Analysis objective
- Time windows: default 24h, 72h, 7d, 30d, 90d
- Optional path to `tetap/stock-skills` through `STOCK_SKILLS_HOME`

## Mandatory Workflow

1. Normalize ticker and company name.
2. Collect evidence from all configured source groups.
3. Deduplicate by title, URL, timestamp, source, and semantic similarity where possible.
4. Classify every evidence item into material-event categories.
5. Detect missing, stale, failed, or low-reliability source groups.
6. Check price/volume/fund-flow anomaly versus available news coverage.
7. Assign coverage score, evidence status, and confidence cap.
8. Write:
   - `evidence_pack.json`
   - `evidence_pack.md`
9. Return a handoff summary for the downstream analysis skill.

## Source Groups

The audit must try these groups:

1. Official disclosures:
   - company announcements
   - exchange announcements
   - regulator / official portal
2. Market news:
   - financial news
   - 7x24 flash news
   - sector news
3. Policy and industry:
   - policy events
   - industry association
   - supply chain events
4. Social / sentiment:
   - investor forums
   - social platforms
   - discussion heat
5. Market anomaly:
   - price change
   - volume spike
   - turnover spike
   - fund-flow anomaly

## Hard Rules

- Never claim "no major news" unless official disclosures, market news, and flash news were all checked.
- If official disclosure sources fail or are not implemented, downstream confidence must be capped at 5/10.
- If price or volume is abnormal but no explanatory news is found, mark `information_gap_risk = high` and cap downstream confidence at 4/10.
- If one material event appears only in one low-reliability source, mark it as `unconfirmed`.
- If source groups conflict, preserve both versions and require downstream analysis to discuss the conflict.
- Do not invent dates, prices, announcements, filings, news, or social sentiment.
- Do not place trades or connect to brokerage APIs.

## Execution

Preferred command:

```bash
python .agents/skills/news-evidence-gate/scripts/news_audit.py \
  --query "<ticker-or-company>" \
  --market "<A|HK|US|auto>" \
  --stock-home "$STOCK_SKILLS_HOME" \
  --out "./.cache/news-evidence-gate/<ticker-or-company>"
```

Demo command:

```bash
python .agents/skills/news-evidence-gate/scripts/news_audit.py \
  --query DEMO \
  --market A \
  --demo \
  --out /tmp/news-evidence-demo
```

## Output Contract

Return a JSON object matching `templates/evidence_pack.schema.json`.

Required summary fields:

- `evidence_status`: PASS / WARN / BLOCK
- `coverage_score`: 0-100
- `confidence_cap`: 0-10
- `source_coverage`
- `time_coverage`
- `material_events`
- `unconfirmed_events`
- `conflicts`
- `price_volume_anomalies`
- `missing_sources`
- `downstream_instructions`

## Handoff Rules

After producing the evidence pack, instruct the downstream analysis skill:

- Use only facts from `evidence_pack` or explicitly cited/queried sources.
- Start the final report with data coverage and confidence cap.
- Do not exceed the `confidence_cap`.
- Discuss material events and missing-source risks before giving a conclusion.
- If official disclosure is missing, avoid strong BUY/SELL language.
- Include a section: "哪些新增信息会推翻当前结论".
