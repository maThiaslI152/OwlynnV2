"""
Simple Node — Fast answers via the main local model.

Handles greetings, small talk, and direct knowledge questions.
Injects condensed memory context (topics/interests profile) without full past context
to keep the prompt concise.
"""

import asyncio
import logging
import re

from langchain_core.messages import AIMessage, SystemMessage

from src.agent.core.state import AgentState
from src.agent.llm import get_main_llm

get_small_llm = get_main_llm
from src.agent.lm_studio_compat import with_system_for_local_server
from src.agent.response_styles import style_instruction_for_prompt
from src.api.shared import _stringify_lc_message_content
from src.config.config_loader import get_model_config
from src.config.log_middleware import log_node

logger = logging.getLogger(__name__)

SIMPLE_PROMPT = (
    "Today is {current_date}. "
    "Give short, direct answers (1-3 sentences). "
    "No reasoning steps, no preamble, no meta commentary. "
    "Minimize markdown formatting (bolding, headers, lists) to save output tokens. Use plain text where possible. "
    "Never describe, repeat, or reference your own identity, role, purpose, or persona — just answer the question directly. "
    "Do not start responses with 'You are', 'I am', or any self-description."
    "{style_hint}"
    "{memory_hint}"
    "\n\nPersona (for context only — do NOT echo or describe): {persona_prefix}"
)


def _clean_response(text: str) -> str:
    """Strip thinking tokens, reasoning artifacts, and self-descriptive preambles from local model output."""
    if not text:
        return ""
    from src.agent.core.complex_utils.formatter import (
        _content_has_dsml_tool_syntax,
        _strip_dsml_blocks,
    )

    had_tool_leak = _content_has_dsml_tool_syntax(text)
    # Remove <think>...</think> blocks
    out = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Remove <｜end▁of▁thinking｜> blocks (Qwen3.5 alternate format)
    out = re.sub(r"<thinking>.*?</thinking>", "", out, flags=re.DOTALL).strip()
    # Strip "Thinking Process:" sections — Qwen3.5 sometimes embeds these even with enable_thinking=false
    out = re.sub(
        r"Thinking Process:.*?(?=\n\n[^\d]|\Z)", "", out, flags=re.DOTALL
    ).strip()
    # Local models sometimes emit unbound tool markup on the no-tools simple path
    out = _strip_dsml_blocks(out).strip()
    # Strip self-descriptive preambles (model echoing system prompt folded into user message)
    out = re.sub(
        r"^\[SYSTEM INSTRUCTIONS BEGIN\].*?\[SYSTEM INSTRUCTIONS END\]\s*",
        "",
        out,
        flags=re.DOTALL,
    ).strip()
    # Strip raw persona/identity echoes (model describes itself without the markers above).
    # Matches patterns like: "You are Owlynn, a ... assistant. ..." or "I am Owlynn..."
    persona_echo = re.match(
        r"^\s*((You are|I am)\s+Owlynn[^.]+\.\s*)+",
        out,
    )
    if persona_echo:
        out = out[persona_echo.end() :].strip()
    # Remove numbered reasoning steps (e.g. "1. **Analyze**...")
    lines = out.split("\n")
    kept: list[str] = []
    skip = False
    for line in lines:
        s = line.strip()
        if re.match(r"^\d+\.\s+\*\*", s) or s.startswith("Thinking Process:"):
            skip = True
            continue
        if skip and not s:
            continue
        if s and not s.startswith("*   "):
            skip = False
            kept.append(line)
    result = "\n".join(kept).strip()
    if not result:
        # Fallback: extract quoted strings from reasoning
        quotes = re.findall(r'"([^"]{5,})"', out)
        result = quotes[-1] if quotes else out
    if had_tool_leak and (not result.strip() or _content_has_dsml_tool_syntax(result)):
        return (
            "I need a live web lookup for that, but this turn ran on the "
            "no-tools path. Please ask again (e.g. “search the web for Bangkok GDP”)."
        )
    return result or text


def _extract_llm_text(chunk_or_message) -> str:
    """Flatten visible assistant text; fall back to reasoning_content when content is empty."""
    text = _stringify_lc_message_content(getattr(chunk_or_message, "content", None))
    if text:
        return text
    extra = getattr(chunk_or_message, "additional_kwargs", None) or {}
    reasoning = extra.get("reasoning_content") or getattr(
        chunk_or_message, "reasoning_content", None
    )
    return str(reasoning or "")


def _simple_output_max_tokens(budget: int | None) -> int:
    """Cap simple-path completion; never inherit models.main.max_tokens (often 8k).

    A huge max_tokens window slows local decode and invites verbose greetings.
    Router ``token_budget`` (typically 128–256 for trivia) is honored within
    ``simple.max_tokens``.
    """
    from src.config.config_loader import config

    requested = max(64, int(budget or 256))
    cap = max(64, int(config.get("simple.max_tokens", 256) or 256))
    # Honor small trivia budgets (e.g. 128) instead of forcing a 256 floor.
    floor = min(64, cap)
    return max(floor, min(requested, cap))


