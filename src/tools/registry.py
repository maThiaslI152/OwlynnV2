"""Central dynamic tool registry with prerequisite gating and sync-to-async bridging.

Inspired by Hermes tool registry:
- Self-registering tools via @registry.register
- Service-gated tools via check_fn (TTL-cached)
- Bounded tool error outputs (_MAX_TOOL_ERROR_CHARS)
- Long-lived persistent event loop for sync-to-async bridging
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# Max tool error characters to prevent context window blowup
_MAX_TOOL_ERROR_CHARS = 2048
_MAX_LOGGED_ERROR_CHARS = 8192

# Persistent event loops for sync-to-async execution
_tool_loop: asyncio.AbstractEventLoop | None = None
_tool_loop_lock = threading.Lock()
_worker_thread_local = threading.local()


def _get_tool_loop() -> asyncio.AbstractEventLoop:
    """Return a long-lived persistent event loop for sync-to-async tool calls."""
    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
        return _tool_loop


def _bound_error_text(text: str) -> str:
    """Cap oversized error messages destined for the model context."""
    if len(text) <= _MAX_TOOL_ERROR_CHARS:
        return text
    logger.debug(
        "Tool error truncated for context (%d -> %d chars): %s",
        len(text),
        _MAX_TOOL_ERROR_CHARS,
        text[:_MAX_LOGGED_ERROR_CHARS],
    )
    return (
        text[:_MAX_TOOL_ERROR_CHARS]
        + "\n[... error output truncated for context window ...]"
    )


class ToolRegistry:
    """Singleton registry for all agent tools with dynamic availability checking."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._toolboxes: dict[str, set[str]] = {}
        self._check_fns: dict[str, Callable[[], bool]] = {}
        self._check_cache: dict[str, tuple[float, bool]] = {}
        self._cache_ttl_seconds: float = 60.0

    def register(
        self,
        name: str | None = None,
        toolbox: str | list[str] | None = None,
        check_fn: Callable[[], bool] | None = None,
    ):
        """Decorator to register a LangChain tool into the registry."""

        def decorator(tool: BaseTool | Callable) -> BaseTool | Callable:
            tool_name = name or getattr(
                tool, "name", getattr(tool, "__name__", "unknown")
            )
            self._tools[tool_name] = tool

            tb_list = (
                [toolbox] if isinstance(toolbox, str) else (toolbox or ["default"])
            )
            for tb in tb_list:
                if tb not in self._toolboxes:
                    self._toolboxes[tb] = set()
                self._toolboxes[tb].add(tool_name)

            if check_fn is not None:
                self._check_fns[tool_name] = check_fn

            return tool

        return decorator

    def register_tool_instance(
        self,
        tool: BaseTool,
        toolbox: str | list[str] | None = None,
        check_fn: Callable[[], bool] | None = None,
    ):
        """Directly register an initialized BaseTool instance."""
        tool_name = tool.name
        self._tools[tool_name] = tool

        tb_list = [toolbox] if isinstance(toolbox, str) else (toolbox or ["default"])
        for tb in tb_list:
            if tb not in self._toolboxes:
                self._toolboxes[tb] = set()
            self._toolboxes[tb].add(tool_name)

        if check_fn is not None:
            self._check_fns[tool_name] = check_fn

    def is_tool_available(self, tool_name: str) -> bool:
        """Check if a tool's prerequisites are met (cached with TTL)."""
        check_fn = self._check_fns.get(tool_name)
        if check_fn is None:
            return True

        now = time.monotonic()
        cached = self._check_cache.get(tool_name)
        if cached is not None:
            ts, verdict = cached
            if now - ts < self._cache_ttl_seconds:
                return verdict

        try:
            verdict = bool(check_fn())
        except Exception as e:
            logger.debug("Prerequisite check failed for %s: %s", tool_name, e)
            verdict = False

        self._check_cache[tool_name] = (now, verdict)
        return verdict

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def get_toolbox_tools(self, toolbox: str) -> list[BaseTool]:
        """Get all available tools in a specific toolbox category."""
        tool_names = self._toolboxes.get(toolbox, set())
        return [
            self._tools[name]
            for name in sorted(tool_names)
            if name in self._tools and self.is_tool_available(name)
        ]

    def get_all_tools(self) -> list[BaseTool]:
        """Get all registered tools that pass their availability check."""
        return [
            tool
            for name, tool in sorted(self._tools.items())
            if self.is_tool_available(name)
        ]

    def clear_cache(self):
        """Clear cached availability checks."""
        self._check_cache.clear()


# Global tool registry instance
registry = ToolRegistry()
