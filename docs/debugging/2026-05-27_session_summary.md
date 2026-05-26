# Session Summary — 2026-05-27

## Overview

Four investigations executed in parallel across the OwlynnV2 codebase. Below is the synthesis of all findings, fixes applied, and remaining issues.

---

## 1. Embedding Model Identifier Fix

### Problem
```
Invalid model identifier "text-embedding-nomic-embed-text-v1.5@f16"
```
The `@f16` quantization suffix is not valid in Ollama model identifiers. Three files still had stale references.

### Fix Applied
| File | Line | Change |
|------|------|--------|
| `docs/WEB_SEARCH.md` | 150 | `@f16` → `-embedding` |
| `.env.example` | 48 | `@f16` → `-embedding` |
| `tests/test_qdrant_memory_config.py` | 11 | `@f16` → `-embedding` |

Runtime code (`src/memory/long_term.py:31`, `src/config/settings.py:43`) was already correct.

### Verification
- Zero `@f16` occurrences remain in the codebase
- `test_qdrant_memory_config.py` now passes

---

## 2. Logging System Wiring & Bugs

### Status: Already Fully Wired
All integration points were already in place:
- `setup_logging()` called in FastAPI lifespan (`server.py:69`)
- `AuditLogMiddleware` attached (`server.py:142-143`)
- All 10 LangGraph nodes decorated with `@log_node`
- `log_model_attempt` — 9 calls in `complex.py` for fallback chain tracking
- `log_hitl_event` — 6 calls in `security_proxy.py`, 2 in `plan_review.py`, 1 in `scope_clarify.py`
- `set_thread_id()` propagated from `GraphSession._execute` for audit context
- 33 audit log unit tests in `tests/test_audit_log.py`

### Bug 1: Silent Audit Log Drop on Stdout
**File**: `src/config/logging_config.py` line 72  
**Cause**: `_setup_audit_stdout_handler` set `propagate=False` but never called `setLevel()` on the audit logger. Combined with `_setup_audit_file_output` silently passing on profile read failure (no `finally`), the audit logger stayed at default WARNING level — silently dropping all INFO/DEBUG events on stdout.  
**Fix**: Added `audit_logger.setLevel(level)` + wrapped profile read in `try/finally`.

### Bug 2: Teardown Wiped All Handlers
**File**: `src/config/audit_log.py` line 270  
**Cause**: `_teardown_file_handler` removed ALL handlers from the audit logger, including the stdout handler. When `OWLYNN_AUDIT_LOG_ENABLED=0` (CI/tests), all audit output was silenced.  
**Fix**: Filter to only remove `RotatingFileHandler` instances.

### Test Results
- 33/33 audit log tests — PASS
- 9/9 graph tests — PASS
- 864/864 full suite — PASS (1 pre-existing Redis failure unrelated)

---

## 3. Comprehensive Integration Test

### Test Prompt
Comparison of Python FastAPI vs Express.js — requested web search, file write (comparison.md), mermaid diagram, preference memory for type-safe languages.

### Flow Trace
```
router → scope_clarify (skipped) → complex_llm → security_proxy (safe) 
       → tool_action (web_search) → complex_llm (2nd pass, no tools) 
       → security_proxy (no tools) → memory_write
```

### Results: 6/8 Checks Passed

| Check | Status |
|-------|--------|
| Router emitted accurate metadata | PASS |
| web_search tool executed | PASS |
| Structured output (table + mermaid) | PASS |
| Memory: topics/interests/LTM/cache | PASS |
| Thread history clean | PASS |
| Status reached idle | PASS |
| File write invoked | FAIL — agent hallucinated, never called tool |
| Multiple tool types used | FAIL — only web_search, no file I/O |

### Additional Issues Found

**Mem0 search API bug** (`server.py:483`): `user_id` passed as top-level param to `mem0_memory.search()` but Mem0 library expects `filters={"user_id": "..."}`. All `/api/mem0/search` calls return errors.

**STM not populated**: Short-term memory (`memories.json`) empty — agent only wrote to Mem0 LTM.

**Token budget low**: 1536 tokens for complex multi-step task resulted in 70s second LLM pass.

### Documentation
Full report: `docs/debugging/system_integration_test_2026-05-27.md`

---

## 4. Stale Model Loading Analysis

### Embedding Model Auto-Load
**No auto-pull/load exists.** `server.py:90-91` explicitly states:
> Embedding models are pre-pulled manually via `ollama pull` or LM Studio UI. The app relies on them being already available; no auto-load at startup.

The `text-embedding-nomic-embed-text-v1.5-embedding` model is referenced in live code at:
- `src/config/settings.py:43` — default config
- `src/memory/long_term.py:31` — Mem0 embedder config
- `tests/test_qdrant_memory_config.py:11` — test assertion

These are config references (telling Mem0 which model to use for embeddings), not load/pull commands.

### Qwen Model References
**Zero qwen references exist in Python source code.** All occurrences are in documentation:
- `docs/debugging/system_integration_test_2026-05-27.md` — test report (recording what was used)
- `docs/debugging/browser-verification.md` — historical crash report
- `docs/debugging/llm-pool.md` — swap manager log examples
- `docs/debugging/memory-analysis.md` — memory budget analysis
- `docs/guides/lm_studio.md` — LM Studio compatibility note

### What Actually Uses Qwen
The medium LLM is loaded at startup by `server.py:81-88`:
```python
await LLMPool.get_medium_llm("default")
```
This resolves the model name from the user profile (`medium_models["default"]`). The code default is `"medium-default-model"` (a placeholder), with a hardcoded fallback to `"gemma-4-e4b-uncensored-hauhaucs-aggressive"` in `llm.py:131`.

**The integration test showed `qwen3.5-9b-mlx` in use because the live server's profile was configured with that model.** The code itself does not hardcode qwen anywhere.

### Action Needed
1. Check the running profile: `curl http://127.0.0.1:8000/api/profile` to see what `medium_models.default` is set to
2. If it's a qwen variant, update it to the desired model (e.g., gemma)
3. Update `user_profile.py:45` default from `"medium-default-model"` to the actual model name to avoid confusion

---

## Consolidated Action Items

### Priority 1 — Fix Now
1. **Mem0 search API** — change `user_id=user_id` to `filters={"user_id": user_id}` in `server.py:483`
2. **Profile model name** — update `user_profile.py:45` default from `"medium-default-model"` to `"gemma-4-e4b-uncensored-hauhaucs-aggressive"` (matches the hardcoded fallback)

### Priority 2 — Improve
3. **Tool-call compliance** — investigate why the agent omitted `write_workspace_file` in the second LLM pass. Consider adding post-generation validation or stronger system prompt for multi-step plans.
4. **Token budget** — increase from 1536 to 4096 for complex multi-step tasks
5. **STM population** — add short-term memory write in `memory_write` node alongside Mem0 LTM

### Priority 3 — Polish
6. **@log_node enrichment** — currently node lifecycle events don't carry method/function enrichment. Wire `@log_node` decorator into graph nodes for richer telemetry.
7. **Profile model mapping clarity** — consider removing the `medium-default-model` placeholder and using actual model names throughout

---

## No Logging Plan File Found
Searched for `*.plan.md`, `*logging*plan*`, and `*e999dbc9*` across the entire repository — zero results.
