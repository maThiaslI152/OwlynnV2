"""Tests for DeepSeek DSML pseudo-tool-call stripping."""

from src.agent.nodes.complex_utils.cloud_payload import finalize_cloud_visible_content
from src.agent.nodes.complex_utils.formatter import (
    _content_has_dsml_tool_syntax,
    _strip_dsml_blocks,
)


def test_strip_dsml_blocks_removes_tool_call_markup():
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


def test_finalize_cloud_visible_content_strips_dsml():
    dsml_only = (
        "<\uff5c\uff5cDSML\uff5c\uff5ctool_calls>"
        '<\uff5c\uff5cDSML\uff5c\uff5cinvoke name="web_search">'
        "</\uff5c\uff5cDSML\uff5c\uff5cinvoke>"
        "</\uff5c\uff5cDSML\uff5c\uff5ctool_calls>"
    )
    assert finalize_cloud_visible_content(dsml_only) == ""
