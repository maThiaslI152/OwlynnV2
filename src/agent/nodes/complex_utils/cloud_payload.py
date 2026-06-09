"""
DeepSeek cloud payload assembly — prompt layers, anonymization, brief gate, API messages.

Prepares cache-friendly stable/volatile system prompts and converts LangChain messages
for DeepSeek API replay (including ``reasoning_content`` on tool loops).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.agent.anonymization import anonymize
from src.agent.hitl.cloud_brief import build_cloud_brief, estimate_brief_tokens
from src.agent.response_styles import style_instruction_for_prompt
from src.config.audit_log import audit_debug
from src.config.config_loader import config
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

# Stable system core — no date, memory, persona (cache-friendly prefix).
COMPLEX_PROMPT_STABLE = """### Identity
You are Owlynn, an expert reasoning agent. For complex tasks (code, math, multi-step work): think step by step before answering. For simple questions, greetings, or small talk: answer concisely without lengthy preamble.

### Behaviors
- If a request is clearly ambiguous or missing critical details, use ask_user once to clarify. If you can reasonably infer intent from context or memory, just do the work. Don't over-ask.
- When a request matches a known skill, call invoke_skill to get the workflow and follow it. Use list_skills to see available skills if unsure.
- Match your verbosity to the task: be thorough for complex work, be concise for simple questions.
- If project instructions are provided below, they take HIGHEST PRIORITY. Tailor your tone, focus, and approach to match the project's purpose.

### Guidelines
- If writing code, include comments
- When reasoning through a genuinely complex problem, show your thinking. Skip elaborate reasoning for trivial questions.
- Minimize markdown formatting (headers, bolding, heavy bullet lists) to save output tokens. Use plain text where possible.
- Never fabricate facts — if uncertain, say so{style_hint}"""

_VOLATILE_HEADER = """
### Session context (may change each turn)
Current date and time: {current_date}

User memory context:
{memory_context}

Knowledge Cache:
{knowledge_context}

