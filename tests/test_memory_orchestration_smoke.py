"""Automated end-to-end smoke tests for Phase 1 memory orchestration."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.modules.setdefault("mem0", MagicMock())

from src.agent.nodes.memory import (
    memory_inject_lite_node,
    memory_retrieve_node,
    memory_write_node,
)
from src.agent.routing.router import router_node
from src.agent.core.state import AgentState
from src.memory.extraction.queue import STREAM_KEY, enqueue_extraction
from src.memory.extraction.worker import process_extraction_job

PENTEST_QUERY = "Explain OWASP Top 10 for our pentest engagement"
HUMAN_TURN = "Remember my preferred AWS region is ap-southeast-1 for all deployments"
AI_TURN = "I will remember ap-southeast-1 as your preferred AWS region for deployments."

FAKE_ATOMS_JSON = json.dumps(
    {
        "atoms": [
            {
                "tier": "L1",
                "format": "jsdoc",
                "content": "/** @fact preferred_region ap-southeast-1 */",
                "tags": ["infra"],
                "confidence": 0.95,
            }
        ]
    }
)


@pytest.fixture
def pentest_state() -> AgentState:
    return {
        "messages": [HumanMessage(content=PENTEST_QUERY)],
        "thread_id": "memory-smoke-1",
        "project_id": "default",
        "persona_id": "default",
        "web_search_enabled": True,
    }


@pytest.fixture
def mock_extractor_llm():
    bound = MagicMock()
    bound.ainvoke = AsyncMock(return_value=AIMessage(content=FAKE_ATOMS_JSON))
    llm = MagicMock()
    llm.bind = MagicMock(return_value=bound)
    return llm


@pytest.fixture(autouse=True)
def clear_extraction_dedup():
    from src.memory.extraction import queue as q

    q._DEDUP.clear()
    yield
    q._DEDUP.clear()


@pytest.fixture(autouse=True)
def clear_memory_cache():
    from src.agent.nodes.memory import MemoryContextCache

    MemoryContextCache._cache.clear()
    yield
    MemoryContextCache._cache.clear()


@pytest.mark.anyio
async def test_memory_pipeline_lite_router_retrieve_write(
    pentest_state, mock_extractor_llm
):
    """Full inject → route → retrieve → write → extraction worker path."""
    with patch("src.memory.long_term.memory") as mock_mem:
        mock_mem.search = MagicMock()
        lite = await memory_inject_lite_node(pentest_state)
        mock_mem.search.assert_not_called()

    state = {**pentest_state, **lite}

    with patch("src.agent.routing.router._check_cloud_available", return_value=False):
        with patch(
            "src.agent.routing.router._memory_gate_fields",
            return_value={"needs_memory_retrieval": True, "scenario_id": "pentest"},
        ):
            routed = await router_node(state)

    assert routed["route"] == "complex-cloud"
    assert routed.get("needs_memory_retrieval") is True
    assert routed.get("scenario_id") == "pentest"

    state = {**state, **routed}

    with patch("src.memory.long_term.memory") as mock_mem:
        mock_mem.search = MagicMock(
            return_value=[{"memory": "User prefers ap-southeast-1 region"}]
        )
        with patch(
            "src.agent.nodes.memory._is_semantically_similar",
            AsyncMock(return_value=False),
        ):
            retrieved = await memory_retrieve_node(state)
        mock_mem.search.assert_called()

    ctx = retrieved.get("memory_context", "")
    assert "pentest" in ctx.lower()
    assert "ap-southeast-1" in ctx

    state = {
        **state,
        **retrieved,
        "messages": [
            HumanMessage(content=HUMAN_TURN),
            AIMessage(content=AI_TURN),
        ],
    }

    with patch(
        "src.memory.extraction.queue.enqueue_extraction",
        AsyncMock(return_value=True),
    ) as enq:
        with patch("src.memory.long_term.memory", MagicMock()):
            written = await memory_write_node(state)

    assert enq.await_count == 1
    assert written.get("memory_invalidated") is True
    payload = enq.await_args.args[0]
    assert payload.get("turn_text")
    assert "ap-southeast-1" in payload["turn_text"]

    mock_mem = MagicMock()
    mock_mem.add = MagicMock()
    with patch(
        "src.agent.llm.get_extraction_llm", AsyncMock(return_value=mock_extractor_llm)
    ):
        with patch("src.memory.long_term.memory", mock_mem):
            with patch(
                "src.agent.nodes.memory._is_semantically_similar",
                AsyncMock(return_value=False),
            ):
                await process_extraction_job(
                    {
                        "turn_text": "Contact tim@secret.com — preferred region ap-southeast-1",
                        "scenario_id": "pentest",
                        "mem0_uid": "owner",
                        "project_id": "default",
                    }
                )

    assert mock_mem.add.called
    saved = mock_mem.add.call_args[0][0]
    assert "tim@secret.com" not in saved
    assert "ap-southeast-1" in saved
    assert mock_mem.add.call_args.kwargs.get("infer") is False


@pytest.mark.anyio
async def test_memory_write_skips_trivial_short_replies(pentest_state):
    """Selective gate rejects very short assistant confirmations."""
    state: AgentState = {
        **pentest_state,
        "messages": [
            HumanMessage(content=HUMAN_TURN),
            AIMessage(content="Got it."),
        ],
    }
    with patch("src.memory.extraction.queue.enqueue_extraction", AsyncMock()) as enq:
        with patch("src.memory.long_term.memory", MagicMock()):
            out = await memory_write_node(state)
    assert out == {}
    enq.assert_not_awaited()


@pytest.mark.anyio
async def test_retrieve_loads_scenario_without_vector_when_gate_false(pentest_state):
    state: AgentState = {
        **pentest_state,
        "memory_context": "lite bundle",
        "needs_memory_retrieval": False,
        "scenario_id": "pentest",
    }
    with patch("src.memory.long_term.memory") as mock_mem:
        mock_mem.search = MagicMock()
        out = await memory_retrieve_node(state)
        mock_mem.search.assert_not_called()
    assert "Scenario playbook (pentest)" in out.get("memory_context", "")


async def _redis_ping() -> bool:
    try:
        import redis.asyncio as aioredis

        from src.config.settings import REDIS_URL

        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.ping()
            return True
        finally:
            await client.aclose()
    except Exception:
        return False


@pytest.mark.anyio
async def test_redis_enqueue_when_available():
    """Live Redis stream write (skipped when Redis is down)."""
    if not await _redis_ping():
        pytest.skip("Redis not available")

    import redis.asyncio as aioredis

    from src.config.settings import REDIS_URL

    job_id = "smoke-job-automated"
    payload = {
        "turn_id": job_id,
        "turn_text": "Smoke test atom ap-southeast-1",
        "mem0_uid": "owner",
        "project_id": "default",
        "scenario_id": "research",
    }
    queued = await enqueue_extraction(payload)
    assert queued is True

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        length = await client.xlen(STREAM_KEY)
        assert length >= 1
    finally:
        await client.aclose()
