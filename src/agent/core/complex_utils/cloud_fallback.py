"""Deduplicated cloud-to-local fallback handler for complex_llm_node.

When cloud invocation fails (unavailable, rate limit, auth, generic error),
fall back to the local model.  This module centralizes the repeated pattern
that was previously copy-pasted 6+ times in complex.py.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage

from src.config.config_loader import config

logger = logging.getLogger(__name__)

_DEFAULT_FALLBACK_BUDGET = int(config.get("complex.default_token_budget", 4096))
_DEFAULT_FALLBACK_CONTEXT = config.get_main_model_context_window()


def _fallback_error_message(reason: str) -> str:
    """User-facing error message for each fallback reason."""
    return {
        "vision_proxy_failed": "Cloud unavailable — please try again or disable complex reasoning.",
        "cloud_unavailable": "Cloud unavailable — please try again or disable complex reasoning.",
        "rate_limit": "Cloud unavailable — please try again or disable complex reasoning.",
        "auth_error": "Unable to connect to the cloud model — your API key may be invalid or expired. Please check Settings and try again.",
        "cloud_error": "Cloud unavailable — please try again or disable complex reasoning.",
    }.get(reason, "Cloud unavailable — please try again or disable complex reasoning.")


async def handle_cloud_fallback(
    *,
    invoke_local_fallback: Callable[..., Awaitable[tuple[Any, str]]],
    fallback_chain: list[dict],
    reason: str,
    prompt_messages: list,
    tools: list | None = None,
    budget: int = _DEFAULT_FALLBACK_BUDGET,
    max_context: int = _DEFAULT_FALLBACK_CONTEXT,
    vision_intake_mode: str = "text",
    cloud_brief_tokens_est: int = 0,
    anonymization_placeholders_count: int = 0,
) -> dict[str, Any]:
    """Attempt local fallback after cloud failure. Returns the complete AgentState dict.

    Appends to ``fallback_chain`` in-place.  ``invoke_local_fallback`` is passed
    as a parameter to avoid circular imports with complex.py.
    """
    fallback_chain.append(
        {"model": "large-cloud", "status": "failed", "reason": reason}
    )
    try:
        fallback_response, fallback_label = await invoke_local_fallback(
            prompt_messages=prompt_messages,
            tools=tools,
            budget=budget,
            max_context=max_context,
        )
        fallback_chain.append({"model": "local-fallback", "status": "success"})
        return {
            "messages": [
                fallback_response
                if isinstance(fallback_response, AIMessage)
                else AIMessage(content=fallback_response.content)
            ],
            "model_used": fallback_label,
            "model_generated_by": fallback_label,
            "pending_tool_calls": bool(getattr(fallback_response, "tool_calls", None)),
            "security_decision": None,
            "security_reason": None,
            "api_tokens_used": None,
            "fallback_chain": fallback_chain,
            "cloud_brief_tokens_est": cloud_brief_tokens_est,
            "anonymization_placeholders_count": anonymization_placeholders_count,
            "cloud_fallback_used": True,
            "cloud_fallback_reason": reason,
            "vision_intake_mode": vision_intake_mode,
            "vision_proxy_model": None,
        }
    except Exception as fb_err:
        logger.error("[complex] Local fallback also failed: %s", fb_err, exc_info=True)
        fallback_chain.append(
            {"model": "local-fallback", "status": "failed", "reason": str(fb_err)[:80]}
        )
        return {
            "messages": [AIMessage(content=_fallback_error_message(reason))],
            "model_used": "large-cloud-failed",
            "pending_tool_calls": False,
            "security_decision": None,
            "security_reason": None,
            "api_tokens_used": None,
            "fallback_chain": fallback_chain,
            "cloud_brief_tokens_est": cloud_brief_tokens_est,
            "anonymization_placeholders_count": anonymization_placeholders_count,
            "vision_intake_mode": vision_intake_mode,
            "vision_proxy_model": None,
        }
