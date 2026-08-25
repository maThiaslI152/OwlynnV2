"""Automated end-to-end smoke tests for Phase 2 vision proxy."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

sys.modules.setdefault("mem0", MagicMock())

from src.agent.core.complex_utils import vision_proxy
from src.agent.core.complex_utils.vision_model_manager import VisionModelManager
from src.agent.core.complex_utils.vision_schema import (
    format_vision_for_cloud,
    parse_vision_payload,
)
from src.agent.routing.router import _resolve_complex_route

OCR_JSON = json.dumps(
    {
        "text_blocks": [{"text": "ERROR: connection refused on :5432", "bbox": None}],
        "ui_elements": [{"role": "heading", "label": "Terminal"}],
        "subjects": ["terminal"],
        "confidence": 0.91,
    }
)

TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
DATA_URL = f"data:image/png;base64,{TINY_PNG_B64}"


@pytest.fixture(autouse=True)
def clear_vision_cache():
    vision_proxy._TRANSCRIPTION_CACHE.clear()
    yield
    vision_proxy._TRANSCRIPTION_CACHE.clear()


@pytest.fixture
def mock_vlm():
    class FakeLLM:
        async def ainvoke(self, _messages):
            return AIMessage(content=OCR_JSON)

    return FakeLLM()


@pytest.mark.asyncio
async def test_vision_pipeline_json_to_cloud_block(mock_vlm):
    """VLM JSON → formatted block; no image_url in output."""
    with patch(
        "src.agent.core.complex_utils.vision_proxy.get_vision_llm",
        AsyncMock(return_value=mock_vlm),
    ):
        messages = [
            SystemMessage(content="You are helpful."),
            HumanMessage(
                content=[
                    {"type": "text", "text": "What error is shown?"},
                    {"type": "image_url", "image_url": {"url": DATA_URL}},
                ]
            ),
        ]
        processed, ok = await vision_proxy.process_vision_messages(messages)

    assert ok is True
    human = processed[1]
    text = " ".join(b.get("text", "") for b in human.content if b.get("type") == "text")
    assert not any(b.get("type") == "image_url" for b in human.content)
    assert "[Image content transcribed by vision sensor]" in text
    assert "connection refused" in text
    assert "Terminal" in text


@pytest.mark.asyncio
async def test_transcribe_crop_and_cache(mock_vlm):
    with patch(
        "src.agent.core.complex_utils.vision_proxy.get_vision_llm",
        AsyncMock(return_value=mock_vlm),
    ):
        blob = b"\x89PNG\x01smoke"
        a = await vision_proxy.transcribe_crop(blob, mime_type="image/png")
        b = await vision_proxy.transcribe_crop(blob, mime_type="image/png")

    assert a == b
    assert "connection refused" in a


@pytest.mark.asyncio
async def test_vlm_failure_preserves_image_for_fallback():
    async def broken_llm():
        class Fail:
            async def ainvoke(self, _m):
                raise RuntimeError("VLM offline")

        return Fail()

    with patch(
        "src.agent.core.complex_utils.vision_proxy.get_vision_llm",
        broken_llm,
    ):
        messages = [
            HumanMessage(
                content=[
                    {"type": "image_url", "image_url": {"url": DATA_URL}},
                ]
            )
        ]
        processed, ok = await vision_proxy.process_vision_messages(messages)

    assert ok is False
    assert any(b.get("type") == "image_url" for b in processed[0].content)


def test_unparsed_vlm_prose_fallback():
    """Non-JSON VLM output still becomes a cloud block."""
    block = vision_proxy._raw_to_cloud_text("Plain OCR line without JSON")
    assert "Plain OCR line" in block
    assert "[Image content transcribed by vision sensor]" in block


def test_image_routes_complex_cloud_for_vision_proxy():
    """Frontier-quality image prompts route to cloud when mode allows (not local_only)."""
    state = {
        "messages": [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": "Analyze this diagram and provide a formal proof of the theorem",
                    },
                    {"type": "image_url", "image_url": {"url": DATA_URL}},
                ]
            )
        ],
    }
    with patch(
        "src.agent.routing.resolver.get_profile",
        return_value={"cloud_routing_mode": "auto"},
    ):
        route, _ = _resolve_complex_route(
            "Analyze this diagram and provide a formal proof of the theorem",
            state,
            ["all"],
            cloud_available=True,
        )
    assert route == "complex-cloud"


def test_image_routes_local_default_when_local_only():
    """local_only keeps image turns on complex-default even when cloud is available."""
    state = {
        "messages": [
            HumanMessage(
                content=[
                    {"type": "text", "text": "What's in this image?"},
                    {"type": "image_url", "image_url": {"url": DATA_URL}},
                ]
            )
        ],
    }
    with patch(
        "src.agent.routing.resolver.get_profile",
        return_value={"cloud_routing_mode": "local_only"},
    ):
        route, _ = _resolve_complex_route(
            "What's in this image?",
            state,
            ["all"],
            cloud_available=True,
        )
    assert route == "complex-default"


@pytest.mark.asyncio
async def test_vision_model_manager_lazy_acquire():
    mgr = VisionModelManager()
    with patch.object(mgr, "_inflight", 0):
        with patch("src.agent.llm.LLMPool._test_overrides", {"medium": MagicMock()}):
            client = await mgr.acquire()
            assert client is not None
            await mgr.unload()
            assert mgr._client is None


def test_schema_roundtrip():
    payload = parse_vision_payload(OCR_JSON)
    assert payload is not None
    cloud = format_vision_for_cloud(payload)
    assert "Visible text: ERROR: connection refused" in cloud
