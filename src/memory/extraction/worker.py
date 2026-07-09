"""Background memory extraction worker (8B custom prompt → Qdrant via Mem0)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.pii_scrubber import scrub_for_storage
from src.config.audit_log import audit_debug, audit_info, audit_warn
from src.config.config_loader import config
from src.memory.extraction.prompts import build_extraction_messages
from src.memory.extraction.queue import CONSUMER_GROUP, STREAM_KEY
from src.memory.extraction.schema import parse_extraction_response
from src.config.settings import REDIS_URL

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None
_fallback_tasks: set[asyncio.Task] = set()


def schedule_extraction_fallback(payload: dict[str, Any]) -> None:
    """In-process fallback when Redis is unavailable."""
    task = asyncio.create_task(process_extraction_job(payload))
    _fallback_tasks.add(task)
    task.add_done_callback(_fallback_tasks.discard)


async def start_extraction_worker() -> None:
    """Start Redis stream consumer (idempotent)."""
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
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning(
            "[memory.extract] redis package unavailable — worker not started"
        )
        return

    consumer = f"owlynn-{id(asyncio.get_running_loop())}"
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        try:
            await client.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True
            )
        except Exception:
            pass

        while True:
            try:
                from src.api.power_monitor import ECO_MODE

                if ECO_MODE:
                    await asyncio.sleep(60)
                    continue
            except ImportError:
                pass

            entries = await client.xreadgroup(
                CONSUMER_GROUP,
                consumer,
                {STREAM_KEY: ">"},
                count=1,
                block=5000,
            )
            if not entries:
                continue
            for _stream, messages in entries:
                for msg_id, fields in messages:
                    raw = fields.get("payload", "{}")
                    try:
                        payload = json.loads(raw)
                        await process_extraction_job(payload)
                        await client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                    except Exception as exc:
                        audit_warn(
                            "memory.extract",
                            "job_failed",
                            reason=str(exc)[:160],
                            msg_id=msg_id,
                        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("[memory.extract] consumer stopped: %s", exc)
    finally:
        await client.aclose()


async def process_extraction_job(payload: dict[str, Any]) -> None:
    """PII scrub → 8B extract → validate → Mem0 store."""
    turn_text = str(payload.get("turn_text", "")).strip()
    if not turn_text:
        return

    # Safety net: skip pentest turns (memory_write_node should already filter)
    scenario_id = payload.get("scenario_id")
    if scenario_id == "pentest":
        audit_debug("memory.extract", "pentest_skipped", reason="pentest_scenario")
        return

    scrubbed, redactions = scrub_for_storage(turn_text)
    scenario_id = payload.get("scenario_id")
    mem0_uid = str(payload.get("mem0_uid", "owner"))
    project_id = payload.get("project_id", "default")

    from src.agent.llm import get_extraction_llm
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

    from src.memory.long_term import memory

    if memory is None:
        audit_warn("memory.extract", "mem0_unavailable")
        return

    from src.agent.llm import get_small_llm
    from langchain_core.messages import HumanMessage

    small_llm = await get_small_llm()
    saved = 0

    for atom in atoms:
        content = atom["content"]

        try:
            results_dict = await asyncio.to_thread(
                lambda: memory.search(
                    content[:200], filters={"user_id": mem0_uid}, limit=3
                )
            )
            existing_results = (
                results_dict.get("results", [])
                if isinstance(results_dict, dict)
                else results_dict
            )
        except Exception:
            existing_results = []

        existing_facts = [
            (r.get("id"), r.get("memory") or r.get("text", ""))
            for r in existing_results
            if isinstance(r, dict)
        ]

        should_add = True
        if existing_facts:
            facts_str = "\n".join(
                [f"ID: {fid}\nFact: {ftext}" for fid, ftext in existing_facts]
            )
            prompt = (
                f"New fact: {content}\n\nExisting facts:\n{facts_str}\n\n"
                "Compare the new fact to the existing facts. Output one of the following exact commands:\n"
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
                        await asyncio.to_thread(memory.delete, parts[1])
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
            await asyncio.to_thread(
                memory.add, content, user_id=mem0_uid, metadata=metadata, infer=False
            )
            saved += 1

    audit_info(
        "memory.extract",
        "atoms_saved",
        count=saved,
        redactions=redactions,
        scenario_id=scenario_id or "",
    )
