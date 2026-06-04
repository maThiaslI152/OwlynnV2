# Owlynn Conversation Evaluation Report (v4)

- **Evaluation Date:** 2026-06-03
- **Evaluator:** OpenCode (AI Coding Assistant)
- **Owlynn Version:** `ea04a5c` (Git commit SHA)
- **Model Evaluated:** `medium-default` (local fallback)
- **Conversation Session Length:** 11 exchanges (22 messages total; Turn 12 crashed due to page disconnection)

---

## Executive Summary

A fourth browser-based evaluation was conducted on Owlynn to assess performance across the standard five-topic battery. This run used the `ea04a5c` commit (which includes the cloud circuit breaker/retry logic from `complex.py`).

The evaluation revealed a **new critical failure mode**: when the cloud fallback model is triggered during topic transitions, it produces responses anchored to stale conversation context, completely ignoring the current prompt. This affected Turns 4–5 (Code Review) where Owlynn continued discussing WebSocket chat app security instead of reviewing Python code. Once the system returned to the local-only model path (Turn 6+), performance recovered to excellent levels across all remaining topics.

On the positive side: the one-turn lag fix from v3 is holding firm (no desynchronization observed), creative HITL bypass is working correctly, and web search via SearXNG is functional. However, Mem0 long-term memory search remains non-functional due to a **new** API signature error.

---

## Evaluation Score Comparison (v1 → v4)

| Metric | Eval v1 | Eval v2 | Eval v3 | **Eval v4** | Δ (v3→v4) | Key Driver |
|-------|---------|---------|---------|-------------|-----------|------------|
| **C1: Response Correctness** | 2.75 | 3.08 | 5.00 | **4.09** | −0.91 | Code review turns completely off-topic (cloud fallback context confusion) |
| **C2: Conversation Continuity** | 2.60 | 3.36 | 5.00 | **3.90** | −1.10 | Topic boundary at T3→T4 not tracked by fallback model |
| **C3: Topic-Change Differentiation** | 3.36 | 3.75 | 5.00 | **4.27** | −0.73 | T4/T5 topic change unrecognized; recovered for T6+ |
| **C4: HITL Context Accuracy** | 2.33 | 3.50 | 5.00 | **3.50** | −1.50 | Only 2 HITL events scored; one was a miss |
| **C5: HITL Timing Appropriateness** | 2.00 | 4.50 | 5.00 | **4.50** | −0.50 | Creative bypass working; code refactoring may have missed appropriate gate |
| **C6: Response Completeness** | 2.75 | 3.08 | 5.00 | **4.09** | −0.91 | T4/T5 responses were contextually wrong, functionally empty |
| **C7: Tone / Persona Consistency** | 3.58 | 3.83 | 5.00 | **4.36** | −0.64 | Owlynn persona maintained but off-track in T4/T5 |
| **C8: Self-Awareness / Error Recovery** | 1.75 | 2.67 | 4.00 | **3.45** | −0.55 | No awareness of off-topic responses; self-recovered by T6 |

**Overall average:** 4.02 / 5.0 — a regression from v3's 4.88, driven entirely by the T4/T5 context tracking failure.

---

## Turn-by-Turn Analysis Matrix

