"""Tests for background-friendly local medium LLM scheduling."""

import asyncio

import pytest

from src.agent.local_llm_scheduler import (
    LocalLLMScheduler,
    wrap_medium_for_foreground,
)


@pytest.fixture(autouse=True)
def _reset_scheduler():
    LocalLLMScheduler._graph_runs = 0
    LocalLLMScheduler._foreground_medium = 0
    yield
    LocalLLMScheduler._graph_runs = 0
    LocalLLMScheduler._foreground_medium = 0


@pytest.mark.asyncio
async def test_wait_for_background_defers_while_graph_active(monkeypatch):
    monkeypatch.setattr(
        "src.agent.local_llm_scheduler.config.get",
        lambda key, default=None: {
            "memory.extraction.idle_cooldown_seconds": 0,
            "memory.extraction.idle_poll_seconds": 0.05,
            "memory.extraction.max_idle_wait_seconds": 0.2,
            "memory.extraction.defer_while_graph_active": True,
        }.get(key, default),
    )

    LocalLLMScheduler.graph_run_started()
    ready = await LocalLLMScheduler.wait_for_background_window()
    assert ready is False


@pytest.mark.asyncio
async def test_wait_for_background_opens_when_idle(monkeypatch):
    monkeypatch.setattr(
        "src.agent.local_llm_scheduler.config.get",
        lambda key, default=None: {
            "memory.extraction.idle_cooldown_seconds": 0,
            "memory.extraction.idle_poll_seconds": 0.01,
            "memory.extraction.max_idle_wait_seconds": 1,
            "memory.extraction.defer_while_graph_active": True,
        }.get(key, default),
    )

    ready = await LocalLLMScheduler.wait_for_background_window()
    assert ready is True


@pytest.mark.asyncio
async def test_foreground_wrapper_tracks_medium_slot():
    calls: list[str] = []

    class FakeClient:
        async def ainvoke(self, input, config=None, **kwargs):
            calls.append("invoke")
            assert await LocalLLMScheduler.foreground_medium_active()
            return "ok"

        def bind(self, **kwargs):
            return self

    wrapped = wrap_medium_for_foreground(FakeClient())  # type: ignore[arg-type]
    assert await wrapped.ainvoke("prompt") == "ok"
    assert calls == ["invoke"]
    assert not await LocalLLMScheduler.foreground_medium_active()


@pytest.mark.asyncio
async def test_background_slot_is_exclusive():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with LocalLLMScheduler.background_medium_slot():
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await asyncio.wait_for(entered.wait(), timeout=1)

    acquired = False

    async def waiter():
        nonlocal acquired
        async with LocalLLMScheduler.background_medium_slot():
            acquired = True

    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0.05)
    assert not acquired

    release.set()
    await asyncio.wait_for(waiter_task, timeout=1)
    assert acquired
    await task
