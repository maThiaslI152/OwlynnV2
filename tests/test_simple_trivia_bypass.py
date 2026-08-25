"""Deterministic simple-path widening for short trivia / explain queries."""

import sys
from unittest.mock import MagicMock

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import HumanMessage

from src.agent.core.state import AgentState
from src.agent.routing.router import router_node


@pytest.mark.anyio
async def test_what_is_capital_routes_simple():
    state: AgentState = {
        "messages": [HumanMessage(content="What is the capital of France?")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"] == "simple"
    assert out.get("router_metadata", {}).get("reasoning") == "simple_trivia_bypass"


@pytest.mark.anyio
async def test_short_explain_routes_simple():
    state: AgentState = {
        "messages": [HumanMessage(content="Explain what HTTP is")],
        "web_search_enabled": False,
    }
    out = await router_node(state)
    assert out["route"] == "simple"


@pytest.mark.anyio
async def test_web_latest_still_complex():
    state: AgentState = {
        "messages": [HumanMessage(content="What is the latest Python release?")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "web_search" in out.get("selected_toolboxes", [])


@pytest.mark.anyio
async def test_gdp_followup_routes_web_not_simple():
    """Live economic stats must not hit no-tool simple (avoids raw tool_call leaks)."""
    state: AgentState = {
        "messages": [
            HumanMessage(content="what is the capital city of Thailand"),
            HumanMessage(content="what is it's GDP"),
        ],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert out.get("selected_toolboxes") == ["web_search"]


@pytest.mark.anyio
async def test_code_review_without_code_disables_tools():
    """Missing code must not bind tools/ask_user (avoids HITL loops on F2.1)."""
    state: AgentState = {
        "messages": [HumanMessage(content="Please review my code for bugs")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert out.get("selected_toolboxes") == ["none"]
    assert out.get("router_metadata", {}).get("code_review_missing_code") is True
    assert out.get("router_metadata", {}).get("reasoning") == (
        "code_review_missing_code_bypass"
    )


@pytest.mark.anyio
async def test_code_review_with_fence_keeps_file_ops():
    state: AgentState = {
        "messages": [
            HumanMessage(
                content="Please review my code:\n```python\ndef foo():\n    return 1\n```"
            )
        ],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "file_ops" in (out.get("selected_toolboxes") or [])
    assert out.get("router_metadata", {}).get("code_review_missing_code") is False
