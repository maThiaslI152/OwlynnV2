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
    Use this FIRST whenever the user asks about their "current page" (e.g., Moodle, assignments, grades) or wants to know what text is on the page, or asks "what page am I on".

    Prefers the Owlynn Browser Bridge extension (Brave/Chrome) when connected;
    otherwise falls back to AppleScript (Chrome, Safari, Arc) and optional Playwright CDP.

    This tool ONLY returns text context, not visual layout. DO NOT use this tool if the user asks "what you can see", mentions the "screen", or requests visual confirmation. Use `get_active_browser_screenshot` instead for visual requests.
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
    need visual context of the user's active page, or when the user explicitly asks "what can you see", mentions the "screen", or requests visual confirmation.
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
async def capture_kali_terminal(window: str = "main", lines: int = 200) -> str:
    """
    Capture tmux pane output from a remote Kali VM over SSH.

    Args:
        window: The tmux window name (default: "main").
        lines: The number of lines to capture.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.tools.screen_assist.kali_ssh import capture_remote_tmux_pane
    from src.config.config_loader import config

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    return await capture_remote_tmux_pane(
        host=host,
        user=str(kali.get("user", "kali")),
        session=str(kali.get("tmux_session", "main")),
        window=window,
        port=int(kali.get("port", 22)),
        lines=lines,
        identity_file=str(kali.get("identity_file", "")),
    )


@tool
async def run_kali_command(
    command: str, window: str = "main", timeout: int = 60
) -> str:
    """
    Execute a command in the Kali VM tmux session and return the output.

    Sends the command via tmux send-keys, waits for completion using an end
    marker, then captures and returns the output. This is the primary way
    to run pentest tools (nmap, nikto, sqlmap, hydra, etc.) on Kali.

    Args:
        command: The shell command to execute in Kali (e.g., "nmap -sV 10.0.0.1").
        timeout: Max seconds to wait for command completion (default 60).
        window: The tmux window name (default: "main").
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.tools.screen_assist.kali_ssh import run_remote_kali_command
    from src.config.config_loader import config

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    return await run_remote_kali_command(
        host=host,
        user=str(kali.get("user", "kali")),
        session=str(kali.get("tmux_session", "main")),
        window=window,
        command=command,
        port=int(kali.get("port", 22)),
        identity_file=str(kali.get("identity_file", "")),
        timeout=float(timeout),
    )


@tool
async def host_browser_action(
    action: str,
    url: str = "",
    selector: str = "",
    text: str = "",
    element_id: int = -1,
) -> str:
    """
    Interact with a web-based tool running on the host Mac (e.g., Burp Suite, OWASP ZAP).

    Uses the Owlynn Browser Bridge extension to navigate to and interact with
    web-based pentest tool UIs. These tools run on the host Mac, NOT in Kali.

    Supported actions:
    - 'navigate_to': Navigate to the tool's URL (e.g., http://localhost:8080 for Burp).
    - 'read_dom_tree': Read the interactive elements of the tool's UI.
    - 'read_full_dom_tree': Read all visible text + interactive elements.
    - 'click': Click an element by selector or element_id.
    - 'type': Type text into an input field.
    - 'get_html': Get raw HTML of matching elements.

    Common tool URLs:
    - Burp Suite: http://localhost:8080
    - OWASP ZAP: http://localhost:8081

    Args:
        action: The action to perform (navigate_to, read_dom_tree, read_full_dom_tree, click, type, get_html).
        url: The URL to navigate to (required for navigate_to action).
        selector: CSS selector for click/type/get_html actions.
        text: Text to type (for type action).
        element_id: Element ID from read_dom_tree (alternative to selector).
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    try:
        from src.api.routes.browser_extension import (
            dispatch_extension_browser_action,
            is_extension_connected,
        )

        if not is_extension_connected():
            return "Error: Browser extension is not connected. Connect the Owlynn Browser Bridge extension in Brave/Chrome."

        if action == "navigate_to":
            if not url:
                return "Error: URL is required for navigate_to action."
            # Use the extension to navigate to the tool URL
            res = await dispatch_extension_browser_action(
                "navigate", "", url, 0, -1, None
            )
            if res.get("success"):
                return f"Navigated to {url}. Use 'read_dom_tree' to see the tool's UI elements."
            return f"Error navigating to {url}: {res.get('error')}"

        # For other actions, use the extension directly
        res = await dispatch_extension_browser_action(
            action, selector, text, 0, element_id, None
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


@tool
async def send_kali_input(text: str, window: str = "main") -> str:
    """
    Send literal text input (keystrokes) to a running tmux window in the Kali VM.

    This is essential for interacting with tools that don't exit automatically,
    such as msfconsole, reverse shells (nc -lvnp), or interactive prompts.

    Args:
        text: The exact keystrokes to send.
        window: The tmux window name (default: "main").
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.tools.screen_assist.kali_ssh import send_remote_kali_input
    from src.config.config_loader import config

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    return await send_remote_kali_input(
        host=host,
        user=str(kali.get("user", "kali")),
        session=str(kali.get("tmux_session", "main")),
        window=window,
        text=text,
        port=int(kali.get("port", 22)),
        identity_file=str(kali.get("identity_file", "")),
    )


