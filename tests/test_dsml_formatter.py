"""Tests for DeepSeek DSML pseudo-tool-call stripping."""

from src.agent.nodes.complex_utils.cloud_payload import finalize_cloud_visible_content
from src.agent.nodes.complex_utils.formatter import (
    _content_has_dsml_tool_syntax,
    _strip_dsml_blocks,
    needs_web_synthesis_retry,
    placeholder_for_tool_only_turn,
)


def test_strip_dsml_blocks_removes_dsml_markup():
    raw = (
        "Let me grab more info.\n"
        "<\uff5c\uff5cDSML\uff5c\uff5ctool_calls>\n"
        '<\uff5c\uff5cDSML\uff5c\uff5cinvoke name="fetch_webpage">\n'
        '<\uff5c\uff5cDSML\uff5c\uff5cparameter name="url" string="true">'
        "https://example.com</\uff5c\uff5cDSML\uff5c\uff5cparameter>\n"
        "</\uff5c\uff5cDSML\uff5c\uff5cinvoke>\n"
        "</\uff5c\uff5cDSML\uff5c\uff5ctool_calls>"
    )
    cleaned = _strip_dsml_blocks(raw)
    assert cleaned == "Let me grab more info."
    assert not _content_has_dsml_tool_syntax(cleaned)


def test_content_has_dsml_tool_syntax_detects_alt_markers():
    assert _content_has_dsml_tool_syntax('<tool_call>{"name":"web_search"}</tool_call>')
    assert _content_has_dsml_tool_syntax('<function=fetch_webpage>{"url":"x"}')
    assert not _content_has_dsml_tool_syntax("Plain answer with no tool syntax.")


def test_finalize_cloud_visible_content_strips_dsml():
    dsml_only = (
        "<\uff5c\uff5cDSML\uff5c\uff5ctool_calls>"
        '<\uff5c\uff5cDSML\uff5c\uff5cinvoke name="web_search">'
        "</\uff5c\uff5cDSML\uff5c\uff5cinvoke>"
        "</\uff5c\uff5cDSML\uff5c\uff5ctool_calls>"
    )
    assert finalize_cloud_visible_content(dsml_only) == ""


def test_strip_dsml_blocks_removes_tool_call_markup():
    raw = (
        "Based on my search, here's the weather for Tokyo:\n\n"
        "Temperature: 21°C\n\n"
        "<tool_call> <function=create_docx> tokyo_weather.txt </tool_call>"
    )
    cleaned = _strip_dsml_blocks(raw)
    assert "tool_call" not in cleaned.lower()
    assert "Tokyo" in cleaned
    assert not _content_has_dsml_tool_syntax(cleaned)


def test_needs_web_synthesis_retry_on_prose_plus_tool_markup():
    raw = (
        "A" * 100
        + " <tool_call> <function=read_workspace_file> docs/STATUS.md </tool_call>"
    )
    cleaned = _strip_dsml_blocks(raw)
    assert needs_web_synthesis_retry(
        has_tool_calls=False,
        raw_visible=raw,
        cleaned_visible=cleaned,
    )
    assert not needs_web_synthesis_retry(
        has_tool_calls=False,
        raw_visible="Plain answer with enough characters. " * 5,
        cleaned_visible="Plain answer with enough characters. " * 5,
    )


def test_strip_qwen_xml_and_preserve_trailing_prose():
    raw = '<function=fetch_webpage>{"url": "https://example.com"}</function> Here is the weather summary.'
    cleaned = _strip_dsml_blocks(raw)
    assert cleaned == "Here is the weather summary."
    assert not _content_has_dsml_tool_syntax(cleaned)


def test_strip_orphan_qwen_tags():
    raw = "Hello! </tool_call> and </function> should be stripped."
    cleaned = _strip_dsml_blocks(raw)
    assert cleaned == "Hello!  and  should be stripped."
    assert not _content_has_dsml_tool_syntax(cleaned)


def test_content_has_dsml_tool_syntax_detects_orphan_closing_tags():
    assert _content_has_dsml_tool_syntax("Some content </tool_call>")
    assert _content_has_dsml_tool_syntax("Some content </function>")


def test_placeholder_for_tool_only_turn_notebook():
    text = placeholder_for_tool_only_turn([{"name": "notebook_run", "args": {}}])
    assert "notebook_run" in text
    assert "chart" in text.lower() or "Generating" in text
