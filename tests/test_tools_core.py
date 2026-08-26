"""Tests for core workspace tools (no sandbox dependency)."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest

from src.tools.core_tools import (
    delete_workspace_file,
    edit_workspace_file,
    get_safe_workspace_path,
    list_workspace_files,
    read_workspace_file,
    recall_memories,
    write_workspace_file,
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Create a temp workspace and patch the workspace root."""
    monkeypatch.setattr("src.tools.core_tools.BASE_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "src.tools.core_tools.tool_workspace_root", lambda: str(tmp_path)
    )
    return tmp_path


def test_write_and_read(workspace):
    result = write_workspace_file.invoke(
        {"filename": "test.txt", "content": "hello world"}
    )
    assert "Written" in result
    assert (workspace / "test.txt").exists()

    content = read_workspace_file.invoke({"filename": "test.txt"})
    assert content == "hello world"


def test_write_accepts_path_alias(workspace):
    result = write_workspace_file.invoke({"path": "via_path.txt", "content": "ok"})
    assert "Written" in result
    assert (workspace / "via_path.txt").read_text() == "ok"


def test_scratch_root_outside_base_is_allowed(tmp_path, monkeypatch):
    """Ephemeral Normal/Study scratch is not under BASE_WORKSPACE_DIR."""
    base = tmp_path / "projects"
    scratch = tmp_path / "scratch"
    base.mkdir()
    scratch.mkdir()
    monkeypatch.setattr("src.tools.core_tools.BASE_WORKSPACE_DIR", str(base))
    monkeypatch.setattr(
        "src.tools.core_tools.tool_workspace_root", lambda: str(scratch)
    )
    fp, err = get_safe_workspace_path("note.txt")
    assert err is None
    assert fp.endswith("note.txt")
    assert "scratch" in fp
    out = write_workspace_file.invoke({"filename": "note.txt", "content": "hi"})
    assert "Written" in out
    assert (scratch / "note.txt").read_text() == "hi"


def test_edit_file(workspace):
    (workspace / "doc.txt").write_text("foo bar baz")
    result = edit_workspace_file.invoke(
        {
            "filename": "doc.txt",
            "search_pattern": "bar",
            "replacement_text": "qux",
        }
    )
    assert "Updated" in result
    assert (workspace / "doc.txt").read_text() == "foo qux baz"


def test_edit_pattern_not_found(workspace):
    (workspace / "doc.txt").write_text("hello")
    result = edit_workspace_file.invoke(
        {
            "filename": "doc.txt",
            "search_pattern": "missing",
            "replacement_text": "x",
        }
    )
    assert "not found" in result.lower() or "Pattern" in result


def test_list_files(workspace):
    (workspace / "a.txt").write_text("a")
    (workspace / "b.txt").write_text("bb")
    (workspace / "subdir").mkdir()
    result = list_workspace_files.invoke({"directory": "."})
    assert "a.txt" in result
    assert "b.txt" in result
    assert "subdir" in result


def test_delete_file(workspace):
    (workspace / "del.txt").write_text("delete me")
    result = delete_workspace_file.invoke({"filename": "del.txt"})
    assert "Deleted" in result
    assert not (workspace / "del.txt").exists()


def test_delete_nonexistent(workspace):
    result = delete_workspace_file.invoke({"filename": "nope.txt"})
    assert "not found" in result.lower()


def test_read_nonexistent(workspace):
    result = read_workspace_file.invoke({"filename": "nope.txt"})
    assert "not found" in result.lower() or "Error" in result


def test_read_attached_filename_wrapper(workspace):
    processed = workspace / ".processed"
    processed.mkdir()
    (processed / "chapter 1 Digital Literacy.pdf.txt").write_text(
        "study notes from cache"
    )
    (workspace / "chapter 1 Digital Literacy.pdf").write_bytes(b"%PDF-1.4\n")
    result = read_workspace_file.invoke(
        {"filename": "[Attached: chapter 1 Digital Literacy.pdf]"}
    )
    assert "study notes from cache" in result


def test_read_attached_filename_txt(workspace):
    (workspace / "notes.txt").write_text("plain study notes")
    result = read_workspace_file.invoke({"filename": "[Attached: notes.txt]"})
    assert result == "plain study notes"


def test_read_uses_project_processed_cache(workspace):
    processed = workspace / ".processed"
    processed.mkdir()
    (processed / "cached.pdf.txt").write_text("from cache")
    (workspace / "cached.pdf").write_bytes(b"%PDF-1.4")
    result = read_workspace_file.invoke({"filename": "cached.pdf"})
    assert result == "from cache"


def test_path_traversal_blocked(workspace):
    _, err = get_safe_workspace_path("../../etc/passwd")
    assert err is not None
    assert "denied" in err.lower() or "outside" in err.lower()


def test_recall_memories_empty():
    with patch("src.tools.core_tools.search_memories", return_value=[]):
        result = recall_memories.invoke({"query": "test"})
        assert "No relevant" in result


def test_recall_memories_with_results():
    fake = [{"fact": "User likes Python", "timestamp": "2026-01-01T00:00:00"}]
    with patch("src.tools.core_tools.search_memories", return_value=fake):
        result = recall_memories.invoke({"query": "python"})
        assert "Python" in result
