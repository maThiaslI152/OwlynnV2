---
status: active
category: performance
last_updated: 2026-07-07
owner: ai-agent
audience: agent
---

# Semantic Cache

> **Purpose:** Near-instant responses for repetitive questions by bypassing LangGraph entirely with a vector-similarity cache stored in Redis.

## Overview

The Semantic Cache intercepts incoming user prompts **before** the LangGraph agent graph executes. If a semantically identical question was asked in the same project before, the cached answer is streamed back instantly — skipping LLM inference, tool execution, and memory retrieval entirely.

This reduces Time-To-First-Token (TTFT) for cache hits from **3-15s → <100ms**.

## Architecture

```text
WebSocket intake
      │
      ▼
check_semantic_cache(prompt, project_id)
      │
      ├─ MISS → session.start_run() → [full LangGraph graph] → on idle: store_semantic_cache()
      │
      └─ HIT  → stream cached answer → send idle event → done (graph never executes)
```

The cache is **project-scoped**: a question answered in Project A will not be served to Project B, ensuring contextual isolation.

## Module

**File:** `src/memory/semantic_cache.py`

| Function | Description |
|----------|-------------|
| `init_semantic_cache()` | Initialises the `redisvl` `SemanticCache` index. Called once at agent startup from `init_agent()`. |
| `check_semantic_cache(prompt, project_id)` | Embeds the prompt and performs a vector similarity search against Redis. Returns the cached response string or `None`. |
| `store_semantic_cache(prompt, response, project_id)` | Stores the prompt embedding + response text in Redis. Called asynchronously after the `idle` event fires. |

### CustomOpenAIVectorizer

A lightweight Pydantic-compatible vectorizer that calls the **LM Studio embedding endpoint** (`nomic-embed-text-v1.5`) via the OpenAI async client. This reuses the same embedding model already running for Mem0/Qdrant, adding zero additional memory overhead.

## Integration Points

### `src/api/ws/handler.py`

The handler performs the cache check immediately after validating the message payload and resolving `project_id`:

```python
# Before session.start_run()
cached_answer = await check_semantic_cache(user_input, project_id=project_id)
if cached_answer:
    # Stream reply directly over WS — graph never runs
    ...
    continue

# After graph run completes (idle event in forward_events closure)
asyncio.create_task(store_semantic_cache(prompt, ai_text, project_id=project_id))
```

A `_pending_cache` dict shared between the message receive loop and the `forward_events` closure carries the `prompt` and `project_id` across the async boundary.

### `src/agent/core/graph.py`

`init_agent()` fires `init_semantic_cache()` non-blocking on startup:

```python
_asyncio.ensure_future(init_semantic_cache())
```

If Redis is unavailable or redisvl initialisation fails, the cache silently degrades to disabled — the system continues normally without caching.

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Similarity threshold | `0.92` (distance `0.08`) | Minimum similarity required for a cache hit. Uses Redis COSINE distance where `0.0 = identical, 2.0 = opposite`. |
| Cache TTL | `None` (no expiry) | Entries persist indefinitely. Redis eviction policy (`maxmemory-policy`) governs when entries are dropped. |
| Redis index name | `owlynn_semantic_cache` | RedisVL search index name. |
| Embedding model | `models.embedding.model_name` from `defaults.yaml` | Same nomic-embed model used for Mem0. |
| Embedding URL | `models.embedding.base_url` from `defaults.yaml` | LM Studio embedding endpoint. |

## Bypass Conditions

The semantic cache is **skipped** when:

| Condition | Reason |
|-----------|--------|
| `scenario_id == "pentest"` | Pentest sessions must never be cached — operational security |
| `files` attached | Answers depend on file content, not just the question text |
| `message_content` is not a plain string | Multi-modal (image) payloads are not cacheable |

## Cache Population Flow

```text
1. User sends message (cache miss)
2. Graph runs normally
3. complex_llm / simple node produces final text_for_ui
4. handler.forward_events() tracks this text in _last_ai_text_for_cache
5. GraphSession emits {"type": "status", "content": "idle"}
6. forward_events() detects idle + text + pending prompt → fires store_semantic_cache() as background task
7. Next time the same question is asked → cache HIT
```

## Observability

- **Cache HIT**: `INFO [semantic-cache] Cache HIT for thread=<thread_id>` in application logs
- **Init failure**: `WARNING Failed to initialize Semantic Cache: ...` (degraded gracefully)
- **Store failure**: `WARNING Semantic Cache store failed: ...` (non-fatal, answer still delivered)
- **WS event on hit**: `model: "cache"` appears in `stream` and `message` events sent to frontend

## Performance Impact

| Scenario | Before | After |
|----------|--------|-------|
| Repeated project question (HIT) | 3–15s TTFT | < 100ms TTFT |
| New unique question (MISS) | 3–15s TTFT | 3–15s TTFT (no change) |
| Cloud API tokens consumed on hit | Yes | **0** |
| Local LLM GPU utilised on hit | Yes | **0** |

## Related Files

- `src/memory/semantic_cache.py` — Module implementation
- `src/api/ws/handler.py` — Cache check + store hooks
- `src/agent/core/graph.py` — Startup init
- `src/memory/long_term.py` — Mem0 + nomic embed (same vectorizer)
- `docs/architecture/REDIS_LIFECYCLE.md` — Redis memory management (checkpoint eviction)
- `docs/features/MEMORY.md` — Full memory system overview

## Last updated

2026-07-07 — Feature implemented and documented.
