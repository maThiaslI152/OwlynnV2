---
status: active
category: debugging
audience: agent
last_updated: 2026-07-09
owner: ai-agent
---

# Debugging Guide — Index

> **Purpose:** Symptom-to-file mapping for agents and developers. Start with [Quick Health Check](#quick-health-check), then follow the table.

## Related Documents

- [`BUG-ANALYSIS.md`](../BUG-ANALYSIS.md) — Bug inventory from browser audit
- [`architecture/overview.md`](../architecture/overview.md) — System architecture
- [`AGENT_FLOW.md`](../AGENT_FLOW.md) — LangGraph node flow
- [`CHAT_PROTOCOL.md`](../CHAT_PROTOCOL.md) — WebSocket contract
- [`STATUS.md`](../STATUS.md) — Current risks and model config
- [`logging.md`](logging.md) — Full logging & trace system reference

## Crash Log

**Location:** `~/.owlynn/logs/crash.log` (rotating: 5MB max, 3 backups)

Captures:
- Python segfaults and fatal errors (via `faulthandler`)
- Unhandled main-thread exceptions (via `sys.excepthook`)
- Background thread exceptions (via `threading.excepthook`)
- Unhandled async task exceptions (via `loop.set_exception_handler`)

**Audit logs:** `~/.owlynn/logs/audit.jsonl` (structured JSON, all channels) and `~/.owlynn/logs/audit-errors.jsonl` (errors only).

## Symptom → File Mapping

| Symptom | Primary source | Tests / guide |
|---------|----------------|---------------|
| Backend won't start / port conflict | `src/api/server.py` | [backend-api.md](backend-api.md) |
| WebSocket refused / CORS | `src/api/ws/handler.py` | [backend-api.md](backend-api.md) |
| Wrong route (simple vs complex) | `src/agent/nodes/router.py` | `tests/test_router_web_intent.py`, [agent-graph.md](agent-graph.md) |
| Persona leak / wrong answer | `src/agent/nodes/simple.py`, `src/agent/nodes/complex.py` | [agent-graph.md](agent-graph.md) |
| Infinite agent loop | `src/agent/graph.py` | [agent-graph.md](agent-graph.md) |
| Web search: no final answer / DSML in chat / excerpt dump | `src/agent/nodes/complex.py`, `src/api/ws/handler.py` | [`changes/web-search-synthesis-fix/CHANGELOG.md`](../changes/web-search-synthesis-fix/CHANGELOG.md), `tests/test_tool_output_delta.py` |
| Cloud cost chip missing after chat switch | `frontend-v2/src/lib/cloudUsage.ts`, `src/api/server.py` | [`changes/cloud-usage-context-chip/CHANGELOG.md`](../changes/cloud-usage-context-chip/CHANGELOG.md) |
| Cloud chip popover overlaps inspector below | `frontend-v2/src/index.css` | [`changes/ui-inspector-markdown-fixes/CHANGELOG.md`](../changes/ui-inspector-markdown-fixes/CHANGELOG.md) |
| Markdown table clips in narrow chat | `frontend-v2/src/components/AppShell.tsx` | [`changes/ui-inspector-markdown-fixes/CHANGELOG.md`](../changes/ui-inspector-markdown-fixes/CHANGELOG.md) |
| HITL approval missing | `src/agent/nodes/security_proxy.py` | `tests/test_security_proxy.py`, [tools.md](tools.md) |
| LM Studio not reachable | `src/agent/llm.py`, `src/config/defaults.yaml` | [llm-pool.md](llm-pool.md) |
| Model name mismatch | `src/config/defaults.yaml` | [llm-pool.md](llm-pool.md) |
| DeepSeek 401/403/429 | `src/agent/nodes/complex_utils/cloud_invoke.py` | [llm-pool.md](llm-pool.md) |
| Context overflow | `src/agent/nodes/summarize.py` | [llm-pool.md](llm-pool.md) |
| Qdrant / Redis down | `src/memory/`, `docker-compose.yml` | [memory.md](memory.md) |
| Memory panel loading forever | `src/memory/project.py`, `frontend-v2/src/components/MemoryPanel.tsx` | [memory.md](memory.md) |
| Tool execution fails | `src/agent/tool_sets.py`, `src/tools/` | [tools.md](tools.md) |
| `read_workspace_file` ERROR card but answer follows | `src/api/ws/handler.py` `_tool_status_from_content` | [`changes/tool-preamble-read-file-fix/CHANGELOG.md`](../changes/tool-preamble-read-file-fix/CHANGELOG.md), `tests/test_ws_tool_ui_helpers.py` |
| “Reading workspace file…” streams before tool card | `src/api/ws/handler.py`, `frontend-v2/src/lib/toolPreamble.ts` | [`changes/tool-preamble-read-file-fix/CHANGELOG.md`](../changes/tool-preamble-read-file-fix/CHANGELOG.md) |
| Browser page not prefilled in composer | `browser-extension/`, `src/api/routes/browser_extension.py`, `frontend-v2/src/App.tsx` | [`changes/browser-extension-active-tab/CHANGELOG.md`](../changes/browser-extension-active-tab/CHANGELOG.md) |
| Frontend blank / WS desync | `frontend-v2/src/App.tsx`, `frontend-v2/src/lib/wsClient.ts` | [frontend.md](frontend.md) |
| App crashes during tool execution | `src/agent/core/complex.py`, `~/.owlynn/logs/crash.log` | [`changes/crash-proof-logging-reconnect/CHANGELOG.md`](../changes/crash-proof-logging-reconnect/CHANGELOG.md) |
| WebSocket keeps disconnecting | `frontend-v2/src/lib/wsClient.ts` (auto-reconnect), `src/api/ws/handler.py` | [`changes/crash-proof-logging-reconnect/CHANGELOG.md`](../changes/crash-proof-logging-reconnect/CHANGELOG.md) |
| Silent crash (no error in UI) | `~/.owlynn/logs/crash.log`, `src/api/server.py` (faulthandler) | [`changes/crash-proof-logging-reconnect/CHANGELOG.md`](../changes/crash-proof-logging-reconnect/CHANGELOG.md) |
| Electron / Safe Mode IPC | `frontend-v2/src/lib/electronBridge.ts` | [frontend.md](frontend.md) |
| Slow responses / thermal | `src/config/defaults.yaml` (M4 timeouts) | [profiling.md](profiling.md) |

## Quick Health Check

### 1. Containers

```bash
podman ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "qdrant|redis"
```

Expected: `owlynn_qdrant`, `owlynn_redis` up. Fix: `podman compose up -d` or `./start.sh`.

### 2. LM Studio

```bash
curl -s http://127.0.0.1:1234/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',[])))"
```

Expected: ≥1 model. Unified local model: `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`. See [llm-pool.md](llm-pool.md).

### 3. Backend

```bash
curl -s http://127.0.0.1:8000/api/unified-settings | head -c 80
```

### 4. Frontend tests

```bash
cd frontend-v2 && npx vitest run 2>&1 | tail -3
```

### 5. CI gate

```bash
./scripts/ci.sh --quick
```

## Decision tree

```
Symptom?
├─ Backend/API error → backend-api.md
├─ Wrong model/route → router.py + agent-graph.md + logcat.py --channel agent.model
├─ "What happened in conversation X?" → trace_view.py <thread_id>
├─ LLM timeout/OOM → llm-pool.md + defaults.yaml
├─ Memory/Qdrant → memory.md
├─ Tool/HITL → tools.md + HITL.md + trace_view.py <thread_id> --type tool_call
├─ Frontend/WS → frontend.md + CHAT_PROTOCOL.md
└─ Performance → profiling.md + trace_view.py <thread_id> --type tool_call
```

## Related

- [`../PROJECT_GUIDE.md`](../PROJECT_GUIDE.md) — file map
- [`../guides/dev-startup.md`](../guides/dev-startup.md) — launch steps

## Last updated

2026-06-10 — agent symptom table with src/file column
