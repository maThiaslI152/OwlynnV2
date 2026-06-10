import pytest
from langchain_core.messages import HumanMessage, AIMessage
from src.agent.nodes.simple import simple_node
from src.agent.state import AgentState


@pytest.mark.anyio
async def test_simple_node_streams_and_aggregates(monkeypatch):
    """Verify that simple_node uses astream and aggregates the chunks correctly."""

    class FakeLLM:
        def bind(self, **kwargs):
            return self

        async def astream(self, prompt, **kwargs):
            class Chunk:
                def __init__(self, content):
                    self.content = content

            chunks = [Chunk("Hello"), Chunk(" "), Chunk("world!")]
            for chunk in chunks:
                yield chunk

    async def fake_get_small_llm():
        return FakeLLM()

    monkeypatch.setattr("src.agent.nodes.simple.get_small_llm", fake_get_small_llm)

    state: AgentState = {
        "messages": [HumanMessage(content="Hi")],
        "token_budget": 256,
        "persona": "You are a helpful assistant.",
    }

    out = await simple_node(state)

    assert "messages" in out
    assert len(out["messages"]) == 1
    assert isinstance(out["messages"][0], AIMessage)
    assert out["messages"][0].content == "Hello world!"
    assert out["model_used"] == "small-local"
    assert out["fallback_chain"][0]["status"] == "success"
