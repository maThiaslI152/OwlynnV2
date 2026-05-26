---
purpose: "Debugging guide for the FastAPI backend: failure modes, WebSocket issues, CRUD and settings operations."
---

# Debugging: Backend API

**Quick Reference:** FastAPI server on `127.0.0.1:8000`, Uvicorn with WebSocket support. Key files: `src/api/server.py` (~1830 lines), `src/config/settings.py`, `src/config/logging_config.py`.

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| `Address already in use` on port 8000 | Another uvicorn process is running | `lsof -i :8000` | Kill stale process: `kill $(lsof -ti :8000)` |
| Server starts but 404 on all endpoints | Wrong working directory (Python path) | `curl -s http://127.0.0.1:8000/docs` | Run from workspace root: `uvicorn src.api.server:app` |
| `ModuleNotFoundError: No module named 'src'` | Virtual environment not active or not in workspace root | `which python3`, `pwd` | Activate venv and `cd` to `/Users/tim/Works/OwlynnV2` |
| `ImportError` for langgraph/httpx/etc | Missing dependency | `pip list \| grep langgraph` | `pip install -r requirements.txt` |
| WebSocket handshake rejected (403) | CORS origin mismatch or frontend on wrong port | Check browser console for CORS errors | Ensure frontend connects to `ws://127.0.0.1:8000/ws/chat/<thread_id>` |
| `ERR_CONNECTION_REFUSED` in browser | Backend not running | `curl http://127.0.0.1:8000/api/unified-settings` | Start backend: `uvicorn src.api.server:app --host 127.0.0.1 --port 8000` |
| REST endpoint returns 500 | Unhandled exception in handler | Check uvicorn stdout for traceback | Depends on traceback — check [agent-graph.md](agent-graph.md) or [llm-pool.md](llm-pool.md) |
| WebSocket disconnects mid-stream | Graph execution crashed or client timeout | Check uvicorn stdout for traceback | Depends on traceback |
| `GET /api/unified-settings` returns 404 | Endpoint regression (known past issue) | `curl -v http://127.0.0.1:8000/api/unified-settings` | Regenerate or verify route is registered in server.py |

## Diagnostic Commands

### Port and Process

```bash
# Check what's on port 8000
lsof -i :8000

# Kill stale uvicorn processes
pkill -f "uvicorn src.api.server"

# Check if anything else is using port 8000
lsof -i :8000 | grep -v uvicorn
```

### Health Checks

```bash
# REST API health
curl -s http://127.0.0.1:8000/api/unified-settings | python3 -m json.tool | head -20

# OpenAPI docs (should be accessible)
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs

# Check all registered routes
curl -s http://127.0.0.1:8000/openapi.json | python3 -c "
import sys,json
paths = json.load(sys.stdin).get('paths',{})
for p in sorted(paths):
    methods = ','.join(paths[p].keys())
    print(f'{methods:20s} {p}')
"
```

### WebSocket Test

```bash
# Simple connect/disconnect test (requires websocat or python websockets)
python3 -c "
import asyncio, websockets
async def test():
    uri = 'ws://127.0.0.1:8000/ws/chat/test-thread-123'
    async with websockets.connect(uri) as ws:
        print('Connected:', ws.response_headers.get('sec-websocket-accept'))
        # Send a stop message to cleanly disconnect
        await ws.send('{\"type\":\"stop\"}')
asyncio.run(test())
"
```

## Log Interpretation

### Backend stdout (Uvicorn)

Normal startup sequence:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### WebSocket connection lifecycle

```
# Client connects
INFO:     ('127.0.0.1', 54321) - "WebSocket /ws/chat/<thread_id>" [accepted]

# Graph execution starts (stdout, application-level logging)
INFO:__main__:Starting graph run for thread <thread_id>

# Client disconnects normally
INFO:     connection closed

# Client disconnects abnormally (graph still running)
INFO:     connection closed
WARNING:__main__:WebSocket disconnected during active run for thread <thread_id>
```

### Error Patterns and Their Meaning

