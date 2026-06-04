# Centralize Configuration — Before & After

## Problem

~100 hardcoded settings were scattered across 25+ files in three inconsistent tiers:

| Tier | Mechanism | Issues |
|------|-----------|--------|
| Env vars | `.env` → `settings.py` | Incomplete — only ~25 settings exposed |
| User profile | `user_profile.py` → `data/user_profile.json` | Model config mixed with user prefs, hardcoded defaults |
| Module constants | `_CONSTANT = ...` in individual files | No override path, 4 known conflicts |

### Known Conflicts Before

| Setting | File A | Value A | File B | Value B |
|---------|--------|---------|--------|---------|
| Medium context window | `settings.py:74` | 32000 | `summarize.py:40` | 100000 |
| Medium context window | `settings.py:74` | 32000 | `complex.py:29` | 16384 |
| Cloud model name | `user_profile.py:43` | `deepseek-chat` | `llm.py:185` | `deepseek-v4` |
| Small max_tokens (non-M4) | `settings.py:131` | 1024 | `llm.py:71` | 512 |

### Before: Changing a Model Name Required

Editing the model name in **8+ files**: `user_profile.py`, `llm.py`, `graph.py`, `secret_store.py`, `complex.py`, `router.py`, `.env.example`, `settings.py`.

### Duplicated Values (same value in 3+ files)

| Value | Occurrences | Files |
|-------|------------|-------|
| `http://127.0.0.1:1234/v1` | 8+ | `user_profile.py`, `llm.py`, `web_retrieval.py`, `long_term.py`, `complex.py`, etc. |
| `https://api.deepseek.com/v1` | 6+ | `user_profile.py`, `llm.py`, `graph.py`, `secret_store.py`, `complex.py` |
| `deepseek-v4` / `deepseek-chat` | 5+ | `user_profile.py`, `llm.py`, `graph.py`, `secret_store.py` |

---

## Solution

Single source of truth: `src/config/defaults.yaml` with a layered override system.

### Priority chain (lowest → highest)

```
defaults.yaml  →  env vars  →  user_profile.json
```

### After: Changing a Model Name

Edit **one line** in `defaults.yaml` (or set the env var, or update the profile).

---

## Files Changed

### New Files
- `src/config/defaults.yaml` — All default values (~150 settings organized into 16 sections)
- `src/config/config_loader.py` — Loads YAML, applies env/profile overrides, exposes typed accessors
- `docs/changes/centralize-config/CHANGELOG.md` — This file

### Modified Files (25 files)

| File | Changes |
|------|---------|
| `src/config/settings.py` | Delegate to config_loader; keep backward-compat module variables |
| `src/memory/user_profile.py` | Remove hardcoded model/endpoint defaults; user profile only stores overrides |
| `src/agent/llm.py` | All model params from config_loader instead of inline defaults |
| `src/agent/nodes/router.py` | Context windows, budget tiers, thresholds from config_loader |
| `src/agent/nodes/complex.py` | Context window, safety margin, retries, budgets from config_loader |
| `src/agent/nodes/summarize.py` | Context window, threshold, keep_turns from config_loader |
| `src/agent/graph.py` | Context window, summarize threshold from config_loader |
| `src/agent/cloud_circuit_breaker.py` | Default thresholds from config_loader |
| `src/agent/cloud_cost_tracker.py` | Pricing from config_loader |
| `src/agent/swap_manager.py` | Base URL, timeouts from config_loader |
| `src/agent/router/classifier.py` | Max input chars from config_loader |
| `src/agent/router/selector.py` | Swap threshold, context ceiling from config_loader |
| `src/tools/web_retrieval.py` | LM Studio endpoint from config_loader |
| `src/tools/web_tools.py` | Timeouts, user-agents from config_loader |
| `src/tools/core_tools.py` | Max read chars from config_loader |
| `src/tools/notebook.py` | Output truncation from config_loader |
| `src/tools/skills.py` | Matching thresholds from config_loader |
| `src/memory/memory_manager.py` | Max memories, search window from config_loader |
| `src/memory/personal_assistant.py` | Decay constants from config_loader |
| `src/memory/long_term.py` | Qdrant/embedding config from config_loader |
| `src/agent/nodes/memory.py` | Cache TTL from config_loader |
| `src/api/server.py` | Chunk params, truncation limits, PDF rendering, budget settings from config_loader |
| `src/config/secret_store.py` | Cloud base URL/model from config_loader (fallback) |
| `src/config/audit_log.py` | Rotation sizes, sanitize max len from config_loader |
| `.env.example` | Reference new config structure |

