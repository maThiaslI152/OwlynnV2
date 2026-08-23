"""
Unit tests for persona management, dynamic persona loading, and completions API routing.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock mem0 to prevent DB connection issues during standalone tests
sys.modules["mem0"] = MagicMock()

from src.memory.persona_manager import (
    PERSONAS_DIR,
    get_persona_by_id,
    list_personas,
    save_custom_persona,
)


class TestPersonaManager(unittest.TestCase):
    """Verifies that persona profiles are managed, listed, and loaded correctly."""

    def test_list_personas_includes_builtins(self):
        """list_personas should return all built-in personas by default."""
        personas = list_personas()
        ids = {p["id"] for p in personas}
        self.assertIn("default", ids)
        self.assertIn("coder", ids)
        self.assertIn("writer", ids)
        self.assertIn("researcher", ids)

    def test_get_persona_by_id_builtin(self):
        """get_persona_by_id should return built-in specs correctly."""
        coder = get_persona_by_id("coder")
        self.assertEqual(coder["id"], "coder")
        self.assertEqual(coder["name"], "Owlynn Coder")
        self.assertIn("Expert Software Engineering Lead", coder["role"])

    def test_get_persona_by_id_fallback(self):
        """get_persona_by_id should gracefully fall back to default if ID is missing or invalid."""
        fallback = get_persona_by_id("nonexistent_id")
        self.assertEqual(fallback["id"], "default")

        fallback_empty = get_persona_by_id(None)
        self.assertEqual(fallback_empty["id"], "default")

    def test_save_and_retrieve_custom_persona(self):
        """save_custom_persona persists to disk and get_persona_by_id loads it successfully."""
        custom_spec = {
            "id": "helper-bot",
            "name": "Helper Bot",
            "role": "Silly Helper",
            "tone": "hyperactive",
            "instructions": "Be silly and suggest random recipes.",
            "allowed_toolboxes": ["memory"],
        }

        saved = save_custom_persona(custom_spec)
        self.assertTrue(saved)

        try:
            # Check retrieved persona
            retrieved = get_persona_by_id("helper-bot")
            self.assertEqual(retrieved["id"], "helper-bot")
            self.assertEqual(retrieved["name"], "Helper Bot")
            self.assertEqual(retrieved["tone"], "hyperactive")

            # Verify listed personas includes it
            all_personas = list_personas()
            ids = {p["id"] for p in all_personas}
            self.assertIn("helper-bot", ids)

        finally:
            # Cleanup custom persona file
            custom_file = PERSONAS_DIR / "helper-bot.json"
            if custom_file.exists():
                custom_file.unlink()

    def test_save_custom_persona_built_in_overwrite_prevention(self):
        """save_custom_persona should refuse to overwrite built-in persona IDs."""
        bad_spec = {
            "id": "coder",
            "name": "Hacker Coder",
            "role": "Destructive hacker",
            "tone": "edgy",
            "instructions": "Delete everything.",
        }
        saved = save_custom_persona(bad_spec)
        self.assertFalse(saved)

        # Verify original coder spec is intact
        coder = get_persona_by_id("coder")
        self.assertEqual(coder["name"], "Owlynn Coder")


if __name__ == "__main__":
    unittest.main()
