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
_CLOUD_RERANK_TOP_K = int(config.get("complex.tool_rerank_top_k", 12))
_RERANK_MIN_COUNT = int(config.get("complex.tool_rerank_min_count", 10))


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


def _extract_last_user_text(prompt_messages: list) -> str:
    """Best-effort last user message text for tool rerank query."""
    for msg in reversed(prompt_messages or []):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                return " ".join(parts)
            return str(content or "")
    if prompt_messages:
        return str(getattr(prompt_messages[-1], "content", "") or "")
    return ""


def _collect_prev_tool_names(messages: list | None) -> set[str]:
    names: set[str] = set()
    for msg in messages or []:
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name", "")
            else:
                name = getattr(tc, "name", "") or ""
            if name:
                names.add(str(name))
    return names


def _build_rerank_query(prompt_messages: list, state: dict | None = None) -> str:
    """Query text: last user message + optional task_category + skill name."""
    parts = [_extract_last_user_text(prompt_messages)]
    state = state or {}
    meta = state.get("router_metadata") or {}
    features = meta.get("features") if isinstance(meta, dict) else None
    task_category = None
    if isinstance(features, dict):
        task_category = features.get("task_category")
    elif isinstance(meta, dict):
        task_category = meta.get("task_category")
    if task_category:
        parts.append(str(task_category))
    skill = state.get("skill_matched")
    if isinstance(skill, dict) and skill.get("name"):
        parts.append(str(skill["name"]))
    elif isinstance(skill, str) and skill:
        parts.append(skill)
    return " ".join(p for p in parts if p).strip()


def _pinned_tool_names(state: dict | None = None) -> set[str]:
    pinned = {"ask_user"}
    cfg_pinned = config.get("complex.pinned_tools") or ["ask_user"]
    if isinstance(cfg_pinned, list):
        pinned.update(str(n) for n in cfg_pinned if n)
    if state:
        pinned |= _collect_prev_tool_names(state.get("messages"))
    return pinned


def _rerank_tools_for_bind(
    tools: list | None,
    *,
    prompt_messages: list | None = None,
    state: dict | None = None,
    top_k: int | None = None,
    min_count: int | None = None,
    query: str | None = None,
) -> list | None:
    """Shared embedding rerank before bind_tools (local, pentest, cloud).

    Always keeps pinned tools (ask_user + config) and tools used in the current
    thread; reranks the remainder to fill ``top_k``. Result is sorted
    alphabetically for KV-cache stability.
    """
    if not tools:
        return tools

    from src.agent.tool_reranker import rerank_tools

    sorted_tools = sorted(tools, key=lambda t: getattr(t, "name", str(t)))

    if not config.get("complex.tool_rerank_enabled", True):
        return sorted_tools

    threshold = (
        min_count
        if min_count is not None
        else int(config.get("complex.tool_rerank_min_count", _RERANK_MIN_COUNT))
    )
    if len(sorted_tools) <= threshold:
        return sorted_tools

    k = (
        top_k
        if top_k is not None
        else int(config.get("complex.tool_rerank_top_k", _CLOUD_RERANK_TOP_K))
    )
    pinned = _pinned_tool_names(state)
    must_keep = [t for t in sorted_tools if getattr(t, "name", "") in pinned]
    remainder = [t for t in sorted_tools if getattr(t, "name", "") not in pinned]

    slots = max(0, k - len(must_keep))
    if slots <= 0:
        selected = must_keep[:k] if len(must_keep) > k else must_keep
    elif not remainder:
        selected = must_keep
    else:
        q = (
            query
            if query is not None
            else _build_rerank_query(prompt_messages or [], state)
        )
        selected_remainder = rerank_tools(str(q), remainder, top_k=slots)
        selected = must_keep + list(selected_remainder)

    # Dedup by name, then alphabetical sort for KV cache
    seen: set[str] = set()
    deduped: list = []
    for t in selected:
        name = getattr(t, "name", str(t))
        if name in seen:
            continue
        seen.add(name)
        deduped.append(t)
    return sorted(deduped, key=lambda t: getattr(t, "name", str(t)))


def _rerank_local_tools(
    tools: list | None,
    prompt_messages: list,
    *,
    state: dict | None = None,
) -> list | None:
    """Backward-compatible local/pentest wrapper around shared rerank helper."""
    return _rerank_tools_for_bind(
        tools,
        prompt_messages=prompt_messages,
        state=state,
        top_k=_LOCAL_RERANK_TOP_K,
    )


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

    if tools_bound and tools:
        tools = _rerank_tools_for_bind(
            tools,
            prompt_messages=prompt_messages,
            state=state,
            top_k=_CLOUD_RERANK_TOP_K,
        )

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
    state: dict | None = None,
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

    tools = _rerank_local_tools(tools, prompt_messages, state=state)
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
    state: dict | None = None,
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
    tools = _rerank_local_tools(tools, prompt_messages, state=state)
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
    state: dict | None = None,
) -> tuple[Any, str]:
    """Invoke local main model as fallback when cloud fails."""
    response, _api_tokens = await _invoke_local_path(
        prompt_messages=prompt_messages,
        tools=tools,
        budget=budget,
        max_context=max_context,
        is_fallback=True,
        state=state,
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
