# Confidence Cap Rules

The downstream stock-analysis skill must not exceed these confidence caps.

| Condition | Max Confidence |
|---|---:|
| All core source groups covered, no major conflict | 8 |
| Minor source gaps, no material event | 7 |
| Market news missing | 6 |
| Flash news missing | 6 |
| Social sentiment missing | 7 |
| Official disclosure missing | 5 |
| Latest price unavailable | 6 |
| Price/volume/fund-flow anomaly without matching news | 4 |
| Material event appears but is unconfirmed | 5 |
| Conflicting reports on key event | 4 |
| Only low-reliability sources available | 3 |
| No recent official/news data available | 2 |

## Evidence status

- PASS: coverage_score >= 80 and no critical source missing.
- WARN: coverage_score 40-79 or any important source partial/missing.
- BLOCK: coverage_score < 40, no usable market/news evidence, or official + market news both missing.

## Required behavior

- A downstream report must show `confidence_cap` and explain why.
- If status is BLOCK, do not produce a strong stock conclusion. Return missing data and manual checks.
- If status is WARN, continue only with conditional language and capped confidence.
