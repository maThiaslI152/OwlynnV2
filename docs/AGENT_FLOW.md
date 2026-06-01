---
status: active
category: architecture
last_updated: 2026-05-31
owner: human
---

# Agent Flow (LangGraph)

> **Purpose:** LangGraph agent execution flow, node descriptions, and state transitions.

## Overview

The LangGraph agent is a stateful, cyclic execution graph that orchestrates message routing, LLM inference, tool execution with security gating, and memory writeback.

## Entry Points

```text
src/agent/graph.py               # Graph builder, init_agent(), route_decision()
src/agent/nodes/router.py         # router_node()
src/agent/nodes/simple.py          # simple_node()
src/agent/nodes/complex.py         # complex_llm_node(), complex_tool_action_node()
src/agent/nodes/scope_clarify.py   # scope_clarify_node() (NEW)
src/agent/nodes/plan_review.py     # plan_review_node() (NEW)
src/agent/nodes/memory.py          # memory_inject_node(), memory_write_node()
src/agent/nodes/security_proxy.py  # security proxy gate
src/agent/hitl/policy.py          # Shared policy + is_sensitive_call() (NEW)
src/agent/hitl/context.py         # build_hitl_context(), enrich_interrupt() (NEW)
src/agent/hitl/cloud_brief.py     # Cloud brief builder (NEW)
src/agent/hitl/scope_heuristics.py # Scope clarification heuristics (NEW)
src/agent/tool_sets.py             # COMPLEX_TOOLS_WITH_WEB, COMPLEX_TOOLS_NO_WEB
src/agent/state.py                 # AgentState TypedDict
```

## Architecture

### Graph Topology

```
START → memory_inject → auto_summarize? → router → simple → memory_write → END
                                              → scope_clarify ─────────────────┐
                                                   ↓                          │
                                              complex_llm ←───────────────────┐│
                                                   ↓                         ││
                                              plan_review ─────┐             ││
                                                   ↓            │(denied)     ││
                                              security_proxy    │             ││
                                                   ↓            │             ││
                                              tool_action ──────┘             ││
                                                   ↓                          ││
                                              memory_write ←──────────────────┘│
                                                                     ←─────────┘
```

HITL interrupt nodes (highlighted):
- **scope_clarify**: Runs after router for vague build/create requests. Uses Small LLM to ask clarifying questions.
- **plan_review**: Runs after complex_llm when sensitive tools are planned. Reviews intent + pitfalls before approval.
- **security_proxy**: Existing security gate (deduplicated — skips if plan_review already approved).

## Flow

### memory_inject

| Concern | Detail |
|---------|--------|
| Input | User message + thread_id |
| Action | Builds `memory_context` from Mem0 search + user profile + topics/interests |
| Filtering | Filters out config fields (LLM URLs, tokens, etc.) from profile |
| Caching | 5-min TTL per thread (`MemoryContextCache`) |
| Output | AgentState with populated `memory_context` |

### router

| Concern | Detail |
|---------|--------|
| Input | AgentState with `memory_context` and user message |
| Keyword bypass | Greetings → `simple`. Web intent → `complex` |
| Tool history | Conversation with tool calls in history → stays `complex` |
| LLM classification | Falls back to Small_LLM JSON classification |
| Build delegation | Detects build/create requests via `scope_heuristics.needs_clarification()` and skips router HITL — delegates to `scope_clarify` instead of asking generic skill questions |
| Default fallback | `complex` if classification fails |
| Output | Route value + toolbox categories + `router_metadata` |

### scope_clarify

| Concern | Detail |
|---------|--------|
| Input | AgentState with user message, route must start with `complex` |
| Gate 1 — Heuristic | `scope_heuristics.needs_clarification()` — regex-based detection of build/create verb + article + noun patterns. Requires 2+ missing dimensions (language, ui_surface) to trigger. Adds `fastapi` and `api` to explicit signal sets. |
| Gate 2 — Profile | `scope_clarification_enabled` (default true) |
| Gate 3 — Dedup | Skips if `router_clarification_used` is true (router already handled) |
| LLM | Small LLM generates 1-3 clarifying questions with choices; heuristic is authoritative — LLM cannot override the need for clarification |
| Fallback | Generic questions built from missing dimensions when Small LLM is unavailable or returns empty |
| Interrupt | `scope_clarification_required` type with `task_summary`, `questions[]`, `pitfalls[]` |
| Resume | `ask_user_response` with `answers` dict keyed by question `id` |
| Output | `clarified_scope` dict injected into `complex_llm` system prompt as CONFIRMED REQUIREMENTS |
| Max questions | 3 per interrupt, 1 round per message |
| Model tier | Small LLM only — never uses cloud |

### simple

