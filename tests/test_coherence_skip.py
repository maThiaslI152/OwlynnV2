"""Coherence LLM skip heuristics for fast paths."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.nodes.coherence import should_skip_coherence_llm

_OK_SEARCH = (
    "🔍 search results for query\n"
    "1. Headline\n"
    "URL: https://example.com\n"
    "Body text here\n"
)


def test_skip_simple_route(monkeypatch):
    monkeypatch.setattr(
        "src.agent.nodes.coherence.config.get",
        lambda key, default=None: {
            "coherence.enabled": True,
            "coherence.skip_simple": True,
            "coherence.skip_short_answer_chars": 800,
            "coherence.skip_successful_web": True,
        }.get(key, default),
    )
    skip, reason = should_skip_coherence_llm(
        {"route": "simple"},
        response_content="Hello!",
        tool_failures=0,
        current_turn_messages=[],
    )
    assert skip is True
    assert reason == "simple_route"


def test_skip_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "src.agent.nodes.coherence.config.get",
        lambda key, default=None: False if key == "coherence.enabled" else default,
    )
    skip, reason = should_skip_coherence_llm(
        {"route": "complex-default"},
        response_content="A" * 2000,
        tool_failures=0,
        current_turn_messages=[],
    )
    assert skip is True
    assert reason == "coherence_disabled"


def test_skip_short_answer(monkeypatch):
    def _get(key, default=None):
        return {
            "coherence.enabled": True,
            "coherence.skip_simple": True,
            "coherence.skip_short_answer_chars": 800,
            "coherence.skip_successful_web": True,
        }.get(key, default)

    monkeypatch.setattr("src.agent.nodes.coherence.config.get", _get)
    skip, reason = should_skip_coherence_llm(
        {"route": "complex-default"},
        response_content="Short answer under limit.",
        tool_failures=0,
        current_turn_messages=[],
    )
    assert skip is True
    assert reason == "short_answer"


def test_skip_successful_web(monkeypatch):
    def _get(key, default=None):
        return {
            "coherence.enabled": True,
            "coherence.skip_simple": True,
            "coherence.skip_short_answer_chars": 50,
            "coherence.skip_successful_web": True,
        }.get(key, default)

    monkeypatch.setattr("src.agent.nodes.coherence.config.get", _get)
    turn = [
        HumanMessage(content="latest news"),
        ToolMessage(content=_OK_SEARCH, name="web_search", tool_call_id="1"),
        AIMessage(content="x" * 200),
    ]
    skip, reason = should_skip_coherence_llm(
        {"route": "complex-default"},
        response_content="x" * 200,
        tool_failures=0,
        current_turn_messages=turn,
    )
    assert skip is True
    assert reason == "successful_web_synthesis"


def test_no_skip_on_tool_failures(monkeypatch):
    def _get(key, default=None):
        return {
            "coherence.enabled": True,
            "coherence.skip_simple": True,
            "coherence.skip_short_answer_chars": 800,
            "coherence.skip_successful_web": True,
        }.get(key, default)

    monkeypatch.setattr("src.agent.nodes.coherence.config.get", _get)
    skip, reason = should_skip_coherence_llm(
        {"route": "complex-default"},
        response_content="Short.",
        tool_failures=1,
        current_turn_messages=[],
    )
    assert skip is False
