# Daily Finance Influencer Radar Design

## Goal

Create a daily Codex thread report at 10:00 Asia/Shanghai that tracks public, citable commentary from selected finance influencers, evaluates emerging industry themes, and produces an A-share observation list with evidence, catalysts, risks, and position-discipline guidance. Also generate a local single-file HTML version of each report for easier reading.

The report is an information and research aid. It must not present itself as guaranteed return guidance, individualized investment advice, or an unconditional buy/sell instruction.

## User Decisions

- Output channel: current Codex thread plus a local HTML report file under `reports/`.
- Schedule: every calendar day at 10:00 Asia/Shanghai.
- Source boundary: use only public, citable, and reasonably stable sources.
- Initial watch list: Li Yien, Justin Sun, Longtou Daban Zhang, Tiancai Aman, Yu Boluo, plus other finance commentators that pass the credibility filter.
- User preference: proceed autonomously after this design.

## Report Structure

Each daily report should use the same sections so the user can compare reports over time. The report must be result-first: industry analysis, stock observation/recommendation, and future forecast come before evidence details.

1. Industry analysis
   - Summarize the strongest 1-5 concrete excellent industries or theme signals.
   - Classify each signal as high, medium, or low confidence.
   - Explain conclusion, policy basis, key data, industry logic, catalysts, validation points, invalidation signals, and risks.
   - High-confidence industries should include at least 2-3 public data points or verifiable facts with dates and source links.

2. A-share observation and recommendation pool
   - List candidate A-share stocks connected to the strongest industry themes.
   - For each stock, include ticker, company name, company profile, main business, industry-chain position, actual business evidence, revenue/order/customer/announcement support, recent price move, current price position, distance from 52-week/year-to-date/historical highs when available, valuation judgment, hype/inflation check, plain-language buy-or-do-not-buy conclusion, trigger condition, no-buy condition, and key risk.
   - Keep all information for one stock together in one stock card or subsection so the user can understand the business, price position, valuation, and buyability in one place.
   - Avoid jargon such as right-side confirmation, trend confirmation, high-volatility watch, core watch, or elastic watch unless it is immediately translated into a buy-or-do-not-buy conclusion.
   - Allowed conclusion labels: can buy, cannot buy now, wait for pullback before buying, wait for earnings/order confirmation before buying, or insufficient data to judge.
   - Do not give unconditional buy/sell instructions.

3. Future forecast
   - Produce a result-oriented ranking of future industries that are more likely to strengthen.
   - Combine current and expected policy direction, industry data, capital-market preference, and company-level validation.
   - For each predicted industry, explain why it is attractive, policy catalyst, data to track, likely realization window, invalidation signals, and what not to chase.

4. Influencer and reliable-source tracker
   - Cover the initial watch list first, but do not limit the report to those five people.
   - Add other public finance commentators, industry researchers, public real-position authors, institutional or sector researchers, financial media writers, and industry experts when they provide traceable, relevant, and non-duplicative signals.
   - For each item, include source link, publication time when available, a concise paraphrase, industry tags, confidence level, and why the source is included or downweighted.

5. Cross-verification
   - Separate multi-source agreement from single-source claims.
   - Identify whether commentary aligns with policy news, industry news, market behavior, or company announcements.
   - Mark unverified reposts, unclear original sources, and content that appears mainly promotional.

6. Risk and position discipline
   - Include reminders about chasing high moves, position sizing, stop-loss discipline, event-driven volatility, and verification gaps.
   - State that the output is for research and monitoring, not personalized financial advice.

## Source Rules

Preferred sources:

- First-party public posts: Weibo, WeChat public articles, Xueqiu posts, public video pages, public interview pages, and public live replay descriptions.
- Verifiable secondary sources: financial media articles, platform charts, news reports, and community citations that clearly indicate they are not the original source.
- Market and company context: exchange announcements, company filings, sector news, major policy releases, and reputable market summaries.

Restricted sources:

- Platforms requiring login, unstable dynamic feeds, or content without a durable public URL may be used only as weak leads.
- Screenshots without an original source are weak evidence.
- Claims about real positions or real-money trading must be treated as unverified unless supported by public, dated, and reviewable evidence.

## Influencer Credibility Filter

