# Handoff Contract

The evidence pack is the contract between `news-evidence-gate` and downstream stock-analysis skills.

## Downstream skill must

1. Read `evidence_pack.json` and `evidence_pack.md`.
2. Start final report with:
   - evidence_status
   - coverage_score
   - confidence_cap
   - source coverage table
   - missing sources
3. Discuss all high/extreme material events before technical or valuation conclusions.
4. Mention all conflicts and unconfirmed events.
5. Do not exceed `confidence_cap`.
6. If official disclosure is missing, avoid strong BUY/SELL wording.
7. If price/volume anomaly is unexplained, state information-gap risk.
8. Include a section: "哪些新增信息会推翻当前结论".

## Downstream skill must not

- Say "无重大利空/无重大利好" unless official disclosure, market news, and flash news are all covered.
- Treat social-media rumors as confirmed facts.
- Ignore missing source groups.
- Raise confidence above the cap.
- Place trades or connect to brokerage accounts.
