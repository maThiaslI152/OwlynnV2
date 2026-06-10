"""Florence-2 LM Studio load helpers for vision_proxy."""

from __future__ import annotations

import pytest

from src.agent.nodes.complex_utils import lm_studio_florence as fl


@pytest.mark.asyncio
async def test_is_florence_loaded_when_instance_present(monkeypatch):
    catalog = [
        {
            "key": "florence-2-base-nsfw-v2-ext-mlx",
            "loaded_instances": [{"id": "inst-1"}],
        },
        {"key": "minicpm5-1b", "loaded_instances": []},
    ]

    async def fake_catalog(_client):
        return catalog

    monkeypatch.setattr(fl, "fetch_lm_studio_catalog", fake_catalog)
    assert await fl.is_florence_loaded()


@pytest.mark.asyncio
async def test_is_florence_loaded_false_when_not_loaded(monkeypatch):
    catalog = [
        {
            "key": "florence-2-base-nsfw-v2-ext-mlx",
            "loaded_instances": [],
        }
    ]

    async def fake_catalog(_client):
        return catalog

    monkeypatch.setattr(fl, "fetch_lm_studio_catalog", fake_catalog)
    assert not await fl.is_florence_loaded()


@pytest.mark.asyncio
async def test_ensure_florence_loaded_skips_when_already_active(monkeypatch):
    async def loaded(_client=None):
        return True

    monkeypatch.setattr(fl, "is_florence_loaded", loaded)
    assert await fl.ensure_florence_loaded()
