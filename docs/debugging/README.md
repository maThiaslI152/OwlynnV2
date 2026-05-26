---
last_verified: 2026-05-26
auto_generated: false
purpose: "Debugging guide index with symptom-to-document mapping, quick health check, and decision tree for troubleshooting."
---
# Debugging Guide — Index

Entry point for AI agents and developers troubleshooting OwlynnV2. This index maps symptoms to the appropriate subsystem debug doc. Start with the [Quick Health Check](#quick-health-check) below, then follow the decision tree.

## Related Documents

- [BUG-ANALYSIS.md](../BUG-ANALYSIS.md) — Full analysis of 8 bugs found in 2026-05-25 browser audit
- [browser-verification.md](browser-verification.md) — Live browser test results confirming 6 fixes, 1 partial, 1 untested
- [memory-analysis.md](memory-analysis.md) — Full memory budget breakdown, crash root cause, and Podman/MLX optimization
- [ARCHITECTURE_OVERVIEW.md](../ARCHITECTURE_OVERVIEW.md) — System architecture, component relationships
- [AGENT_FLOW.md](../AGENT_FLOW.md) — LangGraph node flow and tool binding
- [CHAT_PROTOCOL.md](../CHAT_PROTOCOL.md) — WebSocket contract and event types
- [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md) — Resource budget and latency targets
- [FRONTEND_CUTOVER_ROLLBACK.md](../FRONTEND_CUTOVER_ROLLBACK.md) — Rollback procedure for broken frontend state
- [STATUS.md](../STATUS.md) — Current project status and active bugs
- [ADR.md](../ADR.md) — Architecture decision records

## Symptom → Doc Mapping

| Symptom | Guide |
|---------|-------|
| Backend won't start / port conflict / 500 errors | [backend-api.md](backend-api.md) |
| WebSocket connection refused / handshake failure / CORS error | [backend-api.md](backend-api.md) |
| Agent produces wrong output / persona leak / hallucination | [agent-graph.md](agent-graph.md) |
| Router misclassifies simple vs complex / wrong route | [agent-graph.md](agent-graph.md) |
| Infinite agent loop / message never completes | [agent-graph.md](agent-graph.md) |
| Security proxy blocks legitimate actions | [agent-graph.md](agent-graph.md) |
| LM Studio can't connect / model not found | [llm-pool.md](llm-pool.md) |
| Model swap hangs / OOM / timeout | [llm-pool.md](llm-pool.md) |
| LM Studio segfault / MLX memory crash | [memory-analysis.md](memory-analysis.md) |
| DeepSeek API returns 401/403/429 | [llm-pool.md](llm-pool.md) |
| Token budget exceeded / context window overflow | [llm-pool.md](llm-pool.md) |
| Qdrant won't connect / Redis down / containers not running | [memory.md](memory.md) |
| Memory panel "Loading..." indefinitely (BUG-3) | [memory.md](memory.md) |
| Embeddings fail / dimension mismatch | [memory.md](memory.md) |
| Tool execution fails / wrong toolbox selected | [tools.md](tools.md) |
| HITL approval not showing / security prompt missing | [tools.md](tools.md) |
| Document generation (DOCX/XLSX/PPTX/PDF) errors | [tools.md](tools.md) |
| Frontend blank / build fails / state desync | [frontend.md](frontend.md) |
| WebSocket reconnection loops / message not appearing | [frontend.md](frontend.md) |
| Orchestration panel empty after message (BUG-2) | [frontend.md](frontend.md) |
| Tauri app won't launch / CSP errors / TCC denied | [tauri-desktop.md](tauri-desktop.md) |
| Screen capture fails / TTS not working | [tauri-desktop.md](tauri-desktop.md) |
| High memory usage / slow responses / thermal throttle | [profiling.md](profiling.md) |
| Performance regression / SLO violation | [profiling.md](profiling.md) |

## Quick Health Check

Run these commands in order to verify the full stack is operational. Each command should produce output similar to the "Expected" column. If any fails, follow the linked guide.

### 1. Containers

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -E "qdrant|redis|searxng"
```

Expected: All three containers showing `Up` with ports 6333 (Qdrant), 6379 (Redis), 8888 (SearXNG).

If missing: `docker-compose up -d` (see [memory.md](memory.md) for container-level debugging).

### 2. LM Studio

```bash
curl -s http://127.0.0.1:1234/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Models: {len(d.get(\"data\",[]))}')" 2>/dev/null || echo "LM Studio not reachable"
```

Expected: At least 1 model loaded (typically `ibm-grok4-ultrafast-coder-1b` for small LLM, plus optionally `gemma-4-e4b-uncensored-hauhaucs-aggressive` for medium).

If missing: Launch LM Studio manually (see [llm-pool.md](llm-pool.md)).

### 3. Backend

```bash
curl -s http://127.0.0.1:8000/api/unified-settings 2>/dev/null | head -c 100 || echo "Backend not running"
```

Expected: JSON response with settings data.

### 4. Frontend Build

```bash
cd frontend-v2 && npx vitest run 2>&1 | tail -5
```

Expected: All tests passing (currently 50+).

### 5. Full CI Gate

```bash
./scripts/ci.sh --quick
```

Expected: All four checks pass (Python tests, audit tests, frontend tests, frontend build). This runs the same checks as the pre-push hook.

## Log File Locations

| Component | Log Source |
|-----------|-----------|
| Backend (Uvicorn/FastAPI) | stdout of `uvicorn src.api.server:app` process |
| LangGraph Stream | WebSocket event stream forwarded to frontend (visible in browser DevTools → Network → WS tab) |
| LM Studio | LM Studio app logs (visible in LM Studio UI) |
| Model Swap | `src/agent/swap_manager.py` emits structured log entries at `INFO` level |
| Tool Execution | Backend `tool_execution` WebSocket events + audit log JSONL |
| Frontend | Browser DevTools Console |
| Tauri Desktop | macOS Console.app → search for process name, or `tari dev` output |
| Containers | `docker logs <container-name>` (qdrant, redis, searxng) |

## Rollback to Known-Good State

If the application is broken and you need to revert to a previously working state, follow the procedure in [`../FRONTEND_CUTOVER_ROLLBACK.md`](../FRONTEND_CUTOVER_ROLLBACK.md).

For full application rollback (not just frontend):

```bash
# Check recent git history for a known-good commit
git log --oneline -20

# Roll back to that commit (replace <hash>)
git checkout <hash>

# Rebuild and restart
./start.sh
```

## Decision Tree

```
ISSUE REPORTED
│
├─ Backend won't start?
│  └─→ backend-api.md
│
├─ WebSocket connection fails?
│  └─→ backend-api.md
│
├─ Agent produces wrong/missing response?
│  ├─ Persona leak in output? → agent-graph.md (simple/complex node)
│  ├─ Wrong route chosen? → agent-graph.md (router classification)
│  └─ Infinite loop / no response? → agent-graph.md (graph execution)
│
├─ LLM/model errors?
│  ├─ LM Studio unreachable? → llm-pool.md
│  ├─ Swap fails / OOM? → llm-pool.md
│  └─ Cloud API errors? → llm-pool.md
│
├─ Memory/context issues?
│  ├─ Containers not running? → memory.md
│  ├─ Embeddings fail? → memory.md
│  └─ Memory panel stuck? → memory.md
│
├─ Tool execution failures?
│  └─→ tools.md
│
├─ Frontend issues?
│  ├─ Blank screen / build fails? → frontend.md
│  ├─ Orchestration panel empty? → frontend.md
│  ├─ State desync / reconnection loop? → frontend.md
│  └─ Tauri-specific features broken? → tauri-desktop.md
│
├─ Performance problems?
│  ├─ High memory / slow responses? → profiling.md
│  └─ Thermal throttling? → profiling.md
│
└─ Unknown / multiple systems?
   └─ Run Quick Health Check above, then follow each failing component's guide
```
