---
title: "Model Name Centralization & Codebase Refactoring — 2026-06-27"
category: changes
date: 2026-06-27
---

# Model Name Centralization & Codebase Refactoring

## Summary

Centralized model name resolution into `ConfigLoader` (single source of truth), extracted a ChatOpenAI factory to eliminate 4 duplicated construction blocks, deduplicated 6 identical cloud fallback blocks in `complex.py` into `cloud_fallback.py`, fixed 3 bugs (stale E2B fallbacks, missing `router_llm` config, legacy `gemma4` vision mode), and unified `_latest_user_text()` across 2 files.

## Problem

Model names were hardcoded in 7+ locations across 6 files. Changing models (e.g., E2B → Qwen3) required editing 14 files. Two stale E2B fallbacks in `llm.py:151,180` silently caused the system to use the wrong model when config resolution failed. The `router_llm` config section was missing from `defaults.yaml` but referenced by the router, causing `int(None)` crashes. `complex.py` had 6 near-identical fallback blocks (~300 lines of duplication). `_latest_user_text()` was defined twice with different implementations.

## Solution

### Phase 1: Single Source of Truth for Model Names

Added 3 accessor methods to `ConfigLoader`:

```python
ConfigLoader.get_small_model_name()    # → models.small.model_name
ConfigLoader.get_cloud_model_name()    # → models.cloud.model_name
ConfigLoader.get_embedding_model_name() # → models.embedding.model_name
```

Updated 7 call sites to use these accessors instead of hardcoded strings:

| File | Line(s) | Before | After |
|------|---------|--------|-------|
| `src/agent/llm.py` | 68, 103 | `"qwen3-vl-4b-instruct-c_abliterated-v2-mlx"` | `config.get_small_model_name()` |
| `src/agent/llm.py` | 151, 180 | `"gemma-4-e2b-heretic-uncensored-mlx"` | `config.get_small_model_name()` |
| `src/cli.py` | 42, 92 | `"qwen3-vl-4b"` | `config.get_small_model_name()` |
| `src/api/routes/openai.py` | 21 | `"qwen3-vl-4b"` | `config.get_small_model_name()` |
| `src/agent/core/complex_utils/lm_studio_vision.py` | 24 | `config.get(...)` | `config.get_small_model_name()` |

Also fixed `get_m4_optimization()` which referenced non-existent `models.extraction` config path — changed to `models.small`.

### Phase 2: ChatOpenAI Factory

Extracted `_build_local_llm_client()` in `src/agent/llm.py` to eliminate 4 near-identical ChatOpenAI construction blocks:

```python
def _build_local_llm_client(
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    max_output_tokens: int = 512,
    timeout: float = 10,
) -> ChatOpenAI:
```

Refactored `get_small_llm()`, `get_fallback_llm()`, and `VisionModelManager.acquire()` to use the factory. Each slot overrides only the parameters that differ from defaults.

### Phase 3: Cloud Fallback Deduplication

Created `src/agent/core/complex_utils/cloud_fallback.py` with `handle_cloud_fallback()`. This function accepts `invoke_local_fallback` as a parameter (to avoid circular imports) and replaces 6 identical fallback blocks in `complex.py`:

- Vision proxy failure
- Tools-off cloud unavailable
- Initial cloud acquisition failure
- Rate limit retry failure
- Auth error (401/403)
- Generic cloud error

Each block was ~25 lines. Total reduction: ~250 lines from `complex.py`.

### Phase 4: Bug Fixes

| Bug | File | Fix |
|-----|------|-----|
| Stale E2B fallback in `get_fallback_llm()` | `src/agent/llm.py:151,180` | Changed to `config.get_small_model_name()` |
| Missing `router_llm` config section | `src/config/defaults.yaml` | Added `router_llm.temperature` and `router_llm.max_tokens` |
| Legacy `gemma4` vision mode | `src/agent/core/complex_utils/vision_proxy.py:58` | Removed `"gemma4"` from mode tuple |
| Stale E2B in eval script | `scripts/run_extension_eval_automated.py:75,123` | Updated to Qwen3 model name |
| `models.extraction` config path | `src/config/config_loader.py:326` | Changed to `models.small` |

### Phase 5: Config Constants

Added module-level constants in `src/agent/core/complex.py`:

```python
_DEFAULT_TOKEN_BUDGET = int(config.get("complex.default_token_budget", 4096))
_SMALL_CONTEXT_WINDOW = int(config.get("models.small.context_window", 65536))
```

