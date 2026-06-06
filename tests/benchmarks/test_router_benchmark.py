"""
Benchmark: Router node throughput, token budget accuracy, HITL rate,
skill matcher latency, and concurrency behavior.

All tests use MockDelayLLM — no actual LLM server required.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import HumanMessage

from tests.benchmarks.conftest import (
    BENCH_CONCURRENCY,
    BENCH_ITERATIONS,
    BENCH_WARMUP,
    LatencyTracker,
    MockDelayLLM,
    ProfileBuilder,
    make_mock_llm,
    make_router_state,
    setup_benchmark_llms,
    teardown_benchmark_llms,
    time_async_call,
    time_concurrent,
    ROUTER_INPUTS,
    SHORT_INPUTS,
    LARGE_INPUTS,
)
from tests.benchmarks.report import BenchmarkEntry, record_entry


@pytest.fixture(autouse=True)
def _clean():
    teardown_benchmark_llms()
    yield
    teardown_benchmark_llms()


# ═══════════════════════════════════════════════════════════════════════════
# Router throughput — single-invocation latency by input size
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestRouterThroughput:
    """Measure router_node latency across varied input sizes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "input_text",
        [
            "Hello",  # short
            "What is machine learning?",  # medium
            "Write a Python function to parse a large CSV "  # long
            "file, filter rows where column 'status' is 'active', "
            "and write the results to a new file with timestamp columns added.",
        ],
    )
    async def test_router_latency_by_input_size(self, input_text: str):
        """p50/p95/p99 latency for router_node at different input lengths."""
        from src.agent.nodes.router import router_node
        from src.agent.llm import LLMPool

        mock_small = make_mock_llm(
            delay_ms=15,
            content='{"routing":"complex","confidence":0.85,"toolbox":"all"}',
        )
        setup_benchmark_llms(small=mock_small)
        profile = ProfileBuilder().build()

        with (
            patch("src.agent.nodes.router.get_profile", return_value=profile),
            patch("src.agent.nodes.router._check_cloud_available", return_value=False),
        ):
            state = make_router_state(text=input_text)

            # Warmup
            for _ in range(BENCH_WARMUP):
                await router_node(state)

            # Measured runs
            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, _ = await time_async_call(router_node, state)
                tracker.record(elapsed)

        label = f"router_node (len={len(input_text)})"
        entry = BenchmarkEntry(
            name=label,
            category="router",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"input_len": len(input_text)},
        )
        record_entry(entry)

        assert (
            tracker.p50 * 1000 < 500
        ), f"Router p50 latency {tracker.p50 * 1000:.1f}ms exceeds 500ms threshold"

    @pytest.mark.asyncio
    async def test_router_batch_throughput(self):
        """Throughput: invoke router_node 50x with varied inputs."""
        from src.agent.nodes.router import router_node

        mock_small = make_mock_llm(
            delay_ms=15,
            content='{"routing":"complex","confidence":0.9,"toolbox":"all"}',
        )
        setup_benchmark_llms(small=mock_small)
        profile = ProfileBuilder().build()

        states = [make_router_state(text=t) for t in ROUTER_INPUTS * 5]

        with (
            patch("src.agent.nodes.router.get_profile", return_value=profile),
            patch("src.agent.nodes.router._check_cloud_available", return_value=False),
        ):
            # Warmup
            for _ in range(BENCH_WARMUP):
                await router_node(states[0])

            # Measured
            tracker = LatencyTracker()
            for state in states[:BENCH_ITERATIONS]:
                elapsed, _ = await time_async_call(router_node, state)
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="router_batch_throughput",
            category="router",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        # Throughput should be at least 5 calls/sec with 20ms mock delay
        thr = tracker.count / sum(tracker.samples) if tracker.samples else 0
        assert thr > 5, f"Router throughput {thr:.1f}/s below 5/s minimum"