@tool
async def kali_tmux_new_window(window_name: str) -> str:
    """
    Create a new tmux window in the Kali VM.

    Useful when you need to run multiple tools in parallel (e.g., starting a listener
    in one window, and running an exploit in another).

    Args:
        window_name: A short, descriptive name for the window (e.g., "listener", "nmap").
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.tools.screen_assist.kali_ssh import create_remote_tmux_window
    from src.config.config_loader import config

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()

    return await create_remote_tmux_window(
        host=host,
        user=str(kali.get("user", "kali")),
        session=str(kali.get("tmux_session", "main")),
        window_name=window_name,
        port=int(kali.get("port", 22)),
    )


@tool
async def kali_tmux_list_windows() -> str:
    """
    List all active tmux windows in the Kali VM.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.tools.screen_assist.kali_ssh import list_remote_tmux_windows
    from src.config.config_loader import config

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()

    return await list_remote_tmux_windows(
        host=host,
        user=str(kali.get("user", "kali")),
        session=str(kali.get("tmux_session", "main")),
        port=int(kali.get("port", 22)),
    )


@tool
async def kali_reset_vm() -> str:
    """
    Reset the Kali VM to a clean state.

    This is useful between engagements to ensure no files or states leak from one pentest to another.
    Note: This will delete all files in the kali user's home directory and recreate the default tmux session.
    """
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.config.config_loader import config
    import asyncio

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    # Execute cleanup script via SSH
    user = str(kali.get("user", "kali"))
    port = int(kali.get("port", 22))
    identity_file = str(kali.get("identity_file", ""))

    cmd = "killall tmux; rm -rf /home/kali/*; tmux new-session -d -s main -n shell"

    from src.tools.screen_assist.kali_ssh import _ssh_exec

    # Try to use Lima snapshots first
    import subprocess

    vm_name = str(kali.get("vm_name", "owlynn-kali"))

    # Check if 'clean' snapshot exists
    snap_check = subprocess.run(
        ["limactl", "snapshot", "list", vm_name], capture_output=True, text=True
    )
    if "clean" in snap_check.stdout:
        # Restore the snapshot
        res = subprocess.run(
            ["limactl", "snapshot", "restore", vm_name, "clean"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return "Successfully restored Kali VM to the 'clean' snapshot."

    # Fallback/Initial setup: run manual cleanup, then save as 'clean' snapshot
    stdout, stderr, rc = await _ssh_exec(
        host, user, cmd, port, identity_file, timeout=10.0
    )

    if rc != 0:
        return f"Error: Failed to reset VM: {stderr.strip()}"

    # Take a snapshot for next time
    subprocess.run(
        ["limactl", "snapshot", "create", vm_name, "--tag", "clean"],
        capture_output=True,
    )

    return "Successfully reset Kali VM to a clean state and created 'clean' snapshot for future resets."


SCREEN_ASSIST_TOOLS = [
    capture_local_terminal,
    read_screen_element,
    get_active_browser_context,
    get_active_browser_screenshot,
    active_browser_action,
    capture_kali_terminal,
    run_kali_command,
    send_kali_input,
    kali_tmux_new_window,
    kali_tmux_list_windows,
    kali_reset_vm,
    host_browser_action,
    upload_from_workspace,
]
