"""Ensure Florence-2 is the active LM Studio model for vision_proxy OCR."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from src.config.config_loader import config

logger = logging.getLogger(__name__)

_LOAD_POLL_INTERVAL_S = 2.0


def configured_florence_model_name() -> str:
    """OpenAI-compatible model id used in /v1/chat/completions."""
    return str(
        config.get("models.vision_proxy.model_name", "florence-2-base-nsfw-v2-ext-mlx")
    )


def configured_florence_lm_studio_key() -> str:
    """Native LM Studio catalog key for /api/v1/models/load."""
    override = config.get("models.vision_proxy.lm_studio_model_key")
    if override:
        return str(override)
    return configured_florence_model_name()


def lm_studio_management_base() -> str:
    return str(
        config.get(
            "external_services.lm_studio.management_url",
            "http://127.0.0.1:1234",
        )
    ).rstrip("/")


def _model_key_matches_florence(key: str, *, expected: str) -> bool:
    k = (key or "").lower()
    e = expected.lower()
    return e in k or k in e or "florence" in k


def _find_florence_catalog_entry(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    expected = configured_florence_lm_studio_key()
    for entry in models:
        key = str(entry.get("key") or "")
        if _model_key_matches_florence(key, expected=expected):
            return entry
    return None


def _loaded_instance_ids(entry: dict[str, Any]) -> list[str]:
    return [
        str(inst.get("id"))
        for inst in (entry.get("loaded_instances") or [])
        if isinstance(inst, dict) and inst.get("id")
    ]


async def fetch_lm_studio_catalog(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get(
        f"{lm_studio_management_base()}/api/v1/models",
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return list(data.get("models") or [])


async def is_florence_loaded(client: httpx.AsyncClient | None = None) -> bool:
    """True when Florence has at least one loaded instance in LM Studio."""
    owns = client is None
    if owns:
        client = httpx.AsyncClient()
    try:
        catalog = await fetch_lm_studio_catalog(client)
        entry = _find_florence_catalog_entry(catalog)
        return bool(entry and _loaded_instance_ids(entry))
    except Exception as exc:
        logger.debug("[vision_florence] loaded check failed: %s", exc)
        return False
    finally:
        if owns:
            await client.aclose()


async def ensure_florence_loaded() -> bool:
    """
    Load Florence-2 in LM Studio if auto-load is enabled and it is not active.

    Vision proxy must never run against Qwen/MiniCPM weights — only Florence OCR.
    """
    if await is_florence_loaded():
        return True
    if not config.get("cloud.vision_lm_studio_auto_load", True):
        return False

    expected_key = configured_florence_lm_studio_key()
    load_timeout = float(config.get("cloud.vision_lm_studio_load_timeout", 120))
    deadline = time.monotonic() + load_timeout

    async with httpx.AsyncClient() as client:
        try:
            catalog = await fetch_lm_studio_catalog(client)
        except Exception as exc:
            logger.warning("[vision_florence] LM Studio catalog unavailable: %s", exc)
            return False

        entry = _find_florence_catalog_entry(catalog)
        if entry is None:
            logger.error(
                "[vision_florence] Florence not in LM Studio catalog (expected %s)",
                expected_key,
            )
            return False

        model_key = str(entry.get("key") or expected_key)
        logger.info("[vision_florence] Loading %s for vision_proxy OCR…", model_key)
        try:
            resp = await client.post(
                f"{lm_studio_management_base()}/api/v1/models/load",
                json={"model": model_key},
                timeout=load_timeout,
            )
        except Exception as exc:
            logger.warning("[vision_florence] Load request failed: %s", exc)
            return False

        if resp.status_code not in (200, 201, 202):
            logger.warning(
                "[vision_florence] Load rejected (%s): %s",
                resp.status_code,
                resp.text[:200],
            )
            return False

        while time.monotonic() < deadline:
            if await is_florence_loaded(client):
                logger.info("[vision_florence] Load complete: %s", model_key)
                return True
            await asyncio.sleep(_LOAD_POLL_INTERVAL_S)

    logger.warning("[vision_florence] Timed out waiting for %s to load", expected_key)
    return False