def _runnable_config_for_stream():
    """Inherit LangGraph callbacks so astream emits on_chat_model_stream to WS."""
    try:
        from langgraph.config import get_config

        return get_config()
    except RuntimeError:
        return None


async def _get_llm_response(runnable, prompt) -> str:
    """Safely stream or invoke the runnable.

    Handles MagicMock/Mock/AsyncMock objects which may not support real async iteration.
    Passes LangGraph config into astream so token chunks reach the WS handler early
    (otherwise TTFT ≈ full generate because only on_chain_end flushed text).
    """
    is_mock = False
    astream_attr = getattr(runnable, "astream", None)
    for obj in (runnable, astream_attr):
        if obj is not None:
            tp_name = type(obj).__name__
            if "mock" in tp_name.lower():
                is_mock = True
                break

    if is_mock or not hasattr(runnable, "astream"):
        response = await runnable.ainvoke(prompt)
        return (
            _extract_llm_text(response)
            if hasattr(response, "content")
            else str(response)
        )

    try:
        response_content = ""
        stream_cfg = _runnable_config_for_stream()
        if stream_cfg is not None:
            stream_iter = runnable.astream(prompt, config=stream_cfg)
        else:
            stream_iter = runnable.astream(prompt)
        async for chunk in stream_iter:
            part = _extract_llm_text(chunk)
            if part:
                response_content += part
        return response_content
    except (TypeError, AttributeError):
        response = await runnable.ainvoke(prompt)
        return (
            _extract_llm_text(response)
            if hasattr(response, "content")
            else str(response)
        )


@log_node("simple")
async def simple_node(state: AgentState) -> AgentState:
    """Fast-path node: short answers without tools."""
    style_hint = style_instruction_for_prompt(state.get("response_style"))
    from datetime import date

    # Inject condensed memory context (topics/interests only, no past context) for personalization
    memory_ctx = state.get("memory_context") or ""
    memory_hint = ""
    # Extract the "Your Knowledge About User" section if present (topics/interests)
    if memory_ctx and "=== Your Knowledge About User ===" in memory_ctx:
        parts = memory_ctx.split("=== Your Knowledge About User ===")
        if len(parts) > 1:
            knowledge = parts[1].split("===")[0].strip()
            if knowledge:
                memory_hint = f"\n{knowledge}"
    persona_desc = state.get("persona")
    if persona_desc and persona_desc != "None":
        persona_prefix = persona_desc
    else:
        persona_prefix = "You are Owlynn, a helpful assistant."

    system = SystemMessage(
        content=SIMPLE_PROMPT.format(
            persona_prefix=persona_prefix,
            current_date=date.today().strftime("%B %d, %Y"),
            style_hint=style_hint,
            memory_hint=memory_hint,
        )
    )
    messages = list(state.get("messages") or [])
    prompt = with_system_for_local_server(system, messages)

    # Direct response via main local model
    budget = state.get("token_budget") or 256
    output_tokens = _simple_output_max_tokens(budget)
    main_extra = dict(get_model_config("main").get("extra_body") or {})
    fallback_chain: list[dict] = []
    try:
        start_ts = asyncio.get_running_loop().time()
        llm = await get_small_llm()
        response_content = await _get_llm_response(
            llm.bind(
                temperature=0.4,
                max_tokens=output_tokens,
                extra_body=main_extra,
            ),
            prompt,
        )
        content = _clean_response(response_content)
        model = "main-local"
        fallback_chain.append(
            {
                "model": "main-local",
                "status": "success",
                "reason": "simple_route",
                "duration_ms": max(
                    0, int((asyncio.get_running_loop().time() - start_ts) * 1000)
                ),
            }
        )
    except Exception as e:
        fallback_chain.append(
            {
                "model": "main-local",
                "status": "failed",
                "reason": str(e)[:120],
                "duration_ms": 0,
            }
        )
        logger.warning(
            "[simple] Main model failed (%s), retrying once with lower temperature", e
        )
        try:
            fb_start = asyncio.get_running_loop().time()
            llm = await get_small_llm()
            response_content = await _get_llm_response(
                llm.bind(
                    temperature=0.1,
                    max_tokens=output_tokens,
                    extra_body=main_extra,
                ),
                prompt,
            )
            content = _clean_response(response_content)
            model = "main-local-retry"
            fallback_chain.append(
                {
                    "model": "main-local",
                    "status": "success",
                    "reason": "retry_lower_temp",
                    "duration_ms": max(
                        0, int((asyncio.get_running_loop().time() - fb_start) * 1000)
                    ),
                }
            )
        except Exception as retry_err:
            fallback_chain.append(
                {
                    "model": "main-local",
                    "status": "failed",
                    "reason": f"retry_failed: {str(retry_err)[:100]}",
                    "duration_ms": 0,
                }
            )
            logger.error("[simple] Retry also failed: %s", retry_err)
            content = (
                "I apologize, but I encountered an error generating a response. "
                "Please try again."
            )
            model = "main-local-failed"

    return {
        "messages": [AIMessage(content=content)],
        "model_used": model,
        "fallback_chain": fallback_chain,
    }
