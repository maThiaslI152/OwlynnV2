"""Automated end-to-end smoke tests for Phase 1 memory orchestration."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.modules.setdefault("mem0", MagicMock())

from src.agent.core.state import AgentState
from src.agent.nodes.memory import (
    memory_inject_lite_node,
    memory_retrieve_node,
    memory_write_node,
)
from src.agent.routing.router import router_node
from src.memory.extraction.queue import enqueue_extraction
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

    if hasattr(q, "_DEDUP") and isinstance(q._DEDUP, dict):
        q._DEDUP.clear()
    yield
    if hasattr(q, "_DEDUP") and isinstance(q._DEDUP, dict):
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

    async def fake_small_llm():
        class LLM:
            def bind(self, **_kwargs):
                return self

            async def ainvoke(self, _messages):
                class R:
                    content = '{"routing":"complex","confidence":0.9,"toolbox":"all"}'

                return R()

        return LLM()

    with patch("src.agent.routing.router._check_cloud_available", return_value=False):
        with patch("src.agent.routing.router.get_main_llm", fake_small_llm):
            with patch("src.agent.routing.router.get_small_llm", fake_small_llm):
                with patch(
                    "src.agent.routing.router._memory_gate_fields",
                    return_value={
                        "needs_memory_retrieval": True,
                        "scenario_id": "pentest",
                    },
                ):
                    routed = await router_node(state)

    assert routed["route"] in ("complex-cloud", "complex-default")
    assert routed.get("needs_memory_retrieval") is True
    assert routed.get("scenario_id") == "pentest"

    state = {**state, **routed}

    # Pentest mode: memory_retrieve_node skips Mem0, uses engagement context
    with patch("src.memory.long_term.memory") as mock_mem:
        mock_mem.search = MagicMock(
            return_value=[{"memory": "User prefers ap-southeast-1 region"}]
        )
        with (
            patch(
                "src.agent.nodes.memory._is_semantically_similar",
                AsyncMock(return_value=False),
            ),
            patch(
                "src.memory.pentest_engagement.get_active_engagement",
                AsyncMock(return_value={"id": "eng-1", "name": "Pentest Alpha"}),
            ),
            patch(
                "src.memory.pentest_engagement.get_engagement_context",
                AsyncMock(return_value="Active pentest engagement context"),
            ),
            patch(
                "src.memory.pentest_engagement.get_findings_summary",
                AsyncMock(return_value={"total": 0}),
            ),
        ):
            retrieved = await memory_retrieve_node(state)
        # Pentest mode bypasses Mem0 search entirely
        mock_mem.search.assert_not_called()

    ctx = retrieved.get("memory_context", "")
    assert "pentest" in ctx.lower() or "engagement" in ctx.lower()

    state = {
        **state,
        **retrieved,
        "messages": [
            HumanMessage(content=HUMAN_TURN),
            AIMessage(content=AI_TURN),
        ],
    }

    # Pentest mode: memory_write_node skips extraction, logs to engagement timeline
    with (
        patch(
            "src.memory.extraction.queue.enqueue_extraction",
            AsyncMock(return_value=True),
        ) as enq,
        patch("src.memory.long_term.memory", MagicMock()),
    ):
        written = await memory_write_node(state)

    # Pentest mode skips Mem0 extraction
    assert enq.await_count == 0
    assert written.get("memory_invalidated") is True

    # Extraction worker also skips pentest turns
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

    # Pentest extraction worker skips — no Mem0 writes
    assert not mock_mem.add.called


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


async def _postgres_reachable() -> bool:
    """True when the async SQLAlchemy session can connect."""
    try:
        from sqlalchemy import text

        from src.models.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.anyio
async def test_postgres_enqueue_when_available():
    """Live Postgres extraction enqueue (skipped when DB is down)."""
    from src.memory.postgres_health import is_postgres_available, reset_postgres_breaker

    reset_postgres_breaker()
    if not await _postgres_reachable():
        pytest.skip("Postgres not available")
    if not is_postgres_available():
        pytest.skip("Postgres circuit open")

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
