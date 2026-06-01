---
status: active
category: debugging
last_updated: 2026-05-31
owner: human
---

# Debugging: Tools & ToolboxRegistry

> **Purpose:** Debugging guide for agent tool execution issues.


**Quick Reference:** 20 tools across 5 toolbox categories. Dynamically bound via `src/agent/tool_sets.py` (ToolboxRegistry) based on router classification. HITL gating via `src/agent/nodes/security_proxy.py`. Key files: `src/agent/tool_sets.py`, `src/agent/nodes/security_proxy.py`, `src/tools/*.py`.

## Tool Categories

| Category | Tools | Files |
|----------|-------|-------|
| `web_search` | `web_search`, `fetch_webpage` | `src/tools/web_tools.py`, `src/tools/web_search_enhanced.py`, `src/tools/web_retrieval.py` |
| `file_ops` | `read_workspace_file`, `write_workspace_file`, `edit_workspace_file`, `list_workspace_files`, `delete_workspace_file` | `src/tools/core_tools.py` |
| `data_viz` | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf`, `notebook_run`, `notebook_reset` | `src/tools/doc_generator.py`, `src/tools/notebook.py` |
| `productivity` | `todo_add`, `todo_list`, `todo_complete`, `list_skills`, `invoke_skill` | `src/tools/todo.py`, `src/tools/skills.py` |
| `memory` | `recall_memories` | `src/tools/core_tools.py` |

**Always included:** `ask_user` (HITL escape hatch, `src/tools/ask_user.py`)

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| Tool execution returns error | Tool-specific failure (missing file, API error, timeout) | Check `tool_execution` WS event for `error` field | See per-tool guidance below |
| Wrong toolbox selected for task | Router classified task incorrectly | Check `router_info` WS event `route` and `features.task_category` | Fix router classification (see [agent-graph.md](agent-graph.md)) |
| HITL approval prompt not showing | Frontend interrupt handler not wired | Check `interrupt` WS event emission in `forward_events()` | Verify frontend `handleInterrupt` in `App.tsx` |
| HITL approval denied but tool still runs | `denied_tools` not being checked | Check `security_proxy_node()` output for `denied_tools` | Verify denial propagation to `complex_llm` system prompt |
| `ask_user` tool not working | Escape hatch not bound to LLM | `ask_user` is always included in tool sets | If missing, check `tool_sets.py` `resolve_tools()` |
| Notebook execution hangs | Python subprocess stuck or infinite loop | Check backend process tree for zombie notebook processes | Kill stale notebook processes, add timeout |
| Document generation fails | Missing Python library (python-docx, openpyxl, etc.) | `pip list \| grep python-docx` | `pip install` missing dependency |
| Web search returns no results | All tiers exhausted, SearXNG down, or network issue | Check SearXNG health: `curl http://localhost:8888/search` | Ensure SearXNG running, check internet, try alternate tier |
| Workspace file operations fail | Wrong workspace path or permission denied | Check active workspace: `GET /api/projects` | Verify workspace path exists and is writable |
| Tool execution panel shows mock data (BUG-6) | Frontend renders demo entries | See [frontend.md](frontend.md) BUG-6 section | See [frontend.md](frontend.md) |

## Diagnostic Commands

### Tool Execution Audit

```bash
# Check tool execution history via WebSocket events
# (visible in browser DevTools → Network → WS tab, filter for "tool_execution")

# Check audit logs on disk (if exported)
find . -name "audit*.jsonl" 2>/dev/null | head -5

# Run the tool automation script to test tool execution
./scripts/run_workspace_tool_automation.sh
```

### Notebook Debugging

```bash
# Check for zombie notebook processes
ps aux | grep notebook | grep -v grep

# Kill all notebook processes
pkill -f "notebook"

# Reset notebook state
# (may involve deleting a temp file or state file in workspace)
```

### Web Search Tier Debugging

```bash
# Check each search tier
# Tier 0: Weather
curl -s "wttr.in/Bangkok?format=3"

# Tier 0.5: SearXNG
curl -s "http://localhost:8888/search?q=test&format=json" | head -c 100

# Tier 1A: Check API keys
echo "BRAVE_API_KEY: ${BRAVE_API_KEY:0:8}..."
echo "SERPER_API_KEY: ${SERPER_API_KEY:0:8}..."
echo "TAVILY_API_KEY: ${TAVILY_API_KEY:0:8}..."

# Tier 1B: DDG (test with curl_cffi if available)
python3 -c "
try:
    from curl_cffi import requests
    r = requests.get('https://duckduckgo.com/html/?q=test')
    print(f'DDG search: HTTP {r.status_code}')
except Exception as e:
    print(f'DDG search failed: {e}')
"
```

