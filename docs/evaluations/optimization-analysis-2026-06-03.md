---
title: "OwlynnV2 Optimization Analysis"
status: active
category: evaluation
last_updated: 2026-06-03
---

# OwlynnV2 — Optimization Analysis

> Comprehensive review grounded in architecture docs, evaluation reports (v1 → v2), PERFORMANCE_SLOS.md, and full codebase inspection.  
> Generated: 2026-06-03

---

## Project Goals — Current Status

| Goal | Source | Status |
|------|--------|--------|
| Local-first AI coworker on Apple Silicon (M4 Air 24GB) | ARCHITECTURE_OVERVIEW | ✅ Achieved |
| Privacy-preserving — no data leaves machine unless opted in | ARCHITECTURE_OVERVIEW | ✅ Achieved |
| Three-tier LLM strategy (Small/Medium/Cloud) with smart routing | ARCHITECTURE_OVERVIEW | ✅ Achieved |
| 22-tool productivity agent with web search, file ops, docs, REPL | Tool inventory | ✅ Achieved |
| Three-tier memory (STM/LTM/Personal) with cross-session recall | Memory system | ✅ Achieved |
| Human-in-the-loop safety gates for sensitive operations | HITL subsystem | ⚠️ Partially — false positives remain |
| Response latency: <2s simple, <8s complex, <3s first token | PERFORMANCE_SLOS | ❌ Missed — complex turns avg 180–350s |
| Streaming throughput: >30 tok/s medium, >80 tok/s small | PERFORMANCE_SLOS | ⚠️ Untested in eval |
| Memory budget: ~7.1 GB sustained, ~8.5 GB peak | PERFORMANCE_SLOS | ✅ Within bounds |
| Self-awareness and error recovery | Eval C8 | ❌ Lowest score (2.67/5.0) |
| Continuous, contextual conversation over 12+ turns | Eval C2 | ⚠️ 3.36/5.0 — degrades in later turns |
| Persona consistency (Owlynn identity) | Eval C7 | ⚠️ 3.83/5.0 — breaks under lag |

---

## Evaluation Trajectory (v1 → v2)

| Category | v1 | v2 | Δ | Gap to 4.5+ |
|----------|-----|-----|---|-------------|
| C1: Response Correctness | 2.75 | **3.08** | +0.33 | 🔴 Large |
| C2: Conversation Continuity | 2.60 | **3.36** | +0.76 | 🟡 Medium |
| C3: Topic-Change Differentiation | 3.36 | **3.75** | +0.39 | 🟡 Medium |
| C4: HITL Context Accuracy | 2.33 | **3.50** | +1.17 | 🟡 Medium |
| C5: HITL Timing Appropriateness | 2.00 | **4.50** | +2.50 | ✅ Target |
| C6: Response Completeness | 2.75 | **3.08** | +0.33 | 🔴 Large |
| C7: Tone / Persona Consistency | 3.58 | **3.83** | +0.25 | 🟡 Medium |
| C8: Self-Awareness / Error Recovery | 1.75 | **2.67** | +0.92 | 🔴 Large |

The biggest remaining gaps (C1, C6, C8) are all directly caused by the **one-turn lag** infrastructure bug.

---

## Optimization Opportunities

### 🔴 Category A — Critical Infrastructure

#### A1. Client-Server Message Synchronization (One-Turn Lag)

**Problem**: When local model inference exceeds the browser timeout (~300s), the client grabs stale DOM text and sends the next prompt. All subsequent responses are offset by one turn.

**Evidence**: Turns 9, 11 in v2 had durations of 300.7s and 350.0s. Turns 9–12 scored 1–2/5 on correctness. This single bug accounts for ~40% of lost eval points.

**Root Cause**: No message correlation between client and server.

**Fix**:
1. Add `message_id` (UUID) to every outgoing user message
2. Server echoes `message_id` in all response events
3. Client waits indefinitely (spinner + elapsed timer) until matching `message_id` events arrive
4. Client never sends prompt N+1 until response for prompt N completes
5. Add `turn_complete` WebSocket event for unambiguous turn boundaries

**Impact**: 🔴 Critical | **Effort**: Medium | **Files**: `src/api/server.py`, frontend WS handler

---

#### A2. Local Model Inference Latency

**Problem**: Complex turns take 150–350s. SLO target is <8s. Performance is 20–40x worse.

**Evidence**: T1=270s, T3=183s, T4=163s, T9=301s, T11=350s.

**Root Cause**: 100K default context window on Q4_K_M Gemma 4 is too large for most queries.

**Fix** (layered):
1. Reduce default context window: 100K → 32K for most turns
2. Compress system prompt + memory injection (currently 2000–4000 tokens)
3. Evaluate alternative quantizations or models for speed/quality trade-offs
4. Ensure streaming starts before full response completes

**Impact**: 🔴 Critical | **Effort**: Low–High | **Files**: `src/config/settings.py`, `src/agent/llm.py`

---

#### A3. DeepSeek Cloud Fallback Configuration

**Problem**: Turn 5 returns empty content — only a fallback warning. DeepSeek API key is invalid.

**Fix**:
1. Validate API key at startup with a clear warning if unavailable
2. Ensure fallback chain always produces content (never empty responses)
3. Add health-check endpoint for tier availability

