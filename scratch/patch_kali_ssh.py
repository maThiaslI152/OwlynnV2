import re

with open("src/tools/screen_assist/kali_ssh.py", "r") as f:
    content = f.read()

# Patch capture_remote_tmux_pane
old_capture = """async def capture_remote_tmux_pane(
    *,
    host: str,
    user: str,
    session: str,
    port: int = 22,
    lines: int = 200,
    identity_file: str = "",
    timeout: float = 30.0,
) -> str:"""
new_capture = """async def capture_remote_tmux_pane(
    *,
    host: str,
    user: str,
    session: str,
    window: str = "main",
    port: int = 22,
    lines: int = 200,
    identity_file: str = "",
    timeout: float = 30.0,
) -> str:"""
content = content.replace(old_capture, new_capture)

content = content.replace(
    'remote = f"tmux capture-pane -p -t {shlex.quote(session)} -S -{max(1, lines)}"',
    'target = f"{session}:{window}"\n    remote = f"tmux capture-pane -p -t {shlex.quote(target)} -S -{max(1, lines)}"',
)

# Patch run_remote_kali_command
old_run = """async def run_remote_kali_command(
    *,
    host: str,
    user: str,
    session: str,
    command: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 60.0,
    poll_interval: float = 0.5,
) -> str:"""
new_run = """async def run_remote_kali_command(
    *,
    host: str,
    user: str,
    session: str,
    window: str = "main",
    command: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 60.0,
    poll_interval: float = 0.5,
) -> str:"""
content = content.replace(old_run, new_run)

# Inside run_remote_kali_command, we need to replace all `shlex.quote(session)` with `shlex.quote(target)`
# and add `target = f"{session}:{window}"` at the top of the function.
old_session_setup = """    session = session.strip() or "main"
    marker = f"__OWLYNN_DONE_{uuid.uuid4().hex[:12]}__\""""
new_session_setup = """    session = session.strip() or "main"
    window = window.strip() or "main"
    target = f"{session}:{window}"
    marker = f"__OWLYNN_DONE_{uuid.uuid4().hex[:12]}__\""""
content = content.replace(old_session_setup, new_session_setup)

content = content.replace(
    "tmux send-keys -t {shlex.quote(session)}",
    "tmux send-keys -t {shlex.quote(target)}",
)
content = content.replace(
    "tmux capture-pane -p -t {shlex.quote(session)}",
    "tmux capture-pane -p -t {shlex.quote(target)}",
)

with open("src/tools/screen_assist/kali_ssh.py", "w") as f:
    f.write(content)
