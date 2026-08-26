---
status: active
category: architecture
last_updated: 2026-08-26
owner: ai-agent
audience: agent
---

# Postgres Memory Lifecycle

> **Purpose:** How Owlynn stores checkpoints, long-term memory, semantic cache, and extraction jobs in a single local Postgres (pgvector) instance — and what happens when it is degraded.

## Overview

Postgres is the durable hub. Redis and Qdrant are **not** on the live memory path. `start.sh` uses `docker-compose.mvp.yml` (Postgres + optional StirlingPDF only). Postgres container `mem_limit: 768m`; recommend Podman machine **4 GB** RAM so the VM does not OOM under load (see `docs/guides/dev-startup.md`).

| Store | Module | Backend |
|-------|--------|---------|
| LangGraph checkpoints | `src/agent/core/checkpointer.py` | `AsyncPostgresSaver` |
| Long-term memory (LTM) | `src/memory/long_term.py` | `memory_vectors` (pgvector, 1024-dim) |
| Semantic response cache | `src/memory/semantic_cache.py` | `semantic_cache` (pgvector) |
| Extraction queue | `src/memory/extraction/` | `extraction_jobs` + `LISTEN/NOTIFY` |
| Thought graph / STM / personal | `thought_graph.py`, `memory_manager.py`, `personal_assistant.py` | Postgres tables |
| Profile / persona | JSON under `data/` | Files (survive Postgres outage) |

**HTTP:** Canonical LTM REST paths are `/api/memory/*`. Legacy `/api/mem0/*` aliases remain. The `mem0_uid` DB column name is unchanged (shim over pgvector — not the Mem0 library).

## Checkpoints

`AsyncPostgresSaver` persists graph state after each step. On startup, `init_agent()` verifies round-trip persistence; on failure it falls back to in-memory `MemorySaver` (conversations will not survive restarts).

## Semantic cache

Entries live in the `semantic_cache` table (prompt embedding + response text, project-scoped). Similarity uses cosine distance (threshold ≈ 0.08 ≈ 92% similar). When Postgres is unavailable, cache check/store soft-fail and chat continues without caching.

See [`docs/features/SEMANTIC_CACHE.md`](../features/SEMANTIC_CACHE.md).

## Extraction queue

`enqueue_extraction()` inserts into `extraction_jobs` and wakes the worker via `pg_notify('extraction_channel', ...)`. The worker (`src/memory/extraction/worker.py`) `LISTEN`s for jobs, runs dual-channel extraction (declarative facts + procedural skills) when the local LLM is idle, and writes L1 atoms into `memory_vectors`.

Dedup is `INSERT … ON CONFLICT DO NOTHING` on `turn_id`. Returns `True` if newly queued, `False` if dedup hit, `None` if the Postgres circuit is open (explicit skip — not success). If enqueue fails with circuit closed, an in-process fallback may retain the job briefly; it is not a second durable store.

## Soft-path circuit breaker

Module: `src/memory/postgres_health.py`.

| Parameter | Default | Role |
|-----------|---------|------|
| Failure threshold | 2 consecutive failures | Opens the circuit |
| Cooldown (open window) | **45 seconds** | Soft paths skipped; then half-open trial |
| Half-open | after cooldown | One trial allowed; success closes, failure re-opens |

While open: LTM search/add, semantic cache, thought-graph writes, and extraction enqueue soft-skip (no pool spam). Chat LLM path continues. UI toast + System info show “Postgres degraded — memory/history may not persist”.

## When Postgres is degraded

Local Mac setup keeps **one** Postgres — no Redis/Qdrant dual-write for HA.

| Area | Behavior |
|------|----------|
| Chat LLM path | Continues (tools/routing still work) |
| Checkpoints | May fall back to `MemorySaver` at startup; mid-session durability depends on checkpointer health |
| LTM / semantic cache / extraction / thought-graph writes | Soft-miss / `None` / `False` when circuit open or DB unreachable — callers must not treat skips as persisted success |
| Profile / persona / skills files | Unaffected (filesystem) |
| `/api/health` | `status`: `ok` \| `degraded` (memory durability); `agent`: `ready` \| `initializing` (use `agent` for “can I talk?”); nested `postgres` / `checkpointer` |

## Related

- `docs/features/MEMORY.md` — full memory system
- `docs/features/SEMANTIC_CACHE.md` — cache hit path
- `docker-compose.mvp.yml` — production-dev compose (Postgres only)
- `src/agent/core/checkpointer.py` — Postgres checkpointer
- `src/memory/extraction/worker.py` — LISTEN worker

## Last updated

2026-08-26 — Podman 4 GB + postgres `mem_limit: 768m`; residual risks cleared (health readiness, `/api/memory/*`, 45s circuit, soft-fail returns).
