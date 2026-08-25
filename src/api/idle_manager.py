"""Idle resource manager — unloads LM Studio model and stops StirlingPDF after inactivity.

Config keys (defaults.yaml):
  startup.idle_unload_minutes     — 0 = disabled  (default: 15)
  services.stirling_pdf.idle_shutdown — false by default (opt-in)
  services.stirling_pdf.idle_minutes  — 10
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from src.config.config_loader import config

logger = logging.getLogger(__name__)

# ── Shared state ──────────────────────────────────────────────────────────────
_last_chat_activity: float = time.monotonic()
_last_pdf_activity: float = time.monotonic()
_llm_unloaded: bool = False


def record_activity() -> None:
    """Call on every incoming chat message to reset the idle timer."""
    global _last_chat_activity, _llm_unloaded
    _last_chat_activity = time.monotonic()
    _llm_unloaded = False  # model will be confirmed loaded by ensure_llm_loaded()


def record_pdf_activity() -> None:
    """Call before/after any PDF intake call."""
    global _last_pdf_activity
    _last_pdf_activity = time.monotonic()


# ── LM Studio idle-unload ─────────────────────────────────────────────────────


async def _get_lm_studio_base_url() -> str:
    return config.get_main_model_base_url().rstrip("/")


async def _get_loaded_model_key() -> str | None:
    """Return the model key currently loaded in LM Studio, or None."""
    base = await _get_lm_studio_base_url()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base}/models")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            if models:
                return models[0].get("id")
    except Exception as e:
        logger.debug("LM Studio model check failed: %s", e)
    return None


async def _unload_llm() -> None:
    """Unload the current model from LM Studio to free unified memory."""
    if config.get_models_provider() == "ollama":
        return

    model_key = (
        config.get("models.main.lm_studio_model_key")
        or config.get("models.small.lm_studio_model_key")
        or await _get_loaded_model_key()
    )
    if not model_key:
        logger.debug("[idle] No model loaded, nothing to unload.")
        return
    base = await _get_lm_studio_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(f"{base}/models/{model_key}")
            if resp.status_code in (200, 204):
                logger.info(
                    "[idle] Unloaded LLM '%s' from LM Studio (idle timeout).", model_key
                )
            else:
                logger.debug("[idle] LM Studio unload response: %s", resp.status_code)
    except Exception as e:
        logger.warning("[idle] Failed to unload LLM: %s", e)


async def ensure_llm_loaded() -> None:
    """If the model was unloaded, trigger a reload by sending a tiny ping request.

    LM Studio reloads the model on the first inference request automatically.
    We send a lightweight completions ping with a short timeout so the model
    is warm before the real graph invocation begins.
    """
    if config.get("models.provider", "lm_studio") == "ollama":
        return

    global _llm_unloaded
    if not _llm_unloaded:
        return
    base = await _get_lm_studio_base_url()
    model_key = (
        config.get("models.main.lm_studio_model_key")
        or config.get("models.main.model_name")
        or ""
    )
    try:
        logger.info("[idle] Reloading LLM model '%s' before inference...", model_key)
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(
                f"{base}/completions",
                json={"model": model_key, "prompt": "hi", "max_tokens": 1},
            )
        _llm_unloaded = False
        logger.info("[idle] LLM model reloaded.")
    except Exception as e:
        logger.warning(
            "[idle] LLM reload ping failed (model may still be loading): %s", e
        )


# ── StirlingPDF idle-shutdown ─────────────────────────────────────────────────


async def _container_cli() -> list[str]:
    """Prefer podman when available, else docker."""
    import shutil

    if shutil.which("podman"):
        return ["podman"]
    if shutil.which("docker"):
        return ["docker"]
    return []


async def _stop_stirling() -> None:
    """Stop the owlynn_stirling_pdf container (Podman or Docker)."""
    cli = await _container_cli()
    if not cli:
        logger.warning(
            "[idle] Neither podman nor docker found; cannot stop StirlingPDF."
        )
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            *cli,
            "stop",
            "owlynn_stirling_pdf",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        logger.info(
            "[idle] StirlingPDF container stopped via %s (idle timeout).", cli[0]
        )
    except Exception as e:
        logger.warning("[idle] Failed to stop StirlingPDF: %s", e)


async def ensure_stirling_running() -> None:
    """Start StirlingPDF if idle-shutdown is enabled and the container is stopped.

    Waits up to 10 seconds for the health endpoint to be ready.
    """
    if not config.get("services.stirling_pdf.idle_shutdown", False):
        return
    stirling_url = config.get("external_services.stirling_pdf.url") or config.get(
        "stirlingpdf.url", "http://127.0.0.1:8090"
    )
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{stirling_url}/api/v1/info")
            if resp.status_code < 400:
                return  # Already running
    except Exception:
        pass  # Container is down — start it

    record_pdf_activity()  # reset timer before start
    cli = await _container_cli()
    if not cli:
        logger.warning(
            "[idle] Neither podman nor docker found; cannot start StirlingPDF."
        )
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            *cli,
            "start",
            "owlynn_stirling_pdf",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        logger.info("[idle] Starting StirlingPDF container via %s on-demand...", cli[0])
    except Exception as e:
        logger.warning("[idle] Failed to start StirlingPDF: %s", e)
        return

    # Wait for health
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{stirling_url}/api/v1/info")
                if resp.status_code < 400:
                    logger.info("[idle] StirlingPDF ready.")
                    return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    logger.warning(
        "[idle] StirlingPDF did not become ready within 10s, proceeding anyway."
    )


# ── Background watcher loop ───────────────────────────────────────────────────


async def idle_watcher_loop() -> None:
    """Background task that polls for idle conditions every 60 seconds."""
    global _llm_unloaded

    llm_idle_minutes = int(config.get("startup.idle_unload_minutes", 15))
    stirling_idle_minutes = int(config.get("services.stirling_pdf.idle_minutes", 10))
    stirling_shutdown_enabled = bool(
        config.get("services.stirling_pdf.idle_shutdown", False)
    )

    logger.info(
        "[idle] Watcher started — LLM unload after %dm, StirlingPDF shutdown: %s (%dm)",
        llm_idle_minutes,
        stirling_shutdown_enabled,
        stirling_idle_minutes,
    )

    while True:
        await asyncio.sleep(60)
        now = time.monotonic()

        # ── LLM idle unload ──────────────────────────────────────────────
        if llm_idle_minutes > 0 and not _llm_unloaded:
            idle_secs = now - _last_chat_activity
            if idle_secs >= llm_idle_minutes * 60:
                logger.info(
                    "[idle] %.0f min since last chat — unloading LLM.", idle_secs / 60
                )
                await _unload_llm()
                _llm_unloaded = True

        # ── StirlingPDF idle shutdown ────────────────────────────────────
        if stirling_shutdown_enabled:
            pdf_idle_secs = now - _last_pdf_activity
            if pdf_idle_secs >= stirling_idle_minutes * 60:
                stirling_url = config.get(
                    "external_services.stirling_pdf.url"
                ) or config.get("stirlingpdf.url", "http://127.0.0.1:8090")
                try:
                    async with httpx.AsyncClient(timeout=2) as client:
                        resp = await client.get(f"{stirling_url}/api/v1/info")
                        if resp.status_code < 400:
                            logger.info(
                                "[idle] %.0f min since last PDF — stopping StirlingPDF.",
                                pdf_idle_secs / 60,
                            )
                            await _stop_stirling()
                except Exception:
                    pass  # Already stopped
