"""
Stress tests for concurrent operations on MemoryManager and PersonalAssistant.
"""

import asyncio
import time
import unittest

from src.memory.memory_manager import (
    load_memories,
    save_memory,
    search_memories,
)
from src.memory.personal_assistant import (
    load_interests,
    load_topics,
    track_topic,
    update_interests,
)


class TestMemoryCRUDStress(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Clear out memories to start fresh
        self.test_id = str(time.time())

    async def test_concurrent_stm_saves(self):
        """Concurrent saves to STM should not lose any facts."""
        num_tasks = 40
        facts_to_save = [f"Stress fact {self.test_id} #{i}" for i in range(num_tasks)]

        async def _save_fact(fact):
            await save_memory(fact)

        await asyncio.gather(*[_save_fact(f) for f in facts_to_save])

        memories = await load_memories()
        saved_facts = {m.get("fact") for m in memories}

        # Verify all our unique facts made it
        for fact in facts_to_save:
            self.assertIn(fact, saved_facts)

    async def test_concurrent_personal_assistant_updates(self):
        """Concurrent updates to topics and interests should not clobber each other."""
        num_tasks = 50
        category = f"stress_category_{self.test_id}"
        topic_name = "concurrent_topic"

        async def _update():
            await track_topic(category, topic_name, strength=1.0)
            await update_interests({f"stress_interest_{self.test_id}": True})

        await asyncio.gather(*[_update() for _ in range(num_tasks)])

        topics = await load_topics()
        self.assertIn(category, topics)

        topic_entry = next(
            (t for t in topics[category] if t["name"] == topic_name), None
        )
        self.assertIsNotNone(topic_entry)
        self.assertEqual(topic_entry["occurrences"], num_tasks)

        interests = await load_interests()
        self.assertIn(f"stress_interest_{self.test_id}", interests)
        self.assertEqual(
            interests[f"stress_interest_{self.test_id}"]["count"], num_tasks
        )


if __name__ == "__main__":
    unittest.main()
