"""
Shared benchmark fixtures: MockDelayLLM, timing helpers, LLMPool override injection,
and ProfileBuilder for quick profile creation.

All benchmarks use mock LLMs that simulate realistic inference latency via asyncio.sleep
— no actual LLM server required.
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

sys.modules["mem0"] = MagicMock()

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.llm import LLMPool

# ── Report output path (shared across benchmarks) ─────────────────────────
_REPORT_DIR = Path(__file__).parent
REPORT_PATH = _REPORT_DIR / "benchmark_report.json"


def _env_int(name: str, default: int) -> int:
    try:
        return int(Path("/dev/null").read_text() or "0") or int(
            __import__("os").environ.get(name, str(default))
        )
    except Exception:
        return default


BENCH_CONCURRENCY = _env_int("BENCH_CONCURRENCY", 4)
BENCH_WARMUP = _env_int("BENCH_WARMUP", 2)
BENCH_ITERATIONS = _env_int("BENCH_ITERATIONS", 50)


# ── MockDelayLLM ──────────────────────────────────────────────────────────


class MockDelayLLM:
    """
    Mock LLM that simulates realistic LM Studio inference latency via asyncio.sleep.

    Configurable delay, response content, and optional tool_calls for the complex path.
    Supports bind() and bind_tools() chaining to match the ChatOpenAI interface.
    """

    def __init__(
        self,
        delay_ms: int = 50,
        response_content: str = "Mock response",
        tool_calls: list | None = None,
        fail_on_call: Exception | None = None,
    ):
        self._delay = delay_ms / 1000.0
        self._content = response_content
        self._tool_calls = tool_calls
        self._fail_on_call = fail_on_call
        # Track call count for observability
        self.call_count = 0
        self.total_latency = 0.0

    def bind(self, **kwargs):
        return self

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, messages):
        if self._fail_on_call:
            raise self._fail_on_call
        self.call_count += 1
        await asyncio.sleep(self._delay)
        self.total_latency += self._delay
        return AIMessage(content=self._content, tool_calls=self._tool_calls or [])


def make_mock_llm(
    delay_ms: int = 50,
    content: str = "Mock response",
    tool_calls: list | None = None,
) -> MockDelayLLM:
    """Convenience factory for MockDelayLLM."""
    return MockDelayLLM(
        delay_ms=delay_ms, response_content=content, tool_calls=tool_calls
    )


def make_fail_llm(exc: Exception) -> MockDelayLLM:
    """Factory for a MockDelayLLM that raises on every call."""
    return MockDelayLLM(delay_ms=0, response_content="", fail_on_call=exc)


# ── ProfileBuilder ────────────────────────────────────────────────────────


@dataclass
class ProfileBuilder:
    """Build a user profile dict for benchmark tests without touching filesystem."""

    name: str = "BenchUser"
    cloud_anonymization_enabled: bool = True
    cloud_escalation_enabled: bool = True
    cloud_routing_mode: str = "auto"
    lm_studio_fold_system: bool = False
    router_hitl_enabled: bool = False  # disabled in benchmarks to avoid interrupt()
    route_confidence_threshold: float = 0.6
    skill_clarification_threshold: float = 0.5
    cloud_llm_base_url: str = "https://api.deepseek.com/v1"
    cloud_llm_model_name: str = "deepseek-chat"
    main_llm_base_url: str = "http://127.0.0.1:1234/v1"
    main_llm_model_name: str = (
        "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
    )
    small_llm_base_url: str = "http://127.0.0.1:1234/v1"
    small_llm_model_name: str = (
        "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
    )
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    custom_sensitive_terms: list = field(default_factory=list)
    deepseek_api_key: str = ""
    web_search_enabled: bool = True

    def build(self) -> dict:
        return {
            "name": self.name,
            "cloud_anonymization_enabled": self.cloud_anonymization_enabled,
            "cloud_escalation_enabled": self.cloud_escalation_enabled,
            "cloud_routing_mode": self.cloud_routing_mode,
            "lm_studio_fold_system": self.lm_studio_fold_system,
            "router_hitl_enabled": self.router_hitl_enabled,
            "route_confidence_threshold": self.route_confidence_threshold,
            "skill_clarification_threshold": self.skill_clarification_threshold,
            "cloud_llm_base_url": self.cloud_llm_base_url,
            "cloud_llm_model_name": self.cloud_llm_model_name,
            "main_llm_base_url": self.main_llm_base_url,
            "main_llm_model_name": self.main_llm_model_name,
            "small_llm_base_url": self.small_llm_base_url,
            "small_llm_model_name": self.small_llm_model_name,
            "llm_base_url": self.llm_base_url,
            "custom_sensitive_terms": self.custom_sensitive_terms,
            "deepseek_api_key": self.deepseek_api_key,
            "web_search_enabled": self.web_search_enabled,
        }


# ── Timing helpers ────────────────────────────────────────────────────────


class LatencyTracker:
    """Collect per-invocation latencies and compute percentile stats."""

    def __init__(self):
        self.samples: list[float] = []

    def record(self, elapsed_s: float):
        self.samples.append(elapsed_s)

    @property
    def count(self) -> int:
        return len(self.samples)

    def percentile(self, p: float) -> float:
        """Compute the p-th percentile (e.g. 0.50, 0.95, 0.99)."""
        if not self.samples:
            return 0.0
        s = sorted(self.samples)
        idx = int(len(s) * p)
        if idx >= len(s):
            idx = len(s) - 1
        return s[idx]

    @property
    def p50(self) -> float:
        return self.percentile(0.50)

    @property
    def p95(self) -> float:
        return self.percentile(0.95)

    @property
    def p99(self) -> float:
        return self.percentile(0.99)

    @property
    def mean(self) -> float:
        if not self.samples:
            return 0.0
        return sum(self.samples) / len(self.samples)

    @property
    def min(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max(self) -> float:
        return max(self.samples) if self.samples else 0.0

    def summary(self) -> dict:
        return {
            "count": self.count,
            "min_ms": round(self.min * 1000, 2),
            "max_ms": round(self.max * 1000, 2),
            "mean_ms": round(self.mean * 1000, 2),
            "p50_ms": round(self.p50 * 1000, 2),
            "p95_ms": round(self.p95 * 1000, 2),
            "p99_ms": round(self.p99 * 1000, 2),
            "throughput_ops_per_sec": (
                round(self.count / (self.max - self.min), 2)
                if self.count > 1 and self.max > self.min
                else 0
            ),
        }


async def time_async_call(fn, *args, **kwargs) -> tuple[float, object]:
    """Time a single async function call. Returns (elapsed_seconds, result)."""
    start = asyncio.get_running_loop().time()
    result = await fn(*args, **kwargs)
    elapsed = asyncio.get_running_loop().time() - start
    return elapsed, result


async def time_concurrent(fn, args_list: list, concurrency: int = 4) -> LatencyTracker:
    """Run *fn* concurrently across *args_list*. Returns LatencyTracker."""
    sem = asyncio.Semaphore(concurrency)
    tracker = LatencyTracker()
    results = {}

    async def _worker(idx, args):
        async with sem:
            elapsed, result = await time_async_call(fn, *args)
            tracker.record(elapsed)
            results[idx] = result

    tasks = [_worker(i, args) for i, args in enumerate(args_list)]
    await asyncio.gather(*tasks)
    return tracker


# ── LLMPool override helpers ──────────────────────────────────────────────


def setup_benchmark_llms(
    small: MockDelayLLM | None = None,
    medium: MockDelayLLM | None = None,
    cloud: MockDelayLLM | None = None,
    fallback: MockDelayLLM | None = None,
    complex_local: MockDelayLLM | None = None,
    main: MockDelayLLM | None = None,
) -> dict:
    """Register mock LLMs in LLMPool and return the override dict."""
    overrides = {}
    if main is not None:
        overrides["main"] = main
    if small is not None:
        overrides["small"] = small
    if medium is not None:
        overrides["medium"] = medium
        if "main" not in overrides:
            overrides["main"] = medium
        if fallback is None:
            overrides["fallback"] = medium
        if complex_local is None:
            overrides["complex_local"] = medium
    if cloud is not None:
        overrides["cloud"] = cloud
    if fallback is not None:
        overrides["fallback"] = fallback
    if complex_local is not None:
        overrides["complex_local"] = complex_local
    LLMPool.set_test_overrides(overrides)
    return overrides


def teardown_benchmark_llms():
    LLMPool.clear_test_overrides()
    LLMPool.clear()


# ── Benchmark state helpers ───────────────────────────────────────────────


def make_router_state(
    text: str = "Hello, how are you?",
    web_search: bool = True,
    extra: dict | None = None,
) -> dict:
    """Build a minimal AgentState dict for router_node."""
    state = {
        "messages": [HumanMessage(content=text)],
        "web_search_enabled": web_search,
    }
    if extra:
        state.update(extra)
    return state


def make_complex_state(
    route: str = "complex-default",
    text: str = "Write a Python function to sort a list",
    extra: dict | None = None,
) -> dict:
    """Build a minimal AgentState dict for complex_llm_node."""
    state = {
        "messages": [HumanMessage(content=text)],
        "route": route,
        "mode": "tools_on",
        "web_search_enabled": True,
        "memory_context": "None",
        "persona": "Test persona",
        "response_style": None,
        "security_decision": None,
        "security_reason": None,
        "token_budget": 4096,
        "selected_toolboxes": ["all"],
    }
    if extra:
        state.update(extra)
    return state


def make_simple_state(
    text: str = "Hello",
    extra: dict | None = None,
) -> dict:
    """Build a minimal AgentState dict for simple_node."""
    state = {
        "messages": [HumanMessage(content=text)],
        "token_budget": 256,
        "response_style": None,
        "memory_context": "None",
    }
    if extra:
        state.update(extra)
    return state


# ── Benchmark input generators ────────────────────────────────────────────


SHORT_INPUTS = [
    "Hello",
    "Hi there",
    "Thanks",
    "What time is it?",
    "Goodbye",
]

ROUTER_INPUTS = [
    "Hello",
    "What is the capital of France?",
    "Write a Python function to sort a list of dictionaries by a key",
    "Explain quantum computing in simple terms",
    "Create a REST API endpoint for user registration using FastAPI",
    "What's the weather in Bangkok today?",
    "Refactor this code to use async/await: def fetch_data(url): ...",
    "Compare the performance of B-tree vs LSM-tree for key-value stores",
    "Prove that the square root of 2 is irrational",
    "Analyze this CSV file and create a visualization",
]

COMPLEX_INPUTS = [
    "Write a function to parse CSV data",
    "Explain the difference between TCP and UDP",
    "Create a React component with TypeScript that handles form validation",
    "Solve this differential equation: dy/dx = x^2 + y^2",
    "Implement Dijkstra's algorithm in Rust",
]

LARGE_INPUTS = [
    "x" * 1000,  # ~1KB input
    "x" * 5000,  # ~5KB input
    "x" * 15000,  # ~15KB input
    "x" * 50000,  # ~50KB input
]


# ── Pytest fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_pool_after_test():
    """Auto-clean LLMPool overrides after each test."""
    yield
    teardown_benchmark_llms()


def pytest_sessionfinish(session, exitstatus):
    """Write benchmark_report.json after all tests complete."""
    try:
        from tests.benchmarks.report import print_summary, write_report

        path = write_report()
        print(f"\n[benchmark] Report written to {path}")
        print_summary()
    except Exception:
        pass