**Impact**: 🟡 Medium | **Effort**: Low | **Files**: `src/agent/llm.py`, `src/agent/nodes/complex.py`

---

#### A4. Mem0 LTM Search Silently Broken (API Breaking Change)

**Problem**: Live server logs reveal all Mem0 searches failing:
```
[mem0] search failed: Top-level entity parameters frozenset({'user_id'})
are not supported in search(). Use filters={'user_id': '...'} instead.
```

Long-term memory is **write-only** — facts saved but never recalled.

**Root Cause**: Mem0 library API change — `search(query, user_id=...)` → `search(query, filters={'user_id': ...})`.

**Fix**:
1. Update `long_term.py` to use `filters=` parameter
2. Add startup health check for Mem0 search
3. Pin Mem0 version in requirements.txt

**Impact**: 🔴 Critical | **Effort**: 5 minutes | **Files**: `src/memory/long_term.py`, `src/agent/nodes/memory.py`

---

### 🟡 Category B — Response Quality & HITL Refinement

#### B1. Code Refactoring HITL False Positive

**Problem**: "Write an improved version of process_users" triggers `scope_clarify` — "write" is in `_BUILD_VERBS` with no creative signal bypass for code refactoring.

**Fix**: Add `_REFACTOR_SIGNALS` list ("improve", "refactor", "optimize", "modify", "review", "rewrite") + code symbol detection (`.py`, `.js`, function names) to bypass scope_clarify.

**Impact**: 🟡 Medium | **Effort**: Low | **Files**: `src/agent/hitl/scope_heuristics.py`

---

#### B2. Self-Awareness & Error Recovery (C8)

**Problem**: System never detects own errors. Confidence always 95% even on wrong responses.

**Fix**:
1. Response-query coherence check via small LLM
2. Meaningful confidence from token probabilities + tool success/failure
3. Lag detection from timestamp comparison

**Impact**: 🟡 Medium | **Effort**: Medium

---

#### B3. Context Window Loss in Long Sessions (C2)

**Problem**: Final wrap-up forgets mid-session topics. Auto-summarize too aggressive.

**Fix**:
1. Topic-aware summarization — preserve "topics discussed" manifest
2. Sliding window with anchors (keep first/last N messages)
3. Query LTM at wrap-up to supplement compressed context

**Impact**: 🟡 Medium | **Effort**: Medium | **Files**: `src/agent/nodes/summarize.py`

---

### 🟢 Category C — Memory & Context Optimization

#### C1. Memory Injection Token Budget

Relevance-gate LTM injection (cosine >0.7), cap total injected context at 2000 tokens.

#### C2. STM → LTM Promotion Strategy

Auto-promote facts recalled 3+ times; prune facts >30 days without recall.

#### C3. Synchronous JSON I/O in Async Context

Use `aiofiles` or `asyncio.to_thread()` for JSON persistence in memory modules.

---

### 🟡 Category D — Code Health

#### D1. server.py Decomposition (2215 lines)

Split into `api/routes/{profile,memory,project,files,chat}.py` + `api/ws/handler.py`.

#### D2. complex.py Refactoring (1130 lines)

Extract `FallbackExecutor`, `ToolBinder`, response formatting into separate modules.

#### D3. WebSocket Event Buffer Unbounded Growth

Cap `event_buffer` at 1000 entries with rolling window.

#### D4. Notebook Tool Sandboxing

Run `notebook_run` in subprocess with resource limits instead of in-process `exec()`.

---

### 🟢 Category E — Developer Experience

#### E1. Automated SLO Testing — Create `scripts/slo_check.py` for CI integration
#### E2. API-Based Eval Harness — Replace browser-based eval with direct API testing
#### E3. Archive Completed Specs — Move 2 completed specs from `specs/active/` to `specs/completed/`

---

### 🟢 Category F — Documentation

#### F1. Create dedicated `docs/HITL.md` and `docs/MEMORY.md`
#### F2. Update README test counts (822 unit, 96 frontend) and Node version (≥20)
#### F3. Fix `docs/architecture/overview.md` to describe Owlynn, not SDD harness

---

## Quick Wins

| # | Item | Effort | Impact |
|---|------|--------|--------|
| A4 | Fix Mem0 search API in long_term.py | 5 min | 🔴 Critical |
| A2a | Reduce context window 100K → 32K | 5 min | 🔴 High |
| B1 | Add `_REFACTOR_SIGNALS` to scope_heuristics.py | 15 min | 🟡 Medium |
| A3 | Add API key validation at startup | 30 min | 🟡 Medium |
| D3 | Cap event_buffer at 1000 entries | 15 min | 🟢 Low |
| E3 | Move specs to completed/ | 5 min | 🟢 Trivial |
| F2 | Update README numbers | 5 min | 🟢 Trivial |

---

## Summary

**A1 (Message Correlation IDs)** is the single highest-leverage optimization — 40% of eval point losses.

**A4 (Mem0 LTM Search)** is a silent emergency — LTM is completely non-functional. 1-line fix.

**A2 (Inference Latency)** is 20–40x worse than SLO. Context window reduction is the easiest win.

A1 + A2 + A4 together would likely push eval scores from ~3.3 to ~4.0+.
