"""Tool-first workspace write — skip bind_tools planning for clear save intents.

When the user already named ``write_workspace_file`` / a concrete workspace
``.txt``/``.md`` target, inject the tool call with a short note body instead of
paying a full local bind_tools prefill (topic-drift T4 was ~137s of planning).
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from src.agent.core.ask_user_guards import (
    build_workspace_note_content,
    extract_workspace_write_filename,
    is_clear_workspace_write_intent,
    turn_has_successful_workspace_write,
)
from src.agent.core.complex_utils.formatter import latest_user_text


def _turn_has_write_tool(messages: list) -> bool:
    for msg in messages or []:
        if (
            isinstance(msg, ToolMessage)
            and (getattr(msg, "name", None) or "") == "write_workspace_file"
        ):
            return True
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role == "tool" and (getattr(msg, "name", None) or "") == "write_workspace_file":
            return True
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                name = (
                    tc.get("name")
                    if isinstance(tc, dict)
                    else getattr(tc, "name", "")
                )
                if name == "write_workspace_file":
                    return True
    return False


def should_inject_tool_first_write(state: dict[str, Any], turn_messages: list) -> bool:
    """True when we should emit write_workspace_file without an LLM plan round."""
    user = latest_user_text(turn_messages) or ""
    if not is_clear_workspace_write_intent(user):
        return False
    if turn_has_successful_workspace_write(turn_messages):
        return False
    if _turn_has_write_tool(turn_messages):
        return False
    boxes = list(state.get("selected_toolboxes") or [])
    # Allow when file toolbox selected, or empty/all (router may still bind file_ops).
    if boxes and boxes != ["none"] and "file_ops" not in boxes and "all" not in boxes:
        return False
    return True


def build_tool_first_write_message(messages: list) -> AIMessage:
    """Build an AIMessage with a deterministic write_workspace_file tool call."""
    user = latest_user_text(messages) or ""
    filename = extract_workspace_write_filename(user)
    note = build_workspace_note_content(messages, user_text=user)
    call_id = f"toolfirst_write_{uuid.uuid4().hex[:10]}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_workspace_file",
                "args": {"filename": filename, "content": note},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )
