"""Tests for tool-first workspace list/read injection."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.tool_first_list_read import (
    build_tool_first_list_read_message,
    should_inject_tool_first_list_read,
)


def test_should_inject_clear_list_read_file_ops():
    msgs = [
        HumanMessage(
            content="List workspace files and read bangkok_notes.txt back to me."
        )
    ]
    assert should_inject_tool_first_list_read(
        {"selected_toolboxes": ["file_ops"]}, msgs
    )


def test_should_not_inject_after_successful_read():
    msgs = [
        HumanMessage(content="List workspace files and read note.txt back to me."),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_workspace_file",
                    "id": "1",
                    "args": {"filename": "note.txt"},
                }
            ],
        ),
        ToolMessage(
            content="note body here",
            tool_call_id="1",
            name="read_workspace_file",
        ),
    ]
    assert not should_inject_tool_first_list_read(
        {"selected_toolboxes": ["file_ops"]}, msgs
    )


def test_should_not_inject_wrong_toolbox():
    msgs = [
        HumanMessage(
            content="List workspace files and read note.txt back to me."
        )
    ]
    assert not should_inject_tool_first_list_read(
        {"selected_toolboxes": ["web_search"]}, msgs
    )


def test_build_tool_first_list_read_message_args():
    msgs = [
        HumanMessage(
            content="List workspace files and read bangkok_notes_abc.txt back to me."
        )
    ]
    ai = build_tool_first_list_read_message(msgs)
    assert ai.tool_calls
    names = [tc["name"] for tc in ai.tool_calls]
    assert names == ["list_workspace_files", "read_workspace_file"]
    assert ai.tool_calls[1]["args"]["filename"] == "bangkok_notes_abc.txt"
