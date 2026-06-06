"""Knowledge panel should show one row per indexed file, not per RAG chunk."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.memory.project import (
    ProjectManager,
    _collapse_knowledge_file_entries,
    _knowledge_doc_base,
)


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

    def test_migrate_collapses_existing_projects_json(self):
        pm = ProjectManager()
        project = pm.create_project("Collapse Test")
        pid = project["id"]
        with pm._lock:
            pm.projects[pid]["files"] = [
                {"name": "a.xlsx#chunk0", "type": "knowledge", "added_at": 1.0},
                {"name": "a.xlsx#chunk1", "type": "knowledge", "added_at": 2.0},
            ]
            pm._save()
        reloaded = ProjectManager()
        files = reloaded.get_project(pid)["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "a.xlsx")
        reloaded.delete_project(pid)


class TestIndexKnowledgeDocument(unittest.TestCase):
    def test_index_registers_single_ui_row(self):
        pm = ProjectManager()
        project = pm.create_project("Index Test")
        pid = project["id"]

        async def run():
            with patch("src.memory.long_term.memory") as mock_memory:
                mock_memory.add = MagicMock()
                ok = await pm.index_knowledge_document(
                    pid, "budget.pdf", ["chunk one text", "chunk two text"]
                )
                self.assertTrue(ok)
                files = pm.get_project(pid)["files"]
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0]["name"], "budget.pdf")
                self.assertEqual(mock_memory.add.call_count, 2)

        asyncio.run(run())
        pm.delete_project(pid)


if __name__ == "__main__":
    unittest.main()
