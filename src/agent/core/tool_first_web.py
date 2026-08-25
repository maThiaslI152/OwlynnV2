"""Tool-first web path — run web_search without bind_tools planning prefill.

When the router selects toolbox ``["web_search"]``, inject a deterministic
``web_search`` tool call, then synthesize once without tool schemas. Escalate
to normal complex bind_tools only when search fails or results are empty.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.complex_utils.formatter import latest_user_text
from src.agent.core.complex_utils.helpers import _web_search_tool_output_has_results

TOOL_FIRST_PHASE_SEARCH = "search"
TOOL_FIRST_PHASE_DONE = "done"

_PRONOUN_FOLLOWUP_RE = re.compile(
    r"\b(it|its|it's|they|their|them|this|that)\b", re.IGNORECASE
)


def is_web_search_only_toolbox(state: dict[str, Any]) -> bool:
    toolboxes = state.get("selected_toolboxes") or []
    return list(toolboxes) == ["web_search"]


def should_inject_tool_first_search(state: dict[str, Any], turn_messages: list) -> bool:
    """True when we should emit a synthetic web_search tool call (no LLM)."""
    if not is_web_search_only_toolbox(state):
        return False
    phase = state.get("_tool_first_web_phase")
    if phase in (TOOL_FIRST_PHASE_SEARCH, TOOL_FIRST_PHASE_DONE):
        return False
    if _turn_has_web_search_tool(turn_messages):
        return False
    return True


def should_synthesize_tool_first(state: dict[str, Any], turn_messages: list) -> bool:
    """True when search already ran and we should synthesize without tools."""
    if state.get("_tool_first_web_phase") != TOOL_FIRST_PHASE_SEARCH:
        return False
    if not is_web_search_only_toolbox(state):
        return False
    return _turn_has_successful_web_search(turn_messages)


def should_escalate_tool_first(state: dict[str, Any], turn_messages: list) -> bool:
    """True when tool-first search ran but failed — fall back to bind_tools."""
    if state.get("_tool_first_web_phase") != TOOL_FIRST_PHASE_SEARCH:
        return False
    if not _turn_has_web_search_tool(turn_messages):
        return False
    return not _turn_has_successful_web_search(turn_messages)


def _prior_human_text(messages: list) -> str:
    """Return the previous human turn (not the latest), for pronoun follow-ups."""
    humans: list[str] = []
    for msg in messages:
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            content = getattr(msg, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    str(b.get("text", b) if isinstance(b, dict) else b) for b in content
                )
            text = str(content).strip()
            if text:
                humans.append(text)
    if len(humans) >= 2:
        return humans[-2]
    return ""


def resolve_tool_first_search_query(messages: list) -> str:
    """Build a search query; expand short pronoun follow-ups with prior human context."""
    query = (latest_user_text(messages) or "").strip()
    if len(query) > 400:
        query = query[:400]
    if not query:
        return query
    if _PRONOUN_FOLLOWUP_RE.search(query):
        prior = _prior_human_text(messages)
        if prior and prior.lower() not in query.lower():
            combined = f"{prior} — {query}"
            return combined[:400]
    return query


def build_tool_first_web_search_message(messages: list) -> AIMessage:
    """Build an AIMessage with a deterministic web_search tool call."""
    query = resolve_tool_first_search_query(messages)
    call_id = f"toolfirst_{uuid.uuid4().hex[:12]}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {"query": query, "focus_query": query},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def _turn_has_web_search_tool(messages: list) -> bool:
    for msg in messages:
        if (
            isinstance(msg, ToolMessage)
            and (getattr(msg, "name", None) or "") == "web_search"
        ):
            return True
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role == "tool" and (getattr(msg, "name", None) or "") == "web_search":
            return True
    return False


def _turn_has_successful_web_search(messages: list) -> bool:
    for msg in messages:
        name = getattr(msg, "name", None) or ""
        if name != "web_search":
            continue
        content = getattr(msg, "content", "") or ""
        if _web_search_tool_output_has_results(str(content)):
            return True
    return False