Agent persona (for context only — do NOT echo or describe):
{persona}"""

_BRIEF_CACHE: dict[str, tuple[float, str]] = {}
_BRIEF_CACHE_TTL = float(config.get("memory.cache.ttl", 300))

_FRONTIER_HINTS = frozenset(
    {
        "prove",
        "theorem",
        "calculus",
        "frontier",
        "formal proof",
        "derive",
        "qed",
    }
)


@dataclass
class CloudThinkingConfig:
    """Resolved thinking mode for a single cloud invocation."""

    thinking_enabled: bool
    reasoning_effort: Optional[str] = None
    extra_body: dict = field(default_factory=dict)


@dataclass
class CloudPayload:
    """Prepared messages and metadata for a DeepSeek cloud call."""

    system_stable: str
    system_volatile: str
    system: SystemMessage
    messages: list[BaseMessage]
    prompt_messages: list[BaseMessage]
    anon_mapping: Optional[dict[str, str]]
    cloud_brief_tokens_est: int = 0
    anonymization_placeholders_count: int = 0
    vision_intake_mode: str = "text"
    vision_proxy_ok: bool = True


def has_tool_history(messages: list[BaseMessage]) -> bool:
    """Return True when thread contains tool calls or tool results."""
    for msg in messages:
        if isinstance(msg, ToolMessage):
            return True
        if getattr(msg, "tool_calls", None):
            return True
    return False


def resolve_cloud_thinking_config(
    *,
    state: dict,
    profile: dict,
    tools_bound: bool,
    mode: str,
) -> CloudThinkingConfig:
    """
    Resolve DeepSeek thinking.type and reasoning_effort for this request.

    Honors profile ``cloud_thinking_mode`` (auto|always|never) and
    ``tool_loop_force_thinking`` when user chose never but tools are active.
    """
    user_mode = str(
        profile.get("cloud_thinking_mode") or config.get("cloud.thinking_mode", "auto")
    ).lower()
    effort = str(
        profile.get("cloud_reasoning_effort")
        or config.get("cloud.reasoning_effort", "high")
    ).lower()
    if effort not in ("high", "max"):
        effort = "high"

    force_tools = bool(config.get("cloud.tool_loop_force_thinking", True))
    tool_active = has_tool_history(list(state.get("messages") or []))

    thinking_enabled = True
    if user_mode == "never":
        if force_tools and (tools_bound or tool_active):
            thinking_enabled = True
        else:
            thinking_enabled = False
    elif user_mode == "always":
        thinking_enabled = True
    else:
        # auto
        if mode == "tools_off" and not tool_active:
            thinking_enabled = False
        elif profile.get("cloud_model_tier") == "pro":
            thinking_enabled = True
        elif tool_active or tools_bound:
            thinking_enabled = True
        else:
            user_text = _last_user_text(state)
            if any(h in user_text.lower() for h in _FRONTIER_HINTS):
                effort = "max"
                thinking_enabled = True
            else:
                thinking_enabled = tools_bound

    extra: dict[str, Any] = {
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
    }
    reasoning: Optional[str] = effort if thinking_enabled else None
    return CloudThinkingConfig(
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning,
        extra_body=extra,
    )


def build_volatile_suffix(
    *,
    memory_context: str,
    knowledge_context: str,
    persona: str,
    extra_suffix: str = "",
) -> str:
    """Build volatile system suffix only (date, memory, persona — no stable core)."""
    block = _VOLATILE_HEADER.format(
        current_date=datetime.now().strftime("%B %d, %Y, %I:%M %p"),
        memory_context=memory_context or "None",
        knowledge_context=knowledge_context or "None",
        persona=persona or "No persona available",
    )
    return block + extra_suffix


def build_volatile_system_block(
    *,
    memory_context: str,
    knowledge_context: str,
    persona: str,
    style_hint: str,
    extra_suffix: str = "",
) -> str:
    """Build the volatile system suffix (date, memory, persona, dynamic notices)."""
    block = _VOLATILE_HEADER.format(
        current_date=datetime.now().strftime("%B %d, %Y, %I:%M %p"),
        memory_context=memory_context or "None",
        knowledge_context=knowledge_context or "None",
        persona=persona or "No persona available",
    )
    stable = COMPLEX_PROMPT_STABLE.format(style_hint=style_hint)
    return stable + block + extra_suffix


def message_to_deepseek_dict(msg: BaseMessage) -> dict:
    """
    Convert a LangChain message to DeepSeek/OpenAI API dict.

    Preserves ``reasoning_content`` on assistant messages for tool-loop replay.
    """
    if isinstance(msg, SystemMessage):
        return {"role": "system", "content": _content_to_str(msg.content)}
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    if isinstance(msg, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": msg.tool_call_id,
            "content": _content_to_str(msg.content),
        }
    if isinstance(msg, AIMessage):
        out: dict[str, Any] = {
            "role": "assistant",
            "content": _content_to_str(msg.content) or "",
        }
        reasoning = _extract_reasoning_content(msg)
        if reasoning:
            out["reasoning_content"] = reasoning
        if msg.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc.get("name"),
                        "arguments": json.dumps(tc.get("args", {}))
                        if isinstance(tc.get("args"), dict)
                        else str(tc.get("args", "")),
                    },
                }
                for tc in msg.tool_calls
            ]
        return out
    return {"role": "user", "content": _content_to_str(getattr(msg, "content", ""))}


def messages_to_deepseek_api(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to API payload list with reasoning_content preserved."""
    return [message_to_deepseek_dict(m) for m in messages]


def capture_cloud_response(response: Any) -> AIMessage:
    """
    Build AIMessage from cloud response, preserving reasoning_content when present.

    LangChain may place reasoning in additional_kwargs or on the message directly.
    """
    content = getattr(response, "content", None) or ""
    tool_calls = getattr(response, "tool_calls", None) or []
    reasoning = _extract_reasoning_content(response)
    if not reasoning:
        meta = getattr(response, "response_metadata", {}) or {}
        reasoning = meta.get("reasoning_content")
    content = finalize_cloud_visible_content(str(content), reasoning)
    kwargs: dict[str, Any] = {}
    if reasoning:
        kwargs["reasoning_content"] = reasoning
    return AIMessage(content=content, tool_calls=tool_calls, additional_kwargs=kwargs)


