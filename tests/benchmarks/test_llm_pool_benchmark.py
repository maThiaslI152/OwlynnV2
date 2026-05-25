"""
Benchmark: LLM pool concurrent access, cold vs warm pool latency,
and swap manager simulation.

All tests use MockDelayLLM via test overrides.
"""

import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock, patch

sys.modules["mem0"] = MagicMock()

import pytest

from tests.benchmarks.conftest import (
    BENCH_ITERATIONS,
    BENCH_WARMUP,
    LatencyTracker,
    MockDelayLLM,
    ProfileBuilder,
    make_mock_llm,
    setup_benchmark_llms,
    teardown_benchmark_llms,
    time_async_call,
    time_concurrent,
)
from tests.benchmarks.report import BenchmarkEntry, record_entry


@pytest.fixture(autouse=True)
def _clean():

    teardown_benchmark_llms()
    yield
    teardown_benchmark_llms()


# ═══════════════════════════════════════════════════════════════════════════
# Pool concurrent access
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
class TestPoolConcurrentAccess:
    """Measure LLMPool lock contention under concurrent get_*llm() calls."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
    async def test_pool_concurrent_get_small(self, concurrency: int):
        """Concurrent get_small_llm() calls — cached path."""
        from src.agent.llm import LLMPool

        mock = make_mock_llm(delay_ms=0, content="pooled")
        setup_benchmark_llms(small=mock)

        # Warm: ensure pool is populated
        await LLMPool.get_small_llm()

        async def _get():
            return await LLMPool.get_small_llm()

        args_list = [() for _ in range(concurrency * 5)]
        tracker = await time_concurrent(
            _get, args_list, concurrency=concurrency
        )

        entry = BenchmarkEntry(
            name=f"pool_get_small_c{concurrency}",
            category="pool",
            warmup_iters=0,
            measured_iters=tracker.count,
            concurrency=concurrency,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
    async def test_pool_concurrent_get_medium(self, concurrency: int):
        """Concurrent get_medium_llm() calls — tests lock contention."""
        from src.agent.llm import LLMPool

        mock = make_mock_llm(delay_ms=0, content="pooled")
        setup_benchmark_llms(medium=mock)

        # Warm: ensure pool is populated
        await LLMPool.get_medium_llm("default")

        async def _get():
            return await LLMPool.get_medium_llm("default")

        args_list = [() for _ in range(concurrency * 5)]
        tracker = await time_concurrent(
            _get, args_list, concurrency=concurrency
        )

        entry = BenchmarkEntry(
            name=f"pool_get_medium_c{concurrency}",
            category="pool",
            warmup_iters=0,
            measured_iters=tracker.count,
            concurrency=concurrency,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)


# ═══════════════════════════════════════════════════════════════════════════
# Pool cold vs warm
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
class TestPoolColdVsWarm:
    """Measure first-call (cold) vs cached-call (warm) latency for each slot."""

    @pytest.mark.asyncio
    async def test_pool_small_cold_vs_warm(self):
        """First get_small_llm() vs subsequent calls."""
        from src.agent.llm import LLMPool
        LLMPool.clear()

        mock = make_mock_llm(delay_ms=0, content="pooled")
        setup_benchmark_llms(small=mock)

        # Cold call
        cold_start = asyncio.get_running_loop().time()
        _ = await LLMPool.get_small_llm()
        cold_elapsed = (asyncio.get_running_loop().time() - cold_start) * 1000

        # Warm calls
        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS):
            start = asyncio.get_running_loop().time()
            _ = await LLMPool.get_small_llm()
            tracker.record((asyncio.get_running_loop().time() - start))

        entry = BenchmarkEntry(
            name="pool_small_cold_vs_warm",
            category="pool",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"cold_ms": round(cold_elapsed, 2), "warm_p50_ms": round(tracker.p50 * 1000, 2)},
        )
        record_entry(entry)

    @pytest.mark.asyncio
    async def test_pool_medium_warm_cache_hit(self):
        """Medium LLM with same variant returns cached instance instantly."""
        from src.agent.llm import LLMPool
        LLMPool.clear()

        mock = make_mock_llm(delay_ms=0, content="pooled")
        setup_benchmark_llms(medium=mock)

        # First call populates pool
        _ = await LLMPool.get_medium_llm("default")

        # Warm calls with same variant
        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS):
            start = asyncio.get_running_loop().time()
            _ = await LLMPool.get_medium_llm("default")
            tracker.record((asyncio.get_running_loop().time() - start))

        entry = BenchmarkEntry(
            name="pool_medium_warm_same_variant",
            category="pool",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        # Warm cached calls should be near-instant
        assert tracker.p50 * 1000 < 5, (
            f"Pool warm cache p50 {tracker.p50*1000:.1f}ms exceeds 5ms"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Swap manager simulation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
class TestSwapManagerSimulation:
    """Simulate SwapManager HTTP overhead for model swap."""

    @pytest.mark.asyncio
    async def test_swap_manager_mock_roundtrip(self):
        """Simulate full swap cycle: unload + load + poll."""
        # Simulate the swap manager's _poll_until_loaded pattern
        async def _simulate_poll(model_key: str, timeout: int, poll_interval: float):
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(poll_interval)  # mock HTTP round-trip
                return True  # simulate immediate success
            return False

        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS):
            start = asyncio.get_running_loop().time()
            await asyncio.sleep(0.05)  # unload latency
            await asyncio.sleep(0.05)  # load request latency
            await _simulate_poll("test-model", 10, 0.5)  # poll latency
            elapsed = asyncio.get_running_loop().time() - start
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="swap_manager_mock_roundtrip",
            category="pool",
            warmup_iters=0,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"simulated_unload_ms": 50, "simulated_load_ms": 50, "simulated_poll_ms": 500},
        )
        record_entry(entry)

        # Simulated swap should complete in ~600ms
        assert tracker.p50 * 1000 < 800, (
            f"Swap simulation p50 {tracker.p50*1000:.1f}ms exceeds 800ms"
        )
