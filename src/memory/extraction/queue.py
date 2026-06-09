"""Redis stream queue for async memory extraction jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from src.config.settings import REDIS_URL

logger = logging.getLogger(__name__)

STREAM_KEY = "owlynn:memory:extract"
CONSUMER_GROUP = "owlynn-extractors"
_DEDUP: dict[str, float] = {}
_DEDUP_TTL_S = 86_400


def _dedup_key(payload: dict[str, Any]) -> str:
    return str(payload.get("turn_id") or payload.get("job_id") or uuid.uuid4())


async def enqueue_extraction(payload: dict[str, Any]) -> bool:
    """Enqueue a memory extraction job. Returns True if queued."""
    key = _dedup_key(payload)
    if key in _DEDUP:
        return False
    _DEDUP[key] = asyncio.get_running_loop().time()

    body = json.dumps({**payload, "turn_id": key})
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.xadd(STREAM_KEY, {"payload": body})
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "[memory.extract] Redis enqueue failed: %s — using in-process fallback", exc
        )
        from src.memory.extraction.worker import schedule_extraction_fallback

        schedule_extraction_fallback(payload)
        return True
