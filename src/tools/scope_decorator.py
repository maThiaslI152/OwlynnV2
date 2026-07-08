"""Scope validation decorator for pentest tools.

Wraps pentest tools with automatic scope validation before execution.
Targets are extracted from tool arguments and validated against the
active engagement's scope.

Usage::

    from src.tools.scope_decorator import scope_validated

    @tool
    @scope_validated
    async def nmap_scan(target: str, ...) -> str:
        ...
"""

from __future__ import annotations

import functools
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def scope_validated(func: Callable) -> Callable:
    """Decorator that validates tool args against engagement scope before execution.

    Extracts target IPs/hosts/domains from tool arguments and validates them
    against the active engagement's scope. If any target is out of scope,
    returns a BLOCKED message instead of executing the tool.

    Only applies when an active pentest engagement exists. In non-pentest mode,
    the tool executes normally.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        from src.tools.scope_guard import guard_tool_call, extract_targets_from_args
        from src.memory.pentest_engagement import get_active_engagement

        # Only validate when an active engagement exists
        eng = get_active_engagement()
        if eng:
            tool_name = func.__name__
            # Convert positional args to kwargs for target extraction
            # Most pentest tools use keyword args, but handle positional fallback
            bound_args = kwargs.copy()
            if args:
                # Try to bind positional args to parameter names
                import inspect

                try:
                    sig = inspect.signature(func)
                    param_names = list(sig.parameters.keys())
                    for i, arg in enumerate(args):
                        if i < len(param_names):
                            bound_args[param_names[i]] = arg
                except (ValueError, IndexError):
                    pass

            allowed, reason = guard_tool_call(tool_name, bound_args)
            if not allowed:
                logger.warning(
                    "[scope] BLOCKED %s: %s (targets: %s)",
                    tool_name,
                    reason,
                    extract_targets_from_args(tool_name, bound_args),
                )
                return f"BLOCKED: {reason}"

        return await func(*args, **kwargs)

    return wrapper