| Concern | Detail |
|---------|--------|
| Model | Small_LLM (LFM2.5-1.2B) |
| Tools | None bound |
| Memory context | Not injected into prompt |
| Artifact cleaning | Strips `<think>` tags and reasoning artifacts |
| Current date | Injected into prompt |
| Response style | Injected from user settings |
| Fallback | Falls back to Medium_Default on model failure |
| Output | Single `AIMessage` |

### complex_llm

| Concern | Detail |
|---------|--------|
| Model | Selected M-tier or Cloud model with dynamically-bound tools |
| Tool count | Up to 22 tools (with web) or 20 (without web) |
| Context | Injects current date, memory context, persona, response style |
| Artifact cleaning | Strips `<think>` tags from output |
| Auto-read | Detects when model outputs prose instead of tool calls for workspace files, auto-reads them |
| State flag | Sets `pending_tool_calls` flag for security proxy |
| Output | `AIMessage` with optional `tool_calls` + `fallback_chain` |

### security_proxy

| Concern | Detail |
|---------|--------|
| Sensitive tools | `write_workspace_file`, `edit_workspace_file`, `delete_workspace_file`, `notebook_run` |
| Dangerous patterns | Blocks `rm -rf`, `sudo`, `curl`, `ssh`, etc. in arguments |
| Safe tools | Auto-approved, flow continues to `tool_action` |
| Sensitive tools | Triggers HITL `interrupt()` — frontend shows inline security prompt |
| Approval | Resumes graph, continues to `tool_action` |
| Denial | Appends denied tool names to `denied_tools` state field, emits `[POLICY BLOCK]` AIMessage, exits to `memory_write` |

**Denied tools tracking**: Denied tool names accumulate in `AgentState.denied_tools` across turns. On next `complex_llm` invocation, system prompt includes `BLOCKED TOOLS (do NOT call these): ...` to prevent retries.

### Frontend Inline Security Prompt

Renders an inline card in the chat area (between messages and composer) with:
- Tool name, risk category, rationale
- Three buttons: **Decline**, **Allow**, **Auto-Allow** (sets `execution_policy` to `auto_approve` via `PUT /api/unified-settings`)

Key files:

| File | Role |
|------|------|
| `frontend-v2/src/state/useAppStore.ts` | `InlineSecurityPrompt` type, Zustand state |
| `frontend-v2/src/App.tsx` | `handleInterrupt`, `handleAutoApprove` logic |
| `frontend-v2/src/components/AppShell.tsx` | Renders inline card |
| `frontend-v2/src/index.css` | `.security-inline-*` styles |
| `src/agent/nodes/security_proxy.py` | Gate logic, denied-tool accumulation |
| `src/agent/state.py` | `denied_tools` field |

### tool_action

| Concern | Detail |
|---------|--------|
| Execution | Approved tool calls via LangGraph `ToolNode` |
| Fetch retry | Appends nudges for failed static fetches |
| Answer nudge | Appends web search answer nudges for successful searches |
| Loop | Returns to `complex_llm` for next reasoning step |

### memory_write

| Concern | Detail |
|---------|--------|
| Recording | Records conversation via `personal_assistant` module |
| Extraction | Extracts topics and interests |
| Mem0 save | Saves enriched facts to Mem0/Qdrant |
| Cache invalidation | Invalidates memory context cache |
| WS event | Emits `memory_updated` |

## Tool Binding

Defined in `src/agent/tool_sets.py`:

| Set | Count | Tools |
|-----|-------|-------|
| `COMPLEX_TOOLS_WITH_WEB` | 22 | Full tool set including `web_search`, `fetch_webpage` |
| `COMPLEX_TOOLS_NO_WEB` | 20 | All tools except web search |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Keyword bypass before LLM classification | Fast path for obvious greetings | May misclassify edge cases |
| Simple node disables tools | Low latency for trivial queries | Can't handle web/live-data questions |
| Security proxy HITL gate | Safety for destructive operations | Latency for approved sensitive calls |
| Denied tools accumulation across turns | Prevents LLM from retrying denied tools | State grows across conversation |

## Testing

```bash
pytest tests/test_router_properties.py -v
pytest tests/test_llm_pool.py -v
pytest tests/test_swap_manager.py -v
pytest tests/test_security_proxy.py -v
pytest tests/test_memory_nodes.py -v
```

## Configuration

| Profile Field | Type | Default | Node |
|---------------|------|---------|------|
| `router_hitl_enabled` | boolean | `true` | router |
| `router_clarification_threshold` | float | `0.6` | router |
| `cloud_escalation_enabled` | boolean | `true` | complex_llm |
| `cloud_anonymization_enabled` | boolean | `true` | complex_llm (cloud path) |
| `medium_models` | object | Three variant keys | complex_llm (model selection) |

## Related

- [`docs/ARCHITECTURE_OVERVIEW.md`](ARCHITECTURE_OVERVIEW.md) — system architecture
- [`docs/README.md`](README.md) — project documentation map

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
