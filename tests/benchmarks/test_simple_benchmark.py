"""
Benchmark: Simple node latency by input size, fallback path overhead,
and concurrency throughput.

All tests use MockDelayLLM — no actual LLM server required.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest

from tests.benchmarks.conftest import (
    BENCH_CONCURRENCY,
    BENCH_ITERATIONS,
    BENCH_WARMUP,
    LatencyTracker,
    MockDelayLLM,
    make_mock_llm,
    make_fail_llm,
    make_simple_state,
    setup_benchmark_llms,
    teardown_benchmark_llms,
    time_async_call,
    time_concurrent,
    SHORT_INPUTS,
)
from tests.benchmarks.report import BenchmarkEntry, record_entry


@pytest.fixture(autouse=True)
def _clean():

    teardown_benchmark_llms()
    yield
    teardown_benchmark_llms()


# ═══════════════════════════════════════════════════════════════════════════
# Simple node latency by input size
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
class TestSimpleLatency:
    """Measure simple_node latency across input sizes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("input_text,label", [
        ("Hello", "short"),
        ("What is the capital of Thailand?", "medium"),
        ("Explain the difference between HTTP/1.1 and HTTP/2 in terms of "
         "multiplexing, header compression, and server push.", "long"),
    ])
    async def test_simple_latency_by_input_size(self, input_text: str, label: str):
        """p50/p95/p99 latency for simple_node at different input lengths."""
        from src.agent.nodes.simple import simple_node
        from src.agent.llm import LLMPool

        mock_small = make_mock_llm(delay_ms=15, content="Mock simple response")
        setup_benchmark_llms(small=mock_small)

        state = make_simple_state(text=input_text)

        # Warmup
        for _ in range(BENCH_WARMUP):
            await simple_node(state)

        # Measured
        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS):
            elapsed, _ = await time_async_call(simple_node, state)
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name=f"simple_node_{label}",
            category="simple",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"input_len": len(input_text)},
        )
        record_entry(entry)

        assert tracker.p50 * 1000 < 300, (
            f"Simple node p50 {tracker.p50*1000:.1f}ms exceeds 300ms threshold"
        )

    @pytest.mark.asyncio
    async def test_simple_batch_throughput(self):
        """Throughput: invoke simple_node 50x."""
        from src.agent.nodes.simple import simple_node

        mock_small = make_mock_llm(delay_ms=15, content="Hi there!")
        setup_benchmark_llms(small=mock_small)

        states = [make_simple_state(text=t) for t in SHORT_INPUTS * 10]

        # Warmup
        for _ in range(BENCH_WARMUP):
            await simple_node(states[0])

        tracker = LatencyTracker()
        for state in states[:BENCH_ITERATIONS]:
            elapsed, _ = await time_async_call(simple_node, state)
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="simple_batch_throughput",
            category="simple",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        thr = tracker.count / sum(tracker.samples) if tracker.samples else 0
        assert thr > 10, f"Simple throughput {thr:.1f}/s below 10/s minimum"


# ═══════════════════════════════════════════════════════════════════════════
# Simple node fallback overhead
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
class TestSimpleFallback:
    """Measure penalty when small LLM fails and falls back to medium."""

    @pytest.mark.asyncio
    async def test_simple_fallback_latency(self):
        """Latency when small LLM raises and medium is used as fallback."""
        from src.agent.nodes.simple import simple_node

        # Small LLM fails, medium succeeds
        mock_small = MockDelayLLM(
            delay_ms=0, response_content="", fail_on_call=RuntimeError("Small failed")
        )
        mock_medium = make_mock_llm(delay_ms=80, content="Fallback response")
        setup_benchmark_llms(small=mock_small, medium=mock_medium)

        state = make_simple_state(text="Hello")

        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS):
            elapsed, _ = await time_async_call(simple_node, state)
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="simple_fallback_latency",
            category="simple",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"fallback_triggered": True},
        )
        record_entry(entry)

        # Fallback should add latency but complete
        assert tracker.count == BENCH_ITERATIONS


# ═══════════════════════════════════════════════════════════════════════════
# Simple node concurrency
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
class TestSimpleConcurrency:
    """Measure simple_node throughput under concurrent load."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
    async def test_simple_concurrent_throughput(self, concurrency: int):
        """Throughput at different concurrency levels."""
        from src.agent.nodes.simple import simple_node

        mock_small = make_mock_llm(delay_ms=10, content="Quick answer")
        setup_benchmark_llms(small=mock_small)

        args_list = [
            (make_simple_state(text=t),) for t in SHORT_INPUTS * (concurrency // 2 or 1)
        ]

        tracker = await time_concurrent(
            simple_node,
            args_list[:max(10, concurrency * 3)],
            concurrency=concurrency,
        )

        entry = BenchmarkEntry(
            name="simple_concurrency",
            category="simple",
            warmup_iters=0,
            measured_iters=tracker.count,
            concurrency=concurrency,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)
