# Agent Flow (LangGraph)

## Graph Topology

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

## Node Details

### memory_inject
- Builds `memory_context` from Mem0 search + user profile + topics/interests
- Filters out config fields (LLM URLs, tokens, etc.) from profile
- Caches context per thread (5-min TTL)

### router
- Keyword bypass for greetings → `simple`
- Web intent detection → `complex`
- Conversation with tool history → stays `complex`
- Falls back to LFM2.5-1.2B JSON classification
- Default fallback: `complex`

### simple
- LFM2.5-1.2B, no tools, no memory context in prompt
- Strips `<think>` tags and reasoning artifacts
- Falls back to Qwen3.5-9B on model failure
- Injects current date and response style

### complex_llm
- Qwen3.5-9B with 20 tools bound
- Injects current date, memory context, persona, response style
- Strips `<think>` tags from output
- Auto-reads workspace files when model outputs prose instead of tool calls
- Sets `pending_tool_calls` flag for security proxy

### security_proxy
- Checks tool names against `SENSITIVE_TOOLS` set (`write_workspace_file`, `edit_workspace_file`, `delete_workspace_file`, `notebook_run`)
- Checks arguments for dangerous patterns (rm -rf, sudo, curl, ssh, etc.)
- Safe tools: auto-approved, flow continues to `tool_action`
- Sensitive tools: triggers HITL `interrupt()` — frontend shows an **inline security prompt** in the chat area (see below)
- On approval: resumes the graph, flow continues to `tool_action`
- On denial: appends denied tool names to `denied_tools` state field, emits a `[POLICY BLOCK]` AIMessage, and exits to `memory_write`

**Denied tools tracking:**
- Denied tool names accumulate in `AgentState.denied_tools` across turns
- On the next `complex_llm` invocation, the system prompt includes `BLOCKED TOOLS (do NOT call these): ...` so the LLM knows which tools are off-limits
- This prevents the LLM from retrying the same denied tool in subsequent turns

### Frontend Inline Security Prompt

When a sensitive tool is intercepted, the frontend renders an **inline card directly in the chat area** (between messages and the composer), rather than hiding the approval behind a sidebar panel. The card displays:

- Tool name, risk category, and rationale
- Three action buttons:
  - **Decline** — denies the tool, sends `{"type": "security_approval", "approved": false}`
  - **Allow** — approves this one request, sends `{"type": "security_approval", "approved": true}`
  - **Auto-Allow** — approves AND sets `execution_policy` to `auto_approve` via `PUT /api/unified-settings`, so future sensitive tools are auto-approved until changed back

Key files:
- `frontend-v2/src/state/useAppStore.ts` — `InlineSecurityPrompt` type and Zustand state
- `frontend-v2/src/App.tsx` — `handleInterrupt`, `handleAutoApprove` logic
- `frontend-v2/src/components/AppShell.tsx` — renders the inline card
- `frontend-v2/src/index.css` — `.security-inline-*` styles
- `src/agent/nodes/security_proxy.py` — gate logic and denied-tool accumulation
- `src/agent/state.py` — `denied_tools` field

### tool_action
- Executes approved tool calls via LangGraph ToolNode
- Appends fetch retry nudges for failed static fetches
- Appends web search answer nudges for successful searches
- Returns to complex_llm for next reasoning step

### memory_write
- Records conversation via personal_assistant module
- Extracts topics and interests
- Saves enriched facts to Mem0/Qdrant
- Invalidates memory context cache

## Tool Binding

Defined in `src/agent/tool_sets.py`:
- `COMPLEX_TOOLS_WITH_WEB` (20 tools)
- `COMPLEX_TOOLS_NO_WEB` (18 tools, no web_search/fetch_webpage)