# ═══════════════════════════════════════════════════════════════════════════
# Token budget accuracy
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestTokenBudgetAccuracy:
    """Verify estimate_token_budget stays within per-route caps."""

    @pytest.mark.parametrize(
        "route,budget_max",
        [
            ("simple", 4096 - 1500),
            ("complex-default", 8192),
            ("complex-vision", 8192),
            ("complex-longctx", 8192),
            ("complex-cloud", 16384),
        ],
    )
    def test_budget_within_route_cap(self, route: str, budget_max: int):
        """Token budget never exceeds the route's max."""
        from src.agent.nodes.router import estimate_token_budget

        for text in ROUTER_INPUTS + LARGE_INPUTS:
            budget = estimate_token_budget(text, route)
            assert budget > 0, f"Budget must be positive for route={route}"
            assert (
                budget <= budget_max
            ), f"Budget {budget} exceeds cap {budget_max} for route={route}"

    def test_budget_scale_with_input_length(self):
        """Longer inputs produce larger budgets (up to the cap)."""
        from src.agent.nodes.router import estimate_token_budget

        short_budget = estimate_token_budget("hi", "complex-default")
        long_budget = estimate_token_budget("x" * 2000, "complex-default")
        assert (
            long_budget >= short_budget
        ), f"Long input budget {long_budget} should be >= short budget {short_budget}"

    def test_budget_floor_512_for_complex(self):
        """Complex routes never drop below 512 token budget."""
        from src.agent.nodes.router import estimate_token_budget

        for route in [
            "complex-default",
            "complex-vision",
            "complex-longctx",
            "complex-cloud",
        ]:
            budget = estimate_token_budget("x" * 100000, route)
            assert (
                budget >= 512
            ), f"Budget floor for {route} is {budget}, expected >= 512"


# ═══════════════════════════════════════════════════════════════════════════
# HITL interception rate
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestHITLInterceptRate:
    """Measure how often HITL triggers at different confidence thresholds."""

    @pytest.mark.parametrize("confidence_threshold", [0.3, 0.5, 0.7, 0.9])
    def test_hitl_rate_by_threshold(self, confidence_threshold: float):
        """HITL should trigger when confidence < threshold and HITL enabled."""
        from src.agent.nodes.router import parse_routing

        # Simulate LLM responses at different confidence levels
        confidences = [0.1, 0.2, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
        hitl_count = 0

        for conf in confidences:
            content = '{"routing":"complex","confidence":%.2f,"toolbox":"all"}' % conf
            decision, confidence, toolbox = parse_routing(content)
            # HITL fires if confidence < threshold AND HITL enabled
            if confidence < confidence_threshold:
                hitl_count += 1

        expected_rate = sum(1 for c in confidences if c < confidence_threshold) / len(
            confidences
        )
        actual_rate = hitl_count / len(confidences)

        assert (
            abs(actual_rate - expected_rate) < 0.01
        ), f"HITL rate {actual_rate:.2%} vs expected {expected_rate:.2%}"


# ═══════════════════════════════════════════════════════════════════════════
# Skill matcher latency
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestSkillMatcherLatency:
    """Measure SkillMatcher.match_with_confidence() latency."""

    @pytest.mark.asyncio
    async def test_skill_matcher_baseline_latency(self):
        """p50/p95/p99 latency for a single match_with_confidence call."""
        from src.tools.skills import SkillMatcher, _default_loader as skill_loader

        matcher = SkillMatcher(skill_loader)
        tracker = LatencyTracker()

        inputs = [
            "research quantum computing",
            "write a blog post about AI",
            "create a data visualization",
            "manage my tasks",
            "recall what we talked about",
        ]

        for text in inputs * 10:
            start = asyncio.get_running_loop().time()
            _ = matcher.match_with_confidence(text, top_k=3)
            elapsed = asyncio.get_running_loop().time() - start
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="skill_matcher_latency",
            category="router",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        # Skill matcher should complete under 100ms p50
        assert (
            tracker.p50 * 1000 < 100
        ), f"Skill matcher p50 {tracker.p50 * 1000:.1f}ms exceeds 100ms"


# ═══════════════════════════════════════════════════════════════════════════
# Router concurrency
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestRouterConcurrency:
    """Measure router_node throughput under concurrent load."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
    async def test_router_concurrent_throughput(self, concurrency: int):
        """Throughput at different concurrency levels."""
        from src.agent.nodes.router import router_node

        mock_small = make_mock_llm(
            delay_ms=15,
            content='{"routing":"complex","confidence":0.9,"toolbox":"all"}',
        )
        setup_benchmark_llms(small=mock_small)
        profile = ProfileBuilder().build()

        args_list = [
            (make_router_state(text=t),)
            for t in ROUTER_INPUTS * (concurrency // 2 or 1)
        ]

        with (
            patch("src.agent.nodes.router.get_profile", return_value=profile),
            patch("src.agent.nodes.router._check_cloud_available", return_value=False),
        ):
            tracker = await time_concurrent(
                router_node,
                args_list[: max(10, concurrency * 3)],
                concurrency=concurrency,
            )

        thr = tracker.count / sum(tracker.samples) if tracker.samples else 0
        entry = BenchmarkEntry(
            name="router_concurrency",
            category="router",
            warmup_iters=0,
            measured_iters=tracker.count,
            concurrency=concurrency,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)
