import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.project import project_manager
from src.tools.rag_tools import _keyword_search_local, search_workspace_docs


@pytest.fixture
def mock_processed_dir(tmp_path):
    """Fixture to set up a mock workspace and .processed directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    processed = workspace / ".processed"
    processed.mkdir()

    # Create dummy processed files
    with open(processed / "doc1.txt", "w", encoding="utf-8") as f:
        f.write("The quick brown fox jumps over the lazy dog. Codeword is ZEBRA-42.")
    with open(processed / "doc2.md", "w", encoding="utf-8") as f:
        f.write(
            "Database configuration. Username: admin, Host: localhost. Secret token: OWLYNN-KEY."
        )

    return workspace


def test_keyword_search_local(mock_processed_dir):
    with patch(
        "src.tools.rag_tools.get_project_workspace",
        return_value=str(mock_processed_dir),
    ):
        # Test full match
        hits = _keyword_search_local("default", "ZEBRA-42")
        assert len(hits) == 1
        assert hits[0]["metadata"]["filename"] == "doc1"
        assert "ZEBRA-42" in hits[0]["memory"]

        # Test partial word matches
        hits = _keyword_search_local("default", "database admin host")
        assert len(hits) == 1
        assert hits[0]["metadata"]["filename"] == "doc2"
        assert "Username: admin" in hits[0]["memory"]

        # Test no matches
        hits = _keyword_search_local("default", "nonexistentstuff")
        assert len(hits) == 0


@pytest.mark.anyio
async def test_search_workspace_docs_hybrid(mock_processed_dir):
    # Mock context active project ID
    from src.tools.workspace_context import _active_project_id

    _active_project_id.set("test_proj")

    # Mock Mem0 vector store return value
    mock_mem0 = MagicMock()
    mock_mem0.search.return_value = [
        {
            "memory": "Semantic search result about dog",
            "metadata": {"filename": "doc1", "source": "vector_search"},
        }
    ]

    with (
        patch(
            "src.tools.rag_tools.get_project_workspace",
            return_value=str(mock_processed_dir),
        ),
        patch("src.memory.long_term.memory", mock_mem0),
    ):
        # Perform query that matches keyword higher than vector
        result = search_workspace_docs.invoke({"query": "OWLYNN-KEY"})
        # Assert keyword match is in output
        assert "OWLYNN-KEY" in result
        # Assert filename source is outputted
        assert "doc2" in result


@pytest.mark.anyio
async def test_api_directory_indexing_endpoint():
    """Test POST /api/projects/{project_id}/knowledge/directory endpoint logic."""
    from fastapi import HTTPException

    from src.api.routes.project import api_add_project_directory_knowledge

    # 1. Missing directory path raises 400
    with pytest.raises(HTTPException) as exc:
        await api_add_project_directory_knowledge("test_proj", {})
    assert exc.value.status_code == 400

    # 2. Access denied for path outside workspace
    with (
        patch(
            "src.config.settings.get_project_workspace",
            return_value="/workspace/project_dir",
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await api_add_project_directory_knowledge(
            "test_proj", {"directory_path": "/etc/passwd"}
        )
    assert exc.value.status_code == 403
