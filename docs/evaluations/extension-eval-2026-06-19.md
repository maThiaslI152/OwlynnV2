# Extension Eval — 2026-06-19

**Overall: 175/200 (87.5%) — PASS**

- Profile: `cloud`
- Mock mode: `True`
- Vision available: `False`

## Per-Track Results

| Track | Score | % | Status |
|-------|-------|---|--------|
| Track 6 — Connection Lifecycle | 175/200 | 87.5% | ✅ Pass |

## Turn Details

### [EX6.1] Extension Auto-Connect — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 11.7s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (293 chars ≥ 10)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.3] Graceful Missing Extension (screenshot) — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: `complex-cloud`
- Duration: 15.3s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (68 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
