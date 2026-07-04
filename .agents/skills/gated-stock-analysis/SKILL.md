---
name: gated-stock-analysis
description: >-
  Use for reliable stock analysis when the user wants a final answer based on
  complete news, announcements, market events, social sentiment, price anomalies,
  and verified evidence. Always run news-evidence-gate first, then hand the
  evidence pack to the appropriate downstream stock-analysis skill such as
  stock-main, $stock from tetap/stock-skills, china-stock-research-orchestrator,
  or stockaskill.
---

# Gated Stock Analysis

## Purpose

This skill orchestrates a two-stage stock research workflow:

1. Evidence audit with `news-evidence-gate`.
2. Final analysis with the most suitable downstream stock-analysis skill.

## Required Workflow

1. Identify ticker/company, market, and user objective.
2. Run evidence audit:

```bash
python .agents/skills/news-evidence-gate/scripts/news_audit.py \
  --query "<ticker-or-company>" \
  --market "<A|HK|US|auto>" \
  --out "./.cache/news-evidence-gate/<ticker-or-company>"
```

Only pass `--stock-home "$STOCK_SKILLS_HOME"` when an external `tetap/stock-skills`
checkout is actually configured. The evidence gate has built-in A-share collectors
and must not block solely because `STOCK_SKILLS_HOME` is absent.

3. Read:
   - `evidence_pack.json`
   - `evidence_pack.md`

4. If `evidence_status = BLOCK`:
   - Do not run a strong final stock analysis.
   - Return missing sources, confidence cap, and what must be checked manually.

5. If `evidence_status = WARN`:
   - Continue to downstream analysis only with conditional language.
   - Force downstream confidence not to exceed `confidence_cap`.
   - Final report must start with data coverage warnings.

6. If `evidence_status = PASS`:
   - Run downstream analysis normally.
   - Still include evidence coverage in the final report.

## Downstream Routing

- A-share tactical analysis, sector, hotspot, fund flow, technicals:
  use `stock-main` / `$stock` from `tetap/stock-skills`.
- A-share fundamental deep dive:
  use `china-stock-research-orchestrator` if installed.
- Quant scan, portfolio, backtest:
  use `stockaskill` if installed.

## Final Report Must Include

1. Evidence coverage table.
2. Material events found.
3. Missing or stale sources.
4. Conflicting reports.
5. Price/volume anomaly explanation.
6. Confidence cap.
7. Downstream analysis conclusion.
8. What news or disclosure would invalidate the conclusion.

## Prohibited Output

- Do not say "无重大利空/无重大利好" unless official disclosure, market news, and flash news are covered.
- Do not produce confidence above `confidence_cap`.
- Do not treat social-media rumors as confirmed facts.
- Do not ignore `missing_sources`.
- Do not place trades or connect to brokerage accounts.
