"""Startup preload behavior — unified local model preloading and Eco-Mode battery skipping."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_preload_on_ac_power_initializes_main_llm():
    """On AC power, startup preload initializes main LLM and runs default swap."""
    swap_mock = AsyncMock()
    main_llm_mock = AsyncMock()

    async def fake_preload():
        from src.api.power_monitor import is_on_battery

        if os.getenv("OWLYNN_NO_PRELOAD") == "1":
            return

        if await is_on_battery():
            return

        await swap_mock()
        await main_llm_mock()

    with (
        patch(
            "src.api.power_monitor.is_on_battery",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch.dict(os.environ, {"OWLYNN_NO_PRELOAD": "0"}, clear=False),
    ):
        await fake_preload()

    swap_mock.assert_called_once()
    main_llm_mock.assert_called_once()


@pytest.mark.asyncio
async def test_preload_skips_heavy_llm_when_on_battery():
    """When running on battery (Eco-Mode), startup skips heavy LLM preloading."""
    main_llm_mock = AsyncMock()
    swap_mock = AsyncMock()
    eco_mode_activated = False

    async def fake_preload():
        nonlocal eco_mode_activated
        from src.api.power_monitor import is_on_battery

        if os.getenv("OWLYNN_NO_PRELOAD") == "1":
            return

        if await is_on_battery():
            eco_mode_activated = True
            return

        await swap_mock()
        await main_llm_mock()

    with (
        patch(
            "src.api.power_monitor.is_on_battery",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.dict(os.environ, {"OWLYNN_NO_PRELOAD": "0"}, clear=False),
    ):
        await fake_preload()

    assert eco_mode_activated is True
    swap_mock.assert_not_called()
    main_llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_preload_skips_when_env_var_set():
    """When OWLYNN_NO_PRELOAD=1 is set, preload exits immediately."""
    main_llm_mock = AsyncMock()

    async def fake_preload():
        if os.getenv("OWLYNN_NO_PRELOAD") == "1":
            return
        await main_llm_mock()

    with patch.dict(os.environ, {"OWLYNN_NO_PRELOAD": "1"}):
        await fake_preload()

    main_llm_mock.assert_not_called()
