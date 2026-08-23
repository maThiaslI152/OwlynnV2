"""Lazy-loaded vision VLM client for vision proxy (Gemma 4 E2B)."""

from __future__ import annotations

import asyncio
import logging
import time

from langchain_openai import ChatOpenAI

from src.agent.core.complex_utils.lm_studio_vision import (
    configured_vision_model_name,
    ensure_vision_vlm_loaded,
)
from src.config.audit_log import audit_debug, audit_info
from src.config.config_loader import config, get_model_config

logger = logging.getLogger(__name__)


class VisionModelManager:
    """Dedicated vision VLM client (Gemma 4 E2B); never falls back to other models."""

    def __init__(self) -> None:
        self._client: ChatOpenAI | None = None
        self._last_used: float = 0.0
        self._inflight: int = 0
        self._idle_seconds = float(config.get("cloud.vision_idle_unload_seconds", 300))
        self._watchdog_task: asyncio.Task | None = None
        self._model_name: str = configured_vision_model_name()

    async def start(self) -> None:
        if self._watchdog_task and not self._watchdog_task.done():
            return
        self._watchdog_task = asyncio.create_task(self._idle_watchdog())

    async def stop(self) -> None:
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
        await self.unload()

    def touch(self) -> None:
        self._last_used = time.monotonic()

    async def acquire(self) -> ChatOpenAI:
        from src.agent.llm import LLMPool, _build_local_llm_client

        if "vision" in LLMPool._test_overrides:
            return LLMPool._test_overrides["vision"]
        if "medium" in LLMPool._test_overrides:
            return LLMPool._test_overrides["medium"]

        self._inflight += 1
        try:
            if self._client is None:
                model_cfg = get_model_config("vision") or get_model_config("small")
                model_name = str(
                    model_cfg.get("model_name") or configured_vision_model_name()
                )

                if not await ensure_vision_vlm_loaded():
                    raise RuntimeError(
                        f"Vision VLM ({model_name}) is not loaded in LM Studio"
                    )

                self._client = _build_local_llm_client(
                    temperature=float(
                        model_cfg.get("temperature")
                        if model_cfg.get("temperature") is not None
                        else config.get("cloud.vision_temperature", 0.1)
                    ),
                    max_tokens=int(config.get("cloud.vision_max_tokens", 2048)),
                    max_output_tokens=int(config.get("cloud.vision_max_tokens", 2048)),
                    timeout=120,
                    model_slot="vision",
                )
                self._model_name = model_name
                audit_info(
                    "agent.model",
                    "vision_proxy_loaded",
                    model=model_name,
                    role="vision_proxy",
                )
            self.touch()
            return self._client
        finally:
            self._inflight -= 1

    @property
    def model_name(self) -> str:
        return self._model_name

    async def unload(self) -> None:
        if self._client is not None:
            audit_debug("agent.model", "vision_proxy_unloaded", reason="idle")
            self._client = None

    async def _idle_watchdog(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                if self._client is None or self._inflight > 0:
                    continue
                if time.monotonic() - self._last_used > self._idle_seconds:
                    await self.unload()
        except asyncio.CancelledError:
            raise


_manager = VisionModelManager()


async def get_vision_llm() -> ChatOpenAI:
    return await _manager.acquire()


def get_vision_proxy_model_name() -> str:
    return _manager.model_name


async def start_vision_manager() -> None:
    await _manager.start()


async def stop_vision_manager() -> None:
    await _manager.stop()
