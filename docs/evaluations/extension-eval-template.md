# Extension Eval — TEMPLATE

**Overall: X/Y (Z%) — PASS / MARGINAL / FAIL**

- Profile: `cloud` | `local`
- Mock mode: `true` (Python mock extension) | `false` (real Brave)
- Vision available: `true` | `false`
- Run date: YYYY-MM-DD

---

## Pass Standard

| Band | Score | Meaning |
|------|-------|---------|
| ✅ Pass | ≥ 75% | Extension suite healthy |
| ⚠️ Marginal | 60–74% | Investigate specific tracks |
| ❌ Fail | < 60% | Regression detected |

Track 6 (Connection Lifecycle) must score 100% regardless of overall score.

---

## Per-Track Results

| Track | Score | % | Status |
|-------|-------|---|--------|
| Track 1 — Active Tab Context | X/200 | Z% | ✅ / ⚠️ / ❌ |
| Track 2 — Visual Context | X/200 | Z% | ✅ / ⚠️ / ❌ |
| Track 3 — Interactive DOM | X/300 | Z% | ✅ / ⚠️ / ❌ |
| Track 4 — Background Scraping | X/200 | Z% | ✅ / ⚠️ / ❌ |
| Track 5 — Moodle Extraction | X/300 | Z% | ✅ / ⚠️ / ❌ |
| Track 6 — Connection Lifecycle | X/200 | Z% | ✅ / ⚠️ / ❌ |

---

## Turn Details

### [EX1.1] Tab Context Retrieval — ✅ X/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: X.Xs
- Breakdown:
  - +40: Tool called correctly
  - +20: Response non-empty
  - +25: Marker found
  - +10: No DSML leak
  - +5: Clean response

<!-- Repeat for each turn -->

---

## Notes

<!-- Add any observations, regressions, or follow-ups here -->
