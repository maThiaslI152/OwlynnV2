"""LangChain tools for screen assist (read-only context capture)."""

from __future__ import annotations

from langchain_core.tools import tool

from src.config.config_loader import config
from src.tools.screen_assist.gateway import get_screen_assist_gateway


def _enabled() -> bool:
    return bool(config.get("screen_assist.enabled", True))


@tool
async def capture_local_terminal(session: str = "") -> str:
    """
    Capture visible text from a local macOS tmux session (``capture-pane -p``).

    Use when the user refers to their terminal, tmux pane, or shell output on this Mac.
    ``session`` overrides the default from config (``screen_assist.tmux_session``).
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    gw = get_screen_assist_gateway()
    return await gw.capture_terminal_pane(session or None)


@tool
async def read_screen_element(x: int, y: int) -> str:
    """
    Read UI context at screen coordinates (macOS Accessibility API).

    Falls back to a local vision crop + OCR when AX returns no text (blindspot).
    Coordinates are in screen pixels (origin top-left).
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    gw = get_screen_assist_gateway()
    return await gw.read_ax_at(x, y)


@tool
async def get_active_browser_context() -> str:
    """
    Return the active browser tab URL, title, page text, and selection.

    Prefers the Owlynn Browser Bridge extension (Brave/Chrome) when connected;
    otherwise falls back to AppleScript (Chrome, Safari, Arc) and optional Playwright CDP.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    gw = get_screen_assist_gateway()
    return await gw.active_browser_url()


@tool
async def capture_kali_terminal(session: str = "") -> str:
    """
    Capture tmux pane output from a remote Kali VM over SSH.

    Requires ``screen_assist.kali.host`` in config. Session defaults to ``kali.tmux_session``.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    gw = get_screen_assist_gateway()
    return await gw.capture_kali_pane(session or None)


SCREEN_ASSIST_TOOLS = [
    capture_local_terminal,
    read_screen_element,
    get_active_browser_context,
    capture_kali_terminal,
]
