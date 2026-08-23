"""
Unit Tests for Project & Chat CRUD Operations
===============================================

Tests the ``ProjectManager`` class from ``src.memory.project`` using
standard unittest assertions. Organized into three test classes:

- **TestProjectCRUD**: Create, edit, delete projects. Validates structure,
  persistence, field isolation, and default protection.
- **TestChatCRUD**: Add, rename, delete chats within projects. Validates
  dedup, field preservation, and count correctness.
- **TestEdgeCases**: Empty names, 200+ char names, unicode, special chars.

Each test method documents which requirement it validates (e.g., Req 1.1).
setUp/tearDown handle project lifecycle to avoid test pollution.

Run: ``pytest tests/test_crud_operations.py -v``
"""

import asyncio
import os
import sys
import unittest

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory.project import ProjectManager


class TestProjectCRUD(unittest.IsolatedAsyncioTestCase):
    """Unit tests for project create operations.
    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 7.1
    """

    async def asyncSetUp(self):
        self.pm = ProjectManager()
        self.created_project_ids = []

    async def asyncTearDown(self):
        for pid in self.created_project_ids:
            await self.pm.delete_project(pid)

    async def _create_and_track(self, name, instructions=None):
        project = await self.pm.create_project(name, instructions)
        self.created_project_ids.append(project["id"])
        return project

    async def test_create_project_returns_valid_structure(self):
        """Verify returned dict has keys id, name, instructions, files, chats, category."""
        result = await self._create_and_track("Structure Test")
        expected_keys = {"id", "name", "instructions", "files", "chats", "category"}
        self.assertTrue(expected_keys.issubset(result.keys()))

    async def test_create_project_name_matches(self):
        """Verify result['name'] equals provided name."""
        result = await self._create_and_track("My Project Name")
        self.assertEqual(result["name"], "My Project Name")

    async def test_create_project_id_length(self):
        """Verify result['id'] is 8 characters."""
        result = await self._create_and_track("ID Length Test")
        self.assertEqual(len(result["id"]), 8)

    async def test_create_project_default_instructions(self):
        """Verify default instructions assigned when none provided."""
        result = await self._create_and_track("Default Instructions Test")
        self.assertIsNotNone(result["instructions"])
        self.assertIsInstance(result["instructions"], str)
        self.assertGreater(len(result["instructions"]), 0)

    async def test_create_project_custom_instructions(self):
        """Verify custom instructions assigned when provided."""
        custom = "You are a specialized coding assistant."
        result = await self._create_and_track(
            "Custom Instructions Test", instructions=custom
        )
        self.assertEqual(result["instructions"], custom)

    async def test_create_project_empty_lists(self):
        """Verify chats and files are empty lists."""
        result = await self._create_and_track("Empty Lists Test")
        self.assertEqual(result["chats"], [])
        self.assertEqual(result["files"], [])

    async def test_create_project_persisted(self):
        """Verify get_project(id) returns equivalent dict after creation."""
        result = await self._create_and_track("Persistence Test")
        fetched = await self.pm.get_project(result["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], result["id"])
        self.assertEqual(fetched["name"], result["name"])
        self.assertEqual(fetched["instructions"], result["instructions"])
        self.assertEqual(fetched["files"], result["files"])
        self.assertEqual(fetched["chats"], result["chats"])
        self.assertEqual(fetched["category"], result["category"])

    # --- Task 1.2: Edit project tests ---
    # Validates: Requirements 2.1, 2.2, 2.3, 2.4, 7.1

    async def test_edit_project_name(self):
        """Verify update_project returns dict with new name. (Req 2.1)"""
        project = await self._create_and_track("Original Name")
        updated = await self.pm.update_project(project["id"], name="Updated Name")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "Updated Name")

    async def test_edit_project_preserves_other_fields(self):
        """Verify id, instructions, chats, files, category unchanged after name update. (Req 2.2)"""
        project = await self._create_and_track(
            "Preserve Fields Test", instructions="Custom instructions"
        )
        original_id = project["id"]
        original_instructions = project["instructions"]
        original_chats = project["chats"]
        original_files = project["files"]
        original_category = project["category"]

        updated = await self.pm.update_project(project["id"], name="New Name")
        self.assertEqual(updated["id"], original_id)
        self.assertEqual(updated["instructions"], original_instructions)
        self.assertEqual(updated["chats"], original_chats)
        self.assertEqual(updated["files"], original_files)
        self.assertEqual(updated["category"], original_category)

    async def test_edit_project_name_nonexistent(self):
        """Verify update_project returns None for unknown ID. (Req 2.3)"""
        result = await self.pm.update_project("nonexistent_id", name="Doesn't Matter")
        self.assertIsNone(result)

    async def test_edit_project_persisted(self):
        """Verify get_project reflects update after save. (Req 2.4, 7.1)"""
        project = await self._create_and_track("Persist Edit Test")
        await self.pm.update_project(project["id"], name="Persisted Name")
        fetched = await self.pm.get_project(project["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Persisted Name")

    # --- Task 1.3: Delete project tests ---
    # Validates: Requirements 3.1, 3.2, 3.3, 3.4, 7.3

    async def test_delete_project(self):
        """Verify delete returns True and get_project returns None. (Req 3.1, 3.4)"""
        project = await self.pm.create_project("Delete Me")
        pid = project["id"]
        result = await self.pm.delete_project(pid)
        self.assertTrue(result)
        self.assertIsNone(await self.pm.get_project(pid))

    async def test_delete_default_project_rejected(self):
        """Verify delete_project('default') returns False and default project still exists. (Req 3.2, 7.3)"""
        result = await self.pm.delete_project("default")
        self.assertFalse(result)
        default = await self.pm.get_project("default")
        self.assertIsNotNone(default)
        self.assertEqual(default["id"], "default")

    async def test_delete_nonexistent_project(self):
        """Verify deleting a nonexistent project returns False. (Req 3.3)"""
        result = await self.pm.delete_project("nonexistent_id_xyz")
        self.assertFalse(result)


class TestChatCRUD(unittest.IsolatedAsyncioTestCase):
    """Unit tests for chat create operations.
    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 7.1
    """

    async def asyncSetUp(self):
        self.pm = ProjectManager()
        self.project = await self.pm.create_project("Chat Test Project")
        self.pid = self.project["id"]
        self.chat_info = {"id": "chat-001", "name": "Test Chat", "created_at": 1000.0}
        await self.pm.add_chat_to_project(self.pid, self.chat_info)

    async def asyncTearDown(self):
        await self.pm.delete_project(self.pid)

    async def test_add_chat(self):
        """Verify chat appears in project's chats list. (Req 4.1)"""
        project = await self.pm.get_project(self.pid)
        self.assertTrue(any(c["id"] == "chat-001" for c in project["chats"]))
        chat = next(c for c in project["chats"] if c["id"] == "chat-001")
        self.assertEqual(chat["name"], "Test Chat")
        self.assertEqual(chat["created_at"], 1000.0)

    async def test_add_duplicate_chat_ignored(self):
        """Verify adding same chat ID twice results in one entry. (Req 4.2)"""
        duplicate_chat = {
            "id": "chat-001",
            "name": "Duplicate Chat",
            "created_at": 2000.0,
        }
        await self.pm.add_chat_to_project(self.pid, duplicate_chat)
        project = await self.pm.get_project(self.pid)
        matching = [c for c in project["chats"] if c["id"] == "chat-001"]
        self.assertEqual(len(matching), 1)
        # Original chat should be preserved, not the duplicate
        self.assertEqual(matching[0]["name"], "Test Chat")

    async def test_add_chat_nonexistent_project(self):
        """Verify no exception raised when adding chat to nonexistent project. (Req 4.3)"""
        chat = {"id": "chat-999", "name": "Ghost Chat", "created_at": 3000.0}
        # Should not raise any exception
        await self.pm.add_chat_to_project("nonexistent_project_id", chat)

    async def test_add_chat_persisted(self):
        """Verify chat persists across get_project calls. (Req 4.4, 7.1)"""
        # First retrieval
        project1 = await self.pm.get_project(self.pid)
        self.assertTrue(any(c["id"] == "chat-001" for c in project1["chats"]))

        # Second retrieval — should still be there
        project2 = await self.pm.get_project(self.pid)
        self.assertTrue(any(c["id"] == "chat-001" for c in project2["chats"]))
        chat = next(c for c in project2["chats"] if c["id"] == "chat-001")
        self.assertEqual(chat["name"], "Test Chat")

    # --- Task 2.2: Chat update and delete tests ---
    # Validates: Requirements 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 7.1

    async def test_edit_chat_name(self):
        """Verify name updated for matching chat. (Req 5.1)"""
        await self.pm.update_chat_in_project(self.pid, "chat-001", name="Renamed Chat")
        project = await self.pm.get_project(self.pid)
        chat = next(c for c in project["chats"] if c["id"] == "chat-001")
        self.assertEqual(chat["name"], "Renamed Chat")

    async def test_edit_chat_preserves_id_and_timestamp(self):
        """Verify id and created_at unchanged after name update. (Req 5.2)"""
        await self.pm.update_chat_in_project(self.pid, "chat-001", name="New Name")
        project = await self.pm.get_project(self.pid)
        chat = next(c for c in project["chats"] if c["id"] == "chat-001")
        self.assertEqual(chat["id"], "chat-001")
        self.assertEqual(chat["created_at"], 1000.0)

    async def test_edit_chat_nonexistent_chat(self):
        """Verify no exception for unknown chat ID. (Req 5.3)"""
        # Should not raise any exception
        await self.pm.update_chat_in_project(self.pid, "nonexistent-chat", name="Ghost")

    async def test_delete_chat(self):
        """Verify chat removed from list. (Req 6.1)"""
        await self.pm.delete_chat_from_project(self.pid, "chat-001")
        project = await self.pm.get_project(self.pid)
        self.assertFalse(any(c["id"] == "chat-001" for c in project["chats"]))

    async def test_delete_chat_count(self):
        """Verify len(chats) decreases by 1. (Req 6.2)"""
        project_before = await self.pm.get_project(self.pid)
        count_before = len(project_before["chats"])
        await self.pm.delete_chat_from_project(self.pid, "chat-001")
        project_after = await self.pm.get_project(self.pid)
        self.assertEqual(len(project_after["chats"]), count_before - 1)

    async def test_delete_nonexistent_chat(self):
        """Verify no exception, list unchanged. (Req 6.3)"""
        project_before = await self.pm.get_project(self.pid)
        chats_before = list(project_before["chats"])
        # Should not raise any exception
        await self.pm.delete_chat_from_project(self.pid, "nonexistent-chat-id")
        project_after = await self.pm.get_project(self.pid)
        self.assertEqual(project_after["chats"], chats_before)


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Edge case tests for empty, long, and special-character names.
    Validates: Requirement 7.2
    """

    async def asyncSetUp(self):
        self.pm = ProjectManager()
        self.created_project_ids = []

    async def asyncTearDown(self):
        for pid in self.created_project_ids:
            await self.pm.delete_project(pid)

    async def _create_and_track(self, name, instructions=None):
        project = await self.pm.create_project(name, instructions)
        self.created_project_ids.append(project["id"])
        return project

    # --- Empty string name ---

    async def test_create_project_empty_name(self):
        """Verify creating a project with empty string name succeeds."""
        result = await self._create_and_track("")
        self.assertEqual(result["name"], "")
        self.assertEqual(len(result["id"]), 8)
        fetched = await self.pm.get_project(result["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "")

    # --- Very long name (200+ chars) ---

    async def test_create_project_long_name(self):
        """Verify creating a project with a very long name (200+ chars) succeeds."""
        long_name = "A" * 250
        result = await self._create_and_track(long_name)
        self.assertEqual(result["name"], long_name)
        self.assertEqual(len(result["id"]), 8)
        fetched = await self.pm.get_project(result["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], long_name)

    # --- Special characters and unicode ---

    async def test_create_project_special_characters(self):
        """Verify creating a project with special characters succeeds."""
        special_name = "Test <>&\"'!@#$%^*(){}[]|\\:;,./?"
        result = await self._create_and_track(special_name)
        self.assertEqual(result["name"], special_name)
        fetched = await self.pm.get_project(result["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], special_name)

    async def test_create_project_unicode(self):
        """Verify creating a project with unicode characters succeeds."""
        unicode_name = "项目テスト프로젝트 🚀✨"
        result = await self._create_and_track(unicode_name)
        self.assertEqual(result["name"], unicode_name)
        fetched = await self.pm.get_project(result["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], unicode_name)

    # --- Chat operations with special character names ---

    async def test_chat_add_special_characters(self):
        """Verify adding a chat with special character name works."""
        project = await self._create_and_track("Edge Chat Project")
        chat_info = {
            "id": "edge-chat-001",
            "name": "Chat <>&\"' 🎉",
            "created_at": 1000.0,
        }
        await self.pm.add_chat_to_project(project["id"], chat_info)
        fetched = await self.pm.get_project(project["id"])
        chat = next(c for c in fetched["chats"] if c["id"] == "edge-chat-001")
        self.assertEqual(chat["name"], "Chat <>&\"' 🎉")

    async def test_chat_rename_unicode(self):
        """Verify renaming a chat to a unicode name works."""
        project = await self._create_and_track("Unicode Chat Project")
        chat_info = {"id": "edge-chat-002", "name": "Original", "created_at": 2000.0}
        await self.pm.add_chat_to_project(project["id"], chat_info)
        await self.pm.update_chat_in_project(
            project["id"], "edge-chat-002", name="新しい名前 🌟"
        )
        fetched = await self.pm.get_project(project["id"])
        chat = next(c for c in fetched["chats"] if c["id"] == "edge-chat-002")
        self.assertEqual(chat["name"], "新しい名前 🌟")


class TestConcurrentCRUDInvariants(unittest.IsolatedAsyncioTestCase):
    """Stress tests for repeated/interleaved CRUD invariants."""

    async def asyncSetUp(self):
        self.pm = ProjectManager()
        self.project_a = await self.pm.create_project("Concurrent A")
        self.project_b = await self.pm.create_project("Concurrent B")

    async def asyncTearDown(self):
        await self.pm.delete_project(self.project_a["id"])
        await self.pm.delete_project(self.project_b["id"])

    async def test_concurrent_duplicate_chat_insert_dedup(self):
        """Concurrent inserts with same chat_id should leave one entry."""
        pid = self.project_a["id"]
        chat = {"id": "dup-chat", "name": "Dup", "created_at": 1000.0}

        async def _insert():
            await self.pm.add_chat_to_project(pid, dict(chat))

        await asyncio.gather(*[_insert() for _ in range(40)])

        project = await self.pm.get_project(pid)
        matches = [c for c in project["chats"] if c.get("id") == "dup-chat"]
        self.assertEqual(len(matches), 1)

    async def test_concurrent_mixed_ops_remain_project_isolated(self):
        """Concurrent mixed operations should not leak chats across projects."""
        pid_a = self.project_a["id"]
        pid_b = self.project_b["id"]

        async def _ops_a(i: int):
            cid = f"a-{i}"
            await self.pm.add_chat_to_project(
                pid_a, {"id": cid, "name": f"A {i}", "created_at": float(i)}
            )
            if i % 2 == 0:
                await self.pm.update_chat_in_project(pid_a, cid, name=f"A updated {i}")
            if i % 3 == 0:
                await self.pm.delete_chat_from_project(pid_a, cid)

        async def _ops_b(i: int):
            cid = f"b-{i}"
            await self.pm.add_chat_to_project(
                pid_b, {"id": cid, "name": f"B {i}", "created_at": float(i)}
            )
            if i % 2 == 1:
                await self.pm.update_chat_in_project(pid_b, cid, name=f"B updated {i}")
            if i % 4 == 0:
                await self.pm.delete_chat_from_project(pid_b, cid)

        await asyncio.gather(
            *[_ops_a(i) for i in range(50)], *[_ops_b(i) for i in range(50)]
        )

        project_a = await self.pm.get_project(pid_a)
        project_b = await self.pm.get_project(pid_b)

        self.assertTrue(
            all(str(c.get("id", "")).startswith("a-") for c in project_a["chats"])
        )
        self.assertTrue(
            all(str(c.get("id", "")).startswith("b-") for c in project_b["chats"])
        )


if __name__ == "__main__":
    unittest.main()
