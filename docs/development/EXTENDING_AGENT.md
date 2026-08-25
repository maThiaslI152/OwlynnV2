---
status: active
category: guide
last_updated: 2026-08-25
owner: ai-agent
audience: agent
---

# Extending the Agent (Developer Guide)

> **Purpose:** Developer guide for extending Owlynn's agent behavior, tools, and event stream.

Reference for developers modifying Owlynn's agent behavior. Covers the LangGraph execution flow, tool contract, and frontend WebSocket event stream.

## Overview

Three subsystems must stay consistent when modifying agent behavior:

- LangGraph execution flow (`src/agent/core/graph.py` and nodes under `src/agent/core/` and `src/agent/nodes/`)
- Routing (`src/agent/routing/` — deterministic bypasses; live path does not use RouteClassifier LLM)
- Dynamic tool contract (`src/tools/registry.py`, `src/agent/tool_sets.py`, `src/agent/core/complex.py`, `src/agent/core/tool_first_web.py`, `src/agent/core/complex_tool_action.py`)
- Frontend WebSocket event stream (`docs/development/CHAT_PROTOCOL.md`)

## Entry Points

```text
src/agent/routing/router.py       # router_node() — routing behavior
src/agent/core/graph.py           # route_decision() — route validation & graph topology
src/agent/core/simple.py          # simple_node() — fast answers
src/agent/core/complex.py         # complex_llm_node() coordinator facade
src/agent/core/complex_prompt.py  # Prompt templates & deterministic tool ordering
src/agent/core/complex_executor.py # Cloud & fallback invocation
src/agent/core/complex_tool_action.py # Parallel tool dispatch, output bounding, error hints
src/tools/registry.py             # ToolRegistry (dynamic discovery, check_fn gating)
src/agent/tool_sets.py            # TOOLBOX_REGISTRY — tool binding
src/agent/nodes/memory.py         # memory_inject_lite_node(), memory_retrieve_node(), memory_write_node()
src/tools/                        # Tool implementations (@tool and @registry.register)
src/api/ws/handler.py             # serialize_message() — frontend contract
docs/development/CHAT_PROTOCOL.md # WebSocket event contract
```

## Architecture

### Graph Topology

```
START → memory_inject_lite → router → memory_retrieve → auto_summarize? → simple → memory_write → END
                                                                              → scope_clarify → complex_llm
                                                                                    ↔ plan_review / security_proxy
                                                                                    ↔ complex_tool_action → memory_write → END
```

### Consistency Constraints

- `complex_llm` → `security_proxy` → `complex_tool_action` → loop back to `complex_llm` is the secure tool cycle
- `simple` node explicitly tells the model "Do not use tools" — routing web/live-data questions to `simple` prevents tool usage
- **KV Prompt Cache Preservation**: Never inject synthetic `HumanMessage` prompts mid-turn; embed error recovery guidance directly in `ToolMessage(content=...)`
- **Deterministic Tool Ordering**: All tool schemas are sorted alphabetically before binding to LLMs
- The frontend expects responses as `type: "chunk"` and/or `type: "message"` events from LangGraph streaming
- Tool calls must appear in `AIMessage.tool_calls`; tool results as `ToolMessage` outputs

## API

### Routing Behavior

`router_node()` → `src/agent/routing/router.py`
- Behavior: Classifies requests and selects route + toolbox categories
- Change points: `simple_keywords` keyword bypass, `_WEBISH_HINTS` web intent forcing, `_toolbox_for_local_first()` (narrow local-first toolboxes; lean default never implicit `["all"]`)
- Risk: Routing web/live-data questions to `simple` prevents tool usage (simple node disables tools)

`route_decision()` → `src/agent/core/graph.py`
- Behavior: Validates/normalizes `route` value into `simple|complex-local|complex-cloud`
- Change if: Adding additional route values — update the conditional mapping

### Simple Node Behavior

