"""
Coherence Retry Node — Self-correction loop for low-confidence responses.

When ``coherence_check`` grades a response below the configured threshold,
``coherence_retry_node`` re-invokes the same model path with a synthesis
nudge and replaces the last assistant message. Bounded by ``coherence.max_retries``
in ``defaults.yaml`` (default: 1). Mirrors the synthesis-retry pattern in
``complex.py`` for web-search final-answer stalls.

Cloud route uses ``_invoke_cloud_path``; local routes use ``_invoke_local_path``
with tools unbound. Strict-cloud mode is respected — no silent fallback to local
when cloud is unavailable and strict mode is on.
"""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.core.complex_executor import _invoke_cloud_path, _invoke_local_path
from src.agent.core.complex_utils.formatter import (
    _strip_dsml_blocks,
    _strip_thinking_tags,
    latest_user_text,
)
from src.agent.core.state import AgentState
from src.agent.llm import CloudUnavailableError, get_cloud_llm
from src.config.audit_log import audit_info, audit_warn
from src.config.config_loader import config
from src.config.log_middleware import log_node
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

_DSML_MARKER_RE_PARTIAL_RE = re.compile(
    r"<[\s\uFF5C|]*DSML[\s\uFF5C|]*[a-z_]*[\s\uFF5C|]*>",
    re.IGNORECASE,
)


def _coherence_retry_settings() -> dict[str, Any]:
    """Read coherence retry settings from defaults.yaml with safe defaults."""
    block = config.get("coherence", {}) or {}
    return {
        "enabled": bool(block.get("enabled", True)),
        "threshold": float(block.get("retry_threshold", 0.4)),
        "max_retries": int(block.get("max_retries", 1)),
        "retry_budget": int(block.get("retry_token_budget", 2048)),
    }


def _retry_nudge(query: str, confidence: float, reason: str) -> HumanMessage:
    """Build the synthesis nudge that asks the model to try again."""
    return HumanMessage(
        content=(
            "[QUALITY IMPROVEMENT NEEDED] Your previous answer scored "
            f"{confidence:.2f}/1.0 on coherence (reason: {reason}). "
            f"Address the user's original query: {query[:300]}\n\n"
            "Write a complete, accurate answer. If you don't know, say so "
            "explicitly rather than guessing. Do NOT output tool_calls, DSML, "
            "or partial markup."
        )
    )


@log_node("coherence_retry")
async def coherence_retry_node(state: AgentState) -> dict[str, Any]:
    """Retry the last assistant turn with a synthesis nudge.

    Reads the last user query + last AI response, builds a nudge that tells
    the model to try again, invokes the same route (cloud or local main),
    and replaces the last assistant message in the thread.
    """
    settings = _coherence_retry_settings()
    if not settings["enabled"]:
        return {}

    messages = list(state.get("messages") or [])
    if not messages:
        return {}

    route = state.get("route") or "complex-cloud"
    confidence = float(state.get("response_confidence") or 0.0)
    coherence = state.get("response_coherence") or {}
    reason = str(coherence.get("reason") or "low_coherence")

    query = latest_user_text(messages)

    retry_nudge = _retry_nudge(query, confidence, reason)

    thread_messages = messages + [retry_nudge]
    budget = settings["retry_budget"]
    local_max_context = int(config.get("models.main.context_window", 16384))

    new_response: AIMessage | None = None
    fallback_chain_addition: list[dict] = []
    new_api_tokens: dict | None = None

    try:
        if route == "complex-cloud":
            profile = get_profile()
            try:
                llm = await get_cloud_llm(profile.get("cloud_model_tier"))
            except CloudUnavailableError as exc:
                logger.warning("[coherence_retry] Cloud unavailable: %s", exc)
                fallback_chain_addition.append(
                    {
                        "model": "large-cloud",
                        "status": "failed",
                        "reason": f"coherence_retry_cloud_unavailable:{type(exc).__name__}",
                    }
                )
                return {
                    "_coherence_retry_round": (state.get("_coherence_retry_round") or 0)
                    + 1,
                    "fallback_chain": fallback_chain_addition,
                    "coherence_retry_reason": "cloud_unavailable",
                }
            try:
                new_response, new_api_tokens = await _invoke_cloud_path(
                    llm=llm,
                    prompt_messages=thread_messages,
                    tools=None,
                    budget=budget,
                    state=state,
                    profile=profile,
                    mode="tools_off",
                    tools_bound=False,
                )
            except CloudUnavailableError as exc:
                logger.warning("[coherence_retry] Cloud invoke failed: %s", exc)
                return {
                    "_coherence_retry_round": (state.get("_coherence_retry_round") or 0)
                    + 1,
                    "fallback_chain": fallback_chain_addition,
                    "coherence_retry_reason": "cloud_unavailable",
                }
        elif route in {"complex-default", "main-local"}:
            new_response, new_api_tokens = await _invoke_local_path(
                prompt_messages=thread_messages,
                tools=None,
                budget=budget,
                max_context=local_max_context,
            )
    except Exception as exc:
        logger.warning("[coherence_retry] Retry invocation failed: %s", exc)
        audit_warn(
            "agent.coherence",
            "retry_failed",
            error=str(exc)[:120],
            route=route,
        )
        return {
            "_coherence_retry_round": (state.get("_coherence_retry_round") or 0) + 1,
            "fallback_chain": fallback_chain_addition,
            "coherence_retry_reason": f"retry_failed:{type(exc).__name__}",
        }

    if new_response is None:
        return {
            "_coherence_retry_round": (state.get("_coherence_retry_round") or 0) + 1,
            "fallback_chain": fallback_chain_addition,
            "coherence_retry_reason": "no_response",
        }

    raw = str(getattr(new_response, "content", "") or "")
    cleaned = _strip_dsml_blocks(_strip_thinking_tags(raw)).strip()
    if not cleaned:
        for marker in (
            r"<[\s\uFF5C|]*DSML[\s\uFF5C|]*[a-z_]*[\s\uFF5C|]*>",
            r"<\s*tool_call\s*>",
        ):
            parts = re.split(marker, raw, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) > 1:
                tail = parts[-1]
                tail = re.sub(r"</?[\s\uFF5C|]*DSML[\s\uFF5C|]*>", "", tail)
                tail = re.sub(r"</?\s*tool_call\s*>", "", tail)
                tail = tail.strip()
                if tail and len(tail) >= 3:
                    cleaned = tail
                    break
        if not cleaned:
            cleaned = "[empty response after retry]"

    replaced = AIMessage(
        content=cleaned,
        tool_calls=[],
        additional_kwargs=dict(getattr(new_response, "additional_kwargs", None) or {}),
    )

    audit_info(
        "agent.coherence",
        "retry_completed",
        route=route,
        round=(state.get("_coherence_retry_round") or 0) + 1,
        prev_confidence=confidence,
        prev_reason=reason,
        retry_chars=len(cleaned),
    )

    out: dict[str, Any] = {
        "messages": [replaced],
        "_coherence_retry_round": (state.get("_coherence_retry_round") or 0) + 1,
        "coherence_retry_reason": reason,
    }
    if fallback_chain_addition:
        existing = list(state.get("fallback_chain") or [])
        out["fallback_chain"] = existing + fallback_chain_addition
    if new_api_tokens:
        out["api_tokens_used"] = new_api_tokens

    return out
