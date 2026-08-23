"""
Cross-Session Memory Manager (STM)
-----------------------------------
Persists important facts across chat sessions in the ``memories`` PostgreSQL
table (replaces data/memories.json).
The agent calls save_memory() to store, search_memories() to retrieve.
"""

import logging
import re
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

from sqlalchemy import delete, func, select

from src.config.audit_log import audit_debug, audit_info
from src.config.config_loader import config
from src.memory.db_models import Memory
from src.models.db import AsyncSessionLocal

_MAX_MEMORIES = int(config.get("memory.max_facts", 200))
_SEARCH_WINDOW = int(config.get("memory.search_window", 50))


async def load_memories() -> list[dict]:
    """Load all memories from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Memory).order_by(Memory.id))
        rows = result.scalars().all()
    return [
        {"fact": m.fact, "timestamp": m.created_at.isoformat() if m.created_at else ""}
        for m in rows
    ]


async def save_memory(fact: str) -> str:
    """Save a new fact/memory to persistent storage. Returns confirmation string."""
    fact = fact.strip()
    if not fact:
        return "Empty fact — nothing saved."

    async with AsyncSessionLocal() as session:
        # Avoid exact duplicates (case-insensitive)
        existing = await session.execute(
            select(Memory).where(func.lower(Memory.fact) == fact.lower())
        )
        if existing.scalar_one_or_none() is not None:
            total = await session.scalar(select(func.count()).select_from(Memory))
            audit_debug("memory.stm", "save_skipped_duplicate", total_count=total)
            return f"Memory already exists: '{fact}'"

        # Check current count for cap enforcement
        total_before = await session.scalar(select(func.count()).select_from(Memory))

        new_mem = Memory(fact=fact, created_at=datetime.now(tz=UTC))
        session.add(new_mem)
        await session.flush()  # get auto-assigned id

        capped = False
        if total_before and total_before >= _MAX_MEMORIES:
            capped = True
            # Remove the oldest records to stay within the cap
            excess = total_before - _MAX_MEMORIES + 1
            oldest_rows = (
                (
                    await session.execute(
                        select(Memory).order_by(Memory.id).limit(excess)
                    )
                )
                .scalars()
                .all()
            )
            oldest_ids = [m.id for m in oldest_rows]
            if oldest_ids:
                await session.execute(delete(Memory).where(Memory.id.in_(oldest_ids)))

        await session.commit()

    total_after = await _count_memories()
    audit_info(
        "memory.stm",
        "saved",
        total_count=total_after,
        was_dedup=False,
        was_capped=capped,
        removed=capped,
    )
    return f"✅ Remembered: '{fact}'"


async def search_memories(query: str, top_k: int = 8) -> list[dict]:
    """
    Keyword-overlap search over the most recent _SEARCH_WINDOW memories.
    Returns up to top_k matches sorted by relevance, falling back to
    the most recent memories when no keyword match is found.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Memory).order_by(Memory.id))
        rows = result.scalars().all()

    memories = [
        {"fact": m.fact, "timestamp": m.created_at.isoformat() if m.created_at else ""}
        for m in rows
    ]

    if not memories:
        return []

    query_words = set(re.findall(r"\w+", query.lower(), re.UNICODE))
    window = memories[-_SEARCH_WINDOW:] if len(memories) > _SEARCH_WINDOW else memories

    scored = []
    for m in window:
        fact_words = set(re.findall(r"\w+", m.get("fact", "").lower(), re.UNICODE))
        overlap = len(query_words & fact_words)
        if overlap > 0:
            scored.append((overlap, m))

    if scored:
        scored.sort(key=lambda x: -x[0])
        result_list = [m for _, m in scored[:top_k]]
        audit_debug(
            "memory.stm",
            "searched",
            query_word_count=len(query_words),
            match_count=len(result_list),
            total_count=len(memories),
        )
        return result_list

    # Fallback: most recent
    result_list = window[-top_k:]
    audit_debug(
        "memory.stm",
        "searched_fallback",
        query_word_count=len(query_words),
        match_count=0,
        total_count=len(memories),
    )
    return result_list


async def delete_memory(fact: str) -> bool:
    """Remove a specific fact from memories. Returns True if removed."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Memory).where(Memory.fact == fact))
        target = result.scalar_one_or_none()
        if target is not None:
            before = await session.scalar(select(func.count()).select_from(Memory))
            await session.delete(target)
            await session.commit()
            after = before - 1
            audit_info("memory.stm", "deleted", total_before=before, total_after=after)
            return True

    total = await _count_memories()
    audit_debug("memory.stm", "delete_not_found", total_count=total)
    return False


# ── Internal helpers ────────────────────────────────────────────────────────


async def _count_memories() -> int:
    """Return current row count for audit logging."""
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(Memory)) or 0
