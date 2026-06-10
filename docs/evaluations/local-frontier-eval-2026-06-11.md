---
status: completed
category: evaluation
audience: agent
last_updated: 2026-06-11
owner: ai-agent
---

# Local Frontier Evaluation — 2026-06-11 (pipeline sync)

**Script:** `scripts/run_local_frontier_eval.py` (`eval_version: 2026-06-11`)  
**Profile:** `cloud` (escalation ON, DeepSeek key valid)  
**Score:** **1565 / 1900 (82.37%)** — 19 turns, 0 skipped  
**Duration:** ~78 min  
**Artifact:** `data/frontier_eval_run_data.json`

## What changed in this eval

- **Graph-idle wait** — completion requires no `.composer-stop`, HITL pending, running tools, or streaming cursor (not first bubble)
- **Timeline tool scrape** — tools collected from `.messages > *` siblings after last user message
- **Expanded coverage** — frontier tier (F7), router LLM (F8), vision OCR (F9), memory (M1–M2), file watcher (W1), formats (FF1–FF4)
- **Fixtures:** `assets/eval_fixtures/` (pdf, docx, xlsx, csv, ocr png)

## Turn results

| Turn | Route | Grade | Key notes |
|------|-------|-------|-----------|
| F1.1 Simple | `simple` ✓ | 70 | Route OK; **empty reply** after 180s idle timeout |
| F2.1 Complex | `complex-cloud` ✓ | 90 | Valid “paste code” response |
| F3.1 Web+file | `complex-cloud` ✓ | 60 | **Missing tools** in timeline (web_search, write_workspace_file) |
| F4.1 Read file | `complex-cloud` ✓ | 60 | **Missing** `read_workspace_file` tool card |
| F5.1 React | `complex-cloud` ✓ | 90 | Long codegen response |
| F6.1 Memory | `complex-cloud` ✓ | 100 | Recalled Tokyo / tokyo_weather.txt |
| F7.1 Frontier flash | `complex-cloud` ✓ | 100 | `model_tier=flash` — frontier hints do **not** auto-escalate tier |
| F7.2 Pro path | `complex-cloud` ✓ | 100 | `model_tier=pro` after profile bump |
| F8.1 Router LLM | `complex-cloud` ✓ | 90 | Route OK; source=`deterministic` not `llm_classifier` (+5 partial) |
| F9.1 Vision OCR | `complex-cloud` ✗ | 65 | Expected `vision_cloud`; got complex-cloud; OCR marker not in answer |
| M1.1 Memory seed | `complex-cloud` ✓ | 95 | WS `memory_updated` not captured (+5 penalty) |
| M1.2 Session recall | `complex-cloud` ✓ | 100 | ZEBRA-42 recalled |
| M2.1 LTM cross-thread | `complex-cloud` ✓ | 100 | Codeword recalled in new chat (HITL resolved) |
| M4.1 Gate negative | `complex-cloud` ✗ | 40 | Expected `simple`; got complex-cloud |
| W1.1 File watcher | `complex-cloud` ✓ | 65 | Timeout; **missing** `read_workspace_file` tool |
| FF1.1 PDF | `complex-cloud` ✓ | 85 | Marker in answer; processed OK |
| FF2.1 DOCX | `complex-cloud` ✓ | 85 | Marker in answer |
| FF3.1 XLSX | `complex-cloud` ✓ | 85 | Cell marker in answer |
| FF4.1 CSV | `complex-cloud` ✓ | 85 | CSV marker in answer |

## Findings

### Improved vs v2 (75.8%, 6 turns)

- Score **82.37%** on 19 turns with stricter idle-based completion
- **Memory pipeline validated:** session recall (M1.2), LTM cross-thread (M2.1), frontier pro tier path (F7.2)
- **Format ingestion:** pdf/docx/xlsx/csv attach → answer contains fixture markers (FF1–FF4)

### Confirmed architectural gaps

1. **Frontier tier** — `_needs_frontier_quality()` routes to cloud but does **not** bump `cloud_model_tier`; F7.1 correctly runs on `flash`
2. **Vision route** — image attach did not produce `vision_cloud` route (F9.1); fell through to `complex-cloud`
3. **Router LLM classifier** — F8 ambiguous prompt still classified as `deterministic`, not `llm_classifier`
4. **ToolActivityCard scrape** — F3/F4/W1 show empty `executed_tools` despite complex-cloud routes (UI cards may not render in headless or tools run without cards)

### Remaining product issues

- **F1.1** — Simple path empty visible reply (known; route + model badge OK)
- **F3/F4/W1** — Tool execution not observed in timeline within timeout
- **M4.1** — “Hi there!” routed to complex-cloud instead of simple (retrieval gate negative control failed)
- **F9.1** — Vision proxy path not engaged on image drop

### Recommended follow-ups

- Investigate why image attachment does not trigger `vision_cloud` deterministic route
- Fix simple-path streaming empty bubble (BUG candidate)
- Ensure ToolActivityCard emits for all tool_action runs in headless eval
- Tighten M4 negative control prompt or router greeting bypass

## Scorer hardening (post-run)

This run's 82.37% used DOM scraping, which **under-scored** several turns whose WS event
stream proved they succeeded. The scorer was then changed to read tools/route/task_category
from captured WS events (`tool_execution`, `router_info`) as the source of truth, and the
DSML gate was broadened to catch `<tool_call>` / `<function=` leaks.

Re-scoring the WS-derived facts for the affected turns:

| Turn | Run grade | Hardened grade | Reason |
|------|-----------|----------------|--------|
| W1.1 watcher | 65 | 100 | `read_workspace_file` fired (WS); was mis-read as no-tool |
| F9.1 vision | 65 | 100 | task_category `vision_cloud`; OCR marker recalled |
| F8.1 router LLM | 90 | 100 | `llm_classifier` source credited |
| F3.1 web+file | 60 | 25 | `<tool_call>` markup leaked as text (real bug, now caught) |
| F4.1 read file | 60 | 45 | tool-call-as-text leak (real bug, now caught) |

A clean re-run with the hardened scorer is the next action.

---

## Post-fix re-runs (2026-06-11)

After harness + product fixes documented in [`changes/frontier-eval-memory-session/CHANGELOG.md`](../changes/frontier-eval-memory-session/CHANGELOG.md):

| Run | Score | Key deltas vs 82.37% baseline |
|-----|-------|-------------------------------|
| `FrontierEval_b1e097` | **1790/1900 (94.21%)** | F3 stall fixed (33s); F4=100; F9=100 |
| `FrontierEval_ba6eb0` | **1785/1900 (93.95%)** | M4=90; F8=95 (hitl); F9=60 (Florence OCR fail) |

**Fixes shipped:**

- WS `tool_execution` merge + idle tool-stall early exit
- F4 workspace seed (`status_eval.md` fixture)
- M4 greeting gate (`Hi there!`)
- F8 reword + `new_chat_before`
- F9 Florence strict preflight + auto-load
- Scoring-only cloud Qwen fallback cap (grade ≤49)
- Background memory extraction deferral (`local_llm_scheduler.py`)

**Still open:** F1 empty simple bubble, F6 tool use vs STM recall, F9 Florence load variance, target ≥97% not met.

**Latest artifact:** `data/frontier_eval_run_data.json` (`cloud_scoring: qwen_fallback_fail`)

## Related

- [`local-frontier-eval-2026-06-10-v2.md`](local-frontier-eval-2026-06-10-v2.md) — prior 75.8% (6 turns)
- [`docs/standards/EVALUATION.md`](../standards/EVALUATION.md) — pipeline + turn matrix
