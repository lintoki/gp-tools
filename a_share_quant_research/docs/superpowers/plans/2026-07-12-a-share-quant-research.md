# A股半自动量化投研系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立目录中构建一个失败关闭、可追溯、可回测的A股日线半自动投研系统，最多输出5只候选以及Markdown、JSON、CSV报告。

**Architecture:** 生产运行时完全自研，采用Provider接口、raw/normalized/curated数据湖、运行级质量门禁、确定性因子、自研事件驱动回测、Evidence Gate、境外风险上下文和统一报告模型。Qlib不进入生产依赖，只允许作为可选测试对照。

**Tech Stack:** Python 3.11–3.13、pandas、PyArrow、DuckDB、Pydantic 2、HTTPX、PyYAML、pytest、ruff；AkShare为可选生产数据依赖。

## Global Constraints

- 不连接券商、不自动下单、不承诺收益。
- 生产路径禁止随机数据、示例数据、固定占位值和静默过期缓存回退。
- 必需数据未通过门禁时，整次运行停止且不调用语言模型。
- 每个请求最多3次总尝试，最多切换1个备用源，每数据集默认60秒截止时间。
- 所有因子由程序计算，语言模型只处理文本分类、事件抽取、产业链、矛盾和解释。
- 因子权重、股票池、数据质量和交易成本规则均由YAML配置。
- 每个新函数先写失败测试，再写最小实现。
- 用户明确要求本任务不提交Git；每个任务以测试、静态检查和只读diff审查替代提交。

---

## File Map

```text
a_share_quant_research/
  pyproject.toml                 依赖、pytest、ruff和命令入口
  Makefile                       统一任务入口
  README.md                      安装、真实数据配置和使用说明
  AGENTS.md                      强制工程约束
  ARCHITECTURE.md                运行架构、数据流和失败语义
  PLANS.md                       阶段状态、验收结果和已知问题
  config/*.yaml                  股票池、因子、质量、来源、回测配置
  src/a_share_research/
    cli.py                       手动命令入口
    settings.py                  YAML和环境变量配置
    core/models.py               溯源、批次、manifest、失败和运行状态
    core/retry.py                有限重试与熔断
    providers/base.py            统一Provider协议与注册表
    providers/akshare.py         A股免费聚合数据适配
    providers/official.py        FRED、SEC、CFTC等HTTP适配
    storage/lake.py              raw/Parquet/DuckDB分层写入
    quality/contracts.py         数据契约定义
    quality/gate.py              运行级质量门禁
    universe/rules.py            历史股票池和交易状态
    factors/*.py                 八类因子、标准化和组合评分
    backtest/*.py                事件驱动撮合、成本、指标、实验账本
    evidence/*.py                证据模型、去重、验证和LLM结果模式
    context/*.py                 美国市场、行业和期货风险标签
    reporting/*.py               JSON规范模型与Markdown/CSV渲染
    pipeline.py                  状态机和每日流水线
  tests/                         单元、集成、质量和未来函数测试
  tests/fixtures/TEST_ONLY_*     明确仅供测试的固定夹具
```

### Task 1: 项目治理、配置和CLI骨架

**Files:**
- Create: `pyproject.toml`, `Makefile`, `AGENTS.md`
- Create: `config/universe.yaml`, `config/factors.yaml`, `config/quality.yaml`, `config/providers.yaml`, `config/backtest.yaml`
- Create: `src/a_share_research/__init__.py`, `src/a_share_research/cli.py`, `src/a_share_research/settings.py`
- Test: `tests/unit/test_settings.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `load_settings(config_dir: Path) -> Settings`
- Produces: `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write failing settings and CLI tests**

```python
def test_load_settings_reads_factor_weights(config_dir):
    settings = load_settings(config_dir)
    assert sum(settings.factor_weights.values()) == pytest.approx(1.0)

def test_cli_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    assert "daily-report" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_settings.py tests/unit/test_cli.py -v`
Expected: FAIL because package and functions do not exist.

