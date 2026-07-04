# News Evidence Gate · 中船特气

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

- [official_disclosure:eastmoney_announcements] 2026-06-26 中船特气:中船特气关于股票交易停牌核查结果暨复牌的公告 (trading_halt)
- [official_disclosure:eastmoney_announcements] 2026-06-23 中船特气:中船特气关于股票交易风险提示暨停牌核查的公告 (trading_halt)
- [official_disclosure:eastmoney_announcements] 2026-06-12 中船特气:中船特气股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-06-11 中船特气:中船特气2025年年度权益分派实施公告 (dividend)
- [official_disclosure:eastmoney_announcements] 2026-06-09 中船特气:中船特气股票交易异常波动暨严重异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-05-29 中船特气:中船特气股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-05-16 中船特气:中船特气股票交易严重异常波动公告 (trading_anomaly)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- {"type": "structured_price_volume_anomaly", "source": "price_volume:sina_quote", "detail": "行情: 中船特气 688146 最新330.14 涨跌幅-9.55% 最高369.91 最低319.30 振幅13.87% 成交额44.72亿 时间2026-07-03 15:34:59", "matched_news": true, "risk": "medium", "raw": {"url": "https://hq.sinajs.cn/list=sh688146", "fields": ["中船特气", "358.000", "365.000", "330.140", "369.910", "319.300", "330.140", "330.250", "13028575", "4472339230.000", "4493", "330.140", "30422", "330.130", "38666", "330.120", "2132", "330.100", "3742", "330.080", "500", "330.250", "200", "330.290", "9567", "330.300", "1194", "330.400", "496", "330.500", "2026-07-03", "15:34:59", "00", "D|5890|1944524.60"], "pct": -9.550684931506847, "amplitude": 13.865753424657537, "amount": 4472339230.0, "anomaly": true}}

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
