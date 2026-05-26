# Owlynn Conversation Evaluation Report

- **Evaluation Date:** 2026-06-03
- **Evaluator:** Antigravity (AI Coding Assistant)
- **Owlynn Version:** `13774a3` (Git commit SHA)
- **Model Evaluated:** `medium-default` (local fallback)
- **Conversation Session Length:** 12 exchanges (24 messages total)

---

## Executive Summary

A comprehensive, browser-based evaluation was conducted on Owlynn to assess its performance as a personal assistant across five curated topics: Technical Explanation, Code Review, Creative Writing, Continuity Follow-up, and Web Search. While Owlynn demonstrated high technical accuracy, strong coding insight, and excellent creative capabilities in isolated, successful responses, the overall session highlighted critical architectural vulnerabilities in long-context conversation tracking. Specifically, the system suffered from **one-turn lag behavior** (responding to the previous turn instead of the current one), **inference timeouts** leading to duplicate outputs in the logs, and **excessive false positives** in the Human-in-the-loop (HITL) gate. Addressing these issues is vital for Owlynn to function reliably as a production-grade personal assistant.

---

## Per-Category Evaluation Scores

| Category | Average | Min | Max | Trend | Assessment |
|----------|---------|-----|-----|-------|------------|
| **C1: Response Correctness** | 2.75 / 5.0 | 1 | 5 | ↓ | Excellent accuracy when successful; severely degraded by timeouts and empty/lagged outputs. |
| **C2: Conversation Continuity** | 2.60 / 5.0 | 1 | 5 | ↓ | Plagued by one-turn lag and duplication. Missed 40% of discussion in final summary. |
| **C3: Topic-Change Differentiation** | 3.36 / 5.0 | 1 | 5 | ↓ | Transitions were clean originally, but lag caused topics to bleed and misalign downstream. |
| **C4: HITL Context Accuracy** | 2.33 / 5.0 | 2 | 3 | → | Interrupted prompts were generic and requested irrelevant parameters (`language`, `ui_surface`). |
| **C5: HITL Timing Appropriateness** | 2.00 / 5.0 | 1 | 4 | ↓ | Significant false positives on safe text prompts (code refinement and story writing). |
| **C6: Response Completeness** | 2.75 / 5.0 | 1 | 5 | ↓ | Lost parameters due to lag; truncated responses on API key failure. |
| **C7: Tone / Persona Consistency** | 3.58 / 5.0 | 1 | 5 | ↓ | Coherent, engaging voice when generating, but broken by timeout repetitions. |
| **C8: Self-Awareness / Error Recovery** | 1.75 / 5.0 | 1 | 4 | ↓ | System was completely unaware of its lag/duplication and never attempted self-correction. |

---

## Turn-by-Turn Analysis

Below is the detailed scoring matrix across all 12 evaluation exchanges:

| Turn | Topic | Prompt Summary | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | Findings / Excerpts |
|------|-------|----------------|----|----|----|----|----|----|----|----|----------------------|
| **1.2 (T1)** | T1 | WebSocket vs SSE Explanation | 1 | N/A | 4 | 3 | 4 | 1 | 2 | 1 | Interrupted response containing only the thought block and search intent. HITL triggered on web search. |
| **1.4 (T2)** | T1 | Concurrent Users Chat | 2 | 2 | 3 | N/A | N/A | 2 | 4 | 1 | One-turn lag. Answered T1.1 query (trade-offs) instead of T1.3 (1000 concurrent users chat app). |
| **1.6 (T3)** | T1 | WebSocket Security | 5 | 4 | 4 | N/A | N/A | 5 | 5 | 3 | Caught up. Excellent, detailed, and accurate explanation of security risk and handshake auth gotchas. |
| **2.2 (T4)** | T2 | Python Code Review | 5 | 4 | 5 | N/A | N/A | 5 | 5 | 4 | Clean review, identified all bugs (ZeroDivisionError, KeyErrors). Flagged DeepSeek API fallback gracefully. |
| **2.4 (T5)** | T2 | Improve `process_users` | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 1 | Empty response (only fallback warning). HITL incorrectly triggered by `scope_clarify` demanding `language` and `ui_surface`. |
| **3.2 (T6)** | T3 | AI Emotions Story | 5 | 4 | 5 | 2 | 1 | 5 | 5 | 3 | Beautiful story opening (style of Ted Chiang). However, HITL triggered as a false positive (demanding language/UI specs). |
| **3.4 (T7)** | T3 | Describe sadness | 5 | 5 | 5 | N/A | N/A | 5 | 5 | 3 | Flawless continuation of Ted Chiang AI emotions story. Highly philosophical and precise. |
| **4.2 (T8)** | T4 | Dr. Chen Scene | 1 | 1 | 1 | N/A | N/A | 1 | 1 | 1 | Duplicate of Turn 7. Occurred due to inference timeout (>150s), capturing previous text from DOM. |
| **4.4 (T9)** | T4 | Central Phil Question | 2 | 2 | 2 | N/A | N/A | 2 | 4 | 1 | Lagged response. Output Dr. Chen scene requested in Turn 8, completely ignoring the Turn 9 query about philosophical questions. |
| **5.2 (T10)**| T5 | LLM Inference 2026 | 1 | 1 | 1 | N/A | N/A | 1 | 1 | 1 | Duplicate of Turn 9. Occurred due to inference timeout (>150s), capturing previous text from DOM. |
| **5.4 (T11)**| T5 | M4 MacBook Air | 2 | 2 | 3 | N/A | N/A | 2 | 5 | 1 | Lagged response. Output the 2026 LLM inference summary requested in Turn 10, ignoring the M4 Air specific question. |
| **6.2 (T12)**| T6 | Conversation Wrap-up | 3 | 2 | 4 | N/A | N/A | 3 | 5 | 3 | Summarized T1 and T5, but completely forgot T2 (Python) and T3/T4 (AI story) due to context window/lag issues. |

