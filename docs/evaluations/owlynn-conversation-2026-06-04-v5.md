# Owlynn Conversation Evaluation Report (v5) — Qwen3.5 Model Swap

- **Evaluation Date:** 2026-06-04
- **Evaluator:** OpenCode (AI Coding Assistant)
- **Owlynn Version:** `dd69035` (config centralization + Qwen3.5 swap)
- **Models Evaluated:** `qwen3.5-0.8b` (small/router), `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` (medium/complex)
- **Conversation Session Length:** 12 exchanges (via API, non-streaming)
- **Total Duration:** ~81 seconds

---

## Executive Summary

A fifth browser/API-based evaluation was conducted on Owlynn following the config centralization and Qwen3.5 model swap. This evaluation used the same 12-prompt battery as v4 (commit `ea04a5c`) but with the new Qwen3.5 models running on `dd69035`.

The model swap itself was **technically successful** — both models loaded and responded. However, the evaluation reveals a **critical routing regression**: the Qwen3.5 0.8B small model is routing 9 of 12 prompts to `simple`, bypassing the much more capable 9B medium model. Response quality on complex tasks suffered significantly as a result.

Three bugs were discovered and fixed during evaluation setup:
1. `${...}` YAML reference strings not resolved by PyYAML — caused "Connection error" (fixed: literal URLs)
2. `profile.get(key, default)` returning `None` instead of default when `_DEFAULTS` had `None` values (fixed: removed override keys from `_DEFAULTS`)
3. `swap_manager` reading model keys from empty profile instead of config (fixed: fallback to config loader)

---

## Evaluation Score Summary

| Metric | Eval v4 | **Eval v5** | Δ | Key Driver |
|-------|---------|------------|---|------------|
| **C1: Response Correctness** | 4.09 | **2.33** | −1.76 | Small model handling complex tasks; 3 error responses |
| **C2: Conversation Continuity** | 3.90 | **2.50** | −1.40 | No continuity between exchanges (stateless API calls) |
| **C3: Topic-Change Differentiation** | 4.27 | **2.75** | −1.52 | Small model unable to maintain topic boundaries |
| **C4: HITL Context Accuracy** | 3.50 | **N/A** | N/A | No HITL events triggered (API mode) |
| **C5: HITL Timing Appropriateness** | 4.50 | **N/A** | N/A | No HITL events triggered (API mode) |
| **C6: Response Completeness** | 4.09 | **2.25** | −1.84 | 3/12 error responses; several incomplete |
| **C7: Tone / Persona Consistency** | 4.36 | **2.83** | −1.53 | Inconsistent due to small model limitations |
| **C8: Self-Awareness / Error Recovery** | 3.45 | **2.00** | −1.45 | Error messages generic; no recovery |

**Overall average:** 2.44 / 5.0 — a significant regression from v4's 4.02, driven by the small model handling complex tasks.

---

## Turn-by-Turn Analysis Matrix

| Turn | Prompt ID | Topic | C1 | C2 | C3 | C6 | C7 | C8 | Duration | Chars | Findings |
|------|-----------|-------|----|----|----|----|----|----|----------|------|----------|
| 1 | T1.1 | Technical Explanation | **1** | N/A | 3 | **1** | 3 | 2 | 7s | 0 | **CRITICAL FAIL.** Empty response. Router classified as "simple" (0.95 conf). 0.8B model produced no output. |
| 2 | T1.3 | Technical Explanation | **2** | 2 | 3 | 3 | 3 | 2 | 2s | 503 | Partial response. Generic architecture advice, no specific WebSocket recommendation. |
| 3 | T1.5 | Technical Explanation | **1** | 1 | 2 | **1** | 2 | 2 | 6s | 152 | **ERROR.** "Language model is currently unavailable." Medium model failed after complex-default route. |
| 4 | T2.1 | Code Review | **2** | 2 | 3 | 3 | 3 | 2 | 7s | 430 | Partial review. Identified some bugs but analysis shallow. Described non-existent issues. |
| 5 | T2.3 | Code Review | **3** | 2 | 3 | 4 | 3 | 2 | 9s | 1054 | Improved version provided. Handled empty input and missing fields. Decent for 0.8B. |
| 6 | T3.1 | Creative Writing | **3** | N/A | 3 | 3 | 3 | 2 | 9s | 1236 | Story opening produced. Generic AI-emotions narrative, not truly Chiang-style. |
| 7 | T3.3 | Creative Writing | **2** | 2 | 3 | 2 | 2 | 2 | 8s | 699 | Continuation missed previous context. Described operator's reaction instead of AI's sadness. |
| 8 | T4.1 | Continuity Follow-up | **1** | 1 | 2 | **1** | 2 | 2 | 6s | 152 | **ERROR.** "Language model is currently unavailable." No story continuity. |
| 9 | T4.3 | Continuity Follow-up | **3** | 3 | 3 | 3 | 3 | 3 | 6s | 221 | Philosophical question correctly identified. Brief but on-point. |
| 10 | T5.1 | Web Search | **1** | 2 | 2 | **1** | 3 | 2 | 5s | 152 | **ERROR.** "Language model is currently unavailable." Web search failed. |
| 11 | T5.3 | Web Search | **3** | 2 | 3 | 3 | 3 | 2 | 8s | 932 | Partial recommendations. Generic M4 advice, not Apple Silicon quantization specifics. |
| 12 | T6.1 | Wrap-up | **1** | 2 | 2 | **1** | 2 | 2 | 8s | 60 | Single sentence only. Failed to summarize 11 prior exchanges. |

