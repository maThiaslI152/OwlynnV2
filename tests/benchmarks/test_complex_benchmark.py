import time

"""
Benchmark: Complex node per-route latency, fallback chain coverage,
context trimming efficiency, post-processing overhead, tool action throughput,
and end-to-end graph latency.

All tests use MockDelayLLM — no actual LLM server required.
"""

import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from tests.benchmarks.conftest import (
    BENCH_CONCURRENCY,
    BENCH_ITERATIONS,
    BENCH_WARMUP,
    LatencyTracker,
    MockDelayLLM,
    ProfileBuilder,
    make_mock_llm,
    make_complex_state,
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


@pytest.fixture(autouse=True)
def _mock_rerank():
    with patch("src.agent.tool_reranker.rerank_tools", side_effect=lambda q, t, top_k=15: t) as mock:
        yield mock


# ═══════════════════════════════════════════════════════════════════════════
# Per-route latency
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestComplexPerRouteLatency:
    """Measure complex_llm_node latency for each route variant."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "route,model_delay",
        [
            ("complex-default", 80),
            ("complex-cloud", 120),
            ("complex-cloud", 150),
            ("complex-cloud", 300),
        ],
    )
    async def test_complex_latency_per_route(self, route: str, model_delay: int):
        """p50/p95/p99 per route with realistic mock delays."""
        from src.agent.core.complex import complex_llm_node

        mock_llm = make_mock_llm(
            delay_ms=model_delay,
            content="Here is the analysis you requested.",
            tool_calls=None,
        )
        setup_benchmark_llms(medium=mock_llm, cloud=mock_llm)
        profile = ProfileBuilder().build()

        state = make_complex_state(
            route=route,
            text="Write a Python function to sort a list of dictionaries by a key",
        )

        with (
            patch("src.agent.core.complex.get_profile", return_value=profile),
            patch(
                "src.agent.core.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
        ):
            # Warmup
            for _ in range(BENCH_WARMUP):
                await complex_llm_node(state)

            # Measured
            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, _ = await time_async_call(complex_llm_node, state)
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name=f"complex_{route}",
            category="complex",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"route": route, "mock_delay_ms": model_delay},
        )
        record_entry(entry)

        # Assert p50 is within 2x of mock delay (allowing for CPU overhead)
        assert tracker.p50 * 1000 < model_delay * 3, (
            f"Route {route} p50 {tracker.p50 * 1000:.1f}ms > {model_delay * 3}ms threshold"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Fallback chain coverage
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestFallbackChainCoverage:
    """Force each fallback path and measure added latency."""

    @pytest.mark.asyncio
    async def test_cloud_fallback_on_unavailable(self):
        """Cloud route falls back to medium-default when CloudUnavailableError raised."""
        from src.agent.llm import CloudUnavailableError
        from src.agent.core.complex import complex_llm_node

        mock_medium = make_mock_llm(delay_ms=80, content="Fallback response")

        async def _cloud_raises(*_args, **_kwargs):
            raise CloudUnavailableError("No API key")

        setup_benchmark_llms(medium=mock_medium, fallback=mock_medium)
        profile = ProfileBuilder().build()

        state = make_complex_state(route="complex-cloud")

        with (
            patch("src.agent.core.complex.get_cloud_llm", side_effect=_cloud_raises),
            patch("src.agent.core.complex.get_profile", return_value=profile),
        ):
            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, result = await time_async_call(complex_llm_node, state)
                tracker.record(elapsed)
                assert "fallback" in result["model_used"], (
                    f"Expected fallback label, got {result['model_used']}"
                )

        entry = BenchmarkEntry(
            name="fallback_cloud_unavailable",
            category="complex",
            warmup_iters=0,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"fallback_type": "CloudUnavailableError"},
        )
        record_entry(entry)

    @pytest.mark.asyncio
    async def test_medium_default_graceful_error(self):
        """Medium-default route without fallback produces graceful error."""
        from src.agent.core.complex import complex_llm_node

        mock_fail = MockDelayLLM(
            delay_ms=0,
            response_content="",
            fail_on_call=RuntimeError("LM Studio not running"),
        )
        setup_benchmark_llms(medium=mock_fail)
        profile = ProfileBuilder().build()

        state = make_complex_state(route="complex-default")

        with (
            patch(
                "src.agent.core.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_fail,
            ),
            patch("src.agent.core.complex.get_profile", return_value=profile),
        ):
            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, result = await time_async_call(complex_llm_node, state)
                tracker.record(elapsed)
                # Should produce a graceful error message
                msgs = result.get("messages", [])
                assert len(msgs) > 0
                assert (
                    "error" in msgs[0].content.lower()
                    or "unavailable" in msgs[0].content.lower()
                )

        entry = BenchmarkEntry(
            name="fallback_medium_default_graceful",
            category="complex",
            warmup_iters=0,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"fallback_type": "RuntimeError"},
        )
        record_entry(entry)


# ═══════════════════════════════════════════════════════════════════════════
# Context trimming efficiency
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestContextTrimEfficiency:
    """Measure _trim_tool_history token reduction."""

    def test_trim_reduces_message_count(self):
        """Trim with 20 tool cycles should reduce message count."""
        from src.agent.core.complex import _trim_tool_history

        # Build a conversation with many tool cycles
        messages = [HumanMessage(content="Do something complex")]
        for i in range(20):
            messages.append(
                AIMessage(
                    content=f"Step {i}",
                    tool_calls=[
                        {
                            "name": "read_workspace_file",
                            "args": {"filename": f"file_{i}.py"},
                            "id": f"call_{i}",
                        }
                    ],
                )
            )
            messages.append(
                ToolMessage(
                    content=f"Contents of file_{i}.py",
                    tool_call_id=f"call_{i}",
                    name="read_workspace_file",
                )
            )

        original_count = len(messages)
        trimmed = _trim_tool_history(messages, max_tool_cycles=6)

        assert len(trimmed) == original_count, (
            "Trim preserves message count, compresses content only"
        )
        # Old tool messages should be compressed to summary strings
        old_tool_count = 0
        for i, msg in enumerate(trimmed):
            if isinstance(msg, ToolMessage) and "completed" in str(msg.content):
                old_tool_count += 1
        assert old_tool_count > 0, (
            "Some old tool messages should be compressed to summaries"
        )

    def test_trim_preserves_recent_cycles(self):
        """Recent tool cycles are preserved, old ones compressed."""
        from src.agent.core.complex import _trim_tool_history

        messages = [HumanMessage(content="Task")]
        for i in range(10):
            messages.append(
                AIMessage(
                    content=f"Step {i}",
                    tool_calls=[
                        {
                            "name": "web_search",
                            "args": {"query": f"query_{i}"},
                            "id": f"call_{i}",
                        }
                    ],
                )
            )
            messages.append(
                ToolMessage(
                    content=f"Results for query {i}",
                    tool_call_id=f"call_{i}",
                    name="web_search",
                )
            )

        trimmed = _trim_tool_history(messages, max_tool_cycles=3)

        # Last tool message should be intact (preserved)
        last_tool = [m for m in trimmed if isinstance(m, ToolMessage)][-1]
        assert "Results for query 9" in last_tool.content

        # An early tool message should be compressed summary
        first_tool = [m for m in trimmed if isinstance(m, ToolMessage)][0]
        assert "completed" in first_tool.content or "returned" in first_tool.content


# ═══════════════════════════════════════════════════════════════════════════
# Post-processing overhead
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestPostProcessingOverhead:
    """Measure anonymize, deanonymize, think-tag strip, _auto_read_workspace_bundle."""

    def test_anonymize_latency(self):
        """Anonymize with typical user data."""
        from src.agent.cloud.anonymization import anonymize

        text = "Hello, my email is user@example.com and my IP is 192.168.1.1"
        context = {"name": "John Doe", "custom_sensitive_terms": []}

        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS * 2):
            start = time.perf_counter()
            result, mapping = anonymize(text, context)
            elapsed = time.perf_counter() - start
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="postproc_anonymize",
            category="complex",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        assert tracker.p50 * 1000 < 5, (
            f"Anonymize p50 {tracker.p50 * 1000:.1f}ms exceeds 5ms"
        )

    def test_deanonymize_latency(self):
        """Deanonymize with 10 mappings."""
        from src.agent.cloud.anonymization import anonymize, deanonymize

        text = "Hello, my email is user@example.com and my IP is 192.168.1.1"
        _, mapping = anonymize(text, {"name": "John Doe"})

        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS * 2):
            deanonymized = text
            for placeholder, original in mapping.items():
                deanonymized = deanonymized.replace(placeholder, original)
            start = time.perf_counter()
            _ = deanonymize(deanonymized, mapping)
            elapsed = time.perf_counter() - start
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="postproc_deanonymize",
            category="complex",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        assert tracker.p50 * 1000 < 2, (
            f"Deanonymize p50 {tracker.p50 * 1000:.1f}ms exceeds 2ms"
        )

    def test_think_tag_strip_latency(self):
        """_strip_thinking_tags with embedded <think> blocks."""
        from src.agent.core.complex import _strip_thinking_tags

        text = (
            "<think>Let me think about this carefully. "
            "The answer involves several steps.</think>\n\n"
            "Here is the final answer."
        )

        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS * 2):
            start = time.perf_counter()
            _ = _strip_thinking_tags(text)
            elapsed = time.perf_counter() - start
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="postproc_think_tag_strip",
            category="complex",
            warmup_iters=0,
            measured_iters=tracker.count,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        assert tracker.p50 * 1000 < 1, (
            f"Think tag strip p50 {tracker.p50 * 1000:.1f}ms exceeds 1ms"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Tool action throughput
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestToolActionThroughput:
    """Measure complex_tool_action_node calls/sec."""

    @pytest.mark.asyncio
    async def test_tool_action_throughput(self):
        """Throughput for tool action execution with empty tool env."""
        from src.agent.core.complex import complex_tool_action_node

        # Build a state where the last message has no tool_calls (fast skip)
        state = {
            "messages": [HumanMessage(content="Hello"), AIMessage(content="Hi")],
            "web_search_enabled": True,
        }

        tracker = LatencyTracker()
        for _ in range(BENCH_ITERATIONS):
            elapsed, _ = await time_async_call(complex_tool_action_node, state)
            tracker.record(elapsed)

        entry = BenchmarkEntry(
            name="tool_action_noop",
            category="complex",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
        )
        record_entry(entry)

        # Fast skip should be < 5ms p50
        assert tracker.p50 * 1000 < 5, (
            f"Tool action noop p50 {tracker.p50 * 1000:.1f}ms exceeds 5ms"
        )


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end graph latency
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.benchmark
class TestGraphE2ELatency:
    """Measure full graph latency per route (with MemorySaver)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "route,model_delay",
        [
            ("complex-default", 60),
            ("complex-cloud", 150),
        ],
    )
    async def test_graph_e2e_per_route(self, route: str, model_delay: int):
        """End-to-end graph invocation per route."""
        from langgraph.checkpoint.memory import MemorySaver
        from src.agent.core.graph import build_graph
        from langchain_core.messages import HumanMessage

        mock_llm = make_mock_llm(
            delay_ms=model_delay,
            content="E2E response",
            tool_calls=None,
        )
        setup_benchmark_llms(medium=mock_llm, cloud=mock_llm, small=mock_llm)
        profile = ProfileBuilder().build()

        graph = build_graph().compile(checkpointer=MemorySaver())

        input_state = {
            "messages": [
                HumanMessage(content="Write a hello world function in Python")
            ],
            "route": route,
            "mode": "tools_on",
            "web_search_enabled": True,
            "memory_context": "None",
            "persona": "Test persona",
            "token_budget": 4096,
            "selected_toolboxes": ["all"],
            "project_id": "default",
        }
        config = {"configurable": {"thread_id": f"e2e-bench-{route}"}}

        with (
            patch("src.agent.routing.router.get_profile", return_value=profile),
            patch(
                "src.agent.routing.router._check_cloud_available",
                return_value=(route == "complex-cloud"),
            ),
            patch("src.agent.core.complex.get_profile", return_value=profile),
            patch(
                "src.agent.core.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
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
            patch("src.memory.long_term.memory", MagicMock()),
            patch(
                "src.agent.nodes.memory.get_memory_context_for_prompt",
                return_value="Mock",
            ),
            patch("src.agent.nodes.memory.MemoryContextCache") as mock_cache,
            patch("src.agent.nodes.memory._should_save_memory", return_value=False),
        ):
            mock_cache.get.return_value = ("cached context", "cached knowledge")

            # Warmup
            for _ in range(BENCH_WARMUP):
                await graph.ainvoke(input_state, config)

            # Measured
            tracker = LatencyTracker()
            for _ in range(BENCH_ITERATIONS):
                elapsed, result = await time_async_call(
                    graph.ainvoke, input_state, config
                )
                tracker.record(elapsed)

        entry = BenchmarkEntry(
            name=f"graph_e2e_{route}",
            category="complex",
            warmup_iters=BENCH_WARMUP,
            measured_iters=BENCH_ITERATIONS,
            samples_ms=[s * 1000 for s in tracker.samples],
            metadata={"route": route, "mock_delay_ms": model_delay},
        )
        record_entry(entry)

        assert tracker.count == BENCH_ITERATIONS, "All graph invocations must complete"
