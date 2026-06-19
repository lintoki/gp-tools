# Daily Finance Influencer Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a daily Codex thread automation that posts a 10:00 Asia/Shanghai finance influencer radar report and writes a local result-first HTML version.

**Architecture:** Use the Codex app automation facility as the scheduler and thread delivery mechanism. Ask the automation to also write a single-file HTML report under `reports/` so the user can open a polished local version. The report layout prioritizes concrete excellent-industry analysis, stock single-name diagnostic cards with direct buy-or-do-not-buy conclusions, and future excellent-industry forecast before evidence details.

**Tech Stack:** Codex app `automation_update`, Markdown documentation, public web sources at automation runtime.

---

## File Structure

- Create: `docs/superpowers/specs/2026-06-19-daily-finance-influencer-radar-design.md`
  - Purpose: product scope, report format, evidence rules, risk boundaries, and source policy.
- Create: `docs/superpowers/plans/2026-06-19-daily-finance-influencer-radar.md`
  - Purpose: implementation checklist and exact automation prompt.
- Create: `reports/finance-radar-preview-2026-06-19.html`
  - Purpose: visual preview of the HTML report format.
- No application source files are created in the first version.

### Task 1: Document the Approved Design

**Files:**
- Create: `docs/superpowers/specs/2026-06-19-daily-finance-influencer-radar-design.md`

- [x] **Step 1: Create the specification**

Write the approved scope: daily thread report, public citable sources, influencer credibility filter, industry scoring, A-share observation pool, and non-goals.

- [x] **Step 2: Self-review the specification**

Verify the file has no placeholders, no contradictory report sections, and no language that implies guaranteed returns or personalized investment advice.

Expected result: the specification is concise, internally consistent, and suitable for the automation prompt.

### Task 2: Create the Daily Automation

**Files:**
- No repository files changed by this task.

- [x] **Step 1: Create a Codex heartbeat automation**

Use `codex_app.automation_update` with:

```text
mode: create
kind: heartbeat
destination: thread
name: 每日财经博主言论与A股观察报告
schedule: every day at 10:00 Asia/Shanghai
status: ACTIVE
```

The automation should also create `reports/finance-radar-YYYY-MM-DD.html` and include the local path in its thread response.
The HTML report should be result-first: section 1 concrete excellent-industry ranking with policy and data, section 2 stock single-name diagnostic cards covering company profile, real business, recent move, price position, valuation/hype, direct buy-or-do-not-buy conclusion, triggers and risks, section 3 future excellent-industry forecast with policy/data reasoning, followed by expanded influencer/reliable-source tracking, cross-verification, and risk discipline. Optical modules/CPO and storage/HBM/DRAM/NAND must be actively evaluated as standalone subsectors instead of being hidden under broad AI or semiconductor categories.

- [x] **Step 2: Use this automation prompt**

```text
生成中文财经投研雷达报告，结果优先，不是个性化投顾或收益承诺。

报告顺序：
1. 具体优秀行业榜单：优先级、置信度、结论、政策依据、关键数据、行业逻辑、催化剂、验证点、失效条件和风险。
2. 股票单票体检卡：每只股票集中写清企业基本信息、主营业务、产业链位置、实际业务/收入/订单/客户/公告支撑、最近涨幅、当前价格位置、是否接近52周/年内/历史高点、估值是否虚高、是否概念炒作、买不买结论、买入触发条件、暂不购买条件和风险。
3. 未来优秀行业预测：结合当前和未来政策、产业数据、资金偏好，给出未来更可能走强的行业排序。
4. 博主和可靠信源追踪：覆盖李一恩、孙宇晨、龙头大班长、天才阿蛮、宇菠萝，但不能只看这五人；必须扩展检索其他靠谱财经博主、产业研究者、公开实盘作者、券商/机构研究观点、财经媒体作者和行业专家。
5. 观点交叉验证、风险与仓位纪律。

硬规则：
- 高置信行业至少给2-3个公开可验证数据点或事实。
- 高优先级股票至少给2-3个可验证事实或数据点。
- 找不到数据必须写“未找到可靠公开数据”或“未找到可靠行情数据”，并降低置信度。
- 买不买结论必须用白话：可以买、现在不能买、等回调再买、等业绩/订单确认后再买、资料不足不判断。禁止只写右侧确认、趋势确认、回撤关注、高波动观察、弹性观察、核心观察这类黑话。
- 不要编造博主观点、持仓、链接、日期、政策、行业数据、股票行情或估值数据。
- 同时生成 `reports/finance-radar-YYYY-MM-DD.html`，HTML 首屏展示行业榜单、股票单票体检卡、未来行业预测。
```

- [x] **Step 3: Verify the automation**

View the created automation and confirm these properties:

```text
name: 每日财经博主言论与A股观察报告
kind: heartbeat
destination: current thread
cadence: daily at 10:00 Asia/Shanghai
status: ACTIVE
```

### Task 3: Record Environment Notes

**Files:**
- Modify: final user response only.

- [x] **Step 1: Report git limitation**

Mention that `git` was not available in the current PowerShell PATH or common install locations, so the required documentation commit could not be created from this environment.

- [x] **Step 2: Summarize delivered artifacts**

Report these created files:

```text
D:\Dev\Code\gp-tools\docs\superpowers\specs\2026-06-19-daily-finance-influencer-radar-design.md
D:\Dev\Code\gp-tools\docs\superpowers\plans\2026-06-19-daily-finance-influencer-radar.md
```

## Self-Review

- Spec coverage: the plan covers the approved thread output, daily schedule, public-source boundary, influencer filter, industry analysis, A-share observation pool, and risk language.
- Placeholder scan: no placeholder sections or deferred requirements remain.
- Type consistency: automation fields and report sections are named consistently across the specification and plan.
