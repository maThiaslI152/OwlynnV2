"""Semantic Caching using PostgreSQL pgvector.

Replaces the previous Redis redisvl implementation.  Cache entries are stored
in the ``semantic_cache`` table managed by
:class:`~src.memory.db_models.SemanticCacheEntry`.

All operations are async and use the shared :mod:`src.models.db` session.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text

from src.config.config_loader import config
from src.memory.db_models import SemanticCacheEntry
from src.models.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_embed_model: str = config.get_embedding_model_name()
_embed_url: str = config.get_embedding_base_url()

# Cosine distance threshold: < 0.08 ≈ >92% similar → cache hit
_CACHE_THRESHOLD: float = 0.08

# In-memory exact-match cache: (project_id, normalized_prompt) -> (cached_at, response)
_exact_cache: dict[tuple[str, str], tuple[datetime, str]] = {}
_EXACT_CACHE_MAX_ENTRIES = 1000
_EXACT_CACHE_TTL_SECONDS = 3600 * 24  # 24 hours


def _normalize_exact_prompt(prompt: str) -> str:
    """Normalize prompt for exact in-memory hash matching."""
    return " ".join(prompt.strip().lower().split())


def _is_poisoned_cache_response(response: str | None) -> bool:
    """True when a cached answer is unbound tool markup (must never be served)."""
    if not response or not str(response).strip():
        return True
    try:
        from src.agent.core.complex_utils.formatter import _content_has_dsml_tool_syntax

        return bool(_content_has_dsml_tool_syntax(str(response)))
    except Exception:
        # Conservative: obvious gemma/qwen tool leaks
        t = str(response)
        return "<|tool_call" in t or "<tool_call>" in t or "<function=" in t


async def purge_poisoned_cache_entries() -> int:
    """Delete semantic_cache rows whose response is leaked tool-call markup."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    DELETE FROM semantic_cache
                    WHERE response ILIKE '%tool_call%'
                       OR response ILIKE '%<function=%'
                       OR response ILIKE '%GoogleSearch%'
                    """
                )
            )
            await session.commit()
            deleted = result.rowcount or 0
        if deleted:
            logger.info(
                "[semantic_cache] Purged %d poisoned tool-leak cache entries", deleted
            )
        return int(deleted)
    except Exception as exc:
        logger.warning("[semantic_cache] purge_poisoned failed: %s", exc, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


async def _get_embedding(text_: str) -> list[float]:
    """Delegate to the shared embedding helper in :mod:`src.memory.long_term`."""
    from src.memory.long_term import get_embedding

    return await get_embedding(text_)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def init_semantic_cache() -> None:
    """No-op initialiser kept for API compatibility.

    The ``semantic_cache`` table is created by Alembic migrations.  Nothing
    needs to be set up at runtime.
    """
    logger.info("[semantic_cache] pgvector semantic cache ready (table=semantic_cache)")


async def check_semantic_cache(prompt: str, project_id: str = "default") -> str | None:
    """Look up a semantically similar prompt in the cache.

    First checks the ultra-fast in-memory exact-match cache (<1ms TTFT).
    If missed, falls back to pgvector cosine distance search.

    Args:
        prompt:     The raw user prompt to look up.
        project_id: Project scope for the lookup.

    Returns:
        The cached response string, or ``None`` if no hit was found.
    """
    # ── Fast path: In-memory exact match (<1ms) ───────────────────────────
    norm_prompt = _normalize_exact_prompt(prompt)
    cache_key = (project_id, norm_prompt)
    if cache_key in _exact_cache:
        cached_at, cached_res = _exact_cache[cache_key]
        if datetime.now(UTC) - cached_at < timedelta(seconds=_EXACT_CACHE_TTL_SECONDS):
            if not _is_poisoned_cache_response(cached_res):
                logger.info(
                    "[semantic_cache] Exact in-memory Cache HIT for project=%s",
                    project_id,
                )
                return cached_res
            else:
                _exact_cache.pop(cache_key, None)
        else:
            _exact_cache.pop(cache_key, None)

    # ── Fallback path: pgvector cosine similarity search ──────────────────
    from src.memory.postgres_health import (
        is_postgres_available,
        record_postgres_failure,
        record_postgres_success,
    )

    if not is_postgres_available():
        return None

    try:
        scoped_prompt = f"[Project: {project_id}] {prompt}"
        embedding = await _get_embedding(scoped_prompt)
        vec_literal = str(embedding)

        sql = text(
            """
            SELECT response
            FROM semantic_cache
            WHERE project_id = :project_id
              AND (embedding::vector <=> (:vec)::vector) < :threshold
            ORDER BY embedding::vector <=> (:vec)::vector
            LIMIT 1
            """
        )

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sql,
                {
                    "project_id": project_id,
                    "vec": vec_literal,
                    "threshold": _CACHE_THRESHOLD,
                },
            )
            row = result.fetchone()

        if row:
            if _is_poisoned_cache_response(row.response):
                logger.warning(
                    "[semantic_cache] Ignoring poisoned cache hit for project=%s",
                    project_id,
                )
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            delete(SemanticCacheEntry).where(
                                SemanticCacheEntry.response == row.response
                            )
                        )
                        await session.commit()
                except Exception as purge_exc:
                    logger.debug(
                        "[semantic_cache] poisoned row delete failed: %s", purge_exc
                    )
                return None
            record_postgres_success()
            logger.debug(
                "[semantic_cache] pgvector Cache HIT for project=%s", project_id
            )
            # Warm up the in-memory exact cache with this hit
            _exact_cache[cache_key] = (datetime.now(UTC), row.response)
            return row.response

        record_postgres_success()
        logger.debug("[semantic_cache] Cache MISS for project=%s", project_id)
        return None

    except Exception as exc:
        record_postgres_failure()
        logger.warning("[semantic_cache] check failed: %s", exc, exc_info=True)
        return None


async def store_semantic_cache(
    prompt: str,
    response: str,
    project_id: str = "default",
) -> None:
    """Embed *prompt* and INSERT a new entry into ``semantic_cache``.

    Also populates the in-memory exact cache for instant subsequent hits.

    Args:
        prompt:     The raw user prompt to cache.
        response:   The LLM response to store.
        project_id: Project scope for the cache entry.
    """
    from src.memory.postgres_health import (
        is_postgres_available,
        record_postgres_failure,
        record_postgres_success,
    )

    if _is_poisoned_cache_response(response):
        logger.warning("[semantic_cache] Refusing to store poisoned tool-leak response")
        return

    # Update in-memory exact cache
    norm_prompt = _normalize_exact_prompt(prompt)
    cache_key = (project_id, norm_prompt)
    if len(_exact_cache) >= _EXACT_CACHE_MAX_ENTRIES:
        # Evict oldest 10%
        oldest_keys = sorted(_exact_cache.keys(), key=lambda k: _exact_cache[k][0])[
            : _EXACT_CACHE_MAX_ENTRIES // 10
        ]
        for ok in oldest_keys:
            _exact_cache.pop(ok, None)
    _exact_cache[cache_key] = (datetime.now(UTC), response)

    if not is_postgres_available():
        return
    try:
        scoped_prompt = f"[Project: {project_id}] {prompt}"
        embedding = await _get_embedding(scoped_prompt)

        row = SemanticCacheEntry(
            project_id=project_id,
            prompt_scoped=scoped_prompt,
            response=response,
            embedding=embedding,
        )

        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()

        record_postgres_success()
        logger.debug("[semantic_cache] Stored entry for project=%s", project_id)

    except Exception as exc:
        record_postgres_failure()
        logger.warning("[semantic_cache] store failed: %s", exc, exc_info=True)


async def cleanup_old_cache_entries(days: int = 30) -> int:
    """Delete cache entries older than *days* days.

    Args:
        days: Entries created more than this many days ago are removed.
              Defaults to 30 days.

    Returns:
        Number of rows deleted.
    """
    try:
        cutoff = datetime.now(UTC) - timedelta(days=days)

        async with AsyncSessionLocal() as session:
            stmt = delete(SemanticCacheEntry).where(
                SemanticCacheEntry.created_at < cutoff
            )
            result = await session.execute(stmt)
            await session.commit()
            deleted = result.rowcount

        logger.info(
            "[semantic_cache] Cleaned up %d entries older than %d days", deleted, days
        )
        return deleted

    except Exception as exc:
        logger.warning("[semantic_cache] cleanup failed: %s", exc, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Quick smoke-test (python -m src.memory.semantic_cache)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _test() -> None:
        await init_semantic_cache()
        await store_semantic_cache("Hello world", "Hi there!", project_id="test")
        res = await check_semantic_cache("Hello world", project_id="test")
        print("Result:", res)

    asyncio.run(_test())
