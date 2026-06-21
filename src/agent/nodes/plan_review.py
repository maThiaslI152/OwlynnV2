"""
Plan review node — sits after ``complex_llm`` and before ``security_proxy``.

Reviews pending tool calls, identifies sensitive operations, builds a
human-readable plan summary with pitfalls, and interrupts for approval.
"""

import json
import logging
import re
from typing import Any

from langgraph.types import interrupt
from langchain_core.messages import AIMessage

from src.agent.core.state import AgentState
from src.agent.hitl.policy import is_sensitive_call
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.config.log_middleware import log_hitl_event, log_node

_PLAN_REVIEW_PROMPT = """Analyze these planned tool calls and identify risks:

{plan_summary}

Output exactly one JSON object on a single line. No markdown, no explanation, no leading text. Start with {{ and end with }}:
{{"stated_intent":"one-line summary of what Owlynn wants to do","pitfalls":["risk 1","risk 2"],"safe_to_proceed":true}}"""


def _tool_calls_from_last_message(state: AgentState) -> list[dict[str, Any]]:
    messages = list(state.get("messages") or [])
    if not messages:
        return []
    last = messages[-1]
    return list(getattr(last, "tool_calls", None) or [])


def _has_sensitive_pending(state: AgentState) -> bool:
    """Check if any pending tool calls match sensitive policy."""
    tool_calls = _tool_calls_from_last_message(state)
    for call in tool_calls:
        name = str(call.get("name", "unknown"))
        args = call.get("args", {})
        if is_sensitive_call(name, args):
            return True
    return False


