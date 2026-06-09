"""R7: web_search aggregate timeout returns user-visible message."""

import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_web_search_aggregate_timeout():
    from src.tools.web_tools import web_search

    async def instant_timeout(coro, timeout):
        if asyncio.iscoroutine(coro):
            coro.close()
        raise asyncio.TimeoutError()

    with patch("src.tools.web_tools.asyncio.wait_for", side_effect=instant_timeout):
        result = await web_search.ainvoke({"query": "test timeout query xyz"})

    assert "timed out" in str(result).lower()
