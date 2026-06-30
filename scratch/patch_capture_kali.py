with open("src/tools/screen_assist/tools.py", "r") as f:
    content = f.read()

# Replace the capture_kali_terminal implementation
old_func = """@tool
async def capture_kali_terminal(session: str = "") -> str:
    \"\"\"
    Capture tmux pane output from a remote Kali VM over SSH.

    Requires ``screen_assist.kali.host`` in config. Session defaults to ``kali.tmux_session``.
    \"\"\"
    if not _enabled():
        return "Error: screen assist is disabled in configuration."
    gw = get_screen_assist_gateway()
    return await gw.capture_kali_pane(session or None)"""

new_func = """@tool
async def capture_kali_terminal(window: str = "main", lines: int = 200) -> str:
    \"\"\"
    Capture tmux pane output from a remote Kali VM over SSH.

    Args:
        window: The tmux window name (default: "main").
        lines: The number of lines to capture.
    \"\"\"
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
    )"""

content = content.replace(old_func, new_func)

with open("src/tools/screen_assist/tools.py", "w") as f:
    f.write(content)
