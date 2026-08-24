"""LangGraph complex reasoning node — coordinator facade.

Orchestrates prompt assembly, LLM execution, fallback management, cutoff continuation,
and tool dispatch across modular sub-packages.

See:
- complex_prompt.py — prompt templates, tool guidance, context budgeting
- complex_executor.py — cloud/fallback execution, cutoff handling, telemetry
- complex_tool_action.py — parallel tool execution, output bounding
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage

from src.agent.cloud.cloud_payload import (
    COMPLEX_PROMPT_STABLE,
    build_volatile_suffix,
    prepare_cloud_payload,
)
from src.agent.core.complex_executor import (
    MAX_CUTOFF_RETRIES,
    _deanonymize_ai_message,
    _invoke_cloud_path,
    _invoke_local_fallback,
    _invoke_local_path,
    _invoke_pentest_path,
    _rerank_local_tools,
    _rerank_tools_for_bind,
    _vision_telemetry,
)
from src.agent.core.complex_prompt import (
    COMPLEX_TOOL_GUIDANCE_COMPACT,
    COMPLEX_TOOL_GUIDANCE_LOCAL_SYNTHESIS,
    COMPLEX_TOOL_GUIDANCE_NO_WEB,
    COMPLEX_TOOL_GUIDANCE_PENTEST,
    COMPLEX_TOOL_GUIDANCE_VISION,
    COMPLEX_TOOL_GUIDANCE_WEB,
    COMPLEX_TOOL_GUIDANCE_WEB_LOCAL,
    _count_ai_tool_rounds,
    _count_web_tool_rounds,
    _current_turn_has_web_activity,
    _looks_like_prose_tool_stall,
    _message_has_image_content,
    _messages_for_current_user_turn,
    _resolve_complex_tools,
    _trim_tool_history,
    _user_intent_needs_workspace_read,
    _workspace_paths_from_text,
)
from src.agent.core.complex_tool_action import (
    _extract_tool_output_delta,
    complex_tool_action_node,
)
from src.agent.core.complex_utils.cloud_fallback import handle_cloud_fallback
from src.agent.core.complex_utils.context_breakdown import (
    enrich_token_usage_with_breakdown,
)
from src.agent.core.complex_utils.fallback import _fallback_for_blank_response
from src.agent.core.complex_utils.formatter import (
    _strip_dsml_blocks,
    _strip_thinking_tags,
    needs_web_synthesis_retry,
)
from src.agent.core.complex_utils.web_budget import (
    WebBudgetStatus,
    evaluate_web_budget,
    filter_tools_for_web_budget,
    resolve_task_category,
)
from src.agent.core.state import AgentState
from src.agent.llm import CloudUnavailableError, get_cloud_llm
from src.agent.response_styles import style_instruction_for_prompt
from src.config.config_loader import config
from src.config.log_middleware import log_model_attempt, log_node
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_BUDGET = int(config.get("complex.default_token_budget", 4096))
_MAX_WEB_TOOL_ROUNDS = int(config.get("complex.max_web_tool_rounds", 3))
_TOOL_RERANK_TOP_K = int(config.get("complex.tool_rerank_top_k", 12))


def _resolve_tool_guidance(
    *,
    route: str,
    scenario_id: str | None,
    vision_task: bool,
    web_on: bool,
    bound_tool_count: int | None = None,
) -> str:
    # Compact guidance when the resolved set is already small (≈ rerank top_k).
    if (
        bound_tool_count is not None
        and bound_tool_count > 0
        and bound_tool_count <= _TOOL_RERANK_TOP_K
        and scenario_id != "pentest"
        and not vision_task
    ):
        return COMPLEX_TOOL_GUIDANCE_COMPACT
    if scenario_id == "pentest":
        return COMPLEX_TOOL_GUIDANCE_PENTEST
    if vision_task:
        return COMPLEX_TOOL_GUIDANCE_VISION
    if route == "complex-cloud":
        return COMPLEX_TOOL_GUIDANCE_WEB if web_on else COMPLEX_TOOL_GUIDANCE_NO_WEB
    return COMPLEX_TOOL_GUIDANCE_WEB_LOCAL if web_on else COMPLEX_TOOL_GUIDANCE_NO_WEB


def _skill_matched_volatile_suffix(state: dict) -> str:
    """Proactive skill hint (+ optional compact auto-inject) for volatile suffix."""
    skill = state.get("skill_matched")
    if not isinstance(skill, dict) or not skill.get("name"):
        return ""
    name = str(skill["name"])
    parts = [
        f"\n\n[SKILL HINT] Matched skill: {name}. "
        f"Call invoke_skill('{name}', context=...) first."
    ]
    if not config.get("routing.skill.auto_inject_enabled", False):
        return "".join(parts)

    score = float(skill.get("score") or 0.0)
    if score < 0.8:
        return "".join(parts)

    try:
        from src.tools.skills import (
            ContextInjector,
            _default_loader,
        )

        skill_def = _default_loader.get_by_name(name)
        if not skill_def:
            return "".join(parts)
        max_chars = int(config.get("routing.skill.auto_inject_max_chars", 1500))
        rendered = ContextInjector().inject(skill_def, context="")
        compact = rendered[:max_chars]
        if len(rendered) > max_chars:
            compact += "\n…[skill truncated]"
        parts.append(f"\n\n[SKILL CONTEXT — {name}]\n{compact}")
    except Exception as exc:
        logger.debug("[complex] skill auto-inject skipped: %s", exc)
    return "".join(parts)


def _apply_web_budget_to_tools(
    *,
    tools: list,
    tools_bound: bool,
    turn_messages: list,
    state: dict,
    volatile_extra: str,
) -> tuple[list | None, bool, str, WebBudgetStatus]:
    """Evaluate web budget and adjust tools + synthesis suffix."""
    web_budget = evaluate_web_budget(
        turn_messages,
        task_category=resolve_task_category(state),
        tool_round=_count_ai_tool_rounds(turn_messages),
        max_tool_rounds=_MAX_WEB_TOOL_ROUNDS,
    )
    tools_for_invoke: list | None = tools if tools_bound else None
    effective_tools_bound = tools_bound

    if tools_bound and tools:
        if web_budget.force_synthesis:
            tools_for_invoke = None
            effective_tools_bound = False
            volatile_extra += COMPLEX_TOOL_GUIDANCE_LOCAL_SYNTHESIS
        else:
            filtered = filter_tools_for_web_budget(tools, web_budget)
            if filtered is None:
                tools_for_invoke = None
                effective_tools_bound = False
            else:
                tools_for_invoke = filtered

    return tools_for_invoke, effective_tools_bound, volatile_extra, web_budget


def _rerank_tools_for_invoke(
    *,
    tools_for_invoke: list | None,
    tools_bound: bool,
    route: str,
    prompt_messages: list,
    state: dict,
) -> list | None:
    """Cap the bind list before invoke and context telemetry (shared list)."""
    if not tools_bound or not tools_for_invoke:
        return tools_for_invoke
    if route == "complex-cloud":
        return _rerank_tools_for_bind(
            tools_for_invoke,
            prompt_messages=prompt_messages,
            state=state,
            top_k=_TOOL_RERANK_TOP_K,
        )
    return _rerank_local_tools(tools_for_invoke, prompt_messages, state=state)


def _clean_ai_message(msg: AIMessage, *, is_length_cutoff: bool = False) -> AIMessage:
    if not msg.content:
        return msg
    cleaned = _strip_dsml_blocks(_strip_thinking_tags(str(msg.content)))
    if is_length_cutoff and cleaned.count("```") % 2 != 0:
        cleaned += "\n```\n"
    if cleaned == msg.content:
        return msg
    return AIMessage(
        content=cleaned,
        tool_calls=list(getattr(msg, "tool_calls", None) or []),
        additional_kwargs=dict(getattr(msg, "additional_kwargs", None) or {}),
        id=getattr(msg, "id", None),
    )


def _needs_synthesis_retry(
    response: AIMessage,
    *,
    turn_messages: list,
) -> bool:
    has_tool_calls = bool(getattr(response, "tool_calls", None))
    raw_visible = str(getattr(response, "content", "") or "")
    cleaned_visible = _strip_dsml_blocks(_strip_thinking_tags(raw_visible))
    if has_tool_calls:
        return False
    if needs_web_synthesis_retry(
        has_tool_calls=has_tool_calls,
        raw_visible=raw_visible,
        cleaned_visible=cleaned_visible,
    ):
        return True
    if _current_turn_has_web_activity(turn_messages):
        return _looks_like_prose_tool_stall(response) or not cleaned_visible.strip()
    return False


async def _retry_synthesis_once(
    *,
    state: dict,
    stable_core: str,
    volatile_extra: str,
    trimmed_messages: list,
    budget: int,
    route: str,
    scenario_id: str | None,
    profile: dict,
    mode: str,
    invoke_fn: Callable[..., Awaitable[tuple[Any, dict[str, int]]]],
    invoke_kwargs: dict[str, Any],
) -> tuple[Any, dict[str, int] | None]:
    """One synthesis-only retry with all tools unbound."""
    from src.agent.core.complex_utils.vision_proxy import process_vision_messages

    retry_extra = volatile_extra + COMPLEX_TOOL_GUIDANCE_LOCAL_SYNTHESIS
    retry_suffix = build_volatile_suffix(
        memory_context=str(state.get("memory_context") or ""),
        knowledge_context=str(state.get("knowledge_context") or ""),
        persona=str(state.get("persona") or "You are Owlynn, an expert assistant."),
        extra_suffix=retry_extra,
    )
    retry_payload = await prepare_cloud_payload(
        state=state,
        system_stable=stable_core,
        volatile_suffix=retry_suffix,
        trimmed_messages=trimmed_messages,
        vision_processor=process_vision_messages,
    )
    logger.info(
        "[complex] synthesis retry route=%s scenario=%s force_tools=None",
        route,
        scenario_id,
    )
    return await invoke_fn(
        prompt_messages=retry_payload.prompt_messages,
        tools=None,
        budget=budget,
        **invoke_kwargs,
    )


async def _finalize_response(
    *,
    response: Any,
    api_tokens: dict[str, int] | None,
    thread_messages: list,
    turn_messages: list,
    web_on: bool,
    web_budget: WebBudgetStatus,
    state: dict,
    stable_core: str,
    volatile_extra: str,
    trimmed_messages: list,
    budget: int,
    route: str,
    scenario_id: str | None,
    profile: dict,
    mode: str,
    invoke_fn: Callable[..., Awaitable[tuple[Any, dict[str, int]]]],
    invoke_kwargs: dict[str, Any],
    synthesis_retry_done: bool,
) -> tuple[Any, dict[str, int] | None, bool]:
    """Clean, optionally retry synthesis, and apply blank fallback."""
    if not isinstance(response, AIMessage):
        return response, api_tokens, synthesis_retry_done

    is_length_cutoff = False
    meta = getattr(response, "response_metadata", {})
    finish_reason = meta.get("finish_reason")
    completion_tokens = meta.get("token_usage", {}).get("completion_tokens", 0)
    is_length_cutoff = finish_reason in ("length", "max_tokens") or (
        completion_tokens > 256 and completion_tokens >= budget - 15
    )
    response = _clean_ai_message(response, is_length_cutoff=is_length_cutoff)

    should_retry = (
        not synthesis_retry_done
        and (
            web_budget.force_synthesis or _current_turn_has_web_activity(turn_messages)
        )
        and _needs_synthesis_retry(response, turn_messages=turn_messages)
    )

    if should_retry:
        try:
            retry_response, retry_tokens = await _retry_synthesis_once(
                state=state,
                stable_core=stable_core,
                volatile_extra=volatile_extra,
                trimmed_messages=trimmed_messages,
                budget=budget,
                route=route,
                scenario_id=scenario_id,
                profile=profile,
                mode=mode,
                invoke_fn=invoke_fn,
                invoke_kwargs=invoke_kwargs,
            )
            if isinstance(retry_response, AIMessage):
                retry_response = _clean_ai_message(retry_response)
                if not getattr(retry_response, "tool_calls", None):
                    cleaned = str(getattr(retry_response, "content", "") or "").strip()
                    if cleaned:
                        return retry_response, retry_tokens, True
                    response = retry_response
                    api_tokens = retry_tokens
            synthesis_retry_done = True
        except Exception as exc:
            logger.warning("[complex] synthesis retry failed: %s", exc)
            synthesis_retry_done = True

    if isinstance(response, AIMessage) and not getattr(response, "tool_calls", None):
        cleaned = _strip_dsml_blocks(
            _strip_thinking_tags(str(getattr(response, "content", "") or ""))
        ).strip()
        if not cleaned and (
            _current_turn_has_web_activity(turn_messages) or web_budget.force_synthesis
        ):
            return (
                _fallback_for_blank_response(
                    thread_messages, web_search_enabled=web_on
                ),
                api_tokens,
                synthesis_retry_done,
            )

    return response, api_tokens, synthesis_retry_done


@log_node("complex_llm")
async def complex_llm_node(state: AgentState) -> AgentState:
    """Complex reasoning node: prepares payload, executes LLM, handles cutoffs & fallbacks."""
    thread_messages = list(state.get("messages") or [])
    if not thread_messages:
        return {"messages": []}

    mode = state.get("mode") or "tools_on"
    route = state.get("route") or "complex-cloud"
    scenario_id = state.get("scenario_id")
    profile = get_profile()

    web_on = state.get("web_search_enabled")
    if web_on is None:
        web_on = True
    web_on = bool(web_on)

    turn_messages = _messages_for_current_user_turn(thread_messages)
    has_images = _message_has_image_content(thread_messages) or bool(
        (state.get("router_metadata") or {}).get("has_images")
    )
    vision_task = has_images and route == "complex-cloud"

    tools = _resolve_complex_tools(
        state, thread_messages, web_on=web_on, vision_task=vision_task
    )

    style_hint = style_instruction_for_prompt(state.get("response_style"))
    persona = state.get("persona") or "You are Owlynn, an expert assistant."
    memory_context = state.get("memory_context") or ""
    knowledge_context = state.get("knowledge_context") or ""

    volatile_extra = ""
    execution_plan = state.get("execution_plan")
    if execution_plan:
        volatile_extra += (
            f"\n\n[EXECUTION PLAN]\n"
            f"The routing logic has generated the following step-by-step plan for you to follow:\n"
            f"{execution_plan}\n"
            f"You should execute these steps using your tools."
        )

    if (state.get("selected_toolboxes") or []) == ["none"]:
        volatile_extra += (
            "\n\n[NO TOOLS AVAILABLE] You have no tools for this turn. "
            "Answer the user's question directly from the conversation history "
            "and memory context provided above. Do NOT attempt to call any tools."
        )

    volatile_extra += _skill_matched_volatile_suffix(state)

    stable_core = COMPLEX_PROMPT_STABLE.format(style_hint=style_hint)
    if mode != "tools_off":
        stable_core += _resolve_tool_guidance(
            route=route,
            scenario_id=scenario_id,
            vision_task=vision_task,
            web_on=web_on,
            bound_tool_count=len(tools) if tools else 0,
        )

    trimmed_messages = _trim_tool_history(thread_messages)
    max_context = int(config.get("models.cloud.context_window", 1048576))
    local_max_context = int(config.get("models.main.context_window", 16384))
    model_label = "large-cloud"
    fallback_chain: list[dict] = []

    tools_bound = mode != "tools_off" and (state.get("selected_toolboxes") or []) != [
        "none"
    ]
    tools_for_invoke, tools_bound, volatile_extra, web_budget = (
        _apply_web_budget_to_tools(
            tools=tools,
            tools_bound=tools_bound,
            turn_messages=turn_messages,
            state=state,
            volatile_extra=volatile_extra,
        )
    )

    from src.agent.core.complex_utils.vision_proxy import process_vision_messages

    async def _local_fallback_with_state(**kwargs):
        return await _invoke_local_fallback(state=state, **kwargs)

    volatile_suffix = build_volatile_suffix(
        memory_context=str(memory_context),
        knowledge_context=str(knowledge_context),
        persona=str(persona),
        extra_suffix=volatile_extra,
    )
    payload = await prepare_cloud_payload(
        state=state,
        system_stable=stable_core,
        volatile_suffix=volatile_suffix,
        trimmed_messages=trimmed_messages,
        vision_processor=process_vision_messages,
    )
    prompt_messages = payload.prompt_messages
    anon_mapping = payload.anon_mapping
    cloud_brief_tokens_est = payload.cloud_brief_tokens_est
    anonymization_placeholders_count = payload.anonymization_placeholders_count
    vision_intake_mode = payload.vision_intake_mode

    tools_for_invoke = _rerank_tools_for_invoke(
        tools_for_invoke=tools_for_invoke,
        tools_bound=tools_bound,
        route=route,
        prompt_messages=prompt_messages,
        state=state,
    )

    if not payload.vision_proxy_ok and has_images:
        logger.warning("[complex] vision_proxy failed; attempting local fallback")
        return await handle_cloud_fallback(
            invoke_local_fallback=_local_fallback_with_state,
            fallback_chain=fallback_chain,
            reason="vision_proxy_failed",
            prompt_messages=prompt_messages,
            tools=None,
            vision_intake_mode="proxy",
            cloud_brief_tokens_est=cloud_brief_tokens_est,
            anonymization_placeholders_count=anonymization_placeholders_count,
        )

    budget = state.get("token_budget") or _DEFAULT_TOKEN_BUDGET
    api_tokens: dict[str, int] | None = None
    response: Any = None
    synthesis_retry_done = False

    if route == "complex-cloud":
        try:
            cloud_llm = await get_cloud_llm(profile.get("cloud_model_tier"))
            model_label = "large-cloud"
            response, api_tokens = await _invoke_cloud_path(
                llm=cloud_llm,
                prompt_messages=prompt_messages,
                tools=tools_for_invoke,
                budget=budget,
                state=state,
                profile=profile,
                mode=mode,
                tools_bound=tools_bound,
            )
            log_model_attempt(model_label, "success", reason="cloud_primary")
        except CloudUnavailableError as e:
            logger.warning("[complex] Cloud unavailable: %s", e)
            return await handle_cloud_fallback(
                invoke_local_fallback=_local_fallback_with_state,
                fallback_chain=fallback_chain,
                reason="cloud_unavailable",
                prompt_messages=prompt_messages,
                tools=tools_for_invoke if tools_bound else None,
                vision_intake_mode=vision_intake_mode,
                cloud_brief_tokens_est=cloud_brief_tokens_est,
                anonymization_placeholders_count=anonymization_placeholders_count,
            )
        except Exception as exc:
            logger.warning(
                "[complex] Cloud invocation error (%s), attempting local fallback", exc
            )
            return await handle_cloud_fallback(
                invoke_local_fallback=_local_fallback_with_state,
                fallback_chain=fallback_chain,
                reason=f"cloud_error_{type(exc).__name__}",
                prompt_messages=prompt_messages,
                tools=tools_for_invoke if tools_bound else None,
                vision_intake_mode=vision_intake_mode,
                cloud_brief_tokens_est=cloud_brief_tokens_est,
                anonymization_placeholders_count=anonymization_placeholders_count,
            )

        async def _cloud_retry_invoke(*, prompt_messages, tools, budget, **_kw):
            retry_llm = await get_cloud_llm(profile.get("cloud_model_tier"))
            return await _invoke_cloud_path(
                llm=retry_llm,
                prompt_messages=prompt_messages,
                tools=tools,
                budget=budget,
                state=state,
                profile=profile,
                mode=mode,
                tools_bound=False,
            )

        response, api_tokens, synthesis_retry_done = await _finalize_response(
            response=response,
            api_tokens=api_tokens,
            thread_messages=thread_messages,
            turn_messages=turn_messages,
            web_on=web_on,
            web_budget=web_budget,
            state=state,
            stable_core=stable_core,
            volatile_extra=volatile_extra,
            trimmed_messages=trimmed_messages,
            budget=budget,
            route=route,
            scenario_id=scenario_id,
            profile=profile,
            mode=mode,
            invoke_fn=_cloud_retry_invoke,
            invoke_kwargs={},
            synthesis_retry_done=synthesis_retry_done,
        )
    elif scenario_id == "pentest":
        model_label = "pentest-local"
        try:
            log_model_attempt(model_label, "success", reason="pentest_local")
            response, api_tokens = await _invoke_pentest_path(
                prompt_messages=prompt_messages,
                tools=tools_for_invoke if tools_bound else None,
                budget=budget,
                max_context=local_max_context,
                state=state,
            )
        except Exception as e:
            logger.warning("[complex] Pentest LLM failed: %s", e)
            return await handle_cloud_fallback(
                invoke_local_fallback=_local_fallback_with_state,
                fallback_chain=fallback_chain,
                reason="pentest_llm_unavailable",
                prompt_messages=prompt_messages,
                tools=tools_for_invoke if tools_bound else None,
                vision_intake_mode=vision_intake_mode,
                cloud_brief_tokens_est=cloud_brief_tokens_est,
                anonymization_placeholders_count=anonymization_placeholders_count,
            )

        response, api_tokens, synthesis_retry_done = await _finalize_response(
            response=response,
            api_tokens=api_tokens,
            thread_messages=thread_messages,
            turn_messages=turn_messages,
            web_on=web_on,
            web_budget=web_budget,
            state=state,
            stable_core=stable_core,
            volatile_extra=volatile_extra,
            trimmed_messages=trimmed_messages,
            budget=budget,
            route=route,
            scenario_id=scenario_id,
            profile=profile,
            mode=mode,
            invoke_fn=_invoke_pentest_path,
            invoke_kwargs={"max_context": local_max_context, "state": state},
            synthesis_retry_done=synthesis_retry_done,
        )
    else:
        model_label = "main-local"
        try:
            log_model_attempt(model_label, "success", reason="local_primary")
            response, api_tokens = await _invoke_local_path(
                prompt_messages=prompt_messages,
                tools=tools_for_invoke if tools_bound else None,
                budget=budget,
                max_context=local_max_context,
                state=state,
            )
        except Exception as e:
            logger.warning("[complex] Local main LLM failed: %s", e)
            return await handle_cloud_fallback(
                invoke_local_fallback=_local_fallback_with_state,
                fallback_chain=fallback_chain,
                reason="local_main_error",
                prompt_messages=prompt_messages,
                tools=tools_for_invoke if tools_bound else None,
                vision_intake_mode=vision_intake_mode,
                cloud_brief_tokens_est=cloud_brief_tokens_est,
                anonymization_placeholders_count=anonymization_placeholders_count,
            )

        response, api_tokens, synthesis_retry_done = await _finalize_response(
            response=response,
            api_tokens=api_tokens,
            thread_messages=thread_messages,
            turn_messages=turn_messages,
            web_on=web_on,
            web_budget=web_budget,
            state=state,
            stable_core=stable_core,
            volatile_extra=volatile_extra,
            trimmed_messages=trimmed_messages,
            budget=budget,
            route=route,
            scenario_id=scenario_id,
            profile=profile,
            mode=mode,
            invoke_fn=_invoke_local_path,
            invoke_kwargs={"max_context": local_max_context, "state": state},
            synthesis_retry_done=synthesis_retry_done,
        )

    if anon_mapping:
        response = _deanonymize_ai_message(response, anon_mapping)

    out_messages = [response]
    has_tool_calls = bool(getattr(response, "tool_calls", None))

    _cutoff_round = state.get("_cutoff_round", 0)
    meta = getattr(response, "response_metadata", {})
    finish_reason = meta.get("finish_reason")
    completion_tokens = meta.get("token_usage", {}).get("completion_tokens", 0)
    is_length_cutoff = finish_reason in ("length", "max_tokens") or (
        completion_tokens > 256 and completion_tokens >= budget - 15
    )

    if (
        not has_tool_calls
        and _cutoff_round < MAX_CUTOFF_RETRIES
        and response
        and is_length_cutoff
    ):
        logger.info(
            "[complex] Response cut off, auto-continuing round %d/%d",
            _cutoff_round + 1,
            MAX_CUTOFF_RETRIES,
        )
        api_tokens = enrich_token_usage_with_breakdown(
            api_tokens,
            prompt_messages,
            max_context=max_context,
            bound_tools=tools_for_invoke if tools_bound else None,
        )
        return {
            "messages": out_messages,
            "model_used": model_label,
            "pending_tool_calls": False,
            "security_decision": None,
            "security_reason": None,
            "_cutoff_pending": True,
            "_cutoff_round": _cutoff_round + 1,
            "api_tokens_used": api_tokens,
            "fallback_chain": fallback_chain,
            "cloud_brief_tokens_est": cloud_brief_tokens_est,
            "anonymization_placeholders_count": anonymization_placeholders_count,
            **_vision_telemetry(vision_intake_mode),
        }

    api_tokens = enrich_token_usage_with_breakdown(
        api_tokens,
        prompt_messages,
        max_context=max_context,
        bound_tools=tools_for_invoke if tools_bound else None,
    )
    return {
        "messages": out_messages,
        "model_used": model_label,
        "pending_tool_calls": has_tool_calls,
        "security_decision": None,
        "security_reason": None,
        "_cutoff_pending": False,
        "_cutoff_round": _cutoff_round,
        "api_tokens_used": api_tokens,
        "fallback_chain": fallback_chain,
        "cloud_brief_tokens_est": cloud_brief_tokens_est,
        "anonymization_placeholders_count": anonymization_placeholders_count,
        **_vision_telemetry(vision_intake_mode),
    }


__all__ = [
    "_count_web_tool_rounds",
    "_extract_tool_output_delta",
    "_fallback_for_blank_response",
    "_looks_like_prose_tool_stall",
    "_messages_for_current_user_turn",
    "_resolve_complex_tools",
    "_user_intent_needs_workspace_read",
    "_workspace_paths_from_text",
    "complex_llm_node",
    "complex_tool_action_node",
]