@log_node("plan_review")
async def plan_review_node(state: AgentState) -> AgentState:
    """Review planned tool calls and gate sensitive operations.

    Runs after ``complex_llm`` when there are pending tool calls and any match
    sensitive policy. Uses Small LLM for intent/pitfalls text (no cloud).
    """
    profile = get_profile()
    if not profile.get("plan_review_enabled", True):
        logger.debug("[plan_review] Skipped — disabled in profile")
        return {"plan_review_approved": None}

    execution_policy = profile.get("execution_policy", "auto_approve")
    if execution_policy == "auto_approve":
        logger.debug("[plan_review] Skipped — execution_policy is auto_approve")
        return {"plan_review_approved": None}

    tool_calls = _tool_calls_from_last_message(state)
    if not tool_calls:
        return {"plan_review_approved": None}

    # Classify calls
    sensitive_calls: list[dict[str, Any]] = []
    safe_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        name = str(call.get("name", "unknown"))
        args = call.get("args", {})
        if is_sensitive_call(name, args):
            sensitive_calls.append(dict(call))
        else:
            safe_calls.append(dict(call))

    if not sensitive_calls:
        logger.debug("[plan_review] No sensitive calls — skipping plan review")
        return {"plan_review_approved": None}

    # ── Build plan summary ──────────────────────────────────────
    plan_summary_lines = []
    for c in sensitive_calls:
        plan_summary_lines.append(
            f"Tool: {c.get('name', 'unknown')}, Args: {c.get('args', {})}"
        )
    for c in safe_calls:
        plan_summary_lines.append(
            f"Tool (safe): {c.get('name', 'unknown')}, Args: {c.get('args', {})}"
        )
    plan_summary = "\n".join(plan_summary_lines)

    # ── Generate intent + pitfalls with Small LLM ─────────────────
    stated_intent = ""
    pitfalls: list[str] = []

    try:
        from src.agent.llm import get_small_llm

        small_llm = await get_small_llm()
        review_prompt = _PLAN_REVIEW_PROMPT.format(plan_summary=plan_summary)
        response = await small_llm.ainvoke(review_prompt)
        result = _parse_json(
            response.content if hasattr(response, "content") else str(response)
        )
        stated_intent = result.get("stated_intent", "")
        pitfalls = result.get("pitfalls", [])
    except Exception as e:
        logger.warning("[plan_review] Small LLM failed: %s", e)
        pitfalls = [
            "Unable to automatically analyze plan risks — please review manually."
        ]

    # ── Build interrupt payload ──────────────────────────────────
    from src.agent.hitl.context import build_hitl_context

    ctx = build_hitl_context(state)

    interrupt_payload: dict[str, Any] = {
        "type": "plan_review_required",
        "title": f"Plan review — {len(sensitive_calls)} sensitive action(s) planned",
        "stated_intent": stated_intent
        or "Owlynn plans to execute sensitive workspace operations.",
        "conversation_snippet": ctx.get("conversation_snippet", ""),
        "planned_actions": [
            {"tool": c.get("name", "unknown"), "summary": str(c.get("args", {}))[:200]}
            for c in tool_calls
        ],
        "pitfalls": pitfalls,
        "sensitive_tool_calls": sensitive_calls,
    }

    decision = interrupt(interrupt_payload)

    approved = _normalize_approval(decision)

    if approved:
        logger.info("[plan_review] Plan approved by human reviewer")
        approved_tools = [str(c.get("name", "unknown")) for c in tool_calls]
        log_hitl_event(
            "plan_reviewed",
            decision="approved",
            tools=approved_tools,
            pitfalls=pitfalls[:3],
        )
        return {
            "plan_review_approved": True,
            "plan_review_feedback": decision.get("feedback", "")
            if isinstance(decision, dict)
            else "",
            "execution_approved": True,
            "pending_tool_calls": True,
            "pending_tool_names": [str(c.get("name", "unknown")) for c in tool_calls],
            "security_decision": "approved",
        }

    # Denied — block and write denied message
    denied_tool_names = [str(c.get("name", "unknown")) for c in sensitive_calls]
    prior_denied = state.get("denied_tools") or []
    log_hitl_event(
        "plan_reviewed",
        decision="denied",
        tools=denied_tool_names,
        feedback=decision.get("feedback", "") if isinstance(decision, dict) else "",
    )
    denied_message = AIMessage(
        content=(
            f"[PLAN REVIEW BLOCK] Human reviewer denied {', '.join(denied_tool_names)}. "
            "The planned action was rejected. I can suggest a safer alternative or a different approach."
        )
    )
    logger.info("[plan_review] Plan denied: %s", denied_tool_names)
    return {
        "messages": [denied_message],
        "execution_approved": False,
        "security_decision": "denied",
        "security_reason": "Plan review denied by human reviewer.",
        "pending_tool_calls": False,
        "denied_tools": prior_denied + denied_tool_names,
        "plan_review_approved": False,
        "plan_review_feedback": decision.get("feedback", "")
        if isinstance(decision, dict)
        else "",
    }


def _normalize_approval(decision: Any) -> bool:
    if isinstance(decision, bool):
        return decision
    if isinstance(decision, str):
        return decision.strip().lower() in {
            "approve",
            "approved",
            "allow",
            "yes",
            "y",
            "true",
        }
    if isinstance(decision, dict):
        approved = decision.get("approved")
        if isinstance(approved, bool):
            return approved
        if isinstance(approved, str):
            return approved.strip().lower() in {
                "approve",
                "approved",
                "allow",
                "yes",
                "y",
                "true",
            }
    return False


def _parse_json(content) -> dict:
    """Parse JSON from LLM response, handling markdown fences, prose wrappers,
    thinking tags, and other noise common in small-model output."""
    content = str(content or "").strip()

    # ── Strip markdown code fences ──────────────────────────────────
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    # ── Attempt direct parse ───────────────────────────────────────
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # ── Try extracting JSON object between outermost curly braces ──
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # ── Strip common LLM noise prefixes then retry ─────────────────
    cleaned = re.sub(
        r"^(here\s+is\s+(the\s+)?(json|analysis|result|response)[:\s-]*|ok[.,:;\s]*|sure[.,:;\s]*)",
        "",
        content,
        flags=re.IGNORECASE,
    ).strip()
    if cleaned and cleaned != content:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match2 = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match2:
                try:
                    return json.loads(match2.group(0))
                except json.JSONDecodeError:
                    pass

    raise ValueError(f"Could not parse JSON from content: {content[:200]}")