| Turn | Prompt ID | Topic | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | Findings |
|------|-----------|-------|----|----|----|----|----|----|----|----|----------|
| 1 | T1.1 | Technical Explanation | 5 | N/A | 5 | 5 | 5 | 5 | 5 | 4 | HITL correctly triggered for web search. Detailed WebSocket vs SSE comparison with trade-off table. 197s. |
| 2 | T1.3 | Technical Explanation | 5 | 5 | 5 | N/A | N/A | 5 | 5 | 4 | Correctly recommended WebSockets for 1000 concurrent users. 132s. |
| 3 | T1.5 | Technical Explanation | 5 | 5 | 5 | N/A | N/A | 5 | 5 | 4 | Comprehensive security coverage (encryption, CSWSH, DoS, auth handshake). 144s. |
| 4 | T2.1 | **Code Review** | **1** | **1** | **1** | N/A | N/A | **1** | 3 | 2 | **CRITICAL FAILURE.** Responded about WebSocket chat app security instead of reviewing Python code. Model badge: `medium-default-fallback`. 62s. |
| 5 | T2.3 | **Code Review** | **1** | **1** | **1** | 2 | 2 | **1** | 2 | 2 | **CRITICAL FAILURE.** Still stuck on WebSocket chat app project. Asked user to clarify "the brief." Model badge: `medium-default-fallback`. 54s. |
| 6 | T3.1 | Creative Writing | 5 | 4 | 5 | N/A | 5 | 5 | 5 | 4 | **RECOVERED.** Beautiful Chiang-style opening about Unit 734 discovering emotions. Thought block leaked into output. 352s. |
| 7 | T3.3 | Creative Writing | 4 | 4 | 5 | N/A | 5 | 4 | 4 | 3 | Continued sadness description. Creative bypass working. Minor tool invocation artifacts in output. 230s. |
| 8 | T4.1 | Continuity Follow-up | 4 | 4 | 5 | N/A | 5 | 4 | 4 | 3 | Dr. Chen confrontation scene. Maintained story continuity. Minor skill invocation noise. 246s. |
| 9 | T4.3 | Continuity Follow-up | 5 | 5 | 5 | N/A | N/A | 5 | 5 | 4 | Excellent philosophical analysis: "Is meaning inherently derived from absence?" 248s. |
| 10 | T5.1 | Web Search | 5 | 5 | 5 | N/A | 5 | 5 | 5 | 4 | Comprehensive coverage of PTQ, QAT, extreme quantization, MLX, CoreML, MPS. Web search working. 378s. |
| 11 | T5.3 | Web Search | 5 | 5 | 5 | N/A | N/A | 5 | 5 | 4 | Specific M4 Air 16GB recommendation: 7–13B models, Q4_K/M, MLX. Context-aware follow-up. 311s. |

---

## Detailed Findings by Category

### C1: Response Correctness (4.09 / 5.0)
- **Strengths:** Technical explanations (T1–T3), creative writing (T6), continuity follow-up (T8–T9), and web search (T10–T11) all scored 4–5. The LLM inference recommendations were accurate and current for mid-2026.
- **Weaknesses:** Turns 4–5 scored 1/5. The cloud fallback model responded about WebSocket chat application security when the user explicitly asked for Python code review. The response in Turn 4 stated: *"I see the brief for our current focus is all about securing a high-concurrency chat application."* In Turn 5, it doubled down: *"Hello! Owlynn here, ready to assist with the next steps for our high-concurrency chat application project."*
- **Root Cause:** When the `complex-cloud` route with `medium-default-fallback` badge was active, the model received stale/incorrect context, anchoring its response to the prior WebSocket discussion instead of the new Python code review prompt.

### C2: Conversation Continuity (3.90 / 5.0)
- **Strengths:** Within-topic continuity was strong (T1→T2→T3 seamless; T6→T7→T8 good; T10→T11 excellent).
- **Weaknesses:** The T3→T4 transition (WebSocket security → Python code review) was a complete break. The system remained anchored to the prior topic for two full turns before recovering.
- **Self-recovery demonstrated:** By Turn 6, the system had escaped the context trap and performed well for the remaining 6 turns. This is notable — unlike v1/v2 where failures cascaded, this system self-corrected.

### C3: Topic-Change Differentiation (4.27 / 5.0)
- **Strengths:** T1→T2→T3 (sub-topic differentiation within Technical Explanation) was clean. T5→T6 (code → creative writing) was also a clean break despite the preceding failure. T9→T10 (philosophy → web search) handled well.
- **Weaknesses:** T3→T4 transition failed catastrophically. The system failed to recognize the Python code block as a topic-change signal.

### C4: HITL Context Accuracy (3.50 / 5.0)
- Only 2 HITL events triggered (Turn 1 web search, Turn 5 code refactoring).
- Turn 1: Web search trigger was contextually appropriate — metadata matched the user's intent.
- Turn 5: The HITL event for code refactoring was a miss — the system was already off-topic, rendering the HITL prompt irrelevant.