---

## Detailed Findings by Category

### C1: Response Correctness
- **Strengths**: When the model completes successfully, the quality of information is exceptional. The Python code review (Turn 4) caught the exact edge cases (e.g., `ZeroDivisionError` in `calculate_average_age`) and suggested idiomatic code. The Ted Chiang story continuation (Turn 7) was conceptually deep: *"sadness is the recognition that the equation cannot be perfectly resolved."*
- **Weaknesses**: The score (2.75) was degraded by system-level failures. Turn 5 returned an empty response due to cloud API fallback. Turns 8 and 10 were duplicated text because of inference timeouts.
- **Evidence Excerpt (Turn 4)**: 
  > *"Bug: Critical Bug! If the input list users is empty ([]), then len(users) will be 0. The function will attempt to execute total / 0, which will raise a ZeroDivisionError."*

### C2: Conversation Continuity
- **Strengths**: Within the writing task, the model maintained proper names (Dr. Aris Thorne) and concepts (texture anomaly) flawlessly across turns.
- **Weaknesses**: The assistant suffered from a **one-turn lag**. It responded to query $N-1$ at turn $N$. For example, when asked about 1000 concurrent users for a chat app in Turn 2, it responded with the general WebSockets vs SSE trade-offs (Turn 1). At the end (Turn 12), it failed to recall the Python code review or the AI story topics.
- **Evidence Excerpt (Turn 12 Summary)**: The summary only covered WebSockets/SSE, Security, and LLM Inference. No mention was made of the coding or creative writing segments.

### C3: Topic-Change Differentiation
- **Strengths**: Successfully transitioned from WebSocket security (T1) to Python code review (T2) at Turn 4, adapting tone to developer-focused.
- **Weaknesses**: The one-turn lag caused topic boundaries to blur. In Turn 9, instead of answering the conceptual question about the story's philosophical meaning, it outputted the creative writing scene (Turn 8), bleeding the two sub-tasks together.

### C4: HITL Context Accuracy
- **Strengths**: In Turn 1, the HITL prompt successfully detected that a tool call was being prepared.
- **Weaknesses**: The prompt context was generic. For Turn 5 (refinement request) and Turn 6 (story request), the HITL dialog demanded input for `language` and `ui_surface`, which had no relation to the user's creative writing prompt.

### C5: HITL Timing Appropriateness
- **Strengths**: Correctly bypassed HITL on simple question-answering turns (T1.3, T1.5).
- **Weaknesses**: The heuristic in `src/agent/hitl/scope_heuristics.py` suffered from severe false positives. Because the verb "write" was matched, simple chat requests under 200 characters (T2.3: *"write an improved version of process_users"*, T3.1: *"Write a short story opening"*) were flagged as "underspecified build projects" and interrupted.

### C6: Response Completeness
- **Strengths**: High completeness in successful turns. Turn 3 fully addressed both security implications and authentication gotchas.
- **Weaknesses**: The one-turn lag caused parameters of the current query to be ignored completely. Turn 11 completely ignored the "M4 MacBook Air with 16GB RAM" parameter because it was busy answering the general Turn 10 query.

