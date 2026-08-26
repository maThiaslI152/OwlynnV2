"""Guards that prevent ask_user loops on underspecified or already-clear requests."""

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


def is_code_review_missing_code(
    messages: list, *, user_text: str | None = None
) -> bool:
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


_CLEAR_WRITE_HINTS = (
    "write_workspace_file",
    "save a short note to my workspace",
    "save a note to my workspace",
    "save this to my workspace",
    "write a note to my workspace",
    "write a file to my workspace",
    "create a file in my workspace",
    "save to workspace as",
)


def is_clear_workspace_write_intent(text: str) -> bool:
    """True when the user already named the write tool / a concrete save target.

    Mid-thread models sometimes call ask_user instead of write_workspace_file;
    binding ask_user then is harmful (especially if GraphInterrupt is mishandled).
    """
    user_lower = (text or "").lower()
    if not user_lower:
        return False
    if "write_workspace_file" in user_lower:
        return True
    if any(hint in user_lower for hint in _CLEAR_WRITE_HINTS):
        return True
    # "save … as foo.txt" / "write … bangkok_notes.txt"
    return (
        ("save" in user_lower or "write" in user_lower)
        and "workspace" in user_lower
        and (".txt" in user_lower or ".md" in user_lower)
    )


_WRITE_FILENAME_RE = re.compile(
    r"(?:as|file(?:name)?)\s+[`'\"]?([\w./-]+\.(?:txt|md|json|csv))[`'\"]?",
    re.IGNORECASE,
)
_WRITE_FILENAME_BARE_RE = re.compile(
    r"\b([\w./-]+\.(?:txt|md|json|csv))\b",
    re.IGNORECASE,
)


def extract_workspace_write_filename(text: str) -> str:
    """Best-effort filename from a clear write ask; fallback note.txt."""
    m = _WRITE_FILENAME_RE.search(text or "")
    if m:
        return m.group(1).lstrip("./")
    m = _WRITE_FILENAME_BARE_RE.search(text or "")
    if m:
        return m.group(1).lstrip("./")
    return "note.txt"


def build_workspace_note_content(messages: list, *, user_text: str = "") -> str:
    """Short note from recent assistant replies (for forced write_workspace_file)."""
    bits: list[str] = []
    for msg in reversed(messages or []):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
        )
        if role not in ("ai", "assistant"):
            continue
        text = message_text(msg).strip()
        if not text or len(text) < 8:
            continue
        bits.append(text[:240])
        if len(bits) >= 3:
            break
    bits.reverse()
    body = "\n".join(f"- {b}" for b in bits) if bits else "- (conversation notes)"
    header = "Workspace note\n"
    if user_text and "summar" in user_text.lower():
        header = "Summary note\n"
    return f"{header}{body}\n"[:1500]


def turn_has_successful_workspace_write(messages: list) -> bool:
    """True when this turn already has a successful write_workspace_file ToolMessage."""
    for msg in reversed(messages or []):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
        )
        if role in ("human", "user"):
            break
        name = getattr(msg, "name", None) or ""
        if name != "write_workspace_file":
            continue
        content = message_text(msg)
        if "✅" in content or "Written to" in content:
            return True
    return False


_CLEAR_LIST_READ_HINTS = (
    "list_workspace_files",
    "read_workspace_file",
    "list workspace files and read",
    "list workspace files and then read",
    "list my workspace and read",
    "list the workspace and read",
)


def is_clear_workspace_list_read_intent(text: str) -> bool:
    """True when the user clearly asked to list and/or read a workspace file.

    Mid-thread models otherwise thrash on repeated list/read (topic-drift T5).
    """
    user_lower = (text or "").lower()
    if not user_lower:
        return False
    if any(hint in user_lower for hint in _CLEAR_LIST_READ_HINTS):
        return True
    has_file = bool(_WRITE_FILENAME_BARE_RE.search(user_lower))
    wants_list = "list" in user_lower and "workspace" in user_lower
    wants_read = "read" in user_lower and (
        "workspace" in user_lower or has_file or "back to me" in user_lower
    )
    if wants_list and wants_read:
        return True
    return bool(wants_read and has_file)


def extract_workspace_read_filename(text: str) -> str:
    """Best-effort filename from a clear list/read ask; fallback note.txt."""
    return extract_workspace_write_filename(text)


def _is_successful_read_tool_content(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    # Tool errors are prefixed; successful reads return file body (or truncation note).
    if text.startswith(("Error:", "Error ")):
        return False
    return "Error: File" not in text[:80]


def turn_has_successful_workspace_read(messages: list) -> bool:
    """True when this turn already has a successful read_workspace_file ToolMessage."""
    for msg in reversed(messages or []):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
        )
        if role in ("human", "user"):
            break
        name = getattr(msg, "name", None) or ""
        if name != "read_workspace_file":
            continue
        if _is_successful_read_tool_content(message_text(msg)):
            return True
    return False


def turn_has_successful_workspace_list(messages: list) -> bool:
    """True when this turn already has a successful list_workspace_files ToolMessage."""
    for msg in reversed(messages or []):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
        )
        if role in ("human", "user"):
            break
        name = getattr(msg, "name", None) or ""
        if name != "list_workspace_files":
            continue
        content = message_text(msg)
        if content and not content.startswith("Error"):
            return True
    return False


def successful_workspace_read_body(messages: list) -> str | None:
    """Return the latest successful read_workspace_file body for this turn."""
    for msg in reversed(messages or []):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else None)
        )
        if role in ("human", "user"):
            break
        name = getattr(msg, "name", None) or ""
        if name != "read_workspace_file":
            continue
        content = message_text(msg)
        if not _is_successful_read_tool_content(content):
            continue
        # Drop in-tool guidance suffixes before surfacing to the user.
        cut = content.find("\n\n[Tool Guidance]:")
        if cut >= 0:
            content = content[:cut]
        return content.strip()
    return None


def should_strip_ask_user(messages: list, *, user_text: str | None = None) -> bool:
    """True when ask_user must not be bound for this turn."""
    if is_code_review_missing_code(messages, user_text=user_text):
        return True
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
    text = text or ""
    return is_clear_workspace_write_intent(text) or is_clear_workspace_list_read_intent(
        text
    )


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
