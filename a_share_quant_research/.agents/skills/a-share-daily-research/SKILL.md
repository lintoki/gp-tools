---
name: a-share-daily-research
description: Use when running the configured daily A-share research workflow, refreshing market data, validating completeness, checking evidence, computing factors, backtesting signals, or producing candidate reports.
---

# A股每日投研

固定项目根目录为 `D:\Dev\Code\gp-tools\a_share_quant_research`。无论当前工作区在哪里，先运行 `Set-Location D:\Dev\Code\gp-tools\a_share_quant_research`，再使用 `.venv\Scripts\python.exe -m a_share_research.cli`。如果项目或虚拟环境不存在，立即停止并报告，不得在其他目录猜测替代路径。只编排程序和检查产物，不得生成未经程序计算的数据，不得自动交易。

## 启动检查

1. 读取 `AGENTS.md`、`README.md` 和 `config/*.yaml`。
2. 确认使用真实生产输入，拒绝 `TEST_ONLY_` 夹具、随机数据、示例数据和过期缓存。
3. 确认每个必需字段包含来源、抓取时间、数据日期、可知时间和运行 ID。
4. 如数据目录不存在，先运行 `init-db`。所有网络操作遵守配置的超时和最大尝试次数；不得无限重试。

## 严格执行顺序

每条命令都记录参数、退出码和产物路径。任一步退出码非零、输入缺失、时间戳过期或数据门禁失败时，立即停止本次流程，输出 `BLOCKED_DATA` 和“不推荐”，不要调用语言模型或继续下游步骤。

1. 运行 `update-data` 更新配置股票池的必需数据域；不得用低可信源静默替换失败域。
2. 运行 `validate-data`，同时传入覆盖所有下游输入的 `--artifacts-json`；只有状态为 `PASS` 且 run ID、数据哈希、精确文件哈希齐全才继续。后续所有命令使用同一个 `--gate-json` 和 `--run-id`，不得替换或修改已授权文件。
3. 运行 `build-universe`，硬性排除非主板、ST/退市、上市期不足、流动性不足及缺少交易状态的股票。
4. 运行 `run-evidence-gate`。要求反方搜索；证据 event/entity 必须匹配且发布时间不得晚于 as-of；A/B 可作核心证据，无 A/B 时至少两个独立 C，D 只能作线索。无法验证的重大事件不得计分。
5. 运行 `compute-factors`。确认全部必需因子存在，并保留原始值、标准化值、得分和可知时间。
6. 运行 `rank-industries`。美国行业、股市和期货只能作为风险上下文，不得进入 A 股数值评分。
7. 运行 `select-candidates`。最多 5 只；不足时不得凑数，无合格股票时输出“不推荐”。
8. 运行 `backtest` 检查历史同类信号；需要滚动结果时随后运行 `walk-forward`。不得只选择最优参数，保留失败实验。
9. 只接受 `DailyResearchPipeline` 产生、run ID 与门禁一致的规范报告 JSON，再运行 `daily-report` 输出 Markdown、JSON、CSV；不得人工补写数值字段。

## 输出审查

确认报告包含数据更新时间、市场环境、行业排名、候选因子、关键与反方证据、失效条件、历史信号、风险和观察/等待确认/候选池结论。数值必须可追溯到程序产物，文本解释必须引用 evidence ID。不得连接券商、账户、委托或执行真实期货对冲。
