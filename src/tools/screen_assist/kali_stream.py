"""Streaming Kali terminal — persistent SSH + tmux pipe-pane for live output."""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class KaliTerminalStreamer:
    """Streams Kali tmux pane output to connected clients via diff-based polling."""

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 60022,
        session: str = "main",
        window: str = "main",
        identity_file: str = "",
        poll_interval: float = 0.5,
    ):
        self.host = host
        self.user = user
        self.port = port
        self.session = session
        self.window = window
        self.identity_file = identity_file
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_output: str = ""
        self._subscribers: list[Callable[[str, str], Awaitable[None]]] = []
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "[kali_stream] Started streaming from %s:%s", self.host, self.session
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[kali_stream] Stopped streaming")

    async def subscribe(
        self, callback: Callable[[str, str], Awaitable[None]]
    ) -> Callable[[], Awaitable[None]]:
        async with self._lock:
            self._subscribers.append(callback)
        if len(self._subscribers) == 1 and not self._running:
            await self.start()

        async def _remove():
            await self._unsubscribe(callback)

        return _remove

    async def _unsubscribe(self, callback: Callable) -> None:
        async with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
        if not self._subscribers and self._running:
            await self.stop()

    async def get_snapshot(self) -> str:
        return self._last_output

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                output = await self._capture_pane()
                if output is not None and output != self._last_output:
                    diff = self._compute_diff(self._last_output, output)
                    self._last_output = output
                    if diff:
                        await self._broadcast(diff, output)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[kali_stream] Poll error: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def _capture_pane(self) -> str | None:
        ssh_cmd = self._build_ssh_cmd()
        target = f"{self.session}:{self.window}"
        remote = f"tmux capture-pane -p -t {shlex.quote(target)} -S -500"
        ssh_cmd.append(remote)
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode != 0:
                return None
            return stdout.decode("utf-8", errors="replace")
        except (asyncio.TimeoutError, OSError):
            return None

    def _build_ssh_cmd(self) -> list[str]:
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
        ]
        if self.port != 22:
            cmd.extend(["-p", str(self.port)])
        if self.identity_file.strip():
            cmd.extend(["-i", self.identity_file.strip()])
        cmd.append(f"{self.user}@{self.host}")
        return cmd

    @staticmethod
    def _compute_diff(old: str, new: str) -> str:
        if not old:
            return new
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        if len(new_lines) > len(old_lines):
            return "\n".join(new_lines[len(old_lines) :]) + "\n"
        if new_lines != old_lines:
            return "\n".join(new_lines[-20:]) + "\n"
        return ""

    async def _broadcast(self, diff: str, full_snapshot: str) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                await callback(diff, full_snapshot)
            except Exception as e:
                logger.warning("[kali_stream] Subscriber error: %s", e)


_streamers: dict[str, KaliTerminalStreamer] = {}


def get_terminal_streamer(
    host: str = "127.0.0.1",
    user: str = "kali",
    port: int = 60022,
    session: str = "main",
    window: str = "main",
    identity_file: str = "~/.lima/_config/user",
) -> KaliTerminalStreamer:
    key = f"{host}:{port}:{session}:{window}"
    if key not in _streamers:
        _streamers[key] = KaliTerminalStreamer(
            host=host,
            user=user,
            port=port,
            session=session,
            window=window,
            identity_file=identity_file,
        )
    return _streamers[key]


async def stop_all_streamers() -> None:
    for streamer in _streamers.values():
        await streamer.stop()
    _streamers.clear()
