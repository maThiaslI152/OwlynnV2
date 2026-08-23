"""LM Studio model swap for pentest mode.

Unloads the main model (google/gemma-4-26b-a4b-qat) and loads the pentest model
(Gemma 4 12B Coder) when entering pentest mode. Reverses on exit.

LM Studio API:
- GET  /api/v1/models        — catalog with loaded_instances
- POST /api/v1/models/load   — {"model": "<key>"}
- POST /api/v1/models/unload — {"model": "<key>"}
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from src.config.config_loader import config

logger = logging.getLogger(__name__)

_LOAD_TIMEOUT_S = 120.0
_POLL_INTERVAL_S = 2.0

IS_PENTEST_SWAPPED = False


def _management_base() -> str:
    return str(
        config.get(
            "external_services.lm_studio.management_url", "http://127.0.0.1:1234"
        )
    ).rstrip("/")


def _main_model_key() -> str:
    """LM Studio catalog key for the main model."""
    override = config.get("models.main.lm_studio_model_key")
    if override:
        return str(override)
    return config.get_main_model_name()


_small_model_key = _main_model_key


def _pentest_model_key() -> str:
    """LM Studio catalog key for the pentest model (Gemma 4 12B)."""
    override = config.get("models.pentest.lm_studio_model_key")
    if override:
        return str(override)
    return config.get_pentest_model_name()


async def _get_catalog(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(f"{_management_base()}/api/v1/models", timeout=15.0)
    resp.raise_for_status()
    return list(resp.json().get("models") or [])


def _is_loaded(entry: dict) -> bool:
    instances = entry.get("loaded_instances") or []
    return any(isinstance(i, dict) and i.get("id") for i in instances)


def _find_entry(catalog: list[dict], key: str) -> dict | None:
    key_lower = key.lower()
    # 1. Exact match
    for entry in catalog:
        entry_key = str(entry.get("key") or "").lower()
        if entry_key == key_lower:
            return entry
    # 2. Substring match
    for entry in catalog:
        entry_key = str(entry.get("key") or "").lower()
        if key_lower in entry_key or entry_key in key_lower:
            return entry
    return None


async def _unload_model(client: httpx.AsyncClient, key: str) -> bool:
    """Unload a model. Returns True if unloaded or already unloaded."""
    try:
        # Get instance_id from catalog (LM Studio requires it)
        catalog = await _get_catalog(client)
        entry = _find_entry(catalog, key)
        if not entry:
            logger.info("[model_swap] Model not in catalog, nothing to unload: %s", key)
            return True  # Already unloaded
        instances = entry.get("loaded_instances") or []
        if not instances:
            logger.info("[model_swap] Model already unloaded: %s", key)
            return True
        instance_id = instances[0].get("id") if isinstance(instances[0], dict) else None
        payload: dict = {"model": key}
        if instance_id:
            payload["instance_id"] = instance_id
        resp = await client.post(
            f"{_management_base()}/api/v1/models/unload",
            json=payload,
            timeout=30.0,
        )
        if resp.status_code in (200, 201, 202):
            logger.info("[model_swap] Unloaded: %s", key)
            return True
        logger.warning(
            "[model_swap] Unload rejected (%s): %s", resp.status_code, resp.text[:200]
        )
        return False
    except Exception as e:
        logger.warning("[model_swap] Unload failed: %s", e)
        return False


async def _load_model(client: httpx.AsyncClient, key: str) -> bool:
    """Load a model and wait until it has a loaded instance."""
    deadline = time.monotonic() + _LOAD_TIMEOUT_S
    try:
        load_payload = {
            "model": key,
            "flash_attention": True,
            "speculative_draft_simple": False,
            "speculative_draft_model": "",
        }
        resp = await client.post(
            f"{_management_base()}/api/v1/models/load",
            json=load_payload,
            timeout=_LOAD_TIMEOUT_S,
        )
        if resp.status_code not in (200, 201, 202):
            logger.warning(
                "[model_swap] Load rejected (%s): %s", resp.status_code, resp.text[:200]
            )
            return False
    except Exception as e:
        logger.warning("[model_swap] Load request failed: %s", e)
        return False

    # Poll until loaded
    while time.monotonic() < deadline:
        try:
            catalog = await _get_catalog(client)
            entry = _find_entry(catalog, key)
            if not entry:
                logger.warning(
                    "[model_swap] Model key '%s' not found in LM Studio catalog", key
                )
                return False
            if _is_loaded(entry):
                logger.info("[model_swap] Loaded: %s", key)
                return True
        except Exception:
            pass
        await asyncio.sleep(_POLL_INTERVAL_S)

    logger.warning("[model_swap] Timed out waiting for %s to load", key)
    return False


async def swap_to_pentest() -> dict:
    """Swap from default model to pentest model.

    Returns {"ok": bool, "message": str}.
    """
    main_key = _main_model_key()
    pentest_key = _pentest_model_key()

    global IS_PENTEST_SWAPPED
    IS_PENTEST_SWAPPED = True

    if config.get("models.provider", "lm_studio") == "ollama":
        return {"ok": True, "message": "Using Ollama (auto-loads models on demand)."}

    async with httpx.AsyncClient() as client:
        # Check if unified model (same model for main and pentest)
        if main_key == pentest_key:
            catalog = await _get_catalog(client)
            entry = _find_entry(catalog, pentest_key)
            if entry and _is_loaded(entry):
                return {
                    "ok": True,
                    "message": f"Unified model active: {pentest_key}",
                }
            if await _load_model(client, pentest_key):
                return {"ok": True, "message": f"Unified model loaded: {pentest_key}"}
            return {
                "ok": False,
                "message": f"Failed to load unified model: {pentest_key}",
            }

        # Check current state
        catalog = await _get_catalog(client)
        pentest_entry = _find_entry(catalog, pentest_key)
        if pentest_entry and _is_loaded(pentest_entry):
            return {
                "ok": True,
                "message": f"Pentest model already loaded: {pentest_key}",
            }

        # Unload main model first (free VRAM)
        main_entry = _find_entry(catalog, main_key)
        if main_entry and _is_loaded(main_entry):
            await _unload_model(client, main_key)
            # Brief pause for VRAM release
            await asyncio.sleep(2.0)

        # Load pentest model
        if await _load_model(client, pentest_key):
            return {"ok": True, "message": f"Swapped to pentest model: {pentest_key}"}
        return {"ok": False, "message": f"Failed to load pentest model: {pentest_key}"}


async def swap_to_default() -> dict:
    """Swap from pentest model back to default model.

    Returns {"ok": bool, "message": str}.
    """
    main_key = _main_model_key()
    pentest_key = _pentest_model_key()

    global IS_PENTEST_SWAPPED
    IS_PENTEST_SWAPPED = False

    if config.get("models.provider", "lm_studio") == "ollama":
        return {"ok": True, "message": "Using Ollama (auto-loads models on demand)."}

    async with httpx.AsyncClient() as client:
        # Check if unified model (same model for main and pentest)
        if main_key == pentest_key:
            catalog = await _get_catalog(client)
            entry = _find_entry(catalog, main_key)
            if entry and _is_loaded(entry):
                return {"ok": True, "message": f"Unified model active: {main_key}"}
            if await _load_model(client, main_key):
                return {"ok": True, "message": f"Unified model loaded: {main_key}"}
            return {
                "ok": False,
                "message": f"Failed to load unified model: {main_key}",
            }

        # Check current state
        catalog = await _get_catalog(client)
        main_entry = _find_entry(catalog, main_key)
        if main_entry and _is_loaded(main_entry):
            return {"ok": True, "message": f"Default model already loaded: {main_key}"}

        # Unload pentest model first
        pentest_entry = _find_entry(catalog, pentest_key)
        if pentest_entry and _is_loaded(pentest_entry):
            await _unload_model(client, pentest_key)
            await asyncio.sleep(2.0)

        # Load default model
        if await _load_model(client, main_key):
            return {"ok": True, "message": f"Swapped to default model: {main_key}"}
        return {"ok": False, "message": f"Failed to load default model: {main_key}"}
