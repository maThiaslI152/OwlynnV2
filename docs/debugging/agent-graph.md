---
purpose: "Debugging guide for the LangGraph agent graph: topology, node behavior, routing, and common failures."
---

# Debugging: Agent Graph (LangGraph)

**Quick Reference:** Stateful cyclic LangGraph orchestrating conversation flow. Key files: `src/agent/graph.py` (graph builder + checkpoint config), `src/agent/state.py` (AgentState definition), `src/agent/nodes/router.py` (routing logic), `src/agent/nodes/simple.py` (simple answers), `src/agent/nodes/complex.py` (tool-calling responses), `src/agent/nodes/security_proxy.py` (HITL gate), `src/agent/nodes/summarize.py` (context compression).

## Graph Topology

```
START → memory_inject → [summarize_gate → auto_summarize] → router
                                                            ├─→ simple → memory_write → END
                                                            └─→ complex_llm ↔ security_proxy ↔ tool_action
                                                                                                  ↓
                                                                                            memory_write → END
```

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| Persona/system prompt leaks into response (BUG-1) | System message included in `messages` list incorrectly | Inspect `AgentState.messages` before simple/complex node | Filter system messages from message list before passing to LLM |
| Router misclassifies (simple sent to complex, or vice versa) | Small LLM hallucination or keyword bypass misfire | Check `router_info` WS event for `classification_source` | Adjust keyword patterns in router, check small LLM output |
| Infinite loop (router → complex → tool → router) | Recursion limit not configured or graph edge misconfigured | Check iteration count in LangGraph stream | Set `recursion_limit` in graph config (default: 25) |
| Agent produces no response (empty output) | LLM returned empty content or network error swallowed | Check LangGraph stream for error events | Add timeout and error handling in complex/simple nodes |
| `ToolMessage` not followed by `AIMessage` | Tool node produced no output or graph edge broken | Check graph state after `tool_action` node | Verify tool execution completed and edge to `complex_llm` exists |
| Security proxy blocks ALL tools | `SENSITIVE_TOOLS` set too broad or all tools flagged | Check `security_proxy.py` `SENSITIVE_TOOLS` set | Ensure only truly sensitive tools are in the set |
| Summarize node compresses unnecessarily | Token estimation heuristic overestimates usage | Check `summarize_gate` condition (85% threshold) | Tune threshold or improve token counting |
| Checkpoint load fails (loss of conversation history) | Redis unavailable and MemorySaver lost state | Check Redis connectivity (see [memory.md](memory.md)) | Restart Redis; verify `checkpointer.setup()` completed |
| Node output field mismatch with state | State TypedDict keys don't match node return dicts | Check `AgentState` in `state.py` vs node return values | Align node output keys with state definition |

## Diagnostic Commands

### Inspect Graph State

```bash
# Connect to running backend and inspect thread state via Python
python3 -c "
import asyncio
from src.agent.graph import graph, checkpointer

async def inspect(thread_id):
    config = {'configurable': {'thread_id': thread_id}}
    state = await graph.aget_state(config)
    if state and state.values:
        msgs = state.values.get('messages', [])
        print(f'Thread: {thread_id}')
        print(f'Messages: {len(msgs)}')
        print(f'Router metadata: {state.values.get(\"router_metadata\", \"NOT SET\")}')
        print(f'Pending tools: {state.values.get(\"pending_tool_calls\", False)}')
        print(f'Denied tools: {state.values.get(\"denied_tools\", [])}')
        print(f'Active tokens: {state.values.get(\"active_tokens\", 0)}')
    else:
        print(f'No state found for thread {thread_id}')

asyncio.run(inspect('<thread-id>'))
"
```

### Check Redis Checkpoint

```bash
# Connect to Redis and inspect checkpoint keys
redis-cli -u redis://localhost:6379 KEYS 'checkpoint:*' | head -20

# Check checkpoint count
redis-cli -u redis://localhost:6379 DBSIZE

# Check Redis memory usage
redis-cli -u redis://localhost:6379 INFO memory | grep used_memory_human
```

### Trace Graph Execution

Run a single message through the graph with verbose logging:

```bash
python3 -c "
import asyncio, logging
logging.basicConfig(level=logging.DEBUG)

from src.agent.graph import graph
from src.agent.state import AgentState

async def trace():
    config = {'configurable': {'thread_id': 'debug-trace'}}
    initial = {'messages': [{'role': 'user', 'content': 'Hello'}]}
    
    async for event in graph.astream(initial, config, stream_mode='values'):
        node_name = event[1].get('langgraph_node', 'unknown')
        msgs = event[1].get('messages', [])
        router = event[1].get('router_metadata', {})
        print(f'Node: {node_name} | Messages: {len(msgs)} | Route: {router.get(\"route\",\"N/A\")}')

asyncio.run(trace())
"
```

Expected output:
```
Node: memory_inject | Messages: 2 | Route: N/A
Node: router | Messages: 2 | Route: simple
Node: simple | Messages: 3 | Route: simple
Node: memory_write | Messages: 3 | Route: simple
```

## Log Interpretation

### Router Node

```
# Keyword bypass (greeting)
INFO:src.agent.nodes.router:Keyword bypass: greeting → simple

# Deterministic routing (web intent)
INFO:src.agent.nodes.router:Web intent detected → complex-default

# LLM classifier
INFO:src.agent.nodes.router:LLM classifier → complex-default (confidence: 0.87)

# HITL clarification
INFO:src.agent.nodes.router:Low confidence (0.45), triggering HITL clarification
```

### Simple Node

