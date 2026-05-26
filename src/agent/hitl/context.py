"""
HITL context builder — shared helper used by router, plan_review, security_proxy,
and scope_clarify to build enriched interrupt payloads.
"""

from typing import Any
from langchain_core.messages import HumanMessage, AIMessage


def build_hitl_context(state: dict) -> dict[str, Any]:
    """Extract conversation context fields for HITL interrupt enrichment.

    Returns a dict with keys usable across all interrupt types:
    - conversation_snippet: Last user + last assistant message (truncated)
    - stated_intent: Heuristic one-liner derived from last AIMessage + tool names
    - affected_resources: Parsed paths from tool args
    """
    messages = list(state.get("messages") or [])

    # Last user and assistant messages for snippet
    last_user = ""
    last_assistant = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and not last_user:
            last_user = _truncate(str(msg.content), 200)
        elif isinstance(msg, AIMessage) and not last_assistant:
            last_assistant = _truncate(str(msg.content), 200)
        if last_user and last_assistant:
            break

    snippet = f"User: {last_user}\nOwlynn: {last_assistant}" if last_user or last_assistant else ""

    # Stated intent from last AIMessage
    intent = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = str(msg.content or "")
            intent = _truncate(content, 150)
            break

    # Affected resources from pending tool calls
    affected = _extract_affected_resources(messages)

    return {
        "conversation_snippet": snippet,
        "stated_intent": f"Owlynn wants to {intent}" if intent else "",
        "affected_resources": affected,
    }


def enrich_interrupt(interrupt_payload: dict, state: dict) -> dict:
    """Attach conversation context fields to an interrupt payload dict."""
    ctx = build_hitl_context(state)
    enriched = dict(interrupt_payload)
    if ctx["conversation_snippet"]:
        enriched.setdefault("conversation_snippet", ctx["conversation_snippet"])
    if ctx["stated_intent"]:
        enriched.setdefault("stated_intent", ctx["stated_intent"])
    if ctx["affected_resources"]:
        enriched.setdefault("affected_resources", ctx["affected_resources"])
    return enriched


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_affected_resources(messages: list) -> list[str]:
    """Extract file paths from pending tool call args."""
    import json
    paths = []
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        for call in tool_calls:
            args = call.get("args", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(args, dict):
                for key in ("path", "file_path", "source_path", "target_path"):
                    if key in args:
                        paths.append(str(args[key]))
        if paths:
            break
    return paths[:10]
