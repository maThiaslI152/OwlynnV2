"""
Simple Node — Fast answers via the small LLM (LFM2.5-1.2B or similar).

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
from src.agent.state import AgentState

from src.config.audit_log import audit_info
from src.config.log_middleware import log_node

logger = logging.getLogger(__name__)

SIMPLE_PROMPT = (
    "Today is {current_date}. "
    "Give short, direct answers (1-3 sentences). "
    "No reasoning steps, no preamble, no meta commentary. "
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
    out = re.sub(r"Thinking Process:.*?(?=\n\n[^\d]|\Z)", "", out, flags=re.DOTALL).strip()
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
        out = out[persona_echo.end():].strip()
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
        
    system = SystemMessage(content=SIMPLE_PROMPT.format(
        persona_prefix=persona_prefix,
        current_date=date.today().strftime('%B %d, %Y'),
        style_hint=style_hint,
        memory_hint=memory_hint,
    ))
    messages = list(state.get("messages") or [])
    prompt = with_system_for_local_server(system, messages)

    # Try small model, fall back to large on failure
    budget = state.get("token_budget") or 256
    fallback_chain: list[dict] = []
    try:
        start_ts = asyncio.get_running_loop().time()
        llm = await get_small_llm()
        response = await llm.bind(temperature=0.4, max_tokens=budget).ainvoke(prompt)
        content = _clean_response(response.content or "")
        model = "small-local"
        fallback_chain.append({
            "model": "small-local",
            "status": "success",
            "reason": "simple_route",
            "duration_ms": max(0, int((asyncio.get_running_loop().time() - start_ts) * 1000)),
        })
    except Exception as e:
        logger.warning("[simple] Small model failed (%s), falling back to medium-default", e)
        fallback_chain.append({
            "model": "small-local",
            "status": "failed",
            "reason": str(e)[:120],
            "duration_ms": 0,
        })
        from src.agent.llm import get_medium_llm
        fb_start = asyncio.get_running_loop().time()
        llm = await get_medium_llm("default")
        response = await llm.bind(temperature=0.4, max_tokens=budget).ainvoke(prompt)
        content = _clean_response(response.content or "")
        model = "medium-default-fallback"
        fallback_chain.append({
            "model": "medium-default-fallback",
            "status": "success",
            "reason": "fallback_simple_failed",
            "duration_ms": max(0, int((asyncio.get_running_loop().time() - fb_start) * 1000)),
        })

    return {"messages": [AIMessage(content=content)], "model_used": model, "fallback_chain": fallback_chain}
