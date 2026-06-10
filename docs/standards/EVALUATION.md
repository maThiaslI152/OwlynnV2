---
status: active
category: standards
last_updated: 2026-06-10
owner: ai-agent
audience: agent
---

# Evaluation Standard

> **Purpose:** How to run automated browser evaluations against the **current** Owlynn stack (cloud-primary routing, ToolActivityCard UI, BUG-13..16 behavior).

## CI vs evaluation

| Layer | Command | Purpose |
|-------|---------|---------|
| Pre-push | `./scripts/ci.sh --quick` | 919 pytest + 111 vitest + ruff/mypy (~57% `src/` cov) |
| Live cloud | `./scripts/ci.sh --network` | DeepSeek E2E, KV cache, chat matrix (`DEEPSEEK_API_KEY`) |
| Benchmarks | `./scripts/ci.sh --benchmarks` | Router/complex/memory latency → `tests/benchmarks/benchmark_report.json` |
| **Frontier eval** | `python scripts/run_local_frontier_eval.py` | 6-turn scored routing + tools + response quality |
| **Conversation eval** | `python scripts/run_browser_eval.py` | 12-prompt multi-topic run (qualitative) |

Eval scripts are **not** in the CI gate — they need LM Studio + running stack (+ optional DeepSeek key).

## Architecture assumptions (2026-06-10)

```text
router → simple | complex-default (local Qwen) | complex-cloud (DeepSeek)
complex_llm → tool loops, HITL, web synthesis cap (max_web_tool_rounds: 3)
UI → ToolActivityCard in chat (not sidebar tool-name badges)
```

**Profiles:**

| Profile | When | Complex route expected |
|---------|------|----------------------|
| `cloud` | `cloud_escalation_enabled` + valid key | `complex-cloud` |
| `local` | Escalation off or no key | `complex-default` |
| `auto` | Read from `/api/unified-settings` + `/api/cloud-status` | Resolved at run start |

## Frontier evaluation (`run_local_frontier_eval.py`)

### Topics (6 turns)

1. **F1.1** — Simple greeting → `simple`, local small model, &lt;180s
2. **F2.1** — Code review → `complex` tier
3. **F3.1** — Web search + `write_workspace_file` (HITL on write)
4. **F4.1** — `read_workspace_file` on `docs/STATUS.md`
5. **F5.1** — Multi-file React + CSS generation
6. **F6.1** — Memory recall (no tools)

### Scoring (per turn, /100)

| Criterion | Points |
|-----------|--------|
| Route match (tier-aware) | 40 (30 if complex but wrong tier) |
| Non-empty response (min chars) | 20 |
| Expected tools (ToolActivityCard scrape) | 40 |
| DSML leak in assistant bubble | −15 |

### Prerequisites

- `./start.sh` (backend `:8000`, frontend `:5173`)
- LM Studio with models from `defaults.yaml`
- Playwright: `pip install playwright && playwright install chromium`

### Commands

```bash
# Production-like (cloud-first):
python scripts/run_local_frontier_eval.py --profile auto

# Local-only regression (compare to 2026-06-05 baseline):
python scripts/run_local_frontier_eval.py --cloud-off --profile local
```

### Artifacts

| Path | Content |
|------|---------|
| `data/frontier_eval_run_data.json` | Telemetry, grades, `eval_version`, profile |
| `assets/frontier_eval_screenshots/` | Per-turn PNGs |
| `docs/evaluations/local-frontier-eval-YYYY-MM-DD.md` | Human summary (required after significant runs) |

## Conversation evaluation (`run_browser_eval.py`)

12 curated prompts (technical, code review, creative, continuity, web search). Qualitative — no strict route grades. Output: `data/eval_run_data.json`, `assets/eval_screenshots/`.

## Reporting

After each significant frontier run:

1. Write `docs/evaluations/local-frontier-eval-YYYY-MM-DD.md`
2. Add entry to `docs/INDEX.md`
3. Note `runtime_profile`, score, and regressions vs prior baseline

## Related

- [`docs/PROJECT_GUIDE.md`](../PROJECT_GUIDE.md) — CI table + root layout
- [`docs/BUG-TRACKER.md`](../BUG-TRACKER.md) — BUG-13..16
- [`local-frontier-eval-2026-06-05.md`](../evaluations/local-frontier-eval-2026-06-05.md) — 600/600 local baseline
