# A股半自动量化投研系统

这是一个失败关闭（fail-closed）、可追溯的日线/低频 A 股投研项目。它读取和计算市场、财务、行业与事件数据，每日最多生成 5 只候选股票及风险报告；不连接券商、不自动下单、不承诺收益。

只要必需数据缺失、来源异常、过期或校验失败，运行状态就是 `BLOCKED_DATA`，对应分析立即停止并输出“不推荐”。系统不会静默使用随机数据、示例数据、模型猜测或过期缓存补位。

## 当前能力

- 分层存储：Parquet 原始/标准化数据与 DuckDB 加工数据，保留来源、抓取时间、数据日期、可知时间、运行 ID 和内容哈希。
- 数据接口：统一提供者协议、AkShare A 股日线适配器、FRED/CFTC/SEC 官方数据适配器、有限次数重试和数据源切换入口。
- 数据质量：模式、逐行类型/完整性、有效期/可知时间、唯一性和失败关闭检查；未协调的多源批次保守阻断。
- 股票池：主板、ST/退市整理、上市天数、停牌、流动性及可成交状态的可配置过滤。
- 因子：趋势、相对强弱、量价/换手、波动/回撤、财务、估值分位、行业景气及事件催化；输出原始值、标准化值和得分。
- 回测：复权数据输入、停牌、涨跌停、T+1、费用、印花税、滑点、无法成交、历史股票池和可知时间约束，并保留所有实验结果。
- Evidence Gate：A/B/C/D 证据等级、独立来源、转载去重、反方证据、发布时间与事件时间、无法验证状态。
- 全球上下文：美国行业/市场走势和期货信息只用于风险说明，不进入 A 股数值评分，也不执行真实期货对冲。
- 报告：Markdown、JSON、CSV 三种格式；数据不足时明确“不推荐”。

## 安装

要求 Python 3.11–3.13。PowerShell：

```powershell
cd D:\Dev\Code\gp-tools\a_share_quant_research
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

如果本机的构建隔离无法联网，可先安装 `setuptools` 和 `wheel`，再执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
```

密钥只能通过环境变量或外部密钥管理器提供，不得写入代码或 YAML。免费公共数据源可能限流、变更接口或短时不可用；此时系统会在有界重试后停止。

## 配置

配置均在 `config/`：

- `providers.yaml`：数据源优先级、限速、超时与最大重试次数。
- `quality.yaml`：各数据域的新鲜度、完整率和一致性阈值。
- `universe.yaml`：板块、ST、上市时间、停牌和流动性过滤。
- `factors.yaml`：必需因子、公式参数和评分权重。
- `backtest.yaml`：T+1、手数、手续费、印花税、滑点与资金参数。

## 手动运行

先查看统一入口：

```powershell
.\.venv\Scripts\python.exe -m a_share_research.cli --help
```

推荐按以下顺序运行。任一步返回非零退出码时停止，不得跳过门禁。

1. `init-db`：创建 raw、normalized、curated、manifests、quarantine 目录。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli init-db --data-dir data
   ```

2. `update-data`：从真实 AkShare 接口增量抓取 A 股日线并写入标准化 Parquet。时间必须带时区。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli update-data --symbols 600000,000001 --start-date 2026-01-01 --end-date 2026-07-10 --as-of 2026-07-12T08:00:00+08:00 --run-id daily-20260712 --data-dir data --config-dir config
   ```

3. `validate-data`：读取数据批次清单、数据契约和源输入文件清单 JSON，逐文件计算授权哈希并输出质量报告。只有 `PASS` 才能继续。`artifacts.json` 是“逻辑名称到文件路径”的映射，后续文件一旦变化就会阻断。程序生成的 Universe、因子、证据、行业、候选和回测结果采用带 run ID、门禁快照和 payload hash 的阶段产物封装，由下一个命令继续校验，无需预先存在。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli validate-data --batches-json inputs/batches.json --contracts-json inputs/contracts.json --artifacts-json inputs/artifacts.json --as-of 2026-07-12T08:30:00+08:00 --output-json outputs/quality.json
   ```

   常用逻辑名为：`universe_securities`、`universe_bars`、`event`、`evidence`、`factor_bars`、`factor_benchmark`、`factor_financials`、`factor_valuations`、`factor_industry`、`factor_events`、`context`、`orders`、`backtest_bars`、`historical_universe`、`backtest_config`、`walk_windows`。只列本次实际会用到的文件。

4. `build-universe`：按历史时点和配置生成合格股票池及停牌/涨跌停标志。交易状态列缺失时失败关闭。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli build-universe --securities-csv inputs/securities.csv --bars-csv inputs/universe-bars.csv --as-of 2026-07-12 --config-dir config --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/universe.json
   ```