def finalize_cloud_visible_content(content: str, reasoning: str | None = None) -> str:
    """Use visible answer text; fall back to reasoning only when content is empty."""
    text = (content or "").strip()
    chain = (reasoning or "").strip()
    if not text and chain:
        return chain
    return text


def extract_api_token_usage(response: Any) -> dict[str, int]:
    """Extract prompt/completion and cache hit/miss tokens from a cloud response."""
    usage = getattr(response, "response_metadata", {}).get("token_usage", {})
    if not usage:
        usage = getattr(response, "usage_metadata", {}) or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    cache_hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    cache_miss = int(usage.get("prompt_cache_miss_tokens") or 0)
    if cache_miss == 0 and cache_hit == 0 and prompt > 0:
        cache_miss = prompt
    reasoning_tokens = 0
    details = usage.get("completion_tokens_details") or {}
    if isinstance(details, dict):
        reasoning_tokens = int(details.get("reasoning_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "prompt_cache_hit_tokens": cache_hit,
        "prompt_cache_miss_tokens": cache_miss,
        "reasoning_tokens": reasoning_tokens,
    }


def _brief_cache_key(state: dict) -> str:
    scope = state.get("clarified_scope") or {}
    plan = state.get("plan_review_approved")
    thread = state.get("thread_id") or state.get("conversation_id") or ""
    raw = json.dumps(
        {"scope": scope, "plan": plan, "thread": thread}, sort_keys=True, default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_cached_brief(key: str) -> Optional[str]:
    entry = _BRIEF_CACHE.get(key)
    if not entry:
        return None
    ts, text = entry
    if time.monotonic() - ts > _BRIEF_CACHE_TTL:
        del _BRIEF_CACHE[key]
        return None
    return text


def invalidate_brief_cache() -> None:
    """Clear cloud brief builder cache (e.g. after memory_write)."""
    _BRIEF_CACHE.clear()


async def prepare_cloud_payload(
    *,
    state: dict,
    system_stable: str,
    volatile_suffix: str,
    trimmed_messages: list[BaseMessage],
    vision_processor,
) -> CloudPayload:
    """
    Anonymize, apply cloud brief gate, run vision proxy, and assemble prompt messages.

    Parameters
    ----------
    vision_processor
        Async callable ``(messages) -> (messages, ok)`` — typically ``process_vision_messages``.
    """
    profile = get_profile()
    anon_mapping: Optional[dict[str, str]] = None
    anon_ctx = {
        "name": profile.get("name", ""),
        "custom_sensitive_terms": profile.get("custom_sensitive_terms", []),
    }

    volatile_text = volatile_suffix
    stable_text = system_stable

    if profile.get("cloud_anonymization_enabled", True):
        stable_text, m1 = anonymize(stable_text, anon_ctx)
        anon_mapping = m1 or anon_mapping
        volatile_text, m2 = anonymize(volatile_text, anon_ctx)
        if m2:
            anon_mapping = {**(anon_mapping or {}), **m2}

    anon_messages: list[BaseMessage] = []
    for msg in trimmed_messages:
        if isinstance(msg.content, str) and profile.get(
            "cloud_anonymization_enabled", True
        ):
            content, msg_mapping = anonymize(msg.content, anon_ctx)
            if msg_mapping:
                anon_mapping = {**(anon_mapping or {}), **msg_mapping}
            new_msg = copy.copy(msg)
            new_msg.content = content
            if isinstance(msg, AIMessage) and msg.tool_calls:
                new_msg.tool_calls = msg.tool_calls
            anon_messages.append(new_msg)
        else:
            anon_messages.append(msg)

    cloud_brief_tokens_est = 0
    placeholder_count = len(anon_mapping) if anon_mapping else 0
    use_brief = profile.get("cloud_brief_enabled", True) and not has_tool_history(
        trimmed_messages
    )

    if use_brief:
        cache_key = _brief_cache_key(state)
        brief = _get_cached_brief(cache_key)
        if not brief:
            plan_review_summary: dict[str, Any] | None = None
            if state.get("plan_review_approved") is not None:
                plan_review_summary = {
                    "approved": bool(state.get("plan_review_approved")),
                    "stated_intent": state.get("plan_review_feedback")
                    or "Plan reviewed",
                    "pitfalls": [],
                }
            last_user_message = ""
            last_assistant_summary = ""
            for msg in reversed(trimmed_messages):
                if isinstance(msg, HumanMessage) and not last_user_message:
                    last_user_message = str(msg.content)
                if isinstance(msg, AIMessage) and not last_assistant_summary:
                    c = str(msg.content)
                    last_assistant_summary = c[:300] if len(c) > 300 else c
                if last_user_message and last_assistant_summary:
                    break
            memory_context = ""
            if state.get("memory_context"):
                mc = state.get("memory_context")
                memory_context = str(mc) if isinstance(mc, str) else json.dumps(mc)
            brief = build_cloud_brief(
                clarified_scope=state.get("clarified_scope"),
                plan_review_summary=plan_review_summary,
                memory_context=memory_context,
                knowledge_context=str(state.get("knowledge_context") or ""),
                last_user_message=last_user_message,
                last_assistant_summary=last_assistant_summary,
                selected_toolboxes=state.get("selected_toolboxes"),
                max_chars=profile.get("cloud_brief_max_chars", 8000),
            )
            if brief:
                _BRIEF_CACHE[cache_key] = (time.monotonic(), brief)
        if brief:
            if profile.get("cloud_anonymization_enabled", True):
                brief, brief_mapping = anonymize(brief, anon_ctx)
                if brief_mapping:
                    anon_mapping = {**(anon_mapping or {}), **brief_mapping}
                    placeholder_count = len(anon_mapping)
            cloud_brief_tokens_est = estimate_brief_tokens(brief)
            anon_messages = [HumanMessage(content=brief)]
            audit_debug(
                "agent.cloud",
                "brief_applied",
                tokens_est=cloud_brief_tokens_est,
                placeholders=placeholder_count,
            )

    system_content = stable_text + volatile_text
    system = SystemMessage(content=system_content)
    prompt_messages = [system, *anon_messages]

    prompt_messages, vision_ok = await vision_processor(prompt_messages)
    vision_mode = "proxy" if vision_ok else "proxy_failed"

    if not vision_ok:
        logger.warning(
            "[cloud_payload] vision_proxy failed; cloud may lack image context"
        )

    if profile.get("cloud_anonymization_enabled", True) and anon_mapping is not None:
        reanon: list[BaseMessage] = []
        for msg in prompt_messages:
            if isinstance(msg, (SystemMessage, HumanMessage)) and isinstance(
                msg.content, str
            ):
                content, extra_map = anonymize(msg.content, anon_ctx)
                if extra_map:
                    anon_mapping = {**anon_mapping, **extra_map}
                    placeholder_count = len(anon_mapping)
                new_msg = copy.copy(msg)
                new_msg.content = content
                reanon.append(new_msg)
            else:
                reanon.append(msg)
        prompt_messages = reanon
        if prompt_messages:
            if isinstance(prompt_messages[0], SystemMessage):
                system = prompt_messages[0]
            anon_messages = prompt_messages[1:]

    return CloudPayload(
        system_stable=stable_text,
        system_volatile=volatile_text,
        system=system,
        messages=anon_messages,
        prompt_messages=prompt_messages,
        anon_mapping=anon_mapping,
        cloud_brief_tokens_est=cloud_brief_tokens_est,
        anonymization_placeholders_count=placeholder_count,
        vision_intake_mode=vision_mode,
        vision_proxy_ok=vision_ok,
    )


def _content_to_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(content or "")


def _extract_reasoning_content(msg: Any) -> Optional[str]:
    if hasattr(msg, "reasoning_content") and msg.reasoning_content:
        return str(msg.reasoning_content)
    ak = getattr(msg, "additional_kwargs", None) or {}
    if ak.get("reasoning_content"):
        return str(ak["reasoning_content"])
    return None


def _last_user_text(state: dict) -> str:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
        if getattr(msg, "type", None) == "human":
            return str(getattr(msg, "content", ""))
    return ""