- [ ] **Step 3: Implement package metadata, strict YAML settings and argparse CLI**

```python
def load_settings(config_dir: Path) -> Settings:
    payloads = {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in config_dir.glob("*.yaml")}
    settings = Settings.model_validate(payloads)
    if abs(sum(settings.factor_weights.values()) - 1.0) > 1e-9:
        raise ValueError("factor weights must sum to 1")
    return settings

def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return int(args.handler(args))
```

- [ ] **Step 4: Run tests, ruff and governance text checks**

Run: `python -m pytest tests/unit/test_settings.py tests/unit/test_cli.py -v`
Expected: PASS.

Run: `python -m ruff check src tests`
Expected: exit 0.

Run: `rg -n "禁止编造数据|禁止绕过测试|禁止自动交易|修改因子后必须重新回测|修改数据接口后必须运行数据质量测试|完成任务前必须运行测试并审查diff" AGENTS.md`
Expected: six required policies found.

### Task 2: 溯源模型、有限重试和运行状态机

**Files:**
- Create: `src/a_share_research/core/models.py`, `src/a_share_research/core/retry.py`
- Test: `tests/unit/core/test_models.py`, `tests/unit/core/test_retry.py`

**Interfaces:**
- Produces: `DataBatch`, `FieldProvenance`, `FailureRecord`, `RunManifest`, `RunStatus`
- Produces: `BoundedRetryPolicy.execute(operation, is_transient) -> T`

- [ ] **Step 1: Write failing tests for provenance completeness and bounded retry**

```python
def test_data_batch_rejects_missing_provenance():
    with pytest.raises(ValidationError):
        DataBatch(dataset="daily_bars", rows=[{"close": 10.0}])

def test_retry_stops_after_three_total_attempts():
    calls = 0
    def fail():
        nonlocal calls
        calls += 1
        raise TimeoutError("network")
    with pytest.raises(RetryExhausted):
        BoundedRetryPolicy(max_attempts=3, delays=(0, 0)).execute(fail, lambda e: True)
    assert calls == 3
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/core -v`
Expected: FAIL because core models are missing.

- [ ] **Step 3: Implement immutable Pydantic models and retry loop**

```python
class RunStatus(StrEnum):
    CREATED = "CREATED"
    FETCHING = "FETCHING"
    NORMALIZING = "NORMALIZING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    COMPUTING = "COMPUTING"
    EVIDENCE = "EVIDENCE"
    REPORTING = "REPORTING"
    BLOCKED_DATA = "BLOCKED_DATA"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"

class BoundedRetryPolicy:
    def execute(self, operation, is_transient):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except Exception as exc:
                if not is_transient(exc) or attempt == self.max_attempts:
                    raise RetryExhausted(attempt, exc) from exc
                self.sleep(self.delays[attempt - 1])
```

- [ ] **Step 4: Verify GREEN and diff**

Run: `python -m pytest tests/unit/core -v`
Expected: PASS including permanent-error-no-retry test.

### Task 3: 数据湖、DuckDB快照和质量门禁

**Files:**
- Create: `src/a_share_research/storage/lake.py`
- Create: `src/a_share_research/quality/contracts.py`, `src/a_share_research/quality/gate.py`
- Test: `tests/unit/storage/test_lake.py`, `tests/data_quality/test_gate.py`

**Interfaces:**
- Consumes: `DataBatch`, `RunManifest`
- Produces: `DataLake.write_raw`, `write_normalized`, `publish_curated`
- Produces: `QualityGate.validate(batches, contracts, as_of) -> QualityReport`

- [ ] **Step 1: Write failing quality tests**

```python
@pytest.mark.parametrize("mutation", ["missing_column", "duplicate_key", "stale", "partial_failure"])
def test_required_dataset_failure_blocks_run(valid_batch, contract, mutation):
    batch = mutate(valid_batch, mutation)
    report = QualityGate().validate([batch], [contract], AS_OF)
    assert report.status == "FAIL"
    assert report.blocking_errors

def test_publish_curated_refuses_failed_quality(tmp_path, failed_report):
    with pytest.raises(DataGateBlocked):
        DataLake(tmp_path).publish_curated([], failed_report)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/data_quality tests/unit/storage -v`
