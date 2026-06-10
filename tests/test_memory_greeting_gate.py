"""Greeting exchanges must not trigger memory_write."""

from __future__ import annotations

import pytest

from src.agent.nodes.memory import _should_save_memory


@pytest.mark.asyncio
async def test_hi_there_skips_memory_save():
    assert not await _should_save_memory(
        "Hi there!", "Hi there! How can I assist you today?"
    )


@pytest.mark.asyncio
async def test_substantive_exchange_still_saves():
    assert await _should_save_memory(
        "My project codeword is ZEBRA-42 and we use FastAPI.",
        "Noted — ZEBRA-42 with FastAPI backend.",
    )