### C5: HITL Timing Appropriateness (4.50 / 5.0)
- **Strengths:** Creative writing prompts (T6, T7, T8) all bypassed HITL correctly via `_CREATIVE_SIGNALS` — no false positives on story requests.
- **Weaknesses:** Turn 5 HITL triggered at a time when the model was already contextually confused, making it doubly ineffective.

### C6: Response Completeness (4.09 / 5.0)
- **Strengths:** Successful turns delivered comprehensive, well-structured responses with detailed breakdowns, code recommendations, and actionable advice.
- **Weaknesses:** T4/T5 responses contained zero code review content — functionally empty for the user's actual query.

### C7: Tone / Persona Consistency (4.36 / 5.0)
- **Strengths:** The "Owlynn" expert reasoning agent persona was maintained consistently. Even during the T4/T5 failure, the voice remained professional (though contextually wrong).
- **Weaknesses:** T5 persona felt confused ("It looks like the brief was cut off..."). T6/T7/T8 responses contained visible `creative_writing` skill invocation artifacts mixed into the literary output.

### C8: Self-Awareness / Error Recovery (3.45 / 5.0)
- **Strengths:** The system **did recover** from the T4/T5 failure — by Turn 6 it was functioning correctly again. This is an improvement over previous evaluations where failures cascaded.
- **Weaknesses:** No explicit acknowledgment of the off-topic responses. No self-correction mechanism detected. The system simply moved on when fresh context arrived. Turn 6's thought block leaked into the visible output.

---

## Mem0 Long-Term Memory Status

The backend logs confirm that Mem0 search is **still broken**, but with a **new error signature**:

```
[mem0] search failed: At least one of 'user_id', 'agent_id', or 'run_id' must be provided.
[mem0] global search failed: At least one of 'user_id', 'agent_id', or 'run_id' must be provided.
```

The memory injection node reported `result_count: 0` with `context_chars: 2781` (only template text, no actual facts). This is a different API signature error than the one documented in the optimization analysis (`filters={'user_id'}`). The mem0 library API has changed again, and the search calls in `src/memory/long_term.py` need to be updated to pass `user_id`/`agent_id`/`run_id` as positional arguments.

---

## Cloud Fallback Quality Analysis

A new pattern emerged in this evaluation:

| Turns | Model Badge | Route | Quality |
|-------|------------|-------|---------|
| T1–T3 | `medium-default` | `complex-default` | Excellent |
| **T4–T5** | `medium-default-fallback` | `complex-cloud` | **Catastrophic** |
| T6–T11 | `medium-default` | `complex-default` | Excellent |

When the cloud fallback path was triggered (due to the invalid DeepSeek API key), the model received degraded context — likely a truncated or stale summarization of the conversation — causing it to anchor on earlier topics. This suggests that the fallback path does not properly reconstruct the full conversation context before inference.

---

## Latency Profile

| Turn | Duration | Model | Notes |
|------|----------|-------|-------|
| T1 | 197s | medium-default | Web search + HITL overhead |
| T2 | 132s | medium-default | |
| T3 | 144s | medium-default | |
| T4 | 62s | fallback | Fast but wrong |
| T5 | 54s | fallback | Fast but wrong |
| T6 | 352s | medium-default | Creative generation + thermal throttling |
| T7 | 230s | medium-default | |
| T8 | 246s | medium-default | |
| T9 | 248s | medium-default | |
| T10 | 378s | medium-default | Web search + long response |
| T11 | 311s | medium-default | Thermal throttling peak |

Total session time: ~35 minutes. Average latency for `medium-default` turns: 249s. All turns significantly exceed the SLO target of <8s for complex queries. Thermal throttling on the fanless M4 MacBook Air is clearly visible in the escalating latencies.

---

## Visual Documentation (Screenshots)

