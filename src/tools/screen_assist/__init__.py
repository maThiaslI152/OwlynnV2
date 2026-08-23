"""Screen assist — headless macOS terminal, AX, browser, Kali SSH."""

from __future__ import annotations

from typing import Protocol

from src.tools.screen_assist.gateway import (
    MacScreenAssistGateway,
    get_screen_assist_gateway,
)
from src.tools.screen_assist.tools import SCREEN_ASSIST_TOOLS

__all__ = [
    "SCREEN_ASSIST_TOOLS",
    "MacScreenAssistGateway",
    "ScreenAssistGateway",
    "get_screen_assist_gateway",
]


class ScreenAssistGateway(Protocol):
    async def capture_terminal_pane(self, session: str) -> str: ...

    async def read_ax_at(self, x: int, y: int) -> str: ...

    async def active_browser_url(self) -> str: ...
