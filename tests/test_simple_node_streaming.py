import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.core.simple import _simple_output_max_tokens, simple_node
from src.agent.core.state import AgentState


def test_simple_output_max_tokens_caps_not_main_floor():
    """Simple path must not inherit models.main.max_tokens (often 8192)."""
    from src.config.config_loader import config

    cap = max(64, int(config.get("simple.max_tokens", 256) or 256))
    floor = min(64, cap)
    assert _simple_output_max_tokens(128) == max(floor, min(128, cap))
    assert _simple_output_max_tokens(256) == max(floor, min(256, cap))
    assert _simple_output_max_tokens(4096) <= cap
    assert _simple_output_max_tokens(64) >= min(64, floor)


@pytest.mark.anyio
async def test_simple_node_streams_and_aggregates(monkeypatch):
    """Verify that simple_node uses astream and aggregates the chunks correctly."""

    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def astream(self, prompt, **kwargs):
            # Config may be passed for WS on_chat_model_stream propagation.
            assert "config" in kwargs or kwargs == {}

            class Chunk:
                def __init__(self, content):
                    self.content = content

            chunks = [Chunk("Hello"), Chunk(" "), Chunk("world!")]
            for chunk in chunks:
                yield chunk

    async def fake_get_main_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.core.simple.get_main_llm", fake_get_main_llm)
    monkeypatch.setattr("src.agent.core.simple.get_small_llm", fake_get_main_llm)
    # Outside a LangGraph run, get_config may raise — force None path then with config.
    monkeypatch.setattr(
        "src.agent.core.simple._runnable_config_for_stream", lambda: {"tags": ["test"]}
    )

    state: AgentState = {
        "messages": [HumanMessage(content="Hi")],
        "token_budget": 128,
        "persona": "You are a helpful assistant.",
    }

    out = await simple_node(state)

    assert "messages" in out
    assert len(out["messages"]) == 1
    assert isinstance(out["messages"][0], AIMessage)
    assert out["messages"][0].content == "Hello world!"
    assert out["model_used"] in ("main-local", "small-local")
    assert out["fallback_chain"][0]["status"] == "success"


def test_runnable_config_for_stream_tolerates_missing_context():
    """Outside LangGraph, config lookup must not raise."""
    from src.agent.core.simple import _runnable_config_for_stream

    # May return None or a dict depending on ambient context; must not raise.
    _ = _runnable_config_for_stream()

