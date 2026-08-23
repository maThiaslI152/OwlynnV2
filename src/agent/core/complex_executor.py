"""LLM execution, cloud invocation, fallback management, and cutoff continuation for the complex path.

Extracted from complex.py for modularity and maintainability.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.cloud.anonymization import deanonymize
from src.agent.cloud.cloud_cost_tracker import get_cost_tracker
from src.agent.cloud.cloud_invoke import invoke_cloud_chat, response_to_ai_message
from src.agent.cloud.cloud_payload import (
    extract_api_token_usage,
    resolve_cloud_thinking_config,
)
from src.agent.core.complex_prompt import _cap_budget_to_context
from src.agent.llm import CloudUnavailableError, get_fallback_llm
from src.config.config_loader import config

logger = logging.getLogger(__name__)

# Execution constants
MAX_CUTOFF_RETRIES = int(config.get("complex.max_cutoff_retries", 1))
_MAX_CLOUD_RETRIES = int(config.get("complex.max_cloud_retries", 3))
_DEFAULT_TOKEN_BUDGET = int(config.get("complex.default_token_budget", 4096))
_SMALL_CONTEXT_WINDOW = config.get_main_model_context_window()
_LOCAL_RERANK_TOP_K = int(config.get("complex.local_tool_rerank_top_k", 8))


def _sanitize_local_prompt_messages(prompt_messages: list) -> list:
    """Convert image_url blocks to text descriptors for text-only local models."""
    sanitized_messages = []
    for msg in prompt_messages:
        if isinstance(msg, HumanMessage) and isinstance(msg.content, list):
            new_content = []
            for block in msg.content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    new_content.append(
                        {"type": "text", "text": "[Image attached by user]"}
                    )
                else:
                    new_content.append(block)
            sanitized_messages.append(
                HumanMessage(content=new_content, id=getattr(msg, "id", None))
            )
        else:
            sanitized_messages.append(msg)
    return sanitized_messages


def _rerank_local_tools(tools: list | None, prompt_messages: list) -> list | None:
    if not tools:
        return tools
    from src.agent.tool_reranker import rerank_tools

    sorted_tools = sorted(tools, key=lambda t: getattr(t, "name", str(t)))
    if len(sorted_tools) <= 10:
        return sorted_tools
    query_text = prompt_messages[-1].content if prompt_messages else ""
    return rerank_tools(str(query_text), sorted_tools, top_k=_LOCAL_RERANK_TOP_K)


def _local_api_tokens(response: Any) -> dict[str, int]:
    usage = extract_api_token_usage(response)
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
        "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
    }


def _vision_telemetry(vision_intake_mode: str) -> dict[str, Any]:
    from src.agent.core.complex_utils.lm_studio_vision import (
        configured_vision_model_name,
    )

    return {
        "vision_intake_mode": vision_intake_mode,
        "vision_proxy_model": (
            configured_vision_model_name() if vision_intake_mode == "proxy" else None
        ),
    }


async def _invoke_cloud_path(
    *,
    llm: Any,
    prompt_messages: list,
    tools: list | None,
    budget: int,
    state: dict,
    profile: dict,
    mode: str,
    tools_bound: bool,
) -> tuple[Any, dict[str, int]]:
    """Invoke DeepSeek via raw API path with thinking config and cost tracking."""
    from src.agent.cloud.cloud_circuit_breaker import get_circuit_breaker

    if get_circuit_breaker().is_open():
        raise CloudUnavailableError("Cloud circuit breaker open")

    thinking = resolve_cloud_thinking_config(
        state=state,
        profile=profile,
        tools_bound=tools_bound,
        mode=mode,
    )
    model_name = getattr(llm, "model_name", None) or config.get_cloud_model_name()
    client = getattr(llm, "async_client", None)
    use_raw_api = (
        client is not None
        and not isinstance(client, MagicMock)
        and hasattr(getattr(client, "chat", None), "completions")
    )

    thread_id = (
        state.get("thread_id")
        or state.get("conversation_id")
        or (state.get("configurable") or {}).get("thread_id")
    )

    if not use_raw_api:
        if tools_bound and tools:
            bound = llm.bind_tools(tools, strict=True).bind(max_tokens=budget)
        else:
            bound = llm.bind(max_tokens=budget)
        try:
            response = await bound.ainvoke(prompt_messages)
            get_circuit_breaker().record_success()
        except Exception:
            get_circuit_breaker().record_failure()
            raise
        usage = extract_api_token_usage(response)
    else:
        try:
            from src.agent.cloud.cloud_privacy import cloud_user_fingerprint

            raw, usage = await invoke_cloud_chat(
                llm_client=client,
                model_name=model_name,
                messages=prompt_messages,
                tools=tools if tools_bound else None,
                max_tokens=budget,
                thinking=thinking,
                user_id=cloud_user_fingerprint(str(thread_id) if thread_id else None),
            )
            response = response_to_ai_message(raw)
        except RuntimeError as exc:
            if "circuit breaker" in str(exc).lower():
                raise CloudUnavailableError(str(exc)) from exc
            raise

    get_cost_tracker().record_usage(
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        prompt_cache_hit_tokens=usage.get("prompt_cache_hit_tokens", 0),
        prompt_cache_miss_tokens=usage.get("prompt_cache_miss_tokens", 0),
        reasoning_tokens=usage.get("reasoning_tokens", 0),
        model_tier=str(profile.get("cloud_model_tier") or "flash"),
        model_name=str(model_name or ""),
    )
    api_tokens = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
        "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
    }
    return response, api_tokens


async def _invoke_local_path(
    *,
    prompt_messages: list,
    tools: list | None,
    budget: int,
    max_context: int,
    is_fallback: bool = False,
) -> tuple[Any, dict[str, int]]:
    """Invoke local main model (gemma-4-12b) for normal complex reasoning or fallback."""
    llm = await get_fallback_llm()
    fallback_budget = _cap_budget_to_context(
        prompt_messages,
        min(budget, _DEFAULT_TOKEN_BUDGET),
        max_context,
    )
    from src.agent.llm import DEFAULT_LOCAL_STOP_TOKENS
    from src.config.config_loader import get_model_config

    tools = _rerank_local_tools(tools, prompt_messages)
    stop_tokens = get_model_config("main").get("stop") or DEFAULT_LOCAL_STOP_TOKENS
    if tools:
        bound = llm.bind_tools(tools).bind(max_tokens=fallback_budget, stop=stop_tokens)
    else:
        bound = llm.bind(max_tokens=fallback_budget, stop=stop_tokens)

    sanitized_messages = _sanitize_local_prompt_messages(prompt_messages)

    logger.info(
        "[complex] Invoking local main model (fallback=%s) context=%d budget=%d (tools=%d)",
        is_fallback,
        max_context,
        fallback_budget,
        len(tools) if tools else 0,
    )
    response = await bound.ainvoke(sanitized_messages)
    return response, _local_api_tokens(response)


async def _invoke_pentest_path(
    *,
    prompt_messages: list,
    tools: list | None,
    budget: int,
    max_context: int,
) -> tuple[Any, dict[str, int]]:
    """Invoke local pentest model with sorted/reranked tools and pentest stop tokens."""
    from src.agent.llm import DEFAULT_LOCAL_STOP_TOKENS, get_pentest_llm
    from src.config.config_loader import get_model_config

    llm = await get_pentest_llm()
    fallback_budget = _cap_budget_to_context(
        prompt_messages,
        min(budget, _DEFAULT_TOKEN_BUDGET),
        max_context,
    )
    tools = _rerank_local_tools(tools, prompt_messages)
    pentest_cfg = get_model_config("pentest")
    stop_tokens = pentest_cfg.get("stop") or DEFAULT_LOCAL_STOP_TOKENS
    temperature = float(pentest_cfg.get("temperature", 0.2))
    if tools:
        bound = llm.bind_tools(tools).bind(
            max_tokens=fallback_budget,
            stop=stop_tokens,
            temperature=temperature,
        )
    else:
        bound = llm.bind(
            max_tokens=fallback_budget,
            stop=stop_tokens,
            temperature=temperature,
        )

    sanitized_messages = _sanitize_local_prompt_messages(prompt_messages)
    logger.info(
        "[complex] Invoking pentest local model context=%d budget=%d (tools=%d)",
        max_context,
        fallback_budget,
        len(tools) if tools else 0,
    )
    response = await bound.ainvoke(sanitized_messages)
    return response, _local_api_tokens(response)


async def _invoke_local_fallback(
    *,
    prompt_messages: list,
    tools: list | None,
    budget: int,
    max_context: int,
) -> tuple[Any, str]:
    """Invoke local main model as fallback when cloud fails."""
    response, _api_tokens = await _invoke_local_path(
        prompt_messages=prompt_messages,
        tools=tools,
        budget=budget,
        max_context=max_context,
        is_fallback=True,
    )
    return response, "main-local-fallback"


def _deanonymize_ai_message(
    response: AIMessage, anon_mapping: dict[str, str]
) -> AIMessage:
    """Deanonymize assistant content, tool args, and reasoning_content."""
    content = response.content
    if content:
        content = deanonymize(str(content), anon_mapping)
    reasoning = getattr(response, "additional_kwargs", {}).get("reasoning_content")
    if reasoning:
        reasoning = deanonymize(str(reasoning), anon_mapping)
    tool_calls = getattr(response, "tool_calls", None) or []
    if tool_calls:
        for tc in tool_calls:
            if tc.get("args"):
                args_str = json.dumps(tc["args"])
                args_str = deanonymize(args_str, anon_mapping)
                tc["args"] = json.loads(args_str)
    kwargs = dict(getattr(response, "additional_kwargs", None) or {})
    if reasoning:
        kwargs["reasoning_content"] = reasoning
    return AIMessage(
        content=content,
        tool_calls=tool_calls,
        additional_kwargs=kwargs,
        id=getattr(response, "id", None),
    )