`simple_node()` → `src/agent/core/simple.py`
- Behavior: Small_LLM direct answer, no tools, no memory context
- Change points: `SIMPLE_PROMPT` (especially "Do not use tools." directive), `response_style` system hints
- Contract: Returns single `AIMessage`, typically no tool calls

### Complex Node Behavior

`complex_llm_node()` → `src/agent/core/complex.py` (facade over `complex_prompt.py` and `complex_executor.py`)
- Behavior: M-tier or Cloud model with dynamically-bound tools
- Change points: `src/agent/core/complex_prompt.py`, guidance strings, tool list selection logic (`web_search_enabled`, `mode`), `_rerank_tools_for_invoke` before bind + context breakdown
- Tool sets: resolved via `src/agent/tool_sets.py` (`resolve_tools()`); `"all"` / `COMPLEX_TOOLS_*` omit screen-assist and ipynb (named toolboxes keep them)

### Memory Injection & Retrieval

`memory_inject_lite_node()` / `memory_retrieve_node()` → `src/agent/nodes/memory.py`
- Behavior: Split memory path (lite context before router, pgvector search after router if gated)
- Storage: PostgreSQL pgvector (`memory_vectors` table) + PostgreSQL `memories` table

### Memory Writing

`memory_write_node()` → `src/agent/nodes/memory.py`
- Behavior: Records conversation summary + topics/interests, enqueues async extraction to PostgreSQL `extraction_jobs`, triggers `SkillLearnerEngine`
- Dependencies: `src/memory/extraction/worker.py` and `src/memory/skills_learner.py`

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Secure tool cycle (complex → proxy → action → loop) | Mandatory gating for destructive actions | Extra hop per tool call |
| Simple node disables tools | Fast path for trivial queries | Misrouting web queries to simple breaks functionality |
| Memory context cache per thread_id | Reduce repeated memory lookups | Stale data if cache invalidation incomplete |
| Structured ask_user_response payloads | Preserved without backend string coercion | Frontend must handle object types |
| In-place ToolMessage recovery | Preserves KV cache and message alternation | Error instructions packed in tool result |

## Testing

Minimum testing for developer changes:

```bash
./scripts/ci.sh --quick
```

## Adding/Modifying a Tool

1. Implement the tool in `src/tools/*` as a LangChain `@tool` or with `@registry.register(name, toolbox="...", check_fn=...)`
2. Export from `src/tools/__init__.py`
3. If not using `@registry.register()`, add to `TOOLBOX_REGISTRY` in `src/agent/tool_sets.py`
4. Update guidance text in `src/agent/core/complex_prompt.py` if needed
5. Verify frontend rendering via `docs/development/CHAT_PROTOCOL.md`

Frontend rendering depends on `serialize_message()` in `src/api/ws/handler.py`:
- Tool calls must appear in `AIMessage.tool_calls`
- Tool results must appear as `ToolMessage` outputs

## Adding New Graph Nodes

Update at minimum:
- `src/agent/graph.py` — topology (edges and conditional routing)
- `src/agent/state.py` — fields produced/consumed
- `src/api/ws/handler.py` — event forwarding (new message types)

Prefer extending the existing secure cycle (`complex_llm` + `security_proxy` + `tool_action`) over introducing a separate workflow.

## Documentation Checklist

When changing core behavior, update:

| Change Type | Update |
|------------|--------|
| Frontend/backend WebSocket keys | `docs/CHAT_PROTOCOL.md` |
| Tool binding or tool guidance | `docs/TOOLS.md` |
| Routing/node topology | `docs/AGENT_FLOW.md` |
| Memory context format | `docs/guides/personal_assistant_memory.md` |

## Related

- [`docs/README.md`](README.md) — project documentation map
- [`docs/AGENT_FLOW.md`](AGENT_FLOW.md) — node-by-node flow
- [`docs/architecture/overview.md`](architecture/overview.md) — system architecture

## Last updated

2026-06-10 — graph topology synced with graph.py
