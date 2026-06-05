"""
Centralized logging configuration for the Owlynn application.

Call ``setup_logging()`` once at application startup (e.g. in the FastAPI
lifespan or main entry point) to configure:

1. **Application logger** — stdout with consistent ``[LEVEL] name: message`` format
2. **Audit logger** — channel-based structured JSON-line logging with rotating
   file output and per-channel level control.

Environment Variables
---------------------
``OWLYNN_AUDIT_LOG_DIR``
    Override the audit log directory. Set to empty string to disable file
    output entirely (useful in CI/tests).
``OWLYNN_AUDIT_LOG_ENABLED``
    Set to ``"0"`` to disable audit file logging.
"""

from __future__ import annotations

import logging
import os
import sys


import logging
logger = logging.getLogger(__name__)
def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger, application handler, and audit subsystem.

    Parameters
    ----------
    level : int
        Logging level for the application handler (default: ``logging.INFO``).
        Set to ``logging.DEBUG`` for verbose output during development.
    """
    # ── 1. Application-level stdout handler ────────────────────────────────
    if os.environ.get("OWLYNN_DEBUG") == "1":
        level = logging.DEBUG

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # ── 2. Audit log stdout handler (compact JSON) ─────────────────────────
    _setup_audit_stdout_handler(level)

    # ── 3. Audit file handler (rotating JSON) + per-channel levels ─────────
    _setup_audit_file_output()


def _setup_audit_stdout_handler(level: int) -> None:
    """Attach a compact stdout handler to the ``audit`` logger so JSON lines
    are visible in the terminal alongside normal application logs."""
    audit_logger = logging.getLogger("audit")
    # Only attach if not already present (idempotent)
    for h in audit_logger.handlers:
        if getattr(h, "name", "") == "audit_stdout":
            return

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.name = "audit_stdout"
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(stdout_handler)
    audit_logger.setLevel(level)
    audit_logger.propagate = False


def _setup_audit_file_output() -> None:
    """Read audit configuration from environment / profile and initialize
    rotating file output with per-channel levels."""
    from src.config.audit_log import configure_audit_log

    # Environment overrides (for CI / test mode)
    audit_enabled_env = os.environ.get("OWLYNN_AUDIT_LOG_ENABLED")
    if audit_enabled_env == "0":
        configure_audit_log(enabled=False)
        return

    # Read profile for channel levels (best-effort)
    channel_levels = None
    enabled = True
    try:
        from src.memory.user_profile import get_profile

        profile = get_profile()
        channel_levels_raw = profile.get("audit_log_levels")
        if isinstance(channel_levels_raw, dict) and channel_levels_raw:
            channel_levels = channel_levels_raw
        enabled = profile.get("audit_log_enabled", True)
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass
    finally:
        configure_audit_log(channel_levels=channel_levels, enabled=enabled)
