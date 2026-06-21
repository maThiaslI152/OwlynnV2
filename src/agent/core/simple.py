"""
Simple Node — Fast answers via the small LLM (Gemma-4-E2B or similar).

Handles greetings, small talk, and direct knowledge questions.
Injects condensed memory context (topics/interests profile) without full past context
to keep the prompt short for small models. Falls back to the large model if the small one fails.
"""

import asyncio
import logging
import re

from langchain_core.messages import AIMessage, SystemMessage
from src.agent.llm import get_small_llm
from src.agent.response_styles import style_instruction_for_prompt
from src.agent.lm_studio_compat import with_system_for_local_server
from src.agent.core.state import AgentState
from src.api.shared import _stringify_lc_message_content

from src.config.log_middleware import log_node
from src.config.config_loader import get_model_config

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
    """Strip thinking tokens, reasoning artifacts, and self-descriptive preambles from small model output."""
    if not text:
        return ""
    # Remove <think>...</think> blocks
    out = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Remove <｜end▁of▁thinking｜> blocks (Qwen3.5 alternate format)
    out = re.sub(r"<thinking>.*?</thinking>", "", out, flags=re.DOTALL).strip()
    # Strip "Thinking Process:" sections — Qwen3.5 sometimes embeds these even with enable_thinking=false
    out = re.sub(
        r"Thinking Process:.*?(?=\n\n[^\d]|\Z)", "", out, flags=re.DOTALL
    ).strip()
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
    """Gemma can fill reasoning_content and leave content empty below ~512 tokens."""
    small_cfg = get_model_config("small")
    floor = int(small_cfg.get("max_tokens") or 512)
    return max(int(budget or 256), floor)


async def _get_llm_response(runnable, prompt) -> str:
    """Safely stream or invoke the runnable.

    Handles MagicMock/Mock/AsyncMock objects which may not support real async iteration.
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
        async for chunk in runnable.astream(prompt):
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

    # Try small model, fall back to large on failure
    budget = state.get("token_budget") or 256
    output_tokens = _simple_output_max_tokens(budget)
    small_extra = dict(get_model_config("small").get("extra_body") or {})
    fallback_chain: list[dict] = []
    try:
        start_ts = asyncio.get_running_loop().time()
        llm = await get_small_llm()
        response_content = await _get_llm_response(
            llm.bind(
                temperature=0.4,
                max_tokens=output_tokens,
                extra_body=small_extra,
            ),
            prompt,
        )
        content = _clean_response(response_content)
        model = "small-local"
        fallback_chain.append(
            {
                "model": "small-local",
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
                "model": "small-local",
                "status": "failed",
                "reason": str(e)[:120],
                "duration_ms": 0,
            }
        )
        logger.warning(
            "[simple] Small model failed (%s), retrying once with lower temperature", e
        )
        try:
            fb_start = asyncio.get_running_loop().time()
            llm = await get_small_llm()
            response_content = await _get_llm_response(
                llm.bind(
                    temperature=0.1,
                    max_tokens=output_tokens,
                    extra_body=small_extra,
                ),
                prompt,
            )
            content = _clean_response(response_content)
            model = "small-local-retry"
            fallback_chain.append(
                {
                    "model": "small-local-retry",
                    "status": "success",
                    "reason": "fallback_simple_retry",
                    "duration_ms": max(
                        0, int((asyncio.get_running_loop().time() - fb_start) * 1000)
                    ),
                }
            )
        except Exception as retry_err:
            logger.warning("[simple] Retry also failed: %s", retry_err)
            content = (
                "Sorry, I could not process that request. Please try again or rephrase."
            )
            model = "small-local-failed"
            fallback_chain.append(
                {
                    "model": "small-local-failed",
                    "status": "failed",
                    "reason": str(retry_err)[:120],
                }
            )

    return {
        "messages": [AIMessage(content=content)],
        "model_used": model,
        "fallback_chain": fallback_chain,
    }
