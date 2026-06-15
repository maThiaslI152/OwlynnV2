"""Tests for render_interactive_block and fence formatting."""

from __future__ import annotations

import json

import pytest

from src.tools.interactive_content import (
    BLOCK_LANG,
    format_interactive_fence,
    render_interactive_block,
)


def test_format_quiz_fence():
    payload = {
        "question": "What is 2+2?",
        "options": ["3", "4", "5"],
        "correctIndex": 1,
        "explanation": "Basic arithmetic.",
    }
    fence = format_interactive_fence("quiz", payload)
    assert fence.startswith("```owlynn-quiz\n")
    assert fence.endswith("\n```")
    assert "What is 2+2?" in fence


def test_format_rejects_invalid_quiz():
    with pytest.raises(ValueError):
        format_interactive_fence("quiz", {"question": "Only question"})


def test_render_interactive_block_tool():
    result = render_interactive_block.invoke(
        {
            "block_type": "callout",
            "payload": {"variant": "tip", "body": "Remember to review."},
        }
    )
    assert "owlynn-callout" in result
    assert "Remember to review" in result


def test_all_block_types_have_schema():
    for block_type in BLOCK_LANG:
        payload = _minimal_payload(block_type)
        fence = format_interactive_fence(block_type, payload)
        assert f"```{BLOCK_LANG[block_type]}" in fence


def _minimal_payload(block_type: str) -> dict:
    if block_type == "quiz":
        return {"question": "Q?", "options": ["A", "B"], "correctIndex": 0}
    if block_type == "steps":
        return {"steps": [{"heading": "One", "body": "First step"}]}
    if block_type == "callout":
        return {"body": "Note text"}
    if block_type == "embed":
        return {"type": "chart", "url": "/api/files/chart.html?project_id=default"}
    if block_type == "cell":
        return {"code": "print(1)"}
    raise ValueError(block_type)
