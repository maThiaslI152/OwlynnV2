"""Tests for tool-first workspace write injection."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.tool_first_write import (
    build_tool_first_write_message,
    should_inject_tool_first_write,
)


def test_should_inject_clear_write_file_ops():
    msgs = [
        HumanMessage(
            content=(
                "Save a short note to my workspace as bangkok_notes.txt. "
                "Use write_workspace_file."
            )
        )
    ]
    assert should_inject_tool_first_write(
        {"selected_toolboxes": ["file_ops"]}, msgs
    )


def test_should_not_inject_after_successful_write():
    msgs = [
        HumanMessage(content="Save note as x.txt via write_workspace_file"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_workspace_file",
                    "id": "1",
                    "args": {"filename": "x.txt", "content": "hi"},
                }
            ],
        ),
        ToolMessage(
            content="✅ Written to x.txt", tool_call_id="1", name="write_workspace_file"
        ),
    ]
    assert not should_inject_tool_first_write(
        {"selected_toolboxes": ["file_ops"]}, msgs
    )


def test_should_not_inject_wrong_toolbox():
    msgs = [
        HumanMessage(
            content="Save a short note to my workspace as note.txt. Use write_workspace_file."
        )
    ]
    assert not should_inject_tool_first_write(
        {"selected_toolboxes": ["web_search"]}, msgs
    )


def test_build_tool_first_write_message_args():
    msgs = [
        AIMessage(content="Bangkok is the capital of Thailand."),
        HumanMessage(
            content=(
                "Save a short note to my workspace as bangkok_notes_abc.txt "
                "summarizing Bangkok. Use write_workspace_file."
            )
        ),
    ]
    ai = build_tool_first_write_message(msgs)
    assert ai.tool_calls
    tc = ai.tool_calls[0]
    assert tc["name"] == "write_workspace_file"
    assert tc["args"]["filename"] == "bangkok_notes_abc.txt"
    assert "Bangkok" in tc["args"]["content"] or "Workspace note" in tc["args"]["content"]