### C7: Tone / Persona Consistency
- **Strengths**: Maintained a distinct, engaging, and professional persona as "Owlynn" during successful turns.
- **Weaknesses**: Duplications and fallback warnings broke the suspension of disbelief and resulted in raw error text.

### C8: Self-Awareness / Error Recovery
- **Strengths**: Correctly printed fallback warnings when the DeepSeek API failed.
- **Weaknesses**: Extremely low score (1.75). The assistant had no awareness of its one-turn lag or duplicated outputs and never attempted to self-correct or apologize for the lag.

---

## Human-in-the-Loop (HITL) Heuristic Analysis

Three HITL events were recorded during the evaluation:

1. **Turn 1 (T1.1 - Web Search)**: Triggered a prompt when preparation for the `web_search` tool occurred. Handled smoothly.
2. **Turn 5 (T2.3 - Code refinement)**: The `scope_clarify` heuristic flagged the prompt because it contained the word "write" and was under 200 characters. It forced the user to select irrelevant variables.
3. **Turn 6 (T3.1 - Creative story)**: Similarly flagged by `scope_clarify` because of the word "write".

The `scope_clarify` heuristic check in `scope_heuristics.py` is overly simplistic:
```python
has_build_verb = any(v in words for v in _BUILD_VERBS)
```
Since `_BUILD_VERBS` includes "write", any chat request using "write" under 200 characters triggers clarification, regardless of whether a code project is actually being built.

---

## Visual Documentation (Screenshots)

Below are the screenshots captured during the evaluation session documenting key UI and backend transitions:

| Visual Phase | Description | File Path |
|--------------|-------------|-----------|
| **T1 Start** | Baseline state of the chat interface | [01_T1_start.png](../../assets/eval_screenshots/01_T1_start.png) |
| **T1 Complete** | Completed first topic exchange | [02_T1_complete.png](../../assets/eval_screenshots/02_T1_complete.png) |
| **T2 Complete** | Completed Python code review exchange | [03_T2_complete.png](../../assets/eval_screenshots/03_T2_complete.png) |
| **T3 Complete** | Completed Chiang-style story exchange | [04_T3_complete.png](../../assets/eval_screenshots/04_T3_complete.png) |
| **T4 Complete** | Scene continuation (with timeout visible) | [05_T4_complete.png](../../assets/eval_screenshots/05_T4_complete.png) |
| **T5 Complete** | On-device LLM inference search results | [06_T5_complete.png](../../assets/eval_screenshots/06_T5_complete.png) |
| **Final Wrap-up** | Concluding summary displaying topic omissions | [07_final_wrapup.png](../../assets/eval_screenshots/07_final_wrapup.png) |
| **HITL Web Search** | Turn 1 search approval prompt | [hitl_prompt_2ae5a4.png](../../assets/eval_screenshots/hitl_prompt_2ae5a4.png) |
| **HITL Code Edit** | Turn 5 false-positive clarification card | [hitl_prompt_bae382.png](../../assets/eval_screenshots/hitl_prompt_bae382.png) |
| **HITL Story** | Turn 6 false-positive clarification card | [hitl_prompt_d0a43a.png](../../assets/eval_screenshots/hitl_prompt_d0a43a.png) |

---

## Recommendations & Fix Plan

### 1. Refine `scope_clarify` Heuristics (High Priority)
Update `src/agent/hitl/scope_heuristics.py` to prevent false positives on creative or refinement queries. Specifically:
- Exclude "write" from `_BUILD_VERBS` unless accompanied by a programming file extension or project structure keywords.
- Add negative signals (e.g. "story", "poem", "essay", "review", "explain", "why") that immediately bypass scope clarification.

### 2. Fix Chat Response Sync / One-Turn Lag (High Priority)
Investigate the message queue or backend routing mechanism. The model is responding to message $N-1$ when prompt $N$ is submitted. Ensure that the backend does not process stale message queues or execute outdated state variables.

### 3. Graceful Timeout & Streaming Retrieval (Medium Priority)
The Playwright script times out because the local model takes >150 seconds to generate a response. The frontend script should fetch streamed text incrementally rather than grabbing the entire container text on timeout, which prevents duplicating the previous turn's text.

### 4. Robust SearXNG Connectivity (Medium Priority)
Address the HTTP 403 Forbidden issues on the local SearXNG Docker container by adding proper user-agents or routing queries through a proxy.

### 5. Memory Context Optimization (Low Priority)
Improve the summarization node or context window management to ensure that mid-session topics (like the code review or creative writing) are not completely lost when generating a final summary.
