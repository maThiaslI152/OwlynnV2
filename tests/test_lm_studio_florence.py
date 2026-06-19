"""Vision VLM LM Studio load helpers (Qwen3-VL-4B)."""

from __future__ import annotations

import pytest

from src.agent.nodes.complex_utils import lm_studio_vision as fl


@pytest.mark.asyncio
async def test_is_vision_vlm_loaded_when_instance_present(monkeypatch):
    catalog = [
        {
            "key": "qwen3-vl-4b-instruct-c_abliterated-v2-mlx",
            "loaded_instances": [{"id": "inst-1"}],
        },
        {"key": "minicpm5-1b", "loaded_instances": []},
    ]

    async def fake_catalog(_client):
        return catalog

    monkeypatch.setattr(fl, "fetch_lm_studio_catalog", fake_catalog)
    assert await fl.is_vision_vlm_loaded()


@pytest.mark.asyncio
async def test_is_vision_vlm_loaded_false_when_not_loaded(monkeypatch):
    catalog = [
        {
            "key": "qwen3-vl-4b-instruct-c_abliterated-v2-mlx",
            "loaded_instances": [],
        }
    ]

    async def fake_catalog(_client):
        return catalog

    monkeypatch.setattr(fl, "fetch_lm_studio_catalog", fake_catalog)
    assert not await fl.is_vision_vlm_loaded()


@pytest.mark.asyncio
async def test_ensure_vision_vlm_loaded_skips_when_already_active(monkeypatch):
    async def loaded(_client=None):
        return True

    monkeypatch.setattr(fl, "is_vision_vlm_loaded", loaded)
    assert await fl.ensure_vision_vlm_loaded()
