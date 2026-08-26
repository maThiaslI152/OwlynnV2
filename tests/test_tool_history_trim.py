"""Prior-turn tool compression for multi-turn prefills."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.complex_prompt import _trim_tool_history


def test_prior_turn_web_search_is_compressed():
    fat = "x" * 12_000
    messages = [
        HumanMessage(content="what is Thailand GDP?"),
        AIMessage(
            content="", tool_calls=[{"name": "web_search", "id": "a", "args": {}}]
        ),
        ToolMessage(content=fat, tool_call_id="a", name="web_search"),
        AIMessage(content="About $500B."),
        HumanMessage(content="anyway what's the weather in Bangkok?"),
        AIMessage(
            content="", tool_calls=[{"name": "web_search", "id": "b", "args": {}}]
        ),
        ToolMessage(
            content="Bangkok 27C overcast " + ("y" * 8000),
            tool_call_id="b",
            name="web_search",
        ),
    ]
    trimmed = _trim_tool_history(
        messages,
        max_tool_cycles=6,
        prior_turn_max_chars=400,
        current_turn_max_chars=6000,
    )
    prior = trimmed[2]
    current = trimmed[6]
    assert isinstance(prior, ToolMessage)
    assert isinstance(current, ToolMessage)
    assert len(str(prior.content)) <= 500
    assert "truncated" in str(prior.content) or "completed" in str(prior.content)
    assert len(str(current.content)) <= 6200
    assert "27C" in str(current.content)


def test_in_turn_old_tools_stubbed_beyond_max_cycles():
    msgs: list = [HumanMessage(content="go")]
    for i in range(8):
        msgs.append(
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search", "id": f"t{i}", "args": {}}],
            )
        )
        msgs.append(
            ToolMessage(
                content=f"result-{i}-" + ("z" * 2000),
                tool_call_id=f"t{i}",
                name="web_search",
            )
        )
    trimmed = _trim_tool_history(msgs, max_tool_cycles=2, current_turn_max_chars=500)
    tool_msgs = [m for m in trimmed if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 8
    # First 6 stubbed
    for m in tool_msgs[:6]:
        assert "completed" in str(m.content)
    # Last 2 capped but retain payload head
    assert "result-6" in str(tool_msgs[6].content) or "result-7" in str(
        tool_msgs[6].content
    )
