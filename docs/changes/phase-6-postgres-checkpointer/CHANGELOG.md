## 2026-07-10 — Phase 6: Migrating LangGraph checkpointer from Redis to PostgreSQL

### What
Migrated the LangGraph checkpointer from Redis to PostgreSQL. The state persistence is now handled by PostgreSQL natively, eliminating the need for a 30-day TTL eviction script. Note that Semantic Cache and Memory Extraction Queue are still managed via Redis.

### Why
- PostgreSQL offers native durability for state persistence.
- Eliminates the bounded memory limit issues with LangGraph checkpoints accumulating in Redis.
- Allows native relational integration for legacy chat checks.

### Files
- `pyproject.toml` / `uv.lock`: Installed `langgraph-checkpoint-postgres`, `psycopg`, and `psycopg-pool`.
- `src/agent/core/checkpointer.py`: Created this new file to manage the `psycopg_pool.AsyncConnectionPool` and instantiate `AsyncPostgresSaver`.
- `src/agent/core/graph.py`: Switched to `AsyncPostgresSaver` in `init_agent()`. Removed the `_evict_stale_checkpoints` logic.
- `src/api/controllers/graph_session.py`: Updated `_check_checkpoint` logic to use Postgres `aget_tuple()`.
- `src/api/routes/project.py`: Updated legacy chat checks to query Postgres.
- `src/api/server.py`: Updated legacy chat warning log.
