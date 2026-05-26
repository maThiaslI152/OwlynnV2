"""
Circuit Breaker for Cloud LLM API Calls.

Prevents hammering a failing DeepSeek API by tracking consecutive failures
and temporarily disabling cloud escalation after a threshold is reached.

Usage::

    from src.agent.cloud_circuit_breaker import CloudCircuitBreaker

    cb = CloudCircuitBreaker()
    cb.record_success()    # Call after every successful cloud API response
    cb.record_failure()    # Call after every failed cloud API attempt
    if cb.is_open():
        # Circuit is open — skip cloud, use local fallback
        ...
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CloudCircuitBreaker:
    """Tracks consecutive failures and auto-disables cloud after threshold.

    The circuit breaker has three states:

    - **closed**: Normal operation, cloud calls allowed.
    - **open**: Too many consecutive failures, cloud calls blocked.
    - **half-open**: Cooldown period elapsed, next call will test recovery.

    After ``failure_threshold`` consecutive failures, the circuit opens
    and stays open for ``cooldown_seconds``. After cooldown, a single
    trial call is allowed. Success resets the circuit; failure re-opens it.
    """

    # Defaults
    _failure_threshold = 3
    _cooldown_seconds = 60

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: int = 60,
    ):
        """Initialize the circuit breaker.

        Parameters
        ----------
        failure_threshold : int
            Number of consecutive failures before the circuit opens.
        cooldown_seconds : int
            Seconds to wait before allowing a trial call.
        """
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._consecutive_failures: int = 0
        self._last_failure_time: Optional[float] = None
        self._circuit_open: bool = False

    # ── public API ─────────────────────────────────────────────────

    def record_success(self) -> None:
        """Record a successful cloud API call. Resets the circuit."""
        if self._consecutive_failures > 0:
            logger.info(
                "[circuit-breaker] Reset after success (was %d consecutive failures)",
                self._consecutive_failures,
            )
        self._consecutive_failures = 0
        self._last_failure_time = None
        self._circuit_open = False

    def record_failure(self) -> None:
        """Record a failed cloud API attempt."""
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()
        if self._consecutive_failures >= self._failure_threshold:
            self._circuit_open = True
            logger.warning(
                "[circuit-breaker] Circuit OPEN — %d consecutive failures, "
                "cloud escalation disabled for %ds",
                self._consecutive_failures,
                self._cooldown_seconds,
            )

    def is_open(self) -> bool:
        """Return ``True`` if cloud calls should be blocked.

        Checks cooldown expiry: if the cooldown period has elapsed since
        the last failure, transitions to half-open (allows one trial).
        """
        if not self._circuit_open:
            return False
        if self._last_failure_time is None:
            return False
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._cooldown_seconds:
            # Cooldown expired — half-open: allow one trial
            self._circuit_open = False
            logger.info(
                "[circuit-breaker] Cooldown expired — half-open, next call allowed"
            )
            return False
        return True

    def is_closed(self) -> bool:
        """Return ``True`` if cloud calls are allowed."""
        return not self.is_open()

    # ── diagnostics ────────────────────────────────────────────────

    @property
    def state(self) -> str:
        """Current state: ``"closed"``, ``"open"``, or ``"half-open"``."""
        if self.is_open():
            return "open"
        if self._consecutive_failures > 0:
            return "half-open"
        return "closed"

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failures since last success."""
        return self._consecutive_failures

    @property
    def remaining_cooldown(self) -> float:
        """Seconds until cooldown expires (0 if circuit is closed)."""
        if not self._circuit_open or self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        return max(0.0, self._cooldown_seconds - elapsed)

    def reset(self) -> None:
        """Force-reset the circuit breaker to closed state."""
        self._consecutive_failures = 0
        self._last_failure_time = None
        self._circuit_open = False
        logger.info("[circuit-breaker] Forced reset to closed")


# ── module-level singleton ────────────────────────────────────────

_breaker: Optional[CloudCircuitBreaker] = None


def get_circuit_breaker() -> CloudCircuitBreaker:
    """Return the module-level circuit breaker singleton."""
    global _breaker
    if _breaker is None:
        _breaker = CloudCircuitBreaker()
    return _breaker


def reset_circuit_breaker() -> None:
    """Reset the module-level circuit breaker (for testing)."""
    global _breaker
    _breaker = None
