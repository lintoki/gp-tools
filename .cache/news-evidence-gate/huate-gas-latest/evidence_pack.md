# News Evidence Gate · 华特气体

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

- [official_disclosure:eastmoney_announcements] 2026-07-03 华特气体:广东信达律师事务所关于广东华特气体股份有限公司差异化分红事项的法律意见书 (dividend)
- [official_disclosure:eastmoney_announcements] 2026-07-03 华特气体:广东华特气体股份有限公司2025年年度权益分派实施公告 (dividend)
- [official_disclosure:eastmoney_announcements] 2026-06-24 华特气体:广东华特气体股份有限公司股票交易异常波动公告 (trading_anomaly)
- [official_disclosure:eastmoney_announcements] 2026-06-12 华特气体:广东华特气体股份有限公司2023年限制性股票激励计划部分第一类限制性股票回购注销实施公告 (shareholder_change)
- [official_disclosure:eastmoney_announcements] 2026-06-12 华特气体:北京金诚同达(深圳)律师事务所关于广东华特气体股份有限公司2023年限制性股票激励计划部分第一类限制性股票回购注销实施情况的法律意见书 (shareholder_change)
- [official_disclosure:eastmoney_announcements] 2026-06-12 华特气体:广东华特气体股份有限公司股东减持股份结果公告 (shareholder_change)
- [official_disclosure:eastmoney_announcements] 2026-06-11 华特气体:广东华特气体股份有限公司董事、高级管理人员减持股份结果公告 (shareholder_change)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- {"type": "structured_price_volume_anomaly", "source": "price_volume:sina_quote", "detail": "行情: 华特气体 688268 最新225.91 涨跌幅-9.27% 最高256.00 最低225.00 振幅12.45% 成交额23.90亿 时间2026-07-03 15:34:59", "matched_news": true, "risk": "medium", "raw": {"url": "https://hq.sinajs.cn/list=sh688268", "fields": ["华特气体", "246.660", "249.000", "225.910", "256.000", "225.000", "225.910", "225.940", "10217529", "2389944156.000", "18572", "225.910", "3151", "225.900", "200", "225.890", "600", "225.880", "1022", "225.870", "958", "225.940", "200", "225.980", "4514", "225.990", "4600", "226.000", "360", "226.130", "2026-07-03", "15:34:59", "00", "D|4252|960569.32"], "pct": -9.273092369477908, "amplitude": 12.449799196787147, "amount": 2389944156.0, "anomaly": true}}

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
