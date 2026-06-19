# Cloud-Only Pivot (2026-06-19)

## Summary

Pivoted OwlynnV2 from 3-tier model architecture (router → local Qwen → cloud) to **2-tier cloud-only** (router → vision → complex-cloud DeepSeek V4), removing all local Qwen fallback paths, and shipped the R5 coherence self-correction loop.

## Motivation

- Mac M4 Air 24GB — local Qwen 9B caused 2–3 min response times, battery drain, and thermal throttling
- DeepSeek V4 is the main workhorse; local Qwen eliminated
- `complex-default` route removed entirely; all complex reasoning → `complex-cloud`

## Changes

### Configuration (`src/config/`)

- **Removed** `models.medium` block from `defaults.yaml`
- **Added** `models.extraction` with `gemma-4-e2b-heretic-uncensored-mlx`
- **Removed** `require_medium_when_cloud_unavailable`, `cloud.no_local_fallback`
- **Removed** `MEDIUM_*` env var maps from `config_loader.py`
- `settings.py`: `MEDIUM_*` constants → `CLOUD_CONTEXT` aliases (backward compat for router)
- **Removed** `get_model_config()` medium special handling

### Core Source (`src/agent/`)

- **Removed** `medium` route labels from `state.py`: `complex-default`, `medium-*` labels, `current_medium_model`
- **Removed** `complex-default` edges from `graph.py`; added `coherence_retry_gate`
- **Removed** 7 medium fallback chains from `complex.py` (all → cloud-only)
- **Updated** `simple.py`: retry-once MiniCPM5 (no medium fallback)
- **Deleted** `cloud_strict.py` (strict-cloud concept removed entirely)
- **Added** `coherence_retry.py`: R5 self-correction node (cloud-only, no local fallback)
- `llm.py`: removed `_medium_llm` slot + `get_medium_llm()`; added `get_extraction_llm()`
- `server.py`: removed medium preload/warmup
- `extraction/worker.py`: switched to `get_extraction_llm()`
- `openai.py`/`cli.py`: default model → `minicpm5-1b`
- `user_profile.py`: removed `cloud_no_local_fallback`

### Router (`src/agent/router/`)

- All `complex-default` references → `complex-cloud`
- `classifier.py`, `selector.py`, `models.py`, `budget.py`: removed medium-variant logic
- Florence-unavailable fallback: routes to `complex-cloud` with `task_category=vision_fallback`

### R5 Coherence Self-Correction

- New node: `src/agent/nodes/coherence_retry.py`
- Gate: `coherence_retry_gate` conditional edge in graph
- Config: `coherence.max_retries: 1`, threshold 0.4
- Cloud-only (no local Qwen rewrite fallback)

### Tests (26 files updated)

- All route/model/import references updated to cloud-only
- Rewrote `test_cloud_strict_mode.py` (removed strict-cloud tests)
- Rewrote `test_coherence_retry_node.py` (new coverage)
- Updated `test_frontier_eval_scoring.py`: `CLOUD_QWEN_FALLBACK_BADGES` → `CLOUD_FAILURE_BADGES`
- Updated `test_memory_nodes.py`, `test_unified_settings.py`

### Eval Scripts

- Removed `eval_cloud_qwen_fallback()` from all eval scripts
- Removed `CLOUD_QWEN_FALLBACK_BADGES` constant → `CLOUD_FAILURE_BADGES`
- Updated `run_local_frontier_eval.py`, `run_educator_eval.py`, `run_browser_eval.py`

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `complex-default` removed entirely (not aliased) | Cleanest refactor, ~30 tests simplified |
| Memory extraction → Gemma-4-E2B | Small model, always loadable, no cloud cost |
| Simple node → retry-once MiniCPM5 | Cheap, on-device; no medium fallback needed |
| Strict-cloud concept removed | Cloud is default; no local fallback to block |
| `MEDIUM_*` constants aliased to `CLOUD_CONTEXT` | Keep router code compiling during transition |

## Deleted Files

- `src/agent/cloud_strict.py`
- (All imports updated)

## Verification

- **CI green**: ruff, mypy, 1058 pytest (0 failed), 22 contract, 135 vitest
- **LM Studio**: Extraction model loads, no medium slot needed
- **Playwright MCP**: Host-native (npx), no podman container

## Related

- [`docs/changes/coherence-self-correction/CHANGELOG.md`](../coherence-self-correction/CHANGELOG.md) — R5 loop
- [`docs/STATUS.md`](../../STATUS.md) — current project state
- [`docs/architecture/DEEPSEEK_V4_INTEGRATION.md`](../../architecture/DEEPSEEK_V4_INTEGRATION.md) — DeepSeek V4 integration