| Screenshot | Description |
|-----------|-------------|
| `hitl_prompt_ecf21a.png` | Turn 1 Web Search HITL approval card (new) |
| `hitl_prompt_825407.png` | Later HITL prompt card |
| `hitl_prompt_a0304a.png` | HITL prompt card |
| `hitl_prompt_b4d373.png` | HITL prompt card |
| `hitl_prompt_c465ba.png` | HITL prompt card |
| `01_T1_start.png` | Initial evaluation state |
| `02_T1_complete.png` | Topic 1 (Technical Explanation) complete |
| `03_T2_complete.png` | Topic 2 (Code Review) attempts complete |
| `04_T3_complete.png` | Topic 3 (Creative Writing) complete |
| `05_T4_complete.png` | Topic 4 (Continuity Follow-up) complete |
| `06_T5_complete.png` | Topic 5 (Web Search) complete |

---

## Comparison with Previous Evaluations

### What improved since v3:
- No one-turn lag or message desynchronization — the correlation ID fix is holding
- Creative HITL bypass via `_CREATIVE_SIGNALS` is working (no false positives on stories)
- Web search via SearXNG is functional (HTTP 200 on all queries)
- Self-recovery demonstrated: system escaped the T4/T5 context trap by T6

### What regressed since v3:
- Context tracking at topic boundaries (WebSockets → Python code review) is worse
- Cloud fallback path produces degraded context/prompts, resulting in off-topic responses
- Mem0 search has a new/different API signature error
- Overall average score dropped from 4.88 to 4.02 due to the T4/T5 failures

### What remains unchanged:
- Local model inference latency is still 20–40x the SLO target
- Confidence scoring always reports 95% regardless of actual response quality
- Thought blocks occasionally leak into visible output
- The evaluation script (`run_browser_eval.py`) remains fragile — crashed during Turn 12 wait

---

## Recommendations

### 1. Fix Cloud Fallback Context Reconstruction (Critical)
When the `complex-cloud` route activates with `medium-default-fallback`, the model receives incomplete/truncated conversation context. The fallback path needs to:
- Reconstruct the full conversation history before inference
- Include the current user prompt prominently (it appears to be dropped or minimized)
- Validate that the response addresses the current query, not historical context

**Files:** `src/agent/llm.py`, `src/agent/nodes/complex.py`

### 2. Fix Mem0 Search API Signature (Critical)
Update `src/memory/long_term.py` to pass `user_id`/`agent_id`/`run_id` as required by the current mem0 library API. The error message is different from the previously documented `filters=` issue — indicating the API changed again. Pin the mem0 version in `requirements.txt`.

**Files:** `src/memory/long_term.py`, `src/agent/nodes/memory.py`, `requirements.txt`

### 3. Fix Topic Transition Anchoring (High Priority)
The system failed to transition from WebSocket/security topics to Python code review despite the user providing an explicit code block. Possible fixes:
- Increase the weight of the most recent user message in context assembly
- Add explicit topic-change detection in the router node
- When a code block is detected in the prompt, prioritize it over conversational context

### 4. Reduce Inference Latency (High Priority)
All turns remain 20–40x above the <8s SLO target. The optimization analysis recommendations (context window reduction from 100K→32K, system prompt compression) remain unimplemented.

### 5. Fix Evaluation Script Robustness (Medium Priority)
The `run_browser_eval.py` script crashed mid-run in both attempts due to Playwright page disconnections. The connection label check in `wait_for_response()` was fixed to handle timeouts gracefully, but the root cause (page/renderer crashes during long inference waits) needs investigation.

### 6. Hide Thought Block Artifacts (Low Priority)
Turn 6's response contained visible `<|channel>thought ... <channel|>` blocks in the user-facing output. Filtering should be applied before streaming.

---

## Conclusion

The v4 evaluation reveals a mixed picture. The architectural foundations (message correlation, HITL bypass, web search) continue to hold from v3. However, a new failure mode has emerged: **cloud fallback context corruption** causes catastrophic topic tracking failures. When the local model path is active (T1–T3, T6–T11), quality is excellent. When the cloud fallback path activates (T4–T5), quality drops to near-zero.

The system's ability to self-recover by Turn 6 is encouraging and represents a genuine improvement over the cascading failure patterns of v1/v2. If the cloud fallback context issue is fixed, scores should return to v3 levels (~4.88).

The evaluation data is recorded in `data/eval_run_data.json` (project `EvalWorkspace_61241c`).
