"""Tests for local complex path web synthesis (Gemma 12B)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.complex import (
    _apply_web_budget_to_tools,
    complex_llm_node,
)
from src.agent.core.complex_prompt import (
    COMPLEX_TOOL_GUIDANCE_LOCAL_SYNTHESIS,
    COMPLEX_TOOL_GUIDANCE_NO_WEB,
    COMPLEX_TOOL_GUIDANCE_WEB_LOCAL,
    _LOCAL_HTML_CHART_GUIDANCE,
)


class _Tool:
    def __init__(self, name: str):
        self.name = name


def test_force_synthesis_unbinds_all_tools():
    tools = [_Tool("web_search"), _Tool("notebook_run"), _Tool("ask_user")]
    turn = [
        HumanMessage(content="news"),
        AIMessage(
            content="", tool_calls=[{"id": "1", "name": "web_search", "args": {}}]
        ),
        ToolMessage(content="results", tool_call_id="1", name="web_search"),
        AIMessage(
            content="", tool_calls=[{"id": "2", "name": "web_search", "args": {}}]
        ),
        ToolMessage(content="more", tool_call_id="2", name="web_search"),
        AIMessage(
            content="", tool_calls=[{"id": "3", "name": "fetch_webpage", "args": {}}]
        ),
        ToolMessage(content="page", tool_call_id="3", name="fetch_webpage"),
    ]
    tools_for_invoke, tools_bound, volatile_extra, status = _apply_web_budget_to_tools(
        tools=tools,
        tools_bound=True,
        turn_messages=turn,
        state={"router_metadata": {"task_category": "web_search"}},
        volatile_extra="",
    )
    assert status.force_synthesis is True
    assert tools_for_invoke is None
    assert tools_bound is False
    assert COMPLEX_TOOL_GUIDANCE_LOCAL_SYNTHESIS in volatile_extra


@pytest.mark.asyncio
async def test_blank_web_search_uses_fallback_prose():
    web_body = (
        '🔍 Web search results for: "python 3.14"\n\n'
        "**1. What's new**\n"
        "   URL: https://docs.python.org/3.14/\n"
        "   New features listed.\n"
    )
    state = {
        "messages": [
            HumanMessage(content="Python 3.14 features"),
            AIMessage(
                content="",
                tool_calls=[{"id": "1", "name": "web_search", "args": {"query": "x"}}],
            ),
            ToolMessage(content=web_body, tool_call_id="1", name="web_search"),
        ],
        "route": "complex-default",
        "mode": "tools_on",
        "web_search_enabled": True,
        "memory_context": "",
        "persona": "Test",
        "response_style": None,
        "token_budget": 1024,
        "selected_toolboxes": ["all"],
        "router_metadata": {"task_category": "web_search"},
    }

    blank_response = AIMessage(content="")
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_bound.ainvoke = AsyncMock(return_value=blank_response)
    mock_llm.bind_tools.return_value.bind.return_value = mock_bound
    mock_llm.bind.return_value = mock_bound

    with (
        patch(
            "src.agent.core.complex.get_profile",
            return_value={"cloud_model_tier": "flash"},
        ),
        patch(
            "src.agent.core.complex.prepare_cloud_payload",
            new_callable=AsyncMock,
        ) as mock_payload,
        patch(
            "src.agent.core.complex._invoke_local_path",
            new_callable=AsyncMock,
            return_value=(blank_response, {"prompt_tokens": 1, "completion_tokens": 0}),
        ) as mock_invoke,
    ):
        mock_payload.return_value = MagicMock(
            prompt_messages=state["messages"],
            anon_mapping={},
            cloud_brief_tokens_est=0,
            anonymization_placeholders_count=0,
            vision_intake_mode="text",
            vision_proxy_ok=True,
        )
        result = await complex_llm_node(state)

    assert mock_invoke.call_count >= 1
    first_call_tools = mock_invoke.call_args_list[0].kwargs.get("tools")
    final_msg = result["messages"][0]
    assert not getattr(final_msg, "tool_calls", None)
    content = str(getattr(final_msg, "content", "") or "")
    assert content.strip()
    assert "empty response" not in content.lower()
    assert first_call_tools is None or isinstance(first_call_tools, list)


def test_local_chart_guidance_uses_offline_chartjs():
    assert "/vendor/chart.umd.min.js" in _LOCAL_HTML_CHART_GUIDANCE
    assert (
        "no CDN" in _LOCAL_HTML_CHART_GUIDANCE.lower()
        or "no cdn" in _LOCAL_HTML_CHART_GUIDANCE.lower()
    )
    assert "cdn.jsdelivr" not in _LOCAL_HTML_CHART_GUIDANCE
    assert "write_workspace_file" in _LOCAL_HTML_CHART_GUIDANCE
    for guidance in (COMPLEX_TOOL_GUIDANCE_WEB_LOCAL, COMPLEX_TOOL_GUIDANCE_NO_WEB):
        assert "/vendor/chart.umd.min.js" in guidance
        assert "SVG" not in guidance or "inline SVG" not in guidance
