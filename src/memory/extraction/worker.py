"""Background memory extraction worker — PostgreSQL queue backend.

Replaces the Redis xreadgroup consumer loop with:
  - LISTEN/NOTIFY for efficient wakeup
  - SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent processing
  - Proper retry tracking and DLQ behaviour (retry_count, status=failed)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.pii_scrubber import scrub_for_storage
from src.config.audit_log import audit_debug, audit_info, audit_warn
from src.config.config_loader import config
from src.memory.extraction.prompts import build_extraction_messages
from src.memory.extraction.schema import parse_extraction_response

logger = logging.getLogger(__name__)

_NOTIFY_CHANNEL = "extraction_channel"
_MAX_RETRIES = 3
_POLL_INTERVAL_S = 30  # fallback poll when LISTEN is idle
_worker_task: asyncio.Task | None = None
_fallback_tasks: set[asyncio.Task] = set()


def schedule_extraction_fallback(payload: dict[str, Any]) -> None:
    """In-process fallback when DB enqueue fails (e.g., during tests)."""
    task = asyncio.create_task(process_extraction_job(payload))
    _fallback_tasks.add(task)
    task.add_done_callback(_fallback_tasks.discard)


async def start_extraction_worker() -> None:
    """Start the PostgreSQL-backed extraction worker (idempotent)."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_consumer_loop())


async def stop_extraction_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None


async def _consumer_loop() -> None:
    """Main consume loop: LISTEN for notifications, poll as fallback."""
    try:
        import asyncpg  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("[memory.extract] asyncpg not available — worker not started")
        return

    from src.models.db import DATABASE_URL

    # Build a raw asyncpg DSN from the SQLAlchemy URL
    raw_dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(raw_dsn)
        await conn.add_listener(_NOTIFY_CHANNEL, _on_notify)
        logger.info("[memory.extract] PostgreSQL LISTEN started on channel '%s'", _NOTIFY_CHANNEL)

        while True:
            try:
                from src.api.power_monitor import ECO_MODE  # type: ignore[import-untyped]

                if ECO_MODE:
                    await asyncio.sleep(60)
                    continue
            except ImportError:
                pass

            # Poll for any missed pending jobs (handles crash recovery & fallback)
            await _drain_pending_jobs()

            # Wait up to _POLL_INTERVAL_S for a NOTIFY or timeout
            await asyncio.sleep(_POLL_INTERVAL_S)

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("[memory.extract] worker stopped: %s", exc)
    finally:
        if conn:
            try:
                await conn.remove_listener(_NOTIFY_CHANNEL, _on_notify)
                await conn.close()
            except Exception:
                pass


def _on_notify(connection: Any, pid: int, channel: str, payload: str) -> None:
    """Called by asyncpg when a NOTIFY arrives — triggers an immediate drain."""
    asyncio.create_task(_drain_pending_jobs())