### Workspace Operations

```bash
# Check active workspace
curl -s http://127.0.0.1:8000/api/projects | python3 -c "
import sys,json
projects = json.load(sys.stdin)
active = [p for p in projects if p.get('id') == 'default']
print('Active workspace:', active[0].get('name') if active else 'NOT FOUND')
"

# List workspace files
curl -s http://127.0.0.1:8000/api/workspace/files | head -c 200

# Check workspace directory exists
ls -la <workspace-path>/
```

## Log Interpretation

### Tool Execution Events (WebSocket)

```json
// Tool started
{"type":"tool_execution","status":"running","tool_name":"web_search","tool_call_id":"call_abc","input":"{\"query\":\"test\"}"}

// Tool succeeded
{"type":"tool_execution","status":"success","tool_name":"web_search","tool_call_id":"call_abc","output":"[search results]","duration":2.34}

// Tool failed
{"type":"tool_execution","status":"error","tool_name":"fetch_webpage","tool_call_id":"call_def","error":"HTTP 403: Access denied","duration":1.20}
```

### Security Proxy Logs

```
# Safe tool auto-approved
INFO:src.agent.nodes.security_proxy:Tool 'web_search' auto-approved (safe category)

# Sensitive tool requires HITL
INFO:src.agent.nodes.security_proxy:Sensitive tool 'write_workspace_file' requires approval
INFO:src.agent.nodes.security_proxy:Tool risk: FILE_WRITE, rationale: Writing to /Users/tim/...

# Tool denied
INFO:src.agent.nodes.security_proxy:User denied tool 'write_workspace_file'
INFO:src.agent.nodes.security_proxy:Appending to denied_tools: ['write_workspace_file']
```

### Tool-Specific Errors

```
# File not found
ERROR:src.tools.core_tools:read_workspace_file: File not found: path/to/file.txt

# Permission denied
ERROR:src.tools.core_tools:write_workspace_file: Permission denied: path/to/file.txt

# Notebook execution error
ERROR:src.tools.notebook:notebook_run: NameError: name 'x' is not defined

# Document generation missing lib
ERROR:src.tools.doc_generator:create_docx: ModuleNotFoundError: No module named 'docx'

# Web search exhausted all tiers
WARNING:src.tools.web_search_enhanced:All search tiers exhausted, returning empty results

# MCP client error
ERROR:src.tools.mcp_client:MCP tool execution failed: Connection refused
```

## Step-by-Step Procedures

### Procedure 1: Tool Execution Returns Error

1. Identify the failing tool from the `tool_execution` WS event:
   - `tool_name` and `error` fields tell you what failed and why.

2. Check the tool source file in `src/tools/` for the specific error handler.

3. For file operations:
   - Verify workspace path exists and is accessible
   - Check file permissions: `ls -la <path>`
   - Check if file is locked by another process: `lsof <path>`

4. For web search:
   - Verify SearXNG is running: `curl http://localhost:8888/search`
   - Check internet connectivity: `curl -s https://google.com | head -c 10`
   - Check API keys if using Tier 1A

5. For document generation:
   - Verify Python library is installed: `pip list | grep <library>`
   - Install missing libs: `pip install python-docx openpyxl python-pptx reportlab`

6. For notebook:
   - Kill stale notebook processes: `pkill -f notebook`
   - The notebook may need a reset: check `notebook_reset` tool

### Procedure 2: HITL / Security Proxy Debugging

1. Verify the interrupt event is emitted:
   - Check DevTools → Network → WS tab for `"type":"interrupt"` events
   - Should contain tool details: `tool_name`, `tool_call_id`, `risk`, `rationale`

2. Verify frontend receives interrupt:
   - `App.tsx` `handleInterrupt()` should dispatch to store
   - `HitlPromptCard` should render inline in the message timeline
   - Interrupts now appear as conversation-inline cards (not sidebar-only)

