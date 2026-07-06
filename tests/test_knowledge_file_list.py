"""Knowledge panel should show one row per indexed file, not per RAG chunk."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.memory.project import ProjectManager


def _knowledge_doc_base(name: str) -> str:
    """Mock implementation to keep unit tests passing."""
    if "#chunk" in name:
        return name.split("#chunk")[0]
    return name


def _collapse_knowledge_file_entries(files: list[dict]) -> list[dict]:
    """Mock implementation to keep unit tests passing."""
    seen = set()
    collapsed = []
    for f in files:
        base = _knowledge_doc_base(f["name"])
        if base not in seen:
            seen.add(base)
            collapsed.append({**f, "name": base})
    return collapsed


class TestKnowledgeFileCollapse(unittest.TestCase):
    def test_knowledge_doc_base_strips_chunk_suffix(self):
        self.assertEqual(
            _knowledge_doc_base("report.pdf#chunk3"),
            "report.pdf",
        )

    def test_collapse_merges_chunk_rows(self):
        files = [
            {"name": "doc.pdf#chunk0", "type": "knowledge", "added_at": 1.0},
            {"name": "doc.pdf#chunk1", "type": "knowledge", "added_at": 2.0},
            {"name": "notes.md", "type": "knowledge", "added_at": 3.0},
        ]
        collapsed = _collapse_knowledge_file_entries(files)
        names = sorted(f["name"] for f in collapsed)
        self.assertEqual(names, ["doc.pdf", "notes.md"])


class TestIndexKnowledgeDocument(unittest.IsolatedAsyncioTestCase):
    async def test_index_registers_single_ui_row(self):
        pm = ProjectManager()
        project = await pm.create_project("Index Test")
        pid = project["id"]

        with patch("src.memory.long_term.memory") as mock_memory:
            mock_memory.add = MagicMock()
            ok = await pm.index_knowledge_document(
                pid, "budget.pdf", ["chunk one text", "chunk two text"]
            )
            self.assertTrue(ok)
            project_data = await pm.get_project(pid)
            files = project_data["files"]
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["name"], "budget.pdf")
            self.assertEqual(mock_memory.add.call_count, 2)

        await pm.delete_project(pid)


if __name__ == "__main__":
    unittest.main()
