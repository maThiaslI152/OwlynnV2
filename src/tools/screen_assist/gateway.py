"""macOS screen-assist gateway — tmux, AX, browser, Kali SSH."""

from __future__ import annotations

from src.config.config_loader import config
from src.tools.screen_assist.ax_macos import read_ax_context
from src.tools.screen_assist.browser import active_browser_tab, browser_dom_snapshot
from src.tools.screen_assist.kali_ssh import capture_remote_tmux_pane
from src.tools.screen_assist.tmux import capture_tmux_pane


class MacScreenAssistGateway:
    """Headless Python orchestration for terminal + UI context (macOS)."""

    async def capture_terminal_pane(self, session: str | None = None) -> str:
        name = (session or "").strip() or str(
            config.get("screen_assist.tmux_session", "owlynn")
        )
        lines = int(config.get("screen_assist.tmux_history_lines", 200))
        return await capture_tmux_pane(name, lines=lines)

    async def read_ax_at(self, x: int, y: int) -> str:
        text, _ = await read_ax_context(x, y)
        return text

    async def active_browser_url(self) -> str:
        if bool(config.get("browser_extension.active_tab_enabled", True)):
            try:
                from src.api.routes.browser_extension import (
                    dispatch_extension_get_active_tab,
                    format_active_tab_context,
                    is_extension_connected,
                )

                if is_extension_connected():
                    tab = await dispatch_extension_get_active_tab()
                    if tab:
                        return format_active_tab_context(tab)
            except Exception:
                pass

        tab = await active_browser_tab()
        cdp = str(config.get("screen_assist.browser_cdp_url", "") or "")
        if cdp and not tab.startswith("Error"):
            dom = await browser_dom_snapshot(cdp)
            if dom and not dom.startswith("Error"):
                return f"{tab}\n--- dom ---\n{dom}"
        return tab

    async def capture_browser_screenshot(self) -> str | None:
        if bool(config.get("browser_extension.active_tab_enabled", True)):
            try:
                from src.api.routes.browser_extension import (
                    dispatch_extension_capture_screenshot,
                    is_extension_connected,
                )

                if is_extension_connected():
                    return await dispatch_extension_capture_screenshot()
            except Exception:
                pass
        return None

    async def capture_kali_pane(self, session: str | None = None) -> str:
        kali = config.get("screen_assist.kali") or {}
        return await capture_remote_tmux_pane(
            host=str(kali.get("host", "") or ""),
            user=str(kali.get("user", "kali") or "kali"),
            session=(session or "").strip()
            or str(kali.get("tmux_session", "main") or "main"),
            port=int(kali.get("port", 22) or 22),
            lines=int(kali.get("history_lines", 200) or 200),
            identity_file=str(kali.get("identity_file", "") or ""),
        )


_gateway: MacScreenAssistGateway | None = None


def get_screen_assist_gateway() -> MacScreenAssistGateway:
    global _gateway
    if _gateway is None:
        _gateway = MacScreenAssistGateway()
    return _gateway