```
# Port conflict — another uvicorn is already running
ERROR:    [Errno 48] Address already in use

# Missing Python dependency
ModuleNotFoundError: No module named 'langgraph'
→ Fix: pip install -r requirements.txt

# LM Studio not reachable (propagated from llm_pool)
ERROR:src.agent.llm:Cannot connect to LM Studio at http://127.0.0.1:1234
→ Fix: Launch LM Studio, see [llm-pool.md](llm-pool.md)

# Redis not available (checkpointer falls back to memory)
WARNING:langgraph.checkpoint.redis:Cannot connect to Redis at redis://localhost:6379
INFO:langgraph.checkpoint.memory:Falling back to MemorySaver
→ Fix: docker-compose up -d redis, see [memory.md](memory.md)

# CORS rejection — frontend origin not allowed
 WARNING:  Forbidden origin: http://localhost:5173
→ Fix: Check CORS middleware config in server.py
```

## Step-by-Step Procedures

### Procedure 1: Backend Won't Start

1. Check for port conflict:
   ```bash
   lsof -i :8000
   ```
   Expected: Empty (nothing on port 8000). If uvicorn appears, kill it:
   ```bash
   kill $(lsof -ti :8000)
   ```

2. Verify Python environment:
   ```bash
   cd /Users/tim/Works/OwlynnV2
   which python3  # Should point to venv python
   python3 -c "import langgraph; print('langgraph OK')"
   python3 -c "import fastapi; print('fastapi OK')"
   ```

3. If imports fail, reinstall:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the server:
   ```bash
   uvicorn src.api.server:app --host 127.0.0.1 --port 8000
   ```
   Expected: `Uvicorn running on http://127.0.0.1:8000`

5. Verify with health check:
   ```bash
   curl -s http://127.0.0.1:8000/api/unified-settings | head -c 50
   ```
   Expected: JSON response starting with `{"name":`.

### Procedure 2: WebSocket Connection Fails

1. Verify backend is running:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs
   ```
   Expected: `200`

2. Check WebSocket endpoint directly:
   ```bash
   python3 -c "
   import asyncio, websockets
   async def test():
       try:
           async with websockets.connect('ws://127.0.0.1:8000/ws/chat/test-conn') as ws:
               print('OK: WebSocket connected')
       except Exception as e:
           print(f'FAIL: {e}')
   asyncio.run(test())
   "
   ```
   Expected: `OK: WebSocket connected`

3. If fails with `Connection refused`:
   - Backend not running or wrong port. Re-run Procedure 1.

4. If fails with `403 Forbidden`:
   - CORS mismatch. Check that the frontend is connecting from an allowed origin.
   - In browser-only dev mode (`localhost:5173`), ensure CORS middleware allows this origin.
   - Check `src/api/server.py` for CORS configuration.

5. If connects but immediately disconnects:
   - Check backend stdout for error traceback.
   - The graph may be failing during startup. See [agent-graph.md](agent-graph.md).

### Procedure 3: REST Endpoint Returns 500

1. Check the full traceback in uvicorn stdout:
   ```bash
   # While backend is running, trigger the failing endpoint
   curl -v http://127.0.0.1:8000/api/<failing-endpoint>
   ```
   Expected: uvicorn stdout shows the Python traceback.

2. Common traceback patterns:
   - `ModelSwapError` → see [llm-pool.md](llm-pool.md)
   - `KeyError` in state → see [agent-graph.md](agent-graph.md) (missing state field)
   - `ConnectionRefusedError` to Redis/Qdrant → see [memory.md](memory.md)
   - `httpx.ConnectError` → LM Studio or external service unreachable

3. For silent 500s (no traceback):
   - Check if a try/except in the handler silently catches the error.
   - Search `src/api/server.py` for `except` blocks near the failing route.
   - Add temporary `logger.exception()` to the except block for diagnosis.

## Known Fixes

- **Profile update silently ignoring invalid keys**: Resolved — `POST /api/profile` now reports partial field failures. See [STATUS.md](../STATUS.md).
- **`GET /api/unified-settings` regressed to 404**: Resolved — route was restored. If it recurs, check for route registration conflicts in `server.py`.
- **`OPENAI_API_KEY` global side-effect**: Resolved — removed from global scope. See [STATUS.md](../STATUS.md).
- **Chat title generation failing silently**: Known bug (BUG-4) — `generate_chat_title_router_llm` wrapped in try/except. See [BUG-ANALYSIS.md](../BUG-ANALYSIS.md).
