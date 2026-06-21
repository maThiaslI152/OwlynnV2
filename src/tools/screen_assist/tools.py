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
async def get_active_browser_screenshot() -> str:
    """
    Return a base64 encoded jpeg screenshot of the user's active browser tab.

    This command requires the Owlynn Browser Bridge extension. Use this when you
    need visual context of the user's active page.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    gw = get_screen_assist_gateway()
    b64 = await gw.capture_browser_screenshot()
    if not b64:
        return "Error: Could not capture browser screenshot (extension may be disconnected)."
    # The vision proxy interceptor expects image_urls in dict block format
    # In LangChain tools, we return a JSON string or dict that indicates an image.
    import json

    return json.dumps({"vision_interception_required": True, "image_url": b64})


@tool
async def active_browser_action(
    action: str,
    selector: str = "",
    text: str = "",
    y: int = 0,
    element_id: int = -1,
    element_ids: list[int] = None,
) -> str:
    """
    Perform an action in the user's active browser tab (Brave/Chrome extension only).

    Supported actions:
    - 'read_dom_tree': Returns a distilled map of interactive elements with unique IDs (e.g., [@12]). Use this FIRST.
    - 'read_full_dom_tree': Same as read_dom_tree, but also includes all visible text on the page. Use this to read quiz questions or full context.
    - 'click': Click element matching 'selector' OR 'element_id'. Can also accept 'element_ids' list to batch-click multiple elements (e.g., answering a quiz).
    - 'hover': Hover over element matching 'selector' OR 'element_id' without clicking. Useful for expanding menus or revealing tooltips.
    - 'type': Type 'text' into input matching 'selector' OR 'element_id'. Can also batch-type into 'element_ids'.
    - 'show_hints': Draws numbered overlays over all clickable elements. Returns the total count. Call this BEFORE taking a screenshot to see numbers!
    - 'get_html': Returns the raw outerHTML of all elements matching 'selector'. Use this to read the DOM structure (like radio button values) before clicking.
    - 'scroll': Scroll the page down by 'y' pixels.
    - 'go_back': Navigate back in browser history.
    - 'go_forward': Navigate forward in browser history.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    try:
        from src.api.routes.browser_extension import (
            dispatch_extension_browser_action,
            is_extension_connected,
        )

        if not is_extension_connected():
            return "Error: Browser extension is not connected."

        res = await dispatch_extension_browser_action(
            action, selector, text, y, element_id, element_ids
        )
        if res.get("success"):
            extras = {k: v for k, v in res.items() if k != "success"}
            if extras:
                if "dom_tree" in extras and len(extras) == 1:
                    return f"Action '{action}' executed successfully.\nDOM Tree:\n{extras['dom_tree']}"
                import json

                return f"Action '{action}' executed successfully.\nResult:\n{json.dumps(extras, indent=2)}"
            return f"Action '{action}' executed successfully."
        return f"Error: {res.get('error')}"
    except Exception as e:
        return f"Error: {str(e)}"


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


@tool
async def upload_from_workspace(selector: str, filename: str) -> str:
    """
    Upload a file from the active workspace into a file input on the active browser tab.
    This bypasses extension restrictions by using Playwright CDP.

    Args:
        selector: The CSS selector for the <input type="file"> element.
        filename: The filename from the workspace to upload.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.tools.core_tools import get_safe_workspace_path

    filepath, err = get_safe_workspace_path(filename)
    if err:
        return err

    import os

    if not os.path.exists(filepath):
        return f"Error: File '{filename}' not found in workspace."

    from src.config.config_loader import config

    cdp_url = config.get("screen_assist.browser_cdp_url", "")
    if not cdp_url.strip():
        return "Error: browser_cdp_url is not configured. Start browser with --remote-debugging-port=9222 and set config."

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Error: playwright not installed."

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                return "Error: no browser contexts on CDP endpoint."
            page = browser.contexts[0].pages[0] if browser.contexts[0].pages else None
            if page is None:
                return "Error: no active page on CDP endpoint."

            await page.set_input_files(selector, filepath)
            return f"Successfully set file input '{selector}' to '{filename}'."
    except Exception as exc:
        return f"Error: CDP upload failed ({exc})"


SCREEN_ASSIST_TOOLS = [
    capture_local_terminal,
    read_screen_element,
    get_active_browser_context,
    get_active_browser_screenshot,
    active_browser_action,
    capture_kali_terminal,
    upload_from_workspace,
]
