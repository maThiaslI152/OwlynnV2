"""Tests for .ipynb tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tools import ipynb_tools
from src.tools.workspace_context import reset_active_project, set_active_project_for_run


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.tools.workspace_context.tool_workspace_root", lambda: str(tmp_path)
    )
    token = set_active_project_for_run("default")
    yield tmp_path
    reset_active_project(token)


def test_write_and_read_ipynb(ws: Path):
    cells = json.dumps(
        [
            {"cell_type": "markdown", "source": "# Title"},
            {"cell_type": "code", "source": "x = 1\n"},
        ]
    )
    out = ipynb_tools.write_ipynb.invoke(
        {"filename": "lesson.ipynb", "cells_json": cells}
    )
    assert "Saved notebook" in out
    summary = ipynb_tools.read_ipynb.invoke({"filename": "lesson.ipynb"})
    assert "2 cells" in summary
    assert "markdown" in summary


def test_read_ipynb_missing(ws: Path):
    result = ipynb_tools.read_ipynb.invoke({"filename": "missing.ipynb"})
    assert "not found" in result.lower()