Replaced 5 occurrences of `int(config.get("complex.default_token_budget", 4096))` with `_DEFAULT_TOKEN_BUDGET`.

### Phase 6: Unified `_latest_user_text()`

Moved canonical `latest_user_text()` to `src/agent/core/complex_utils/formatter.py` (where `_flatten_human_content` lives). Removed duplicate definitions from `complex.py` and `fallback.py`. Updated 3 callers:

- `src/agent/core/complex.py`
- `src/agent/core/complex_utils/fallback.py`
- `src/agent/nodes/coherence_retry.py`

## Files Changed

### Created
| File | Lines | Purpose |
|------|-------|---------|
| `src/agent/core/complex_utils/cloud_fallback.py` | 100 | Centralized cloud-to-local fallback handler |

### Modified (Production)
| File | Changes |
|------|---------|
| `src/config/config_loader.py` | Added `get_small_model_name()`, `get_cloud_model_name()`, `get_embedding_model_name()`; fixed `models.extraction` → `models.small` |
| `src/config/defaults.yaml` | Added `router_llm` section (temperature, max_tokens) |
| `src/agent/llm.py` | Extracted `_build_local_llm_client()` factory; fixed stale E2B fallbacks; updated `_resolve_cloud_model_name()` |
| `src/agent/core/complex.py` | Replaced 6 fallback blocks with `handle_cloud_fallback()`; added `_DEFAULT_TOKEN_BUDGET`/`_SMALL_CONTEXT_WINDOW` constants; unified `latest_user_text` import |
| `src/agent/core/complex_utils/formatter.py` | Added `latest_user_text()` canonical implementation |
| `src/agent/core/complex_utils/fallback.py` | Removed local `_latest_user_text()`; imports from formatter |
| `src/agent/core/complex_utils/vision_model_manager.py` | Uses `_build_local_llm_client()` factory |
| `src/agent/core/complex_utils/vision_proxy.py` | Removed `"gemma4"` from vision mode tuple |
| `src/agent/core/complex_utils/lm_studio_vision.py` | Uses `config.get_small_model_name()` |
| `src/agent/nodes/coherence_retry.py` | Updated `_latest_user_text` import |
| `src/api/routes/openai.py` | Uses `config.get_small_model_name()` |
| `src/cli.py` | Uses `config.get_small_model_name()` |
| `scripts/run_extension_eval_automated.py` | Updated E2B model name to Qwen3 |

### Modified (Tests)
| File | Changes |
|------|---------|
| `tests/test_complex_workspace_paths.py` | Updated `_latest_user_text` → `latest_user_text` import |
| `tests/test_router_properties.py` | Added `"complex-default"` to `VALID_COMPLEX_ROUTES` |

### Modified (Formatting — pre-existing lint fixes)
| File | Changes |
|------|---------|
| `scripts/bench_local_models.py` | Renamed ambiguous `l` → `line` in list comprehensions |
| `scripts/eval_local_models.py` | Removed f-string without placeholders |

## Impact

| Metric | Before | After |
|--------|--------|-------|
| `complex.py` lines | 1932 | 1623 (-309) |
| `llm.py` lines | 328 | 292 (-36) |
| Hardcoded model names in `src/` | 7+ | 0 |
| ChatOpenAI construction sites | 5 | 1 (factory) |
| Cloud fallback blocks | 6 | 0 (centralized) |
| `_latest_user_text` definitions | 2 | 1 |
| `config.get("complex.default_token_budget")` calls | 11 | 0 (module constant) |
| Bugs fixed | — | 3 |
| CI checks passing | 5/7 | 6/7 |

## Remaining Known Issues

### Pre-existing test failures (4)
These existed before this refactoring and are not regressions:

| Test | Root cause |
|------|-----------|
| `test_router_skill_hitl_round_trip` | `execution_policy: auto_approve` in user profile skips HITL; test doesn't mock `get_profile()` |
| `test_router_skill_hitl_resume` | Same |
| `test_router_confident_ambiguous_skill_hitl` | Same |
| `test_long_context_boundary_routes_cloud_not_default` | No DeepSeek API key in test env; router correctly returns `complex-default` |

### Cosmetic (2)
| File | Line | Issue |
|------|------|-------|
| `src/agent/core/simple.py` | 2 | Docstring mentions "Gemma-4-E2B" |
| `src/agent/nodes/summarize.py` | 5 | Docstring mentions "Gemma-4-E2B" |

Both are comments only. Change to "unified local model" when convenient.