```
# Normal execution
INFO:src.agent.nodes.simple:Simple node responding with Small_LLM

# Fallback on failure
WARNING:src.agent.nodes.simple:Small_LLM failed, falling back to Medium_Default
INFO:src.agent.nodes.simple:model_used=medium-default-fallback
```

### Complex Node

```
# Normal tool-calling execution
INFO:src.agent.nodes.complex:Complex node with Medium_Default, 12 tools bound

# Tool calls emitted
INFO:src.agent.nodes.complex:LLM requested 2 tool calls: [web_search, fetch_webpage]

# Prose detection (model output text instead of tool calls)
WARNING:src.agent.nodes.complex:Model produced prose instead of tool calls, auto-reading workspace files

# Fallback chain
WARNING:src.agent.nodes.complex:Medium_LongCtx failed (context too large), escalating to Cloud
```

### Security Proxy

```
# Auto-approved safe tool
INFO:src.agent.nodes.security_proxy:Tool 'web_search' auto-approved (safe)

# HITL triggered
INFO:src.agent.nodes.security_proxy:Sensitive tool 'write_workspace_file' requires HITL approval
INFO:src.agent.nodes.security_proxy:Interrupting graph for user approval

# Denied
INFO:src.agent.nodes.security_proxy:User denied tool 'edit_workspace_file', adding to denied_tools
```

### Summarize Node

```
# Context compression triggered
INFO:src.agent.nodes.summarize:Active tokens 8700/10000 (87%), compressing 12 messages
INFO:src.agent.nodes.summarize:Summarized: freed ~4500 tokens, 5 takeaways generated

# Skip (below threshold)
INFO:src.agent.nodes.summarize:Active tokens 3200/10000 (32%), skipping summarization
```

## Bug-Specific Debugging

### BUG-1: Persona/System Prompt Leaks into First Response

**Location:** `src/agent/nodes/simple.py` or `src/agent/nodes/complex.py`

**Root cause hypothesis:** The system message (containing persona description) is being included in the `messages` list passed to the LLM as if it were a user/assistant message. The LLM then echoes it back as its response.

**Debug steps:**

1. Inspect `AgentState.messages` before entering the simple/complex node:
   - System messages should not appear in the chat message list visible to the LLM as conversation context.
   - They should be injected into the prompt separately.

2. In `simple_node()`:
   - Check how `SystemMessage` is added to the conversation.
   - Verify the LLM receives `[SystemMessage(prompt), HumanMessage(user_input)]` — the SystemMessage should be the prompt instruction, not the persona description.

3. In `complex_llm_node()`:
   - Check the system prompt construction.
   - Ensure persona/profile text is part of the system prompt, not part of the message history.

## Step-by-Step Procedures

### Procedure 1: Agent Produces Wrong Response

1. Capture the `router_info` WS event to see routing decision:
   - Open DevTools → Network → WS tab
   - Note the `route`, `confidence`, `classification_source`, and `reasoning` fields

2. If route is correct but output is wrong:
   - Check which model produced the response (from `model_info` WS event)
   - For simple route: see [llm-pool.md](llm-pool.md) for small LLM debugging
   - For complex route: check tool binding (see [tools.md](tools.md))
   - For BUG-1 (persona leak): check message formatting in simple/complex nodes

3. If route is wrong:
   - `classification_source: "keyword_bypass"` → keyword patterns in `router.py` need adjustment
   - `classification_source: "llm_classifier"` → small LLM misclassified; check prompt in router
   - `classification_source: "hitl"` → HITL triggered; low confidence routing
   - `classification_source: "deterministic"` → deterministic rule fired incorrectly

### Procedure 2: Infinite Loop / Message Never Completes

1. Check the graph's recursion limit:
   - Default is 25 (set in `graph.py` via `recursion_limit` in config)
   - If tool calls cycle (LLM calls tool, tool result leads to more tool calls), count can hit limit

2. Check for router → complex → router cycling:
   - Each complete message turn should visit the router once at the start
   - A loop would show: router → complex → tool → complex → tool → ... (inside one turn)

3. Force kill the run:
   - Send `{"type": "stop"}` via WebSocket
   - Or restart the backend

4. Reduce recursion limit for tighter loop detection:
   - Set `recursion_limit` lower in graph config for testing

### Procedure 3: Security Proxy Blocks Legitimate Action

1. Check if the tool is in `SENSITIVE_TOOLS` set in `src/agent/nodes/security_proxy.py`:
   - Currently: `write_workspace_file`, `edit_workspace_file`, `delete_workspace_file`, `notebook_run`
   - If a legitimate tool is in this set, HITL approval is required

2. Check if the tool arguments trigger dangerous pattern detection:
   - `security_proxy.py` scans arguments for patterns like `rm -rf`, `sudo`, `curl`, `ssh`
   - Legitimate commands may match these patterns

3. To bypass for testing:
   - Set execution policy to `auto_approve` via `PUT /api/unified-settings` with `{"execution_policy": "auto_approve"}`
   - Or modify `SENSITIVE_TOOLS` set temporarily

## Known Fixes

- **`print()` → logger**: All nodes now use structured logging via `src/config/logging_config.py`. See [STATUS.md](../STATUS.md).
- **Bare `raise` in complex.py**: Replaced with graceful error message. See [STATUS.md](../STATUS.md).
- **Denied tools tracking**: Denied tool names accumulate in `AgentState.denied_tools` to prevent LLM retries. See [AGENT_FLOW.md](../AGENT_FLOW.md) for details.
- **Auto-summarize**: Wired between `memory_inject` and `router` with 85% threshold. See [AGENT_FLOW.md](../AGENT_FLOW.md).
- See also: [ARCHITECTURE_OVERVIEW.md](../ARCHITECTURE_OVERVIEW.md) section 1 for full graph flow.