---

## Model Swap: Qwen3.5 Family (2026-06-04)

Switched default models to the Qwen3.5 family with author-recommended tuning.

### Model Changes

| Slot | Old Model | New Model | Rationale |
|------|-----------|-----------|-----------|
| Small (router) | `liquid/lfm2.5-1.2b` | `qwen3.5-0.8b` | Qwen3.5 0.8B — 262K native context, hybrid architecture |
| Medium default | `gemma-4-e4b-uncensored-hauhaucs-aggressive` | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` | Qwen3.5 9B Q6_K — 262K context, 0/465 refusals |
| Medium vision | `zai-org/glm-4.6v-flash` | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` | Same model, natively multimodal |
| Medium longctx | `lfm2-8b-a1b` | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` | Same model, extensible to 1M tokens |

### Tuning Based on Author Recommendations

| Setting | Old | New | Source |
|---------|-----|-----|--------|
| Small context_window | 4096 | **32768** | Qwen3.5 native 262K; practical ~32K on M4 24GB |
| Medium context_window | 16384 | **32768** | Minimum 128K for thinking; ~32K practical with Q6_K |
| Longctx context_window | 131072 | **131072** | Unchanged; try if VRAM permits |
| Medium temperature | 0.4 | **0.7** | Qwen non-thinking rec: `0.7, top_p=0.8, top_k=20` |
| Medium max_tokens | 4096 | **8192** | Qwen recommends 32768 for normal, ~8K practical |
| Router input_reserves (default/longctx) | 4000 | **8000** | More room with larger context window |
| Router budget_max (other) | 8192 | **16384** | Model can handle more output |

### New: `extra_body` Support

Added `extra_body` field to model configs in `defaults.yaml` and `config_loader.py`. This is critical for Qwen3.5:

```yaml
models:
  small:
    extra_body:
      chat_template_kwargs:
        enable_thinking: false    # 0.8B prone to thinking loops
  medium:
    extra_body:
      chat_template_kwargs:
        enable_thinking: false    # Non-thinking agent mode
```

The `get_model_config()` accessor deep-merges `extra_body` from base config + variant overrides, and `llm.py` passes it to `ChatOpenAI(extra_body=...)`.

### Profile Cleanup

Cleared all model-related overrides from `data/user_profile.json` (set to empty/None) so the new YAML defaults take effect. User can still explicitly set overrides for custom models.

### Files Changed in This Update

- `src/config/defaults.yaml` — Model names, context windows, temps, extra_body, reserves/budgets
- `src/config/config_loader.py` — Deep-merge extra_body in get_model_config()
- `src/agent/llm.py` — Pass extra_body from config to ChatOpenAI constructors
- `data/user_profile.json` — Cleared model overrides (YAML now sole source of truth)

---

## Debugging Session — 3 Cycles (2026-06-04)

### Eval Trajectory

| Eval | Score | Key Finding | Response |
|------|-------|------------|----------|
| v5 (Qwen3.5 initial) | **2.44** | 33% error rate, 9/12 misrouted to simple, keyword bypass "hi" → "Chiang" | 5 bugs found + fixed |
| v6 (HITL + budgets fixed) | **3.67** | 0 errors, medium model working, 105-205s latency | Router bypasses added |
| v7-final | **~4.0 est.** | Router bypasses confirmed, preload+warmup working, 16K context stable | Ongoing |

### Bugs Found and Fixed (14 total)

| # | Bug | Symptom | Fix |
|---|-----|---------|-----|
| 1 | YAML `${...}` refs not resolved | "Connection error" | Literal URLs in defaults.yaml |
| 2 | Profile None overriding `.get()` | `float(None)` error | Removed override keys from `_DEFAULTS` |
| 3 | SwapManager empty profile | Medium model can't load | Fallback to config loader |
| 4 | `"hi"` substring → "Chiang", "which" | 6/12 misrouted to simple | Word-boundary regex `\b(...)\b` |
| 5 | GraphInterrupt in API mode | All requests empty | Skip interrupt when `mode=="api"` |
| 6 | Qwen3.5 thinking eats budget | Empty responses | Budgets: 512→1024, 8192→16384 |
| 7 | No `request_timeout` on LLMs | Infinite hangs | Added to small + medium clients |
| 8 | 0.8B handles complex tasks | Shallow reviews/writing | Keyword bypasses (code_review, creative_writing, explain_compare) |
| 9 | Budget capped at 3072 | Truncated responses | `_LONG_FORM_HINTS` → budget_max=16384 |
| 10 | Router 500-char truncation | Misses code content | `max_input_chars: 500→2000` |
| 11 | `max_cutoff_retries: 3` | Extra LLM calls | Reduced to 1 |
| 12 | API no conversation persistence | No continuity | Accept optional `thread_id` |
| 13 | LM Studio startup race | 0s failures on first call | Preload + warmup both models |
| 14 | LM Studio n_ctx=8192 too small | Prompt exceeds context | Set to 32768 in LM Studio; code-side cap at 16384 |

### Config Audit — True Single Source of Truth

- 4 missing YAML entries added (`models.cloud.context_window`, `request_timeout`, voice settings)
- 6 stale code fallbacks synced to match YAML
- `ConfigValidator` checks 60+ paths at startup
- `validate_config()` → 0 missing, 0 warnings
- Dev-startup guide updated with config contract + env var table

### Quick Improvements

| Item | Change |
|------|--------|
| Web search timeout | `asyncio.wait_for(search, 60s)` aggregate cap |
| Thinking artifact stripping | Enhanced `<think>` + `Thinking Process:` removal |
| Topics manifest | "## Topics Discussed" section in summarization |
| mem0 deps | `mem0ai[nlp]` for spaCy/fastembed |

### Model Preloading

Both models now preload + warmup at server startup:
- Small (0.8B): client created → 3s settle → inference call "hi"
- Medium (9B): swap if needed → client created → 3s settle → inference call "hi"
- Prevents 0-second first-call failures

### Current Model Config

| Slot | Model | Context | Temp | Max Tokens |
|------|-------|---------|------|------------|
| Router | `qwen3.5-0.8b` | 16384 | 0.2 | 1024 |
| Complex | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` | 16384 | 0.7 | 16384 |
| Cloud | `deepseek-v4` | 131072 | 0.4 | 8192 |

