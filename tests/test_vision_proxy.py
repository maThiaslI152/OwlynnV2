"""Unit tests for cloud-route vision-to-text proxy."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent.nodes.complex_utils import vision_proxy


def _fake_ocr_json(text: str) -> str:
    return json.dumps(
        {
            "text_blocks": [{"text": text, "bbox": None}],
            "ui_elements": [],
            "subjects": ["image"],
            "confidence": 0.9,
        }
    )


@pytest.mark.asyncio
async def test_process_vision_messages_transcribes_image(monkeypatch):
    async def fake_get_vision_llm():
        class FakeLLM:
            async def ainvoke(self, _messages):
                return AIMessage(
                    content=_fake_ocr_json("A red square on white background.")
                )

        return FakeLLM()

    monkeypatch.setattr(
        vision_proxy, "get_vision_llm", fake_get_vision_llm
    )

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
    assert any(
        "[Vision sensor output" in b.get("text", "")
        for b in human.content
        if b.get("type") == "text"
    )


@pytest.fixture(autouse=True)
def _clear_vision_cache():
    from src.agent.nodes.complex_utils import vision_proxy as vp

    vp._TRANSCRIPTION_CACHE.clear()
    yield
    vp._TRANSCRIPTION_CACHE.clear()


@pytest.mark.asyncio
async def test_process_vision_messages_failure_keeps_image_and_returns_false(
    monkeypatch,
):
    async def fake_get_vision_llm():
        class FakeLLM:
            async def ainvoke(self, _messages):
                raise RuntimeError("VLM unavailable")

        return FakeLLM()

    monkeypatch.setattr(
        vision_proxy, "get_vision_llm", fake_get_vision_llm
    )

    messages = [
        HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,failcase"},
                }
            ]
        )
    ]

    processed, ok = await vision_proxy.process_vision_messages(messages)

    assert ok is False
    human = processed[0]
    assert any(b.get("type") == "image_url" for b in human.content)


@pytest.mark.asyncio
async def test_transcribe_crop_uses_bytes_cache(monkeypatch):
    calls = []

    async def fake_get_vision_llm():
        class FakeLLM:
            async def ainvoke(self, _messages):
                calls.append(1)
                return AIMessage(content=_fake_ocr_json("crop text"))

        return FakeLLM()

    monkeypatch.setattr(
        vision_proxy, "get_vision_llm", fake_get_vision_llm
    )

    out1 = await vision_proxy.transcribe_crop(b"\x89PNG\x01", mime_type="image/png")
    out2 = await vision_proxy.transcribe_crop(b"\x89PNG\x01", mime_type="image/png")

    assert "crop text" in out1
    assert out1 == out2
    assert len(calls) == 1
