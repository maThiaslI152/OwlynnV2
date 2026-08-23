"""
Cloud LLM Usage & Cost Tracker.

Tracks per-session token usage (input/output/cache-hit) and estimated cost for
DeepSeek V4 API calls. Supports flash vs pro tier pricing and daily budget warnings.
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug
from src.config.config_loader import config

_FLASH_INPUT = float(config.get("models.cloud.pricing.input_per_1m_usd", 0.14))
_FLASH_CACHE_HIT = float(config.get("models.cloud.pricing.cache_hit_per_1m_usd", 0.014))
_FLASH_OUTPUT = float(config.get("models.cloud.pricing.output_per_1m_usd", 0.28))
_PRO_INPUT = float(config.get("models.cloud.pricing.pro.input_per_1m_usd", 0.435))
_PRO_CACHE_HIT = float(
    config.get("models.cloud.pricing.pro.cache_hit_per_1m_usd", 0.014)
)
_PRO_OUTPUT = float(config.get("models.cloud.pricing.pro.output_per_1m_usd", 0.87))


def _pricing_for_tier(tier: str) -> tuple[float, float, float]:
    if str(tier).lower() == "pro":
        return _PRO_INPUT, _PRO_CACHE_HIT, _PRO_OUTPUT
    return _FLASH_INPUT, _FLASH_CACHE_HIT, _FLASH_OUTPUT


def _estimate_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    prompt_cache_hit_tokens: int,
    prompt_cache_miss_tokens: int,
    tier: str,
) -> float:
    input_price, cache_price, output_price = _pricing_for_tier(tier)
    miss = prompt_cache_miss_tokens or max(0, prompt_tokens - prompt_cache_hit_tokens)
    hit = prompt_cache_hit_tokens
    input_cost = (miss / 1_000_000) * input_price + (hit / 1_000_000) * cache_price
    output_cost = (completion_tokens / 1_000_000) * output_price
    return round(input_cost + output_cost, 6)


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
    last_call_time: float | None = None
    last_turn: dict | None = None
    _warned_thresholds: set[float] = field(default_factory=set, repr=False)

    def record_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        prompt_cache_hit_tokens: int = 0,
        prompt_cache_miss_tokens: int = 0,
        reasoning_tokens: int = 0,
        model_tier: str = "flash",
        model_name: str = "",
    ) -> None:
        """Record token usage from a successful API call."""
        tier = str(model_tier or "flash").lower()
        turn_cost = _estimate_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
            prompt_cache_miss_tokens=prompt_cache_miss_tokens,
            tier=tier,
        )
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.prompt_cache_hit_tokens += prompt_cache_hit_tokens
        self.prompt_cache_miss_tokens += prompt_cache_miss_tokens
        self.reasoning_tokens += reasoning_tokens
        self.total_calls += 1
        self.last_call_time = time.monotonic()
        cache_hit_ratio = (
            prompt_cache_hit_tokens / max(prompt_tokens, 1) if prompt_tokens else 0.0
        )
        self.last_turn = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "reasoning_tokens": reasoning_tokens,
            "model_tier": tier,
            "model_name": model_name,
            "estimated_cost_usd": turn_cost,
            "cache_hit_ratio": round(cache_hit_ratio, 4),
        }
        if prompt_tokens > 0:
            audit_debug(
                "agent.cloud",
                "cache_usage",
                prompt_tokens=prompt_tokens,
                cache_hit=prompt_cache_hit_tokens,
                cache_miss=prompt_cache_miss_tokens,
                hit_ratio=round(cache_hit_ratio, 4),
                model_tier=tier,
            )

    def record_failure(self) -> None:
        """Record a failed API call (no token cost)."""
        self.failed_calls += 1
        self.last_call_time = time.monotonic()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cache_hit_ratio(self) -> float:
        if self.prompt_tokens <= 0:
            return 0.0
        return round(self.prompt_cache_hit_tokens / self.prompt_tokens, 4)

    @property
    def estimated_cost(self) -> float:
        """Estimated session cost in USD (flash-tier baseline for mixed sessions)."""
        return _estimate_cost(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            prompt_cache_hit_tokens=self.prompt_cache_hit_tokens,
            prompt_cache_miss_tokens=self.prompt_cache_miss_tokens,
            tier="flash",
        )

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.session_start

    def budget_snapshot(self, daily_token_limit: int) -> dict:
        limit = max(int(daily_token_limit or 0), 0)
        used = self.total_tokens
        if limit <= 0:
            return {
                "daily_token_limit": 0,
                "used_tokens": used,
                "remaining_tokens": None,
                "used_pct": 0.0,
            }
        used_pct = round(min(used / limit, 1.0), 4)
        return {
            "daily_token_limit": limit,
            "used_tokens": used,
            "remaining_tokens": max(limit - used, 0),
            "used_pct": used_pct,
        }

    def consume_budget_warnings(
        self, daily_token_limit: int, thresholds: list[float]
    ) -> list[dict]:
        """Return newly crossed budget warning payloads (once per threshold)."""
        budget = self.budget_snapshot(daily_token_limit)
        used_pct = float(budget.get("used_pct") or 0.0)
        warnings: list[dict] = []
        for threshold in sorted(float(t) for t in thresholds):
            if threshold in self._warned_thresholds:
                continue
            if used_pct >= threshold:
                self._warned_thresholds.add(threshold)
                warnings.append(
                    {
                        "threshold": threshold,
                        "used_pct": used_pct,
                        "used_tokens": budget["used_tokens"],
                        "daily_token_limit": budget["daily_token_limit"],
                        "estimated_cost_usd": self.estimated_cost,
                    }
                )
        return warnings

    def summary(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "prompt_cache_hit_tokens": self.prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": self.prompt_cache_miss_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "cache_hit_ratio": self.cache_hit_ratio,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "estimated_cost_usd": self.estimated_cost,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "last_turn": self.last_turn,
            "pricing": {
                "flash": {
                    "input_per_1m_usd": _FLASH_INPUT,
                    "cache_hit_per_1m_usd": _FLASH_CACHE_HIT,
                    "output_per_1m_usd": _FLASH_OUTPUT,
                },
                "pro": {
                    "input_per_1m_usd": _PRO_INPUT,
                    "cache_hit_per_1m_usd": _PRO_CACHE_HIT,
                    "output_per_1m_usd": _PRO_OUTPUT,
                },
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
        self.last_turn = None
        self._warned_thresholds.clear()


_tracker: SessionCostTracker | None = None


def get_cost_tracker() -> SessionCostTracker:
    global _tracker
    if _tracker is None:
        _tracker = SessionCostTracker()
    return _tracker


def reset_cost_tracker() -> None:
    global _tracker
    _tracker = None


def build_cloud_usage_payload(
    *,
    turn_usage: dict | None = None,
    model_used: str | None = None,
) -> dict:
    """Build WS/API payload for session cloud usage."""
    from src.memory.user_profile import get_profile

    tracker = get_cost_tracker()
    profile = get_profile()
    daily_limit = int(
        profile.get("cloud_daily_token_limit")
        or config.get("cloud.budget.daily_token_limit", 500_000)
    )
    thresholds = profile.get("cloud_budget_warning_thresholds") or config.get(
        "cloud.budget.warning_thresholds", [0.5, 0.8, 0.95]
    )
    turn: dict = {}
    if turn_usage:
        turn = {
            "prompt_tokens": int(turn_usage.get("prompt_tokens", 0)),
            "completion_tokens": int(turn_usage.get("completion_tokens", 0)),
            "prompt_cache_hit_tokens": int(
                turn_usage.get("prompt_cache_hit_tokens", 0)
            ),
            "prompt_cache_miss_tokens": int(
                turn_usage.get("prompt_cache_miss_tokens", 0)
            ),
        }
    if model_used:
        turn["model_used"] = model_used
    return {
        "turn": turn,
        "session": tracker.summary(),
        "budget": tracker.budget_snapshot(daily_limit),
        "warning_thresholds": list(thresholds),
    }
