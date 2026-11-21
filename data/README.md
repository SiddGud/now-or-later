# Data

Cleaned responses from both surveys, collected 5 to 15 November 2026. Made by `analysis/report_assets.py` from the raw Google Sheet export.

| File | Contents |
|---|---|
| `now_or_later_responses_summary.csv` | One row per response (215 rows). Opens as a table on GitHub. |
| `now_or_later_responses_clean.csv` | The same rows plus `trialsJSON`: every tap, with the offer shown, the choice and the decision time in ms. |

**Removed for privacy:** UPI IDs, free-text comments and full browser strings (`device_type` gives phone or computer). Removed rows are 2 setup tests, 2 duplicate submissions of the same response, and 1 response from a team member.

## Key columns

| Column | Meaning |
|---|---|
| `id` | Random respondent id |
| `survey_form` | `main (index.html)` or `short (proposal.html)` |
| `status`, `exclusion_reason` | `analysed` (188 rows) or `excluded`, with the reason: careless answering in the main survey (3 or more of 5 warning signs), or a rushed response in the short survey (over 25% of taps under 400 ms) |
| `version` | Main survey version (v1, v2 from 6 Nov, v3 from 7 Nov; see `docs/PROJECT_CONTEXT.md`) |
| `order`, `nudgeGroup`, `anchorGroup`, `flipOrder` | Random assignments |
| `A_<context>_ind` | Switch point when the wait starts today (₹, or days for health) |
| `B_<context>_ind` | Switch point when the wait starts in 30 days |
| `A_<context>_k`, `B_<context>_k` | Discount rate, k = (switch point / sooner value − 1) / 30 |
| `*_censored` | `low` or `high` when the switch point is pinned at an end of the range |
| `*_meanRT` | Mean decision time in ms |
| `flipNear`, `flipFar`, `flipped` | Classic reversal pair answers |
| `nudge_*` | Hidden-zero task; compare by `nudgeGroup` |
| `anchorYes`, `anchorAmount` | Anchoring task; compare by `anchorGroup` |
| `p1`–`p5`, `type1Score`, `correctScore` | Reflection puzzles: answers, number of intuitive answers, number correct |
| `trust`, `stress`, `spending`, `priorKnowledge`, `otherSurvey`, `age`, `describes`, `year`, `field` | Controls and demographics |
| `attn1`, `attn2`, `attentionFail` | Attention checks (dominance check in the short survey) |

Contexts are `gain`, `loss` (fine), `health` (headache-free days in the main survey, days of flu in the short one) and `friend`.