An influencer or commentator can be added to the daily report when at least two of these conditions are met:

- Long-term public output with timestamps.
- Clear historical theses that can be reviewed after the fact.
- Public portfolio, real-position discussion, or trade reasoning that can be checked without relying on private groups.
- Industry-level reasoning rather than code-only promotion.
- Frequent citation by other public sources, without being purely traffic-driven.

Downgrade or exclude a commentator when content shows one or more of these signals:

- Only posts stock codes without logic.
- Frequently deletes or materially rewrites calls after market moves.
- Pushes private paid groups as the main action.
- Uses exaggerated profit claims.
- Lacks an original, stable source.

## Ranking Method

The daily automation should rank themes using a simple evidence score:

- Source quality: first-party and stable sources score higher.
- Consensus: independent commentators converging on the same theme score higher.
- External validation: policy, industry news, company announcements, or market behavior score higher.
- Time sensitivity: fresh and specific claims score higher than stale broad narratives.
- Data support: policy documents, association data, company announcements, earnings forecasts, order or tender data, prices, sales volume, capacity, penetration rate, capex, inventory cycle, valuation percentile, fund flow, or index performance score higher.
- Risk penalty: crowded trades, sharp recent moves, unverifiable claims, and obvious promotional language score lower.

Confidence labels:

- High: multiple independent sources, good traceability, external validation, and identifiable catalysts.
- Medium: good logic or source quality but incomplete external validation.
- Low: interesting lead, limited evidence, unclear source, or high promotional risk.

If reliable public data cannot be found for an industry, the report must state that clearly and lower the confidence level instead of inventing numbers.

## Stock Diagnostic Requirements

Each high-priority stock should be presented as a single diagnostic card or subsection with these fields:

- Company profile: main business, core product, industry-chain position, and downstream/customer direction.
- Actual business verification: company announcement, financial report, earnings preview, exchange Q&A, order/tender, customer, capacity, or product progress where available.
- Price position: 5-day, 20-day, 60-day, and year-to-date move where available; distance from 52-week high, year-to-date high, or historical high where available; state whether it is near a high.
- Valuation and hype check: PE/PB/PS/PEG, historical valuation percentile, peer comparison, market cap vs earnings fit, performance growth, and concept heat where available.
- Buy-or-do-not-buy conclusion: use plain labels only and attach reason, trigger, position discipline, stop-loss or invalidation condition.

If reliable stock price, valuation, or business data cannot be found, the report must say so and avoid presenting a buyability conclusion as strong.

## Subsector Consensus Rule

The report must not hide important subsectors inside broad categories. When several tracked commentators mention the same subsector, it must be evaluated as a standalone candidate industry.

Required active watch tags:

- Optical modules, silicon photonics, CPO, 800G, and 1.6T.
- Storage, HBM, DRAM, NAND, and enterprise SSD.

Examples:

- Do not write only "AI compute" when the concrete signal is optical modules or CPO.
- Do not write only "semiconductors" when the concrete signal is DRAM, NAND, HBM, or storage modules.
- If a popular subsector is not selected as a high-ranking industry, the report must explain why it was downgraded: weak data, crowded trade, valuation, lack of source verification, or missing earnings validation.

The output should use a professional portfolio-manager style: conclusion first, data second, risk third. Blogger consensus is useful only when it is supported by policy, industry data, order evidence, earnings, or market behavior.

## Automation Behavior

The automation should run every calendar day at 10:00 Asia/Shanghai and post the report in the current thread. It should also create `reports/finance-radar-YYYY-MM-DD.html` as a polished single-file HTML report and include the local path in the thread response. It should browse or otherwise verify current public sources at runtime. When current information cannot be found, it should say so plainly and avoid filling gaps with invented claims.

The report should use concise Chinese, include links for cited sources, and keep stock observations clearly separated from risk reminders. The local HTML layout should open with the three highest-priority result blocks: concrete excellent industry ranking, stock single-name diagnostic cards, and future excellent-industry forecast; evidence, expanded influencer/reliable-source tracking, and risk details should follow.

## Non-Goals

- No automatic trading.
- No personalized financial planning.
- No scraping behind login walls.
- No promise that any influencer has real positions unless independently verifiable.
- No local database in the first version.
