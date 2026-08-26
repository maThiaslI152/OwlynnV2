"""ask_user guards — block HITL loops on code-review-without-code."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.ask_user_guards import (
    ai_message_asks_user,
    build_workspace_note_content,
    extract_workspace_read_filename,
    extract_workspace_write_filename,
    is_clear_workspace_list_read_intent,
    is_clear_workspace_write_intent,
    is_code_review_missing_code,
    is_code_review_request,
    should_strip_ask_user,
    strip_ask_user_tools,
    successful_workspace_read_body,
    turn_has_reviewable_code,
    turn_has_successful_workspace_read,
    turn_has_successful_workspace_write,
)


def test_code_review_request_detection():
    assert is_code_review_request("Please review my code for bugs")
    assert is_code_review_request("code review this function")
    assert not is_code_review_request("what is the capital of France")


def test_missing_code_true_without_fence():
    msgs = [HumanMessage(content="Please review my code for bugs")]
    assert is_code_review_missing_code(msgs) is True
    assert turn_has_reviewable_code(msgs) is False


def test_missing_code_false_with_fence():
    msgs = [
        HumanMessage(
            content="Please review my code:\n```python\ndef foo():\n    return 1\n```"
        )
    ]
    assert is_code_review_missing_code(msgs) is False
    assert turn_has_reviewable_code(msgs) is True


def test_strip_ask_user_tools():
    class T:
        def __init__(self, name):
            self.name = name

    tools = [T("web_search"), T("ask_user"), T("read_workspace_file")]
    out = strip_ask_user_tools(tools)
    assert [t.name for t in out] == ["web_search", "read_workspace_file"]


def test_ai_message_asks_user():
    assert ai_message_asks_user(
        AIMessage(
            content="",
            tool_calls=[{"name": "ask_user", "args": {"question": "?"}, "id": "1"}],
        )
    )
    assert not ai_message_asks_user(AIMessage(content="ok"))


def test_clear_workspace_write_intent():
    assert is_clear_workspace_write_intent(
        "Save a short note to my workspace as bangkok_notes.txt. Use write_workspace_file."
    )
    assert is_clear_workspace_write_intent(
        "please write_workspace_file with the summary"
    )
    assert not is_clear_workspace_write_intent("what is the weather in Bangkok?")


def test_clear_workspace_list_read_intent():
    assert is_clear_workspace_list_read_intent(
        "List workspace files and read bangkok_notes.txt back to me."
    )
    assert is_clear_workspace_list_read_intent(
        "Please use read_workspace_file on note.txt"
    )
    # Bare tool-name alone must not match (Hypothesis property-test noise).
    assert not is_clear_workspace_list_read_intent("list_workspace_files")
    assert not is_clear_workspace_list_read_intent("what is the weather in Bangkok?")


def test_extract_write_filename():
    assert (
        extract_workspace_write_filename(
            "Save a note as bangkok_notes_abc.txt summarizing …"
        )
        == "bangkok_notes_abc.txt"
    )


def test_extract_read_filename():
    assert (
        extract_workspace_read_filename(
            "List workspace files and read bangkok_notes_xyz.txt back to me."
        )
        == "bangkok_notes_xyz.txt"
    )


def test_should_strip_ask_user_on_write():
    msgs = [
        HumanMessage(
            content="Save a short note to my workspace as note.txt. Use write_workspace_file."
        )
    ]
    assert should_strip_ask_user(msgs) is True


def test_should_strip_ask_user_on_list_read():
    msgs = [HumanMessage(content="List workspace files and read note.txt back to me.")]
    assert should_strip_ask_user(msgs) is True


def test_build_workspace_note_content():
    msgs = [
        HumanMessage(content="capital?"),
        AIMessage(content="Bangkok is the capital."),
        HumanMessage(content="save a note"),
    ]
    note = build_workspace_note_content(msgs, user_text="summarizing Bangkok")
    assert "Bangkok" in note
    assert "Summary" in note


def test_turn_has_successful_workspace_write():
    msgs = [
        HumanMessage(content="Save note as x.txt via write_workspace_file"),
        AIMessage(
            content="",
            tool_calls=[{"name": "write_workspace_file", "id": "1", "args": {}}],
        ),
        ToolMessage(
            content="✅ Written to x.txt", tool_call_id="1", name="write_workspace_file"
        ),
    ]
    assert turn_has_successful_workspace_write(msgs) is True
    assert (
        turn_has_successful_workspace_write(
            [HumanMessage(content="Save note as x.txt via write_workspace_file")]
        )
        is False
    )


def test_turn_has_successful_workspace_read():
    body = "Bangkok is the capital. GDP and weather notes."
    msgs = [
        HumanMessage(content="List workspace files and read note.txt back to me."),
        AIMessage(
            content="",
            tool_calls=[{"name": "read_workspace_file", "id": "1", "args": {}}],
        ),
        ToolMessage(content=body, tool_call_id="1", name="read_workspace_file"),
    ]
    assert turn_has_successful_workspace_read(msgs) is True
    assert successful_workspace_read_body(msgs) == body
    assert (
        turn_has_successful_workspace_read(
            [
                HumanMessage(content="List workspace files and read note.txt"),
                ToolMessage(
                    content="Error: File 'note.txt' not found.",
                    tool_call_id="1",
                    name="read_workspace_file",
                ),
            ]
        )
        is False
    )
