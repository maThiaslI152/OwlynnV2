"""Tests for chart_artifact parsing from write_workspace_file output."""

from src.tools.notebook_libs import parse_chart_artifact


def test_parse_chart_artifact_write_workspace_html():
    artifact = parse_chart_artifact(
        "✅ Written to prices.html",
        project_id="default",
    )
    assert artifact == {
        "filename": "prices.html",
        "url": "/api/files/prices.html?project_id=default",
        "kind": "interactive",
        "mime_type": "text/html",
    }


def test_parse_chart_artifact_write_workspace_png():
    artifact = parse_chart_artifact(
        "✅ Written to trend.png",
        project_id="proj-2",
    )
    assert artifact == {
        "filename": "trend.png",
        "url": "/api/files/trend.png?project_id=proj-2",
        "kind": "static",
        "mime_type": "image/png",
    }


def test_write_workspace_file_success_attaches_chart_artifact():
    """Mirrors WS handler logic for write_workspace_file + .html."""
    content = "✅ Written to python_benchmarks.html"
    tool_name = "write_workspace_file"
    status = "success"
    chart_artifact = None
    if status == "success" and tool_name in ("notebook_run", "write_workspace_file"):
        chart_artifact = parse_chart_artifact(content, "default")
    assert chart_artifact is not None
    assert chart_artifact["kind"] == "interactive"
    assert chart_artifact["filename"] == "python_benchmarks.html"
