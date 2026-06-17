"""Strict cloud mode — block local Qwen fallback on compute paths (eval / debug)."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from src.config.config_loader import config

CLOUD_FAILED_MODEL = "large-cloud-failed"
SMALL_FAILED_MODEL = "small-local-failed"


def cloud_no_local_fallback_enabled() -> bool:
    """True when profile or config disables local Qwen fallback on cloud compute paths."""
    from src.memory.user_profile import get_profile

    profile = get_profile()
    profile_val = profile.get("cloud_no_local_fallback")
    if profile_val is True:
        return True
    if profile_val is False:
        return False
    return bool(config.get("cloud.no_local_fallback", False))


def cloud_failure_message(reason: str) -> str:
    return (
        f"Cloud compute failed ({reason}). Strict cloud mode is enabled — "
        "local Qwen fallback is disabled. Check DeepSeek API status, circuit breaker, "
        "and vision proxy, then retry."
    )


def block_cloud_local_fallback(
    *,
    fallback_chain: list,
    reason: str,
    vision_intake_mode: str = "text",
    vision_proxy_model: str | None = None,
    cloud_brief_tokens_est: int = 0,
    anonymization_placeholders_count: int = 0,
) -> dict | None:
    """Return a graph update dict when strict mode blocks fallback; else None."""
    if not cloud_no_local_fallback_enabled():
        return None
    chain = list(fallback_chain)
    chain.append(
        {
            "model": CLOUD_FAILED_MODEL,
            "status": "blocked",
            "reason": reason,
        }
    )
    return {
        "messages": [AIMessage(content=cloud_failure_message(reason))],
        "model_used": CLOUD_FAILED_MODEL,
        "pending_tool_calls": False,
        "security_decision": None,
        "security_reason": None,
        "fallback_chain": chain,
        "cloud_brief_tokens_est": cloud_brief_tokens_est,
        "anonymization_placeholders_count": anonymization_placeholders_count,
        "vision_intake_mode": vision_intake_mode,
        "vision_proxy_model": vision_proxy_model,
    }