async def _drain_pending_jobs() -> None:
    """Claim and process all pending jobs using FOR UPDATE SKIP LOCKED."""
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from src.memory.db_models import ExtractionJob
    from src.models.db import AsyncSessionLocal
    from src.agent.model_swap import IS_PENTEST_SWAPPED

    if IS_PENTEST_SWAPPED:
        return

    try:
        async with AsyncSessionLocal() as session:
            # Claim one job atomically
            stmt = (
                select(ExtractionJob)
                .where(
                    ExtractionJob.status == "pending",
                    ExtractionJob.retry_count < _MAX_RETRIES,
                )
                .order_by(ExtractionJob.enqueued_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            if job is None:
                return

            # Mark as processing
            job.status = "processing"
            await session.commit()
            job_id = job.id

        # Execute outside the lock so we don't hold it during LLM call
        payload = {
            "turn_id": job.turn_id,
            "turn_text": job.turn_text,
            "mem0_uid": job.mem0_uid,
            "project_id": job.project_id,
            "scenario_id": job.scenario_id,
        }
        try:
            await process_extraction_job(payload)
            status, error = "done", None
        except Exception as exc:
            status, error = "failed", str(exc)[:500]
            audit_warn(
                "memory.extract",
                "job_failed",
                job_id=job_id,
                retry_count=job.retry_count,
                reason=error,
            )

        # Update final status
        async with AsyncSessionLocal() as session:
            from datetime import datetime, timezone

            await session.execute(
                update(ExtractionJob)
                .where(ExtractionJob.id == job_id)
                .values(
                    status=status if status == "done" or job.retry_count + 1 >= _MAX_RETRIES else "pending",
                    retry_count=job.retry_count + 1,
                    error=error,
                    processed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        # Recursively drain more pending jobs
        await _drain_pending_jobs()

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("[memory.extract] drain error: %s", exc)


async def process_extraction_job(payload: dict[str, Any]) -> None:
    """PII scrub → 8B extract → validate → pgvector store."""
    turn_text = str(payload.get("turn_text", "")).strip()
    if not turn_text:
        return

    # Safety net: skip pentest turns (memory_write_node should already filter)
    scenario_id = payload.get("scenario_id")
    if scenario_id == "pentest":
        audit_debug("memory.extract", "pentest_skipped", reason="pentest_scenario")
        return

    scrubbed, redactions = scrub_for_storage(turn_text)
    mem0_uid = str(payload.get("mem0_uid", "owner"))
    project_id = payload.get("project_id", "default")

    from src.agent.llm import get_extraction_llm, get_small_llm
    from src.agent.local_llm_scheduler import invoke_medium_background

    messages_spec = build_extraction_messages(scrubbed, scenario_id)
    llm = await get_extraction_llm(foreground=False)
    bound = llm.bind(
        temperature=float(config.get("memory.extraction.temperature", 0.1)),
        max_tokens=int(config.get("memory.extraction.max_tokens", 1024)),
    )
    response = await invoke_medium_background(
        bound,
        [
            SystemMessage(content=messages_spec[0]["content"]),
            HumanMessage(content=messages_spec[1]["content"]),
        ],
    )
    atoms = parse_extraction_response(str(response.content or ""))
    if not atoms:
        audit_info("memory.extract", "no_atoms", redactions=redactions)
        return

    from src.memory.long_term import LongTermMemory

    ltm = LongTermMemory()
    small_llm = await get_small_llm()
    saved = 0

    for atom in atoms:
        content = atom["content"]

        # Semantic dedup: search for similar existing memories
        existing_results = await ltm.search(
            content[:200], filters={"user_id": mem0_uid}, limit=3
        )
        existing_facts = [
            (r.get("id"), r.get("memory", ""))
            for r in existing_results.get("results", [])
            if isinstance(r, dict)
        ]

        should_add = True
        if existing_facts:
            facts_str = "\n".join(
                [f"ID: {fid}\nFact: {ftext}" for fid, ftext in existing_facts]
            )
            prompt = (
                f"New fact: {content}\n\nExisting facts:\n{facts_str}\n\n"
                "Compare the new fact to the existing facts. Output one of:\n"
                "1. REDUNDANT - if the new fact is already covered.\n"
                "2. NEW - if it is completely new.\n"
                "3. DELETE <ID> - if the new fact supersedes the old one."
            )
            resp = await small_llm.ainvoke([HumanMessage(content=prompt)])
            decision = str(resp.content).strip()

            if decision.startswith("REDUNDANT"):
                should_add = False
            elif decision.startswith("DELETE"):
                parts = decision.split(" ")
                if len(parts) >= 2:
                    try:
                        await ltm.delete(parts[1])
                    except Exception:
                        pass

        if should_add:
            metadata = {
                "tier": atom["tier"],
                "format": atom["format"],
                "tags": atom["tags"],
                "confidence": atom["confidence"],
                "source": atom["source"],
                "scenario_id": scenario_id or "",
                "project_id": project_id,
            }
            await ltm.add(content, user_id=mem0_uid, metadata=metadata)
            saved += 1

    audit_info(
        "memory.extract",
        "atoms_saved",
        count=saved,
        redactions=redactions,
        scenario_id=scenario_id or "",
    )
