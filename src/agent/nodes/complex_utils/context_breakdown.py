"""Estimate per-category context usage for cloud/local complex turns."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


def _message_char_count(msg) -> int:
    content = getattr(msg, "content", None) or ""
    total = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                total += len(block)
            elif isinstance(block, dict):
                total += len(str(block.get("text", "")))
    else:
        total += len(str(content))
    return total + 20  # role / formatting overhead


def _chars_to_tokens(chars: int) -> int:
    return max(0, int(chars / 3.5))


def estimate_message_category_tokens(msg) -> tuple[str, int]:
    """Return (category, estimated_tokens) for one LangChain message."""
    tokens = _chars_to_tokens(_message_char_count(msg))
    if isinstance(msg, SystemMessage):
        return "system", tokens
    if isinstance(msg, ToolMessage):
        return "tools", tokens
    if isinstance(msg, (HumanMessage, AIMessage)):
        return "conversation", tokens
    return "conversation", tokens


def estimate_context_breakdown(
    prompt_messages: list,
    *,
    max_context: int,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    input_actual: int | None = None,
) -> dict:
    """
    Build OpenCode-style context breakdown: system / conversation / tools / output
    as token counts and percentages of max_context.
    """
    categories = {"system": 0, "conversation": 0, "tools": 0}
    for msg in prompt_messages or []:
        cat, n = estimate_message_category_tokens(msg)
        categories[cat] = categories.get(cat, 0) + n

    input_estimated = sum(categories.values())
    if input_actual and input_actual > 0 and input_estimated > 0:
        scale = input_actual / input_estimated
        categories = {k: int(v * scale) for k, v in categories.items()}
        input_estimated = input_actual
    elif input_actual and input_actual > 0:
        input_estimated = input_actual

    output = int(output_tokens or 0)
    reasoning = int(reasoning_tokens or 0)
    total_used = input_estimated + output + reasoning
    limit = max(int(max_context or 0), 1)

    def pct(n: int) -> float:
        return round(min(100.0, (n / limit) * 100), 1)

    return {
        "max_context": limit,
        "categories": {
            **categories,
            "output": output,
            "reasoning": reasoning,
        },
        "category_pct": {
            "system": pct(categories["system"]),
            "conversation": pct(categories["conversation"]),
            "tools": pct(categories["tools"]),
            "output": pct(output),
            "reasoning": pct(reasoning),
        },
        "input_estimated": input_estimated,
        "total_used": total_used,
        "used_pct": pct(total_used),
    }


def enrich_token_usage_with_breakdown(
    api_tokens: dict | None,
    prompt_messages: list,
    *,
    max_context: int,
) -> dict | None:
    """Attach context_breakdown to api_tokens_used payload for the UI."""
    if not api_tokens:
        return api_tokens
    enriched = dict(api_tokens)
    enriched["context_breakdown"] = estimate_context_breakdown(
        prompt_messages,
        max_context=max_context,
        output_tokens=int(enriched.get("completion_tokens") or 0),
        reasoning_tokens=int(enriched.get("reasoning_tokens") or 0),
        input_actual=int(enriched.get("prompt_tokens") or 0) or None,
    )
    return enriched
