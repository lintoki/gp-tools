# Source Matrix

## A-share source groups

| Group | Examples | Reliability | Required? | Notes |
|---|---|---:|---:|---|
| Official disclosure | 巨潮资讯、上交所、深交所、北交所、证监会、交易所问询函 | 5 | Yes | Missing official disclosure caps confidence at 5/10. |
| Market news | 东方财富、财联社、证券时报、上证报、中证报等 | 4 | Yes | Must record retrieval time and headline timestamp if available. |
| Flash news | 7x24 快讯、市场要闻 | 3 | Yes | Useful for intraday events and sector catalysts. |
| Policy / industry | 部委、协会、地方政府、产业链官方数据 | 4 | Conditional | Required when industry/policy is core to thesis. |
| Social sentiment | 雪球、股吧、淘股吧、社交平台 | 2 | Optional | Cannot alone support core conclusion. |
| Price / volume anomaly | K线、成交量、换手、资金流、板块偏离 | 4 | Yes | If anomaly cannot be explained by news, cap confidence at 4/10. |

## HK source groups

| Group | Examples | Reliability | Required? |
|---|---|---:|---:|
| Official disclosure | HKEXnews、公司 IR | 5 | Yes |
| Market news | 主流财经媒体、券商事件摘要 | 4 | Yes |
| Southbound / flow | 港股通、成交额、资金流 | 3 | Conditional |

## US source groups

| Group | Examples | Reliability | Required? |
|---|---|---:|---:|
| Official disclosure | SEC EDGAR、公司 IR、8-K、10-Q、10-K、Form 4 | 5 | Yes |
| Market news | Reuters、Bloomberg、CNBC、company press releases | 4 | Yes |
| Social sentiment | Reddit、StockTwits、X 等 | 2 | Optional |
| Options / flow | Option chain, OI, volume, unusual option activity | 3 | Conditional |
