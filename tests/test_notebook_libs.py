"""Tests for notebook library probing and recovery nudges."""

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


from src.tools.notebook_libs import (
    available_notebook_libraries,
    chart_completion_message,
    format_available_libraries,
    notebook_interactive_viz_guidance,
    notebook_module_missing_nudge,
    parse_chart_artifact,
    turn_ends_with_chart_completion,
)


def test_format_available_libraries_lists_detected_modules():
    available_notebook_libraries.cache_clear()
    text = format_available_libraries()
    assert "pandas" in text
    assert "numpy" in text


def test_notebook_module_missing_nudge_viz_steers_to_html():
    available_notebook_libraries.cache_clear()
    nudge = notebook_module_missing_nudge("matplotlib")
    assert "matplotlib" in nudge
    assert "Actually available" in nudge
    assert "Do NOT retry matplotlib" in nudge
    assert "inline HTML" in nudge


def test_notebook_module_missing_nudge_non_viz():
    nudge = notebook_module_missing_nudge("foobar")
    assert "foobar" in nudge
    assert "Retry using only" in nudge
    assert "inline HTML" not in nudge


def test_parse_chart_artifact_interactive_html():
    artifact = parse_chart_artifact(
        "[Cell 1]\nInteractive chart saved to ukraine_sitrep.html",
        project_id="proj-1",
    )
    assert artifact == {
        "filename": "ukraine_sitrep.html",
        "url": "/api/files/ukraine_sitrep.html?project_id=proj-1",
        "kind": "interactive",
        "mime_type": "text/html",
    }


def test_parse_chart_artifact_static_png():
    artifact = parse_chart_artifact(
        "[Cell 1]\nChart saved to trend.png",
        project_id="default",
    )
    assert artifact == {
        "filename": "trend.png",
        "url": "/api/files/trend.png?project_id=default",
        "kind": "static",
        "mime_type": "image/png",
    }


def test_parse_chart_artifact_skips_errors():
    assert (
        parse_chart_artifact("[Cell 1] Error:\nTraceback", project_id="default") is None
    )
    assert parse_chart_artifact("[Cell 1]\nNo chart here", project_id="default") is None


def test_notebook_interactive_viz_guidance_mentions_plotly():
    guidance = notebook_interactive_viz_guidance("proj-1")
    assert "plotly" in guidance.lower()
    assert "chart.html" in guidance
    assert "project_id=proj-1" in guidance


def test_chart_completion_message_interactive():
    text = chart_completion_message(
        "[Cell 1]\nInteractive chart saved to chart.html",
        project_id="default",
    )
    assert text is not None
    assert "interactive chart" in text.lower()


def test_turn_ends_with_chart_completion():
    turn = [
        HumanMessage(content="Visualize this"),
        AIMessage(
            content="", tool_calls=[{"id": "1", "name": "notebook_run", "args": {}}]
        ),
        ToolMessage(
            content="[Cell 1]\nChart saved to trend.png",
            tool_call_id="1",
            name="notebook_run",
        ),
        AIMessage(content="I've created a chart from our conversation."),
    ]
    assert turn_ends_with_chart_completion(turn, project_id="default") is True

    incomplete = turn[:-1]
    assert turn_ends_with_chart_completion(incomplete, project_id="default") is False
