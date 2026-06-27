"""Remote Kali VM terminal capture over SSH."""

from __future__ import annotations

import asyncio
import shlex


async def capture_remote_tmux_pane(
    *,
    host: str,
    user: str,
    session: str,
    port: int = 22,
    lines: int = 200,
    identity_file: str = "",
    timeout: float = 30.0,
) -> str:
    """SSH to Kali (or any host) and run ``tmux capture-pane -p``."""
    host = host.strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    session = session.strip() or "main"
    remote = f"tmux capture-pane -p -t {shlex.quote(session)} -S -{max(1, lines)}"
    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
    ]
    if port != 22:
        ssh_cmd.extend(["-p", str(port)])
    if identity_file.strip():
        ssh_cmd.extend(["-i", identity_file.strip()])
    ssh_cmd.append(f"{user}@{host}")
    ssh_cmd.append(remote)

    proc = await asyncio.create_subprocess_exec(
        *ssh_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: SSH tmux capture timed out."

    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        return f"Error: SSH capture failed ({err or proc.returncode})"

    text = (stdout or b"").decode("utf-8", errors="replace")
    if not text.strip():
        return f"(remote tmux session '{session}' on {host} returned empty pane)"
    return text
