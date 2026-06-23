# Tail Overnight Trader

尾盘隔夜策略筛选、纸面交易和复盘工具。

这个程序只做四件事：

- 按你执行命令的当下行情扫描 A 股候选。
- 把入选股票保存为扫描快照，也可以记录为纸面交易。
- 生成可直接打开的 HTML 报告，给出严格策略建议。
- 次日早盘按固定退出纪律复盘纸面交易。

它不会连接券商账户，不会自动下单，也不构成投资建议。

## 安装

建议 Python 3.9+。

```bash
cd /Users/zhihu/Documents/gp/gp-tools/tail_overnight_trader
python3 -m pip install -r requirements.txt
```

## 策略规则

程序把短视频文案里的尾盘隔夜策略落成可检查条件：

- 只看主板股票：`000/001/002/003/600/601/603/605` 开头。
- 剔除 ST 和退市风险名称。
- 当日涨幅在 `3%` 到 `5%`。
- 近 20 个交易日至少 1 次涨停，默认最多 3 次，避免过度妖股。
- 量比不低于 `1`。
- 换手率在 `5%` 到 `10%`。
- 总市值在 `50 亿` 到 `200 亿`。
- 个股涨幅强于你传入的大盘涨跌幅。
- 分时价格大部分时间在均价线上方。
- 14:30 后创日内新高，并出现贴近均价线但不跌破的回踩。

无法可靠量化的描述不会硬编，比如“主力是否在场”。程序只输出可观测原因和过滤原因。

## 扫描候选并打开 HTML

什么时候执行就按当时行情计算。策略本身仍然严格：如果没有 14:30 后分时、涨幅超过 5%、尾盘没有创新高回踩，报告会直接建议空仓或不新增仓位。

```bash
python3 run_report.py
```

这个默认命令只生成报告，不记录纸面交易，不自动下单。高级参数入口仍然保留：

```bash
python3 -m tail_trader.cli scan --market-change-pct 0.8
```

高级参数说明：

- `--market-change-pct`：大盘涨跌幅，用来判断个股是否强于大盘。
- `--top 20`：打印前 20 个结果。
- `--max-prefilter 80`：最多对 80 只预筛股票拉取日线和分时，避免 AKShare 请求过多。

扫描结果会保存到：

```text
data/scans/YYYYMMDD-HHMMSS.json
```

HTML 报告会保存到：

```text
data/reports/YYYYMMDD-HHMMSS.html
```

macOS 可以直接打开：

```bash
open data/reports/YYYYMMDD-HHMMSS.html
```

本地生成文件会自动控制体积：

- `data/scans/*.json` 最多保留最近 10 个。
- `data/reports/*.html` 最多保留最近 10 个。
- `data/reviews/*.md` 最多保留最近 10 个。
- `data/backtests/*.html` 和 `data/backtests/*.json` 各最多保留最近 10 个。
- `data/trades.jsonl` 最多保留最近 10 条纸面交易记录。

每次生成新文件前会先清理同类旧文件，避免目录越来越大。

## 固定区间回测

已提供一个无参数脚本，回测 `2026-01-01` 到 `2026-01-07`：

```bash
python3 backtest_20260101_20260107.py
```

输出位置：

```text
data/backtests/20260101-20260107.html
data/backtests/20260101-20260107.json
```

注意这个脚本是本地快速抽样验证：每个交易日最多检查 80 只主板股票。历史尾盘形态使用 Baostock 5 分钟 K 线近似，历史量比用当日成交量 / 前 5 个交易日日均成交量近似，历史总市值用东方财富当前总市值按历史收盘价缩放估算。报告里会写明这些口径，不把它当成全市场精确胜率。

## 记录纸面交易

扫描时加 `--record`，会把入选靠前的候选写入纸面交易流水：

```bash
python3 -m tail_trader.cli scan --market-change-pct 0.8 --record --record-top 1 --shares 100
```

纸面交易文件：

```text
data/trades.jsonl
```

## 次日复盘

次日早盘后运行：

```bash
python3 -m tail_trader.cli review --date 2026-06-24
```

默认退出纪律：

- 次日早盘先到 `+2%`，按止盈价退出。
- 先到 `-2%`，按止损价退出。
- 到 10:30 还没有触发止盈或止损，按 10:30 前最后一个分时收盘价退出。

可调整：

```bash
python3 -m tail_trader.cli review --date 2026-06-24 --target-profit-pct 1.5 --stop-loss-pct 2.0
```

复盘报告会保存到：

```text
data/reviews/YYYY-MM-DD.md
```

## 测试

```bash
cd /Users/zhihu/Documents/gp/gp-tools/tail_overnight_trader
python3 -m unittest discover -s tests -v
```

## 数据源

默认使用 AKShare 和东方财富：

- `stock_zh_a_spot`：全市场实时快照。
- 东方财富 `ulist`：补充量比、换手率、总市值。
- `stock_zh_a_hist`：历史日线，用于近 20 日涨停判断。
- `stock_zh_a_hist_min_em`：1 分钟分时，用于尾盘形态和次日复盘。

AKShare 接口偶尔会因为网络、限频或源站字段变化失败。程序会在扫描结果里记录失败原因，不会静默当作入选。

回测脚本额外使用 Baostock：

- `query_trade_dates`：确认实际交易日。
- `query_all_stock`：取历史日期可交易股票列表。
- `query_history_k_data_plus`：取历史日线和 5 分钟线。