5. `run-evidence-gate`：校验单个事件和证据包，必须真实完成反方搜索并显式传入标志。证据必须带 event ID、entity ID、发布时间和事件时间。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli run-evidence-gate --event-json inputs/event.json --evidence-json inputs/evidence.json --counter-search-performed --as-of 2026-07-12T08:30:00+08:00 --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/evidence.json
   ```

6. `compute-factors`：从指定目录读取 `bars.csv`、`benchmark.csv`、`financials.csv`、`valuations.csv`、`industry.csv`、`events.csv`，按可知时间计算因子。事件输入必须含 `published_at`。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli compute-factors --bundle-dir inputs/factor_bundle --as-of 2026-07-12T08:30:00+08:00 --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/factors.json
   ```

7. `rank-industries`：对已校验的全球/行业上下文生成行业方向与排名。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli rank-industries --context-json inputs/context.json --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/industries.json
   ```

8. `select-candidates`：只读取同一门禁快照产生的因子、Universe 和一个或多个 Evidence 阶段产物（多个证据文件用逗号分隔）。只有因子齐全、实体拥有已验证证据、位于合格股票池且当前可成交时才入选，最多输出 5 只。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli select-candidates --factors-json outputs/factors.json --evidence-json outputs/evidence-list.json --universe-json outputs/universe.json --config-dir config --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/candidates.json
   ```

9. `backtest`：使用历史信号订单和日线数据运行单次回测；信号在收盘形成，只能在下一交易日开盘执行。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli backtest --orders-csv inputs/orders.csv --bars-csv inputs/bars.csv --historical-universe-csv inputs/historical-universe.csv --as-of 2026-07-10 --benchmark-return 0.012 --config config/backtest.yaml --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/backtest.json
   ```

10. `walk-forward`：使用窗口 JSON 运行滚动回测；每个窗口必须含 `start`、`end` 和 `benchmark_return`，成功和失败结果都会保留。

   ```powershell
   .\.venv\Scripts\python.exe -m a_share_research.cli walk-forward --orders-csv inputs/orders.csv --bars-csv inputs/bars.csv --historical-universe-csv inputs/historical-universe.csv --windows-json inputs/windows.json --config config/backtest.yaml --gate-json outputs/quality.json --run-id daily-20260712 --output-json outputs/walk-forward.json
   ```

11. `daily-report`：只把程序管线生成、run ID 与质量门禁一致的规范报告 JSON 渲染为 Markdown、JSON 和 CSV。门禁失败时只允许渲染错误完全一致的 `BLOCKED_DATA` 报告。

    ```powershell
    .\.venv\Scripts\python.exe -m a_share_research.cli daily-report --report-json outputs/canonical-daily-report.json --candidates-json outputs/candidates.json --factors-json outputs/factors.json --config-dir config --gate-json outputs/quality.json --run-id daily-20260712 --output-dir outputs/daily/2026-07-12
    ```

手动命令稳定后，也可调用 `.agents/skills/a-share-daily-research/SKILL.md` 所定义的相同流程。Skill 只负责编排命令，不能生成程序未计算的数据。

## 测试与审查

```powershell
make verify
.\.venv\Scripts\python.exe -m ruff format src tests --check
```

在 Windows 未安装 `make` 时，直接运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src
```

修改因子后必须重跑回测和防未来函数测试；修改数据接口后必须运行数据质量测试；完成前必须检查测试结果和 diff。

## 第一版边界与已知限制

- 生产抓取当前直接实现 A 股日线；财务、公告、新闻、行业指数等域已有统一接口/模型，但仍需按实际可用的免费源逐项接入，缺少时不会开始推理。
- Evidence Gate 是确定性规则引擎。语言模型如被外部调用，只能完成文本分类、事件抽取、产业链与矛盾证据解释，并必须引用程序提供的 evidence ID。
- `daily-report` 是严格的规范 JSON 渲染器，不会自行抓数或补字段。
- 回测是可解释的日线模拟器；Qlib 保留为未来对照验证选项，未作为运行时依赖。
- 期货对冲当前仅为研究资源和风险情景，不包含真实头寸建议或交易执行。

本项目是研究工具，不构成投资建议。任何候选都必须结合数据时点、证据状态、历史信号表现和个人风险承受能力独立判断。
