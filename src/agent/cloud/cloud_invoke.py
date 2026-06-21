"""
Raw DeepSeek cloud invocation with reasoning_content replay and cache metrics.

Uses the OpenAI-compatible API directly so ``reasoning_content`` on assistant
messages is preserved on tool-loop round-trips (LangChain serializers drop it).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from langchain_core.messages import BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.agent.cloud.cloud_payload import (
    CloudThinkingConfig,
    capture_cloud_response,
    extract_api_token_usage,
    messages_to_deepseek_api,
)
from src.config.config_loader import config

logger = logging.getLogger(__name__)

_MAX_CLOUD_RETRIES = int(config.get("complex.max_cloud_retries", 3))


async def invoke_cloud_chat(
    *,
    llm_client: Any,
    model_name: str,
    messages: list[BaseMessage],
    tools: Optional[list] = None,
    max_tokens: int,
    thinking: CloudThinkingConfig,
    strict_tools: bool = True,
    user_id: Optional[str] = None,
) -> tuple[Any, dict[str, int]]:
    """
    Invoke DeepSeek chat completions with custom message serialization.

    Returns the raw API response object and normalized token usage dict.
    """
    from src.agent.cloud.cloud_circuit_breaker import get_circuit_breaker

    breaker = get_circuit_breaker()
    if breaker.is_open():
        raise RuntimeError("Circuit breaker open")

    api_messages = messages_to_deepseek_api(messages)
    create_kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": api_messages,
        "max_tokens": max_tokens,
        "temperature": float(config.get("models.cloud.temperature", 0.4)),
    }
    create_kwargs.update(thinking.extra_body or {})
    if thinking.reasoning_effort and thinking.thinking_enabled:
        create_kwargs["reasoning_effort"] = thinking.reasoning_effort

    if user_id:
        create_kwargs["user"] = str(user_id)

    if tools:
        create_kwargs["tools"] = [convert_to_openai_tool(t) for t in tools]
        create_kwargs["tool_choice"] = "auto"
        if strict_tools:
            create_kwargs["strict"] = True

    base_url = str(
        config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    ).rstrip("/")
    beta_url = base_url.replace("/v1", "/beta") if "/v1" in base_url else base_url

    last_error: Exception | None = None
    for attempt in range(_MAX_CLOUD_RETRIES + 1):
        try:
            response = await _create_with_fallback(
                llm_client, create_kwargs, primary_url=base_url, fallback_url=beta_url
            )
            breaker.record_success()
            usage = extract_api_token_usage(response)
            return response, usage
        except Exception as exc:
            last_error = exc
            err_str = str(exc).lower()
            if "401" in err_str or "403" in err_str:
                breaker.record_failure()
                raise
            is_retryable = "429" in err_str or any(
                code in err_str for code in ("500", "502", "503", "504")
            )
            if not is_retryable or attempt >= _MAX_CLOUD_RETRIES:
                breaker.record_failure()
                raise
            await asyncio.sleep(2**attempt)

    breaker.record_failure()
    raise last_error if last_error else RuntimeError("Cloud retry exhausted")


async def _create_with_fallback(
    llm_client: Any,
    create_kwargs: dict[str, Any],
    *,
    primary_url: str,
    fallback_url: str,
) -> Any:
    """Try /v1 strict tool calls; fall back to /beta on schema validation errors."""
    try:
        return await llm_client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        err = str(exc).lower()
        if tools_strict_failed(err) and fallback_url != primary_url:
            logger.warning(
                "[cloud_invoke] strict tool schema failed on %s; retrying %s",
                primary_url,
                fallback_url,
            )
            client = _client_for_base_url(llm_client, fallback_url)
            return await client.chat.completions.create(**create_kwargs)
        raise


def tools_strict_failed(err: str) -> bool:
    """Heuristic: detect strict JSON-schema tool validation failures."""
    markers = ("strict", "schema", "json_schema", "invalid tool", "tool_call")
    return any(m in err for m in markers)


def _client_for_base_url(llm_client: Any, base_url: str) -> Any:
    """Return an async OpenAI client pointed at ``base_url`` (reuse API key)."""
    from openai import AsyncOpenAI

    from src.config.secret_store import resolve_deepseek_api_key

    api_key = getattr(llm_client, "api_key", None) or resolve_deepseek_api_key()
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


def response_to_ai_message(raw_response: Any) -> Any:
    """Convert OpenAI chat completion to LangChain AIMessage with reasoning_content."""
    choice = raw_response.choices[0]
    msg = choice.message
    tool_calls = []
    if getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            args_raw = tc.function.arguments or "{}"
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"raw": args_raw}
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                }
            )
    content = msg.content or ""
    reasoning = getattr(msg, "reasoning_content", None) or ""
    fake = type(
        "CloudResponse",
        (),
        {
            "content": content,
            "tool_calls": tool_calls,
            "reasoning_content": reasoning,
            "response_metadata": {
                "token_usage": _usage_dict(raw_response),
                "finish_reason": choice.finish_reason,
            },
        },
    )()
    return capture_cloud_response(fake)


def _usage_dict(raw_response: Any) -> dict[str, int]:
    usage = getattr(raw_response, "usage", None)
    if not usage:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "prompt_cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", 0) or 0,
        "prompt_cache_miss_tokens": getattr(usage, "prompt_cache_miss_tokens", 0) or 0,
    }
