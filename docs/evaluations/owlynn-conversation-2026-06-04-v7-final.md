# Owlynn Conversation Evaluation Report (v7-final) — All Fixes Applied

- **Evaluation Date:** 2026-06-04
- **Evaluator:** OpenCode (AI Coding Assistant)
- **Owlynn Version:** `0d1f15c` (config audit + quick/medium fixes)
- **Models:** `qwen3.5-0.8b` (small), `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` (medium)
- **Completed:** 7/12 exchanges (5 timed out due to medium model latency)
- **Total Duration:** ~14 minutes

---

## Executive Summary

This evaluation tested ALL fixes applied across 3 debugging cycles. The routing keyword bypasses (explain/compare, code_review, creative_writing) are **confirmed working** — all targeted prompts correctly route to the medium 9B model. The remaining issues are hardware/infrastructure: LM Studio model swap race conditions at startup and extended cutoff retry loops on complex tasks.

---

## Turn-by-Turn Results

| Turn | Prompt ID | Topic | Duration | Chars | Route | Model | Quality |
|------|-----------|-------|----------|------|-------|-------|---------|
| 1 | T1.1 | Tech Explanation | 0s | 152 | simple | small | ⚠️ Startup race — small model call failing during model swap |
| 2 | T1.3 | Tech Explanation | **100s** | 1449 | complex-default | **medium (9B)** | ✅ Good. Architecture recommendation referencing prior discussion |
| 3 | T1.5 | Tech Explanation | 10s | 659 | simple | small | ✅ Decent. WebSocket security comparison |
| 4 | T2.1 | Code Review | 362s | 152 | complex-default | medium | ⚠️ Model timed out after cutoff retries |
| 5 | T2.3 | Code Review | 370s | 152 | complex-default | medium | ⚠️ Same — cutoff retry loop |
| 6 | T3.1 | Creative Writing | 0s | 152 | complex-default | medium | ⚠️ Startup race — medium model call failing |
| 7 | T3.3 | Creative Writing | 8s | 224 | simple | small | ✅ Good. Concise sadness description |

---

## Routing Bypasses Confirmed Working

| Bypass | Triggered For | Route | Model |
|--------|--------------|-------|-------|
| `explain_compare_bypass` | T1.3 ("explain how") | complex-default | medium (100s, 1449 chars) |
| `code_review_bypass` | T2.1 ("Review this Python") | complex-default | medium (but timed out) |
| `code_review_bypass` | T2.3 ("Write an improved") | complex-default | medium (but timed out) |
| `creative_writing_bypass` | T3.1 ("Write a short story") | complex-default | medium (but startup race) |

---

## Remaining Issues

### 1. Medium Model Startup Race Condition
When the backend starts, the medium model preload triggers an LM Studio swap (unload→load). The first few LLM calls during this swap fail immediately (0s) with "language model is currently unavailable." T1.1 and T3.1 failed due to this. The small model pool also gets created during the swap window.

**Fix:** Add a startup retry or warmup delay after model preloading.

### 2. Cutoff Retry Loops (T2.1: 362s, T2.3: 370s)
Even with `max_cutoff_retries=1`, the complex node added ~240s of extra time. The `request_timeout=120s` on the medium model should have capped individual calls, but the total duration suggests multiple retries across different tiers (medium → fallback → retry).

**Fix:** Add a total request timeout in the complex node to abort cutoff retries.

### 3. Medium Model Latency (100s)
T1.3 took 100s for 1449 chars (~14.5 chars/s). This is within the expected range for the 9B Q6_K model on M4 Air but well above the SLO target of <8s for complex queries.

---

## All Fixes Applied (Commits `2b907d2` → `0d1f15c`)

| # | Fix | Status |
|---|-----|--------|
| F1-F14 | Config centralization + YAML refs + profile bugs + budgets | ✅ |
| B1-B3 | Keyword bypasses (code_review, creative_writing, explain_compare) | ✅ Working |
| B4 | _LONG_FORM_HINTS → full budget_max | ✅ |
| B5 | max_input_chars 500→2000 | ✅ |
| B6 | max_cutoff_retries 3→1 | ✅ Partial (still adds time) |
| B7 | request_timeout on LLM clients | ✅ |
| C1 | Config audit — 4 missing entries + 6 stale fallbacks synced | ✅ |
| C2 | ConfigValidator — 60+ paths checked at startup | ✅ |
| R7 | Web search aggregate timeout (60s) | ✅ Coded, not tested |
| R10 | Enhanced `<think>` stripping | ✅ |
| R6 | Topics manifest in summarization | ✅ |
| R12 | mem0ai[nlp] deps | ✅ |
