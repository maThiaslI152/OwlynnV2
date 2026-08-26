"""Tool-first workspace list/read — skip bind_tools planning for clear intents.

When the user already asked to list workspace files and read a named file,
inject both tool calls instead of paying a full local bind_tools prefill
(topic-drift T5 thrash).
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from src.agent.core.ask_user_guards import (
    extract_workspace_read_filename,
    is_clear_workspace_list_read_intent,
    turn_has_successful_workspace_read,
)
from src.agent.core.complex_utils.formatter import latest_user_text


def _turn_has_list_or_read_tool(messages: list) -> bool:
    for msg in messages or []:
        name = getattr(msg, "name", None) or ""
        if isinstance(msg, ToolMessage) and name in (
            "list_workspace_files",
            "read_workspace_file",
        ):
            return True
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role == "tool" and name in ("list_workspace_files", "read_workspace_file"):
            return True
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                tc_name = (
                    tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                )
                if tc_name in ("list_workspace_files", "read_workspace_file"):
                    return True
    return False


def should_inject_tool_first_list_read(
    state: dict[str, Any], turn_messages: list
) -> bool:
    """True when we should emit list+read without an LLM plan round."""
    user = latest_user_text(turn_messages) or ""
    if not is_clear_workspace_list_read_intent(user):
        return False
    if turn_has_successful_workspace_read(turn_messages):
        return False
    if _turn_has_list_or_read_tool(turn_messages):
        return False
    boxes = list(state.get("selected_toolboxes") or [])
    return not (
        boxes and boxes != ["none"] and "file_ops" not in boxes and "all" not in boxes
    )


def build_tool_first_list_read_message(messages: list) -> AIMessage:
    """Build an AIMessage with list_workspace_files + read_workspace_file calls."""
    user = latest_user_text(messages) or ""
    filename = extract_workspace_read_filename(user)
    list_id = f"toolfirst_list_{uuid.uuid4().hex[:10]}"
    read_id = f"toolfirst_read_{uuid.uuid4().hex[:10]}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "list_workspace_files",
                "args": {"directory": "."},
                "id": list_id,
                "type": "tool_call",
            },
            {
                "name": "read_workspace_file",
                "args": {"filename": filename},
                "id": read_id,
                "type": "tool_call",
            },
        ],
    )
