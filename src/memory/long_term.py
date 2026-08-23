"""
Long-Term Memory Management using PostgreSQL pgvector.

Replaces the previous Mem0 + Qdrant implementation.  Embeddings are still
served by LM Studio (nomic-embed-text-v1.5) via the OpenAI-compatible
endpoint.  All vectors are stored in the ``memory_vectors`` table managed
by the :class:`~src.memory.db_models.MemoryVector` ORM model.

Backward-compatible shims
--------------------------
* :class:`LongTermMemory` — async class used by ``extraction/worker.py``
* ``memory`` module-level singleton — sync-callable object used by
  ``api/routes/memory.py``, ``agent/nodes/memory.py``, and tool files that
  call ``memory.add/search/delete/delete_all/reset`` inside
  ``asyncio.to_thread`` or directly from async FastAPI endpoints.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import delete as sa_delete
from sqlalchemy import text

from src.config.audit_log import audit_info, audit_warn
from src.config.config_loader import config
from src.memory.db_models import MemoryVector
from src.models.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding config
# ---------------------------------------------------------------------------

_embed_model: str = config.get_embedding_model_name()
_embed_url: str = config.get_embedding_base_url()

_embed_client = AsyncOpenAI(api_key="sk-dummy", base_url=_embed_url)

# Cosine distance threshold for semantic deduplication on add()
_DEDUP_THRESHOLD: float = 0.08  # < 0.08 => >92% similar → skip


# ---------------------------------------------------------------------------
# Embedding helper (also imported by pentest_vectors & semantic_cache)
# ---------------------------------------------------------------------------


async def get_embedding(text_: str) -> list[float]:
    """Return an embedding vector (1024-dim) for *text_* using the configured model.

    This function is also imported by :mod:`src.memory.pentest_vectors` and
    :mod:`src.memory.semantic_cache`.
    """
    response = await _embed_client.embeddings.create(
        input=[text_],
        model=_embed_model,
    )
    return response.data[0].embedding


def _content_id(content: str, user_id: str) -> str:
    """Deterministic UUID-like ID from content + user_id (SHA-256 prefix)."""
    raw = f"{user_id}:{content}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return str(uuid.UUID(digest[:32]))


# ---------------------------------------------------------------------------
# Core async functions (used directly or via LongTermMemory)
# ---------------------------------------------------------------------------


async def _async_add(
    content: str,
    user_id: str = "default",
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Embed *content* and INSERT into ``memory_vectors``.

    Performs a semantic dedup check first: if a vector with cosine distance
    < _DEDUP_THRESHOLD already exists for this user_id, insertion is skipped.

    Returns the id of the inserted (or existing) row, or None on error.
    """
    if not content or len(content.strip()) < 3:
        return None

    meta = metadata or {}

    try:
        embedding = await get_embedding(content)
        vec_id = _content_id(content, user_id)
        vec_literal = str(embedding)  # "[0.1, 0.2, ...]" accepted by pgvector

        async with AsyncSessionLocal() as session:
            # --- semantic dedup ---
            dedup_sql = text(
                """
                SELECT id
                FROM memory_vectors
                WHERE user_id = :uid
                  AND (embedding::vector <=> (:vec)::vector) < :threshold
                LIMIT 1
                """
            )
            dedup_result = await session.execute(
                dedup_sql,
                {"uid": user_id, "vec": vec_literal, "threshold": _DEDUP_THRESHOLD},
            )
            existing = dedup_result.fetchone()
            if existing:
                logger.debug(
                    "[ltm] Skipping duplicate memory for user=%s (similar to %s)",
                    user_id,
                    existing[0],
                )
                return existing[0]

            row = MemoryVector(
                id=vec_id,
                content=content,
                embedding=embedding,
                user_id=user_id,
                project_id=meta.get("project_id"),
                tier=meta.get("tier"),
                format=meta.get("format"),
                tags=meta.get("tags", []),
                meta_data=meta,
                confidence=meta.get("confidence"),
                source=meta.get("source"),
                scenario_id=meta.get("scenario_id"),
            )
            session.add(row)
            await session.commit()

        audit_info(
            "memory.ltm",
            "add",
            id=vec_id,
            user_id=user_id,
            content_len=len(content),
        )
        return vec_id

    except Exception as exc:
        logger.warning("[ltm] add() failed: %s", exc, exc_info=True)
        audit_warn("memory.ltm", "add_failed", reason=str(exc)[:120], user_id=user_id)
        return None


async def _async_search(
    query: str,
    filters: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, list[dict]]:
    """Embed *query* and return the *limit* nearest memories.

    Returns:
        ``{"results": [{"id": ..., "memory": ..., "metadata": {...}}, ...]}``
    """
    if not query or not query.strip():
        query = " "  # fallback: return nearest to zero-like vector (all memories)

    fltr = filters or {}

    try:
        embedding = await get_embedding(query)
        vec_literal = str(embedding)

        where_clauses = ["1=1"]
        params: dict[str, Any] = {"vec": vec_literal, "lim": limit}
        if fltr.get("user_id"):
            where_clauses.append("user_id = :user_id")
            params["user_id"] = fltr["user_id"]
        if fltr.get("project_id"):
            where_clauses.append("project_id = :project_id")
            params["project_id"] = fltr["project_id"]
        if fltr.get("scenario_id"):
            where_clauses.append("scenario_id = :scenario_id")
            params["scenario_id"] = fltr["scenario_id"]

        where_sql = " AND ".join(where_clauses)

        sql = text(
            f"""
            SELECT
                id,
                content,
                user_id,
                project_id,
                tier,
                format,
                tags,
                confidence,
                source,
                scenario_id,
                created_at,
                (embedding::vector <=> (:vec)::vector) AS distance
            FROM memory_vectors
            WHERE {where_sql}
            ORDER BY embedding::vector <=> (:vec)::vector
            LIMIT :lim
            """
        )

        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        return {
            "results": [
                {
                    "id": row.id,
                    "memory": row.content,
                    "metadata": {
                        "user_id": row.user_id,
                        "project_id": row.project_id,
                        "tier": row.tier,
                        "format": row.format,
                        "tags": row.tags,
                        "confidence": row.confidence,
                        "source": row.source,
                        "scenario_id": row.scenario_id,
                        "created_at": (
                            row.created_at.isoformat() if row.created_at else None
                        ),
                        "score": (
                            1.0 - float(row.distance)
                            if row.distance is not None
                            else 1.0
                        ),
                    },
                }
                for row in rows
            ]
        }

    except Exception as exc:
        logger.warning("[ltm] search() failed: %s", exc, exc_info=True)
        return {"results": []}


