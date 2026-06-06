"""
Security proxy node for tool execution governance.

This node sits between LLM tool-call planning and actual tool execution.
It enforces policy checks and triggers HITL interruption for sensitive actions.
"""

import json
import re
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from src.agent.state import AgentState
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.config.log_middleware import log_hitl_event, log_node

from src.agent.hitl.policy import is_information_retrieval
from src.agent.hitl.context import enrich_interrupt

SENSITIVE_TOOLS = {
    "write_workspace_file",
    "edit_workspace_file",
    "delete_workspace_file",
    "notebook_run",
}

SENSITIVE_PATTERN_RE = re.compile(
    r"(?:\brm\s+-rf\b|(?:^|[;&|])\s*curl\b|(?:^|[;&|])\s*wget\b|\bsudo\b|\bchmod\b|\bchown\b|\bssh\b|\bscp\b)",
    re.IGNORECASE,
)

_DESTRUCTIVE_RE = re.compile(
    r"(?:\brm\s+-rf\b|\bdrop\b|\bdelete\b|\btruncate\b)", re.IGNORECASE
)
_NETWORK_RE = re.compile(
    r"(?:\bcurl\b|\bwget\b|\bhttp[s]?://\b|\bscp\b|\bssh\b)", re.IGNORECASE
)
_PRIVILEGE_RE = re.compile(r"(?:\bsudo\b|\bchmod\b|\bchown\b)", re.IGNORECASE)

_CATEGORY_REMEDIATION = {
    "destructive_action": "Confirm target paths and create a backup/snapshot before execution.",
    "network_exfiltration": "Verify destination/URL allowlist and redact sensitive data before sending.",
    "privilege_escalation": "Run with least privilege and scope command to required files only.",
    "sensitive_tool_execution": "Review tool args carefully and run only if intent is explicit.",
}


def _normalize_approval(decision: Any) -> bool:
    """Normalize resume payload from HITL interrupt into an approval boolean."""
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


def _tool_calls_from_last_message(state: AgentState) -> list[dict[str, Any]]:
    messages = list(state.get("messages") or [])
    if not messages:
        return []
    last = messages[-1]
    return list(getattr(last, "tool_calls", None) or [])


def _is_sensitive_call(tool_name: str, args: Any) -> bool:
    if is_information_retrieval(tool_name):
        return False
    if tool_name in SENSITIVE_TOOLS:
        return True
    args_text = (
        json.dumps(args, ensure_ascii=True) if not isinstance(args, str) else args
    )
    return bool(SENSITIVE_PATTERN_RE.search(args_text))


def _risk_meta_for_call(tool_name: str, args: Any) -> dict[str, Any]:
    args_text = (
        json.dumps(args, ensure_ascii=True) if not isinstance(args, str) else str(args)
    )
    hay = f"{tool_name} {args_text}"

    if _DESTRUCTIVE_RE.search(hay) or tool_name == "delete_workspace_file":
        category = "destructive_action"
        confidence = 0.98
        rationale = "Policy detected delete/drop semantics that can irreversibly modify workspace state."
    elif _NETWORK_RE.search(hay):
        category = "network_exfiltration"
        confidence = 0.9
        rationale = "Policy detected outbound network/remote transfer indicators in tool arguments."
    elif _PRIVILEGE_RE.search(hay):
        category = "privilege_escalation"
        confidence = 0.92
        rationale = (
            "Policy detected elevated-permission command markers in tool arguments."
        )
    else:
        category = "sensitive_tool_execution"
        confidence = 0.8
        rationale = "Tool is in sensitive allowlist and requires explicit approval before execution."

    return {
        "risk_category": category,
        "risk_label": category,
        "risk_confidence": confidence,
        "risk_rationale": rationale,
        "remediation_hint": _CATEGORY_REMEDIATION[category],
    }


_TOOL_ACTION_LABELS = {
    "write_workspace_file": "write to file",
    "edit_workspace_file": "edit file",
    "delete_workspace_file": "delete file",
    "notebook_run": "run code in Python REPL",
}


def _build_title(sensitive_calls: list[dict]) -> str:
    """Generate a context-aware title from the sensitive tool calls."""
    if not sensitive_calls:
        return "Tool approval required"
    call = sensitive_calls[0]
    name = str(call.get("name", "unknown"))
    args = call.get("args", {})
    primary_arg = ""
    if isinstance(args, dict):
        for key in ("path", "file_path", "filename", "name", "file_name", "target"):
            val = args.get(key)
            if val:
                primary_arg = str(val)
                break
    label = _TOOL_ACTION_LABELS.get(name, name)
    if primary_arg:
        return f"Approve {label}: {primary_arg}?"
    return f"Approve {label}?"


def _build_reason(sensitive_calls: list[dict]) -> str:
    """Generate a plain-language explanation of why the tool is being called."""
    if not sensitive_calls:
        return "One or more tool calls require approval."
    call = sensitive_calls[0]
    name = str(call.get("name", "unknown"))
    args = call.get("args", {})
    label = _TOOL_ACTION_LABELS.get(name, name)
    if isinstance(args, dict):
        detail_parts = []
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 100:
                v = v[:80] + "..."
            detail_parts.append(f"{k}={v}")
        if detail_parts:
            return f"Owlynn wants to {label} with: {', '.join(detail_parts[:3])}"
    return f"Owlynn wants to {label}."