Expected: FAIL because storage and gate are missing.

- [ ] **Step 3: Implement append-only raw writes, Parquet partitions and PASS-only DuckDB publishing**

```python
def publish_curated(self, batches, quality_report):
    if quality_report.status != QualityStatus.PASS:
        raise DataGateBlocked(quality_report.blocking_errors)
    with duckdb.connect(str(self.db_path)) as con:
        for batch in batches:
            con.execute("CREATE OR REPLACE VIEW " + safe_name(batch.dataset) + " AS SELECT * FROM read_parquet(?)", [batch.parquet_glob])
```

`QualityGate` must execute schema, type, uniqueness, nullability, coverage, freshness, OHLC, non-negative volume, factor positivity, cross-source and `available_at <= as_of` rules. Every failed rule returns an exact code and affected keys.

- [ ] **Step 4: Verify GREEN and storage invariants**

Run: `python -m pytest tests/data_quality tests/unit/storage -v`
Expected: PASS; no curated database created for failed report.

### Task 4: Provider协议、AkShare和官方境外数据适配

**Files:**
- Create: `src/a_share_research/providers/base.py`, `providers/akshare.py`, `providers/official.py`
- Test: `tests/unit/providers/test_registry.py`, `test_akshare.py`, `test_official.py`

**Interfaces:**
- Produces: `DataProvider.fetch(request) -> DataBatch`
- Produces: `ProviderRegistry.fetch_with_fallback(request) -> DataBatch`

- [ ] **Step 1: Write failing provider tests using injected callables**

```python
def test_registry_switches_to_one_backup_only(primary, backup, request):
    result = ProviderRegistry(primary, [backup]).fetch_with_fallback(request)
    assert result.source_name == backup.name
    assert primary.calls == 3
    assert backup.calls == 1

def test_partial_symbol_failure_is_not_success(provider, request):
    batch = provider.fetch(request)
    assert batch.failed_items
    assert batch.is_complete is False
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/providers -v`
Expected: FAIL because providers are missing.

- [ ] **Step 3: Implement lazy AkShare imports and strict HTTP providers**

```python
class AkshareProvider:
    def __init__(self, api=None):
        self.api = api
    def _api(self):
        if self.api is not None:
            return self.api
        import akshare
        return akshare

class FredCsvProvider(HttpProvider):
    def fetch(self, request):
        response = self.client.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": request.series_id})
        response.raise_for_status()
        return self.normalize_csv(response, request)
```

Implement CFTC Socrata JSON and SEC submissions/XBRL adapters with explicit User-Agent, timeouts and source URI. HTTP parsing or schema changes are permanent failures, not retryable network failures.

- [ ] **Step 4: Verify GREEN without network**

Run: `python -m pytest tests/unit/providers -v`
Expected: PASS using injected responses; no test accesses the internet.

### Task 5: 历史股票池和八类因子

**Files:**
- Create: `src/a_share_research/universe/rules.py`
- Create: `src/a_share_research/factors/base.py`, `technical.py`, `fundamental.py`, `industry.py`, `event.py`, `scoring.py`
- Test: `tests/unit/universe/test_rules.py`, `tests/unit/factors/*.py`, `tests/no_lookahead/test_factors.py`

**Interfaces:**
- Produces: `UniverseBuilder.build(as_of, securities, bars) -> UniverseResult`
- Produces: `FactorEngine.compute(snapshot, as_of) -> list[FactorResult]`
- Produces: `CompositeScorer.score(results, weights) -> list[CandidateScore]`

- [ ] **Step 1: Write failing formula and no-lookahead tests**

