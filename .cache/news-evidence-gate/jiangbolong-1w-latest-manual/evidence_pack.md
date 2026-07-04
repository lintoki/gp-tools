# News Evidence Gate · 301308 江波龙 1周内最新新闻

## 0. Audit Summary

| Key | Value |
|---|---|
| Audit Time | 2026-07-04T20:35:52 |
| Evidence Status | WARN |
| Coverage Score | 43 / 100 |
| Confidence Cap | 6 / 10 |
| Market | A |

## 1. Source Coverage

| Key | Value |
|---|---|
| official_disclosure | covered |
| market_news | missing |
| flash_news | missing |
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

- [cninfo_official_disclosure] 江波龙2026年半年度业绩预告：2026年1月1日至6月30日预计营业收入220.00亿元至250.00亿元，归母净利润92.00亿元至110.00亿元，扣非净利润90.00亿元至105.00亿元 (earnings_revision)
- [cninfo_official_disclosure_boundary] 边界信息：江波龙董事李志雄股份减持计划实施完毕，2026年5月12日至6月25日减持2,399,924股，占目前总股本0.5673%，减持均价575.69元/股；公告日为2026年6月26日 (shareholder_change)

## 4. Unconfirmed Events

- None

## 5. Conflicts

- None detected by MVP logic.

## 6. Price / Volume Anomalies

- No anomaly detected by MVP text logic, or anomaly check not available.

## 7. Missing Sources

- official_disclosure:eastmoney_announcements failed: urlopen failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>; curl fallback failed code=7: curl: (7) Failed to connect to np-anotice-stock.eastmoney.com port 443 after 6 ms: Could not connect to server

- price_volume:sina_quote failed: urlopen failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>; curl fallback failed code=7: curl: (7) Failed to connect to hq.sinajs.cn port 443 after 6 ms: Could not connect to server

- price_volume:eastmoney_kline failed: urlopen failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>; curl fallback failed code=7: curl: (7) Failed to connect to push2his.eastmoney.com port 443 after 6 ms: Could not connect to server

- market_news:eastmoney_search failed: urlopen failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>; curl fallback failed code=7: curl: (7) Failed to connect to so.eastmoney.com port 443 after 5 ms: Could not connect to server

- flash_news:eastmoney_kuaixun failed: urlopen failed: <urlopen error [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。>; curl fallback failed code=7: curl: (7) Failed to connect to kuaixun.eastmoney.com port 443 after 5 ms: Could not connect to server

- STOCK_SKILLS_HOME not set and no builtin collectors succeeded

## 8. Downstream Instructions

- Start final report with evidence_status, coverage_score, and confidence_cap.
- Do not exceed confidence_cap.
- Discuss material_events before technical or valuation conclusions.
- Do not say no major news unless official_disclosure, market_news, and flash_news are covered.
- If official_disclosure is missing, avoid strong BUY/SELL language.
- If price/volume anomaly is unexplained, mark information-gap risk.
- Include a section: 哪些新增信息会推翻当前结论.
