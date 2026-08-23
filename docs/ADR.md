---
status: active
category: architecture
last_updated: 2026-06-27
owner: human
---

# Architecture Decision Log (ADR)

> **Purpose:** Architecture Decision Log for the Owlynn project.

## Overview

Records significant architectural decisions for the Owlynn project, following the [ADR pattern](https://adr.github.io/). Each entry captures context, decision, and consequences.

## Entry Points

```text
docs/ADR.md                # This file
docs/AI_AGENT_INDEX.md     # Cross-references all ADRs
```

## Key Decisions

| ADR | Date | Status | Decision |
|-----|------|--------|----------|
| ADR-0001 | 2026-04-23 | Implemented | Tauri as desktop shell |
| ADR-0002 | 2026-04-23 | Implemented | LangGraph for agent orchestration |
| ADR-0003 | 2026-04-23 | Implemented | Local-first hybrid model architecture |
| ADR-0004 | 2026-04-23 | Implemented | WebSocket as primary transport |
| ADR-0005 | 2026-04-23 | Implemented | Mem0 + Qdrant for long-term memory |
| ADR-0006 | 2026-04-23 | Implemented | Security proxy with HITL approval |
| ADR-0007 | 2026-04-23 | Implemented | Redis for hot state, Qdrant for vector memory |
| ADR-0008 | 2026-04-23 | Implemented | Unfiltered content policy with strict tool controls |
| ADR-0009 | 2026-04-23 | Implemented | Zustand for frontend state management |
| ADR-0010 | 2026-04-23 | Implemented | WebSocket event telemetry for routing and fallback visibility |
| ADR-0011 | 2026-04-23 | Implemented | Auto-summarize with multi-level compression |
| ADR-0012 | 2026-04-24 | Removed (2026-04-29) | macOS-native Live Talk via Tauri events |
| ADR-0013 | 2026-04-24 | Removed (2026-04-29) | Tauri v2 + Swift helper for two-stage voice pipeline |
| ADR-0014 | 2026-05-24 | Implemented | Skill matcher HITL resolves routing ambiguity |
| ADR-0015 | 2026-05-26 | Implemented | Proactive plan-review + scope-clarify HITL gates |
| — | 2026-05-25 | — | Quality audit: browser interactive test |

## Architecture

### ADR-0001: Tauri as Desktop Shell

Tauri v2.10.3 desktop shell with React + TypeScript frontend, macOS native vibrancy, CSS backdrop blur for glass aesthetic.

**Consequences:**

- Native window management and OS-level permissions (screen capture, mic) via Tauri commands
- Rust backend for security-critical paths, separate from Python agent
- Smaller binary (~5MB vs ~100MB Electron)
- `transparent: true` with `titleBarStyle: "Overlay"` caused WebKit GPU compositing crashes on macOS Sequoia 26.4
- CSS body uses solid dark gradient (`#060d18` → `#081122`) with translucent window chrome
- Requires Tauri permission audit before production release

### ADR-0002: LangGraph for Agent Orchestration

Python `StateGraph` with `AgentState` TypedDict.

**Consequences:**

- State transitions are explicit and testable via conditional edges
- Supports cyclic flows (tool call → security → action → LLM loop)
- Redis-backed checkpointing for persistence across restarts
- Checkpoint system enables thread-level conversation history

### ADR-0003: 4-Model Unified Taxonomy with Cloud Escalation

4-tier model system:

| Tier | Model | Context | Location |
|------|-------|---------|----------|
| Main Local | `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` | 32768 | Always local (routing, extraction, direct answers, local complex fallback, pentest mode) |
| Vision | `baidu.unlimited-ocr` | 8192 | Local OCR / visual transcription proxy |
| Embedding | `text-embedding-mxbai-embed-large-v1` (1024 dims) | 512 | Always local (PostgreSQL pgvector LTM, semantic cache, web RAG) |
| Pentest | `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` | 32768 | Local isolated Pentest mode (zero-latency swap) |
| Cloud | `deepseek-v4-flash` / `pro` | 1M | Primary complex cloud reasoning |

**Consequences:**

- `LLMPool` manages lifecycle (`main`, `vision`, `cloud`), centralized in `defaults.yaml`
- Single source of truth for configuration without model swap latencies

### ADR-0004: WebSocket as Primary Transport

Single persistent WebSocket connection per thread (`/ws/chat/{thread_id}`) with JSON event framing.

**Consequences:**

- Event types defined in `docs/CHAT_PROTOCOL.md` with strict shape contracts
- `WsClient` TypeScript wrapper with lifecycle callbacks and send-gating
- Rust Tauri events (voice, screen assist) forwarded through parallel channel
- Connection per-thread; disconnects don't cancel running graph execution

### ADR-0005: Mem0 + Qdrant for Long-Term Memory

Mem0 with local Qdrant on port 6333, LM Studio embeddings (`text-embedding-nomic-embed-text-v1.5-embedding`).

**Consequences:**

- Memory namespace-scoped by project (`project:<id>`) and user identity
- Topic extraction and enriched memory save on every conversation turn
- Memory context TTL-cached (5 min) in `MemoryContextCache`
- Requires Qdrant container running

### ADR-0006: Security Proxy with HITL Approval

Mandatory `security_proxy` node in LangGraph graph with risk classification and configurable execution policy (`hitl` / `auto_approve`).

**Consequences:**

- Every tool call goes through security proxy before execution
- Risk metadata (label, confidence, rationale, remediation) classified server-side
- Frontend shows `ActionProposalQueue` for pending approvals
- Audit trail of all tool executions with hash-verified export

### ADR-0007: Redis for Hot State, Qdrant for Vector Memory

Redis for session state and LangGraph checkpointing; Qdrant for vector memory (via Mem0); SearxNG for local web retrieval.

**Consequences:**

- Redis: sub-millisecond session state access
- Qdrant (port 6333): `text-embedding-nomic-embed-text-v1.5-embedding` embeddings for memory vectors
- Mem0 wraps Qdrant for higher-level memory operations
- SearxNG: privacy-preserving local web search
- All three run in containers (`docker-compose.yml`)

### ADR-0008: Unfiltered Content Policy

No content-behavior filters applied to model outputs. Strict tool-level permissions with destructive-action confirmations and tamper-evident audit trail.

**Consequences:**

- Models produce unfiltered output (user responsible for content)
- Tool execution requires explicit approval for risky operations
- All tool actions logged with HMAC-signed audit hashes
- Audit bundles exportable and verifiable

### ADR-0009: Zustand for Frontend State

Single `useAppStore` store for all frontend state.

**Consequences:**

- No Redux middleware or context provider nesting
- State mutations colocated with store definition
- `verbatimModuleSyntax` requirement in TypeScript config

### ADR-0010: WebSocket Event Telemetry

`router_info` event on every routing decision; `fallback_chain` in `model_info` events.

**Consequences:**

- `router_info`: route, confidence, reasoning, classification_source, features
- `fallback_chain`: ordered model attempts with status, reason, duration_ms
- Both events have WS contract tests
- Frontend `OrchestrationPanel` displays routing and model information

### ADR-0011: Auto-Summarize with Multi-Level Compression

Auto-summarize LangGraph node triggered at >85% context window usage, with structured categorized output and prior-summary awareness.

**Consequences:**

- Small LLM produces structured summary (decisions, facts, preferences, tasks, code)
- Prior auto-summaries fed back into subsequent compression rounds
- Protected messages (tool results, pinned, system) never compressed
- `context_summarized` WebSocket event emitted on compression
- Graceful degradation — LLM failure results in no-op

### ADR-0012: macOS-Native Live Talk (REMOVED)

Status: **SUPERSEDED** by ADR-0013, then **REMOVED** (2026-04-29). All wake-word listening, transcription, and Swift helper infrastructure removed. Only `speak_text` TTS remains.

### ADR-0013: Tauri v2 + Swift Helper (REMOVED)

Status: **REMOVED** (2026-04-29). Two-stage voice pipeline (SoundAnalysis + WhisperKit) removed from codebase.

### ADR-0014: Skill Matcher HITL

Decouples routing confidence and skill ambiguity into separate thresholds (`routing_confidence_threshold` and `skill_clarification_threshold`). Skill matcher always runs (even when LLM is confident), using MatchResult ambiguity signals as independent HITL trigger.

**Consequences:**

- User gains direct say in routing when skills are ambiguous
- Adds latency on ambiguous queries (one HITL round-trip), but only reactively
- `skill_matched` propagates to AgentState for proactive toolbox selection
- Toolbox selection becomes skill-driven via `_toolbox_for_skill`

### Quality Audit: Browser Interactive Test (2026-05-25)

Full interactive browser audit against running OwlynnV2 stack. 19 of 28 features passed, 5 failed, 4 untestable.

| Severity | Count | Key Issue |
|----------|-------|-----------|
| Critical | 1 | Persona/system prompt leaks into first assistant response |
| High | 2 | Orchestration and Memory panels fail to display data |
| Medium | 2 | Safe Mode has no browser fallback; chat auto-titling fails silently |
| Low | 3 | Mock data in production panel; wrong operator note; audit panel won't expand |

All 8 bugs documented in `docs/BUG-ANALYSIS.md`. Phase 8 added to `docs/STATUS.md`.

## Testing

Cross-references: `docs/BUG-ANALYSIS.md`, `docs/STATUS.md` (Phase 8), `docs/AI_AGENT_INDEX.md`

## Configuration

No specific env vars. Policy enforced via ADR decisions in code.

### ADR-0015: Proactive Plan-Review + Scope-Clarify HITL Gates

**Date:** 2026-05-26  
**Status:** Implemented

**Context:** The agent's `complex_llm` node often commits to tool execution plans (write files, run notebooks, delete) without human review. Vague build requests ("build a calculator app") route to `complex-default` with no requirement gathering, resulting in wrong-stack implementations. Existing `security_proxy` and router HITL gates catch individual tool calls but don't surface *intent*, *pitfalls*, or *missing requirements*.

**Decision:** Add two proactive HITL gates in the graph:

1. **`scope_clarify`** (after router, before `complex_llm`): Runs a Small LLM classifier on the user message. If the request is a build/create/implement action with underspecified dimensions (language, UI surface, feature scope), interrupts with multi-choice questions. Stores answers in `clarified_scope` state for injection into `complex_llm`'s system prompt.

2. **`plan_review`** (after `complex_llm`, before `security_proxy`): When `complex_llm` produces sensitive pending tool calls, builds a structured interrupt showing stated intent, planned actions, and pitfalls (heuristic + Small LLM). Human approval gates execution; denial short-circuits to `memory_write`.

Both nodes run **locally only** (Small/Medium LLM, no cloud). When the eventual route is `complex-cloud`, a `cloud_brief.py` module builds a compact anonymized prompt from `clarified_scope` and `plan_review` summaries instead of sending raw chat history.

**Consequences:**

- Extra latency from scope_clarify + plan_review LLM calls; mitigated by heuristic fast-paths and profile toggles
- Double-HITL risk (plan_review then security_proxy) mitigated by security_proxy skipping duplicate interrupts when plan_review was already approved
- All HITL and tool activity cards now render inline in the chat timeline (not sidebar accordions), removing the "missed request" UX gap
- `plan_review_response` client event added to WS protocol for structured plan approval/denial
- Checks scoped to `branch: hitl-improvement`

**Post-implementation fixes (2026-05-26):**

1. **Heuristic was too narrow** — `_BUILD_NOUNS` list missed common terms like "calculator" and "inventory app". Replaced with regex pattern `build/create/make a/an/the <noun>` that catches any build-target noun without an exhaustive list. Added `fastapi` and `api` to explicit signal sets so well-specified API requests don't trigger false positives.

2. **Router was preempting scope_clarify** — Router fired its own skill-ambiguity HITL for low-confidence build requests before scope_clarify could run, setting `router_clarification_used=true` and causing scope_clarify to skip. Fixed by adding `needs_clarification()` check *before* router HITL; if the heuristic detects a build request, router delegates instead of asking "which skill?".

3. **Small LLM could override the heuristic** — The Small LLM classifier's `needs_clarification` field could return `false`, silently skipping the interrupt even when the heuristic correctly identified 2+ missing dimensions. Fixed by removing the LLM's gating authority: the heuristic is the authoritative gate; the Small LLM only generates questions. Fallback generic questions are used if the LLM is unavailable or returns empty.

4. **Vision proxy preload at startup** — Gemma 4 E2B vision proxy loads lazily on first image (not at startup). Unloads after `cloud.vision_idle_unload_seconds` (300s).

## Related

- [`docs/architecture/overview.md`](architecture/overview.md) — system architecture
- [`docs/README.md`](README.md) — project documentation map

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
