---
last_verified: 2026-05-26
auto_generated: false
purpose: "LangGraph node-by-node reference: memory_inject, router, simple, complex_llm, security_proxy, tool_action, memory_write."
---

# Agent Flow (LangGraph)

## Overview

The LangGraph agent is a stateful, cyclic execution graph that orchestrates message routing, LLM inference, tool execution with security gating, and memory writeback.

## Entry Points

```text
src/agent/graph.py               # Graph builder, init_agent(), route_decision()
src/agent/nodes/router.py         # router_node()
src/agent/nodes/simple.py          # simple_node()
src/agent/nodes/complex.py         # complex_llm_node(), complex_tool_action_node()
src/agent/nodes/memory.py          # memory_inject_node(), memory_write_node()
src/agent/nodes/security_proxy.py  # security proxy gate
src/agent/tool_sets.py             # COMPLEX_TOOLS_WITH_WEB, COMPLEX_TOOLS_NO_WEB
src/agent/state.py                 # AgentState TypedDict
```

## Architecture

### Graph Topology

```
START → memory_inject → router → simple → memory_write → END
                               → complex_llm ←──────────────┐
                                    ↓                        │
                               security_proxy                │
                                    ↓                        │
                               tool_action ──────────────────┘
                                    ↓
                               memory_write → END
```

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
| Default fallback | `complex` if classification fails |
| Output | Route value + toolbox categories + `router_metadata` |

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
