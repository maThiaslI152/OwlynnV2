---
status: active
category: architecture
last_updated: 2026-07-07
owner: ai-agent
audience: agent
---

# Redis Memory Management

> **Purpose:** Documents Redis usage patterns and memory management strategies for the Semantic Cache and Memory Extraction Queue (LangGraph checkpoints have been migrated to PostgreSQL).

## Overview

Owlynn uses Redis for memory management features (note that LangGraph checkpoints are stored in PostgreSQL):

| Purpose | Key Pattern | Managed By | TTL Strategy |
|---------|-------------|-----------|-------------|
| Semantic response cache | `owlynn_semantic_cache:*` | `redisvl SemanticCache` | Redis maxmemory-policy |
| Memory extraction queue | N/A (Redis stream) | Background worker | Processed on idle |

## LangGraph Checkpoint Management

*Note: LangGraph checkpoints were migrated to PostgreSQL in Phase 6.*

Previously, `AsyncRedisSaver` was used, which required an eviction task (`_evict_stale_checkpoints`). With the migration to PostgreSQL (`AsyncPostgresSaver` in `src/agent/core/checkpointer.py`), state persistence is natively handled without the need for manual TTL eviction or bounded memory limits.

## Semantic Cache Memory Management

The `redisvl` `SemanticCache` stores embedding vectors + response text in a RedisVL search index (`owlynn_semantic_cache`). Unlike checkpoints, these entries are generally small (text + 768-dim float vector ≈ ~5KB each).

**Memory management:** Governed by Redis `maxmemory-policy` in your Redis configuration. Recommended policy for this use case:

```conf
maxmemory 256mb          # Hard cap (see PERFORMANCE_SLOS.md)
maxmemory-policy allkeys-lru  # Evict least-recently-used entries when limit hit
```

With `allkeys-lru`, the cache self-manages: the least-used (oldest) cache entries are automatically evicted when the 256MB cap is reached, making the cache self-regulating.

From `PERFORMANCE_SLOS.md`:

| Component | Budget |
|-----------|--------|
| Redis (semantic cache + extraction) | 128 MB |

With eviction active:
- Semantic cache is LRU-bounded by `maxmemory-policy` → stays within budget
- Total Redis usage should remain well under 128 MB for a normal user

## Configuration

Configuration for Redis limits can be adapted in `defaults.yaml`.

## Monitoring

### Quick Redis memory check

```bash
redis-cli info memory | grep used_memory_human
redis-cli info keyspace
redis-cli --scan --pattern "owlynn_semantic_cache:*" | wc -l
```

## Related Files

- `src/agent/core/checkpointer.py` — `AsyncPostgresSaver` (migrated checkpointer)
- `src/memory/semantic_cache.py` — `SemanticCache` init and store/check
- `src/memory/extraction/worker.py` — Memory extraction queue processor
- `docs/features/SEMANTIC_CACHE.md` — Semantic cache feature documentation
- `docs/PERFORMANCE_SLOS.md` — Redis memory budget
- `docker-compose.yml` — Redis service definition

## Last updated

2026-07-10 — Updated to reflect Phase 6 migration of LangGraph checkpointer to PostgreSQL.
