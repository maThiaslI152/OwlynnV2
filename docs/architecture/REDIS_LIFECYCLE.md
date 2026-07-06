---
status: active
category: architecture
last_updated: 2026-07-07
owner: ai-agent
audience: agent
---

# Redis Lifecycle Management

> **Purpose:** Documents Redis usage patterns, memory management strategies, and the checkpoint eviction system that prevents unbounded memory growth.

## Overview

Owlynn uses Redis for two distinct purposes, each with different lifecycle requirements:

| Purpose | Key Pattern | Managed By | TTL Strategy |
|---------|-------------|-----------|-------------|
| LangGraph checkpoints | `checkpoint:*` | `AsyncRedisSaver` | **Eviction task** (30-day idle) |
| Semantic response cache | `owlynn_semantic_cache:*` | `redisvl SemanticCache` | Redis maxmemory-policy |

## LangGraph Checkpoint Eviction

### Problem

`AsyncRedisSaver` persists LangGraph thread state (messages, tool call history, intermediate node outputs) as checkpoint keys with **no default TTL**. Over weeks/months of usage, stale threads from closed chats accumulate in Redis, causing:
- Unbounded memory growth → eventual OOM (Out of Memory)
- Slow `SCAN` iterations across a large key space
- Increased RDB snapshot sizes

### Solution: `_evict_stale_checkpoints()`

**File:** `src/agent/core/graph.py`

A background async task that runs **immediately on startup** and then every **24 hours**:

```python
async def _evict_stale_checkpoints(redis_url: str, max_age_days: int = 30):
    # Scans checkpoint:* keys
    # Checks OBJECT IDLETIME for keys with no TTL
    # Deletes any key idle > max_age_days * 86400 seconds
    # Logs number of evicted keys
    await asyncio.sleep(86_400)  # Repeat daily
```

**Eviction criteria:**
1. Key matches pattern `checkpoint:*`
2. Key has **no TTL set** (`ttl == -1`)
3. Redis reports `OBJECT IDLETIME > 30 days` (key has not been read/written in 30+ days)

Keys with active TTLs are left alone — they will expire naturally.

### Wiring

In `init_agent()`, when Redis checkpointer is successfully set up:

```python
checkpointer = AsyncRedisSaver(redis_url=REDIS_URL)
await checkpointer.setup()
_asyncio.ensure_future(_evict_stale_checkpoints(REDIS_URL))
```

Falls back gracefully: if Redis is unavailable, `MemorySaver` is used and eviction is not started.

### Observability

- **Eviction occurred:** `INFO [checkpoint-evict] Evicted N stale checkpoint keys (> 30 days idle)`
- **Scan error:** `WARNING [checkpoint-evict] Error during eviction scan: ...` (non-fatal, retries next day)

## Semantic Cache Memory Management

The `redisvl` `SemanticCache` stores embedding vectors + response text in a RedisVL search index (`owlynn_semantic_cache`). Unlike checkpoints, these entries are generally small (text + 768-dim float vector ≈ ~5KB each).

**Memory management:** Governed by Redis `maxmemory-policy` in your Redis configuration. Recommended policy for this use case:

```conf
maxmemory 256mb          # Hard cap (see PERFORMANCE_SLOS.md)
maxmemory-policy allkeys-lru  # Evict least-recently-used entries when limit hit
```

With `allkeys-lru`, the cache self-manages: the least-used (oldest) cache entries are automatically evicted when the 256MB cap is reached, making the cache self-regulating.

## Memory Budget

From `PERFORMANCE_SLOS.md`:

| Component | Budget |
|-----------|--------|
| Redis (checkpoints + semantic cache) | 128 MB |

With eviction active:
- Checkpoint keys older than 30 days are deleted → keeps checkpoint space bounded
- Semantic cache is LRU-bounded by `maxmemory-policy` → stays within budget
- Total Redis usage should remain well under 128 MB for a normal user

## Configuration

All eviction behaviour is currently hardcoded in `_evict_stale_checkpoints`. Future improvements could expose these via `defaults.yaml`:

```yaml
# Proposed (not yet implemented)
redis:
  checkpoint_eviction:
    enabled: true
    max_age_days: 30
    scan_batch_size: 500
```

## Monitoring

### Quick Redis memory check

```bash
redis-cli info memory | grep used_memory_human
redis-cli info keyspace
redis-cli --scan --pattern "checkpoint:*" | wc -l
redis-cli --scan --pattern "owlynn_semantic_cache:*" | wc -l
```

### Check eviction log

```bash
grep "checkpoint-evict" logs/agent.log
```

## Related Files

- `src/agent/core/graph.py` — `_evict_stale_checkpoints()`, `init_agent()`
- `src/memory/semantic_cache.py` — `SemanticCache` init and store/check
- `docs/features/SEMANTIC_CACHE.md` — Semantic cache feature documentation
- `docs/PERFORMANCE_SLOS.md` — Redis memory budget
- `docker-compose.yml` — Redis service definition

## Last updated

2026-07-07 — Feature implemented. Checkpoint eviction and semantic cache lifecycle documented.
