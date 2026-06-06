import time

"""
Benchmark: Memory node overhead — memory_inject and memory_write latency.

These nodes touch Qdrant/Mem0 for context retrieval and storage.
We mock those calls to measure pure node logic overhead.
"""

import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tests.benchmarks.conftest import (
    BENCH_ITERATIONS,
    BENCH_WARMUP,
    LatencyTracker,
    ProfileBuilder,
    teardown_benchmark_llms,
    time_async_call,
)
from tests.benchmarks.report import BenchmarkEntry, record_entry


@pytest.fixture(autouse=True)
def _clean():
    teardown_benchmark_llms()
    yield
    teardown_benchmark_llms()


# ═══════════════════════════════════════════════════════════════════════════
# Memory inject overhead
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestMemoryInject:
    """Measure memory_inject_node call time with mocked Mem0/Qdrant."""

    @pytest.mark.asyncio
    async def test_memory_inject_baseline(self):
        """p50/p95/p99 latency for memory_inject_node (mocked DB calls)."""
        # Mock long_term memory to return empty results quickly
        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = {"results": []}

        profile = ProfileBuilder().build()

        with (
            patch("src.memory.long_term.memory", mock_mem0),
            patch("src.agent.nodes.memory.get_profile", return_value=profile),
            patch(
                "src.agent.nodes.memory.get_persona_by_id",
                return_value={
                    "id": "default",
                    "name": "Owlynn",
                    "role": "General Workspace Assistant",
                    "tone": "friendly",
                    "instructions": "Help the user.",
                    "allowed_toolboxes": ["all"],
                },
            ),
            patch(
                "src.agent.nodes.memory.get_memory_context_for_prompt",
                return_value="Mock context",
            ),
            patch("src.agent.nodes.memory.MemoryContextCache") as mock_cache,
        ):
            mock_cache.get.return_value = None  # force cache miss

            from src.agent.nodes.memory import memory_inject_node

            state = {
                "messages": [HumanMessage(content="Hello, how are you?")],
                "thread_id": "bench-thread-1",
                "project_id": "default",
            }

            # Warmup
            for _ in range(BENCH_WARMUP):
                await memory_inject_node(state)

            # Measured
            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, _ = await time_async_call(memory_inject_node, state)
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="memory_inject_cold_cache",
            category="memory",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"cache_hit": False},
        )
        record_entry(entry)

        # Memory inject should complete quickly with mocked DB
        assert (
            tracker.p50 * 1000 < 50
        ), f"Memory inject p50 {tracker.p50 * 1000:.1f}ms exceeds 50ms threshold"

    @pytest.mark.asyncio
    async def test_memory_inject_cache_hit(self):
        """Latency when context is cached (fast path)."""
        profile = ProfileBuilder().build()

        with (
            patch("src.agent.nodes.memory.get_profile", return_value=profile),
            patch(
                "src.agent.nodes.memory.get_persona_by_id",
                return_value={
                    "id": "default",
                    "name": "Owlynn",
                    "role": "General Workspace Assistant",
                    "tone": "friendly",
                    "instructions": "Help the user.",
                    "allowed_toolboxes": ["all"],
                },
            ),
            patch("src.agent.nodes.memory.MemoryContextCache") as mock_cache,
        ):
            mock_cache.get.return_value = "Cached context string"
            mock_cache.set = MagicMock()

            from src.agent.nodes.memory import memory_inject_node

            state = {
                "messages": [HumanMessage(content="Hello")],
                "thread_id": "bench-thread-2",
                "project_id": "default",
            }

            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, _ = await time_async_call(memory_inject_node, state)
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="memory_inject_cache_hit",
            category="memory",
            warmup_iters=0,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"cache_hit": True},
        )
        record_entry(entry)

        # Cache hit path should be near-instant
        assert (
            tracker.p50 * 1000 < 10
        ), f"Memory inject cache-hit p50 {tracker.p50 * 1000:.1f}ms exceeds 10ms"


