"""Remote Kali VM terminal capture and command execution over SSH."""

from __future__ import annotations

import asyncio
import shlex
import time
import uuid

from src.memory.pentest_engagement import get_active_engagement, store_evidence


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
    except TimeoutError:
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
    window: str = "main",
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
    target = f"{session}:{window}"
    remote = f"tmux capture-pane -p -t {shlex.quote(target)} -S -{max(1, lines)}"

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
    window: str = "main",
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
    window = window.strip() or "main"
    target = f"{session}:{window}"
    marker = f"__OWLYNN_DONE_{uuid.uuid4().hex[:12]}__"

    # Escape the command for tmux send-keys
    escaped_cmd = command.replace("'", "'\\''")

    # Send command + end marker to tmux
    send_cmd = (
        f"tmux send-keys -t {shlex.quote(target)} {shlex.quote(escaped_cmd)} Enter && "
        f"sleep 0.1 && "
        f"tmux send-keys -t {shlex.quote(target)} {shlex.quote(f'echo {marker}')} Enter"
    )

    stdout, stderr, rc = await _ssh_exec(
        host, user, send_cmd, port, identity_file, timeout=15.0
    )
    if rc != 0:
        return f"Error: Failed to send command to Kali tmux ({stderr.strip() or rc})"

    # Poll for marker in tmux output

    deadline = time.monotonic() + timeout
    last_output = ""

    while time.monotonic() < deadline:
        capture_cmd = f"tmux capture-pane -p -t {shlex.quote(target)} -S -500"
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
                final_output = (
                    "\n".join(output_lines) if output_lines else "(no output)"
                )
                return _process_output_for_evidence(final_output, command)
            elif marker_line_idx >= 0:
                # Couldn't find command line, return everything before marker
                output_lines = lines[:marker_line_idx]
                while output_lines and not output_lines[-1].strip():
                    output_lines.pop()
                final_output = (
                    "\n".join(output_lines) if output_lines else "(no output)"
                )
                return _process_output_for_evidence(final_output, command)

        await asyncio.sleep(poll_interval)

    # Timeout — return whatever we captured last
    final_output = (
        last_output if last_output else f"Error: Command timed out after {timeout}s"
    )
    return _process_output_for_evidence(final_output, command, timed_out=True)


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
    """Send literal text input (keystrokes) to a tmux window.
    Useful for interacting with msfconsole, reverse shells, etc.
    """
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
    """Create a new tmux window in the session."""
    host = host.strip()
    if not host:
        return "Error: host not configured."
    session = session.strip() or "main"

    cmd = f"tmux new-window -t {shlex.quote(session)} -n {shlex.quote(window_name)}"
    stdout, stderr, rc = await _ssh_exec(host, user, cmd, port, identity_file, timeout)
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
    """List windows in the tmux session."""
    host = host.strip()
    if not host:
        return "Error: host not configured."
    session = session.strip() or "main"

    cmd = f"tmux list-windows -t {shlex.quote(session)}"
    stdout, stderr, rc = await _ssh_exec(host, user, cmd, port, identity_file, timeout)
    if rc != 0:
        return f"Error: Failed to list windows: {stderr.strip()}"
    return stdout.strip()


def _process_output_for_evidence(
    output: str, command: str, timed_out: bool = False
) -> str:
    """Save full output to evidence store and return a truncated preview."""
    eng = get_active_engagement()
    if not eng:
        # If no engagement, just truncate it to 2000 chars and return
        if len(output) > 2000:
            return (
                output[:1000]
                + "\n... [OUTPUT TRUNCATED - NO ACTIVE ENGAGEMENT] ...\n"
                + output[-1000:]
            )
        return output

    # Save to evidence
    content_bytes = f"Command: {command}\n\n{output}".encode()

    # Extract binary name for filename
    binary = command.split()[0].split("/")[-1] if command else "command"
    filename = f"{binary}_output.log"

    sha = store_evidence(eng["id"], content_bytes, filename, "text/plain")

    # Truncate for LLM context (50 lines or ~2000 chars)
    lines = output.split("\n")
    if len(lines) > 50:
        preview = (
            "\n".join(lines[:25])
            + "\n\n... [OUTPUT TRUNCATED (Saved to Evidence)] ...\n\n"
            + "\n".join(lines[-25:])
        )
    elif len(output) > 2000:
        preview = (
            output[:1000]
            + "\n\n... [OUTPUT TRUNCATED (Saved to Evidence)] ...\n\n"
            + output[-1000:]
        )
    else:
        preview = output

    status = " (TIMED OUT)" if timed_out else ""
    return f"[Command Output{status}]\n{preview}\n\n[Full output saved to evidence_store: {sha}]"