### To Swap Models

Edit 2 lines in `src/config/defaults.yaml`:
```yaml
models:
  small:
    model_name: "your-router-model"        # Line ~43
  medium:
    variants:
      default:
        model_name: "your-complex-model"   # Line ~70
```

Override priority: **defaults.yaml → env vars → user_profile.json**

---

## Remaining Tasks

### 🔴 High Impact

| # | Task | Why | Effort | Files |
|---|------|-----|--------|-------|
| **R1** | One-turn lag — message correlation IDs | 40% eval losses from browser client sending next prompt before response completes | 2-3 hrs | `server.py`, frontend WS handler |
| **R5** | Response coherence check | System never detects wrong answers; confidence always 95% regardless of quality | 1-2 hrs | new module |
| **R2** | Inference latency reduction | 105-276s vs SLO <8s. Explore Q4_K_M or smaller models | Investigation | `defaults.yaml` |

### 🟡 Medium Impact

| # | Task | Why | Effort | Files |
|---|------|-----|--------|-------|
| **R3** | Cloud fallback test with valid DeepSeek key | Ensure cloud escalation path works end-to-end | 15 min | `complex.py`, `llm.py` |
| **R7** | Verify web search aggregate timeout | Coded with `asyncio.wait_for(search, 60s)` but never tested with live SearXNG | 15 min | `web_tools.py` |
| **R9** | Verify API thread persistence | `thread_id` parameter coded, never tested end-to-end | 15 min | `server.py` |
| **R8** | M4 thermal throttling mitigation | Battery + no cooling = 160-276s latency. AC power recommended | Hardware | N/A |

### 🟢 Documentation & Code Health

| # | Task | Effort |
|---|------|--------|
| D1 | Decompose `server.py` (2283 lines) into `api/routes/*.py` | 3-4 hrs |
| D2 | Refactor `complex.py` (1194 lines) — extract FallbackExecutor, ToolBinder | 2-3 hrs |

### Completed ✅

| # | Task | Commit |
|---|------|--------|
| F1-F14 | Config centralization + 14 bugs | `bb04b25` → `376d140` |
| B1-B7 | Router bypasses + request_timeout + budgets | `6da48bd` |
| C1-C2 | Config audit + validation | `4011a27` |
| R7/R10/R6/R12 | Web search timeout, think stripping, topics, deps | `0d1f15c` |
| Preload | Both models preload + warmup at startup | `acd9f8d` |
| Context | 16K practical windows + 600s timeout | `6367323` |
| D5/D6/F3 | HITL.md, MEMORY.md, README, INDEX, architecture overview | `ce736b5` → `4ea8223` |
| Long eval | 6/17 completed (thermal throttle on battery) | `df51a4e` |
