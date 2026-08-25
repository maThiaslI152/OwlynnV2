"""Guards that prevent ask_user loops on underspecified code-review requests."""

from __future__ import annotations

import re
from typing import Any

_CODE_REVIEW_HINTS = (
    "review my code",
    "code review",
    "check my code",
    "look at this code",
    "review this pr",
    "review this pull request",
    "review this commit",
    "review this diff",
    "review the python code",
    "review the code",
    "review this code",
    "review this function",
    "review the function",
)

_CODE_FENCE_RE = re.compile(r"```[\w+-]*\n")
_ATTACHED_FILE_RE = re.compile(r"\[Attached File:", re.IGNORECASE)
_MISSING_CODE_REPLY = (
    "Please paste the code (or attach a file) you'd like reviewed, "
    "and I'll go through it."
)


def is_code_review_request(text: str) -> bool:
    """True when the user asked for a code review / PR review."""
    user_lower = (text or "").lower()
    if any(hint in user_lower for hint in _CODE_REVIEW_HINTS):
        return True
    return (
        "review" in user_lower
        and "code" in user_lower
        and any(w in user_lower for w in ("bug", "bugs", "function", "python"))
    )


def message_text(msg: Any) -> str:
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content or "")


def turn_has_reviewable_code(messages: list) -> bool:
    """True if the current turn (or recent humans) include fences / attachments."""
    for msg in reversed(messages or []):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
        )
        if role not in ("human", "user"):
            # Also accept tool/file injection markers on any recent message.
            text = message_text(msg)
            if _ATTACHED_FILE_RE.search(text) or _CODE_FENCE_RE.search(text):
                return True
            continue
        text = message_text(msg)
        if _ATTACHED_FILE_RE.search(text) or _CODE_FENCE_RE.search(text):
            return True
        # Long indented / def-heavy blocks without fences still count.
        if "def " in text and ("\n    " in text or "\n\t" in text) and len(text) > 80:
            return True
        # Only inspect the latest human for "missing code" — stop after first human.
        break
    return False


def is_code_review_missing_code(messages: list, *, user_text: str | None = None) -> bool:
    """Code-review ask with no pasted/attached code — must not call ask_user."""
    text = user_text
    if text is None:
        for msg in reversed(messages or []):
            role = (
                getattr(msg, "type", None)
                or getattr(msg, "role", None)
                or (msg.get("role") if isinstance(msg, dict) else None)
            )
            if role in ("human", "user"):
                text = message_text(msg)
                break
    if not is_code_review_request(text or ""):
        return False
    return not turn_has_reviewable_code(messages or [])


def missing_code_review_reply() -> str:
    return _MISSING_CODE_REPLY


def strip_ask_user_tools(tools: list | None) -> list | None:
    """Remove ask_user from a bind list (hard gate)."""
    if not tools:
        return tools
    return [t for t in tools if getattr(t, "name", "") != "ask_user"]


def ai_message_asks_user(response: Any) -> bool:
    tool_calls = getattr(response, "tool_calls", None) or []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        if name == "ask_user":
            return True
    return False
