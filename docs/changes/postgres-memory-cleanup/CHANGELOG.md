# Postgres memory cleanup (Phases 1–3)

**Date:** 2026-08-26

## Summary

Removed leftover Qdrant/Redis/Mem0-library dead weight after the Postgres/pgvector migration, updated active docs to describe the real memory architecture, and added an anti-SPOF circuit breaker so chat can limp when local Postgres is down without hammering a dead pool.

## Phase 1 — Dead infra / config

- Stripped `qdrant` and `redis` services, volumes, and backend env/`depends_on` from `docker-compose.yml` (MVP compose was already Postgres-only).
- Deleted `scripts/drop_legacy_chroma_collection.py`.
- Dropped unused `mem0ai[nlp]` from `pyproject.toml` (and transitive `qdrant-client`); regenerated `uv.lock`.
- Removed `external_services.qdrant` / `external_services.redis` from `defaults.yaml`, env maps, `settings.py`, `.env.example`, advanced-settings `redis_url`, and profile override maps.
- Removed optional Redis/Qdrant probes from `/api/system-info`; dropped unused `redis`/`qdrant` fields from `useSystemHealth.ts`.
- Deleted Redis-checkpointer-era tests; replaced Qdrant config test with `tests/test_pgvector_memory_config.py`; renamed checkpoint property tests to Postgres naming; updated alignment / unified-settings / smoke enqueue tests.
- **Kept:** `mem0_uid` DB column (HTTP path rename deferred to residual-risks pass).

## Phase 2 — Docs truth

- Replaced `docs/architecture/REDIS_LIFECYCLE.md` with `docs/architecture/POSTGRES_MEMORY_LIFECYCLE.md`.
- Updated `MEMORY.md`, `SEMANTIC_CACHE.md`, `overview.md`, `AGENTS.md`, `dev-startup.md`, `docs/INDEX.md`, `docs/README.md`.
- Removed obsolete `redis_url` from `API_REFERENCE.md` / `CHAT_PROTOCOL.md` advanced-settings examples (setting removed in Phase 1).
- Pointed `.agents/skills/update-docs/SKILL.md` at the new lifecycle doc.

## Phase 3 — Anti-SPOF (circuit breaker + honest health)

- Added `src/memory/postgres_health.py` soft-path circuit breaker (open after consecutive failures, cooldown, half-open trial); wired into LTM / semantic cache / thought graph soft paths.
- Honest `/api/health` + `/api/system-info`: expose `postgres` (`ok`/`degraded`/`error`) and `checkpointer` (`postgres`/`memory`); no Redis/Qdrant probes.
- Frontend `useSystemHealth` toast on postgres degrade/recover; `SystemInfoCard` shows degraded as warn.
- Extraction worker LISTEN reconnect with backoff; graph session skips Postgres verify when on MemorySaver or circuit open.

## Deferred

- Renaming `mem0_uid` DB column (out of scope; HTTP path rename done)

## Residual risks cleared

- **`/api/health` `degraded` misread:** Documented that `status` is memory durability (`ok`|`degraded`) while readiness is `agent === "ready"`. Electron splash already used `agent`; App, frontier/browser/extension eval waiters, SDK types, API_REFERENCE, and README updated accordingly. Nested `postgres` / `checkpointer` remain authoritative.
- **Open circuit / empty memory UX:** Toast + SystemInfoCard copy unified to “Postgres degraded — memory/history may not persist” (MemorySaver checkpoints called out separately). Documented the **45s** circuit open window in `POSTGRES_MEMORY_LIFECYCLE.md`.
- **`/api/mem0/*` → `/api/memory/*`:** Canonical `/api/memory/{search,count,add,delete,clear,reset}` with `/api/mem0/*` dual-mount aliases. MemoryPanel + frontier eval prefer `/api/memory/*`. `mem0_uid` column unchanged.
- **Organic / enqueue when circuit open:** `get_or_create_node` returns `None` (no fake ephemeral success); API returns 503; study tool reports failure. `enqueue_extraction` returns `None` on circuit open (vs `False` dedup). Organic/thought-graph/enqueue tests soft-skip or soft-assert; unit tests cover circuit-open returns.

## Ops note (2026-08-26)

- Recommend **Podman machine 4 GB** (was commonly 2 GB); mvp compose sets postgres `mem_limit: 768m`. After the bump, `/api/health` reported `postgres: ok` through full topic-drift E2E.
