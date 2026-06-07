"""
Cloud brief builder — builds compact, anonymized prompt for DeepSeek when
``route == "complex-cloud"``.

Inputs come from local state (post-HITL) — never sends raw chat history,
workspace files, or tool output blobs to cloud.
"""

BRIEF_TEMPLATE = """--- OWLYNN CLOUD BRIEF (local-prepared, user-approved) ---
Requirements: {clarified_scope}
Constraints: {constraints}
Risk notes: {risk_notes}
Current user request: {task}
Prior assistant context: {prior_context}
--- END BRIEF ---"""


def build_cloud_brief(
    *,
    clarified_scope: dict | None = None,
    plan_review_summary: dict | None = None,
    memory_context: str | None = None,
    last_user_message: str = "",
    last_assistant_summary: str = "",
    selected_toolboxes: list[str] | None = None,
    max_chars: int = 8000,
) -> str:
    """Assemble a compact cloud brief string for DeepSeek consumption.

    Returns empty string if there is nothing to brief.
    """
    scope_text = "Not provided"
    constraint_lines: list[str] = []
    task = _truncate(last_user_message, 500) if last_user_message else "Not provided"
    prior_context = (
        _truncate(last_assistant_summary, 300) if last_assistant_summary else "None"
    )

    if clarified_scope and isinstance(clarified_scope, dict):
        formatted = _format_scope(clarified_scope)
        if formatted:
            scope_text = formatted

    if plan_review_summary and isinstance(plan_review_summary, dict):
        approved = plan_review_summary.get("approved", False)
        intent = plan_review_summary.get("stated_intent", "")
        pitfalls = plan_review_summary.get("pitfalls", [])
        if approved:
            constraint_lines.append(
                f"Plan approved. Intent: {intent} Pitfalls acknowledged: {'; '.join(pitfalls) if pitfalls else 'none'}."
            )
        else:
            constraint_lines.append("Plan review skipped or denied.")

    if memory_context:
        safe_context = _filter_memory_context(memory_context)
        if safe_context:
            constraint_lines.append(f"Memory: {safe_context}")

    if selected_toolboxes:
        constraint_lines.append(f"Toolboxes: {', '.join(selected_toolboxes)}")

    if (
        task == "Not provided"
        and not constraint_lines
        and scope_text == "Not provided"
        and prior_context == "None"
    ):
        return ""

    brief = BRIEF_TEMPLATE.format(
        clarified_scope=scope_text,
        constraints="\n".join(constraint_lines) if constraint_lines else "None",
        risk_notes="None reported",
        task=task,
        prior_context=prior_context,
    )

    if len(brief) > max_chars:
        brief = brief[: max_chars - 3] + "..."

    return brief


def estimate_brief_tokens(brief: str) -> int:
    """Rough token count estimate for the brief."""
    return max(1, len(brief) // 4)


def _format_scope(scope: dict) -> str:
    lines = []
    if scope.get("skipped"):
        return "User skipped clarification."
    for key, value in scope.items():
        if key in ("skipped", "_raw"):
            continue
        if isinstance(value, dict):
            label = value.get("label", str(value))
            user_input = value.get("user_input", "")
            if user_input:
                lines.append(f"- {key}: {label} ({user_input})")
            else:
                lines.append(f"- {key}: {label}")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else ""


def _filter_memory_context(memory: str) -> str:
    """Strip known sensitive patterns from memory before cloud send."""
    import re

    cleaned = re.sub(
        r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+",
        "[REDACTED]",
        memory,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "[REDACTED_EMAIL]",
        cleaned,
    )
    cleaned = re.sub(
        r"(?:/Users/|/home/|C:\\Users\\)[^\s\"']+",
        "[REDACTED_PATH]",
        cleaned,
    )
    cleaned = re.sub(
        r"sk-[a-zA-Z0-9]{8,}",
        "[REDACTED_KEY]",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _truncate(cleaned, 1000)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