async def _async_delete(
    memory_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Delete memories by id, or by user_id and metadata filters."""
    try:
        async with AsyncSessionLocal() as session, session.begin():
            if memory_id:
                stmt = sa_delete(MemoryVector).where(MemoryVector.id == memory_id)
            else:
                stmt = sa_delete(MemoryVector)
                if user_id:
                    stmt = stmt.where(MemoryVector.user_id == user_id)
                if metadata:
                    for k, v in metadata.items():
                        # Querying JSONB metadata field in PostgreSQL
                        stmt = stmt.where(
                            MemoryVector.meta_data[k].as_string()
                            == (f'"{v}"' if isinstance(v, str) else str(v))
                        )
            await session.execute(stmt)
        audit_info(
            "memory.ltm", "delete", id=memory_id, user_id=user_id, metadata=metadata
        )
        return True
    except Exception as exc:
        logger.warning("[ltm] delete() failed: %s", exc, exc_info=True)
        return False


async def _async_delete_all(user_id: str) -> bool:
    """Delete all memories for *user_id*."""
    return await _async_delete(user_id=user_id)


async def _async_reset() -> bool:
    """Delete ALL memories from the memory_vectors table."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = sa_delete(MemoryVector)
            await session.execute(stmt)
            await session.commit()
        audit_info("memory.ltm", "reset")
        return True
    except Exception as exc:
        logger.warning("[ltm] reset() failed: %s", exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# LongTermMemory — async class interface (used by extraction/worker.py)
# ---------------------------------------------------------------------------


class LongTermMemory:
    """Async-native wrapper around the pgvector memory store.

    Used by :mod:`src.memory.extraction.worker` which ``await``s each method.
    """

    async def add(
        self,
        content: str,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        return await _async_add(content, user_id=user_id, metadata=metadata)

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> dict[str, list[dict]]:
        return await _async_search(query, filters=filters, limit=limit)

    async def delete(
        self,
        memory_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        return await _async_delete(
            memory_id=memory_id, user_id=user_id, metadata=metadata
        )

    async def delete_all(self, user_id: str) -> bool:
        return await _async_delete_all(user_id)

    async def reset(self) -> bool:
        return await _async_reset()


# ---------------------------------------------------------------------------
# _SyncMemoryShim — synchronous interface (used by legacy callers via
#   asyncio.to_thread or directly from async FastAPI endpoints without await)
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine from synchronous code.

    If called outside an event loop, we use ``asyncio.run``.
    If called from within a running event loop thread, we run it in a separate
    thread via a ThreadPoolExecutor to prevent deadlocking the active loop.
    """
    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


class _SyncMemoryShim:
    """Synchronous shim exposing the same interface as the old Mem0 ``Memory`` object.

    Call sites that use ``asyncio.to_thread(lambda: memory.search(...))``
    will schedule this in a thread-pool where there is no running event loop,
    so we spin up a temporary loop.  Call sites inside async FastAPI handlers
    that call this without ``await`` will trigger ``run_coroutine_threadsafe``.
    """

    async def asearch(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> dict:
        return await _async_search(query, filters=filters, limit=limit)

    async def aadd(
        self,
        content: str,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ):
        return await _async_add(content, user_id=user_id, metadata=metadata)

    async def adelete(
        self,
        memory_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> bool:
        mid = memory_id or kwargs.get("memory_id")
        uid = user_id or kwargs.get("user_id")
        meta = metadata or kwargs.get("metadata")
        return await _async_delete(memory_id=mid, user_id=uid, metadata=meta)

    def add(
        self,
        content: str,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ):
        return _run_async(_async_add(content, user_id=user_id, metadata=metadata))

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> dict:
        return _run_async(_async_search(query, filters=filters, limit=limit))

    def delete(
        self,
        memory_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> bool:
        mid = memory_id or kwargs.get("memory_id")
        uid = user_id or kwargs.get("user_id")
        meta = metadata or kwargs.get("metadata")
        return _run_async(_async_delete(memory_id=mid, user_id=uid, metadata=meta))

    def delete_all(self, user_id: str = "") -> bool:
        return _run_async(_async_delete_all(user_id))

    def reset(self) -> bool:
        return _run_async(_async_reset())


# ---------------------------------------------------------------------------
# Module-level singleton and init log
# ---------------------------------------------------------------------------

#: Backward-compatible ``memory`` object — same API as the old Mem0 singleton.
memory: _SyncMemoryShim = _SyncMemoryShim()

audit_info(
    "memory.ltm",
    "pgvector_init",
    embed_model=_embed_model,
    embed_url=_embed_url,
    table="memory_vectors",
)
