"""
Stress tests for concurrent operations on MemoryManager and PersonalAssistant.
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from src.memory.memory_manager import (
    save_memory,
    search_memories,
    load_memories,
)
from src.memory.personal_assistant import (
    track_topic,
    update_interests,
    load_topics,
    load_interests,
)


class TestMemoryCRUDStress(unittest.TestCase):
    def setUp(self):
        # Clear out memories to start fresh

        # Note: We do not clear topics/interests strictly here to avoid wiping local dev data,
        # but we use unique keys to isolate test data.
        self.test_id = str(time.time())

    def test_concurrent_stm_saves(self):
        """Concurrent saves to STM should not lose any facts."""
        num_threads = 40
        facts_to_save = [f"Stress fact {self.test_id} #{i}" for i in range(num_threads)]

        def _save_fact(fact):
            save_memory(fact)

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(_save_fact, facts_to_save))

        memories = load_memories()
        saved_facts = {m.get("fact") for m in memories}

        # Verify all our unique facts made it
        for fact in facts_to_save:
            self.assertIn(fact, saved_facts)

    def test_concurrent_personal_assistant_updates(self):
        """Concurrent updates to topics and interests should not clobber each other."""
        num_threads = 50
        category = f"stress_category_{self.test_id}"
        topic_name = "concurrent_topic"

        def _update(_):
            track_topic(category, topic_name, strength=1.0)
            update_interests({f"stress_interest_{self.test_id}": True})

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(_update, range(num_threads)))

        topics = load_topics()
        self.assertIn(category, topics)

        topic_entry = next(
            (t for t in topics[category] if t["name"] == topic_name), None
        )
        self.assertIsNotNone(topic_entry)
        self.assertEqual(topic_entry["occurrences"], num_threads)

        interests = load_interests()
        self.assertIn(f"stress_interest_{self.test_id}", interests)
        self.assertEqual(
            interests[f"stress_interest_{self.test_id}"]["count"], num_threads
        )


if __name__ == "__main__":
    unittest.main()