# ═══════════════════════════════════════════════════════════════════════════
# Memory write overhead
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestMemoryWrite:
    """Measure memory_write_node call time with mocked storage."""

    @pytest.mark.asyncio
    async def test_memory_write_baseline(self):
        """p50/p95/p99 latency for memory_write_node (mocked storage)."""
        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = {"results": []}

        profile = ProfileBuilder().build()

        with (
            patch("src.memory.long_term.memory", mock_mem0),
            patch("src.agent.nodes.memory.get_profile", return_value=profile),
            patch("src.agent.nodes.memory.record_conversation", return_value=None),
            patch("src.agent.nodes.memory._should_save_memory", return_value=True),
            patch(
                "src.agent.nodes.memory._is_semantically_similar", return_value=False
            ),
            patch("src.agent.nodes.memory.TopicExtractor") as mock_extract,
            patch("src.agent.nodes.memory.MemoryEnricher") as mock_enrich,
            patch("src.agent.nodes.memory.MemoryContextCache") as mock_cache,
        ):
            mock_extract.extract_topics.return_value = []
            mock_extract.extract_interests.return_value = []
            mock_enrich.enrich_memory.return_value = "enriched fact"
            mock_cache.invalidate_on_write = MagicMock()

            from src.agent.nodes.memory import memory_write_node

            state = {
                "messages": [
                    HumanMessage(content="What is Python?"),
                    AIMessage(content="Python is a programming language."),
                ],
                "thread_id": "bench-thread-3",
                "session_id": "bench-session",
                "project_id": "default",
            }

            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, _ = await time_async_call(memory_write_node, state)
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="memory_write_baseline",
            category="memory",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        assert (
            tracker.p50 * 1000 < 50
        ), f"Memory write p50 {tracker.p50 * 1000:.1f}ms exceeds 50ms threshold"

    @pytest.mark.asyncio
    async def test_memory_write_gate_skip(self):
        """Latency when _should_save_memory returns False (fast skip)."""
        profile = ProfileBuilder().build()

        with (
            patch("src.agent.nodes.memory.get_profile", return_value=profile),
            patch("src.agent.nodes.memory._should_save_memory", return_value=False),
        ):
            from src.agent.nodes.memory import memory_write_node

            state = {
                "messages": [
                    HumanMessage(content="Hello"),
                    AIMessage(content="Hi there!"),
                ],
                "thread_id": "bench-thread-4",
                "session_id": "bench-session",
            }

            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, _ = await time_async_call(memory_write_node, state)
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="memory_write_gate_skip",
            category="memory",
            warmup_iters=0,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"gate_rejected": True},
        )
        record_entry(entry)

        assert (
            tracker.p50 * 1000 < 5
        ), f"Memory write gate-skip p50 {tracker.p50 * 1000:.1f}ms exceeds 5ms"


# ═══════════════════════════════════════════════════════════════════════════
# Context formatting cost
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestContextFormatting:
    """Measure format_memory_context cost with varied data sizes."""

    @pytest.mark.parametrize("num_results", [0, 5, 20, 100])
    def test_format_memory_context_size(self, num_results: int):
        """format_memory_context scales linearly with result count."""
        from src.agent.nodes.memory import format_memory_context

        results = [
            {"memory": f"Memory item {i}: This is a test memory entry."}
            for i in range(num_results)
        ]
        profile = {"name": "TestUser", "role": "admin"}
        enhanced = "Enhanced context string with topics and interests"

        tracker = LatencyTracker()
        for _ in range(max(20, BENCH_ITERATIONS)):
            start = time.perf_counter()
            _ = format_memory_context(results, profile, enhanced)
            elapsed = time.perf_counter() - start
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name=f"format_context_n{num_results}",
            category="memory",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"num_results": num_results},
        )
        record_entry(entry)

        # Formatting 100 results should still be fast (< 5ms p50)
        assert (
            tracker.p50 * 1000 < 5
        ), f"Format context p50 {tracker.p50 * 1000:.1f}ms exceeds 5ms for {num_results} results"
