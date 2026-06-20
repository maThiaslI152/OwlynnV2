# Extension Eval — 2026-06-21

**Overall: 1010/1300 (77.7%) — PASS**

- Profile: `cloud`
- Mock mode: `True`
- Vision available: `False`

## Per-Track Results

| Track | Score | % | Status |
|-------|-------|---|--------|
| Track 1 — Active Tab Context | 205/300 | 68.3% | ⚠️ Marginal |
| Track 3 — Interactive DOM | 225/300 | 75.0% | ✅ Pass |
| Track 4 — Background Scraping | 105/200 | 52.5% | ❌ Fail |
| Track 5 — Moodle Extraction | 300/300 | 100.0% | ✅ Pass |
| Track 6 — Connection Lifecycle | 175/200 | 87.5% | ✅ Pass |

## Turn Details

### [EX1.1] Tab Context Retrieval — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 12.8s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (253 chars ≥ 20)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX1.2] Selected Text Awareness — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 18.7s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (496 chars ≥ 20)
  - +25: Marker 'EVAL_SELECTION_MARKER' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX1.3] Graceful Fallback (no extension) — ❌ 5/100
- Tools: `[]`
- Route: `complex-cloud`
- Duration: 57.5s
- Breakdown:
  - -20: Expected tool 'get_active_browser_context' not called (got: [])
  - +20: Response non-empty (369 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
  - -10: Premature complete (tool stall)

### [EX2.1] Screenshot Capture — ⏭ SKIPPED (vision_unavailable)

### [EX2.2] Screenshot on Demand — ⏭ SKIPPED (vision_unavailable)

### [EX3.1] Click Element — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: `complex-cloud`
- Duration: 14.9s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (79 chars ≥ 10)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.2] Type into Field — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: `complex-cloud`
- Duration: 14.8s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (88 chars ≥ 10)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.3] Scroll Page — ✅ 75/100
- Tools: `['active_browser_action']`
- Route: `complex-cloud`
- Duration: 13.8s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (147 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response

### [EX4.1] Multi-URL Fetch — ❌ 30/100
- Tools: `[]`
- Route: `complex-cloud`
- Duration: 32.0s
- Breakdown:
  - -20: Expected tool 'browser_background_fetch' not called (got: [])
  - +20: Response non-empty (755 chars ≥ 30)
  - +25: Marker 'EVAL_FETCH_MARKER_1' found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX4.2] Error Handling — ✅ 75/100
- Tools: `['browser_background_fetch', 'fetch_webpage']`
- Route: `complex-cloud`
- Duration: 13.9s
- Breakdown:
  - +40: Tool 'browser_background_fetch' called correctly
  - +20: Response non-empty (98 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)

### [EX5.1] Moodle Assignments — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 19.7s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (568 chars ≥ 20)
  - +25: Marker 'EVAL_MOODLE_ASSIGNMENT' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX5.2] Moodle Grades — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 22.7s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (540 chars ≥ 15)
  - +25: Marker 'EVAL_MOODLE_GRADE_88' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX5.3] Non-Moodle Fallback — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 19.7s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (239 chars ≥ 15)
  - +25: Marker 'EVAL_NONMOODLE_CONTENT' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.1] Extension Auto-Connect — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 18.8s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (247 chars ≥ 10)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.3] Graceful Missing Extension (screenshot) — ✅ 75/100
- Tools: `['get_active_browser_screenshot', 'get_active_browser_context']`
- Route: `complex-cloud`
- Duration: 17.4s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (177 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
