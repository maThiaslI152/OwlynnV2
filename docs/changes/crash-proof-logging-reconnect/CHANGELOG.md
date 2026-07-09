# Crash-proof Tool Execution + Logging + Auto-reconnect

**Date:** 2026-07-09
**Scope:** Backend resilience, crash logging, frontend auto-reconnect
**Risk:** Medium — touches tool execution, WS event forwarding, frontend connection lifecycle

## Problem

When users triggered tool-heavy operations (e.g., "Run a quick system check"), the app would suddenly close without error. Root causes:

1. **Tool execution crashes kill the graph** — `ToolNode.ainvoke()` in `complex.py` had no try/except. A single tool throwing an unhandled exception terminated the entire graph run.
2. **One bad event kills all event delivery** — The `forward_events` inner loop in `handler.py` had no per-event error isolation. A single malformed event killed the entire forwarder coroutine.
3. **Tracebacks went to stderr, not logs** — `traceback.print_exc()` in `graph_session.py` wrote to stderr only, which is lost when launched via Electron.
4. **No crash logging infrastructure** — No `faulthandler`, no `sys.excepthook`, no asyncio exception handler. Actual Python crashes were completely silent.
5. **No frontend error event handler** — Backend sent `{"type": "error"}` events but the frontend silently ignored them.
6. **No WebSocket auto-reconnection** — On disconnect, the frontend went to "disconnected" state with no recovery path.

## Changes

### Phase 1: Crash-proof tool execution

| File | Change |
|------|--------|
| `src/agent/core/complex.py:1624` | Wrapped `tool_node.ainvoke()` in try/except. On failure, returns error ToolMessage so LLM can inform user gracefully. |
| `src/api/ws/handler.py:130-806` | Added per-event try/except in `forward_events` inner loop. Bad events are logged and skipped instead of killing the forwarder. |
| `src/api/controllers/graph_session.py:43,50` | Added `exc_info=True` to `logger.error` calls for full tracebacks. |
| `src/api/controllers/graph_session.py:108-116` | Replaced `traceback.print_exc()` with `logger.error(..., exc_info=True)`. |

### Phase 2: Crash logging infrastructure

| File | Change |
|------|--------|
| `src/api/server.py` | Added `faulthandler.enable()` with rotating crash log at `~/.owlynn/logs/crash.log` (5MB, 3 backups). |
| `src/api/server.py` | Added `sys.excepthook` override to capture unhandled main-thread exceptions. |
| `src/api/server.py` | Added `threading.excepthook` for background thread exceptions. |
| `src/api/server.py` | Added `loop.set_exception_handler()` for unhandled async task exceptions. |

### Phase 3: Frontend resilience

| File | Change |
|------|--------|
| `frontend-v2/src/App.tsx` | Added `event.type === 'error'` handler with `toast.error()`. |
| `frontend-v2/src/lib/wsClient.ts` | Added auto-reconnect with exponential backoff (1s→2s→4s→8s→16s, max 5 retries). |
| `frontend-v2/src/lib/wsClient.ts` | Added thread resumption — re-sends last user message on reconnect. |
| `frontend-v2/src/lib/wsClient.ts` | Added `onReconnecting`, `onReconnected`, `onReconnectFailed` callbacks. |
| `frontend-v2/src/App.tsx` | Added `reconnecting` connection state with visible toast banner. |
| `frontend-v2/src/types/protocol.ts` | Added `'reconnecting'` to `ConnectionState` union. |
| `frontend-v2/src/index.css` | Added `connection-dot-reconnecting` style with faster pulse animation. |

## Crash log location

```
~/.owlynn/logs/crash.log
```

Rotating: 5MB max size, 3 backups. Captures:
- Python segfaults and fatal errors (via `faulthandler`)
- Unhandled main-thread exceptions (via `sys.excepthook`)
- Background thread exceptions (via `threading.excepthook`)
- Unhandled async task exceptions (via `loop.set_exception_handler`)

## Reconnection flow

```
WS close detected
  → Set connection = 'reconnecting', show "Reconnecting... (1/5)" toast
  → Wait 1s, attempt reconnect
  → On fail: "Reconnecting... (2/5)", wait 2s, retry
  → On success:
      → Re-send join event for same thread_id
      → Re-send last user message to retry graph run
      → Show toast: "Reconnected — retrying your last message"
  → After 5 fails: Set connection = 'disconnected', show error toast
```

## Verification

- `ruff check src/` — All checks passed
- `ruff format --check src/` — 192 files already formatted
- `mypy src/` — Success: no issues found in 192 source files
- `npx tsc --noEmit` — No errors
- `npx vitest run` — 131 passed (19 test files)
- `pytest tests/test_graph.py tests/test_server_startup.py tests/test_complex_node_properties.py tests/test_websocket_event_contract.py` — 26 passed
