"""
Cloud LLM Usage & Cost Tracker.

Tracks per-session token usage (input/output) and estimated cost for
DeepSeek V4 API calls. Provides a summary endpoint for the frontend.

DeepSeek V4 pricing (as of 2026-05):
- Input:  $0.14 / 1M tokens
- Output: $0.28 / 1M tokens

Usage::

    from src.agent.cloud_cost_tracker import SessionCostTracker
    tracker = SessionCostTracker()
    tracker.record_usage(prompt_tokens=1500, completion_tokens=800)
    summary = tracker.summary()
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Cloud model pricing per 1M tokens (USD) — sourced from centralized config
from src.config.config_loader import config
_PRICE_INPUT_PER_1M = float(config.get("models.cloud.pricing.input_per_1m_usd", 0.14))
_PRICE_OUTPUT_PER_1M = float(config.get("models.cloud.pricing.output_per_1m_usd", 0.28))


@dataclass
class SessionCostTracker:
    """Tracks cumulative cloud API token usage for one session."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    session_start: float = field(default_factory=time.monotonic)
    last_call_time: Optional[float] = None

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record token usage from a successful API call.

        Parameters
        ----------
        prompt_tokens : int
            Number of input/prompt tokens consumed.
        completion_tokens : int
            Number of output/completion tokens consumed.
        """
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_calls += 1
        self.last_call_time = time.monotonic()

    def record_failure(self) -> None:
        """Record a failed API call (no token cost)."""
        self.failed_calls += 1
        self.last_call_time = time.monotonic()

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)."""
        return self.prompt_tokens + self.completion_tokens

    @property
    def estimated_cost(self) -> float:
        """Estimated cost in USD based on DeepSeek V4 pricing."""
        input_cost = (self.prompt_tokens / 1_000_000) * _PRICE_INPUT_PER_1M
        output_cost = (self.completion_tokens / 1_000_000) * _PRICE_OUTPUT_PER_1M
        return round(input_cost + output_cost, 6)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since session started."""
        return time.monotonic() - self.session_start

    def summary(self) -> dict:
        """Return a summary dict suitable for API responses."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "estimated_cost_usd": self.estimated_cost,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "pricing": {
                "input_per_1m_usd": _PRICE_INPUT_PER_1M,
                "output_per_1m_usd": _PRICE_OUTPUT_PER_1M,
            },
        }

    def reset(self) -> None:
        """Reset all counters for a new session."""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_calls = 0
        self.failed_calls = 0
        self.session_start = time.monotonic()
        self.last_call_time = None


# ── module-level singleton ────────────────────────────────────────

_tracker: Optional[SessionCostTracker] = None


def get_cost_tracker() -> SessionCostTracker:
    """Return the module-level cost tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = SessionCostTracker()
    return _tracker


def reset_cost_tracker() -> None:
    """Reset the module-level cost tracker (for testing or new session)."""
    global _tracker
    _tracker = None
