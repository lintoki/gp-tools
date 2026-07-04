# News Evidence Gate · 600667

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-04T20:08:46 |
| Evidence Status | BLOCK |
| Coverage Score | 0 / 100 |
| Confidence Cap | 2 / 10 |
| Market | A |

## 1. Source Coverage

| Key | Value |
|---|---|
| official_disclosure | missing |
| market_news | missing |
| flash_news | missing |
| policy_industry | partial |
| social_sentiment | missing |
| price_volume_anomaly | not_checked |
| collector_errors | present |

## 2. Time Coverage

| Key | Value |
|---|---|
| 24h | missing |
| 72h | missing |
| 7d | missing |
| 30d | missing |
| 90d | missing |

## 3. Material Events

- No material event captured by available sources.

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- No anomaly detected by MVP text logic, or anomaly check not available.

## 7. Missing Sources

- official_disclosure:eastmoney_announcements failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>
- price_volume:sina_quote failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>
- price_volume:eastmoney_kline failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>
- market_news:eastmoney_search failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>
- flash_news:eastmoney_kuaixun failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>
- STOCK_SKILLS_HOME not set and no builtin collectors succeeded

## 8. Downstream Instructions

- Start final report with evidence_status, coverage_score, and confidence_cap.
- Do not exceed confidence_cap.
- Discuss material_events before technical or valuation conclusions.
- Do not say no major news unless official_disclosure, market_news, and flash_news are covered.
- If official_disclosure is missing, avoid strong BUY/SELL language.
- If price/volume anomaly is unexplained, mark information-gap risk.
- Include a section: 哪些新增信息会推翻当前结论.