```python
def test_future_rows_do_not_change_past_factor(engine, snapshot):
    before = engine.compute(snapshot, AS_OF)
    after = engine.compute(snapshot.with_future_extreme_rows(), AS_OF)
    assert before == after

def test_missing_required_factor_excludes_candidate(scorer, results_with_missing):
    score = scorer.score(results_with_missing, WEIGHTS)
    assert score.status == "EXCLUDED_MISSING_FACTOR"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/universe tests/unit/factors tests/no_lookahead/test_factors.py -v`
Expected: FAIL because universe and factors are missing.

- [ ] **Step 3: Implement exact formulas from the design spec**

```python
def trend(close: pd.Series) -> float:
    require_history(close, 60)
    ma20 = close.iloc[-20:].mean()
    ma60 = close.iloc[-60:].mean()
    return 0.5 * (close.iloc[-1] / ma20 - 1) + 0.5 * (ma20 / ma60 - 1)

def robust_cross_section(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    clipped = values.clip(values.quantile(.01), values.quantile(.99))
    z = (clipped - clipped.mean()) / clipped.std(ddof=0)
    return z, clipped.rank(pct=True) * 100
```

Implement all eight factors, dependency manifests, actual-disclosure-date filtering and YAML-only weights. No missing-value imputation is permitted for required factors.

- [ ] **Step 4: Verify GREEN and formulas**

Run: `python -m pytest tests/unit/universe tests/unit/factors tests/no_lookahead/test_factors.py -v`
Expected: PASS, including appended-future invariance.

### Task 6: 自研事件驱动回测和实验账本

**Files:**
- Create: `src/a_share_research/backtest/models.py`, `exchange.py`, `engine.py`, `metrics.py`, `experiments.py`
- Test: `tests/unit/backtest/*.py`, `tests/no_lookahead/test_backtest.py`, `tests/integration/test_walk_forward.py`

**Interfaces:**
- Produces: `ExchangeSimulator.can_fill`, `fill_order`
- Produces: `BacktestEngine.run(strategy, snapshot, config) -> BacktestResult`
- Produces: `ExperimentLedger.record(result_or_failure)`

- [ ] **Step 1: Write failing hand-calculated golden tests**

```python
def test_t_plus_one_prevents_same_day_sale(golden_market):
    result = run_orders(golden_market, [buy("600000", D1), sell("600000", D1)])
    assert result.rejections[-1].code == "T_PLUS_ONE"

def test_locked_limit_up_buy_does_not_fill(golden_market):
    fill = ExchangeSimulator(CONFIG).fill_order(buy("600000", D2), golden_market)
    assert fill.status == "REJECTED_LIMIT_LOCK"

def test_failed_experiment_is_persisted(ledger):
    ledger.record_failure("exp-1", ValueError("bad data"))
    assert ledger.get("exp-1").status == "FAILED"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/backtest tests/no_lookahead/test_backtest.py -v`
Expected: FAIL because backtest modules are missing.

- [ ] **Step 3: Implement dated rules, cash/position ledger and metrics**

```python
def can_sell(position, instrument, trade_date):
    return position.available_quantity(instrument, trade_date) > 0

def annualized_return(equity):
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 252)
    return (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
```

Implement next-open execution, T+1 inventory restrictions, 100-share lot rounding, suspension/limit lock, dated commission and 印花税, directional 滑点, PIT snapshots, full metrics, regimes, sensitivity grids, in/out-of-sample and walk-forward results.

- [ ] **Step 4: Verify GREEN and no-lookahead**

Run: `python -m pytest tests/unit/backtest tests/no_lookahead/test_backtest.py tests/integration/test_walk_forward.py -v`
Expected: PASS and hand-calculated cash/equity values match exactly.

### Task 7: Evidence Gate and structured LLM handoff

**Files:**
- Create: `src/a_share_research/evidence/models.py`, `dedupe.py`, `gate.py`, `handoff.py`
- Test: `tests/unit/evidence/*.py`

**Interfaces:**
- Produces: `EvidenceGate.evaluate(event, evidence) -> VerificationResult`
- Produces: `export_llm_bundle(...)`, `import_llm_analysis(...)`

