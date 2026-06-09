"""Local tmux pane capture (macOS terminal)."""

from __future__ import annotations

import asyncio
import shlex


async def capture_tmux_pane(
    session: str,
    *,
    lines: int = 200,
    timeout: float = 10.0,
) -> str:
    """Return visible tmux pane text via ``capture-pane -p``."""
    session = session.strip()
    if not session:
        return "Error: tmux session name is required."

    cmd = [
        "tmux",
        "capture-pane",
        "-p",
        "-t",
        session,
        "-S",
        f"-{max(1, lines)}",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: tmux capture timed out."

    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        return f"Error: tmux capture failed ({err or proc.returncode})"

    text = (stdout or b"").decode("utf-8", errors="replace")
    if not text.strip():
        return f"(tmux session '{session}' returned empty pane)"
    return text
