"""tool_history_bypass should keep narrow toolboxes for web/file digressions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.state import AgentState
from src.agent.routing.router import router_node


@pytest.mark.anyio
async def test_tool_history_web_digression_keeps_web_search_toolbox():
    state: AgentState = {
        "messages": [
            HumanMessage(content="what is Thailand GDP?"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "web_search", "id": "c1", "args": {"query": "gdp"}}
                ],
            ),
            ToolMessage(content="GDP ~$500B", tool_call_id="c1", name="web_search"),
            AIMessage(content="About $500B."),
            HumanMessage(content="anyway what's the weather in Bangkok right now?"),
        ],
        "web_search_enabled": True,
    }
    with (
        patch("src.agent.routing.router._check_cloud_available", return_value=False),
        patch(
            "src.agent.routing.resolver.get_profile",
            return_value={"cloud_routing_mode": "local_only"},
        ),
        patch(
            "src.agent.core.complex_utils.lm_studio_vision.ensure_vision_vlm_loaded",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        out = await router_node(state)
    assert out["route"] == "complex-default"
    assert out["selected_toolboxes"] == ["web_search"]
    assert (out.get("router_metadata") or {}).get("reasoning") == "tool_history_bypass"


@pytest.mark.anyio
async def test_tool_history_write_note_keeps_file_ops():
    state: AgentState = {
        "messages": [
            HumanMessage(content="what is Thailand GDP?"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "web_search", "id": "c1", "args": {"query": "gdp"}}
                ],
            ),
            ToolMessage(content="GDP ~$500B", tool_call_id="c1", name="web_search"),
            AIMessage(content="About $500B."),
            HumanMessage(
                content="Save a short note to my workspace as note.txt. Use write_workspace_file."
            ),
        ],
        "web_search_enabled": True,
    }
    with (
        patch("src.agent.routing.router._check_cloud_available", return_value=False),
        patch(
            "src.agent.routing.resolver.get_profile",
            return_value={"cloud_routing_mode": "local_only"},
        ),
        patch(
            "src.agent.core.complex_utils.lm_studio_vision.ensure_vision_vlm_loaded",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        out = await router_node(state)
    assert "file_ops" in (out.get("selected_toolboxes") or [])
