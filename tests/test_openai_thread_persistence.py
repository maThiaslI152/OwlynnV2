"""R9: OpenAI compat API passes thread_id to LangGraph config."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules["mem0"] = MagicMock()


@pytest.mark.asyncio
async def test_openai_thread_id_in_config():
    from src.api.routes import openai as openai_routes

    captured: list = []

    async def fake_ainvoke(inputs, config=None):
        captured.append(config)
        from langchain_core.messages import AIMessage

        msgs = inputs.get("messages") or []
        return {"messages": msgs + [AIMessage(content="ok")]}

    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mock_app = MagicMock()
    mock_app.state.agent = mock_agent

    tid = "test-thread-persist-001"
    with patch("src.api.server.app", mock_app):
        await openai_routes.api_openai_chat_completions(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "thread_id": tid,
            }
        )
        await openai_routes.api_openai_chat_completions(
            {
                "messages": [{"role": "user", "content": "follow up"}],
                "thread_id": tid,
            }
        )

    assert len(captured) == 2
    assert captured[0]["configurable"]["thread_id"] == tid
    assert captured[1]["configurable"]["thread_id"] == tid
