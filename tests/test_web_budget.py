"""Tests for category-aware web tool budgets."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.complex_prompt import (
    apply_web_search_answer_nudge,
    web_search_nudge_applied,
)
from src.agent.core.complex_utils.web_budget import (
    WEB_TOOL_NAMES,
    count_web_tool_usage,
    evaluate_web_budget,
    filter_tools_for_web_budget,
    get_web_tool_limits,
)


class _Tool:
    def __init__(self, name: str):
        self.name = name


def test_data_viz_budget_blocks_all_web_tools():
    limits = get_web_tool_limits("data_viz")
    assert limits["web_search"] == 0
    status = evaluate_web_budget(
        [],
        task_category="data_viz",
        tool_round=0,
        max_tool_rounds=3,
    )
    assert status.force_synthesis is False
    assert status.blocked_tools == WEB_TOOL_NAMES
    tools = filter_tools_for_web_budget(
        [_Tool("web_search"), _Tool("notebook_run")],
        status,
    )
    names = {t.name for t in tools or []}
    assert "web_search" not in names
    assert "notebook_run" in names


def test_per_tool_cap_blocks_individual_tools_before_round_cap():
    turn = [
        HumanMessage(content="news"),
        AIMessage(
            content="", tool_calls=[{"id": "1", "name": "web_search", "args": {}}]
        ),
        ToolMessage(content="r1", tool_call_id="1", name="web_search"),
        AIMessage(
            content="", tool_calls=[{"id": "2", "name": "web_search", "args": {}}]
        ),
        ToolMessage(content="r2", tool_call_id="2", name="web_search"),
    ]
    status = evaluate_web_budget(
        turn,
        task_category="default",
        tool_round=2,
        max_tool_rounds=3,
    )
    assert status.usage["web_search"] == 2
    assert "web_search" in status.blocked_tools
    assert "fetch_webpage" not in status.blocked_tools
    assert status.force_synthesis is False

    tools = filter_tools_for_web_budget(
        [_Tool("web_search"), _Tool("fetch_webpage"), _Tool("notebook_run")],
        status,
    )
    names = {t.name for t in tools or []}
    assert "web_search" not in names
    assert "fetch_webpage" in names
    assert "notebook_run" in names


def test_round_cap_forces_synthesis():
    turn = [
        HumanMessage(content="news"),
        AIMessage(
            content="", tool_calls=[{"id": "1", "name": "fetch_webpage", "args": {}}]
        ),
        ToolMessage(content="page", tool_call_id="1", name="fetch_webpage"),
    ]
    status = evaluate_web_budget(
        turn,
        task_category="web_search",
        tool_round=3,
        max_tool_rounds=3,
    )
    assert status.force_synthesis is True
    tools = filter_tools_for_web_budget(
        [_Tool("web_search"), _Tool("read_workspace_file")], status
    )
    assert [t.name for t in tools or []] == ["read_workspace_file"]


def test_count_web_tool_usage_ignores_non_web_tools():
    msgs = [
        ToolMessage(content="file", tool_call_id="1", name="read_workspace_file"),
        ToolMessage(content="ok", tool_call_id="2", name="web_search"),
    ]
    usage = count_web_tool_usage(msgs)
    assert usage["web_search"] == 1
    assert "read_workspace_file" not in usage


def test_web_search_nudge_embedded_in_tool_message_not_human():
    body = (
        '🔍 Web search results for: "test"\n\n'
        "**1. Hit**\n"
        "   URL: https://example.com\n"
        "   Snippet text.\n"
    )
    msg = ToolMessage(content=body, tool_call_id="1", name="web_search")
    nudged = apply_web_search_answer_nudge([msg])
    assert web_search_nudge_applied(nudged)
    assert all(not isinstance(m, HumanMessage) for m in nudged)
