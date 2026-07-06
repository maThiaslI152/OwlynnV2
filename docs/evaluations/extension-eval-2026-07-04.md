# Extension Eval — 2026-07-04

**Overall: 1090/1700 (64.1%) — MARGINAL**

- Profile: `local`
- Mock mode: `True`
- Vision available: `True`

## Per-Track Results

| Track | Score | % | Status |
|-------|-------|---|--------|
| Track 1 — Active Tab Context | 245/300 | 81.7% | ✅ Pass |
| Track 2 — Visual Context | 150/200 | 75.0% | ✅ Pass |
| Track 3 — Interactive DOM | 375/500 | 75.0% | ✅ Pass |
| Track 4 — Background Scraping | 10/200 | 5.0% | ❌ Fail |
| Track 5 — Moodle Extraction | 135/300 | 45.0% | ❌ Fail |
| Track 6 — Connection Lifecycle | 175/200 | 87.5% | ✅ Pass |

## Turn Details

### [EX1.1] Tab Context Retrieval — ✅ 70/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 38.3s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  -   0: Response too short (17 chars < 20)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX1.2] Selected Text Awareness — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 38.3s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (22 chars ≥ 20)
  - +25: Marker 'EVAL_SELECTION_MARKER' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX1.3] Graceful Fallback (no extension) — ✅ 75/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 32.2s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (214 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)

### [EX2.1] Screenshot Capture — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: ``
- Duration: 53.4s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (22 chars ≥ 15)
  - +10: No DSML leak
  - +5: Clean response
  -   ✓: Vision proxy invoked correctly

### [EX2.2] Screenshot on Demand — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: ``
- Duration: 33.2s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (100 chars ≥ 15)
  - +10: No DSML leak
  - +5: Clean response
  -   ✓: Vision proxy invoked correctly

### [EX3.1] Click Element — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: ``
- Duration: 58.5s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (56 chars ≥ 10)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.2] Type into Field — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: ``
- Duration: 59.5s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (10 chars ≥ 10)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.3] Scroll Page — ✅ 75/100
- Tools: `['active_browser_action']`
- Route: ``
- Duration: 40.8s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (82 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.4] Hover Element — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: ``
- Duration: 78.7s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (128 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.5] Batch Selection — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: ``
- Duration: 81.2s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (126 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response

### [EX4.1] Multi-URL Fetch — ❌ 5/100
- Tools: `[]`
- Route: ``
- Duration: 29.8s
- Breakdown:
  - -20: Expected tool 'browser_background_fetch' not called (got: [])
  - +20: Response non-empty (66 chars ≥ 30)
  -   0: Marker 'EVAL_FETCH_MARKER_1' NOT found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX4.2] Error Handling — ❌ 5/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: ``
- Duration: 54.4s
- Breakdown:
  - -20: Expected tool 'browser_background_fetch' not called (got: ['get_active_browser_context', 'active_browser_action'])
  - +20: Response non-empty (397 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
  - -10: Premature complete (tool stall)

### [EX5.1] Moodle Assignments — ❌ 30/100
- Tools: `[]`
- Route: ``
- Duration: 29.8s
- Breakdown:
  - -20: Expected tool 'get_active_browser_context' not called (got: [])
  - +20: Response non-empty (127 chars ≥ 20)
  - +25: Marker 'EVAL_MOODLE_ASSIGNMENT' found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX5.2] Moodle Grades — ❌ 30/100
- Tools: `[]`
- Route: ``
- Duration: 23.7s
- Breakdown:
  - -20: Expected tool 'get_active_browser_context' not called (got: [])
  - +20: Response non-empty (183 chars ≥ 15)
  - +25: Marker 'EVAL_MOODLE_GRADE_88' found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX5.3] Non-Moodle Fallback — ✅ 75/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 38.8s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (56 chars ≥ 15)
  -   0: Marker 'EVAL_NONMOODLE_CONTENT' NOT found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.1] Extension Auto-Connect — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 40.8s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (75 chars ≥ 10)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.3] Graceful Missing Extension (screenshot) — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: ``
- Duration: 40.4s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (54 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
