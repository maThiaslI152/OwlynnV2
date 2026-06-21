import pytest
import time
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.agent.nodes.coherence import (
    _parse_coherence_json,
    coherence_check_node,
)
from src.agent.core.state import AgentState


def test_parse_coherence_json():
    # Test valid JSON
    res = _parse_coherence_json(
        '{"coherent": true, "score": 0.85, "reason": "Response matches"}'
    )
    assert res["coherent"] is True
    assert res["score"] == 0.85
    assert res["reason"] == "Response matches"

    # Test JSON with thinking tags
    res_thinking = _parse_coherence_json(
        "<think>Let me evaluate this response.</think> "
        '{"coherent": false, "score": 0.3, "reason": "Off-topic"}'
    )
    assert res_thinking["coherent"] is False
    assert res_thinking["score"] == 0.3
    assert res_thinking["reason"] == "Off-topic"

    # Test malformed/fallback
    res_malformed = _parse_coherence_json("not a json string")
    assert res_malformed["coherent"] is True
    assert res_malformed["score"] == 1.0
    assert "Failed to parse" in res_malformed["reason"]


@pytest.mark.anyio
async def test_coherence_check_node_coherent(monkeypatch):
    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, prompt, **kwargs):
            class Response:
                content = (
                    '{"coherent": true, "score": 0.9, "reason": "Highly coherent"}'
                )

            return Response()

    async def fake_get_small_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.nodes.coherence.get_small_llm", fake_get_small_llm)

    state: AgentState = {
        "messages": [
            HumanMessage(content="What is the weather today?"),
            AIMessage(content="Today is sunny and warm."),
        ],
        "turn_start_time": time.time() - 2.0,
        "route": "simple",
    }

    out = await coherence_check_node(state)

    assert out["response_confidence"] == 0.9
    assert out["response_coherence"]["coherent"] is True
    assert out["response_coherence"]["score"] == 0.9
    assert out["response_coherence"]["reason"] == "Highly coherent"
    assert out["turn_duration_ms"] >= 2000


@pytest.mark.anyio
async def test_coherence_check_node_tool_failures(monkeypatch):
    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, prompt, **kwargs):
            class Response:
                content = '{"coherent": true, "score": 0.8, "reason": "Answers the query after tool use"}'

            return Response()

    async def fake_get_small_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.nodes.coherence.get_small_llm", fake_get_small_llm)

    # 2 tool messages: 1 failed, 1 succeeded
    state: AgentState = {
        "messages": [
            HumanMessage(content="Read workspace settings"),
            AIMessage(
                content="",
                tool_calls=[{"name": "read_workspace_file", "args": {}, "id": "tc1"}],
            ),
            ToolMessage(content="Error: File not found", tool_call_id="tc1"),
            AIMessage(
                content="",
                tool_calls=[{"name": "read_workspace_file", "args": {}, "id": "tc2"}],
            ),
            ToolMessage(content="Success: settings read", tool_call_id="tc2"),
            AIMessage(
                content="I could not find the first file but successfully loaded the settings."
            ),
        ],
        "turn_start_time": time.time() - 1.0,
        "route": "complex-cloud",
    }

    out = await coherence_check_node(state)

    # base score: 0.8
    # 1 tool failure -> deduction: 0.15
    # calibrated confidence: 0.8 - 0.15 = 0.65
    assert out["response_confidence"] == pytest.approx(0.65)
    assert out["response_coherence"]["coherent"] is True


@pytest.mark.anyio
async def test_coherence_check_node_short_response(monkeypatch):
    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, prompt, **kwargs):
            class Response:
                content = (
                    '{"coherent": true, "score": 0.7, "reason": "Correct but terse"}'
                )

            return Response()

    async def fake_get_small_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.nodes.coherence.get_small_llm", fake_get_small_llm)

    # Route is complex, response is under 10 characters (e.g. "Done.")
    state: AgentState = {
        "messages": [
            HumanMessage(content="Perform complex analysis"),
            AIMessage(content="Done."),
        ],
        "turn_start_time": time.time() - 0.5,
        "route": "complex-cloud",
    }

    out = await coherence_check_node(state)

    # base score: 0.7
    # short response check in complex turn -> deduct 0.3, set coherent = False
    assert out["response_confidence"] == pytest.approx(0.4)
    assert out["response_coherence"]["coherent"] is False


@pytest.mark.anyio
async def test_coherence_check_node_below_retry_threshold(monkeypatch):
    """Below 0.4 the response_confidence triggers the coherence_retry gate."""

    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, prompt, **kwargs):
            class Response:
                content = '{"coherent": false, "score": 0.2, "reason": "Off-topic"}'

            return Response()

    async def fake_get_small_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.nodes.coherence.get_small_llm", fake_get_small_llm)

    state: AgentState = {
        "messages": [
            HumanMessage(content="Explain quantum entanglement"),
            AIMessage(content="It is fast."),
        ],
        "turn_start_time": time.time() - 0.5,
        "route": "complex-cloud",
    }

    out = await coherence_check_node(state)
    assert out["response_confidence"] < 0.4


@pytest.mark.anyio
@patch("src.agent.nodes.coherence.audit_warn")
async def test_coherence_check_node_latency_warning(mock_audit_warn, monkeypatch):
    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, prompt, **kwargs):
            class Response:
                content = '{"coherent": true, "score": 1.0, "reason": "Perfect"}'

            return Response()

    async def fake_get_small_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.nodes.coherence.get_small_llm", fake_get_small_llm)

    # Latency: 20 seconds ago
    state: AgentState = {
        "messages": [
            HumanMessage(content="Hello"),
            AIMessage(content="Hello there!"),
        ],
        "turn_start_time": time.time() - 20.0,
        "route": "simple",
    }

    out = await coherence_check_node(state)

    # Assert that duration is tracked and high turn latency warning was logged
    assert out["turn_duration_ms"] >= 20000
    mock_audit_warn.assert_called_once()
    args, kwargs = mock_audit_warn.call_args
    assert args[0] == "agent.lifecycle"
    assert args[1] == "high_turn_latency"
    assert kwargs["duration_ms"] >= 20000
