"""
Cloud LLM Usage & Cost Tracker.

Tracks per-session token usage (input/output/cache-hit) and estimated cost for
DeepSeek V4 API calls.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug
from src.config.config_loader import config

_PRICE_INPUT_PER_1M = float(config.get("models.cloud.pricing.input_per_1m_usd", 0.14))
_PRICE_CACHE_HIT_PER_1M = float(
    config.get("models.cloud.pricing.cache_hit_per_1m_usd", 0.014)
)
_PRICE_OUTPUT_PER_1M = float(config.get("models.cloud.pricing.output_per_1m_usd", 0.28))


@dataclass
class SessionCostTracker:
    """Tracks cumulative cloud API token usage for one session."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    reasoning_tokens: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    session_start: float = field(default_factory=time.monotonic)
    last_call_time: Optional[float] = None

    def record_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        prompt_cache_hit_tokens: int = 0,
        prompt_cache_miss_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> None:
        """Record token usage from a successful API call."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.prompt_cache_hit_tokens += prompt_cache_hit_tokens
        self.prompt_cache_miss_tokens += prompt_cache_miss_tokens
        self.reasoning_tokens += reasoning_tokens
        self.total_calls += 1
        self.last_call_time = time.monotonic()
        if prompt_tokens > 0:
            hit_ratio = prompt_cache_hit_tokens / max(prompt_tokens, 1)
            audit_debug(
                "agent.cloud",
                "cache_usage",
                prompt_tokens=prompt_tokens,
                cache_hit=prompt_cache_hit_tokens,
                cache_miss=prompt_cache_miss_tokens,
                hit_ratio=round(hit_ratio, 4),
            )

    def record_failure(self) -> None:
        """Record a failed API call (no token cost)."""
        self.failed_calls += 1
        self.last_call_time = time.monotonic()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def estimated_cost(self) -> float:
        """Estimated cost in USD with separate cache-hit input tier."""
        miss = self.prompt_cache_miss_tokens or max(
            0, self.prompt_tokens - self.prompt_cache_hit_tokens
        )
        hit = self.prompt_cache_hit_tokens
        input_cost = (miss / 1_000_000) * _PRICE_INPUT_PER_1M + (
            hit / 1_000_000
        ) * _PRICE_CACHE_HIT_PER_1M
        output_cost = (self.completion_tokens / 1_000_000) * _PRICE_OUTPUT_PER_1M
        return round(input_cost + output_cost, 6)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.session_start

    def summary(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "prompt_cache_hit_tokens": self.prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": self.prompt_cache_miss_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "estimated_cost_usd": self.estimated_cost,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "pricing": {
                "input_per_1m_usd": _PRICE_INPUT_PER_1M,
                "cache_hit_per_1m_usd": _PRICE_CACHE_HIT_PER_1M,
                "output_per_1m_usd": _PRICE_OUTPUT_PER_1M,
            },
        }

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.prompt_cache_hit_tokens = 0
        self.prompt_cache_miss_tokens = 0
        self.reasoning_tokens = 0
        self.total_calls = 0
        self.failed_calls = 0
        self.session_start = time.monotonic()
        self.last_call_time = None


_tracker: Optional[SessionCostTracker] = None


def get_cost_tracker() -> SessionCostTracker:
    global _tracker
    if _tracker is None:
        _tracker = SessionCostTracker()
    return _tracker


def reset_cost_tracker() -> None:
    global _tracker
    _tracker = None
