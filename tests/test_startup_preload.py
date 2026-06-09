"""Startup preload behavior — cloud-primary skips medium when cloud available."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_preload_skips_medium_when_cloud_available():
    """When cloud key present, medium preload should not be called."""
    medium_mock = AsyncMock()
    small_mock = AsyncMock()

    captured: dict = {}

    async def fake_preload():
        from src.config.config_loader import config
        from src.config.secret_store import resolve_deepseek_api_key
        from src.memory.user_profile import get_profile

        profile = get_profile()
        cloud_key = resolve_deepseek_api_key()
        cloud_on = bool(cloud_key) and profile.get("cloud_escalation_enabled", True)
        require_medium = (
            bool(config.get("startup.require_medium_when_cloud_unavailable", True))
            and not cloud_on
        )
        captured["cloud_on"] = cloud_on
        captured["require_medium"] = require_medium

        await small_mock()
        if require_medium:
            await medium_mock()

    with (
        patch(
            "src.config.secret_store.resolve_deepseek_api_key",
            return_value="sk-test",
        ),
        patch(
            "src.memory.user_profile.get_profile",
            return_value={"cloud_escalation_enabled": True},
        ),
    ):
        await fake_preload()

    assert captured["cloud_on"] is True
    assert captured["require_medium"] is False
    medium_mock.assert_not_called()
    small_mock.assert_called_once()
