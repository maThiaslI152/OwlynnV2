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
Task: {task}
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
    parts: list[tuple[str, str]] = []

    # Clarified scope
    if clarified_scope and isinstance(clarified_scope, dict):
        scope_text = _format_scope(clarified_scope)
        if scope_text:
            parts.append(("clarified_scope", scope_text))

    # Plan review summary
    if plan_review_summary and isinstance(plan_review_summary, dict):
        approved = plan_review_summary.get("approved", False)
        intent = plan_review_summary.get("stated_intent", "")
        pitfalls = plan_review_summary.get("pitfalls", [])
        if approved:
            parts.append(
                (
                    "constraints",
                    f"Plan approved. Intent: {intent} Pitfalls acknowledged: {'; '.join(pitfalls) if pitfalls else 'none'}.",
                )
            )
        else:
            parts.append(("constraints", "Plan review skipped or denied."))

    # Memory context (filtered subset — no API keys)
    if memory_context:
        safe_context = _filter_memory_context(memory_context)
        if safe_context:
            parts.append(("constraints", f"Memory: {safe_context}"))

    # Recent messages
    if last_user_message:
        parts.append(("task", _truncate(last_user_message, 500)))
    if last_assistant_summary:
        parts.append(("task", _truncate(last_assistant_summary, 300)))

    # Toolboxes
    if selected_toolboxes:
        parts.append(("constraints", f"Toolboxes: {', '.join(selected_toolboxes)}"))

    if not parts:
        return ""

    # Assemble and cap
    brief = BRIEF_TEMPLATE.format(
        clarified_scope=dict(parts).get("clarified_scope", "Not provided"),
        constraints=dict(parts).get("constraints", "None"),
        risk_notes=dict(parts).get("risk_notes", "None reported"),
        task=dict(parts).get("task", _truncate(last_user_message, 500)),
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
    return _truncate(cleaned, 1000)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
