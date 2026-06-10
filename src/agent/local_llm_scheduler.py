"""Coordinate foreground vs background local medium-LLM usage.

Memory extraction uses Qwen (medium slot) in the background. Foreground agent
paths (complex/simple local fallback) register active medium calls so extraction
defers instead of contending for GPU/CPU on Apple Silicon unified memory.

LM Studio does not expose per-request GPU throttling; defer-until-idle plus
process niceness is the practical mitigation.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from src.config.audit_log import audit_debug, audit_warn
from src.config.config_loader import config

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class LocalLLMScheduler:
    """Tracks active graph runs and foreground medium-LLM calls."""

    _graph_runs: int = 0
    _foreground_medium: int = 0
    _background_sem = asyncio.Semaphore(1)
    _lock = asyncio.Lock()

    @classmethod
    def graph_run_started(cls) -> None:
        cls._graph_runs += 1
        audit_debug(
            "agent.model",
            "graph_run_started",
            active_graph_runs=cls._graph_runs,
        )

    @classmethod
    def graph_run_finished(cls) -> None:
        cls._graph_runs = max(0, cls._graph_runs - 1)
        audit_debug(
            "agent.model",
            "graph_run_finished",
            active_graph_runs=cls._graph_runs,
        )

    @classmethod
    def active_graph_runs(cls) -> int:
        return cls._graph_runs

    @classmethod
    async def foreground_medium_active(cls) -> bool:
        async with cls._lock:
            return cls._foreground_medium > 0

    @classmethod
    @asynccontextmanager
    async def foreground_medium_slot(cls):
        """Held while the agent invokes the local medium (Qwen) model."""
        async with cls._lock:
            cls._foreground_medium += 1
        try:
            yield
        finally:
            async with cls._lock:
                cls._foreground_medium = max(0, cls._foreground_medium - 1)

    @classmethod
    @asynccontextmanager
    async def background_medium_slot(cls):
        """Exclusive slot for one background medium call (memory extraction)."""
        await cls._background_sem.acquire()
        try:
            yield
        finally:
            cls._background_sem.release()

    @classmethod
    async def wait_for_background_window(cls) -> bool:
        """Wait until extraction can safely call the medium LLM.

        Returns True when the wait ended because conditions cleared, False when
        ``max_idle_wait_seconds`` elapsed (caller may proceed with a warning).
        """
        cooldown = float(config.get("memory.extraction.idle_cooldown_seconds", 8))
        poll = float(config.get("memory.extraction.idle_poll_seconds", 2))
        max_wait_raw = config.get("memory.extraction.max_idle_wait_seconds", 600)
        max_wait = float(max_wait_raw) if max_wait_raw is not None else None
        defer_graph = bool(
            config.get("memory.extraction.defer_while_graph_active", True)
        )

        if cooldown > 0:
            await asyncio.sleep(cooldown)

        elapsed = 0.0
        while True:
            async with cls._lock:
                graph_busy = defer_graph and cls._graph_runs > 0
                medium_busy = cls._foreground_medium > 0
                ready = not graph_busy and not medium_busy

            if ready:
                audit_debug(
                    "memory.extract",
                    "background_window_open",
                    waited_seconds=round(elapsed, 1),
                )
                return True

            if max_wait is not None and elapsed >= max_wait:
                audit_warn(
                    "memory.extract",
                    "background_wait_timeout",
                    waited_seconds=round(elapsed, 1),
                    graph_runs=cls._graph_runs,
                    foreground_medium=cls._foreground_medium,
                )
                return False

            await asyncio.sleep(poll)
            elapsed += poll


class _MediumLLMForegroundWrapper:
    """Wraps ChatOpenAI so every ainvoke counts as foreground medium usage."""

    def __init__(self, client: ChatOpenAI):
        self._client = client

    def bind(self, **kwargs: Any):
        return _MediumLLMForegroundWrapper(self._client.bind(**kwargs))

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any):
        async with LocalLLMScheduler.foreground_medium_slot():
            return await self._client.ainvoke(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Any = None, **kwargs: Any):
        async with LocalLLMScheduler.foreground_medium_slot():
            async for chunk in self._client.astream(input, config=config, **kwargs):
                yield chunk

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def wrap_medium_for_foreground(client: ChatOpenAI) -> ChatOpenAI:
    """Return a client that registers foreground medium usage on invoke."""
    return _MediumLLMForegroundWrapper(client)  # type: ignore[return-value]


def _apply_process_nice(delta: int) -> int | None:
    """Lower CPU scheduling priority for background extraction. Returns prior nice."""
    if delta <= 0:
        return None
    try:
        prior = os.nice(0)
        os.nice(delta)
        return prior
    except OSError as exc:
        logger.debug("[memory.extract] process nice unavailable: %s", exc)
        return None


def _restore_process_nice(prior: int | None, delta: int) -> None:
    if prior is None or delta <= 0:
        return
    try:
        os.nice(-delta)
    except OSError:
        pass


async def invoke_medium_background(bound_llm: Any, messages: list) -> Any:
    """Invoke medium LLM for memory extraction with deferral and lower CPU priority."""
    await LocalLLMScheduler.wait_for_background_window()
    nice_delta = int(config.get("memory.extraction.process_nice", 10))

    async with LocalLLMScheduler.background_medium_slot():
        prior_nice = _apply_process_nice(nice_delta)
        try:
            return await bound_llm.ainvoke(messages)
        finally:
            _restore_process_nice(prior_nice, nice_delta)