- [ ] **Step 1: Write failing evidence rule tests**

```python
def test_two_reprints_are_one_c_source():
    result = EvidenceGate().evaluate(EVENT, [C_REPRINT_1, C_REPRINT_2])
    assert result.status == "UNVERIFIED"

def test_two_independent_c_sources_verify_without_ab():
    result = EvidenceGate().evaluate(EVENT, [C_SOURCE_1, C_SOURCE_2])
    assert result.status == "VERIFIED"

def test_d_source_never_scores():
    assert EvidenceGate().evaluate(EVENT, [D_RUMOR]).catalyst_score == 0
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/evidence -v`
Expected: FAIL because evidence modules are missing.

- [ ] **Step 3: Implement deterministic gate and schema-validated LLM handoff**

```python
def verify(evidence):
    ab = [e for e in evidence if e.grade in {"A", "B"}]
    independent_c = independent_clusters(e for e in evidence if e.grade == "C")
    return bool(ab) or len(independent_c) >= 2

def import_llm_analysis(path: Path) -> LlmEvidenceAnalysis:
    return LlmEvidenceAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
```

LLM输入只能包含已验证文本批次；导入模式必须包含事件时间、发布时间、分类、产业链、正反证据引用和矛盾。模式失败即阻断Evidence阶段。

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/evidence -v`
Expected: PASS for A/B、two-C、D-only、unverified-major-event、contradiction and duplicate cases.

### Task 8: 美国市场、行业和期货风险上下文

**Files:**
- Create: `src/a_share_research/context/models.py`, `market.py`, `industry.py`, `futures.py`
- Test: `tests/unit/context/*.py`

**Interfaces:**
- Produces: `ContextEngine.compute(snapshot, as_of) -> GlobalContext`

- [ ] **Step 1: Write failing calendar-aware context tests**

```python
def test_weekly_cot_is_fresh_inside_release_window(engine, friday_snapshot):
    result = engine.compute(friday_snapshot, FRIDAY_AS_OF)
    assert result.futures.status == "READY"

def test_missing_required_us_series_blocks_context(engine, incomplete_snapshot):
    with pytest.raises(ContextDataIncomplete):
        engine.compute(incomplete_snapshot, AS_OF)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/context -v`
Expected: FAIL because context modules are missing.

- [ ] **Step 3: Implement deterministic labels**

```python
def trend_label(series):
    ma20, ma60 = series.tail(20).mean(), series.tail(60).mean()
    return "UP" if series.iloc[-1] > ma20 > ma60 else "DOWN" if series.iloc[-1] < ma20 < ma60 else "MIXED"
```

Compute index trend, volatility direction, yield/credit direction, official-industry evidence summary metadata and COT positioning deltas. Outputs are risk/context labels only and expose no order or target-position type.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/context -v`
Expected: PASS including holiday and weekly release calendar tests.

### Task 9: Pipeline、行业排名、候选和三格式报告

**Files:**
- Create: `src/a_share_research/reporting/models.py`, `render.py`
- Create: `src/a_share_research/pipeline.py`
- Modify: `src/a_share_research/cli.py`
- Test: `tests/unit/reporting/*.py`, `tests/integration/test_daily_pipeline.py`, `tests/data_quality/test_pipeline_blocking.py`

**Interfaces:**
- Produces: `DailyResearchPipeline.run(as_of) -> DailyReport`
- Produces: `render_json`, `render_markdown`, `render_csv`

- [ ] **Step 1: Write failing end-to-end and failure-report tests**

```python
def test_blocked_data_never_calls_compute_or_llm(pipeline, incomplete_batches):
    report = pipeline.run(AS_OF, batches=incomplete_batches)
    assert report.status == "BLOCKED_DATA"
    assert report.candidates == []
    pipeline.factor_engine.compute.assert_not_called()
    pipeline.llm_handoff.export.assert_not_called()

def test_success_outputs_same_candidate_ids_in_all_formats(pipeline, valid_batches, tmp_path):
    report = pipeline.run(AS_OF, batches=valid_batches)
    paths = pipeline.write(report, tmp_path)
    assert candidate_ids(paths.json) == candidate_ids(paths.markdown) == candidate_ids(paths.csv)
    assert len(report.candidates) <= 5
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/unit/reporting tests/integration/test_daily_pipeline.py tests/data_quality/test_pipeline_blocking.py -v`
Expected: FAIL because reporting and pipeline are missing.

- [ ] **Step 3: Implement strict state transitions and canonical JSON model**

```python
def run(self, as_of, batches=None):
    quality = self.quality_gate.validate(batches or self.fetch(as_of), self.contracts, as_of)
    if quality.status != "PASS":
        return DailyReport.blocked(as_of=as_of, errors=quality.blocking_errors)
    snapshot = self.data_lake.publish_curated(batches, quality)
    return self._compute_verified_report(snapshot, as_of)
```

Industry ranking and candidate selection must use configured weights, verified event score and hard exclusions. JSON is canonical; Markdown and CSV read only the validated `DailyReport` object.

- [ ] **Step 4: Verify GREEN and manual CLI**

Run: `python -m pytest tests/unit/reporting tests/integration/test_daily_pipeline.py tests/data_quality/test_pipeline_blocking.py -v`
Expected: PASS.

Run: `python -m a_share_research.cli daily-report --config config --as-of 2025-01-31 --fixture tests/fixtures/TEST_ONLY_daily`
Expected: exit 0 and three matching files under a temporary output directory marked TEST_ONLY.

### Task 10: 文档、全量验证和最终Skill

**Files:**
- Create: `README.md`, `ARCHITECTURE.md`, `PLANS.md`
- Create last: `.agents/skills/a-share-daily-research/SKILL.md`
- Test: `tests/integration/test_docs_commands.py`, `tests/integration/test_skill_contract.py`

**Interfaces:**
- Consumes: all stable CLI commands
- Produces: end-user usage guide and a Skill that only orchestrates program-computed data

- [ ] **Step 1: Write failing docs/Skill contract tests**

```python
def test_documented_commands_exist(readme_commands, cli_commands):
    assert readme_commands <= cli_commands

def test_skill_forbids_generated_numeric_data(skill_text):
    assert "不得生成未经程序计算的数据" in skill_text
    assert "daily-report" in skill_text
    assert "自动交易" in skill_text
```

- [ ] **Step 2: Run and verify RED before creating the Skill**

Run: `python -m pytest tests/integration/test_docs_commands.py tests/integration/test_skill_contract.py -v`
Expected: FAIL because final docs and Skill do not exist.

- [ ] **Step 3: Write result-first documentation and create Skill only after manual commands pass**

README must contain installation, configuration, real-data prerequisites, command sequence, failure semantics, outputs, no-trading disclaimer and troubleshooting. ARCHITECTURE mirrors the approved design. PLANS records each stage test result and unresolved limitations. Skill sequence is exactly: update data -> validate -> Evidence Gate -> factors -> industry ranking -> candidates -> historical performance -> report.

- [ ] **Step 4: Run fresh full verification**

Run: `python -m pytest -q`
Expected: all tests pass, zero failures.

Run: `python -m ruff check src tests`
Expected: exit 0.

Run: `python -m compileall -q src`
Expected: exit 0.

Run: `python -m a_share_research.cli --help`
Expected: exit 0 and all documented commands listed.

- [ ] **Step 5: Review workspace changes without committing**

Run: `git status --short` and `git diff --check` using the bundled Git executable if Git is not on PATH.
Expected: only intended new project files plus temporary visual-companion files; no whitespace errors. Do not run `git commit`.

## Execution Choice

The user authorized automatic approval and requested no more questions. Execute inline in the current session with `superpowers:executing-plans`; do not dispatch subagents and do not commit Git changes.
