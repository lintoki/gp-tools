# News Evidence Gate · DEMO

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-04T15:26:15 |
| Evidence Status | PASS |
| Coverage Score | 100 / 100 |
| Confidence Cap | 8 / 10 |
| Market | A |

## 1. Source Coverage

| Key | Value |
|---|---|
| official_disclosure | covered |
| market_news | covered |
| flash_news | covered |
| policy_industry | covered |
| social_sentiment | covered |
| price_volume_anomaly | covered |
| collector_errors | none |

## 2. Time Coverage

| Key | Value |
|---|---|
| 24h | partial |
| 72h | partial |
| 7d | partial |
| 30d | partial |
| 90d | partial |

## 3. Material Events

- [official_disclosure_demo] 官方公告：DEMO 发布回购进展公告，当前无停牌或退市风险提示。 (delisting_risk, shareholder_change, trading_halt)
- [flash_news_demo] 7x24快讯：相关产业政策发布，市场关注龙头公司订单弹性。 (industry_policy, major_contract)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- {"type": "text_detected_possible_anomaly", "detail": "Captured text contains price/volume/fund-flow anomaly terms.", "matched_news": true, "risk": "medium"}

## 7. Missing Sources

- None

## 8. Downstream Instructions

- Start final report with evidence_status, coverage_score, and confidence_cap.
- Do not exceed confidence_cap.
- Discuss material_events before technical or valuation conclusions.
- Do not say no major news unless official_disclosure, market_news, and flash_news are covered.
- If official_disclosure is missing, avoid strong BUY/SELL language.
- If price/volume anomaly is unexplained, mark information-gap risk.
- Include a section: 哪些新增信息会推翻当前结论.
