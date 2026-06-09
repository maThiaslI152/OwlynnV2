"""Lazy-loaded local VLM client for vision proxy."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from langchain_openai import ChatOpenAI

from src.config.audit_log import audit_debug, audit_info
from src.config.config_loader import config, get_model_config

logger = logging.getLogger(__name__)


class VisionModelManager:
    """Load VLM on first image; drop reference after idle timeout."""

    def __init__(self) -> None:
        self._client: Optional[ChatOpenAI] = None
        self._last_used: float = 0.0
        self._inflight: int = 0
        self._idle_seconds = float(config.get("cloud.vision_idle_unload_seconds", 300))
        self._watchdog_task: asyncio.Task | None = None

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
        from src.agent.llm import LLMPool

        if "medium" in LLMPool._test_overrides:
            return LLMPool._test_overrides["medium"]

        self._inflight += 1
        try:
            if self._client is None:
                model_cfg = get_model_config("medium", "vision")
                extra_body = dict(model_cfg.get("extra_body") or {})
                extra_body["max_output_tokens"] = int(
                    config.get("cloud.vision_max_tokens", 2048)
                )
                self._client = ChatOpenAI(
                    model=model_cfg.get("model_name", "qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k"),
                    api_key="sk-local-no-key-needed",
                    base_url=model_cfg.get("base_url", "http://127.0.0.1:1234/v1"),
                    temperature=float(config.get("cloud.vision_temperature", 0.1)),
                    max_tokens=int(config.get("cloud.vision_max_tokens", 2048)),
                    extra_body=extra_body,
                    request_timeout=model_cfg.get("request_timeout")
                    or model_cfg.get("timeout", 120),
                    stream_chunk_timeout=None,
                )
                audit_info(
                    "agent.model",
                    "vision_proxy_loaded",
                    model=model_cfg.get("model_name"),
                )
            self.touch()
            return self._client
        finally:
            self._inflight -= 1

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


async def start_vision_manager() -> None:
    await _manager.start()


async def stop_vision_manager() -> None:
    await _manager.stop()