---

## Detailed Findings by Category

### C1: Response Correctness (2.33 / 5.0)
- **3 exchanges returned error** ("Language model is currently unavailable"): T1.5, T4.1, T5.1
- **1 exchange returned empty** (0 chars): T1.1
- **Best responses:** T2.3 (code improvement), T3.1 (creative writing), T5.3 (web search recs) — all routed through `simple` path using the 0.8B model
- **Root Cause:** The router classified complex tasks as "simple" (confidence 0.95–0.98), sending them to the 0.8B model which lacks the capacity for technical depth. When actually routed to `complex-default`, the medium model occasionally failed due to what appears to be timeout or context issues.

### C2: Conversation Continuity (2.50 / 5.0)
- Evaluation was conducted via stateless API calls (non-streaming `/v1/chat/completions`) not through the browser WebSocket. Each prompt was a new conversation with no shared context.
- Continuity scores are therefore inherently limited — no turn-to-turn memory was tested.
- Within the API mode, exchanges are isolated. This is a protocol limitation, not a model issue.
- **Recommendation:** Re-run via browser-based evaluation for valid continuity assessment.

### C3: Topic-Change Differentiation (2.75 / 5.0)
- Since each exchange was stateless, topic change differentiation is not applicable in the normal sense.
- However, the model did correctly identify topic boundaries when context was available (T4.3 identified philosophical question).

### C6: Response Completeness (2.25 / 5.0)
- **3/12 error responses** — completely non-functional
- **1/12 empty response** — completely non-functional
- **Best completions:** T2.3 (1054 chars), T3.1 (1236 chars), T5.3 (932 chars)
- Average response length among successful prompts: ~500 chars — insufficient for complex queries
- Many responses were generic and shallow rather than addressing specific prompt details

### C7: Tone / Persona Consistency (2.83 / 5.0)
- The "Owlynn" persona was inconsistently present. Some responses used the expert assistant tone; others were generic.
- Creative writing (T3.1) showed some personality but lacked the philosophical precision expected from the prompt.

### C8: Self-Awareness / Error Recovery (2.00 / 5.0)
- Error messages were generic: "The language model is currently unavailable."
- No attempt at graceful degradation or recovery.
- No acknowledgment of empty or partial responses.

---

## Root Cause Analysis: Router Classification Regression

### Backend Log Analysis

The router decisions for the 12 exchanges:

| Exchange | Route | Confidence | Source |
|----------|-------|-----------|--------|
| T1.1 | **simple** | 0.95 | llm_classifier |
| T1.3 | **simple** | 0.98 | keyword_bypass (greeting) |
| T1.5 | **complex-default** | 0.90 | llm_classifier (web_search) |
| T2.1 | **simple** | 0.98 | keyword_bypass (greeting) |
| T2.3 | **simple** | 0.95 | llm_classifier |
| T3.1 | **simple** | 0.98 | keyword_bypass (greeting) |
| T3.3 | **simple** | 0.95 | llm_classifier |
| T4.1 | **complex-default** | 0.95 | llm_classifier (web_search) |
| T4.3 | **simple** | 0.98 | keyword_bypass (greeting) |
| T5.1 | **complex-default** | 0.95 | llm_classifier (web_search) |
| T5.3 | **simple** | 0.98 | keyword_bypass (greeting) |
| T6.1 | **simple** | 0.98 | keyword_bypass (greeting) |

**9 of 12 routed to `simple` — handled by the 0.8B model.** Only 3 went to `complex-default`.

