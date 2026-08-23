"""Fine-grained cloud API error classification and jittered exponential backoff.

Inspired by Hermes error classifier to distinguish between retryable transient errors
and non-retryable fatal/quota errors.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FailoverReason(str, Enum):
    rate_limit = "rate_limit"
    quota = "quota"
    context_length = "context_length"
    auth = "auth"
    server_error = "server_error"
    timeout = "timeout"
    unknown = "unknown"


@dataclass
class ClassifiedError:
    reason: FailoverReason
    status_code: int | None
    message: str
    retryable: bool
    retry_delay: float = 0.0


_QUOTA_ERROR_PATTERNS = (
    "insufficient_quota",
    "quota_exceeded",
    "out of credits",
    "out of funds",
    "billing",
    "balance insufficient",
)

_CONTEXT_LENGTH_PATTERNS = (
    "maximum context length",
    "context_length_exceeded",
    "prompt is too long",
    "max_tokens",
    "token limit",
)


def jittered_backoff(
    attempt: int, base_delay: float = 1.0, max_delay: float = 16.0
) -> float:
    """Calculate exponential backoff with full jitter to avoid thundering herds."""
    temp = min(max_delay, base_delay * (2**attempt))
    return random.uniform(0.5, temp)


def classify_cloud_error(exc: Exception) -> ClassifiedError:
    """Classify API exceptions into structured failover categories."""
    msg = str(exc).lower()
    status_code = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )

    # 1. Rate limits (HTTP 429 or rate limit message)
    if status_code == 429 or "rate limit" in msg or "too many requests" in msg:
        retry_after = 2.0
        # Parse retry-after if available in response headers
        headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
        if "retry-after" in headers:
            try:
                retry_after = float(headers["retry-after"])
            except (ValueError, TypeError):
                pass
        return ClassifiedError(
            reason=FailoverReason.rate_limit,
            status_code=429,
            message=str(exc),
            retryable=True,
            retry_delay=retry_after,
        )

    # 2. Authentication errors (HTTP 401, 403)
    if status_code in (401, 403) or "unauthorized" in msg or "invalid api key" in msg:
        return ClassifiedError(
            reason=FailoverReason.auth,
            status_code=status_code or 401,
            message=str(exc),
            retryable=False,
        )

    # 3. Quota / Billing exhaustion
    if status_code == 402 or any(p in msg for p in _QUOTA_ERROR_PATTERNS):
        return ClassifiedError(
            reason=FailoverReason.quota,
            status_code=status_code or 402,
            message=str(exc),
            retryable=False,
        )

    # 4. Context length overflow
    if any(p in msg for p in _CONTEXT_LENGTH_PATTERNS):
        return ClassifiedError(
            reason=FailoverReason.context_length,
            status_code=status_code or 400,
            message=str(exc),
            retryable=False,
        )

    # 5. Server errors (HTTP 500, 502, 503, 504, 529)
    if (
        status_code in (500, 502, 503, 504, 529)
        or "bad gateway" in msg
        or "service unavailable" in msg
    ):
        return ClassifiedError(
            reason=FailoverReason.server_error,
            status_code=status_code or 500,
            message=str(exc),
            retryable=True,
            retry_delay=1.5,
        )

    # 6. Timeouts
    if (
        "timeout" in msg
        or "timed out" in msg
        or isinstance(exc, (TimeoutError, asyncio.TimeoutError))
    ):
        return ClassifiedError(
            reason=FailoverReason.timeout,
            status_code=None,
            message=str(exc),
            retryable=True,
            retry_delay=1.0,
        )

    # Unknown
    return ClassifiedError(
        reason=FailoverReason.unknown,
        status_code=status_code,
        message=str(exc),
        retryable=False,
    )
