import unittest
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory.project import ProjectManager


class TestProjectCategoryField(unittest.IsolatedAsyncioTestCase):
    """Tests for the category field on projects (Requirement 6.3)."""

    async def asyncSetUp(self):
        self.pm = ProjectManager()
        self.project = await self.pm.create_project("Category Test Project")

    async def asyncTearDown(self):
        if hasattr(self, "project") and self.project:
            await self.pm.delete_project(self.project["id"])

    async def test_default_project_has_category(self):
        """The default project includes category field set to 'general'."""
        default_project = await self.pm.get_project("default")
        self.assertIsNotNone(default_project)
        self.assertIn("category", default_project)
        self.assertEqual(default_project["category"], "general")

    async def test_new_project_has_category(self):
        """Newly created projects have category='general' by default."""
        self.assertIn("category", self.project)
        self.assertEqual(self.project["category"], "general")

    async def test_update_project_category(self):
        """update_project() accepts and persists category changes."""
        updated = await self.pm.update_project(self.project["id"], category="cybersec")
        self.assertEqual(updated["category"], "cybersec")

        # Verify persistence by re-reading
        fetched = await self.pm.get_project(self.project["id"])
        self.assertEqual(fetched["category"], "cybersec")

    async def test_update_category_to_various_values(self):
        """Category can be set to any valid category string."""
        for cat in [
            "cybersec",
            "writing",
            "research",
            "development",
            "data",
            "general",
        ]:
            updated = await self.pm.update_project(self.project["id"], category=cat)
            self.assertEqual(updated["category"], cat)


if __name__ == "__main__":
    unittest.main()
