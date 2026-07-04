# News Evidence Gate · 华工科技

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-04T20:30:16 |
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

- [official_disclosure:eastmoney_announcements] 2026-06-05 华工科技:2025年年度权益分派实施公告 (dividend)
- [official_disclosure:eastmoney_announcements] 2026-05-21 华工科技:股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-04-14 华工科技:2026年第一季度业绩预告 (earnings_revision)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- {"type": "structured_price_volume_anomaly", "source": "price_volume:sina_quote", "detail": "行情: 华工科技 000988 最新153.95 涨跌幅-1.44% 最高159.86 最低149.90 振幅6.38% 成交额89.71亿 时间2026-07-03 15:00:00", "matched_news": true, "risk": "medium", "raw": {"url": "https://hq.sinajs.cn/list=sz000988", "fields": ["华工科技", "151.690", "156.200", "153.950", "159.860", "149.900", "153.940", "153.950", "57738731", "8970631282.430", "2300", "153.940", "3700", "153.930", "40800", "153.920", "1400", "153.910", "16700", "153.900", "26408", "153.950", "25300", "153.960", "7202", "153.970", "5000", "153.980", "1000", "153.990", "2026-07-03", "15:00:00", "00"], "pct": -1.440460947503197, "amplitude": 6.376440460947509, "amount": 8970631282.43, "anomaly": true}}

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
