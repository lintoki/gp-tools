# News Evidence Gate · 南大光电

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-04T20:44:42 |
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
| policy_industry | covered |
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

- [official_disclosure:eastmoney_announcements] 2026-06-29 南大光电:关于持股5%以上股东股份减持计划完成的公告 (shareholder_change)
- [official_disclosure:eastmoney_announcements] 2026-05-11 南大光电:2025年度权益分派实施公告 (dividend)
- [official_disclosure:eastmoney_announcements] 2026-04-14 南大光电:关于董事股份减持计划完成的公告 (shareholder_change)
- [official_disclosure:eastmoney_announcements] 2026-04-10 南大光电:关于会计政策变更的公告 (industry_policy)
- [official_disclosure:eastmoney_announcements] 2026-04-10 南大光电:中审亚太关于江苏南大光电材料股份有限公司内部控制审计报告 (fraud_investigation)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- {"type": "structured_price_volume_anomaly", "source": "price_volume:sina_quote", "detail": "行情: 南大光电 300346 最新80.18 涨跌幅-9.68% 最高88.66 最低79.33 振幅10.51% 成交额91.84亿 时间2026-07-03 16:29:00", "matched_news": true, "risk": "medium", "raw": {"url": "https://hq.sinajs.cn/list=sz300346", "fields": ["南大光电", "85.580", "88.770", "80.180", "88.660", "79.330", "80.170", "80.180", "111938493", "9183529530.560", "9800", "80.170", "12300", "80.160", "27300", "80.150", "4100", "80.140", "5100", "80.130", "70036", "80.180", "53300", "80.190", "20300", "80.200", "2400", "80.210", "7200", "80.220", "2026-07-03", "16:29:00", "00", "D|8500|681530.000"], "pct": -9.676692576320821, "amplitude": 10.51030753632984, "amount": 9183529530.56, "anomaly": true}}

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
