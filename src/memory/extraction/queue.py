"""PostgreSQL-backed job queue for async memory extraction.

Replaces the Redis stream (owlynn:memory:extract) with a simple
PostgreSQL table queue using INSERT ON CONFLICT DO NOTHING for dedup
and LISTEN/NOTIFY for efficient wakeup.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_NOTIFY_CHANNEL = "extraction_channel"
_DEDUP: dict[str, Any] = {}


async def enqueue_extraction(payload: dict[str, Any]) -> bool | None:
    """Enqueue a memory extraction job.

    Uses INSERT ... ON CONFLICT DO NOTHING so duplicate turn_ids are
    silently dropped (replaces the in-process _DEDUP dict).

    Returns:
        True — job newly enqueued
        False — already existed (dedup)
        None — Postgres circuit open (explicit skip, not success)
    """
    from sqlalchemy import text

    from src.memory.db_models import ExtractionJob
    from src.memory.postgres_health import (
        is_postgres_available,
        record_postgres_failure,
        record_postgres_success,
    )
    from src.models.db import AsyncSessionLocal

    turn_id: str = str(payload.get("turn_id") or payload.get("job_id") or uuid.uuid4())

    if not is_postgres_available():
        logger.warning(
            "[memory.extract] Skipping enqueue — Postgres circuit open (turn_id=%s)",
            turn_id,
        )
        return None

    try:
        async with AsyncSessionLocal() as session:
            job = ExtractionJob(
                turn_id=turn_id,
                mem0_uid=str(payload.get("mem0_uid", "owner")),
                project_id=str(payload.get("project_id", "default")),
                scenario_id=str(payload.get("scenario_id", "normal")),
                turn_text=str(payload.get("turn_text", "")),
                status="pending",
            )
            # merge handles the ON CONFLICT DO NOTHING equivalent for PK/unique
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(ExtractionJob)
                .values(
                    turn_id=job.turn_id,
                    mem0_uid=job.mem0_uid,
                    project_id=job.project_id,
                    scenario_id=job.scenario_id,
                    turn_text=job.turn_text,
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["turn_id"])
                .returning(ExtractionJob.id)  # type: ignore[call-overload]
            )
            result = await session.execute(stmt)
            row = result.fetchone()
            await session.commit()

            if row is None:
                # Already existed — dedup hit
                record_postgres_success()
                return False

            job_id = row[0]
            # Wake up the worker via LISTEN/NOTIFY
            await session.execute(
                text(f"SELECT pg_notify('{_NOTIFY_CHANNEL}', :job_id)"),
                {"job_id": str(job_id)},
            )
            await session.commit()
            record_postgres_success()
            return True

    except Exception as exc:
        record_postgres_failure()
        logger.warning(
            "[memory.extract] DB enqueue failed: %s — using in-process fallback", exc
        )
        from src.memory.extraction.worker import schedule_extraction_fallback

        schedule_extraction_fallback({**payload, "turn_id": turn_id})
        return True
