"""WS handler helpers for tool UI (preamble suppression, status detection)."""

from src.api.ws.handler import (
    _is_tool_preamble_text,
    _tool_status_from_content,
)


def test_tool_preamble_detection():
    assert _is_tool_preamble_text("Reading workspace file…")
    assert _is_tool_preamble_text("Searching the web…")
    assert not _is_tool_preamble_text(
        "Here is a study guide for chapter 1 with real content."
    )


def test_tool_status_prefix_not_substring():
    assert _tool_status_from_content("Error: File 'x.pdf' not found.") == "error"
    assert (
        _tool_status_from_content(
            "Section discusses common error: handling in digital literacy."
        )
        == "success"
    )


def test_workspace_paths_attached_pattern():
    from src.agent.nodes.complex import _workspace_paths_from_text

    paths = _workspace_paths_from_text(
        "Help me study\n[Attached: chapter 1 Digital Literacy.pdf]"
    )
    assert paths == ["chapter 1 Digital Literacy.pdf"]
