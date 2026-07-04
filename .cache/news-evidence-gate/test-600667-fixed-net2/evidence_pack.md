# News Evidence Gate · 600667

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-04T20:10:47 |
| Evidence Status | WARN |
| Coverage Score | 49 / 100 |
| Confidence Cap | 6 / 10 |
| Market | A |

## 1. Source Coverage

| Key | Value |
|---|---|
| official_disclosure | covered |
| market_news | partial |
| flash_news | partial |
| policy_industry | partial |
| social_sentiment | missing |
| price_volume_anomaly | covered |
| collector_errors | present |

## 2. Time Coverage

| Key | Value |
|---|---|
| 24h | partial |
| 72h | partial |
| 7d | partial |
| 30d | partial |
| 90d | partial |

## 3. Material Events

- [official_disclosure:eastmoney_announcements] 2026-06-26 太极实业:股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-06-23 太极实业:2025年年度权益分派实施公告 (dividend)
- [official_disclosure:eastmoney_announcements] 2026-06-19 太极实业:股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-06-18 太极实业:关于完成法定代表人工商变更登记的公告 (management_change)
- [official_disclosure:eastmoney_announcements] 2026-06-13 太极实业:关于选举董事长的公告 (key_person_event, management_change)
- [official_disclosure:eastmoney_announcements] 2026-06-05 太极实业:股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-06-03 太极实业:关于子公司十一科技涉及重大诉讼的进展公告 (litigation)
- [official_disclosure:eastmoney_announcements] 2026-05-28 太极实业:关于董事长辞职暨补选董事的公告 (key_person_event, management_change)
- [official_disclosure:eastmoney_announcements] 2026-05-14 太极实业:股票交易异常波动的公告 (trading_anomaly)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- {"type": "text_detected_possible_anomaly", "detail": "Captured text contains price/volume/fund-flow anomaly terms.", "matched_news": true, "risk": "medium"}

## 7. Missing Sources

- price_volume:eastmoney_kline failed: urlopen failed: Remote end closed connection without response; curl fallback failed code=56: curl: (56) schannel: server closed abruptly (missing close_notify)

- market_news:eastmoney_search structured results empty
- flash_news:eastmoney_kuaixun structured results empty

## 8. Downstream Instructions

- Start final report with evidence_status, coverage_score, and confidence_cap.
- Do not exceed confidence_cap.
- Discuss material_events before technical or valuation conclusions.
- Do not say no major news unless official_disclosure, market_news, and flash_news are covered.
- If official_disclosure is missing, avoid strong BUY/SELL language.
- If price/volume anomaly is unexplained, mark information-gap risk.
- Include a section: 哪些新增信息会推翻当前结论.
