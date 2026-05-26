# Debugging: Memory System

**Quick Reference:** Dual memory architecture: short-term (JSON file-based, 200-entry cap, managed by `src/memory/memory_manager.py`) + long-term (Mem0 + Qdrant vector search, managed by `src/memory/long_term.py`). Redis for LangGraph checkpointing. Key files: `src/memory/memory_manager.py`, `src/memory/long_term.py`, `src/memory/personal_assistant.py`, `src/memory/user_profile.py`, `src/memory/persona.py`, `src/agent/nodes/memory.py` (inject/write nodes).

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| Memory panel "Loading..." indefinitely (BUG-3) | REST fetch hangs or errors silently | Browser Network tab → check `GET /api/topics` and `GET /api/interests` | Fix backend endpoints or add frontend timeout/error state |
| `GET /api/topics` returns 500 or empty | JSON file corrupted or missing | Check topic storage files | Repair or recreate JSON file |
| `GET /api/mem0/search` returns 500 | Qdrant not running or Mem0 config wrong | `curl http://localhost:6333/collections` | `docker-compose up -d qdrant`, check Mem0 config |
| Qdrant connection refused | Qdrant container not running | `docker ps \| grep qdrant` | `docker-compose up -d qdrant` |
| Embedding dimension mismatch (e.g., expected 768, got 384) | Wrong embedding model loaded | Check nomic model in LM Studio | Load `text-embedding-nomic-embed-text-v1.5-embedding` (768-dim) in LM Studio |
| Mem0 search returns no results | Collection empty or embedding model mismatch | Check Qdrant collection stats | Add memory entries, verify embedding dimensions |
| Redis unavailable (checkpoint fallback) | Redis container not running | `docker ps \| grep redis` | `docker-compose up -d redis` |
| Profile/persona not loading | JSON file missing or parse error | Check `src/memory/user_profile.py` file paths | Create default profile if missing |
| Short-term memory JSON corruption | Concurrent writes or process crash during write | Check JSON validity: `python3 -m json.tool <file>` | Repair JSON or delete and recreate |
| Memory context cache stale | TTL expired or manual invalidation not triggered | Check `memory_write_node` for invalidation flag | Force cache refresh by sending `memory_updated` event |

## Diagnostic Commands

### Container Health

```bash
# Check all containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# If running Podman instead of Docker
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Qdrant health
curl -s http://localhost:6333/collections | python3 -c "
import sys,json
cols = json.load(sys.stdin).get('result',{}).get('collections',[])
print(f'Collections: {len(cols)}')
for c in cols:
    print(f'  - {c.get(\"name\",\"?\")}')
"

# Redis health
redis-cli -u redis://localhost:6379 PING 2>/dev/null || echo "Redis not reachable"
redis-cli -u redis://localhost:6379 INFO memory | grep used_memory_human

# SearXNG health
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/search
```

### Container Logs

```bash
# Qdrant logs
docker logs qdrant --tail 20

# Redis logs
docker logs redis --tail 20

# SearXNG logs
docker logs searxng --tail 20
```

### Mem0 / Embeddings

```bash
# Check if embedding model is loaded in LM Studio
curl -s http://127.0.0.1:1234/v1/models | python3 -c "
import sys,json
data = json.load(sys.stdin).get('data',[])
emb_models = [m for m in data if 'embed' in m.get('id','').lower() or 'nomic' in m.get('id','').lower()]
print(f'Embedding models: {len(emb_models)}')
for m in emb_models:
    print(f'  - {m[\"id\"]}')
"

# Test embedding generation
curl -s http://127.0.0.1:1234/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-nomic-embed-text-v1.5-embedding","input":"test"}' | \
  python3 -c "
import sys,json
data = json.load(sys.stdin)
emb = data.get('data',[{}])[0].get('embedding',[])
print(f'Embedding dims: {len(emb)}')
" 2>/dev/null || echo "Embedding API not responding"
```

### REST Endpoints

```bash
# Check topics
curl -s http://127.0.0.1:8000/api/topics | python3 -c "
import sys,json
data = json.load(sys.stdin)
print(f'Topics: {len(data) if isinstance(data,list) else \"ERROR\"}')"

# Check interests
curl -s http://127.0.0.1:8000/api/interests | head -c 100

# Check memory context
curl -s "http://127.0.0.1:8000/api/memory-context?thread_id=test" | head -c 100

# Check Mem0 search
curl -s "http://127.0.0.1:8000/api/mem0/search?query=test&limit=5" | head -c 100

# Check profile
curl -s http://127.0.0.1:8000/api/profile | head -c 100
```

## Log Interpretation

### Memory Inject Node

```
INFO:src.agent.nodes.memory:Building memory context for thread <id>
INFO:src.agent.nodes.memory:Mem0 search returned 5 results for user query
INFO:src.agent.nodes.memory:Profile loaded: name=User, topics=3, interests=2
INFO:src.agent.nodes.memory:Memory context built (cached, TTL: 300s)
```

### Memory Write Node

```
INFO:src.agent.nodes.memory:Extracting topics from conversation...
INFO:src.agent.nodes.memory:Topics extracted: ['python', 'debugging']
INFO:src.agent.nodes.memory:Saving to Mem0/Qdrant...
INFO:src.agent.nodes.memory:Memory write complete, invalidating cache for thread <id>
```

### Mem0/Qdrant Connection

