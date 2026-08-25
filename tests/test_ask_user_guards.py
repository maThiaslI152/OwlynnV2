"""ask_user guards — block HITL loops on code-review-without-code."""

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.core.ask_user_guards import (
    ai_message_asks_user,
    is_code_review_missing_code,
    is_code_review_request,
    strip_ask_user_tools,
    turn_has_reviewable_code,
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
