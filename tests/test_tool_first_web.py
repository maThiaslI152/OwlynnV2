"""Tool-first web helpers — inject search without bind_tools planning."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.tool_first_web import (
    TOOL_FIRST_PHASE_SEARCH,
    build_tool_first_web_search_message,
    should_escalate_tool_first,
    should_inject_tool_first_search,
    should_synthesize_tool_first,
)

_OK_SEARCH = (
    "🔍 search results for query\n"
    "1. Example\n"
    "URL: https://example.com\n"
    "Snippet about X\n"
)


def test_inject_when_web_search_only():
    state = {"selected_toolboxes": ["web_search"]}
    turn = [HumanMessage(content="latest news on AI")]
    assert should_inject_tool_first_search(state, turn) is True


def test_no_inject_when_toolbox_all():
    state = {"selected_toolboxes": ["all"]}
    turn = [HumanMessage(content="latest news on AI")]
    assert should_inject_tool_first_search(state, turn) is False


def test_build_search_message():
    msgs = [HumanMessage(content="current weather Tokyo")]
    ai = build_tool_first_web_search_message(msgs)
    assert isinstance(ai, AIMessage)
    assert ai.tool_calls
    assert ai.tool_calls[0]["name"] == "web_search"
    assert "Tokyo" in ai.tool_calls[0]["args"]["query"]


def test_pronoun_followup_expands_with_prior_human():
    msgs = [
        HumanMessage(content="what is the capital city of Thailand"),
        AIMessage(content="Bangkok is the capital."),
        HumanMessage(content="what is it's GDP"),
    ]
    ai = build_tool_first_web_search_message(msgs)
    q = ai.tool_calls[0]["args"]["query"]
    assert "Thailand" in q
    assert "GDP" in q.upper() or "gdp" in q.lower()


def test_synthesize_after_successful_search():
    state = {
        "selected_toolboxes": ["web_search"],
        "_tool_first_web_phase": TOOL_FIRST_PHASE_SEARCH,
    }
    turn = [
        HumanMessage(content="latest X"),
        AIMessage(
            content="", tool_calls=[{"name": "web_search", "id": "1", "args": {}}]
        ),
        ToolMessage(content=_OK_SEARCH, name="web_search", tool_call_id="1"),
    ]
    assert should_synthesize_tool_first(state, turn) is True
    assert should_escalate_tool_first(state, turn) is False


def test_escalate_on_failed_search():
    state = {
        "selected_toolboxes": ["web_search"],
        "_tool_first_web_phase": TOOL_FIRST_PHASE_SEARCH,
    }
    turn = [
        HumanMessage(content="latest X"),
        ToolMessage(
            content="[web_search] Error: Unable to search",
            name="web_search",
            tool_call_id="1",
        ),
    ]
    assert should_synthesize_tool_first(state, turn) is False
    assert should_escalate_tool_first(state, turn) is True


def test_no_reinject_after_done_phase():
    """After one synthesis, tool-first must not inject another search round."""
    state = {
        "selected_toolboxes": ["web_search"],
        "_tool_first_web_phase": "done",
    }
    turn = [HumanMessage(content="latest news on AI")]
    assert should_inject_tool_first_search(state, turn) is False
    assert should_synthesize_tool_first(state, turn) is False
