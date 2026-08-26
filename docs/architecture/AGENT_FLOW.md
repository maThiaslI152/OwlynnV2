---
status: active
category: architecture
audience: agent
last_updated: 2026-08-26
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
src/agent/core/complex.py      # complex_llm_node(); tool-first web / list-read inject
src/agent/core/tool_first_web.py  # Deterministic web_search then extractive/short synthesis
src/agent/core/tool_first_list_read.py  # Deterministic list+read (T5) without bind_tools
src/agent/core/tool_first_write.py  # Deterministic write inject helpers
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
| Greeting / short trivia → simple | 1 answer (coherence skipped; `simple.max_tokens` 128) |
| Web “latest X” → tool-first | 0 planning + extractive (or 1 unbound synth); coherence skipped |
| Clear list+read → tool-first | inject list+read + post-read short-circuit (no second LLM) |
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

When toolbox is exactly `["web_search"]` and the **current turn** has no `web_search` ToolMessage yet: inject a synthetic `web_search` tool call, run tools, then prefer extractive synthesis (`complex.tool_first_extractive_synth`, default true) — otherwise one unbound synth (`complex.tool_first_synth_token_budget`, default 384; no second synth retry). Escalate to bind_tools only if search fails. Pronoun follow-ups expand the search query with the prior human turn.

**Sticky phase:** Checkpointed `_tool_first_web_phase=done` must **not** block a later user turn. `maybe_clear_stale_tool_first_web_phase` clears `done` when the new turn has not searched yet (fixes topic-drift T3/T6). Only mid-turn `phase=search` blocks re-inject.

### complex_llm (tool-first list/read + short-circuits)

Clear “list files and read note.txt” intents inject `list_workspace_files` + `read_workspace_file` without a bind_tools planning round (`tool_first_list_read.py`). After a successful read (or write), post-read / post-write short-circuits confirm without a second LLM round (T5 / T4).

**ask_user guard:** Code-review / “bugs in this function” with no attached code uses toolbox `none` and strips `ask_user` so the model answers from history instead of HITL loops. Clear workspace-write asks (`write_workspace_file` / “save … as note.txt”) also strip `ask_user` (and force a write tool call if the model still emits it). `GraphInterrupt` from `ask_user` must re-raise in `complex_tool_action` — never become a `system_error` ToolMessage (`src/agent/core/ask_user_guards.py`).

**Multi-turn tool trim:** `_trim_tool_history` always soft-caps ToolMessages from *prior* human turns (`tool_output.prior_turn_max_chars`, default 400) and caps in-turn payloads (`tool_output.current_turn_max_chars`, default 2000) so topic-drift web digressions do not re-prefill fat search blobs.

**simple path:** `simple.max_tokens` (default **128**) caps completion; does not inherit `models.main.max_tokens` (often 8k). Streaming honors the same cap.

**TTFT:** First streamed WS `chunk` stamps audit `ttft_ms`; idle logs `turn_duration_ms` (`src/api/ws/handler.py`).

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| local_only default | Privacy + M4 Air fit; cloud is DeepSeek opt-in | User must flip for Eco-Mode cloud |
| Skip coherence on fast paths | Same-model tax was ~1 extra 12B call every turn | Less self-correction on short/web |
| Tool-first web | Avoid tool-schema prefill before search; clear sticky `done` on new turns | Escalation path if search empty |
| Tool-first list/read | Skip bind_tools for clear list+read (T5) | Only clear intents |
| Pentest hidden | Focus Normal+Study latency first | Feature flag to re-enable |
| RouteClassifier quarantined | Dead on live path; keep for tests | Docs must not claim LLM router |

## Testing

```bash
pytest tests/test_router_web_intent.py tests/test_response_coherence.py \
  tests/test_tool_first_web.py tests/test_tool_first_list_read.py \
  tests/test_simple_trivia_bypass.py -v
```
