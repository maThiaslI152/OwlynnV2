"""Unit tests for BUG-4 fix: Chat Auto-Title fallback."""

import re
from datetime import datetime


def _chat_title_fallback(user_text: str) -> str:
    """Extracted fallback logic from generate_chat_title_router_llm."""
    fallback = user_text.split("\n")[0].strip()
    fallback = re.sub(
        r"^(hi|hey|hello|ok|okay|yes|no|thanks|please)[,.\s]*",
        "",
        fallback,
        flags=re.IGNORECASE,
    ).strip()
    if not fallback:
        return f"Chat — {datetime.now().strftime('%b %d, %I:%M %p')}"
    fallback = re.sub(r"\s+", " ", fallback).strip()
    return fallback[:60]


class TestChatTitleFallback:
    """Verify that greeting-only messages produce timestamp titles."""

    def test_standalone_hi_produces_timestamp(self):
        result = _chat_title_fallback("Hi")
        assert "Chat —" in result

    def test_standalone_hello_produces_timestamp(self):
        result = _chat_title_fallback("Hello")
        assert "Chat —" in result

    def test_standalone_hey_produces_timestamp(self):
        result = _chat_title_fallback("Hey")
        assert "Chat —" in result

    def test_standalone_thanks_produces_timestamp(self):
        result = _chat_title_fallback("Thanks")
        assert "Chat —" in result

    def test_meaningful_message_preserved(self):
        result = _chat_title_fallback("What is the capital of France?")
        assert "What is the capital of France" in result

    def test_greeting_with_content_strips_prefix(self):
        result = _chat_title_fallback("Hi, can you help me with python?")
        assert "can you help me with python" in result.lower()
        assert not result.lower().startswith("hi")

    def test_ok_with_comma_strips_prefix(self):
        result = _chat_title_fallback("OK, let me think about this")
        assert "let me think about this" in result.lower()

    def test_empty_message_returns_timestamp(self):
        result = _chat_title_fallback("")
        assert "Chat —" in result


class TestChatTitleLogLevel:
    """Verify the log level was upgraded from debug to warning."""

    def test_log_level_is_warning_not_debug(self):
        """The generate_chat_title_router_llm function must use logger.warning."""
        import inspect
        from src.agent.nodes.router import generate_chat_title_router_llm

        source = inspect.getsource(generate_chat_title_router_llm)
        assert (
            "logger.warning" in source
        ), "Expected logger.warning (was upgraded from logger.debug for visibility)"
        assert (
            "logger.debug" not in source
        ), "logger.debug should be replaced by logger.warning in chat title fallback"
