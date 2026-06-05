"""Tests for the cloud cost tracker."""

import sys
from unittest.mock import MagicMock

import pytest

sys.modules["mem0"] = MagicMock()


@pytest.fixture
def tracker():
    from src.agent.cloud_cost_tracker import SessionCostTracker

    return SessionCostTracker()


class TestSessionCostTracker:
    def test_initial_state_is_empty(self, tracker):
        assert tracker.prompt_tokens == 0
        assert tracker.completion_tokens == 0
        assert tracker.total_calls == 0
        assert tracker.failed_calls == 0
        assert tracker.total_tokens == 0
        assert tracker.estimated_cost == 0.0

    def test_record_usage_accumulates(self, tracker):
        tracker.record_usage(prompt_tokens=1500, completion_tokens=800)
        assert tracker.prompt_tokens == 1500
        assert tracker.completion_tokens == 800
        assert tracker.total_tokens == 2300
        assert tracker.total_calls == 1

    def test_record_multiple_calls(self, tracker):
        tracker.record_usage(prompt_tokens=1000, completion_tokens=500)
        tracker.record_usage(prompt_tokens=2000, completion_tokens=300)
        assert tracker.prompt_tokens == 3000
        assert tracker.completion_tokens == 800
        assert tracker.total_calls == 2

    def test_estimated_cost_calculation(self, tracker):
        # 1M input + 1M output = $0.14 + $0.28 = $0.42
        tracker.record_usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert abs(tracker.estimated_cost - 0.42) < 0.001

    def test_cost_rounding(self, tracker):
        # 100 input + 100 output
        tracker.record_usage(prompt_tokens=100, completion_tokens=100)
        expected = round((100 / 1_000_000 * 0.14) + (100 / 1_000_000 * 0.28), 6)
        assert tracker.estimated_cost == expected

    def test_record_failure(self, tracker):
        tracker.record_failure()
        assert tracker.failed_calls == 1
        assert tracker.total_calls == 0
        assert tracker.total_tokens == 0

    def test_summary_contains_all_fields(self, tracker):
        tracker.record_usage(prompt_tokens=500, completion_tokens=200)
        summary = tracker.summary()
        assert "prompt_tokens" in summary
        assert "completion_tokens" in summary
        assert "total_tokens" in summary
        assert "total_calls" in summary
        assert "failed_calls" in summary
        assert "estimated_cost_usd" in summary
        assert "elapsed_seconds" in summary
        assert "pricing" in summary
        assert summary["total_tokens"] == 700
        assert summary["total_calls"] == 1

    def test_reset_clears_all(self, tracker):
        tracker.record_usage(prompt_tokens=1000, completion_tokens=500)
        tracker.reset()
        assert tracker.prompt_tokens == 0
        assert tracker.completion_tokens == 0
        assert tracker.total_calls == 0
        assert tracker.failed_calls == 0

    def test_singleton(self):
        from src.agent.cloud_cost_tracker import get_cost_tracker, reset_cost_tracker

        reset_cost_tracker()
        t1 = get_cost_tracker()
        t2 = get_cost_tracker()
        assert t1 is t2