```
# Successful connection
INFO:mem0.memory.main:Connected to Qdrant at http://localhost:6333

# Connection failure
ERROR:mem0.memory.main:Failed to connect to Qdrant: Connection refused
→ Fix: docker-compose up -d qdrant

# Embedding failure
ERROR:src.memory.long_term:Embedding generation failed: HTTP 404
→ Fix: Load text-embedding-nomic-embed-text-v1.5-embedding in LM Studio
```

### JSON File Corruption

```
# Read error
ERROR:src.memory.memory_manager:Failed to read topics file: JSONDecodeError at line 42
→ Fix: Validate JSON, repair or recreate

# Write error
ERROR:src.memory.memory_manager:Failed to write topics file: Permission denied
→ Fix: Check file permissions
```

### Redis Checkpoint

```
# Successful connection
INFO:langgraph.checkpoint.redis:Connected to Redis at redis://localhost:6379

# Fallback to memory
WARNING:langgraph.checkpoint.redis:Cannot connect to Redis, falling back to MemorySaver
INFO:langgraph.checkpoint.memory:Using in-memory checkpointer (data lost on restart)
```

## Bug-Specific Debugging

### BUG-3: Memory Panel "Loading..." Indefinitely

**Location:** `frontend-v2/src/components/MemoryPanel.tsx`

**Debug steps:**

1. Check browser Network tab for requests to:
   - `GET /api/topics` — should return JSON array
   - `GET /api/interests` — should return JSON
   - `GET /api/mem0/search` — may be called on demand

2. If any request returns non-200:
   - Check the backend stdout for the endpoint handler's traceback.
   - Common causes: Qdrant down, JSON file missing, Mem0 config error.

3. If requests hang (pending indefinitely):
   - The fetch call in MemoryPanel may have no timeout.
   - Qdrant or Mem0 may be slow to respond.
   - Add a timeout to the fetch (e.g., 10s) and show error state on timeout.

4. If requests return 200 but panel still shows "Loading...":
   - Check the component's state update logic. The response may not be triggering the render update.
   - Check if the response format matches what the component expects.

## Step-by-Step Procedures

### Procedure 1: Containers Not Running

1. Check container status:
   ```bash
   docker ps -a --format "table {{.Names}}\t{{.Status}}"
   # or
   podman ps -a --format "table {{.Names}}\t{{.Status}}"
   ```

2. Start containers:
   ```bash
   docker-compose up -d
   # or
   podman-compose up -d
   ```

3. Verify each service:
   ```bash
   # Qdrant
   curl -s http://localhost:6333/collections | head -c 50
   # Expected: {"result":{"collections":[...

   # Redis
   redis-cli -u redis://localhost:6379 PING
   # Expected: PONG

   # SearXNG
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/search
   # Expected: 200 or 302
   ```

4. If containers fail to start:
   - Check logs: `docker logs qdrant`, `docker logs redis`, `docker logs searxng`
   - Port conflicts: check `lsof -i :6333`, `lsof -i :6379`, `lsof -i :8888`
   - Memory: Qdrant needs ~512 MB, Redis ~128 MB, SearXNG ~256 MB

### Procedure 2: Embedding Failures

1. Verify embedding model is loaded in LM Studio:
   ```bash
   curl -s http://127.0.0.1:1234/v1/models | python3 -c "
   import sys,json
   models = [m['id'] for m in json.load(sys.stdin).get('data',[])]
   emb = [m for m in models if 'embed' in m.lower() or 'nomic' in m.lower()]
   print('Embedding models:', emb if emb else 'NONE FOUND')
   "
   ```

2. If not loaded: download and load `text-embedding-nomic-embed-text-v1.5-embedding` in LM Studio.

3. Test embedding generation:
   ```bash
   curl -s -w "\nHTTP %{http_code}" http://127.0.0.1:1234/v1/embeddings \
     -H "Content-Type: application/json" \
     -d '{"model":"text-embedding-nomic-embed-text-v1.5-embedding","input":"test"}' | tail -3
   ```
   Expected: HTTP 200 with embedding array of 768 dimensions.

4. If dimension mismatch (384 vs 768):
   - Wrong model loaded. `text-embedding-nomic-embed-text-v1.5-embedding` produces 768-dim embeddings.
   - Check Qdrant collection vector size config — must match embedding dimension.

### Procedure 3: Short-Term Memory JSON Corruption

1. Locate memory files (typically in user data directory):
   ```bash
   find . -name "topics.json" -o -name "interests.json" -o -name "conversations.json" 2>/dev/null
   ```

2. Validate JSON:
   ```bash
   python3 -m json.tool <path-to-file> > /dev/null && echo "VALID" || echo "CORRUPT"
   ```

3. If corrupt:
   - Backup the file: `cp <file> <file>.bak`
   - Try to repair: manually fix JSON syntax issues
   - Or reset: `echo '[]' > <file>` (for arrays) or `echo '{}' > <file>` (for objects)

4. Restart backend after repair.

## Known Fixes

- **Mem0 `user_id` parameter bug**: Resolved — all calls to `mem0_memory.search()` now pass `filters={"user_id": user_id}` (the old `user_id=user_id` keyword argument form was incompatible with Mem0's API). See [STATUS.md](../STATUS.md).
- **Topics/interests not used in simple path**: Resolved — knowledge context now injected into `simple_node()` prompt. See [STATUS.md](../STATUS.md).
- **Memory context caching**: 5-minute TTL per thread, invalidated on `memory_write`. See [AGENT_FLOW.md](../AGENT_FLOW.md).
- See also: [ARCHITECTURE_OVERVIEW.md](../ARCHITECTURE_OVERVIEW.md) sections 6-7 for memory architecture.