@log_node("security_proxy")
async def security_proxy_node(state: AgentState) -> AgentState:
    """
    Validate proposed tool calls and gate execution.
    - Safe calls pass through.
    - Sensitive calls trigger HITL interrupt.
    - If plan_review was already approved and sensitive calls are unchanged,
      skip the second interrupt (dedup).
    """
    tool_calls = _tool_calls_from_last_message(state)
    if not tool_calls:
        return {
            "execution_approved": False,
            "security_decision": "denied",
            "security_reason": "No tool call found for security validation.",
            "pending_tool_calls": False,
        }

    # ── Fast-path: all calls are information retrieval (no HITL needed) ──
    if tool_calls and all(
        is_information_retrieval(str(c.get("name", ""))) for c in tool_calls
    ):
        tool_names = [str(c.get("name", "unknown")) for c in tool_calls]
        logger.info(
            "[security_proxy] All safe tools (%s) — auto-approving, no HITL", tool_names
        )
        for name in tool_names:
            log_hitl_event("tool_classified", tool=name, decision="safe_auto")
        return {
            "execution_approved": True,
            "security_decision": "approved",
            "security_reason": "All tools are information-retrieval (safe).",
            "pending_tool_names": tool_names,
        }

    sensitive_calls: list[dict[str, Any]] = []
    safe_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        name = str(call.get("name", "unknown"))
        args = call.get("args", {})
        if _is_sensitive_call(name, args):
            enriched = dict(call)
            enriched.update(_risk_meta_for_call(name, args))
            sensitive_calls.append(enriched)
            log_hitl_event(
                "tool_classified",
                tool=name,
                decision="sensitive",
                risk=enriched.get("risk_label", "unknown"),
            )
        else:
            safe_calls.append(call)
            log_hitl_event("tool_classified", tool=name, decision="safe")

    if not sensitive_calls:
        return {
            "execution_approved": True,
            "security_decision": "approved",
            "security_reason": None,
            "pending_tool_names": [str(c.get("name", "unknown")) for c in safe_calls],
        }

    # ── API Mode Bypass / Auto-Approval ────────────────────────────────────
    profile = get_profile()
    execution_policy = profile.get("execution_policy", "auto_approve")

    if state.get("mode") == "api":
        approved = bool(state.get("auto_approve_sensitive", False))
        logger.info("[security_proxy] API mode detected — auto_approve=%s", approved)
        log_hitl_event("hitl_skipped", decision="api_mode_auto", approved=approved)
    else:
        # Check if we should auto-approve based on Execution Policy and risk
        # "Red lines": destructive, network, or privilege escalation always require HITL
        highest_risk = max([c.get("risk_confidence", 0) for c in sensitive_calls])
        has_redline = any(
            c.get("risk_category")
            in ("destructive_action", "network_exfiltration", "privilege_escalation")
            for c in sensitive_calls
        )

        if execution_policy == "auto_approve" and not has_redline:
            logger.info(
                "[security_proxy] execution_policy is auto_approve and no redline risks detected — auto-approving"
            )
            log_hitl_event("hitl_skipped", decision="execution_policy_auto")
            approved = True
        # ── Dedup: skip second interrupt when plan_review already approved ────
        elif state.get("plan_review_approved"):
            logger.info(
                "[security_proxy] Plan review already approved — skipping duplicate interrupt"
            )
            log_hitl_event(
                "hitl_skipped",
                decision="plan_review_dedup",
                sensitive_count=len(sensitive_calls),
            )
            return {
                "execution_approved": True,
                "security_decision": "approved",
                "security_reason": "Plan review approved; security proxy skipped duplicate interrupt.",
                "pending_tool_names": [
                    str(c.get("name", "unknown")) for c in tool_calls
                ],
            }
        else:
            enriched_payload = enrich_interrupt(
                {
                    "type": "security_approval_required",
                    "title": _build_title(sensitive_calls),
                    "reason": _build_reason(sensitive_calls),
                    "sensitive_tool_calls": sensitive_calls,
                    "safe_tool_calls": safe_calls,
                    "risk_categories": sorted(
                        {
                            str(c.get("risk_category", "sensitive_tool_execution"))
                            for c in sensitive_calls
                        }
                    ),
                    "instruction": "Approve or deny this action.",
                    "tool_args": sensitive_calls[0].get("args", {})
                    if sensitive_calls
                    else {},
                },
                state,
            )
        decision = interrupt(enriched_payload)
        approved = _normalize_approval(decision)

    if approved:
        approved_tools = [str(c.get("name", "unknown")) for c in tool_calls]
        log_hitl_event(
            "hitl_approved",
            decision="approved",
            tools=approved_tools,
            sensitive_count=len(sensitive_calls),
        )
        return {
            "execution_approved": True,
            "security_decision": "approved",
            "security_reason": "Approved by human reviewer.",
            "pending_tool_names": approved_tools,
        }

    denied_tool_names = [str(c.get("name", "unknown")) for c in sensitive_calls]
    prior_denied = state.get("denied_tools") or []
    all_denied = prior_denied + denied_tool_names

    log_hitl_event(
        "hitl_denied",
        decision="denied",
        tools=denied_tool_names,
        total_denied=len(all_denied),
    )

    denied_message = AIMessage(
        content=(
            f"[POLICY BLOCK] Human reviewer denied {', '.join(denied_tool_names)}. "
            "This tool requires explicit approval and cannot be retried. "
            "I can suggest a safer alternative or a different approach."
        )
    )
    return {
        "messages": [denied_message],
        "execution_approved": False,
        "security_decision": "denied",
        "security_reason": "Sensitive tool request denied by human reviewer.",
        "pending_tool_calls": False,
        "denied_tools": all_denied,
    }
