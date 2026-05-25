---
last_verified: 2026-05-26
auto_generated: false
---

# Extending the Agent (Developer Guide)

Reference for developers modifying Owlynn's agent behavior. Covers the LangGraph execution flow, tool contract, and frontend WebSocket event stream.

## Overview

Three subsystems must stay consistent when modifying agent behavior:

- LangGraph execution flow (`src/agent/graph.py` and nodes under `src/agent/nodes/`)
- Tool contract between LLM and tool execution (`src/agent/tool_sets.py`, `src/agent/nodes/complex.py`, `src/api/server.py`)
- Frontend WebSocket event stream (`docs/CHAT_PROTOCOL.md`)

## Entry Points

```text
src/agent/nodes/router.py       # router_node() — routing behavior
src/agent/graph.py              # route_decision() — route validation
src/agent/nodes/simple.py        # simple_node() — simple answers
src/agent/nodes/complex.py       # complex_llm_node() — tool-calling cycle
src/agent/tool_sets.py           # ToolboxRegistry — tool binding
src/agent/nodes/memory.py        # memory_inject_node(), memory_write_node()
src/tools/                       # Tool implementations (@tool decorators)
src/api/server.py                # serialize_message() — frontend contract
docs/CHAT_PROTOCOL.md            # WebSocket event contract
```

## Architecture

### Graph Topology

```
START → memory_inject → router → simple → memory_write → END
                               → complex_llm ↔ security_proxy ↔ tool_action → memory_write → END
```

### Consistency Constraints

- `complex_llm` → `security_proxy` → `tool_action` → loop back to `complex_llm` is the secure tool cycle
- `simple` node explicitly tells the model "Do not use tools" — routing web/live-data questions to `simple` prevents tool usage
- The frontend expects responses as `type: "chunk"` and/or `type: "message"` events from LangGraph streaming
- Tool calls must appear in `AIMessage.tool_calls`; tool results as `ToolMessage` outputs

## API

### Routing Behavior

`router_node()` → `src/agent/nodes/router.py`
- Behavior: Classifies requests and selects route + toolbox categories
- Change points: `simple_keywords` keyword bypass, `_WEBISH_HINTS` web intent forcing
- Risk: Routing web/live-data questions to `simple` prevents tool usage (simple node disables tools)

`route_decision()` → `src/agent/graph.py`
- Behavior: Validates/normalizes `route` value into `simple|complex`
- Change if: Adding additional route values — update the conditional mapping

### Simple Node Behavior

`simple_node()` → `src/agent/nodes/simple.py`
- Behavior: Small_LLM direct answer, no tools, no memory context
- Change points: `SIMPLE_PROMPT` (especially "Do not use tools." directive), `response_style` system hints
- Contract: Returns single `AIMessage`, typically no tool calls

### Complex Node Behavior

`complex_llm_node()` → `src/agent/nodes/complex.py`
- Behavior: M-tier or Cloud model with dynamically-bound tools
- Change points: `COMPLEX_PROMPT`, `COMPLEX_TOOL_GUIDANCE_WEB` / `_NO_WEB` guidance strings, tool list selection logic (`web_search_enabled`, `mode`)
- Tool sets: resolved via `src/agent/tool_sets.py` (`resolve_tools()`)

### Memory Injection

`memory_inject_node()` → `src/agent/nodes/memory.py`
- Behavior: Builds `memory_context` from long-term memory search, user profile, enhanced personal assistant context
- Cache: `MemoryContextCache` keyed by `thread_id`
- Risk: Changing context format affects prompts in `simple_node()` and `complex_llm_node()`. Changing cache invalidation fields causes stale memory

### Memory Writing

`memory_write_node()` → `src/agent/nodes/memory.py`
- Behavior: Records conversation summary + topics/interests, writes enriched facts to Mem0, invalidates memory context cache
- Dependencies: Topic extraction/enrichment changes affect `docs/guides/personal_assistant_memory.md`

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Secure tool cycle (complex → proxy → action → loop) | Mandatory gating for destructive actions | Extra hop per tool call |
| Simple node disables tools | Fast path for trivial queries | Misrouting web queries to simple breaks functionality |
| Memory context cache per thread_id | Reduce repeated memory lookups | Stale data if cache invalidation incomplete |
| Structured ask_user_response payloads | Preserved without backend string coercion | Frontend must handle object types |

## Testing

Minimum testing for developer changes:

```bash
python tests/run_tests.py
pytest tests/ -k "test_router" -v
pytest tests/ -k "test_complex" -v
pytest tests/ -k "test_memory" -v
cd frontend-v2 && npx vitest run
```

Exercise at minimum:
- Simple greeting path (no tools)
- Complex path with tool calling (e.g., `web_search` intent)
- Memory write + recall (multi-turn)

## Adding/Modifying a Tool

1. Implement the tool in `src/tools/*` as a LangChain `@tool`
2. Export from `src/tools/__init__.py`
3. Add to relevant list(s) in `src/agent/tool_sets.py`
4. Update guidance text in `src/agent/nodes/complex.py`
5. Verify frontend rendering via `docs/CHAT_PROTOCOL.md`

Frontend rendering depends on `serialize_message()` in `src/api/server.py`:
- Tool calls must appear in `AIMessage.tool_calls`
- Tool results must appear as `ToolMessage` outputs

## Adding New Graph Nodes

Update at minimum:
- `src/agent/graph.py` — topology (edges and conditional routing)
- `src/agent/state.py` — fields produced/consumed
- `src/api/server.py` — event forwarding (new message types)

Prefer extending the existing secure cycle (`complex_llm` + `security_proxy` + `tool_action`) over introducing a separate workflow.

## Documentation Checklist

When changing core behavior, update:

| Change Type | Update |
|------------|--------|
| Frontend/backend WebSocket keys | `docs/CHAT_PROTOCOL.md` |
| Tool binding or tool guidance | `docs/TOOLS.md` |
| Routing/node topology | `docs/AGENT_FLOW.md` |
| Memory context format | `docs/guides/personal_assistant_memory.md` |
