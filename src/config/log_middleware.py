"""
Logging middleware and decorators for the Owlynn agent system.

Provides drop-in hooks that auto-log agent behaviour without requiring
invasive changes to existing node or pipeline code.

Decorators
----------
``@log_node`` — wraps a LangGraph node function (sync or async) and logs
entry, exit, duration, and exceptions.

Helpers
-------
``log_model_attempt(model, status, duration, reason)`` — log a single entry
in a model fallback chain.

``log_hitl_event(etype, tool, decision, **details)`` — log a human-in-the-loop
decision (approval, denial, scope clarification).

Middleware
----------
``AuditLogMiddleware`` — raw ASGI middleware that logs HTTP method, path,
status code, and duration. Skips WebSocket upgrade requests.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable

from src.config.audit_log import (
    audit_event,
    set_node,
    set_model,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# @log_node — wraps LangGraph node functions (sync or async)
# ══════════════════════════════════════════════════════════════════════════════


def log_node(node_name: str):
    """Decorator that logs entry, exit, and duration for a LangGraph node.

    Works with both sync and async node functions. Uses ``audit_context``
    to inject ``node`` into the enrichment context for the duration of the call.

    Usage::

        @log_node("complex_llm")
        async def complex_llm_node(state: AgentState) -> AgentState:
            ...

    The decorator:
    - Sets the ``node`` context var so nested ``audit_event`` calls get ``node``.
    - Logs ``"node_entry"`` before the call.
    - Logs ``"node_exit"`` after the call with ``duration_ms``.
    - Logs ``"node_error"`` if an exception propagates.
    """

    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            set_node(node_name)
            audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
            started = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.monotonic() - started) * 1000
                audit_event(
                    "agent.lifecycle",
                    "node_exit",
                    level=logging.DEBUG,
                    duration_ms=round(elapsed, 2),
                )
                return result
            except Exception:
                elapsed = (time.monotonic() - started) * 1000
                audit_event(
                    "agent.lifecycle",
                    "node_error",
                    level=logging.ERROR,
                    duration_ms=round(elapsed, 2),
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            set_node(node_name)
            audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
            started = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.monotonic() - started) * 1000
                audit_event(
                    "agent.lifecycle",
                    "node_exit",
                    level=logging.DEBUG,
                    duration_ms=round(elapsed, 2),
                )
                return result
            except Exception:
                elapsed = (time.monotonic() - started) * 1000
                audit_event(
                    "agent.lifecycle",
                    "node_error",
                    level=logging.ERROR,
                    duration_ms=round(elapsed, 2),
                )
                raise

        return async_wrapper if is_async else sync_wrapper

    return decorator


# ══════════════════════════════════════════════════════════════════════════════
# log_model_attempt — log a single entry in a model fallback chain
# ══════════════════════════════════════════════════════════════════════════════


def log_model_attempt(
    model: str,
    status: str,
    duration_ms: float = 0.0,
    reason: str = "",
    **extra: Any,
) -> None:
    """Log a model selection attempt (used in fallback chains).

    Parameters
    ----------
    model:
        Model label (e.g. ``"large-cloud"``, ``"medium-default"``).
    status:
        ``"success"`` or ``"failed"``.
    duration_ms:
        Time spent in the attempt (ms).
    reason:
        Why the attempt succeeded or failed (e.g. ``"initial_route"``,
        ``"fallback_rate_limit"``, ``"auth_error_401_403"``).
    """
    level = logging.INFO if status == "success" else logging.WARNING
    audit_event(
        "agent.model",
        "model_attempt",
        level=level,
        model=model,
        status=status,
        duration_ms=round(duration_ms, 2),
        reason=reason,
        **extra,
    )
    set_model(model)


# ══════════════════════════════════════════════════════════════════════════════
# log_hitl_event — log a human-in-the-loop decision
# ══════════════════════════════════════════════════════════════════════════════


def log_hitl_event(
    etype: str,
    tool: str = "",
    decision: str = "",
    **details: Any,
) -> None:
    """Log a HITL event from the security proxy, plan review, or scope clarification.

    Parameters
    ----------
    etype:
        Event type: ``"tool_classified"``, ``"hitl_interrupt"``,
        ``"hitl_approved"``, ``"hitl_denied"``, ``"hitl_skipped"``,
        ``"plan_reviewed"``, ``"scope_clarified"``.
    tool:
        Tool name if applicable (e.g. ``"write_workspace_file"``).
    decision:
        ``"approved"``, ``"denied"``, ``"skipped"``, ``"safe"``, ``"sensitive"``.
    """
    level = logging.INFO
    if decision in ("denied", "failed"):
        level = logging.WARNING

    payload: dict[str, Any] = {}
    if tool:
        payload["tool"] = tool
    if decision:
        payload["decision"] = decision
    payload.update(details)

    audit_event("agent.hitl", etype, level=level, **payload)


# ══════════════════════════════════════════════════════════════════════════════
# ASGI middleware — log HTTP requests
# ══════════════════════════════════════════════════════════════════════════════


class AuditLogMiddleware:
    """Raw ASGI middleware that logs HTTP requests (skips WebSocket upgrade).

    Attaches to the FastAPI app via::

        app.add_middleware(AuditLogMiddleware)
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            # Skip WebSocket and lifespan events
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        started = time.monotonic()

        # Capture status code
        status_code = 0

        async def _send(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed = (time.monotonic() - started) * 1000
            audit_event(
                "api.ws",
                "http_request",
                level=logging.DEBUG,
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(elapsed, 2),
            )
