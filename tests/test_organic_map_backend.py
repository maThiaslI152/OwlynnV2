"""Regression tests for organic-map / chat-only backend identity."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_thought_node_is_conversation_identity():
    from src.memory.thought_graph import ThoughtGraphManager

    mgr = ThoughtGraphManager()
    await mgr.ensure_tables()
    node = await mgr.get_or_create_node(
        node_id="organic-node-1",
        title="Organic Branch",
        mode="normal",
    )
    assert node["id"] == "organic-node-1"
    assert node["mode"] == "normal"
    fetched = await mgr.get_node("organic-node-1")
    assert fetched is not None
    assert fetched["title"] == "Organic Branch"


def test_tool_workspace_root_is_ephemeral_outside_pentest(tmp_path, monkeypatch):
    from src.tools import workspace_context as wc

    wc._scratch_dirs.clear()
    monkeypatch.setattr(wc, "get_active_scenario_id", lambda: None)
    monkeypatch.setattr(
        "src.config.audit_log.get_thread_id", lambda: "thread-organic-test"
    )

    root1 = wc.tool_workspace_root()
    root2 = wc.tool_workspace_root()
    assert root1 == root2
    assert "owlynn-scratch" in root1
    assert "projects" not in root1


def test_complex_tools_exclude_workspace_file_crud():
    from src.agent.tool_sets import COMPLEX_TOOLS_NO_WEB, COMPLEX_TOOLS_WITH_WEB

    names_web = {getattr(t, "name", None) or getattr(t, "__name__", "") for t in COMPLEX_TOOLS_WITH_WEB}
    names_no = {getattr(t, "name", None) or getattr(t, "__name__", "") for t in COMPLEX_TOOLS_NO_WEB}
    banned = {
        "read_workspace_file",
        "write_workspace_file",
        "edit_workspace_file",
        "list_workspace_files",
        "delete_workspace_file",
        "download_to_workspace",
        "search_workspace_docs",
    }
    assert names_web.isdisjoint(banned)
    assert names_no.isdisjoint(banned)


def test_pentest_toolbox_still_has_file_ops():
    from src.agent.tool_sets import TOOLBOX_REGISTRY

    pentest = TOOLBOX_REGISTRY.get("pentest") or []
    names = {getattr(t, "name", None) or getattr(t, "__name__", "") for t in pentest}
    assert "read_workspace_file" in names
    assert "write_workspace_file" in names


def test_files_for_message_content_skips_disk_when_no_base():
    from src.api.controllers.ws_helpers import _files_for_message_content

    files = [
        {"type": "workspace_ref", "path": "foo.png", "name": "foo.png"},
        {"name": "note.txt", "type": "text/plain", "data": "aGVsbG8="},
    ]
    out = _files_for_message_content(files, "")
    assert len(out) == 2
    assert out[0]["type"] == "workspace_ref"
    assert out[1]["name"] == "note.txt"


def test_lifespan_does_not_start_file_watcher():
    """Organic-map: lifespan must not start the workspace file watcher."""
    import inspect

    from src.api import server as server_mod

    src = inspect.getsource(server_mod.lifespan)
    assert "file_watcher = None" in src
    assert "start_watcher(" not in src
