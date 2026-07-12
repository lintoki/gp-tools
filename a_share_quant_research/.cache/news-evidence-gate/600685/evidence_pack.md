# News Evidence Gate · 600685

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-12T23:33:02 |
| Evidence Status | BLOCK |
| Coverage Score | 37 / 100 |
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
| price_volume_anomaly | not_checked |
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

- [official_disclosure:eastmoney_announcements] 2026-07-11 中船防务:中船防务2026年半年度业绩预增公告 (earnings_revision)
- [official_disclosure:eastmoney_announcements] 2026-07-09 中船防务:中船防务2025年年度权益分派实施公告 (dividend)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- No anomaly detected by MVP text logic, or anomaly check not available.

## 7. Missing Sources

- price_volume:sina_quote empty
- price_volume:eastmoney_kline failed: urlopen failed: [SSL] record layer failure (_ssl.c:2580); curl fallback failed code=56: curl: (56) schannel: failed to read data from server: SEC_E_DECRYPT_FAILURE (0x80090330) - 无法解密指定的数据。

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
