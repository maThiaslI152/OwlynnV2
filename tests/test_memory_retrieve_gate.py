"""Memory retrieve gate after router."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import HumanMessage

from src.agent.nodes.memory import memory_inject_lite_node, memory_retrieve_node
from src.agent.nodes.router import router_node
from src.agent.state import AgentState


@pytest.mark.anyio
async def test_lite_inject_skips_vector_search():
    state: AgentState = {
        "messages": [HumanMessage(content="Hello, what is OWASP Top 10?")],
        "thread_id": "lite-test",
        "project_id": "default",
        "persona_id": "default",
    }
    with patch("src.memory.long_term.memory") as mock_mem:
        mock_mem.search = MagicMock()
        out = await memory_inject_lite_node(state)
        mock_mem.search.assert_not_called()
    assert "persona" in out
    assert out.get("knowledge_context") == ""


@pytest.mark.anyio
async def test_retrieve_skipped_when_gate_false():
    state: AgentState = {
        "messages": [HumanMessage(content="Hi")],
        "thread_id": "gate-test",
        "memory_context": "lite context",
        "needs_memory_retrieval": False,
        "scenario_id": "pentest",
    }
    with patch("src.memory.long_term.memory") as mock_mem:
        mock_mem.search = MagicMock()
        out = await memory_retrieve_node(state)
        mock_mem.search.assert_not_called()
    assert "Scenario playbook (pentest)" in out.get("memory_context", "")


@pytest.mark.anyio
async def test_router_simple_sets_memory_gate_false():
    state: AgentState = {
        "messages": [HumanMessage(content="Hi there!")],
        "web_search_enabled": True,
        "memory_context": "lite",
    }
    out = await router_node(state)
    assert out["route"] == "simple"
    assert out.get("needs_memory_retrieval") is False
