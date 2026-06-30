with open("src/tools/screen_assist/tools.py", "r") as f:
    content = f.read()

new_tools = """
@tool
async def send_kali_input(text: str, window: str = "main") -> str:
    \"\"\"
    Send literal text input (keystrokes) to a running tmux window in the Kali VM.
    
    This is essential for interacting with tools that don't exit automatically, 
    such as msfconsole, reverse shells (nc -lvnp), or interactive prompts.
    
    Args:
        text: The exact keystrokes to send. 
        window: The tmux window name (default: "main").
    \"\"\"
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
    \"\"\"
    Create a new tmux window in the Kali VM.
    
    Useful when you need to run multiple tools in parallel (e.g., starting a listener
    in one window, and running an exploit in another).
    
    Args:
        window_name: A short, descriptive name for the window (e.g., "listener", "nmap").
    \"\"\"
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
    \"\"\"
    List all active tmux windows in the Kali VM.
    \"\"\"
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
"""

if "async def send_kali_input" not in content:
    content = content.replace(
        "SCREEN_ASSIST_TOOLS =", new_tools + "\nSCREEN_ASSIST_TOOLS ="
    )

with open("src/tools/screen_assist/tools.py", "w") as f:
    f.write(content)
