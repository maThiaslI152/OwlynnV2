"""Tests for ToolNode output delta extraction (LangGraph tool-only vs full history)."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.nodes.complex import (
    _count_ai_tool_rounds,
    _extract_tool_output_delta,
)


def test_extract_delta_when_toolnode_returns_only_tool_messages():
    current = [
        HumanMessage(content="q"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "call_00", "name": "deep_research", "args": {}},
                {"id": "call_01", "name": "web_search", "args": {}},
                {"id": "call_02", "name": "web_search", "args": {}},
            ],
        ),
    ]
    output = [
        ToolMessage(content="r0", tool_call_id="call_00", name="deep_research"),
        ToolMessage(content="r1", tool_call_id="call_01", name="web_search"),
        ToolMessage(content="r2", tool_call_id="call_02", name="web_search"),
    ]
    delta = _extract_tool_output_delta(current, output)
    assert len(delta) == 3
    assert [m.tool_call_id for m in delta] == ["call_00", "call_01", "call_02"]


def test_extract_delta_when_toolnode_returns_full_history():
    current = [
        HumanMessage(content="q"),
        AIMessage(
            content="", tool_calls=[{"id": "call_1", "name": "web_search", "args": {}}]
        ),
    ]
    tool = ToolMessage(content="ok", tool_call_id="call_1", name="web_search")
    output = [*current, tool]
    delta = _extract_tool_output_delta(current, output)
    assert len(delta) == 1
    assert delta[0].tool_call_id == "call_1"


def test_count_ai_tool_rounds():
    msgs = [
        HumanMessage(content="q"),
        AIMessage(
            content="", tool_calls=[{"id": "1", "name": "web_search", "args": {}}]
        ),
        ToolMessage(content="r", tool_call_id="1"),
        AIMessage(
            content="", tool_calls=[{"id": "2", "name": "fetch_webpage", "args": {}}]
        ),
    ]
    assert _count_ai_tool_rounds(msgs) == 2


def test_old_buggy_slice_drops_parallel_tool_results():
    """Regression: slicing tool-only output by len(current) kept only the last tool."""
    current = [HumanMessage(content="q"), AIMessage(content="", tool_calls=[])]
    output = [
        ToolMessage(content="a", tool_call_id="call_00"),
        ToolMessage(content="b", tool_call_id="call_01"),
        ToolMessage(content="c", tool_call_id="call_02"),
    ]
    buggy_delta = output[len(current) :]
    assert len(buggy_delta) == 1
    fixed_delta = _extract_tool_output_delta(current, output)
    assert len(fixed_delta) == 3
