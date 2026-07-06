"""
Structured audit logging for the Owlynn agent system.

Provides channel-based JSON-line logging with context propagation
via ``contextvars``, per-channel level filtering, and dual output:
stdout (human-readable) + rotating JSON file (machine-readable).

Primary API
-----------
``audit_event(channel, event, **data)``
    Emit a structured log event to a named channel.

``audit_context(**ctx)``
    Context manager that injects enrichment keys (thread_id, node, route, etc.)
    into all ``audit_event`` calls made within its scope.

``set_thread_id(tid)`` / ``get_thread_id()``
    Set / read the current thread_id from the ``ContextVar``.

Channels
--------
- ``agent.lifecycle`` — Node entry/exit, graph routing edges
- ``agent.model``    — Model selection, fallback, swap, load/unload
- ``agent.hitl``     — Security proxy, plan review, scope clarification
- ``agent.tool``     — Tool invocation, duration, success/error
- ``agent.token``    — Budget allocation, summarization, tracking
- ``memory.inject``  — Mem0 search, context assembly, cache hits
- ``memory.write``   — Fact extraction, dedup, save to Mem0/STM
- ``memory.cache``   — TTL cache hit/miss/invalidate
- ``memory.ltm``     — Mem0/Qdrant add/search/delete/clear, init failures
- ``memory.stm``     — STM (memories.json) save/load/delete/cap
- ``memory.summarize`` — Summarization trigger, tokens freed, fallback
- ``memory.topics``  — Topic extraction, interest tracking, decay
- ``api.ws``         — WebSocket connect/disconnect/events
- ``api.file``       — File upload, watcher, processing
- ``system``         — Startup, shutdown, config changes
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.config.config_loader import config as _app_config

logger = logging.getLogger(__name__)

# ── Context propagation ──────────────────────────────────────────────────────

_thread_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "audit_thread_id", default=""
)
_node_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "audit_node", default=""
)
_route_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "audit_route", default=""
)
_model_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "audit_model", default=""
)

# Additional enrichment dict (set by `audit_context` or middleware)
_extra_var: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "audit_extra", default={}
)


def set_thread_id(tid: str) -> None:
    """Set the current thread ID for audit enrichment."""
    _thread_id_var.set(tid)


def get_thread_id() -> str:
    """Return the current thread ID, or empty string."""
    return _thread_id_var.get()


def set_node(node: str) -> None:
    """Set the current LangGraph node name."""
    _node_var.set(node)


def set_route(route: str) -> None:
    """Set the current agent route."""
    _route_var.set(route)


def set_model(model: str) -> None:
    """Set the current model label."""
    _model_var.set(model)


@contextmanager
def audit_context(**ctx: Any):
    """Context manager that injects enrichment into all nested ``audit_event`` calls.

    Example::

        with audit_context(thread_id="abc-123", node="router"):
            audit_event("agent.lifecycle", "decision", route="complex-cloud")
    """
    # Merge with existing extras
    existing = _extra_var.get().copy()
    existing.update(ctx)
    token = _extra_var.set(existing)
    try:
        yield
    finally:
        _extra_var.reset(token)


# ── Channel definitions ──────────────────────────────────────────────────────

CHANNELS = frozenset(
    {
        "agent.lifecycle",
        "agent.model",
        "agent.hitl",
        "agent.tool",
        "agent.token",
        "memory.inject",
        "memory.write",
        "memory.cache",
        "memory.ltm",
        "memory.stm",
        "memory.summarize",
        "memory.topics",
        "api.ws",
        "api.file",
        "system",
    }
)

# Default per-channel levels (INFO = only important events; DEBUG = all events)
_DEFAULT_CHANNEL_LEVELS: dict[str, int] = {
    "agent.lifecycle": logging.DEBUG,
    "agent.model": logging.INFO,
    "agent.hitl": logging.INFO,
    "agent.tool": logging.INFO,
    "agent.token": logging.DEBUG,
    "memory.inject": logging.DEBUG,
    "memory.write": logging.INFO,
    "memory.cache": logging.DEBUG,
    "memory.ltm": logging.INFO,
    "memory.stm": logging.INFO,
    "memory.summarize": logging.INFO,
    "memory.topics": logging.DEBUG,
    "api.ws": logging.INFO,
    "api.file": logging.INFO,
    "system": logging.INFO,
}

# ── Runtime configuration ────────────────────────────────────────────────────

# Whether file logging is active (disable in tests / headless CI)
_file_logging_enabled: bool = True

# Per-channel level overrides (set from profile at startup)
_channel_levels: dict[str, int] = dict(_DEFAULT_CHANNEL_LEVELS)

# Rotating file handler reference
_file_handler: RotatingFileHandler | None = None


def _resolve_audit_dir() -> Path:
    """Return the audit log directory, respecting env var override."""
    env_dir = os.environ.get("OWLYNN_AUDIT_LOG_DIR")
    if env_dir is not None:
        if env_dir == "":
            return Path()  # Sentinel: empty path disables file logging
        return Path(env_dir).expanduser().resolve()

    # Default: try profile setting, fall back to ~/.owlynn/logs/
    try:
        from src.memory.user_profile import get_profile

        profile = get_profile()
        audit_dir_str = profile.get("audit_log_dir", "")
        if audit_dir_str:
            return Path(audit_dir_str).expanduser().resolve()
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass
    return Path.home() / ".owlynn" / "logs"


def _setup_file_handler() -> RotatingFileHandler | None:
    """Create a rotating file handler for audit.jsonl."""
    global _file_handler

    audit_dir = _resolve_audit_dir()
    if audit_dir == Path() or audit_dir == Path(""):
        return None  # File logging disabled

    audit_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = audit_dir / "audit.jsonl"

    max_bytes = int(_app_config.get("audit.max_bytes", 10 * 1024 * 1024))
    backup_count = int(_app_config.get("audit.backup_count", 5))

    handler = RotatingFileHandler(
        str(jsonl_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _file_handler = handler

    # Also attach errors-only handler
    errors_path = audit_dir / "audit-errors.jsonl"
    err_max_bytes = int(_app_config.get("audit.error_max_bytes", 5 * 1024 * 1024))
    err_backup_count = int(_app_config.get("audit.error_backup_count", 3))
    err_handler = RotatingFileHandler(
        str(errors_path),
        maxBytes=err_max_bytes,
        backupCount=err_backup_count,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(logging.Formatter("%(message)s"))
    # We'll manage this separately via audit_logger
    err_handler.name = "audit_errors_handler"

    root = logging.getLogger("audit")
    root.addHandler(handler)
    root.addHandler(err_handler)
    root.setLevel(logging.DEBUG)
    root.propagate = False

    return handler


# Specialized logger for audit events (separate from app logger)
_audit_logger = logging.getLogger("audit")


def configure_audit_log(
    channel_levels: dict[str, str] | None = None,
    enabled: bool = True,
) -> None:
    """Configure audit log levels and enable/disable file output.

    Called once at startup (from ``setup_logging``) and can be called again
    if the user updates profile settings.

    Parameters
    ----------
    channel_levels:
        Dict of channel → level name (e.g. ``{"agent.model": "DEBUG"}``).
        Unspecified channels keep their defaults.
    enabled:
        If False, disable all audit file output.
    """
    global _file_logging_enabled, _channel_levels

    _file_logging_enabled = enabled

    if channel_levels:
        for channel, level_name in channel_levels.items():
            if channel in CHANNELS:
                numeric = getattr(logging, level_name.upper(), logging.INFO)
                _channel_levels[channel] = numeric

    if enabled:
        _setup_file_handler()
    else:
        _teardown_file_handler()


def _teardown_file_handler() -> None:
    """Remove rotating file handlers only (preserve stdout handler)."""
    global _file_handler
    root = logging.getLogger("audit")
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler):
            h.close()
            root.removeHandler(h)
    _file_handler = None


def _channel_level(channel: str) -> int:
    """Return the numeric log level for a channel."""
    return _channel_levels.get(channel, logging.INFO)


# Chars to strip from log data values to keep JSON clean and compact
_STRIP_CHARS = set("{}[]<>;\"'")


def _sanitize_value(value: Any) -> Any:
    """Make a value safe for JSON serialization, truncating long strings."""
    max_len = 500
    if isinstance(value, str):
        if len(value) > max_len:
            value = value[:max_len] + "…"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value[:20]]  # cap list length
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in list(value.items())[:20]}
    return str(value)[:max_len]


# ── Public API ───────────────────────────────────────────────────────────────


def audit_event(
    channel: str, event: str, level: int = logging.INFO, **data: Any
) -> None:
    """Emit a structured audit event.

    Parameters
    ----------
    channel:
        Dot-separated log channel (e.g. ``"agent.model"``, ``"memory.cache"``).
        Must be one of the defined ``CHANNELS``.
    event:
        Short event name (e.g. ``"node_entry"``, ``"model_selected"``, ``"cache_hit"``).
    level:
        Python logging level (``logging.DEBUG``, ``INFO``, ``WARNING``, ``ERROR``).
        Events below the channel's configured level are dropped.
    **data:
        Arbitrary keyword data to include in the JSON payload.
        Values are auto-sanitized for JSON serialization.
    """
    if channel not in CHANNELS:
        logger.debug("Unknown audit channel: %s", channel)
        return

    chan_level = _channel_level(channel)
    if level < chan_level:
        return  # Below channel threshold — drop

    # Build enrichment context
    thread_id = _thread_id_var.get() or ""
    node = _node_var.get() or ""
    route = _route_var.get() or ""
    model = _model_var.get() or ""
    extra = _extra_var.get()

    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "channel": channel,
        "event": event,
    }

    if thread_id:
        payload["thread_id"] = thread_id
    if node:
        payload["node"] = node
    if route:
        payload["route"] = route
    if model:
        payload["model"] = model

    # Merge in extra context and per-call data
    if extra:
        for k, v in extra.items():
            if k not in payload:
                payload[k] = _sanitize_value(v)
    if data:
        for k, v in data.items():
            if k not in payload:
                payload[k] = _sanitize_value(v)

    # Serialize to JSON line
    try:
        line = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        logger.warning("Failed to serialize audit event: %s", e)
        return

    # Emit to audit logger (which routes to file + stdout)
    _audit_logger.log(level, line)


# ── Convenience functions ────────────────────────────────────────────────────


def audit_debug(channel: str, event: str, **data: Any) -> None:
    """Shorthand for ``audit_event(..., level=logging.DEBUG)``."""
    audit_event(channel, event, level=logging.DEBUG, **data)


def audit_info(channel: str, event: str, **data: Any) -> None:
    """Shorthand for ``audit_event(..., level=logging.INFO)``."""
    audit_event(channel, event, level=logging.INFO, **data)


def audit_warn(channel: str, event: str, **data: Any) -> None:
    """Shorthand for ``audit_event(..., level=logging.WARNING)``."""
    audit_event(channel, event, level=logging.WARNING, **data)
