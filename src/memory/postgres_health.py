"""Shared Postgres availability gate (circuit breaker).

When local Postgres is down, chat can limp on MemorySaver + empty memory.
This module stops soft-path callers from hammering a dead pool: after a small
number of consecutive failures the circuit opens for a cooldown, then allows
a half-open trial. Open/close transitions log once each (no pool spam).

Usage::

    from src.memory.postgres_health import (
        is_postgres_available,
        record_postgres_failure,
        record_postgres_success,
        postgres_status,
    )

    if not is_postgres_available():
        return []  # soft miss

    try:
        ...
        record_postgres_success()
    except Exception:
        record_postgres_failure()
        raise
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Local Mac SPOF: open quickly, cool down 30–60s (defaults in band).
_DEFAULT_FAILURE_THRESHOLD = 2
_DEFAULT_COOLDOWN_SECONDS = 45


class PostgresCircuitBreaker:
    """Tracks consecutive Postgres failures and blocks soft-path ops when open.

    States:
    - closed: normal — ops allowed
    - open: blocked for cooldown_seconds after failure_threshold failures
    - half-open: cooldown elapsed — next trial allowed; success closes, failure re-opens
    """

    def __init__(
        self,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._failure_threshold = max(1, int(failure_threshold))
        self._cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._consecutive_failures: int = 0
        self._last_failure_time: float | None = None
        self._circuit_open: bool = False
        self._logged_open: bool = False

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def remaining_cooldown(self) -> float:
        if not self._circuit_open or self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        return max(0.0, self._cooldown_seconds - elapsed)

    @property
    def state(self) -> str:
        """Return ``closed``, ``open``, or ``half-open`` without mutating."""
        if self._circuit_open:
            if (
                self._last_failure_time is not None
                and (time.monotonic() - self._last_failure_time)
                >= self._cooldown_seconds
            ):
                return "half-open"
            return "open"
        if self._consecutive_failures > 0:
            return "half-open"
        return "closed"

    def is_open(self) -> bool:
        """True when soft-path Postgres ops should be skipped.

        On cooldown expiry, transitions to half-open (allows one trial) and
        logs the close/recovery transition once.
        """
        if not self._circuit_open:
            return False
        if self._last_failure_time is None:
            return False
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._cooldown_seconds:
            was_logged_open = self._logged_open
            self._circuit_open = False
            self._logged_open = False
            if was_logged_open:
                logger.info(
                    "[postgres-health] Circuit half-open after %.0fs cooldown — trial allowed",
                    self._cooldown_seconds,
                )
            return False
        return True

    def is_closed(self) -> bool:
        return not self.is_open()

    def record_success(self) -> None:
        """Record a successful Postgres op. Closes the circuit; logs once if recovering."""
        was_failing = (
            self._circuit_open or self._consecutive_failures > 0 or self._logged_open
        )
        self._consecutive_failures = 0
        self._last_failure_time = None
        self._circuit_open = False
        self._logged_open = False
        if was_failing:
            logger.info("[postgres-health] Circuit CLOSED — Postgres recovered")

    def record_failure(self) -> None:
        """Record a failed Postgres op. Opens after threshold; logs once per open."""
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()
        if self._consecutive_failures < self._failure_threshold:
            return
        becoming_open = not self._circuit_open or not self._logged_open
        self._circuit_open = True
        if becoming_open and not self._logged_open:
            self._logged_open = True
            logger.warning(
                "[postgres-health] Circuit OPEN — %d consecutive failure(s), "
                "skipping soft Postgres ops for %.0fs",
                self._consecutive_failures,
                self._cooldown_seconds,
            )

    def reset(self) -> None:
        """Force-reset to closed (tests / manual recovery)."""
        self._consecutive_failures = 0
        self._last_failure_time = None
        self._circuit_open = False
        self._logged_open = False
        logger.info("[postgres-health] Circuit forced CLOSED")

    def force_open(self, reason: str = "manual") -> None:
        """Force open (e.g. startup probe failed). Logs once if not already open."""
        self._consecutive_failures = max(
            self._consecutive_failures, self._failure_threshold
        )
        self._last_failure_time = time.monotonic()
        becoming_open = not self._logged_open
        self._circuit_open = True
        if becoming_open:
            self._logged_open = True
            logger.warning(
                "[postgres-health] Circuit OPEN (%s) — soft Postgres ops skipped for %.0fs",
                reason,
                self._cooldown_seconds,
            )


_breaker: PostgresCircuitBreaker | None = None

# Set by graph.init_agent — "postgres" | "memory"
_checkpointer_backend: str = "memory"


def get_postgres_breaker() -> PostgresCircuitBreaker:
    """Return the process-wide Postgres circuit breaker singleton."""
    global _breaker
    if _breaker is None:
        _breaker = PostgresCircuitBreaker()
    return _breaker


def reset_postgres_breaker() -> None:
    """Drop the singleton (tests)."""
    global _breaker
    _breaker = None


def is_postgres_available() -> bool:
    """True when soft-path callers may attempt Postgres."""
    return get_postgres_breaker().is_closed()


def record_postgres_success() -> None:
    get_postgres_breaker().record_success()


def record_postgres_failure() -> None:
    get_postgres_breaker().record_failure()


def postgres_status() -> str:
    """Health field: ``ok`` | ``degraded`` | ``error``.

    - ok: soft-path ops allowed (closed or half-open trial)
    - degraded: circuit open — soft Postgres paths are skipped
    """
    if get_postgres_breaker().is_open():
        return "degraded"
    return "ok"


def set_checkpointer_backend(backend: str) -> None:
    """Record whether the agent compiled with Postgres or MemorySaver."""
    global _checkpointer_backend
    if backend not in ("postgres", "memory"):
        backend = "memory"
    _checkpointer_backend = backend


def get_checkpointer_backend() -> str:
    """Return ``postgres`` or ``memory`` for the active agent checkpointer."""
    return _checkpointer_backend
