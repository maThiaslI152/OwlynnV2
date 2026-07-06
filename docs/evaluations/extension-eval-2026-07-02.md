# Extension Eval — 2026-07-02

**Overall: 960/1700 (56.5%) — FAIL**

- Profile: `local`
- Mock mode: `True`
- Vision available: `True`

## Per-Track Results

| Track | Score | % | Status |
|-------|-------|---|--------|
| Track 1 — Active Tab Context | 255/300 | 85.0% | ✅ Pass |
| Track 2 — Visual Context | 150/200 | 75.0% | ✅ Pass |
| Track 3 — Interactive DOM | 165/500 | 33.0% | ❌ Fail |
| Track 4 — Background Scraping | 80/200 | 40.0% | ❌ Fail |
| Track 5 — Moodle Extraction | 135/300 | 45.0% | ❌ Fail |
| Track 6 — Connection Lifecycle | 175/200 | 87.5% | ✅ Pass |

## Turn Details

### [EX1.1] Tab Context Retrieval — ✅ 80/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 600.4s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  -   0: Response too short (17 chars < 20)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX1.2] Selected Text Awareness — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 163.1s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (73 chars ≥ 20)
  - +25: Marker 'EVAL_SELECTION_MARKER' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX1.3] Graceful Fallback (no extension) — ✅ 75/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 100.6s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (42 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)

### [EX2.1] Screenshot Capture — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: ``
- Duration: 192.0s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (25 chars ≥ 15)
  - +10: No DSML leak
  - +5: Clean response
  -   ✓: Vision proxy invoked correctly

### [EX2.2] Screenshot on Demand — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: ``
- Duration: 106.5s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (45 chars ≥ 15)
  - +10: No DSML leak
  - +5: Clean response
  -   ✓: Vision proxy invoked correctly

### [EX3.1] Click Element — ✅ 75/100
- Tools: `['get_active_browser_context', 'active_browser_action']`
- Route: ``
- Duration: 115.5s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (110 chars ≥ 10)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.2] Type into Field — ❌ 5/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 153.9s
- Breakdown:
  - -20: Expected tool 'active_browser_action' not called (got: ['get_active_browser_context'])
  - +20: Response non-empty (15 chars ≥ 10)
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX3.3] Scroll Page — ✅ 75/100
- Tools: `['active_browser_action']`
- Route: ``
- Duration: 158.0s
- Breakdown:
  - +40: Tool 'active_browser_action' called correctly
  - +20: Response non-empty (14 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response

### [EX3.4] Hover Element — ❌ 5/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 148.8s
- Breakdown:
  - -20: Expected tool 'active_browser_action' not called (got: ['get_active_browser_context'])
  - +20: Response non-empty (340 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX3.5] Batch Selection — ❌ 5/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 228.3s
- Breakdown:
  - -20: Expected tool 'active_browser_action' not called (got: ['get_active_browser_context'])
  - +20: Response non-empty (82 chars ≥ 8)
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX4.1] Multi-URL Fetch — ✅ 75/100
- Tools: `['browser_background_fetch']`
- Route: ``
- Duration: 418.1s
- Breakdown:
  - +40: Tool 'browser_background_fetch' called correctly
  - +20: Response non-empty (112 chars ≥ 30)
  -   0: Marker 'EVAL_FETCH_MARKER_1' NOT found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX4.2] Error Handling — ❌ 5/100
- Tools: `['active_browser_action']`
- Route: ``
- Duration: 212.0s
- Breakdown:
  - -20: Expected tool 'browser_background_fetch' not called (got: ['active_browser_action'])
  - +20: Response non-empty (72 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
  - -10: Premature complete (tool stall)

### [EX5.1] Moodle Assignments — ❌ 30/100
- Tools: `[]`
- Route: ``
- Duration: 241.8s
- Breakdown:
  - -20: Expected tool 'get_active_browser_context' not called (got: [])
  - +20: Response non-empty (39 chars ≥ 20)
  - +25: Marker 'EVAL_MOODLE_ASSIGNMENT' found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX5.2] Moodle Grades — ❌ 30/100
- Tools: `[]`
- Route: ``
- Duration: 39.9s
- Breakdown:
  - -20: Expected tool 'get_active_browser_context' not called (got: [])
  - +20: Response non-empty (97 chars ≥ 15)
  - +25: Marker 'EVAL_MOODLE_GRADE_88' found in response
  - +10: No DSML leak
  - +5: Clean response
  - -10: Premature complete (tool stall)

### [EX5.3] Non-Moodle Fallback — ✅ 75/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 137.6s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (30 chars ≥ 15)
  -   0: Marker 'EVAL_NONMOODLE_CONTENT' NOT found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.1] Extension Auto-Connect — ✅ 100/100
- Tools: `['get_active_browser_context']`
- Route: ``
- Duration: 137.8s
- Breakdown:
  - +40: Tool 'get_active_browser_context' called correctly
  - +20: Response non-empty (18 chars ≥ 10)
  - +25: Marker 'EVAL_TAB_MARKER_7' found in response
  - +10: No DSML leak
  - +5: Clean response

### [EX6.3] Graceful Missing Extension (screenshot) — ✅ 75/100
- Tools: `['get_active_browser_screenshot']`
- Route: ``
- Duration: 105.9s
- Breakdown:
  - +40: Tool 'get_active_browser_screenshot' called correctly
  - +20: Response non-empty (54 chars ≥ 10)
  - +10: No DSML leak
  - +5: Graceful response (no crash)
