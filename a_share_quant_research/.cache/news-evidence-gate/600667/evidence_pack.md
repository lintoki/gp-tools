# News Evidence Gate · 600667

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-12T23:23:46 |
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

- {"type": "structured_price_volume_anomaly", "source": "price_volume:eastmoney_kline", "detail": "K线异常: 600667 2025-01-02至2026-07-10 收盘涨幅288.02% 最高32.10 最新收盘25.26 最新换手20.70% 最新成交额116.44亿", "matched_news": true, "risk": "medium", "raw": {"url": "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600667&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&beg=20250101&end=20500101", "first": {"date": "2025-01-02", "open": 6.78, "close": 6.51, "high": 6.82, "low": 6.44, "volume": 451672.0, "amount": 307698915.0, "amplitude": 5.62, "pct": -3.7, "change": -0.25, "turnover": 2.14}, "last": {"date": "2026-07-10", "open": 26.82, "close": 25.26, "high": 27.95, "low": 25.24, "volume": 4329362.0, "amount": 11644398633.0, "amplitude": 10.32, "pct": -3.84, "change": -1.01, "turnover": 20.7}, "max": {"date": "2026-07-01", "open": 28.86, "close": 32.1, "high": 32.1, "low": 28.86, "volume": 4150707.0, "amount": 12988171255.0, "amplitude": 11.1, "pct": 10.01, "change": 2.92, "turnover": 19.85}, "period_return_pct": 288.01843317972356, "anomaly": true, "has_limit_like_move": true, "has_turnover_spike": true}}

## 7. Missing Sources

- price_volume:sina_quote empty
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