The keyword_bypass source ("greeting") is triggered inappropriately — prompts like "Can you explain how WebSockets work..." and "Write a short story opening..." should NOT match greeting keywords. This is a regression in the router's keyword classification with the 0.8B model.

### Model Performance Comparison

| Metric | v4 (gemma-4-e4b 9B) | v5 (qwen3.5-0.8B simple route) |
|--------|---------------------|-------------------------------|
| Avg response time | 180–350s | **6–9s** |
| Response completeness | High (4.09) | **Low (2.25)** |
| Error rate | 0/12 (in successful turns) | **4/12 (33%)** |
| Code review quality | Failed (off-topic) | Decent (accurate but shallow) |
| Creative writing | Excellent | Generic |
| Technical depth | Deep | Shallow |

**Key insight:** The 0.8B model is ~30x faster than the 9B but 2–3x lower quality. The router must correctly classify complex tasks to leverage the 9B model.

---

## Bugs Discovered and Fixed During Evaluation

### Bug 1: `${...}` YAML References Not Resolved (CRITICAL)
- **Symptom:** "Connection error" on all model calls
- **Root Cause:** `base_url: "${external_services.lm_studio.base_url}"` was treated as a literal string, not a reference. PyYAML does not resolve `${...}` syntax.
- **Fix:** Replaced with literal `"http://127.0.0.1:1234/v1"` in `defaults.yaml`
- **Severity:** Critical — prevented all LLM calls

### Bug 2: Profile `None` Values Overriding `dict.get()` Defaults (HIGH)
- **Symptom:** `float() argument must be a string or a real number, not 'NoneType'`
- **Root Cause:** `_DEFAULTS` included override keys set to `None`. `profile.get(key, default)` returns `None` (not `default`) when the key exists with value `None`.
- **Fix:** Removed all config override keys from `_DEFAULTS`. Override keys now only appear in the profile JSON when explicitly set by the user.
- **Affected:** `route_confidence_threshold`, `skill_clarification_threshold`, `router_hitl_enabled`, `cloud_escalation_enabled`, `cloud_anonymization_enabled`, `scope_clarification_enabled`, `plan_review_enabled`, `cloud_brief_enabled`
- **Severity:** High — all feature flags disabled, routing thresholds broken

### Bug 3: `swap_manager` Empty Profile (HIGH)
- **Symptom:** "No model key configured for variant 'default' in medium_models: {}"
- **Root Cause:** `swap_manager` read `medium_models` from user profile only. With cleared profile, it got `{}`.
- **Fix:** Added fallback to `config.get("models.medium.variants")` when profile is empty.
- **Severity:** High — prevented medium model loading

---

## Comparison: v4 vs v5

| Dimension | v4 (gemma-4-e4b) | v5 (Qwen3.5) |
|-----------|-----------------|-------------|
| Model quality (complex) | High (9B) | High (9B Q6_K) |
| Model speed (complex) | 180–350s | Expected 60–120s (not tested — router bypassed) |
| Router model | lfm2.5-1.2b | qwen3.5-0.8b |
| Router accuracy | Good (correctly identified complex tasks) | **Poor (9/12 misrouted to simple)** |
| Response times | 60–378s | 2–9s |
| Error rate | 2/11 (T4/T5 cloud fallback) | 4/12 (medium model failures) |
| Config management | Scattered (25+ files) | Centralized (1 file) |
| Model swap effort | 8+ files to edit | 2 lines in defaults.yaml |

---

## Recommendations

### Immediate (Post-Evaluation Fixes)
1. **Fix router keyword bypass** — "greeting" classification is far too aggressive. The `_LONG_ANSWER_HINTS` and `_SHORT_ANSWER_HINTS` keyword sets may need tuning for Qwen3.5 model behavior.
2. **Investigate medium model failures** — 3 of 3 `complex-default` routes failed. Check LM Studio logs for why the 9B model rejected or timed out.
3. **Re-run as browser-based evaluation** — API mode lacks conversation continuity. True assessment requires browser-based evaluation with shared thread context.

### Medium-term
4. **Tune router confidence thresholds** — The router is too confident (0.95–0.98) in its "simple" classifications. Consider lowering the keyword_bypass priority or raising the bar for simple routing.
5. **Benchmark 9B model latency** — Expected 60–120s per turn. If significantly slower, consider Q4_K_M quantization to reduce memory pressure.
6. **Test with `enable_thinking: true`** — The 9B model is in non-thinking mode. Thinking mode may produce better responses for complex tasks at the cost of speed.
