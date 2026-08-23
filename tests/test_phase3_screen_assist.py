"""Phase 3 screen assist: tmux, AX, browser, Kali SSH tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.routing.modes import (
    _user_wants_screen_assist,
    augment_toolbox_for_scenario,
)
from src.agent.tool_sets import TOOLBOX_REGISTRY, resolve_tools
from src.tools.screen_assist.gateway import MacScreenAssistGateway
from src.tools.screen_assist.tmux import capture_tmux_pane


@pytest.mark.asyncio
async def test_capture_tmux_pane_success():
    async def fake_exec(*cmd, **kwargs):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"root@host:~# ls\n", b""))
        proc.returncode = 0
        proc.kill = MagicMock()
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        out = await capture_tmux_pane("owlynn")

    assert "root@host" in out


@pytest.mark.asyncio
async def test_gateway_capture_terminal_uses_config():
    gw = MacScreenAssistGateway()
    with patch(
        "src.tools.screen_assist.gateway.capture_tmux_pane",
        AsyncMock(return_value="pane text"),
    ) as mock_cap:
        out = await gw.capture_terminal_pane(None)
    assert out == "pane text"
    mock_cap.assert_awaited_once()
    assert mock_cap.await_args.kwargs["lines"] == 200


@pytest.mark.asyncio
async def test_read_ax_fallback_to_vision(monkeypatch):
    from src.tools.screen_assist import ax_macos

    async def fake_proc(*_a, **_k):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"Terminal|window|10,20|", b""))
        proc.returncode = 0
        return proc

    monkeypatch.setattr(ax_macos.asyncio, "create_subprocess_exec", fake_proc)
    monkeypatch.setattr(
        ax_macos,
        "_vision_crop_fallback",
        AsyncMock(return_value="TEXT: cropped output"),
    )

    text, used_vision = await ax_macos.read_ax_context(10, 20)
    assert used_vision is True
    assert "vision_crop_fallback" in text
    assert "cropped output" in text


def test_screen_assist_toolbox_registered():
    names = {t.name for t in TOOLBOX_REGISTRY["screen_assist"]}
    assert names == {
        "capture_local_terminal",
        "read_screen_element",
        "get_active_browser_context",
        "get_active_browser_screenshot",
        "active_browser_action",
        "capture_kali_terminal",
        "run_kali_command",
        "host_browser_action",
        "capture_desktop_screenshot",
        "upload_from_workspace",
        "kali_tmux_list_windows",
        "kali_reset_vm",
        "send_kali_input",
        "kali_tmux_new_window",
    }


def test_resolve_tools_includes_screen_assist():
    tools = resolve_tools(["screen_assist"], web_search_enabled=False)
    names = {t.name for t in tools}
    assert "capture_local_terminal" in names
    assert "ask_user" in names


def test_user_wants_screen_assist_keywords():
    assert _user_wants_screen_assist("capture my tmux pane")
    assert not _user_wants_screen_assist("what is the capital of france")


def test_augment_toolbox_pentest_adds_screen_assist():
    # Pentest now replaces the toolbox entirely with ["pentest"]
    out = augment_toolbox_for_scenario(["web_search"], "pentest", "nmap scan")
    assert out == ["pentest"]
    assert augment_toolbox_for_scenario(["all"], "pentest", "nmap") == ["all"]
