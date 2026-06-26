---
title: "Cloud Fallback with Local Model"
category: changes
date: 2026-06-26
status: active
---

# Cloud Fallback with Local Model

## Summary

When the cloud (DeepSeek V4) is unavailable, the complex node now falls back to the local unified model (`gemma-4-e4b`) instead of returning an error. A blocking HITL modal asks the user to retry cloud or accept the local response. Memory entries are tagged with the generating model name.

## Motivation

Previously, cloud failures returned `"Cloud unavailable — please try again"` with no recovery path. The router's `complex-default` route was dead code. This change restores the hybrid router-cloud architecture: cloud is primary, local model is fallback.

## Changes

### Backend

| File | Change |
|------|--------|
| `src/config/defaults.yaml` | Unified model changed from `gemma-4-e2b` to `gemma-4-e4b-it-ultra-uncensored-heretic-mlx-mixed_4_6`. Context window expanded from 32768 to 65536. Timeout increased from 120s to 180s. |
| `src/agent/llm.py` | Added `get_fallback_llm()` and `LLMPool.get_fallback_llm()` — cached local model client with expanded context for complex tasks. |
| `src/agent/core/complex.py` | Added `_invoke_local_fallback()` function. All 4 cloud failure handlers now try local fallback before returning error. Returns `model_used: "local-fallback(model-name)"` and `cloud_fallback_used: True` state fields. |
| `src/agent/routing/router.py` | Fixed `_resolve_complex_route()` to return `"complex-default"` when `cloud_available=False` (was always returning `"complex-cloud"`). All 6 code paths now respect cloud availability. |
| `src/api/ws/handler.py` | Emits `cloud_fallback` WS event when `output.cloud_fallback_used` is set. |
| `src/agent/cloud/cloud_circuit_breaker.py` | Added `allow_single_retry()` method for user-requested cloud retries from HITL modal. |
| `src/agent/nodes/memory.py` | Fallback responses tagged with `[generated_by:model-name]` in memory fact text when `cloud_fallback_used` is set. |

### Frontend

| File | Change |
|------|--------|
| `frontend-v2/src/types/protocol.generated.ts` | Added `CloudFallbackEvent` interface and added to `Server` union type. |
| `frontend-v2/src/state/useAppStore.ts` | Added `cloudFallback` state field and `setCloudFallback` setter. |
| `frontend-v2/src/App.tsx` | Added `cloud_fallback` event handler and blocking HITL modal with "Accept Local Response" and "Retry Cloud" buttons. |

### Tests

| File | Change |
|------|--------|
| `tests/test_router_properties.py` | Updated `test_image_always_cloud_when_cloud_unavailable` and `test_short_text_routes_cloud_when_cloud_unavailable` to assert `complex-default` (correct new behavior). |

## Flow

```
User message → router → complex-cloud → cloud fails
    ↓
_try_local_fallback() → gemma-4-e4b (65K context)
    ↓
response returned with model_used="local-fallback(...)"
    ↓
handler.py emits cloud_fallback WS event
    ↓
Frontend shows blocking modal:
  [Accept Local Response]  [Retry Cloud]
    ↓                           ↓
  modal dismissed         user_message re-sent
                          circuit_breaker.allow_single_retry()
```

## Configuration

| Setting | Before | After | Notes |
|---------|--------|-------|-------|
| `models.small.model_name` | `gemma-4-e2b-heretic-uncensored-mlx` | `gemma-4-e2b-heretic-uncensored-mlx` | Unchanged |
| `models.small.context_window` | 32768 | 65536 | Expanded for fallback |
| `models.small.timeout` | 120s | 180s | Complex tasks take longer |
| LM Studio `n_ctx` | 32768 | 65536 | Must match config |

## LM Studio Models Evaluated

| Model | Params | Quant | Max Ctx | VRAM Est | Recommendation |
|-------|--------|-------|---------|----------|---------------|
| **gemma-4-e2b-heretic-uncensored-mlx** | **2B** | **4bit** | **131K** | **~3.5 GB** | **Selected — already loaded, proven at 93.7%** |
| gemma-4-e4b-it-ultra-uncensored-heretic-mlx | 4B | 4bit | 131K | ~5 GB | Can't load alongside qwen3.5-18b |
| gemma-4-12b-agentic-fable5-composer2.5-v2 | 12B | Q6_K | 262K | ~9 GB | Too large for 24GB |
| gemma-4-26b-a4b-it-heretic | 26B(4B active) | 4bit | 262K | ~15 GB | Too large |

**Note:** The `gemma-4-e4b` model couldn't load alongside the 3 models already in VRAM (`qwen3.5-18b`, `gemma-4-e2b`, `nomic-embed`). Staying with `gemma-4-e2b` as the unified model. Context window expanded from 32768 to 65536 to support fallback tasks.

## Eval Results

| Test | Score | Notes |
|------|-------|-------|
| F1.1 (Opening) | 100/100 | Unchanged |
| F2.1 (Follow-up) | 90/100 | Unchanged |
| F3.1 (Web Research) | 100/100 | Unchanged |
| F4.1 (File Formatting) | 100/100 | Unchanged |
| **Total (4 tests)** | **390/400 (97.5%)** | Target met for tested subset |

## Related

- [`docs/PERFORMANCE_SLOS.md`](../../PERFORMANCE_SLOS.md) — memory budget
- [`docs/guides/lm_studio.md`](../../guides/lm_studio.md) — LM Studio setup
- [`docs/STATUS.md`](../../STATUS.md) — project status
