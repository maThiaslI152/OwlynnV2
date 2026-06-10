---
status: superseded
category: evaluation
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Local Frontier Evaluation — 2026-06-10 (superseded methodology)

> **Superseded by:** updated `scripts/run_local_frontier_eval.py` (eval_version `2026-06-10`) and re-run with `--profile` / `--cloud-off`.  
> This report used the **old** scorer (hard-coded `complex-default`, legacy `.tool-name` scraper).

## Original run (flawed scorer)

| Metric | Value |
|--------|-------|
| Score | 250 / 600 (41.67%) |
| CI quick (same day) | ✅ 914 pytest + 111 vitest |

**Why the score was misleading:**

1. **Cloud-primary routing** — With escalation ON, `complex-cloud` is correct; old script penalized it vs `complex-default`.
2. **Stale tool DOM** — UI uses `ToolActivityCard` (`.tool-activity-name code`); old script queried removed `.tool-name` → false tool misses.
3. **F1.1 timeout** — 1200s wait on empty simple reply counted route points anyway.
4. **DSML** — Cloud turns leaked DSML in bubbles; not scored separately.

## System changes since 2026-06-05 baseline (600/600)

| Area | Then | Now |
|------|------|-----|
| Default routing | Local complex (Qwen9B) | **Cloud-first** DeepSeek V4 Flash |
| Routes | `simple` / `complex-default` | + `complex-cloud`, vision proxy, MCP tools |
| Web search | Basic loop | BUG-13: tool delta, DSML strip, synthesis cap |
| UI tools | Sidebar `.tool-name` | Inline **ToolActivityCard** in chat timeline |
| Usage | Static chip | Cloud usage chip + context breakdown (BUG-14) |

## Re-run instructions (current)

```bash
./start.sh
# Cloud-primary (production default):
python scripts/run_local_frontier_eval.py --profile auto

# Local-only regression (apples-to-apples with 2026-06-05):
python scripts/run_local_frontier_eval.py --cloud-off --profile local
```

Artifact: `data/frontier_eval_run_data.json` (includes `eval_version`, `runtime_profile`, `dsml_leak` per turn).

## Related

- [`docs/standards/EVALUATION.md`](../standards/EVALUATION.md)
- [`local-frontier-eval-2026-06-05.md`](local-frontier-eval-2026-06-05.md) — last 100% baseline (local tier)
