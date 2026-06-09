"""complex-cloud + image must run vision_proxy before DeepSeek."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent.nodes.complex_utils import vision_proxy


@pytest.fixture(autouse=True)
def _clear_vision_cache():
    vision_proxy._TRANSCRIPTION_CACHE.clear()
    yield
    vision_proxy._TRANSCRIPTION_CACHE.clear()


@pytest.mark.asyncio
async def test_vision_proxy_replaces_image_with_transcription_text(monkeypatch):
    """Local VLM returns JSON OCR; output is text-only for DeepSeek."""

    async def fake_get_vision_llm():
        class FakeLLM:
            async def ainvoke(self, _messages):
                return AIMessage(
                    content=json.dumps(
                        {
                            "text_blocks": [
                                {
                                    "text": "The image shows a red circle labeled A connected to box B.",
                                    "bbox": None,
                                }
                            ],
                            "ui_elements": [],
                            "subjects": ["diagram"],
                            "confidence": 0.9,
                        }
                    )
                )

        return FakeLLM()

    monkeypatch.setattr(vision_proxy, "get_vision_llm", fake_get_vision_llm)

    messages = [
        SystemMessage(content="You are helpful."),
        HumanMessage(
            content=[
                {"type": "text", "text": "Explain this diagram formally"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,cloudpath"},
                },
            ]
        ),
    ]

    processed, ok = await vision_proxy.process_vision_messages(messages)

    assert ok is True
    human = processed[1]
    assert isinstance(human.content, list)
    assert not any(b.get("type") == "image_url" for b in human.content)
    joined = " ".join(
        b.get("text", "") for b in human.content if b.get("type") == "text"
    )
    assert "red circle" in joined
    assert "[Vision sensor output" in joined
