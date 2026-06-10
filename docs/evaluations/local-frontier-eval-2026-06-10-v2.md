---
status: completed
category: evaluation
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Local Frontier Evaluation — 2026-06-10 (v2 scorer)

**Script:** `scripts/run_local_frontier_eval.py` (`eval_version: 2026-06-10`)  
**Profile:** `cloud` (escalation ON, DeepSeek key valid)  
**Score:** **455 / 600 (75.83%)**  
**Duration:** ~3.5 min (vs ~20 min with old 1200s simple timeout)  
**Artifact:** `data/frontier_eval_run_data.json`

## CI context (same day)

`./scripts/ci.sh --quick` — ✅ 914 pytest + 22 contract + 111 vitest, ~57% coverage

## Turn results

| Turn | Route | Grade | Notes |
|------|-------|-------|-------|
| F1.1 Simple | `simple` ✓ | 80 | Route OK; **empty reply** after 181s (LM Studio stall) |
| F2.1 Complex | `complex-cloud` ✓ | 100 | Asks for code — valid |
| F3.1 Web+file | `complex-cloud` ✓ | 60 | `web_search` ✓; **missing** `write_workspace_file` (HITL or DSML path) |
| F4.1 Read file | `complex-cloud` ✓ | 45 | **DSML leak** instead of tool card / answer |
| F5.1 React | `complex-cloud` ✓ | 85 | DSML penalty; short partial response |
| F6.1 Memory | `complex-cloud` ✓ | 85 | DSML; no tool recall answer |

## Findings

### Improved vs old scorer (41.7%)

- Cloud routes no longer penalized when escalation is ON
- Tool scrape uses **ToolActivityCard** — F3.1 detected `web_search`
- Simple timeout capped at **180s** (not 1200s)

### Remaining issues

1. **F1.1** — Local simple path still fails to stream a visible reply (investigate LM Studio + WS streaming)
2. **F3.1** — File write not completed in eval window (HITL approve flow or synthesis before write)
3. **F4–F6** — DSML in assistant bubbles reduces scores; tools not executed in UI

### Recommended follow-ups

- Re-run local baseline: `python scripts/run_local_frontier_eval.py --cloud-off --profile local`
- Fix simple-path empty response (BUG candidate)
- Strip DSML from intermediate bubbles or enforce tool execution before final message

## Related

- [`local-frontier-eval-2026-06-10.md`](local-frontier-eval-2026-06-10.md) — superseded 41.7% run (old scorer)
- [`docs/standards/EVALUATION.md`](../standards/EVALUATION.md)
