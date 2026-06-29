"""Remote Kali VM terminal capture and command execution over SSH."""

from __future__ import annotations

import asyncio
import shlex
import uuid


def _build_ssh_cmd(
    host: str,
    user: str,
    port: int = 22,
    identity_file: str = "",
) -> list[str]:
    """Build the base SSH command with appropriate options."""
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
    ]
    is_localhost = host in ("127.0.0.1", "localhost", "::1")
    if is_localhost:
        ssh_cmd.extend(
            [
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ]
        )
    if port != 22:
        ssh_cmd.extend(["-p", str(port)])
    if identity_file.strip():
        ssh_cmd.extend(["-i", identity_file.strip()])
    ssh_cmd.append(f"{user}@{host}")
    return ssh_cmd


async def _ssh_exec(
    host: str,
    user: str,
    remote_cmd: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 30.0,
) -> tuple[str, str, int]:
    """Execute a remote command via SSH. Returns (stdout, stderr, returncode)."""
    ssh_cmd = _build_ssh_cmd(host, user, port, identity_file)
    ssh_cmd.append(remote_cmd)

    proc = await asyncio.create_subprocess_exec(
        *ssh_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return "", "SSH command timed out", -1

    return (
        (stdout or b"").decode("utf-8", errors="replace"),
        (stderr or b"").decode("utf-8", errors="replace"),
        proc.returncode or 0,
    )


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

    stdout, stderr, rc = await _ssh_exec(
        host, user, remote, port, identity_file, timeout
    )

    if rc != 0:
        return f"Error: SSH capture failed ({stderr.strip() or rc})"

    if not stdout.strip():
        return f"(remote tmux session '{session}' on {host} returned empty pane)"
    return stdout


async def run_remote_kali_command(
    *,
    host: str,
    user: str,
    session: str,
    command: str,
    port: int = 22,
    identity_file: str = "",
    timeout: float = 60.0,
    poll_interval: float = 0.5,
) -> str:
    """Execute a command in the Kali tmux session and return the output.

    Uses end-marker technique: sends the command, then an echo with a unique
    marker. Polls tmux capture-pane until the marker appears, then extracts
    the output between the command and the marker.
    """
    host = host.strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    session = session.strip() or "main"
    marker = f"__OWLYNN_DONE_{uuid.uuid4().hex[:12]}__"

    # Escape the command for tmux send-keys
    escaped_cmd = command.replace("'", "'\\''")

    # Send command + end marker to tmux
    send_cmd = (
        f"tmux send-keys -t {shlex.quote(session)} {shlex.quote(escaped_cmd)} Enter && "
        f"sleep 0.1 && "
        f"tmux send-keys -t {shlex.quote(session)} {shlex.quote(f'echo {marker}')} Enter"
    )

    stdout, stderr, rc = await _ssh_exec(
        host, user, send_cmd, port, identity_file, timeout=15.0
    )
    if rc != 0:
        return f"Error: Failed to send command to Kali tmux ({stderr.strip() or rc})"

    # Poll for marker in tmux output
    import time

    deadline = time.monotonic() + timeout
    last_output = ""

    while time.monotonic() < deadline:
        capture_cmd = f"tmux capture-pane -p -t {shlex.quote(session)} -S -500"
        stdout, stderr, rc = await _ssh_exec(
            host, user, capture_cmd, port, identity_file, timeout=10.0
        )
        if rc != 0:
            await asyncio.sleep(poll_interval)
            continue

        last_output = stdout

        # Check if marker is present
        if marker in stdout:
            # Extract output between the command and the marker
            lines = stdout.split("\n")
            cmd_line_idx = -1
            marker_line_idx = -1

            for i, line in enumerate(lines):
                # Find the line containing our command (last occurrence before marker)
                if command[:40] in line and cmd_line_idx == -1:
                    cmd_line_idx = i
                if marker in line:
                    marker_line_idx = i
                    break

            if cmd_line_idx >= 0 and marker_line_idx > cmd_line_idx:
                # Output is between command line (exclusive) and marker line (exclusive)
                output_lines = lines[cmd_line_idx + 1 : marker_line_idx]
                # Remove trailing empty lines
                while output_lines and not output_lines[-1].strip():
                    output_lines.pop()
                return "\n".join(output_lines) if output_lines else "(no output)"
            elif marker_line_idx >= 0:
                # Couldn't find command line, return everything before marker
                output_lines = lines[:marker_line_idx]
                while output_lines and not output_lines[-1].strip():
                    output_lines.pop()
                return "\n".join(output_lines) if output_lines else "(no output)"

        await asyncio.sleep(poll_interval)

    # Timeout — return whatever we captured last
    return (
        f"(command timed out after {timeout}s)\n{last_output[-2000:]}"
        if last_output
        else f"Error: Command timed out after {timeout}s"
    )
