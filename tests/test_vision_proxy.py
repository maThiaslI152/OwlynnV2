"""Unit tests for cloud-route vision-to-text proxy."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent.nodes.complex_utils import vision_proxy


@pytest.mark.asyncio
async def test_process_vision_messages_transcribes_image(monkeypatch):
    async def fake_get_medium_llm(_variant):
        class FakeLLM:
            async def ainvoke(self, _messages):
                return AIMessage(content="A red square on white background.")

        return FakeLLM()

    monkeypatch.setattr(vision_proxy, "get_medium_llm", fake_get_medium_llm)

    messages = [
        SystemMessage(content="sys"),
        HumanMessage(
            content=[
                {"type": "text", "text": "describe"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,abc"},
                },
            ]
        ),
    ]

    processed, ok = await vision_proxy.process_vision_messages(messages)

    assert ok is True
    human = processed[1]
    assert isinstance(human.content, list)
    assert all(b.get("type") != "image_url" for b in human.content)
    assert any(
        "red square" in b.get("text", "")
        for b in human.content
        if b.get("type") == "text"
    )


@pytest.mark.asyncio
async def test_process_vision_messages_failure_keeps_image_and_returns_false(
    monkeypatch,
):
    async def fake_get_medium_llm(_variant):
        class FakeLLM:
            async def ainvoke(self, _messages):
                raise RuntimeError("VLM unavailable")

        return FakeLLM()

    monkeypatch.setattr(vision_proxy, "get_medium_llm", fake_get_medium_llm)

    messages = [
        HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,abc"},
                }
            ]
        )
    ]

    processed, ok = await vision_proxy.process_vision_messages(messages)

    assert ok is False
    human = processed[0]
    assert any(b.get("type") == "image_url" for b in human.content)
