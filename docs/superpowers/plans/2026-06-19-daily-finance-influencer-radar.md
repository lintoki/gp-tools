# Daily Finance Influencer Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a daily Codex thread automation that posts a 10:00 Asia/Shanghai finance influencer radar report and writes a local result-first HTML version.

**Architecture:** Use the Codex app automation facility as the scheduler and thread delivery mechanism. Ask the automation to also write a single-file HTML report under `reports/` so the user can open a polished local version. The report layout prioritizes concrete excellent-industry analysis, stock recommendation observation pool, and future excellent-industry forecast before evidence details.

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
The HTML report should be result-first: section 1 concrete excellent-industry ranking with policy and data, section 2 stock recommendation observation pool, section 3 future excellent-industry forecast with policy/data reasoning, followed by influencer tracking, cross-verification, and risk discipline.

- [x] **Step 2: Use this automation prompt**

```text
每天生成一份中文财经投研雷达报告，定位为公开信息研究辅助，不是个性化投资建议或保证收益承诺。

请在运行时检索和核验当前公开、可引用、尽量稳定的来源，优先覆盖李一恩、孙宇晨、龙头大班长、天才阿蛮、宇菠萝，并可补充其他满足可信度筛选的知名财经博主或评论者。只使用公开可访问的信息；需要登录、不可稳定访问、只有截图或无法找到原始出处的内容，只能作为低可信线索，不能作为强证据。

报告必须包含：
1. 今日核心结论：列出1-3个最值得关注的行业或主题，并标记高/中/低置信度。
2. 博主言论追踪：每条包括博主/来源、发布时间、来源链接、观点摘要、行业标签、可信度。
3. 观点交叉验证：区分多人共识、单一观点、与政策/产业新闻/盘面/公告共振的证据；无法核验的内容必须明确说明。
4. 行业前景分析：从政策、订单或业绩可见度、景气周期、资金关注、风险五个角度判断。
5. A股观察池：围绕高质量行业主题列出候选A股股票，包含代码、名称、逻辑、催化剂、风险点、观察纪律。不要输出无条件买入或卖出指令。
6. 风险与仓位纪律：提示不追高、分批、止损、事件兑现、流动性和信息源风险。

筛选和降权规则：
- 优先一手公开内容和可核验二手来源。
- 声称实仓的人，只有在公开、日期清晰、可复盘证据存在时才可标记为较高可信；否则写成未核验。
- 只喊代码不讲逻辑、频繁删帖、强引流付费群、夸大收益、没有原始来源的内容要降权或剔除。
- 不要编造博主观点、持仓、链接、日期或行情数据。

输出风格：中文，结构清晰，结论先行，引用来源使用Markdown链接。股票部分必须清楚标为观察池和研究线索。
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
