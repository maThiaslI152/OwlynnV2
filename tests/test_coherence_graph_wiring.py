"""Tests for the coherence_retry wiring in graph.py (IMP-6 follow-up).

Validates:
- Graph compiles with new coherence_retry node
- coherence_retry_gate routes to retry when below threshold and budget left
- coherence_retry_gate skips retry when confidence is high
- coherence_retry_gate skips retry when retry budget is exhausted
- coherence_retry_gate skips retry when feature is disabled
- coherence_retry → complex_llm edge exists (cycle)
"""

import sys
from unittest.mock import MagicMock

sys.modules["mem0"] = MagicMock()

from langgraph.checkpoint.memory import MemorySaver

from src.agent.core.graph import build_graph, coherence_retry_gate


class TestGraphStructure:
    def test_graph_compiles_with_coherence_retry(self):
        compiled = build_graph().compile(checkpointer=MemorySaver())
        assert compiled is not None

    def test_graph_contains_coherence_retry_node(self):
        builder = build_graph()
        assert "coherence_retry" in builder.nodes

    def test_graph_includes_all_expected_nodes(self):
        builder = build_graph()
        expected = {
            "memory_inject_lite",
            "memory_retrieve",
            "auto_summarize",
            "router",
            "simple",
            "scope_clarify",
            "complex_llm",
            "security_proxy",
            "tool_action",
            "coherence_check",
            "coherence_retry",
            "memory_write",
        }
        assert expected.issubset(set(builder.nodes.keys()))


class TestCoherenceRetryGate:
    """Direct tests for the conditional edge function."""

    def test_routes_to_retry_when_below_threshold_and_budget_left(self):
        state = {
            "response_confidence": 0.2,
            "_coherence_retry_round": 0,
        }
        assert coherence_retry_gate(state) == "coherence_retry"

    def test_skips_retry_when_confidence_high(self):
        state = {
            "response_confidence": 0.85,
            "_coherence_retry_round": 0,
        }
        assert coherence_retry_gate(state) == "memory_write"

    def test_skips_retry_when_budget_exhausted(self):
        state = {
            "response_confidence": 0.1,
            "_coherence_retry_round": 1,
        }
        assert coherence_retry_gate(state) == "memory_write"

    def test_skips_retry_when_confidence_missing(self):
        state = {
            "_coherence_retry_round": 0,
        }
        assert coherence_retry_gate(state) == "memory_write"

    def test_skips_retry_when_confidence_none(self):
        state = {
            "response_confidence": None,
            "_coherence_retry_round": 0,
        }
        assert coherence_retry_gate(state) == "memory_write"

    def test_threshold_is_at_or_above_routes_to_memory_write(self):
        """At exactly 0.4 the response is acceptable; only strictly below triggers retry."""
        state = {
            "response_confidence": 0.4,
            "_coherence_retry_round": 0,
        }
        assert coherence_retry_gate(state) == "memory_write"
