---
status: active
category: architecture
audience: agent
last_updated: 2026-08-25
owner: ai-agent
---

# Agent Flow (LangGraph)

> **Purpose:** LangGraph agent execution flow, node descriptions, and state transitions.

## Overview

The LangGraph agent is a stateful, cyclic execution graph that orchestrates message routing, LLM inference, tool execution with security gating, and memory writeback.

**Local-first (2026-08-25):** Default `cloud_routing_mode=local_only`. Live router uses deterministic bypasses (no classifier LLM). Unified Gemma 4 12B handles simple answers, complex local reasoning, and extraction. Coherence LLM is skipped on simple / short / successful-web turns. Web-only toolbox uses tool-first search (no bind_tools planning prefill). Pentest UI is gated by `features.pentest_enabled` (default false).

## Entry Points

```text
src/agent/core/graph.py        # Graph builder, init_agent(), route_decision()
src/agent/routing/router.py    # router_node() — deterministic + local-first
src/agent/routing/deterministic.py  # Keyword / heuristic bypasses (incl. simple trivia)
src/agent/core/simple.py       # simple_node() — tiny prompt, no tools
src/agent/core/complex.py      # complex_llm_node(); tool-first web inject
src/agent/core/tool_first_web.py  # Deterministic web_search then short synthesis
src/agent/core/ask_user_guards.py # Block ask_user loops on code-review-without-code
src/agent/nodes/coherence.py   # Fast-path skip + optional LLM check
src/agent/nodes/memory.py      # memory_inject_lite, memory_retrieve (sets active_tokens), memory_write
src/agent/nodes/scope_clarify.py / plan_review.py / security_proxy.py
```

## Architecture

### Full Graph Topology (with Semantic Cache)

```
WebSocket intake
     │
     ▼
check_semantic_cache(prompt, project_id)  ← pre-graph bypass
     │
     ├─ HIT  → stream cached answer → idle event                  (graph never runs)
     │
     └─ MISS ─────────────────────────────────────────────────────────────────┐
                                                                               ▼
START → memory_inject_lite → router → memory_retrieve → auto_summarize?
                                                        (active_tokens from retrieve)
      → simple ──► coherence_check (often skipped) → memory_write → END
      → scope_clarify → complex_llm
            │              │
            │    tool-first web: inject web_search (no bind_tools) ──► tool_action
            │              │
            │    plan_review / security_proxy (HITL)
            │              ▼
            │         tool_action ──► complex_llm (synthesis, no tools on tool-first)
            │              │
            └──────────────┘ → coherence_check → memory_write → store_semantic_cache()
```

### Latency envelope (local_only, warm 12B)

| Turn type | Foreground 12B calls |
|-----------|----------------------|
| Greeting / short trivia → simple | 1 answer (coherence skipped) |
| Web “latest X” → tool-first | 0 planning + 1 synthesis (coherence skipped) |
| Complex tools | plan/synth rounds as needed; coherence when not skipped |

## Flow

### router

| Concern | Detail |
|---------|--------|
| Live path | Deterministic bypasses → hardcoded local-first (no RouteClassifier LLM) |
| Simple widen | Casual chatter + short trivia / explain → `simple` |
| Web intent | `selected_toolboxes=["web_search"]` → complex-default + tool-first |
| Cloud | Only when profile `cloud_routing_mode` is `auto`/`cloud_first` and policy allows |
| Default complex route | `complex-default` (legacy alias `complex-local`) |

### coherence_check

| Concern | Detail |
|---------|--------|
| Skip when | `coherence.enabled=false`, route=`simple`, short answer, or successful web synthesis |
| Retry | Still gated by `coherence.enabled` + score < retry_threshold |

### complex_llm (tool-first web)

When toolbox is exactly `["web_search"]` and no search yet this turn: inject a synthetic `web_search` tool call, run tools, then one unbound synthesis (`complex.tool_first_synth_token_budget`, default 1024; no second synth retry). Escalate to bind_tools only if search fails. Pronoun follow-ups expand the search query with the prior human turn.

**ask_user guard:** Code-review / “bugs in this function” with no attached code uses toolbox `none` and strips `ask_user` so the model answers from history instead of HITL loops (`src/agent/core/ask_user_guards.py`).

**simple path:** `simple.max_tokens` (default 512) caps completion; does not inherit `models.main.max_tokens` (often 8k).

**TTFT:** First streamed WS `chunk` stamps audit `ttft_ms`; idle logs `turn_duration_ms` (`src/api/ws/handler.py`).

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| local_only default | Privacy + M4 Air fit; cloud is DeepSeek opt-in | User must flip for Eco-Mode cloud |
| Skip coherence on fast paths | Same-model tax was ~1 extra 12B call every turn | Less self-correction on short/web |
| Tool-first web | Avoid tool-schema prefill before search | Escalation path if search empty |
| Pentest hidden | Focus Normal+Study latency first | Feature flag to re-enable |
| RouteClassifier quarantined | Dead on live path; keep for tests | Docs must not claim LLM router |

## Testing

```bash
pytest tests/test_router_web_intent.py tests/test_response_coherence.py tests/test_tool_first_web.py tests/test_simple_trivia_bypass.py -v
```
