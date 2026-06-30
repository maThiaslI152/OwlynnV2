import re

with open("src/tools/screen_assist/kali_ssh.py", "r") as f:
    content = f.read()

# Add send_remote_kali_input
new_functions = """

async def send_remote_kali_input(
    *,
    host: str,
    user: str,
    session: str,
    window: str = "main",
    text: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 15.0,
) -> str:
    \"\"\"Send literal text input (keystrokes) to a tmux window.
    Useful for interacting with msfconsole, reverse shells, etc.
    \"\"\"
    host = host.strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    session = session.strip() or "main"
    window = window.strip() or "main"
    target = f"{session}:{window}"

    # Use tmux send-keys. We use -l for literal string so we don't have to escape special chars.
    # To send Enter, the caller should include '\n' in the text, or we can just send it.
    # Let's just escape it manually to avoid issues.
    escaped_text = text.replace("'", "'\\''")
    send_cmd = f"tmux send-keys -t {shlex.quote(target)} -l {shlex.quote(text)} && tmux send-keys -t {shlex.quote(target)} Enter"
    # Actually wait, if the text already contains newlines, -l might send them as literal newlines which tmux handles.
    # But wait, if they just want to type "exploit" and press enter, they can send "exploit\\n".
    # Let's just use regular send-keys without -l, but properly quoted. Wait, -l is safer for raw input.
    # Actually, if we just use python's shlex.quote, we can pass it without -l.
    
    send_cmd = f"tmux send-keys -t {shlex.quote(target)} {shlex.quote(text)}"

    stdout, stderr, rc = await _ssh_exec(
        host, user, send_cmd, port, identity_file, timeout
    )
    if rc != 0:
        return f"Error: Failed to send input ({stderr.strip() or rc})"
    return f"Sent input to {target}"

async def create_remote_tmux_window(
    *,
    host: str,
    user: str,
    session: str,
    window_name: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 15.0,
) -> str:
    \"\"\"Create a new tmux window in the session.\"\"\"
    host = host.strip()
    if not host:
        return "Error: host not configured."
    session = session.strip() or "main"
    
    cmd = f"tmux new-window -t {shlex.quote(session)} -n {shlex.quote(window_name)}"
    stdout, stderr, rc = await _ssh_exec(
        host, user, cmd, port, identity_file, timeout
    )
    if rc != 0:
        return f"Error: Failed to create window '{window_name}': {stderr.strip()}"
    return f"Created new window: {window_name}"

async def list_remote_tmux_windows(
    *,
    host: str,
    user: str,
    session: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 15.0,
) -> str:
    \"\"\"List windows in the tmux session.\"\"\"
    host = host.strip()
    if not host:
        return "Error: host not configured."
    session = session.strip() or "main"
    
    cmd = f"tmux list-windows -t {shlex.quote(session)}"
    stdout, stderr, rc = await _ssh_exec(
        host, user, cmd, port, identity_file, timeout
    )
    if rc != 0:
        return f"Error: Failed to list windows: {stderr.strip()}"
    return stdout.strip()
"""
content = content + new_functions

with open("src/tools/screen_assist/kali_ssh.py", "w") as f:
    f.write(content)