3. If interrupt not showing:
   - Check if `SENSITIVE_TOOLS` in `src/agent/hitl/policy.py` includes the tool
   - Safe tools (web_search, fetch_webpage, read_workspace_file, etc.) are auto-approved
   - Only file write/edit/delete and notebook_run trigger HITL
   - Plan review (`plan_review` node) runs before security_proxy for sensitive plans

4. If approval not being sent back:
   - Check DevTools WS tab for the approval message:
     - `{"type":"security_approval","approved":true}`
     - `{"type":"plan_review_response","approved":true}` (for plan review)
     - `{"type":"ask_user_response","answer":{...}}` (for scope clarification)
   - Verify the button click handler sends this payload

### Dev Preview (NEW)

Use the dev API to test HITL UI without interacting with a real agent:

```bash
# Backend must have OWLYNN_DEV=1
./scripts/preview_hitl.sh router            # Router skill ambiguity
./scripts/preview_hitl.sh security           # Security delete_file
./scripts/preview_hitl.sh plan_review        # Plan review approval
./scripts/preview_hitl.sh scope_clarify      # Scope clarification
./scripts/preview_hitl.sh ask_user           # Mid-task ask_user
```

Or via the dev-only dropdown in the Safe Mode panel (visible when `import.meta.env.DEV`).

### Procedure 2b: Scope Clarification Debugging

The `scope_clarify` node runs between `router` and `complex_llm` for vague build/create requests. If it's not triggering:

1. **Check heuristic**: `src/agent/hitl/scope_heuristics.py::needs_clarification()`
   - Uses regex `\b(build|create|make|implement|develop|write)\s+(a|an|the|some|me\s+a)\b`
   - Requires 2+ missing dimensions from `language`, `ui_surface` signal sets
   - Explicit signals include common languages (Python, JS, Rust etc.), UI types (web, desktop, CLI etc.), and frameworks
   - Fix signals ("fix", "bug", "error", "issue", "line") skip the check

2. **Check router delegation**: Router delegates build requests to scope_clarify
   - In `router.py`: before firing router HITL, checks `needs_clarification(user_text)` — if true, skips router HITL and lets scope_clarify handle it
   - If the router fires its own HITL first, `router_clarification_used` is set to true, causing scope_clarify to skip (avoid back-to-back HITL)

3. **Check Small LLM**: The heuristic is authoritative — the Small LLM only generates questions, it cannot override the need for clarification
   - If Small LLM is unavailable or returns empty, fallback questions are generated from the missing dimensions
   - Prompt: `scope_clarify.py::_CLASSIFIER_PROMPT`
   - Fallback: `scope_clarify.py::_build_fallback_questions()`

4. **Check profile**: `scope_clarification_enabled` must be true (default)

5. **Check clarified_scope injection**: After user answers, `clarified_scope` is injected into `complex_llm`'s system prompt as `CONFIRMED REQUIREMENTS (user-approved, do not contradict)`

### Procedure 3: Wrong Toolbox Selected

1. Check `router_info` WS event for the route and task category:
   - `complex-default` for general tasks
   - `complex-vision` for image tasks
   - `complex-longctx` for long context
   - `complex-cloud` for cloud escalation

2. The router selects toolbox categories based on task type:
   - If the agent needs web search but doesn't have it: router should have classified as needing `web_search` toolbox
   - If the agent needs file ops but doesn't have them: router should have classified as needing `file_ops` toolbox

3. Toolbox selection logic is in `src/agent/nodes/router.py`:
   - Check the `toolbox` field in router_metadata
   - `resolve_tools()` in `src/agent/tool_sets.py` maps toolbox names to tool lists

4. To force a specific toolbox for testing:
   - Pass `"all"` for toolbox to include all tools
   - Or manually call `resolve_tools(["web_search", "file_ops"])`

## Known Fixes

- **Tool awareness assertions**: Fixed in Phase 5 — updated to match current `COMPLEX_TOOL_GUIDANCE_WEB` content. See [STATUS.md](../STATUS.md).
- **Audit & verify sub-panel not expanding (BUG-8)**: Known issue in `ToolExecutionPanel.tsx`. See [BUG-ANALYSIS.md](../BUG-ANALYSIS.md).
- **Mock data in tool execution panel (BUG-6)**: Known issue — mock entries persist regardless of actual tool activity. See [frontend.md](frontend.md).
- See also: [AGENT_FLOW.md](../AGENT_FLOW.md) sections on Tool Binding and Security Proxy.

## Related

- [`docs/debugging/README.md`](README.md) — debugging index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
